import streamlit as st
import pandas as pd

# Import konfiguracji
from modules.config import (
    APP_VERSION,
    TOP_ZONES_TO_DISPLAY,
    MIN_ACCEPTABLE_RR,
    TARGET_RR,
    READABLE_CHART_MAX_ZONES,
    DIAGNOSTIC_CHART_MAX_ZONES,
)

# Importy modułów
from modules.data import fetch_ohlcv
from modules.indicators import add_indicators
from modules.pivots import detect_pivots, build_swings
from modules.trend import calculate_trend_scores, determine_trend, get_trend_comment
from modules.ovb_bos import calculate_ovb, calculate_bos, check_opposite_structure, build_trend_change_summary
from modules.patterns import detect_recent_candle_patterns, detect_rsi_divergence, get_rsi_signal
from modules.zones import build_all_zones
from modules.evaluation import evaluate_zones, select_top_zones, select_active_zones, select_strategic_zones, select_chart_zones
from modules.elliott import detect_elliott_scenario
from modules.chart import make_chart


def _fmt_num(value: object, decimals: int = 2) -> str:
    """Bezpieczne formatowanie liczb do prostych tabel użytkowych."""
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "-"


def _human_direction(value: object) -> str:
    direction = str(value).lower()
    if direction == "buy":
        return "BUY"
    if direction == "sell":
        return "SELL"
    return str(value)


def _compact_zone_table(zones_df: pd.DataFrame) -> pd.DataFrame:
    """Buduje prostą tabelę decyzyjną bez wewnętrznych metryk algorytmu."""
    if zones_df is None or zones_df.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for _, row in zones_df.iterrows():
        rows.append(
            {
                "Kod": row.get("zone_code", "-"),
                "Kierunek": _human_direction(row.get("direction", "")),
                "Klasa": row.get("entry_class", "-"),
                "Strefa": f"{_fmt_num(row.get('low'))} – {_fmt_num(row.get('high'))}",
                "Wejście": _fmt_num(row.get("entry")),
                "SL bezp.": _fmt_num(row.get("safe_sl")),
                "TP": _fmt_num(row.get("tp")),
                "R:R": _fmt_num(row.get("rr")),
                "Świeżość": row.get("freshness", "-"),
                "Decyzja": row.get("decision", "-"),
            }
        )

    return pd.DataFrame(rows)


def _run_full_analysis(
    source: str,
    ticker: str,
    exchange_id: str,
    timeframe: str,
    limit: int,
    pivot_left: int,
    pivot_right: int,
    min_move_pct: float,
    trend_points: int,
    min_trend_score: float,
) -> dict:
    """Wykonuje pełną analizę i zwraca komplet danych do renderowania UI."""
    df = fetch_ohlcv(source, ticker, exchange_id, timeframe, limit)
    df = add_indicators(df)

    pivots = detect_pivots(df, left=pivot_left, right=pivot_right)
    swings = build_swings(pivots, min_move_pct=min_move_pct)
    trend_scores = calculate_trend_scores(swings, trend_points)
    trend = determine_trend(swings, points_to_check=trend_points, min_score=min_trend_score)

    ovb_result = calculate_ovb(swings, trend, df.iloc[-1])
    bos_result = calculate_bos(swings, trend, df.iloc[-1])
    opposite_structure = check_opposite_structure(swings, trend)
    trend_change_summary = build_trend_change_summary(ovb_result, bos_result, opposite_structure)

    candle_patterns = detect_recent_candle_patterns(df)
    rsi_signal = get_rsi_signal(df)
    rsi_divergence = detect_rsi_divergence(df, swings)
    elliott = detect_elliott_scenario(swings, trend)

    zones = build_all_zones(df, swings, trend)
    zones_df = evaluate_zones(zones, df, swings, trend, candle_patterns, rsi_signal, rsi_divergence)
    top_zones_df = select_top_zones(zones_df, top_n=TOP_ZONES_TO_DISPLAY)
    active_zones_df = select_active_zones(zones_df, top_n=3)
    strategic_zones_df = select_strategic_zones(zones_df, top_n=3)

    return {
        "df": df,
        "pivots": pivots,
        "swings": swings,
        "trend_scores": trend_scores,
        "trend": trend,
        "ovb_result": ovb_result,
        "bos_result": bos_result,
        "opposite_structure": opposite_structure,
        "trend_change_summary": trend_change_summary,
        "candle_patterns": candle_patterns,
        "rsi_signal": rsi_signal,
        "rsi_divergence": rsi_divergence,
        "elliott": elliott,
        "zones": zones,
        "zones_df": zones_df,
        "top_zones_df": top_zones_df,
        "active_zones_df": active_zones_df,
        "strategic_zones_df": strategic_zones_df,
    }


