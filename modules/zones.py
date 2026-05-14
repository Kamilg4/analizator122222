from typing import Any
import pandas as pd
from .config import FIBO_LEVELS, FIBO_MAIN_LEVELS
from .ovb_bos import find_corrections
from .patterns import candle_direction, candle_body


def normalize_zone(low: float, high: float) -> tuple[float, float]:
    return (min(float(low), float(high)), max(float(low), float(high)))


def zone_mid(zone: dict[str, Any]) -> float:
    return (zone["low"] + zone["high"]) / 2


def add_zone(
    zones: list[dict[str, Any]],
    direction: str,
    zone_type: str,
    low: float,
    high: float,
    source: str,
    strength: int,
    note: str,
    meta: dict[str, Any] | None = None,
) -> None:
    low_value, high_value = normalize_zone(low, high)

    if low_value == high_value:
        return

    zones.append(
        {
            "direction": direction,
            "type": zone_type,
            "low": low_value,
            "high": high_value,
            "source": source,
            "strength": strength,
            "note": note,
            "meta": meta or {},
        }
    )


def get_last_impulse_for_direction(swings: pd.DataFrame, direction: str) -> dict[str, Any]:
    """Zwraca ostatni impuls zgodny z kierunkiem BUY/SELL."""
    if swings.empty:
        return {"available": False}

    impulse = None

    if direction == "buy":
        for i in range(len(swings) - 1):
            start = swings.iloc[i]
            end = swings.iloc[i + 1]
            if start["type"] == "low" and end["type"] == "high" and end["price"] > start["price"]:
                impulse = {
                    "available": True,
                    "start_time": str(start["time"]),
                    "end_time": str(end["time"]),
                    "start_price": float(start["price"]),
                    "end_price": float(end["price"]),
                    "size": float(end["price"] - start["price"]),
                }

    if direction == "sell":
        for i in range(len(swings) - 1):
            start = swings.iloc[i]
            end = swings.iloc[i + 1]
            if start["type"] == "high" and end["type"] == "low" and end["price"] < start["price"]:
                impulse = {
                    "available": True,
                    "start_time": str(start["time"]),
                    "end_time": str(end["time"]),
                    "start_price": float(start["price"]),
                    "end_price": float(end["price"]),
                    "size": float(start["price"] - end["price"]),
                }

    return impulse if impulse else {"available": False}


def build_fibo_zones(swings: pd.DataFrame, atr: float) -> list[dict[str, Any]]:
    """Buduje strefy Fibo dla BUY i SELL z ostatnich impulsów."""
    zones = []
    tolerance = atr * 0.15

    for direction in ["buy", "sell"]:
        impulse = get_last_impulse_for_direction(swings, direction)
        if not impulse.get("available"):
            continue

        start_price = impulse["start_price"]
        end_price = impulse["end_price"]
        size = impulse["size"]

        if direction == "buy":
            for level in FIBO_LEVELS:
                price = end_price - size * level
                strength = 4 if level in FIBO_MAIN_LEVELS else 3
                add_zone(
                    zones,
                    direction="buy",
                    zone_type=f"Fibo {level:.3f}",
                    low=price - tolerance,
                    high=price + tolerance,
                    source="FIBO",
                    strength=strength,
                    note=f"Potencjalna korekta BUY po impulsie {impulse['start_price']:.2f} -> {impulse['end_price']:.2f}.",
                )

        if direction == "sell":
            for level in FIBO_LEVELS:
                price = end_price + size * level
                strength = 4 if level in FIBO_MAIN_LEVELS else 3
                add_zone(
                    zones,
                    direction="sell",
                    zone_type=f"Fibo {level:.3f}",
                    low=price - tolerance,
                    high=price + tolerance,
                    source="FIBO",
                    strength=strength,
                    note=f"Potencjalna korekta SELL po impulsie {impulse['start_price']:.2f} -> {impulse['end_price']:.2f}.",
                )

    return zones


