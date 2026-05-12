import re
from typing import Iterable

import ccxt
import pandas as pd
import streamlit as st
import yfinance as yf


# Nazwy wygodne dla człowieka, które nie są formalnymi tickerami Yahoo.
# Najważniejszy przypadek: ORLEN na Yahoo Finance nadal występuje jako PKN.WA.
POLISH_STOCK_ALIASES = {
    "ORLEN": "PKN.WA",
    "PKNORLEN": "PKN.WA",
    "PKN": "PKN.WA",
}


@st.cache_data(ttl=300)
def fetch_stock_ohlcv(ticker: str, timeframe: str, limit: int) -> pd.DataFrame:
    """
    Pobiera dane OHLCV dla akcji/ETF z Yahoo Finance.

    Dodatkowe ułatwienia:
    - ORLEN / PKN / PKNORLEN -> PKN.WA,
    - jeżeli prosty ticker bez sufiksu nie zadziała, program próbuje też wariantu .WA,
      dzięki czemu łatwiej wpisywać polskie tickery, np. KGH -> KGH.WA.
    """
    interval, period = get_yfinance_params(timeframe)
    candidates = build_stock_ticker_candidates(ticker)
    errors: list[str] = []

    for candidate in candidates:
        try:
            raw = download_yahoo_frame(candidate, period=period, interval=interval)
        except Exception as error:  # noqa: BLE001 - chcemy pokazać czytelną diagnozę końcową.
            errors.append(f"{candidate}: {error}")
            continue

        if raw.empty:
            errors.append(f"{candidate}: brak danych")
            continue

        df = normalize_yahoo_ohlcv(raw)

        if timeframe == "4h":
            df = resample_to_4h(df)

        df = df.tail(limit)
        df.attrs["resolved_symbol"] = candidate
        df.attrs["data_source"] = "Yahoo Finance"
        return df

    attempted = ", ".join(candidates)
    extra = f" Szczegóły: {' | '.join(errors[-3:])}" if errors else ""
    raise ValueError(
        "Brak danych dla podanego symbolu. "
        f"Próbowano: {attempted}. "
        "Dla GPW możesz użyć np. PKN.WA, KGH.WA, CDR.WA, 11B.WA; "
        "Orlen możesz wpisać też jako ORLEN."
        + extra
    )


