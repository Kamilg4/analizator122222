import streamlit as st
import pandas as pd

# Import konfiguracji
from modules.config import APP_VERSION, TOP_ZONES_TO_DISPLAY

# Importy modułów
from modules.data import fetch_ohlcv
from modules.indicators import add_indicators
from modules.pivots import detect_pivots, build_swings
from modules.trend import calculate_trend_scores, determine_trend, get_trend_comment
from modules.ovb_bos import calculate_ovb, calculate_bos, check_opposite_structure, build_trend_change_summary
from modules.patterns import detect_recent_candle_patterns, detect_rsi_divergence, get_rsi_signal
from modules.zones import build_all_zones
from modules.evaluation import evaluate_zones, select_top_zones
from modules.elliott import detect_elliott_scenario
from modules.chart import make_chart


def main() -> None:
    st.set_page_config(page_title="Analizator Tradingowy — FULL", layout="wide")

    st.title("Analizator Tradingowy — FULL PROTOTYPE")
    st.caption(f"Wersja kodu: {APP_VERSION}")
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
            st.caption("Przykłady: NKE, TTWO, AAPL, MSFT, ADS.DE, RHM.DE, 11B.WA")
        else:
            ticker = st.text_input("Para krypto", "BTC/USDT").upper().strip()
            exchange_id = st.selectbox("Giełda", ["binance", "bybit", "okx"], index=0)
            st.caption("Przykłady: BTC/USDT, ETH/USDT, SOL/USDT")

        timeframe = st.selectbox("Interwał", ["15m", "1h", "4h", "1d", "1wk"], index=3)
        limit = st.slider("Liczba świec", min_value=100, max_value=5000, value=2500, step=50)

        st.subheader("Czytelność wykresu")
        show_swings = st.checkbox("Pokaż linię swingów", value=True)
        show_pivot_labels = st.checkbox("Pokaż etykiety H/L przy pivotach", value=False)
        show_zone_labels = st.checkbox("Pokaż etykiety stref", value=True)
        show_crosshair = st.checkbox("Pokaż krzyż kursora", value=True)
        hover_preview_label = st.radio(
            "Podgląd po najechaniu kursorem",
            ["Dane świecy (OHLC)", "Cena pod kursorem"],
            index=0,
        )
        hover_readout_mode = "cursor_price" if hover_preview_label == "Cena pod kursorem" else "candle"
        max_zones_on_chart = st.slider(
            "Maksymalna liczba najlepszych stref na wykresie",
            min_value=0,
            max_value=TOP_ZONES_TO_DISPLAY,
            value=TOP_ZONES_TO_DISPLAY,
            step=1,
        )

        st.subheader("Parametry struktury")
        pivot_left = st.slider("Pivot — świece z lewej", min_value=2, max_value=25, value=3)
        pivot_right = st.slider("Pivot — świece z prawej", min_value=2, max_value=25, value=3)
        min_move_pct = st.slider("Minimalny ruch swingowy (%)", min_value=0.1, max_value=20.0, value=1.0, step=0.1)

        st.subheader("Parametry trendu")
        trend_points = st.slider("Trend — ile ostatnich szczytów/dołków sprawdzać", min_value=3, max_value=8, value=4)
        min_trend_score = st.slider("Trend — minimalna zgodność kierunku", min_value=0.50, max_value=1.00, value=0.67, step=0.01)

        analyze_button = st.button("Analizuj")

    if not analyze_button:
        st.info("Wybierz ticker i kliknij **Analizuj**.")
        return

    try:
        df = fetch_ohlcv(source, ticker, exchange_id, timeframe, limit)
    except Exception as error:
        st.error(f"Nie udało się pobrać danych: {error}")
        st.stop()

    if len(df) < 80:
        st.warning("Pobrano mało świec. Zwiększ liczbę świec albo wybierz wyższy interwał.")

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
    st.subheader("4. Ranking stref wejścia")

    if top_zones_df.empty:
        st.warning("Nie wykryto jakościowych stref wejścia.")
    else:
        st.caption(
            f"Pokazuję maksymalnie {TOP_ZONES_TO_DISPLAY} najlepszych, niepowtarzających się stref. "
            "Pełna lista zostaje w sekcji szczegółów technicznych."
        )
        display_columns = [
            "direction",
            "type",
            "source",
            "low",
            "high",
            "status",
            "distance_pct",
            "width_pct",
            "quality_score",
            "setup_score",
            "score",
            "decision",
            "entry",
            "safe_sl",
            "aggressive_sl",
            "tp",
            "rr",
        ]
        st.dataframe(top_zones_df[display_columns], use_container_width=True)

        best = top_zones_df.iloc[0]
        st.success(
            f"Najlepsza strefa według rankingu jakościowego: **{best['direction'].upper()} — {best['type']}** "
            f"w zakresie **{best['low']:.4f} - {best['high']:.4f}**, "
            f"quality **{best['quality_score']}**, setup **{best['setup_score']}**, "
            f"decyzja: **{best['decision']}**."
        )

        with st.expander("Szczegóły najlepszej strefy"):
            st.write("**Opis:**", best["note"])
            st.write("**Powody punktacji:**", best["reasons"])

    # =========================
    # WYKRES
    # =========================
    st.subheader("5. Wykres")
    chart_title = f"{ticker} — {timeframe} — struktura, OVB, BOS i strefy"
    fig = make_chart(
        df,
        swings,
        ovb_result,
        bos_result,
        top_zones_df,
        chart_title,
        show_swings=show_swings,
        show_pivot_labels=show_pivot_labels,
        show_zone_labels=show_zone_labels,
        max_zones_on_chart=max_zones_on_chart,
        show_crosshair=show_crosshair,
        hover_readout_mode=hover_readout_mode,
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