def build_one_to_one_zones(swings: pd.DataFrame, trend: str, atr: float) -> list[dict[str, Any]]:
    """Buduje strefę 1:1 na podstawie największej albo ostatniej korekty."""
    zones = []

    if trend not in ["wzrostowy", "spadkowy"]:
        return zones

    corrections = find_corrections(swings, trend)
    if not corrections:
        return zones

    last_correction = corrections[-1]
    correction_size = last_correction["size"]
    tolerance = max(atr * 0.20, correction_size * 0.03)

    if trend == "wzrostowy":
        highs = swings[swings["type"] == "high"]
        if highs.empty:
            return zones
        base_high = float(highs.iloc[-1]["price"])
        level = base_high - correction_size
        add_zone(
            zones,
            direction="buy",
            zone_type="Korekta 1:1",
            low=level - tolerance,
            high=level + tolerance,
            source="1:1",
            strength=5,
            note="Powtórzenie ostatniej korekty w trendzie wzrostowym.",
        )

    if trend == "spadkowy":
        lows = swings[swings["type"] == "low"]
        if lows.empty:
            return zones
        base_low = float(lows.iloc[-1]["price"])
        level = base_low + correction_size
        add_zone(
            zones,
            direction="sell",
            zone_type="Korekta 1:1",
            low=level - tolerance,
            high=level + tolerance,
            source="1:1",
            strength=5,
            note="Powtórzenie ostatniej korekty w trendzie spadkowym.",
        )

    return zones


def build_support_resistance_zones(swings: pd.DataFrame, atr: float) -> list[dict[str, Any]]:
    """Buduje proste strefy wsparcia/oporu z ostatnich swingów."""
    zones = []
    tolerance = atr * 0.25

    if swings.empty:
        return zones

    # Bierzemy więcej swingów, żeby złapać także starsze wsparcia/opory,
    # a nie tylko ostatnie 4 punkty struktury.
    recent_lows = swings[swings["type"] == "low"].tail(12)
    recent_highs = swings[swings["type"] == "high"].tail(12)

    for _, row in recent_lows.iterrows():
        add_zone(
            zones,
            direction="buy",
            zone_type="Wsparcie / dołek płynnościowy",
            low=float(row["price"]) - tolerance,
            high=float(row["price"]) + tolerance,
            source="S/R",
            strength=2,
            note="Ostatni dołek jako potencjalna strefa reakcji / zebrania płynności.",
        )

    for _, row in recent_highs.iterrows():
        add_zone(
            zones,
            direction="sell",
            zone_type="Opór / szczyt płynnościowy",
            low=float(row["price"]) - tolerance,
            high=float(row["price"]) + tolerance,
            source="S/R",
            strength=2,
            note="Ostatni szczyt jako potencjalna strefa reakcji / zebrania płynności.",
        )

    return zones


def build_fvg_zones(df: pd.DataFrame, atr: float, lookback: int = 300) -> list[dict[str, Any]]:
    """Wykrywa uproszczone FVG / imbalance."""
    zones = []
    data = df.tail(lookback)

    if len(data) < 3:
        return zones

    for i in range(1, len(data) - 1):
        prev = data.iloc[i - 1]
        next_candle = data.iloc[i + 1]

        # Bullish FVG: luka między high poprzedniej świecy i low następnej.
        if float(next_candle["low"]) > float(prev["high"]):
            gap_size = float(next_candle["low"] - prev["high"])
            if gap_size >= atr * 0.10:
                has_volume = "volume" in df.columns and "volume_ma" in df.columns
                vol_confirm = has_volume and float(next_candle["volume"]) > float(next_candle["volume_ma"])
                add_zone(
                    zones,
                    direction="buy",
                    zone_type="FVG / Imbalance BUY",
                    low=float(prev["high"]),
                    high=float(next_candle["low"]),
                    source="FVG",
                    strength=4 if vol_confirm else 3,
                    note=f"Uproszczony bullish imbalance{' (potwierdzony wolumenem)' if vol_confirm else ''} — potencjalna reakcja przy domknięciu luki.",
                )

        # Bearish FVG: luka między low poprzedniej świecy i high następnej.
        if float(next_candle["high"]) < float(prev["low"]):
            gap_size = float(prev["low"] - next_candle["high"])
            if gap_size >= atr * 0.10:
                has_volume = "volume" in df.columns and "volume_ma" in df.columns
                vol_confirm = has_volume and float(next_candle["volume"]) > float(next_candle["volume_ma"])
                add_zone(
                    zones,
                    direction="sell",
                    zone_type="FVG / Imbalance SELL",
                    low=float(next_candle["high"]),
                    high=float(prev["low"]),
                    source="FVG",
                    strength=4 if vol_confirm else 3,
                    note=f"Uproszczony bearish imbalance{' (potwierdzony wolumenem)' if vol_confirm else ''} — potencjalna reakcja przy domknięciu luki.",
                )

    return zones[-20:]


