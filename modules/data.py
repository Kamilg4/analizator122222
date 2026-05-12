import ccxt
import pandas as pd
import streamlit as st
import yfinance as yf


@st.cache_data(ttl=300)
def fetch_stock_ohlcv(ticker: str, timeframe: str, limit: int) -> pd.DataFrame:
    """Pobiera dane OHLCV dla akcji/ETF z Yahoo Finance."""
    interval, period = get_yfinance_params(timeframe)

    raw = yf.download(
        tickers=ticker,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if raw.empty:
        raise ValueError(
            "Brak danych. Sprawdź ticker, np. NKE, TTWO, AAPL, MSFT, ADS.DE, RHM.DE."
        )

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = pd.DataFrame(index=raw.index)
    df["open"] = raw["Open"]
    df["high"] = raw["High"]
    df["low"] = raw["Low"]
    df["close"] = raw["Close"]
    df["volume"] = raw["Volume"]
    df = df.dropna()

    if timeframe == "4h":
        df = resample_to_4h(df)

    return df.tail(limit)


@st.cache_data(ttl=300)
def fetch_crypto_ohlcv(exchange_id: str, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """Pobiera dane OHLCV dla krypto przez CCXT."""
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})

    if timeframe == "1wk":
        timeframe = "1w"

    # Część giełd krypto ogranicza liczbę świec w jednym zapytaniu.
    crypto_limit = min(limit, 1000)
    candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=crypto_limit)

    df = pd.DataFrame(
        candles,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )

    df["time"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("time")

    return df[["open", "high", "low", "close", "volume"]].dropna()


def get_yfinance_params(timeframe: str) -> tuple[str, str]:
    """Dobiera interwał i zakres historii dla Yahoo Finance."""
    if timeframe == "15m":
        return "15m", "60d"
    if timeframe == "1h":
        return "1h", "730d"
    if timeframe == "4h":
        return "1h", "730d"
    if timeframe == "1d":
        # 10 lat historii jest potrzebne, żeby łapać stare strefy HTF,
        # np. historyczne demand/supply, które mogą leżeć dużo niżej/wyżej od aktualnej ceny.
        return "1d", "10y"
    if timeframe == "1wk":
        return "1wk", "10y"

    raise ValueError(f"Nieobsługiwany interwał: {timeframe}")


def resample_to_4h(df: pd.DataFrame) -> pd.DataFrame:
    """Buduje świece 4H ze świec 1H."""
    df_4h = df.resample("4h").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )

    return df_4h.dropna()


def fetch_ohlcv(source: str, ticker: str, exchange_id: str, timeframe: str, limit: int) -> pd.DataFrame:
    """Główna funkcja pobierająca dane dla akcji albo krypto."""
    if source == "Akcje / ETF":
        return fetch_stock_ohlcv(ticker, timeframe, limit)

    if source == "Krypto":
        return fetch_crypto_ohlcv(exchange_id, ticker, timeframe, limit)

    raise ValueError("Nieznane źródło danych.")
