from __future__ import annotations

from typing import Any

import pandas as pd

from .zones import zone_mid


# Źródła nie są równoważne. W rankingu stref wejścia chcemy wyżej stawiać
# strefy wynikające z większego kontekstu i płynności, a niżej lokalne filtry.
SOURCE_WEIGHTS: dict[str, int] = {
    "HTF/HIST": 7,
    "PIVOT_CLUSTER": 7,
    "OB/LBM": 4,
    "1:1": 3,
    "FTR": 2,
    "FIBO": 2,
    "S/R": 2,
    "FVG": 1,
}


def get_zone_status(zone: dict[str, Any], current_price: float, atr: float) -> dict[str, Any]:
    """
    Określa praktyczne położenie ceny względem strefy.

    Ranking nie może opierać się wyłącznie na tym, czy cena jest już w strefie.
    Dlatego status jest później używany jako bonus do setupu, a nie jako główny
    warunek sortowania.
    """
    low = float(zone["low"])
    high = float(zone["high"])
    width = max(high - low, 0.0)
    width_pct = width / current_price * 100 if current_price > 0 else 999.0

    if low <= current_price <= high:
        return {
            "status": "W STREFIE",
            "distance": 0.0,
            "distance_pct": 0.0,
            "width_pct": float(width_pct),
            "near": True,
            "in_zone": True,
        }

    if current_price < low:
        distance = low - current_price
    else:
        distance = current_price - high

    distance_pct = distance / current_price * 100 if current_price > 0 else 999.0
    near = distance <= max(atr * 1.5, current_price * 0.03)

    return {
        "status": "BLISKO" if near else "DALEKO",
        "distance": float(distance),
        "distance_pct": float(distance_pct),
        "width_pct": float(width_pct),
        "near": near,
        "in_zone": False,
    }


def zones_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return max(float(a["low"]), float(b["low"])) <= min(float(a["high"]), float(b["high"]))


def zone_overlap_ratio(a: dict[str, Any], b: dict[str, Any]) -> float:
    """Zwraca część mniejszej strefy pokrytą przez drugą strefę."""
    overlap = max(0.0, min(float(a["high"]), float(b["high"])) - max(float(a["low"]), float(b["low"])))
    min_width = max(min(float(a["high"]) - float(a["low"]), float(b["high"]) - float(b["low"])), 1e-12)
    return overlap / min_width


def parse_sources(source: str) -> set[str]:
    """Rozbija źródła klastra na unikalne tagi."""
    return {part.strip() for part in str(source).split("+") if part.strip()}


def source_quality_bonus(zone: dict[str, Any]) -> tuple[int, list[str]]:
    sources = parse_sources(str(zone.get("source", "")))
    weighted = sum(SOURCE_WEIGHTS.get(source, 0) for source in sources)
    bonus = min(weighted, 14)

    reasons: list[str] = []
    if sources:
        reasons.append(f"Jakość źródeł ({', '.join(sorted(sources))}): +{bonus}.")

    # Konfluencja różnych technik ma znaczenie, ale nie może pompować score bez limitu.
    if len(sources) >= 2:
        multi_bonus = min(len(sources) - 1, 3)
        bonus += multi_bonus
        reasons.append(f"Konfluencja {len(sources)} źródeł: +{multi_bonus}.")

    return bonus, reasons


def find_take_profit(entry: float, direction: str, swings: pd.DataFrame, safe_sl: float) -> float:
    """Szuka TP na najbliższym przeciwnym swingu. Gdy brak, używa RR 2:1."""
    risk = abs(entry - safe_sl)
    if risk <= 0:
        return entry

    if direction == "buy":
        highs_above = swings[(swings["type"] == "high") & (swings["price"] > entry)]
        if not highs_above.empty:
            return float(highs_above.iloc[-1]["price"])
        return entry + risk * 2

    lows_below = swings[(swings["type"] == "low") & (swings["price"] < entry)]
    if not lows_below.empty:
        return float(lows_below.iloc[-1]["price"])
    return entry - risk * 2


