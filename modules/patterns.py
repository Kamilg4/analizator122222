from typing import Any
import pandas as pd


def candle_direction(row: pd.Series) -> str:
    if row["close"] > row["open"]:
        return "bullish"
    if row["close"] < row["open"]:
        return "bearish"
    return "neutral"


def candle_body(row: pd.Series) -> float:
    return abs(float(row["close"] - row["open"]))


def candle_range(row: pd.Series) -> float:
    return max(float(row["high"] - row["low"]), 1e-12)


def detect_recent_candle_patterns(df: pd.DataFrame, lookback: int = 5) -> dict[str, Any]:
    """Wykrywa proste formacje świecowe z ostatnich świec."""
    if len(df) < 3:
        return {"bullish": [], "bearish": [], "summary": "Za mało świec."}

    recent = df.tail(lookback)
    bullish_patterns = []
    bearish_patterns = []

    for i in range(max(1, len(df) - lookback), len(df)):
        current = df.iloc[i]
        previous = df.iloc[i - 1]

        body = candle_body(current)
        rng = candle_range(current)
        upper_wick = float(current["high"] - max(current["open"], current["close"]))
        lower_wick = float(min(current["open"], current["close"]) - current["low"])
        close_position = float((current["close"] - current["low"]) / rng)

        # Shakeout / młotek.
        if lower_wick >= 2 * max(body, 1e-12) and close_position >= 0.70:
            bullish_patterns.append("shakeout / młotek")

        # Spadająca gwiazda.
        if upper_wick >= 2 * max(body, 1e-12) and close_position <= 0.30:
            bearish_patterns.append("spadająca gwiazda")

        # Objęcie hossy.
        if (
            candle_direction(previous) == "bearish"
            and candle_direction(current) == "bullish"
            and current["open"] <= previous["close"]
            and current["close"] >= previous["open"]
        ):
            bullish_patterns.append("objęcie hossy")

        # Objęcie bessy.
        if (
            candle_direction(previous) == "bullish"
            and candle_direction(current) == "bearish"
            and current["open"] >= previous["close"]
            and current["close"] <= previous["open"]
        ):
            bearish_patterns.append("objęcie bessy")

        # Przenikanie / zasłona.
        prev_mid = float((previous["open"] + previous["close"]) / 2)
        if candle_direction(previous) == "bearish" and candle_direction(current) == "bullish" and current["close"] > prev_mid:
            bullish_patterns.append("przenikanie")
        if candle_direction(previous) == "bullish" and candle_direction(current) == "bearish" and current["close"] < prev_mid:
            bearish_patterns.append("zasłona ciemnej chmury")

    bullish_unique = sorted(set(bullish_patterns))
    bearish_unique = sorted(set(bearish_patterns))

    summary = []
    if bullish_unique:
        summary.append("BUY: " + ", ".join(bullish_unique))
    if bearish_unique:
        summary.append("SELL: " + ", ".join(bearish_unique))

    return {
        "bullish": bullish_unique,
        "bearish": bearish_unique,
        "summary": " | ".join(summary) if summary else "Brak wyraźnych formacji z ostatnich świec.",
        "last_rsi": float(df["rsi"].iloc[-1]) if "rsi" in df.columns else None,
    }


def detect_rsi_divergence(df: pd.DataFrame, swings: pd.DataFrame) -> dict[str, Any]:
    """Uproszczona dywergencja RSI na ostatnich dwóch szczytach/dołkach."""
    result = {
        "bullish": False,
        "bearish": False,
        "status": "Brak dywergencji RSI.",
    }

    if swings.empty or "rsi" not in df.columns:
        result["status"] = "Brak danych RSI albo swingów."
        return result

    lows = swings[swings["type"] == "low"].tail(2)
    highs = swings[swings["type"] == "high"].tail(2)

    messages = []

    if len(lows) == 2:
        low_1 = lows.iloc[0]
        low_2 = lows.iloc[1]
        rsi_1 = float(df.loc[low_1["time"], "rsi"]) if low_1["time"] in df.index else None
        rsi_2 = float(df.loc[low_2["time"], "rsi"]) if low_2["time"] in df.index else None

        if rsi_1 is not None and rsi_2 is not None:
            if low_2["price"] < low_1["price"] and rsi_2 > rsi_1:
                result["bullish"] = True
                messages.append("Bycza dywergencja RSI: cena robi niższy dołek, RSI wyższy dołek.")

    if len(highs) == 2:
        high_1 = highs.iloc[0]
        high_2 = highs.iloc[1]
        rsi_1 = float(df.loc[high_1["time"], "rsi"]) if high_1["time"] in df.index else None
        rsi_2 = float(df.loc[high_2["time"], "rsi"]) if high_2["time"] in df.index else None

        if rsi_1 is not None and rsi_2 is not None:
            if high_2["price"] > high_1["price"] and rsi_2 < rsi_1:
                result["bearish"] = True
                messages.append("Niedźwiedzia dywergencja RSI: cena robi wyższy szczyt, RSI niższy szczyt.")

    if messages:
        result["status"] = " | ".join(messages)

    return result


def get_rsi_signal(df: pd.DataFrame) -> dict[str, Any]:
    last_rsi = float(df["rsi"].iloc[-1]) if "rsi" in df.columns else 50.0

    if last_rsi <= 30:
        return {"direction": "buy", "rsi": last_rsi, "status": "RSI nisko — potencjalne wsparcie dla BUY."}
    if last_rsi >= 70:
        return {"direction": "sell", "rsi": last_rsi, "status": "RSI wysoko — potencjalne wsparcie dla SELL / realizacji zysków."}

    return {"direction": "neutral", "rsi": last_rsi, "status": "RSI neutralne."}