def build_order_block_zones(df: pd.DataFrame, atr: float, lookback: int = 300) -> list[dict[str, Any]]:
    """
    Uproszczone OB/LBM:
    - BUY: ostatnia spadkowa świeca przed mocnym ruchem wzrostowym.
    - SELL: ostatnia wzrostowa świeca przed mocnym ruchem spadkowym.
    """
    zones = []
    data = df.tail(lookback)

    if len(data) < 10:
        return zones

    for i in range(3, len(data) - 5):
        candle = data.iloc[i]
        future = data.iloc[i + 1 : i + 6]
        previous = data.iloc[max(0, i - 10) : i]

        body = candle_body(candle)
        if body <= 0:
            continue

        # BUY OB: świeca spadkowa, po której następuje wyraźny ruch i wybicie lokalnych high.
        if candle_direction(candle) == "bearish":
            future_break = float(future["high"].max()) > float(previous["high"].max()) if not previous.empty else False
            future_move = float(future["high"].max() - candle["low"])
            if future_break and future_move >= atr:
                has_volume = "volume" in df.columns and "volume_ma" in df.columns
                future_vol_max = float(future["volume"].max()) if has_volume else 0.0
                candle_vol_ma = float(candle["volume_ma"]) if has_volume else 0.0
                vol_confirm = has_volume and future_vol_max > candle_vol_ma * 1.3
                add_zone(
                    zones,
                    direction="buy",
                    zone_type="OB / LBM BUY",
                    low=float(candle["low"]),
                    high=float(candle["high"]),
                    source="OB/LBM",
                    strength=6 if vol_confirm else 4,
                    note=f"Uproszczony LBM: ostatnia świeca spadkowa przed impulsem wzrostowym{' (silne wsparcie wolumenu)' if vol_confirm else ''}.",
                )

        # SELL OB: świeca wzrostowa, po której następuje wyraźny ruch i wybicie lokalnych low.
        if candle_direction(candle) == "bullish":
            future_break = float(future["low"].min()) < float(previous["low"].min()) if not previous.empty else False
            future_move = float(candle["high"] - future["low"].min())
            if future_break and future_move >= atr:
                has_volume = "volume" in df.columns and "volume_ma" in df.columns
                future_vol_max = float(future["volume"].max()) if has_volume else 0.0
                candle_vol_ma = float(candle["volume_ma"]) if has_volume else 0.0
                vol_confirm = has_volume and future_vol_max > candle_vol_ma * 1.3
                add_zone(
                    zones,
                    direction="sell",
                    zone_type="OB / LBM SELL",
                    low=float(candle["low"]),
                    high=float(candle["high"]),
                    source="OB/LBM",
                    strength=6 if vol_confirm else 4,
                    note=f"Uproszczony LBM: ostatnia świeca wzrostowa przed impulsem spadkowym{' (silne wsparcie wolumenu)' if vol_confirm else ''}.",
                )

    return zones[-20:]


