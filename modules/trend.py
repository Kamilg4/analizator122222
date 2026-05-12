from typing import Any
import pandas as pd


def calculate_trend_scores(swings: pd.DataFrame, points_to_check: int) -> dict[str, Any]:
    """
    Liczy jakość trendu na kilku ostatnich szczytach/dołkach.
    Dzięki temu w konsolidacji algorytm rzadziej zmienia zdanie.
    """
    empty_result = {
        "available": False,
        "high_up_score": 0.0,
        "low_up_score": 0.0,
        "high_down_score": 0.0,
        "low_down_score": 0.0,
        "up_score": 0.0,
        "down_score": 0.0,
        "high_count": 0,
        "low_count": 0,
    }

    if swings.empty:
        return empty_result

    highs = swings[swings["type"] == "high"].tail(points_to_check)["price"].reset_index(drop=True)
    lows = swings[swings["type"] == "low"].tail(points_to_check)["price"].reset_index(drop=True)

    if len(highs) < 3 or len(lows) < 3:
        return empty_result | {"high_count": len(highs), "low_count": len(lows)}

    high_diff = highs.diff().dropna()
    low_diff = lows.diff().dropna()

    high_up_score = float((high_diff > 0).mean())
    low_up_score = float((low_diff > 0).mean())
    high_down_score = float((high_diff < 0).mean())
    low_down_score = float((low_diff < 0).mean())

    up_score = (high_up_score + low_up_score) / 2
    down_score = (high_down_score + low_down_score) / 2

    return {
        "available": True,
        "high_up_score": high_up_score,
        "low_up_score": low_up_score,
        "high_down_score": high_down_score,
        "low_down_score": low_down_score,
        "up_score": up_score,
        "down_score": down_score,
        "high_count": len(highs),
        "low_count": len(lows),
    }


def determine_trend(swings: pd.DataFrame, points_to_check: int, min_score: float) -> str:
    """Określa trend na podstawie kilku ostatnich szczytów i dołków."""
    scores = calculate_trend_scores(swings, points_to_check)

    if not scores["available"]:
        return "nieczytelny"

    if scores["up_score"] >= min_score and scores["up_score"] > scores["down_score"]:
        return "wzrostowy"

    if scores["down_score"] >= min_score and scores["down_score"] > scores["up_score"]:
        return "spadkowy"

    return "nieczytelny"


def get_trend_comment(trend: str, scores: dict[str, Any], min_score: float) -> str:
    if not scores.get("available"):
        return "Za mało swingów, żeby wiarygodnie określić trend."

    up_pct = scores["up_score"] * 100
    down_pct = scores["down_score"] * 100
    min_pct = min_score * 100

    if trend == "wzrostowy":
        return f"Struktura częściej tworzy wyższe szczyty i wyższe dołki. Wynik wzrostowy: {up_pct:.0f}% przy wymaganych {min_pct:.0f}%."

    if trend == "spadkowy":
        return f"Struktura częściej tworzy niższe szczyty i niższe dołki. Wynik spadkowy: {down_pct:.0f}% przy wymaganych {min_pct:.0f}%."

    return f"Rynek jest nieczytelny albo konsolidacyjny. Wynik wzrostowy: {up_pct:.0f}%, wynik spadkowy: {down_pct:.0f}%, wymagane: {min_pct:.0f}%."
