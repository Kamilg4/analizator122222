# =========================================================
# KONFIGURACJA
# =========================================================

OVB_RATIO = 1.414
FIBO_LEVELS = [0.382, 0.414, 0.5, 0.618, 0.667]
FIBO_MAIN_LEVELS = [0.5, 0.618, 0.667]
DEFAULT_RSI_PERIOD = 14
DEFAULT_ATR_PERIOD = 14

# Wersja patcha
APP_VERSION = "2026-05-14-v10-optymalizacja-wynikow"

# Ranking główny — pokazujemy tylko kilka najbardziej użytecznych kandydatów.
TOP_ZONES_TO_DISPLAY = 5

# Warunek opłacalności setupu.
# Obniżony po analizie statystyk MFE (średnie Max Favorable Excursion wynosiło 1.12R).
MIN_ACCEPTABLE_RR = 1.30
SELL_MIN_ACCEPTABLE_RR = 1.80  # SELL wymaga wyższego R:R (win rate 32.6% vs BUY 36.9%)
TARGET_RR = 1.414  # Obniżone z 1.618 — avg MFE=1.05R, wiele trade'ów nie dociera do 1.618

# Progi ELITE alertów skanera — tylko naprawdę wyjątkowe strefy
ELITE_ALERT_MIN_QUALITY = 28
ELITE_ALERT_MIN_SCORE = 40
ELITE_ALERT_MIN_RR = 1.80

# Konfiguracja skanera autonomicznego
SCAN_INTERVAL_HOURS = 6
SCAN_TIMEFRAME = "1d"
SCAN_CANDLES = 2500

# Słowniki Tickerów do UI
POPULAR_STOCKS = {
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
    "IWM": "iShares Russell 2000 ETF",
    "DIA": "SPDR Dow Jones Industrial ETF",
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corp.",
    "NVDA": "NVIDIA Corp.",
    "AMZN": "Amazon.com Inc.",
    "META": "Meta Platforms Inc.",
    "GOOGL": "Alphabet Inc.",
    "TSLA": "Tesla Inc.",
    "AMD": "Advanced Micro Devices",
    "JPM": "JPMorgan Chase & Co.",
    "NKE": "Nike Inc.",
    "TTWO": "Take-Two Interactive",
    "ADS.DE": "Adidas AG",
    "GLD": "SPDR Gold Shares ETF",
    "SLV": "iShares Silver Trust ETF",
    "PKN.WA": "ORLEN S.A.",
    "PKO.WA": "PKO Bank Polski",
    "ALE.WA": "Allegro.eu",
    "DNP.WA": "Dino Polska",
    "CDR.WA": "CD Projekt",
    "KGH.WA": "KGHM Polska Miedź",
    "PFE": "Pfizer Inc.",
    "UUUU": "Energy Fuels Inc.",
    "MMM": "3M Company",
    "BABA": "Alibaba Group",
    "NFLX": "Netflix Inc.",
    "DIS": "Walt Disney Company",
    "2823.HK": "iShares FTSE China A50 ETF",
}

POPULAR_CRYPTO = {
    "BTC/USDT": "Bitcoin",
    "ETH/USDT": "Ethereum",
    "SOL/USDT": "Solana",
    "XRP/USDT": "Ripple",
    "ADA/USDT": "Cardano",
    "DOGE/USDT": "Dogecoin",
    "DOT/USDT": "Polkadot",
    "LINK/USDT": "Chainlink",
}

# Czytelny wykres ma z założenia pokazywać mało stref.
# Widok główny ma pomagać podjąć decyzję, a nie prezentować pełną mapę wszystkich możliwych stref.
# Dlatego pokazujemy domyślnie tylko:
# - 1 strefę główną,
# - 1 wyraźnie odseparowaną strefę alternatywną.
READABLE_CHART_MAX_ZONES = 2
DIAGNOSTIC_CHART_MAX_ZONES = 5
READABLE_CHART_MAX_OVERLAP_RATIO = 0.12

# Zachowane jako parametr pomocniczy do ewentualnych przyszłych filtrów UI.
# W wersji v8 czytelny wykres rysuje strefy z rankingu nawet wtedy, gdy są strategiczne i dalekie.
READABLE_CHART_MAX_DISTANCE_PCT = 18.0
