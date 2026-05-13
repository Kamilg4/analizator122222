# =========================================================
# KONFIGURACJA
# =========================================================

OVB_RATIO = 1.414
FIBO_LEVELS = [0.382, 0.414, 0.5, 0.618, 0.667]
FIBO_MAIN_LEVELS = [0.5, 0.618, 0.667]
DEFAULT_RSI_PERIOD = 14
DEFAULT_ATR_PERIOD = 14

# Wersja patcha
APP_VERSION = "2026-05-13-v8-widoczne-strefy-i-prosta-tabela"

# Ranking główny — pokazujemy tylko kilka najbardziej użytecznych kandydatów.
TOP_ZONES_TO_DISPLAY = 5

# Warunek opłacalności setupu.
# Użytkownik chciał układ mniej więcej 1:2. Zostawiamy niewielką tolerancję,
# bo TP/SL są liczone z danych świecowych i mogą nie wypaść co do grosza.
MIN_ACCEPTABLE_RR = 1.80
TARGET_RR = 2.00

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
