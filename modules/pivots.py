import pandas as pd


def detect_pivots(df: pd.DataFrame, left: int, right: int) -> pd.DataFrame:
    """
    Wykrywa lokalne szczyty i dołki.

    Pivot high: high świecy jest najwyższy w oknie left/right.
    Pivot low: low świecy jest najniższy w oknie left/right.
    """
    if df.empty or len(df) < left + right + 1:
        return pd.DataFrame(columns=["idx", "time", "type", "price"])

    high = df["high"]
    low = df["low"]

    left_high_max = pd.concat([high.shift(i) for i in range(0, left + 1)], axis=1).max(axis=1)
    left_low_min = pd.concat([low.shift(i) for i in range(0, left + 1)], axis=1).min(axis=1)

    right_high_max = pd.concat([high.shift(-i) for i in range(0, right + 1)], axis=1).max(axis=1)
    right_low_min = pd.concat([low.shift(-i) for i in range(0, right + 1)], axis=1).min(axis=1)

    is_pivot_high = high.eq(left_high_max) & high.eq(right_high_max)
    is_pivot_low = low.eq(left_low_min) & low.eq(right_low_min)

    is_pivot_high.iloc[:left] = False
    is_pivot_high.iloc[len(df) - right :] = False
    is_pivot_low.iloc[:left] = False
    is_pivot_low.iloc[len(df) - right :] = False

    high_pivots = pd.DataFrame({
        "idx": [df.index.get_loc(t) for t in df.index[is_pivot_high]],
        "time": df.index[is_pivot_high],
        "type": "high",
        "price": df.loc[is_pivot_high, "high"].astype(float)
    })
    
    low_pivots = pd.DataFrame({
        "idx": [df.index.get_loc(t) for t in df.index[is_pivot_low]],
        "time": df.index[is_pivot_low],
        "type": "low",
        "price": df.loc[is_pivot_low, "low"].astype(float)
    })

    pivot_df = pd.concat([high_pivots, low_pivots]).sort_values("idx").reset_index(drop=True)
    
    if pivot_df.empty:
        return pd.DataFrame(columns=["idx", "time", "type", "price"])

    return pivot_df


def build_swings(pivots: pd.DataFrame, min_move_pct: float) -> pd.DataFrame:
    """
    Buduje naprzemienną strukturę swingów high-low-high-low.
    Małe ruchy są odrzucane przez min_move_pct.
    """
    if pivots.empty:
        return pivots

    swings = []

    for row in pivots.itertuples(index=False):
        pivot_data = {
            "idx": row.idx,
            "time": row.time,
            "type": row.type,
            "price": row.price
        }

        if not swings:
            swings.append(pivot_data)
            continue

        last = swings[-1]

        # Dwa pivoty tego samego typu obok siebie: zostaje bardziej skrajny.
        if pivot_data["type"] == last["type"]:
            if pivot_data["type"] == "high" and pivot_data["price"] > last["price"]:
                swings[-1] = pivot_data
            elif pivot_data["type"] == "low" and pivot_data["price"] < last["price"]:
                swings[-1] = pivot_data
            continue

        move_pct = abs(pivot_data["price"] - last["price"]) / last["price"] * 100

        if move_pct >= min_move_pct:
            swings.append(pivot_data)

    return pd.DataFrame(swings)