def build_ftr_zones(df: pd.DataFrame, atr: float, lookback: int = 300) -> list[dict[str, Any]]:
    """
    Uproszczony FTR na układzie 3 świec.

    BUY FTR: mocna świeca popytowa, mała świeca podażowa, kolejna świeca zamyka wyżej.
    SELL FTR: mocna świeca podażowa, mała świeca popytowa, kolejna świeca zamyka niżej.
    """
    zones = []
    data = df.tail(lookback)

    if len(data) < 3:
        return zones

    for i in range(1, len(data) - 1):
        c1 = data.iloc[i - 1]
        c2 = data.iloc[i]
        c3 = data.iloc[i + 1]

        body_1 = candle_body(c1)
        body_2 = candle_body(c2)
        body_3 = candle_body(c3)

        if body_1 <= 0 or body_3 <= 0:
            continue

        # BUY FTR.
        if (
            candle_direction(c1) == "bullish"
            and candle_direction(c2) == "bearish"
            and candle_direction(c3) == "bullish"
            and body_2 <= body_1 * 0.60
            and float(c3["close"]) > float(c2["high"])
            and float(c3["close"] - c1["open"]) >= atr * 0.30
        ):
            add_zone(
                zones,
                direction="buy",
                zone_type="FTR BUY",
                low=float(min(c2["low"], c3["low"])),
                high=float(max(c1["high"], c2["high"])),
                source="FTR",
                strength=3,
                note="Uproszczony FTR wzrostowy: nieudana próba cofnięcia ruchu wzrostowego.",
            )

        # SELL FTR.
        if (
            candle_direction(c1) == "bearish"
            and candle_direction(c2) == "bullish"
            and candle_direction(c3) == "bearish"
            and body_2 <= body_1 * 0.60
            and float(c3["close"]) < float(c2["low"])
            and float(c1["open"] - c3["close"]) >= atr * 0.30
        ):
            add_zone(
                zones,
                direction="sell",
                zone_type="FTR SELL",
                low=float(min(c1["low"], c2["low"])),
                high=float(max(c2["high"], c3["high"])),
                source="FTR",
                strength=3,
                note="Uproszczony FTR spadkowy: nieudana próba cofnięcia ruchu spadkowego.",
            )

    return zones[-20:]


def build_pivot_liquidity_cluster_zones(
    swings: pd.DataFrame,
    atr: float,
    min_points: int = 2,
    max_width_pct: float = 12.0,
) -> list[dict[str, Any]]:
    """
    Buduje jakościowe klastry pivotów, nie tylko jeden szeroki zakres.

    Poprzednia wersja zachłannie brała pierwszy pivot i doklejała kolejne, co mogło
    dawać zbyt szeroką strefę typu 140-157, ale nie tworzyło węższego wariantu
    148-155, mimo że ten mógł być lepszy. Teraz generujemy okna cenowe i pozwalamy
    rankingowi wybrać najbardziej wartościowy podzakres.
    """
    candidates: list[dict[str, Any]] = []

    if swings.empty:
        return candidates

    def candidate_overlap_ratio(a: dict[str, Any], b: dict[str, Any]) -> float:
        overlap = max(0.0, min(float(a["high"]), float(b["high"])) - max(float(a["low"]), float(b["low"])))
        min_width = max(min(float(a["high"]) - float(a["low"]), float(b["high"]) - float(b["low"])), 1e-12)
        return overlap / min_width

    for pivot_type, direction, zone_name in [
        ("low", "buy", "Klaster dołków / HTF demand"),
        ("high", "sell", "Klaster szczytów / HTF supply"),
    ]:
        pivots = swings[swings["type"] == pivot_type].copy()
        if len(pivots) < min_points:
            continue

        pivots = pivots.sort_values("price").reset_index(drop=True)
        prices = [float(value) for value in pivots["price"].tolist()]

        for start in range(len(prices)):
            for end in range(start + min_points - 1, len(prices)):
                low_price = prices[start]
                high_price = prices[end]
                midpoint = max((low_price + high_price) / 2, 1e-9)
                width_pct = (high_price - low_price) / midpoint * 100

                if width_pct > max_width_pct:
                    break

                cluster_points = end - start + 1
                if cluster_points < min_points:
                    continue

                # Niewielki padding zapobiega zbyt sztucznemu cięciu strefy, ale nie rozmywa jej.
                padding = max(atr * 0.08, (high_price - low_price) * 0.04)

                compactness_bonus = 2 if width_pct <= 6 else 1 if width_pct <= 9 else 0
                strength = min(6 + min(cluster_points, 4) + compactness_bonus, 12)
                density = cluster_points / max(width_pct, 0.5)

                add_zone(
                    candidates,
                    direction=direction,
                    zone_type=zone_name,
                    low=low_price - padding,
                    high=high_price + padding,
                    source="PIVOT_CLUSTER",
                    strength=strength,
                    note=(
                        f"Klaster {cluster_points} historycznych pivotów w zakresie "
                        f"{low_price:.2f}-{high_price:.2f}. "
                        "Węższe klastry są premiowane, dlatego może powstać zarówno "
                        "szersza strefa 140-157, jak i precyzyjniejsza 148-155."
                    ),
                    meta={
                        "cluster_points": cluster_points,
                        "cluster_width_pct": width_pct,
                        "density": density,
                    },
                )

    # Usuwamy prawie identyczne kopie, ale zostawiamy warianty istotnie węższe/szersze,
    # bo ranking może uznać precyzyjniejszy zakres za lepszy.
    ordered = sorted(
        candidates,
        key=lambda zone: (
            int(zone.get("strength", 0)),
            float(zone.get("meta", {}).get("density", 0.0)),
            -float(zone.get("meta", {}).get("cluster_width_pct", 999.0)),
        ),
        reverse=True,
    )

    unique: list[dict[str, Any]] = []
    for candidate in ordered:
        duplicate = False
        for existing in unique:
            same_direction = candidate["direction"] == existing["direction"]
            same_type = candidate["type"] == existing["type"]
            if same_direction and same_type and candidate_overlap_ratio(candidate, existing) >= 0.92:
                duplicate = True
                break
        if not duplicate:
            unique.append(candidate)
        if len(unique) >= 60:
            break

    return unique


