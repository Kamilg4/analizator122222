import math
import pandas as pd
from .config import DEFAULT_RSI_PERIOD, DEFAULT_ATR_PERIOD


def add_indicators(df: pd.DataFrame, rsi_period: int = DEFAULT_RSI_PERIOD, atr_period: int = DEFAULT_ATR_PERIOD) -> pd.DataFrame:
    """Dodaje RSI, ATR oraz średnią wolumenu do danych."""
    result = df.copy()
    result["rsi"] = calculate_rsi(result["close"], period=rsi_period)
    result["atr"] = calculate_atr(result, period=atr_period)
    if "volume" in result.columns:
        result["volume_ma"] = result["volume"].rolling(20).mean().bfill()
    return result


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Liczy RSI metodą średnich wykładniczych."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, math.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Liczy ATR."""
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()

    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(period).mean()
    return atr.bfill()