def calculate_trade_levels(zone: dict[str, Any], current_price: float, atr: float, swings: pd.DataFrame) -> dict[str, float]:
    direction = str(zone["direction"])

    if float(zone["low"]) <= current_price <= float(zone["high"]):
        entry = current_price
    else:
        entry = zone_mid(zone)

    if direction == "buy":
        safe_sl = float(zone["low"]) - atr * 0.50
        aggressive_sl = float(zone["low"]) - atr * 0.15
        tp = find_take_profit(entry, direction, swings, safe_sl)
        risk = entry - safe_sl
        reward = tp - entry
    else:
        safe_sl = float(zone["high"]) + atr * 0.50
        aggressive_sl = float(zone["high"]) + atr * 0.15
        tp = find_take_profit(entry, direction, swings, safe_sl)
        risk = safe_sl - entry
        reward = entry - tp

    rr = reward / risk if risk > 0 else 0.0

    return {
        "entry": float(entry),
        "safe_sl": float(safe_sl),
        "aggressive_sl": float(aggressive_sl),
        "tp": float(tp),
        "rr": float(rr),
    }


def score_zone(
    zone: dict[str, Any],
    trend: str,
    current_price: float,
    atr: float,
    candle_patterns: dict[str, Any],
    rsi_signal: dict[str, Any],
    rsi_divergence: dict[str, Any],
    trade_levels: dict[str, float],
) -> dict[str, Any]:
    """
    Ocena strefy rozdzielona na dwa niezależne elementy:

    1. quality_score — jakość samej strefy, niezależnie od tego, czy cena jest już w środku.
    2. setup_score — czy strefa jest teraz aktywna i czy pojawił się sygnał lokalny.

    Ranking sortujemy głównie po quality_score, żeby słaba lokalna strefa "w cenie"
    nie wyprzedzała mocnej strefy strategicznej, np. 140-156 na TTWO.
    """
    reasons: list[str] = []
    status = get_zone_status(zone, current_price, atr)
    sources = parse_sources(str(zone.get("source", "")))
    meta = zone.get("meta", {}) or {}

    width_pct = float(status["width_pct"])
    distance_pct = float(status["distance_pct"])
    direction = str(zone["direction"])

    # -------------------------
    # 1. JAKOŚĆ STRUKTURALNA
    # -------------------------
    strength = min(max(int(zone.get("strength", 0)), 0), 12)
    quality_score = strength
    reasons.append(f"Bazowa siła strefy: +{strength}.")

    source_bonus, source_reasons = source_quality_bonus(zone)
    quality_score += source_bonus
    reasons.extend(source_reasons)

    # Strefy z danych historycznych i klastrów pivotów powinny mieć realną premię.
    if "HTF/HIST" in sources:
        quality_score += 2
        reasons.append("Historyczna strefa reakcji HTF/HIST: +2.")
    if "PIVOT_CLUSTER" in sources:
        quality_score += 2
        reasons.append("Klaster pivotów / płynności: +2.")

    cluster_points = int(meta.get("cluster_points", 0) or 0)
    if cluster_points >= 3:
        points_bonus = min(cluster_points - 2, 4)
        quality_score += points_bonus
        reasons.append(f"Liczba pivotów w klastrze ({cluster_points}): +{points_bonus}.")

    reaction_pct = float(meta.get("reaction_pct", 0.0) or 0.0)
    if reaction_pct >= 20:
        quality_score += 2
        reasons.append(f"Mocna historyczna reakcja {reaction_pct:.1f}%: +2.")
    elif reaction_pct >= 10:
        quality_score += 1
        reasons.append(f"Widoczna historyczna reakcja {reaction_pct:.1f}%: +1.")

    # Zbyt szerokie strefy są gorsze, węższe i czytelniejsze premiujemy.
    if width_pct <= 6:
        quality_score += 4
        reasons.append(f"Bardzo precyzyjna szerokość strefy ({width_pct:.1f}%): +4.")
    elif width_pct <= 10:
        quality_score += 3
        reasons.append(f"Dobra szerokość strefy ({width_pct:.1f}%): +3.")
    elif width_pct <= 14:
        quality_score += 2
        reasons.append(f"Akceptowalna szerokość strefy ({width_pct:.1f}%): +2.")
    elif width_pct <= 18:
        quality_score -= 1
        reasons.append(f"Strefa dość szeroka ({width_pct:.1f}%): -1.")
    else:
        quality_score -= 10
        reasons.append(f"Strefa za szeroka do rankingu wejść ({width_pct:.1f}%): -10.")

    # Trend ma znaczenie, ale nie może sam zabić dobrego miejsca strategicznego.
    if trend == "wzrostowy" and direction == "buy":
        quality_score += 1
        reasons.append("Zgodność z trendem wzrostowym: +1.")
    elif trend == "spadkowy" and direction == "sell":
        quality_score += 1
        reasons.append("Zgodność z trendem spadkowym: +1.")
    elif trend in {"wzrostowy", "spadkowy"}:
        quality_score -= 1
        reasons.append("Strefa przeciw aktualnemu trendowi: -1.")

    # Dystans jest tylko delikatnym filtrem. Nie chcemy wyrzucać dobrej strefy
    # 25-35% poniżej ceny, jeśli to mocna strefa HTF.
    if distance_pct > 70:
        quality_score -= 4
        reasons.append(f"Strefa ekstremalnie daleko od ceny ({distance_pct:.1f}%): -4.")
    elif distance_pct > 45:
        quality_score -= 2
        reasons.append(f"Strefa daleko od ceny ({distance_pct:.1f}%): -2.")
    elif distance_pct > 25:
        quality_score -= 1
        reasons.append(f"Strefa dalej od ceny, ale nadal strategiczna ({distance_pct:.1f}%): -1.")

    quality_score = max(int(quality_score), 0)

    # -------------------------
    # 2. AKTYWNOŚĆ SETUPU
    # -------------------------
    setup_score = 0

    if status["in_zone"]:
        setup_score += 3
        reasons.append("Cena jest już w strefie: setup +3.")
    elif status["near"]:
        setup_score += 2
        reasons.append("Cena jest blisko strefy: setup +2.")
    elif distance_pct <= 15:
        setup_score += 1
        reasons.append("Strefa jest w rozsądnym zasięgu ceny: setup +1.")

    # Sygnały świecowe/RSI są obecnie aktualne tylko dla stref w pobliżu ceny.
    # Nie premiujemy nimi stref odległych o kilkadziesiąt procent.
    if status["in_zone"] or status["near"]:
        if direction == "buy":
            if candle_patterns.get("bullish"):
                setup_score += 1
                reasons.append("Lokalna formacja świecowa BUY: setup +1.")
            if rsi_signal.get("direction") == "buy":
                setup_score += 1
                reasons.append("RSI wspiera BUY przy aktywnej strefie: setup +1.")
            if rsi_divergence.get("bullish"):
                setup_score += 1
                reasons.append("Bycza dywergencja RSI przy strefie: setup +1.")
        else:
            if candle_patterns.get("bearish"):
                setup_score += 1
                reasons.append("Lokalna formacja świecowa SELL: setup +1.")
            if rsi_signal.get("direction") == "sell":
                setup_score += 1
                reasons.append("RSI wspiera SELL przy aktywnej strefie: setup +1.")
            if rsi_divergence.get("bearish"):
                setup_score += 1
                reasons.append("Niedźwiedzia dywergencja RSI przy strefie: setup +1.")

        rr = float(trade_levels.get("rr", 0.0))
        if rr >= 3:
            setup_score += 2
            reasons.append("R:R >= 3 przy aktywnej strefie: setup +2.")
        elif rr >= 1.3:
            setup_score += 1
            reasons.append("R:R >= 1.3 przy aktywnej strefie: setup +1.")

    score = quality_score + setup_score

    if quality_score >= 28 and (status["in_zone"] or status["near"]):
        decision = "MOCNA STREFA + AKTYWNA — szukaj dokładnego potwierdzenia"
    elif quality_score >= 28:
        decision = "NAJWAŻNIEJSZA STREFA DO OBSERWACJI"
    elif quality_score >= 22 and (status["in_zone"] or status["near"]):
        decision = "DOBRA STREFA I CENA BLISKO — obserwuj sygnał"
    elif quality_score >= 22:
        decision = "DOBRA STREFA DO OBSERWACJI"
    elif quality_score >= 16:
        decision = "STREFA POMOCNICZA"
    else:
        decision = "NISKI PRIORYTET"

    return {
        "score": int(score),
        "quality_score": int(quality_score),
        "setup_score": int(setup_score),
        "status": status["status"],
        "distance": float(status["distance"]),
        "distance_pct": float(status["distance_pct"]),
        "width_pct": float(status["width_pct"]),
        "decision": decision,
        "reasons": reasons,
    }