def _analysis_params_signature(
    source: str,
    ticker: str,
    exchange_id: str,
    timeframe: str,
    limit: int,
    pivot_left: int,
    pivot_right: int,
    min_move_pct: float,
    trend_points: int,
    min_trend_score: float,
) -> tuple:
    """Zapis parametrów, żeby ostrzec użytkownika po ich zmianie bez ponownej analizy."""
    return (
        source,
        ticker,
        exchange_id,
        timeframe,
        int(limit),
        int(pivot_left),
        int(pivot_right),
        float(min_move_pct),
        int(trend_points),
        float(min_trend_score),
    )


def main() -> None:
    st.set_page_config(page_title="Analizator Tradingowy — FULL", layout="wide")

    st.title("Analizator Tradingowy — FULL PROTOTYPE")
    st.caption(f"Wersja kodu: {APP_VERSION}")
    st.caption("Patch v8: strefa z głównego rankingu jest zawsze rysowana na wykresie, także gdy jest strategiczna. Główna tabela jest uproszczona do danych naprawdę przydatnych decyzyjnie.")
    st.write(
        "Pełny prototyp: dane, pivoty, swingi, trend, OVB, BOS, 3x zmiana trendu, "
        "RSI, formacje świecowe, Fibo, 1:1, OB/LBM, FTR, FVG, strefy, SL/TP/R:R i prosty scenariusz Elliotta."
    )

    st.warning(
        "To jest algorytmiczny prototyp, a nie pewny automat do zarabiania. "
        "OB/LBM, FTR, FVG, Body/Wyckoff i fale Elliotta są tutaj uproszczone regułami matematycznymi. "
        "Wyniki wymagają kontroli na wykresie."
    )

    with st.sidebar:
        st.header("Ustawienia analizy")

        source = st.selectbox("Rynek", ["Akcje / ETF", "Krypto"], index=0)

        if source == "Akcje / ETF":
            ticker = st.text_input("Ticker", "NKE").upper().strip()
            exchange_id = ""
            st.caption(
                "Przykłady: NKE, TTWO, AAPL, MSFT, ADS.DE, RHM.DE, 11B.WA, PKN.WA. "
                "Możesz wpisać ORLEN — aplikacja zamieni to na PKN.WA."
            )
        else:
            ticker = st.text_input("Para krypto", "BTC/USDT").upper().strip()
            exchange_id = st.selectbox(
                "Źródło danych krypto",
                ["yahoo", "kraken", "coinbase", "binance", "bybit", "okx"],
                index=0,
                format_func=lambda value: {
                    "yahoo": "Yahoo Finance — stabilne na Streamlit Cloud",
                    "kraken": "Kraken przez CCXT",
                    "coinbase": "Coinbase przez CCXT",
                    "binance": "Binance przez CCXT — może być blokowane na hostingu",
                    "bybit": "Bybit przez CCXT",
                    "okx": "OKX przez CCXT",
                }[value],
            )
            st.caption(
                "Domyślnie używaj Yahoo Finance. Wpisy BTC/USDT, ETH/USDT i SOL/USDT "
                "są automatycznie zamieniane na BTC-USD, ETH-USD i SOL-USD."
            )

        timeframe = st.selectbox("Interwał", ["15m", "1h", "4h", "1d", "1wk"], index=3)
        limit = st.slider("Liczba świec", min_value=100, max_value=5000, value=2500, step=50)

        st.subheader("Czytelność wykresu")
        chart_zone_mode = st.radio(
            "Tryb stref na wykresie",
            [
                "Czytelny — 1 główna + 1 alternatywna",
                "Diagnostyczny — do 5 stref i konflikty",
            ],
            index=0,
        )
        show_swings = st.checkbox("Pokaż linię swingów", value=True)
        show_pivot_labels = st.checkbox("Pokaż etykiety H/L przy pivotach", value=False)
        show_zone_labels = st.checkbox("Pokaż etykiety stref", value=True)

        if chart_zone_mode.startswith("Diagnostyczny"):
            max_zones_on_chart = st.slider(
                "Liczba stref na wykresie w trybie diagnostycznym",
                min_value=1,
                max_value=DIAGNOSTIC_CHART_MAX_ZONES,
                value=DIAGNOSTIC_CHART_MAX_ZONES,
                step=1,
            )
        else:
            max_zones_on_chart = READABLE_CHART_MAX_ZONES
            st.caption("Tryb czytelny pokazuje wyłącznie główną strefę decyzyjną oraz — jeśli istnieje — jedną głębszą alternatywę.")

        st.subheader("Parametry struktury")
        pivot_left = st.slider("Pivot — świece z lewej", min_value=2, max_value=25, value=3)
        pivot_right = st.slider("Pivot — świece z prawej", min_value=2, max_value=25, value=3)
        min_move_pct = st.slider("Minimalny ruch swingowy (%)", min_value=0.1, max_value=20.0, value=1.0, step=0.1)

        st.subheader("Parametry trendu")
        trend_points = st.slider("Trend — ile ostatnich szczytów/dołków sprawdzać", min_value=3, max_value=8, value=4)
        min_trend_score = st.slider("Trend — minimalna zgodność kierunku", min_value=0.50, max_value=1.00, value=0.67, step=0.01)

        analyze_button = st.button("Analizuj")

    current_analysis_params = _analysis_params_signature(
        source,
        ticker,
        exchange_id,
        timeframe,
        limit,
        pivot_left,
        pivot_right,
        min_move_pct,
        trend_points,
        min_trend_score,
    )

    if "analysis_payload" not in st.session_state:
        st.session_state["analysis_payload"] = None
    if "analysis_params" not in st.session_state:
        st.session_state["analysis_params"] = None

    if analyze_button:
        try:
            with st.spinner("Analizuję wykres i buduję ranking stref..."):
                st.session_state["analysis_payload"] = _run_full_analysis(
                    source,
                    ticker,
                    exchange_id,
                    timeframe,
                    limit,
                    pivot_left,
                    pivot_right,
                    min_move_pct,
                    trend_points,
                    min_trend_score,
                )
                st.session_state["analysis_params"] = current_analysis_params
        except Exception as error:
            st.error(f"Nie udało się wykonać analizy: {error}")
            st.stop()

    if st.session_state["analysis_payload"] is None:
        st.info("Wybierz ticker i kliknij **Analizuj**.")
        return

    if st.session_state["analysis_params"] != current_analysis_params:
        st.warning(
            "Zmieniłeś parametry analizy, ale poniżej nadal pokazuję ostatni policzony wynik. "
            "Kliknij **Analizuj**, aby przeliczyć wykres dla nowych ustawień."
        )

    analysis_payload = st.session_state["analysis_payload"]
    df = analysis_payload["df"]
    pivots = analysis_payload["pivots"]
    swings = analysis_payload["swings"]
    trend_scores = analysis_payload["trend_scores"]
    trend = analysis_payload["trend"]
    ovb_result = analysis_payload["ovb_result"]
    bos_result = analysis_payload["bos_result"]
    opposite_structure = analysis_payload["opposite_structure"]
    trend_change_summary = analysis_payload["trend_change_summary"]
    candle_patterns = analysis_payload["candle_patterns"]
    rsi_signal = analysis_payload["rsi_signal"]
    rsi_divergence = analysis_payload["rsi_divergence"]
    elliott = analysis_payload["elliott"]
    zones = analysis_payload["zones"]
    zones_df = analysis_payload["zones_df"]
    top_zones_df = analysis_payload["top_zones_df"]
    active_zones_df = analysis_payload["active_zones_df"]
    strategic_zones_df = analysis_payload["strategic_zones_df"]

    if len(df) < 80:
        st.warning("Pobrano mało świec. Zwiększ liczbę świec albo wybierz wyższy interwał.")

    # =========================
    # PODSUMOWANIE
    # =========================
    st.subheader("1. Podsumowanie rynku")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Symbol", ticker)

    with col2:
        st.metric("Interwał", timeframe)

    with col3:
        st.metric("Trend", trend)

    with col4:
        st.metric("Ostatnia cena", f"{df['close'].iloc[-1]:.4f}")

    with col5:
        st.metric("RSI", f"{df['rsi'].iloc[-1]:.1f}")

    st.write("**Komentarz do trendu:**", get_trend_comment(trend, trend_scores, min_trend_score))
    st.write("**RSI:**", rsi_signal["status"])
    st.write("**Formacje świecowe:**", candle_patterns["summary"])
    st.write("**Dywergencja RSI:**", rsi_divergence["status"])

    if trend_scores.get("available"):
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Wynik wzrostowy", f"{trend_scores['up_score'] * 100:.0f}%")
        with col2:
            st.metric("Wynik spadkowy", f"{trend_scores['down_score'] * 100:.0f}%")

    # =========================
    # OVB / BOS / 3X ZMIANA
    # =========================
    st.subheader("2. OVB, BOS i 3x zmiana trendu")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("3x zmiana", f"{trend_change_summary['score']} / 3")

    with col2:
        st.metric("OVB", "TAK" if trend_change_summary["ovb_confirmed"] else "NIE")

    with col3:
        st.metric("BOS", "TAK" if trend_change_summary["bos_confirmed"] else "NIE")

    with col4:
        st.metric("Nowa struktura", "TAK" if trend_change_summary["new_structure_confirmed"] else "NIE")

    st.write("**Wniosek:**", trend_change_summary["status"])

    if ovb_result.get("available"):
        st.write("**OVB:**", ovb_result["status"])
        st.write(
            f"Największa korekta: **{ovb_result['max_correction']['size']:.4f}**, "
            f"poziom OVB: **{ovb_result['ovb_level']:.4f}**."
        )
    else:
        st.warning(ovb_result.get("reason", "Nie udało się policzyć OVB."))

    if bos_result.get("available"):
        st.write("**BOS:**", bos_result["status"])
        st.write(f"Podstawa impulsu BOS: **{bos_result['base_price']:.4f}**.")
    else:
        st.warning(bos_result.get("reason", "Nie udało się policzyć BOS."))

    st.write("**Nowa struktura:**", opposite_structure.get("status"))

    # =========================
    # ELLIOTT
    # =========================
    st.subheader("3. Scenariusz Elliotta — uproszczony filtr")

    if elliott.get("available"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Scenariusz", elliott.get("scenario", "brak"))
        with col2:
            st.metric("Score", f"{elliott.get('score', 0)} / 5")
        with col3:
            st.metric("F3/F1", f"{elliott.get('extension_f3', 0):.2f}")
        st.write("**Status:**", elliott.get("status"))
    else:
        st.info(elliott.get("status"))

    # =========================
    # STREFY
    # =========================
    st.subheader("4. Ranking stref — jakość najpierw")

    if top_zones_df.empty:
        st.warning(f"Nie wykryto stref, które jednocześnie mają dobrą jakość i R:R co najmniej ok. 1:{MIN_ACCEPTABLE_RR:.1f}.")
    else:
        st.caption(
            f"Pokazuję maksymalnie {TOP_ZONES_TO_DISPLAY} najlepszych, niepowtarzających się stref, "
            f"które spełniają warunek R:R około 1:{TARGET_RR:.0f} (tolerancja od {MIN_ACCEPTABLE_RR:.1f}). "
            "Pełna lista, także strefy odrzucone przez R:R, zostaje w sekcji szczegółów technicznych."
        )
        compact_top_table = _compact_zone_table(top_zones_df)
        st.dataframe(compact_top_table, use_container_width=True, hide_index=True)
        st.caption("Tabela główna pokazuje tylko dane decyzyjne: gdzie jest strefa, jaki jest plan SL/TP, R:R i czy strefa jest świeża czy zużyta. Metryki techniczne modelu zostawiłem w szczegółach na dole.")

        best = top_zones_df.iloc[0]
        st.success(
            f"Najważniejsza strefa z rankingu: **{best['zone_code']} — {best['direction'].upper()}** "
            f"w zakresie **{best['low']:.4f} - {best['high']:.4f}**. "
            f"Plan techniczny: wejście **{best['entry']:.4f}**, bezpieczny SL **{best['safe_sl']:.4f}**, "
            f"TP **{best['tp']:.4f}**, R:R **{best['rr']:.2f}**. "
            f"Status: **{best['freshness']}**. Decyzja: **{best['decision']}**."
        )

        with st.expander("Szczegóły najlepszej strefy"):
            st.write("**Kod na wykresie:**", best["zone_code"])
            st.write("**Opis:**", best["note"])
            st.write("**Powody punktacji:**", best["reasons"])
            if bool(best.get("conflict", False)):
                st.warning(best.get("conflict_note", "Strefa nakłada się na przeciwną strefę."))

    if not active_zones_df.empty:
        with st.expander("Strefy aktywne teraz — cena w środku albo bardzo blisko", expanded=False):
            st.dataframe(_compact_zone_table(active_zones_df), use_container_width=True, hide_index=True)

    if not strategic_zones_df.empty:
        with st.expander("Mocne strefy strategiczne poza bieżącą ceną", expanded=False):
            st.dataframe(_compact_zone_table(strategic_zones_df), use_container_width=True, hide_index=True)

    # =========================
    # WYKRES
    # =========================
    st.subheader("5. Wykres")
    st.info("Tryb odczytu kursora jest teraz tutaj — bez przewijania panelu bocznego.")

    chart_controls_left, chart_controls_right = st.columns([2, 1])
    with chart_controls_left:
        hover_preview_label = st.radio(
            "Tryb odczytu na wykresie",
            ["Dane świecy (OHLC)", "Cena pod kursorem"],
            index=0,
            horizontal=True,
            key="chart_hover_mode_main",
        )
    with chart_controls_right:
        show_crosshair = st.checkbox(
            "Pokaż krzyż kursora",
            value=True,
            key="chart_crosshair_main",
        )

    hover_readout_mode = "cursor_price" if hover_preview_label == "Cena pod kursorem" else "candle"
    st.caption(
        "Dane świecy (OHLC) pokazują wartości świecy. Cena pod kursorem pokazuje przybliżony poziom osi Y w miejscu kursora."
    )

    if chart_zone_mode.startswith("Czytelny"):
        chart_zones_df = select_chart_zones(top_zones_df, top_n=READABLE_CHART_MAX_ZONES)
        show_conflict_overlays = False
        st.caption(
            "Widok czytelny: rysuję strefę główną z rankingu także wtedy, gdy jest strategiczna i daleko od ceny. "
            "Drugą strefę dokładam tylko wtedy, gdy daje wyraźnie oddzielny scenariusz. Reszta zostaje w tabelach."
        )
    else:
        chart_zones_df = top_zones_df.head(max_zones_on_chart).copy()
        show_conflict_overlays = True
        st.caption(
            "Widok diagnostyczny: pokazuję więcej stref oraz konflikty BUY/SELL. Używaj go do weryfikacji, nie jako domyślnego widoku."
        )

    st.caption(
        "Legenda: zielony prostokąt = BUY, czerwony = SELL. W widoku czytelnym etykieta GŁÓWNA wskazuje główną strefę decyzyjną, "
        "a ALTERNATYWNA — drugi, wyraźnie oddzielony scenariusz. W trybie diagnostycznym żółty pas oznacza konflikt BUY/SELL. "
        "Kody B1/B2/S1/S2 nadal odpowiadają tabeli rankingu."
    )

    chart_title = f"{ticker} — {timeframe} — struktura, OVB, BOS i strefy"
    fig = make_chart(
        df,
        swings,
        ovb_result,
        bos_result,
        chart_zones_df,
        chart_title,
        show_swings=show_swings,
        show_pivot_labels=show_pivot_labels,
        show_zone_labels=show_zone_labels,
        max_zones_on_chart=max_zones_on_chart,
        show_crosshair=show_crosshair,
        hover_readout_mode=hover_readout_mode,
        show_conflict_overlays=show_conflict_overlays,
    )
    st.plotly_chart(fig, use_container_width=True)

    # =========================
    # SZCZEGÓŁY TECHNICZNE
    # =========================
    with st.expander("Szczegóły: ocena trendu"):
        st.json(trend_scores, expanded=True)

    with st.expander("Szczegóły: OVB"):
        st.json(ovb_result, expanded=False)

    with st.expander("Szczegóły: BOS"):
        st.json(bos_result, expanded=False)

    with st.expander("Szczegóły: wszystkie strefy"):
        if zones_df.empty:
            st.write("Brak stref.")
        else:
            st.dataframe(zones_df, use_container_width=True)

    with st.expander("Wykryte swingi"):
        st.dataframe(swings.tail(80), use_container_width=True)

    with st.expander("Ostatnie świece OHLCV + RSI + ATR"):
        st.dataframe(df.tail(80), use_container_width=True)


if __name__ == "__main__":
    main()
