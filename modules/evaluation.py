from __future__ import annotations

from typing import Any

import pandas as pd
import numpy as np

from .zones import zone_mid
from .config import (
    MIN_ACCEPTABLE_RR,
    TARGET_RR,
    READABLE_CHART_MAX_OVERLAP_RATIO,
    READABLE_CHART_MAX_DISTANCE_PCT,
)


# =========================================================
# WAGI I KLASY ŹRÓDEŁ
# =========================================================

# Źródła nie są równoważne. Najmocniejsze są te, które opisują większy kontekst,
# płynność i realną strefę reakcji, a nie tylko lokalny pomocniczy filtr.
SOURCE_WEIGHTS: dict[str, int] = {
    "HTF/HIST": 8,
    "PIVOT_CLUSTER": 7,
    "OB/LBM": 5,
    "1:1": 4,
    "FTR": 3,
    "FIBO": 2,
    "S/R": 2,
    "FVG": 1,
}

STRONG_ANCHOR_SOURCES = {"HTF/HIST", "PIVOT_CLUSTER", "OB/LBM", "1:1"}
WEAK_STANDALONE_SOURCES = {"FVG", "FIBO", "S/R", "FTR"}


# =========================================================
# PODSTAWOWE NARZĘDZIA
# =========================================================

def parse_sources(source: str) -> set[str]:
    """Rozbija źródła klastra na unikalne tagi."""
    return {part.strip() for part in str(source).split("+") if part.strip()}


def zones_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return max(float(a["low"]), float(b["low"])) <= min(float(a["high"]), float(b["high"]))


def zone_overlap_ratio(a: dict[str, Any], b: dict[str, Any]) -> float:
    """Zwraca część mniejszej strefy pokrytą przez drugą strefę."""
    overlap = max(0.0, min(float(a["high"]), float(b["high"])) - max(float(a["low"]), float(b["low"])))
    min_width = max(min(float(a["high"]) - float(a["low"]), float(b["high"]) - float(b["low"])), 1e-12)
    return overlap / min_width