def build_historical_pivot_zones(
    df: pd.DataFrame,
    swings: pd.DataFrame,
    atr: float,
    min_reaction_pct: float = 8.0,
    forward_bars: int = 60,
) -> list[dict[str, Any]]:
    """
    Buduje historyczne strefy HTF demand/supply z dawnych, istotnych pivotów.

    Po co to jest:
    - lokalne FVG/OB/FTR z ostatnich świec nie złapią starych stref typu 31.21-34.42 na NKE,
      jeżeli ta strefa pochodzi z dawnego dołka albo dużej reakcji z wysokiego interwału.
    - ta funkcja bierze cały pobrany zakres danych i szuka miejsc, z których rynek wykonał
      dużą reakcję procentową.

    Logika:
    - Pivot low + późniejszy mocny wzrost = historyczna strefa popytu.
    - Pivot high + późniejszy mocny spadek = historyczna strefa podaży.
    - Zakres strefy bierzemy z pełnej świecy pivotowej, bo w praktyce HTF LBM/OB bywa
      szeroką strefą, a nie jedną linią.
    """
    zones = []

    if df.empty or swings.empty:
        return zones

    for _, swing in swings.iterrows():
        idx = int(swing["idx"])

        if idx < 0 or idx >= len(df) - 5:
            continue

        candle = df.iloc[idx]
        future = df.iloc[idx + 1 : min(len(df), idx + 1 + forward_bars)]

        if future.empty:
            continue

        swing_price = float(swing["price"])

        if swing["type"] == "low":
            max_future_high = float(future["high"].max())
            reaction_pct = (max_future_high - swing_price) / swing_price * 100

            if reaction_pct >= min_reaction_pct:
                strength = 8 if reaction_pct >= 20 else 7
                add_zone(
                    zones,
                    direction="buy",
                    zone_type="Historyczna strefa popytu / HTF demand",
                    low=float(candle["low"]),
                    high=float(candle["high"]),
                    source="HTF/HIST",
                    strength=strength,
                    note=(
                        f"Historyczny pivot low z reakcją +{reaction_pct:.1f}% w kolejnych świecach. "
                        "To ma łapać stare strefy popytowe z dużego kontekstu."
                    ),
                    meta={"reaction_pct": reaction_pct},
                )

        if swing["type"] == "high":
            min_future_low = float(future["low"].min())
            reaction_pct = (swing_price - min_future_low) / swing_price * 100

            if reaction_pct >= min_reaction_pct:
                strength = 8 if reaction_pct >= 20 else 7
                add_zone(
                    zones,
                    direction="sell",
                    zone_type="Historyczna strefa podaży / HTF supply",
                    low=float(candle["low"]),
                    high=float(candle["high"]),
                    source="HTF/HIST",
                    strength=strength,
                    note=(
                        f"Historyczny pivot high z reakcją -{reaction_pct:.1f}% w kolejnych świecach. "
                        "To ma łapać stare strefy podażowe z dużego kontekstu."
                    ),
                    meta={"reaction_pct": reaction_pct},
                )

    return zones