def evaluate_zones(
    zones: list[dict[str, Any]],
    df: pd.DataFrame,
    swings: pd.DataFrame,
    trend: str,
    candle_patterns: dict[str, Any],
    rsi_signal: dict[str, Any],
    rsi_divergence: dict[str, Any],
) -> pd.DataFrame:
    """Ocenia wszystkie wykryte strefy i zwraca pełny ranking."""
    if not zones:
        return pd.DataFrame()

    current_price = float(df["close"].iloc[-1])
    atr = float(df["atr"].iloc[-1]) if "atr" in df.columns else float((df["high"] - df["low"]).tail(14).mean())

    rows: list[dict[str, Any]] = []

    for zone in zones:
        levels = calculate_trade_levels(zone, current_price, atr, swings)
        score_data = score_zone(
            zone,
            trend,
            current_price,
            atr,
            candle_patterns,
            rsi_signal,
            rsi_divergence,
            levels,
        )

        rows.append(
            {
                "direction": zone["direction"],
                "type": zone["type"],
                "source": zone["source"],
                "low": float(zone["low"]),
                "high": float(zone["high"]),
                "status": score_data["status"],
                "distance_pct": score_data["distance_pct"],
                "width_pct": score_data["width_pct"],
                "quality_score": score_data["quality_score"],
                "setup_score": score_data["setup_score"],
                "score": score_data["score"],
                "decision": score_data["decision"],
                "entry": levels["entry"],
                "safe_sl": levels["safe_sl"],
                "aggressive_sl": levels["aggressive_sl"],
                "tp": levels["tp"],
                "rr": levels["rr"],
                "note": zone.get("note", ""),
                "reasons": " | ".join(score_data["reasons"]),
                "meta": zone.get("meta", {}),
            }
        )

    result = pd.DataFrame(rows)

    # Główna zmiana: ranking jest jakościowy, a nie „najpierw to, co właśnie jest w cenie”.
    # Dzięki temu strategiczna strefa HTF/PIVOT_CLUSTER ma szansę być wyżej od lokalnej,
    # ale słabej strefy, nawet jeśli lokalna strefa jest akurat dotykana przez cenę.
    return result.sort_values(
        ["quality_score", "setup_score", "score", "width_pct", "distance_pct"],
        ascending=[False, False, False, True, True],
    ).reset_index(drop=True)


def select_top_zones(zones_df: pd.DataFrame, top_n: int = 5, max_overlap_ratio: float = 0.60) -> pd.DataFrame:
    """
    Zwraca 3-5 najważniejszych stref bez powtarzania prawie tego samego zakresu.

    Jeżeli dwie strefy tego samego kierunku mocno się pokrywają, zostawiamy tę,
    która jest wyżej w rankingu. Dzięki temu tabela nie jest długa i nie pokazuje
    kilku wariantów praktycznie tej samej strefy.
    """
    if zones_df.empty or top_n <= 0:
        return zones_df.head(0).copy()

    selected_indexes: list[int] = []

    for idx, row in zones_df.iterrows():
        candidate = row.to_dict()
        duplicate = False

        for selected_idx in selected_indexes:
            selected = zones_df.loc[selected_idx].to_dict()
            same_direction = str(candidate["direction"]) == str(selected["direction"])
            if same_direction and zone_overlap_ratio(candidate, selected) >= max_overlap_ratio:
                duplicate = True
                break

        if not duplicate:
            selected_indexes.append(idx)

        if len(selected_indexes) >= top_n:
            break

    return zones_df.loc[selected_indexes].reset_index(drop=True)