def get_zone_status(zone: dict[str, Any], current_price: float, atr: float) -> dict[str, Any]:
    """
    Określa praktyczne położenie ceny względem strefy.

    Status położenia nie może sam wygrywać rankingu. Jest tylko informacją,
    czy dana strefa jest aktywna teraz, blisko, czy strategiczna na później.
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


def source_quality_bonus(zone: dict[str, Any]) -> tuple[int, list[str], set[str]]:
    """Liczy jakość źródeł i zwraca także komplet źródeł."""
    sources = parse_sources(str(zone.get("source", "")))
    weighted = sum(SOURCE_WEIGHTS.get(source, 0) for source in sources)
    bonus = min(weighted, 18)

    reasons: list[str] = []
    if sources:
        reasons.append(f"Jakość źródeł ({', '.join(sorted(sources))}): +{bonus}.")

    # Konfluencja różnych technik ma znaczenie, ale sama liczba źródeł
    # nie może bez końca pompować score.
    if len(sources) >= 2:
        multi_bonus = min(len(sources) - 1, 4)
        bonus += multi_bonus
        reasons.append(f"Konfluencja {len(sources)} źródeł: +{multi_bonus}.")

    return bonus, reasons, sources


# =========================================================
# ŚWIEŻOŚĆ / ZUŻYCIE / NIEWAŻNOŚĆ STREFY
# =========================================================

def _count_touch_visits(touches: pd.Series) -> int:
    """Liczy odrębne wejścia ceny w strefę, a nie liczbę świec w środku."""
    if touches.empty:
        return 0
    entries = touches & ~touches.shift(1, fill_value=False)
    return int(entries.sum())


def analyze_zone_history(df: pd.DataFrame, zone: dict[str, Any]) -> dict[str, Any]:
    """
    Ocenia, czy strefa jest świeża, ile razy była testowana i czy została zanegowana.

    Nie mamy pełnej semantyki "momentu powstania" dla każdego typu strefy,
    więc analizujemy całą dostępną historię. To jest konserwatywne: strefy wielokrotnie
    używane są traktowane ostrożniej zamiast sztucznie promowane.
    """
    if df.empty:
        return {
            "touch_count": 0,
            "freshness": "BRAK DANYCH",
            "invalidated": False,
            "last_touch_time": None,
        }

    low = float(zone["low"])
    high = float(zone["high"])
    direction = str(zone.get("direction", "")).lower()

    touches = (df["high"] >= low) & (df["low"] <= high)
    touch_count = _count_touch_visits(touches)
    last_touch_time = None
    if bool(touches.any()):
        last_touch_time = str(df.index[touches][-1])

    # Strefa jest zanegowana dopiero po realnym teście. Nie wolno brać pod uwagę świec
    # sprzed powstania / przed pierwszym wejściem w obszar, bo wtedy prawie każda strefa
    # zostałaby błędnie uznana za nieważną. Przyjmujemy konserwatywnie:
    # - BUY: po ostatnim wejściu w strefę pojawiają się 2 zamknięcia poniżej dolnej krawędzi,
    # - SELL: po ostatnim wejściu w strefę pojawiają się 2 zamknięcia powyżej górnej krawędzi.
    invalidated = False
    if bool(touches.any()):
        last_touch_position = int(np.flatnonzero(touches.to_numpy())[-1])
        after_last_touch = df.iloc[last_touch_position + 1 :]

        if not after_last_touch.empty:
            if direction == "buy":
                invalid_series = after_last_touch["close"] < low
            elif direction == "sell":
                invalid_series = after_last_touch["close"] > high
            else:
                invalid_series = pd.Series(False, index=after_last_touch.index)

            invalidated = bool((invalid_series.rolling(2).sum() >= 2).any())

    if invalidated:
        freshness = "ZANEGOWANA"
    elif touch_count == 0:
        freshness = "ŚWIEŻA"
    elif touch_count == 1:
        freshness = "TESTOWANA 1×"
    elif touch_count == 2:
        freshness = "TESTOWANA 2×"
    else:
        freshness = "ZUŻYTA"

    return {
        "touch_count": int(touch_count),
        "freshness": freshness,
        "invalidated": invalidated,
        "last_touch_time": last_touch_time,
    }


# =========================================================
# POZIOMY TRADE'U
# =========================================================

def find_take_profit(entry: float, direction: str, swings: pd.DataFrame, safe_sl: float) -> float:
    """
    Szuka konserwatywnego TP na najbliższym przeciwnym swingu cenowym.

    Poprzednio wybieraliśmy ostatni pivot w czasie, co potrafiło dawać zbyt odległy TP
    i sztucznie pompować R:R. Teraz wybieramy najbliższą sensowną przeszkodę cenową:
    - BUY: najniższy ważny szczyt powyżej wejścia,
    - SELL: najwyższy ważny dołek poniżej wejścia.

    Gdy takiego swingu nie ma, zostaje awaryjny target 2R.
    """
    risk = abs(entry - safe_sl)
    if risk <= 0:
        return entry

    if direction == "buy":
        highs_above = swings[(swings["type"] == "high") & (swings["price"] > entry)]
        if not highs_above.empty:
            nearest_high = highs_above.sort_values("price", ascending=True).iloc[0]
            return float(nearest_high["price"])
        return entry + risk * TARGET_RR

    lows_below = swings[(swings["type"] == "low") & (swings["price"] < entry)]
    if not lows_below.empty:
        nearest_low = lows_below.sort_values("price", ascending=False).iloc[0]
        return float(nearest_low["price"])
    return entry - risk * TARGET_RR


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

    rr_ok = rr >= MIN_ACCEPTABLE_RR
    if rr >= TARGET_RR:
        rr_status = "SPEŁNIA ~1:2"
    elif rr_ok:
        rr_status = "BLISKO 1:2 — TOLERANCJA"
    else:
        rr_status = "ZA SŁABE R:R"

    return {
        "entry": float(entry),
        "safe_sl": float(safe_sl),
        "aggressive_sl": float(aggressive_sl),
        "tp": float(tp),
        "rr": float(rr),
        "rr_ok": bool(rr_ok),
        "rr_status": rr_status,
    }


# =========================================================
# SCORE
# =========================================================

def _direction_has_local_confirmation(
    direction: str,
    candle_patterns: dict[str, Any],
    rsi_signal: dict[str, Any],
    rsi_divergence: dict[str, Any],
) -> bool:
    if direction == "buy":
        return bool(candle_patterns.get("bullish")) or rsi_signal.get("direction") == "buy" or bool(rsi_divergence.get("bullish"))
    return bool(candle_patterns.get("bearish")) or rsi_signal.get("direction") == "sell" or bool(rsi_divergence.get("bearish"))


def score_zone(
    zone: dict[str, Any],
    trend: str,
    current_price: float,
    atr: float,
    candle_patterns: dict[str, Any],
    rsi_signal: dict[str, Any],
    rsi_divergence: dict[str, Any],
    trade_levels: dict[str, float],
    history: dict[str, Any],
) -> dict[str, Any]:
    """
    Ocena strefy rozdzielona na:
    - quality_score: jakość samego miejsca,
    - setup_score: czy okolica jest teraz handlowo aktywna.

    Ranking jakościowy nie może faworyzować byle jakiej strefy tylko dlatego,
    że cena przypadkiem akurat jest w środku.
    """
    reasons: list[str] = []
    status = get_zone_status(zone, current_price, atr)
    source_bonus, source_reasons, sources = source_quality_bonus(zone)
    meta = zone.get("meta", {}) or {}

    width_pct = float(status["width_pct"])
    distance_pct = float(status["distance_pct"])
    direction = str(zone["direction"]).lower()
    strong_sources = sources & STRONG_ANCHOR_SOURCES
    standalone_weak = bool(sources) and sources.issubset(WEAK_STANDALONE_SOURCES)
    has_local_confirmation = _direction_has_local_confirmation(direction, candle_patterns, rsi_signal, rsi_divergence)

    # -------------------------
    # 1. JAKOŚĆ STRUKTURALNA
    # -------------------------
    strength = min(max(int(zone.get("strength", 0)), 0), 12)
    quality_score = strength
    reasons.append(f"Bazowa siła strefy: +{strength}.")

    quality_score += source_bonus
    reasons.extend(source_reasons)

    if len(strong_sources) >= 2:
        quality_score += 4
        reasons.append(f"Co najmniej 2 mocne kotwice ({', '.join(sorted(strong_sources))}): +4.")
    elif len(strong_sources) == 1:
        quality_score += 2
        reasons.append(f"Mocna kotwica ({', '.join(sorted(strong_sources))}): +2.")

    # FVG/Fibo/SR/FTR same z siebie są za słabe jako gwiazda rankingu.
    if standalone_weak:
        quality_score -= 7
        reasons.append("Tylko pomocnicze źródła bez mocnej kotwicy: -7.")

    if "FVG" in sources and not strong_sources:
        quality_score -= 3
        reasons.append("FVG bez płynności/HTF traktowane tylko pomocniczo: -3.")
    elif "FVG" in sources and strong_sources:
        quality_score += 2
        reasons.append("FVG wewnątrz mocniejszej strefy — konfluencja: +2.")

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

    # Precyzja strefy. Bardzo szerokie poziomy są słabym wejściem.
    if width_pct <= 5:
        quality_score += 4
        reasons.append(f"Bardzo precyzyjna szerokość ({width_pct:.1f}%): +4.")
    elif width_pct <= 9:
        quality_score += 3
        reasons.append(f"Dobra szerokość ({width_pct:.1f}%): +3.")
    elif width_pct <= 13:
        quality_score += 1
        reasons.append(f"Akceptowalna szerokość ({width_pct:.1f}%): +1.")
    elif width_pct <= 18:
        quality_score -= 2
        reasons.append(f"Strefa dość szeroka ({width_pct:.1f}%): -2.")
    else:
        quality_score -= 12
        reasons.append(f"Strefa za szeroka do rankingu wejść ({width_pct:.1f}%): -12.")

    # Świeżość strefy.
    freshness = str(history.get("freshness", "BRAK DANYCH"))
    touch_count = int(history.get("touch_count", 0) or 0)
    invalidated = bool(history.get("invalidated", False))

    if freshness == "ŚWIEŻA":
        quality_score += 3
        reasons.append("Strefa świeża, bez ponownych testów: +3.")
    elif freshness == "TESTOWANA 1×":
        quality_score += 1
        reasons.append("Strefa raz testowana: +1.")
    elif freshness == "TESTOWANA 2×":
        quality_score -= 2
        reasons.append("Strefa testowana 2 razy — ostrożniej: -2.")
    elif freshness == "ZUŻYTA":
        quality_score -= 6
        reasons.append(f"Strefa wielokrotnie testowana ({touch_count} wejść): -6.")

    if invalidated:
        quality_score -= 25
        reasons.append("Strefa zanegowana dwoma zamknięciami poza zakresem: -25.")

    # Trend ma znaczenie. Przeciwtrendowe BUY/SELL bez potwierdzeń mają być niżej.
    if trend == "wzrostowy" and direction == "buy":
        quality_score += 2
        reasons.append("Zgodność z trendem wzrostowym: +2.")
    elif trend == "spadkowy" and direction == "sell":
        quality_score += 2
        reasons.append("Zgodność z trendem spadkowym: +2.")
    elif trend in {"wzrostowy", "spadkowy"}:
        if has_local_confirmation:
            quality_score -= 1
            reasons.append("Strefa przeciw trendowi, ale ma lokalne potwierdzenie: -1.")
        else:
            quality_score -= 4
            reasons.append("Strefa przeciw trendowi bez lokalnego potwierdzenia: -4.")

    # Dystans nie może zabić dobrej strefy strategicznej, ale ekstremalnie dalekie obszary
    # nie powinny wypychać bardziej użytecznych stref.
    if distance_pct > 90:
        quality_score -= 5
        reasons.append(f"Strefa ekstremalnie daleko od ceny ({distance_pct:.1f}%): -5.")
    elif distance_pct > 60:
        quality_score -= 3
        reasons.append(f"Strefa bardzo daleko od ceny ({distance_pct:.1f}%): -3.")
    elif distance_pct > 35:
        quality_score -= 1
        reasons.append(f"Strefa dalsza, ale nadal strategiczna ({distance_pct:.1f}%): -1.")

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

    # Sygnały świecowe/RSI są ważne tylko przy aktualnie testowanej lub bliskiej strefie.
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
            setup_score += 3
            reasons.append("R:R >= 3 przy aktywnej strefie: setup +3.")
        elif rr >= TARGET_RR:
            setup_score += 2
            reasons.append("R:R spełnia warunek ok. 1:2: setup +2.")
        elif rr >= MIN_ACCEPTABLE_RR:
            setup_score += 1
            reasons.append("R:R jest blisko 1:2 i mieści się w tolerancji: setup +1.")
        else:
            setup_score -= 4
            reasons.append(f"R:R {rr:.2f} poniżej wymaganego ~1:2: setup -4.")

    score = quality_score + setup_score
    rr = float(trade_levels.get("rr", 0.0))
    rr_ok = bool(trade_levels.get("rr_ok", False))
    rr_status = str(trade_levels.get("rr_status", "BRAK"))

    # Klasa strefy: oddzielamy jakość od "czy jest teraz w cenie".
    # Dodatkowo strefa nie jest traktowana jako sensowny trade, jeżeli R:R nie daje
    # mniej więcej 1:2. Pozostaje w pełnej tabeli, ale nie powinna wejść do głównego rankingu.
    if invalidated:
        entry_class = "ODRZUCONA"
        decision = "ZANEGOWANA — nie używaj jako aktualnej strefy wejścia"
    elif quality_score < 14:
        entry_class = "ODRZUCONA"
        decision = "NISKI PRIORYTET / ZA SŁABA"
    elif not rr_ok:
        entry_class = "OBSERWACJA"
        decision = f"R:R {rr:.2f} jest słabsze niż ~1:2 — tylko obserwacja, nie setup wejścia"
    elif status["in_zone"] or status["near"]:
        entry_class = "AKTYWNA"
        if quality_score >= 28:
            decision = "MOCNA STREFA + AKTYWNA + R:R ~1:2 — szukaj potwierdzenia"
        elif quality_score >= 20:
            decision = "DOBRA STREFA, CENA BLISKO I R:R OK — obserwuj sygnał"
        else:
            decision = "AKTYWNA, R:R OK, ALE JAKOŚĆ ŚREDNIA — sprawdź ręcznie"
    elif distance_pct <= 20:
        entry_class = "W ZASIĘGU"
        decision = "DOBRA STREFA W ZASIĘGU + R:R OK — obserwuj"
    else:
        entry_class = "STRATEGICZNA"
        decision = "MOCNA STREFA STRATEGICZNA + R:R OK — poza bieżącą ceną"

    return {
        "score": int(score),
        "quality_score": int(quality_score),
        "setup_score": int(setup_score),
        "status": status["status"],
        "distance": float(status["distance"]),
        "distance_pct": float(status["distance_pct"]),
        "width_pct": float(status["width_pct"]),
        "decision": decision,
        "entry_class": entry_class,
        "freshness": freshness,
        "touch_count": touch_count,
        "invalidated": invalidated,
        "sources_count": len(sources),
        "strong_sources_count": len(strong_sources),
        "has_local_confirmation": has_local_confirmation,
        "rr_ok": rr_ok,
        "rr_status": rr_status,
        "reasons": reasons,
    }


# =========================================================
# KONFLIKTY BUY/SELL
# =========================================================

def _apply_conflict_penalties(result: pd.DataFrame) -> pd.DataFrame:
    """Oznacza strefy BUY/SELL, które mocno nachodzą na siebie."""
    if result.empty:
        return result

    result = result.copy()
    result["conflict"] = False
    result["conflict_count"] = 0
    result["conflict_note"] = ""

    for i in range(len(result)):
        row_i = result.iloc[i].to_dict()
        for j in range(i + 1, len(result)):
            row_j = result.iloc[j].to_dict()

            opposite = str(row_i["direction"]) != str(row_j["direction"])
            overlap = zone_overlap_ratio(row_i, row_j)

            if opposite and overlap >= 0.35:
                result.at[result.index[i], "conflict"] = True
                result.at[result.index[j], "conflict"] = True
                result.at[result.index[i], "conflict_count"] = int(result.at[result.index[i], "conflict_count"]) + 1
                result.at[result.index[j], "conflict_count"] = int(result.at[result.index[j], "conflict_count"]) + 1

    conflict_mask = result["conflict"] == True
    if bool(conflict_mask.any()):
        result.loc[conflict_mask, "quality_score"] = (result.loc[conflict_mask, "quality_score"] - 3).clip(lower=0)
        result.loc[conflict_mask, "score"] = (result.loc[conflict_mask, "score"] - 3).clip(lower=0)
        result.loc[conflict_mask, "conflict_note"] = "Nakładanie się mocniejszych stref BUY/SELL — potrzebna ręczna weryfikacja."

        def _conflict_decision(row: pd.Series) -> str:
            if row.get("entry_class") == "ODRZUCONA":
                return str(row.get("decision", ""))
            return "KONFLIKT BUY/SELL — decyzja tylko po dodatkowym potwierdzeniu"

        result.loc[conflict_mask, "decision"] = result.loc[conflict_mask].apply(_conflict_decision, axis=1)

    return result


# =========================================================
# RANKING
# =========================================================

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
        history = analyze_zone_history(df, zone)
        score_data = score_zone(
            zone,
            trend,
            current_price,
            atr,
            candle_patterns,
            rsi_signal,
            rsi_divergence,
            levels,
            history,
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
                "entry_class": score_data["entry_class"],
                "freshness": score_data["freshness"],
                "touch_count": score_data["touch_count"],
                "invalidated": score_data["invalidated"],
                "sources_count": score_data["sources_count"],
                "strong_sources_count": score_data["strong_sources_count"],
                "has_local_confirmation": score_data["has_local_confirmation"],
                "entry": levels["entry"],
                "safe_sl": levels["safe_sl"],
                "aggressive_sl": levels["aggressive_sl"],
                "tp": levels["tp"],
                "rr": levels["rr"],
                "rr_ok": score_data["rr_ok"],
                "rr_status": score_data["rr_status"],
                "note": zone.get("note", ""),
                "reasons": " | ".join(score_data["reasons"]),
                "meta": zone.get("meta", {}),
            }
        )

    result = pd.DataFrame(rows)
    result = _apply_conflict_penalties(result)

    # Ranking jakościowy: top ma być rzetelny, nie tylko "najbliższy kursowi".
    # Odrzucone strefy lądują na końcu, konflikty są niżej przez karę jakości.
    class_priority = {
        "AKTYWNA": 0,
        "W ZASIĘGU": 1,
        "STRATEGICZNA": 2,
        "OBSERWACJA": 8,
        "ODRZUCONA": 9,
    }
    result["entry_class_priority"] = result["entry_class"].map(class_priority).fillna(9).astype(int)

    return result.sort_values(
        ["entry_class_priority", "quality_score", "setup_score", "score", "width_pct", "distance_pct"],
        ascending=[True, False, False, False, True, True],
    ).reset_index(drop=True)


def _assign_zone_codes(zones_df: pd.DataFrame) -> pd.DataFrame:
    """Dodaje kody B1/B2/S1/S2, żeby tabela i wykres mówiły tym samym językiem."""
    if zones_df.empty:
        result = zones_df.copy()
        if "zone_code" not in result.columns:
            result["zone_code"] = pd.Series(dtype="object")
        return result

    result = zones_df.copy().reset_index(drop=True)
    buy_counter = 0
    sell_counter = 0
    codes: list[str] = []

    for _, row in result.iterrows():
        direction = str(row.get("direction", "")).lower()
        if direction == "buy":
            buy_counter += 1
            codes.append(f"B{buy_counter}")
        else:
            sell_counter += 1
            codes.append(f"S{sell_counter}")

    result.insert(0, "zone_code", codes)
    return result


def select_top_zones(zones_df: pd.DataFrame, top_n: int = 5, max_overlap_ratio: float = 0.60) -> pd.DataFrame:
    """
    Zwraca 3-5 najlepszych jakościowo stref bez powtarzania niemal tego samego zakresu.

    Priorytet:
    1. strefy aktywne i w zasięgu,
    2. mocne strategiczne,
    3. bez stref odrzuconych, zanegowanych lub bardzo słabych.
    """
    if zones_df.empty or top_n <= 0:
        return _assign_zone_codes(zones_df.head(0).copy())

    candidates = zones_df[
        (zones_df["entry_class"].isin(["AKTYWNA", "W ZASIĘGU", "STRATEGICZNA"]))
        & (zones_df["invalidated"] == False)
        & (zones_df["rr_ok"] == True)
        & (zones_df["quality_score"] >= 16)
    ].copy()

    # Jeżeli rynek nie daje stref z akceptowalnym R:R, lepiej zwrócić pusty ranking
    # niż udawać, że mamy dobry trade. Pełna tabela nadal pokaże strefy obserwacyjne.
    if candidates.empty:
        return _assign_zone_codes(zones_df.head(0).copy())

    selected_indexes: list[int] = []

    for idx, row in candidates.iterrows():
        candidate = row.to_dict()
        duplicate = False

        for selected_idx in selected_indexes:
            selected = candidates.loc[selected_idx].to_dict()
            same_direction = str(candidate["direction"]) == str(selected["direction"])
            if same_direction and zone_overlap_ratio(candidate, selected) >= max_overlap_ratio:
                duplicate = True
                break

        if not duplicate:
            selected_indexes.append(idx)

        if len(selected_indexes) >= top_n:
            break

    selected = candidates.loc[selected_indexes].reset_index(drop=True)
    return _assign_zone_codes(selected)


def select_active_zones(zones_df: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    """Zwraca najlepsze strefy, które są aktualnie w cenie albo bardzo blisko."""
    if zones_df.empty or top_n <= 0:
        return _assign_zone_codes(zones_df.head(0).copy())

    active = zones_df[
        (zones_df["entry_class"] == "AKTYWNA")
        & (zones_df["invalidated"] == False)
        & (zones_df["rr_ok"] == True)
        & (zones_df["quality_score"] >= 16)
    ].copy()

    active = active.sort_values(
        ["quality_score", "setup_score", "score", "width_pct"],
        ascending=[False, False, False, True],
    ).head(top_n)

    return _assign_zone_codes(active.reset_index(drop=True))


def select_strategic_zones(zones_df: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    """Zwraca mocne strefy dalszego planu, żeby nie mieszać ich z aktywnymi wejściami."""
    if zones_df.empty or top_n <= 0:
        return _assign_zone_codes(zones_df.head(0).copy())

    strategic = zones_df[
        (zones_df["entry_class"] == "STRATEGICZNA")
        & (zones_df["invalidated"] == False)
        & (zones_df["rr_ok"] == True)
        & (zones_df["quality_score"] >= 18)
    ].copy()

    strategic = strategic.sort_values(
        ["quality_score", "score", "width_pct", "distance_pct"],
        ascending=[False, False, True, True],
    ).head(top_n)

    return _assign_zone_codes(strategic.reset_index(drop=True))


def select_chart_zones(
    zones_df: pd.DataFrame,
    top_n: int = 2,
    max_overlap_ratio: float = READABLE_CHART_MAX_OVERLAP_RATIO,
) -> pd.DataFrame:
    """
    Wybiera minimalny zestaw stref do głównego, czytelnego wykresu.

    Zasada projektowa:
    - wykres ma odpowiadać na pytanie: "gdzie jest główny poziom decyzyjny?",
      a nie rysować każdą sensowną strefę z całej analizy,
    - pokazujemy maksymalnie 2 strefy:
        1) GŁÓWNA — najlepsza praktyczna strefa z rankingu,
        2) ALTERNATYWNA — wyraźnie odseparowany głębszy scenariusz w tym samym kierunku,
           jeśli taki istnieje.

    Priorytet czytelności:
    - nie rysujemy zanegowanych stref,
    - nie rysujemy stref bez R:R,
    - strefa z głównego rankingu ma być widoczna na wykresie także wtedy, gdy jest strategiczna i daleko od ceny,
    - nie dublujemy zakresów i nie tworzymy "zielonej/czerwonej ściany".
    """
    if zones_df.empty or top_n <= 0:
        return _assign_zone_codes(zones_df.head(0).copy())

    candidates = zones_df[
        (zones_df["invalidated"] == False)
        & (zones_df["rr_ok"] == True)
        & (zones_df["entry_class"].isin(["AKTYWNA", "W ZASIĘGU", "STRATEGICZNA"]))
    ].copy()

    if candidates.empty:
        return _assign_zone_codes(zones_df.head(0).copy())

    # 1) Główna strefa — bierzemy pierwszą z rankingu po filtrach praktyczności.
    primary = candidates.iloc[0].copy()
    selected_rows: list[pd.Series] = [primary]

    # 2) Alternatywa — preferujemy ten sam kierunek i strefę wyraźnie odseparowaną.
    primary_direction = str(primary.get("direction", "")).lower()
    primary_low = float(primary["low"])
    primary_high = float(primary["high"])

    def _is_clear_alternative(candidate: pd.Series) -> bool:
        candidate_dict = candidate.to_dict()
        primary_dict = primary.to_dict()
        overlap = zone_overlap_ratio(candidate_dict, primary_dict)
        if overlap >= max_overlap_ratio:
            return False

        direction = str(candidate.get("direction", "")).lower()
        low = float(candidate["low"])
        high = float(candidate["high"])

        # Przy BUY interesuje nas głębsza, niżej położona alternatywa.
        if primary_direction == "buy" and direction == "buy":
            return high < primary_low

        # Przy SELL interesuje nas wyższa, dalej położona alternatywa.
        if primary_direction == "sell" and direction == "sell":
            return low > primary_high

        return False

    for _, candidate in candidates.iloc[1:].iterrows():
        if _is_clear_alternative(candidate):
            selected_rows.append(candidate.copy())
            break

    # Jeżeli nie ma logicznej alternatywy w tym samym kierunku, nie dokładamy nic na siłę.
    selected = pd.DataFrame(selected_rows).reset_index(drop=True)
    if "zone_code" not in selected.columns:
        selected = _assign_zone_codes(selected)

    chart_roles = ["GŁÓWNA"]
    if len(selected) >= 2:
        chart_roles.append("ALTERNATYWNA")
    selected.insert(1, "chart_role", chart_roles)

    return selected.head(top_n).reset_index(drop=True)