def cluster_nearby_zones(zones: list[dict[str, Any]], atr: float) -> list[dict[str, Any]]:
    """
    Łączy bliskie strefy, ale nie pompuje sztucznie score przez kilkanaście
    powtórzeń tego samego źródła.

    Siła klastra rośnie przede wszystkim wtedy, gdy dochodzi NOWE źródło konfluencji,
    a nie tylko kolejny podobny FVG czy OB z tej samej rodziny.
    """
    if not zones:
        return []

    threshold = max(atr * 0.20, 1e-9)
    max_cluster_width_pct = 14.0
    sorted_zones = sorted(zones, key=lambda z: (z["direction"], z["low"], z["high"]))
    clusters: list[dict[str, Any]] = []

    for zone in sorted_zones:
        merged = False

        for cluster in clusters:
            same_direction = cluster["direction"] == zone["direction"]
            close_or_overlap = zone["low"] <= cluster["high"] + threshold and zone["high"] >= cluster["low"] - threshold

            new_low = min(float(cluster["low"]), float(zone["low"]))
            new_high = max(float(cluster["high"]), float(zone["high"]))
            mid = max((new_low + new_high) / 2, 1e-9)
            new_width_pct = (new_high - new_low) / mid * 100

            if same_direction and close_or_overlap and new_width_pct <= max_cluster_width_pct:
                old_low = float(cluster["low"])
                old_high = float(cluster["high"])
                cluster["low"] = new_low
                cluster["high"] = new_high

                old_sources = {part for part in str(cluster.get("source", "")).split("+") if part}
                new_sources = {part for part in str(zone.get("source", "")).split("+") if part}
                merged_sources = sorted(old_sources | new_sources)
                cluster["source"] = "+".join(merged_sources)

                # Siła rośnie tylko za nowe źródła, nie za liczbę prawie identycznych stref.
                added_sources = max(len(merged_sources) - len(old_sources), 0)
                strength_bonus = min(added_sources, 2)
                cluster["strength"] = min(max(int(cluster.get("strength", 0)), int(zone.get("strength", 0))) + strength_bonus, 12)

                cluster_meta = cluster.setdefault("meta", {})
                cluster_meta["component_count"] = int(cluster_meta.get("component_count", 1)) + 1
                cluster_meta["source_count"] = len(merged_sources)

                if "Klaster" not in str(cluster["type"]):
                    cluster["type"] = f"Klaster {cluster['direction'].upper()}"

                cluster["note"] = (
                    f"Klaster połączonych stref: zakres {old_low:.2f}-{old_high:.2f} "
                    f"rozszerzony o {float(zone['low']):.2f}-{float(zone['high']):.2f}. "
                    f"Źródła: {cluster['source']}."
                )
                merged = True
                break

        if not merged:
            copied = zone.copy()
            copied_meta = dict(copied.get("meta", {}) or {})
            copied_meta.setdefault("component_count", 1)
            copied_meta.setdefault("source_count", len({part for part in str(copied.get("source", "")).split("+") if part}))
            copied["meta"] = copied_meta
            clusters.append(copied)

    return clusters