@st.cache_data(ttl=300)
def fetch_crypto_yahoo_ohlcv(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """
    Pobiera dane krypto przez Yahoo Finance.

    To jest stabilniejsza opcja na Streamlit Community Cloud niż odpytywanie części giełd
    przez CCXT. Wpisy typu BTC/USDT lub ETH/USDT są zamieniane na Yahoo: BTC-USD, ETH-USD.
    """
    interval, period = get_yfinance_params(timeframe)
    yahoo_symbol = normalize_crypto_to_yahoo(symbol)

    raw = download_yahoo_frame(yahoo_symbol, period=period, interval=interval)
    if raw.empty:
        raise ValueError(
            f"Brak danych krypto z Yahoo Finance dla '{symbol}' po zamianie na '{yahoo_symbol}'. "
            "Przykłady: BTC/USDT, ETH/USDT, SOL/USDT, BTC-USD."
        )

    df = normalize_yahoo_ohlcv(raw)

    if timeframe == "4h":
        df = resample_to_4h(df)

    df = df.tail(limit)
    df.attrs["resolved_symbol"] = yahoo_symbol
    df.attrs["data_source"] = "Yahoo Finance"
    return df


@st.cache_data(ttl=300)
def fetch_crypto_ccxt_ohlcv(exchange_id: str, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """Pobiera dane OHLCV dla krypto przez CCXT z wybranej giełdy."""
    if not hasattr(ccxt, exchange_id):
        raise ValueError(f"Nieobsługiwana giełda CCXT: {exchange_id}")

    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})

    ccxt_timeframe = "1w" if timeframe == "1wk" else timeframe
    crypto_limit = min(limit, 1000)

    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe=ccxt_timeframe, limit=crypto_limit)
    except Exception as error:  # noqa: BLE001
        text = str(error)
        if "451" in text or "restricted location" in text.lower():
            raise ValueError(
                "Wybrana giełda zablokowała dostęp z hostingu Streamlit Cloud. "
                "Wybierz źródło 'Yahoo Finance — stabilne na hostingu' w panelu po lewej."
            ) from error
        raise ValueError(f"Nie udało się pobrać danych z CCXT ({exchange_id}): {error}") from error

    if not candles:
        raise ValueError(f"Brak świec z giełdy {exchange_id} dla pary {symbol}.")

    df = pd.DataFrame(
        candles,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert(None)
    df = df.set_index("time")
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.attrs["resolved_symbol"] = symbol
    df.attrs["data_source"] = f"CCXT: {exchange_id}"
    return df


def download_yahoo_frame(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Jedno miejsce odpowiedzialne za pobieranie danych z Yahoo Finance."""
    raw = yf.download(
        tickers=ticker,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    return raw


def normalize_yahoo_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalizuje ramkę zwracaną przez yfinance do kolumn używanych w aplikacji."""
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.copy()
        raw.columns = raw.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise ValueError(f"Yahoo zwróciło niekompletne dane. Brak kolumn: {', '.join(missing)}")

    df = pd.DataFrame(index=raw.index)
    df["open"] = raw["Open"]
    df["high"] = raw["High"]
    df["low"] = raw["Low"]
    df["close"] = raw["Close"]
    df["volume"] = raw["Volume"]
    return df.dropna()


def build_stock_ticker_candidates(ticker: str) -> list[str]:
    """Buduje kolejność symboli, które warto przetestować dla akcji/ETF."""
    cleaned = ticker.strip().upper().replace(" ", "")
    if not cleaned:
        return []

    alias = POLISH_STOCK_ALIASES.get(cleaned)
    if alias:
        return [alias]

    candidates = [cleaned]

    # Jeżeli użytkownik wpisał prosty ticker bez giełdy, po próbie bazowej sprawdzamy GPW.
    # NKE, TTWO itd. przejdą od razu na pierwszym kandydacie, a np. KGH ma szansę wejść jako KGH.WA.
    if "." not in cleaned and "-" not in cleaned and "/" not in cleaned:
        candidates.append(f"{cleaned}.WA")

    return deduplicate_preserve_order(candidates)


def normalize_crypto_to_yahoo(symbol: str) -> str:
    """
    Zamienia wygodne zapisy kryptowalut na format Yahoo Finance.

    Obsługiwane przykłady:
    - BTC/USDT -> BTC-USD
    - ETH/USDT -> ETH-USD
    - SOL-USDT -> SOL-USD
    - BTCUSD -> BTC-USD
    - BTC-USD -> BTC-USD
    - BTC -> BTC-USD
    """
    cleaned = symbol.strip().upper().replace(" ", "")
    if not cleaned:
        raise ValueError("Nie podano symbolu krypto.")

    cleaned = cleaned.replace("XBT", "BTC")
    cleaned = cleaned.replace("_", "-")

    if "/" in cleaned:
        base, quote = cleaned.split("/", 1)
        return crypto_pair_to_yahoo(base, quote)

    if "-" in cleaned:
        base, quote = cleaned.split("-", 1)
        return crypto_pair_to_yahoo(base, quote)

    match = re.fullmatch(r"([A-Z0-9]+)(USDT|USD|BTC|ETH)", cleaned)
    if match:
        base, quote = match.groups()
        return crypto_pair_to_yahoo(base, quote)

    # Sam skrót monety traktujemy jako kurs do USD.
    return f"{cleaned}-USD"


def crypto_pair_to_yahoo(base: str, quote: str) -> str:
    base = base.strip().upper()
    quote = quote.strip().upper()

    if quote in {"USDT", "USDC", "USD"}:
        quote = "USD"

    return f"{base}-{quote}"


def deduplicate_preserve_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def get_yfinance_params(timeframe: str) -> tuple[str, str]:
    """Dobiera interwał i zakres historii dla Yahoo Finance."""
    if timeframe == "15m":
        return "15m", "60d"
    if timeframe == "1h":
        return "1h", "730d"
    if timeframe == "4h":
        return "1h", "730d"
    if timeframe == "1d":
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
        if exchange_id == "yahoo":
            return fetch_crypto_yahoo_ohlcv(ticker, timeframe, limit)
        return fetch_crypto_ccxt_ohlcv(exchange_id, ticker, timeframe, limit)

    raise ValueError("Nieznane źródło danych.")