def filter_entry_zones_by_width(
    zones: list[dict[str, Any]],
    current_price: float,
    max_entry_width_pct: float = 18.0,
) -> list[dict[str, Any]]:
    """
    Ostateczny filtr bezpieczeństwa dla stref wejścia.

    To jest kluczowa poprawka: jeśli wcześniej kilka modułów sklei strefę typu
    84-254 albo 190-266, to taka strefa NIE przechodzi do rankingu wejść.
    Ona jest za szeroka, żeby ustawić sensowne wejście i SL.
    """
    filtered = []

    for zone in zones:
        width = float(zone["high"] - zone["low"])
        width_pct = width / current_price * 100 if current_price > 0 else 999.0

        if width_pct <= max_entry_width_pct:
            filtered.append(zone)

    return filtered


def build_all_zones(
    df: pd.DataFrame, 
    swings: pd.DataFrame, 
    trend: str, 
    df_mtf: pd.DataFrame | None = None,
    mtf_swings: pd.DataFrame | None = None
) -> list[dict[str, Any]]:
    atr = float(df["atr"].iloc[-1]) if "atr" in df.columns else float((df["high"] - df["low"]).tail(14).mean())
    current_price = float(df["close"].iloc[-1])

    zones = []
    zones.extend(build_fibo_zones(swings, atr))
    zones.extend(build_one_to_one_zones(swings, trend, atr))
    zones.extend(build_support_resistance_zones(swings, atr))
    zones.extend(build_pivot_liquidity_cluster_zones(swings, atr))
    zones.extend(build_historical_pivot_zones(df, swings, atr))
    zones.extend(build_fvg_zones(df, atr))
    zones.extend(build_order_block_zones(df, atr))
    zones.extend(build_ftr_zones(df, atr))

    if df_mtf is not None and not df_mtf.empty:
        # Budujemy proste strefy wsparcia/oporu z wykresu MTF i nakładamy z najwyższą wagą
        if mtf_swings is None:
            from .pivots import detect_pivots, build_swings
            mtf_pivots = detect_pivots(df_mtf, left=3, right=3)
            mtf_swings = build_swings(mtf_pivots, min_move_pct=1.0)
            
        if not mtf_swings.empty:
            mtf_atr = float(df_mtf["atr"].iloc[-1]) if "atr" in df_mtf.columns else float((df_mtf["high"] - df_mtf["low"]).tail(14).mean())
            tolerance = mtf_atr * 0.20
            
            recent_mtf_lows = mtf_swings[mtf_swings["type"] == "low"].tail(5)
            recent_mtf_highs = mtf_swings[mtf_swings["type"] == "high"].tail(5)
        
            for row in recent_mtf_lows.itertuples():
                add_zone(
                    zones,
                    direction="buy",
                    zone_type="Strefa MTF (Wyższy Interwał)",
                    low=float(row.price) - tolerance,
                    high=float(row.price) + tolerance,
                    source="HTF/HIST", # Silne źródło z configu
                    strength=10, # MTF ma najwyższy priorytet
                    note="Kluczowa strefa wsparcia z wyższego interwału czasowego.",
                )
                
            for row in recent_mtf_highs.itertuples():
                add_zone(
                    zones,
                    direction="sell",
                    zone_type="Strefa MTF (Wyższy Interwał)",
                    low=float(row.price) - tolerance,
                    high=float(row.price) + tolerance,
                    source="HTF/HIST", # Silne źródło z configu
                    strength=10, # MTF ma najwyższy priorytet
                    note="Kluczowa strefa oporu z wyższego interwału czasowego.",
                )

    clustered = cluster_nearby_zones(zones, atr)

    # Ostateczny filtr: ranking stref wejścia ma pokazywać miejsca praktyczne,
    # nie abstrakcyjne megaklastry. Strefy powyżej 18% szerokości usuwamy z rankingu.
    return filter_entry_zones_by_width(clustered, current_price, max_entry_width_pct=18.0)
