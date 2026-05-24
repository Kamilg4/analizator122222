from __future__ import annotations

"""
Wspólna funkcja analizy — używana przez app.py, scanner_app.py,
scanner_daemon.py i backtest_engine.py.

Wydzielona, żeby uniknąć duplikacji ~150 linii kodu.
"""

from typing import Any

import pandas as pd

from .data import fetch_ohlcv, get_mtf_timeframe
from .indicators import add_indicators
from .pivots import detect_pivots, build_swings
from .trend import analyze_trend_structure, get_change_reference_trend, finalize_trend_context
from .ovb_bos import calculate_ovb, calculate_bos, check_opposite_structure, build_trend_change_summary
from .patterns import detect_recent_candle_patterns, detect_rsi_divergence, get_rsi_signal
from .zones import build_all_zones
from .evaluation import evaluate_zones, select_top_zones, select_active_zones, select_strategic_zones
from .config import TOP_ZONES_TO_DISPLAY


def run_full_analysis(
    df: pd.DataFrame,
    *,
    df_mtf: pd.DataFrame | None = None,
    pivot_left: int = 3,
    pivot_right: int = 3,
    min_move_pct: float = 1.5,
    trend_points: int = 4,
    min_trend_score: float = 0.67,
    include_elliott: bool = False,
    top_zones_n: int | None = None,
) -> dict[str, Any]:
    """
    Pełna analiza techniczna instrumentu.

    Parametry
    ---------
    df : DataFrame z OHLCV + wskaźnikami (po add_indicators)
    df_mtf : opcjonalny DataFrame z wyższego timeframe'u
    include_elliott : czy liczyć Elliott Wave (niepotrzebne w skanerze)
    top_zones_n : ile top stref zwrócić (domyślnie TOP_ZONES_TO_DISPLAY)

    Zwraca
    ------
    dict ze wszystkimi artefaktami analizy
    """
    if top_zones_n is None:
        top_zones_n = TOP_ZONES_TO_DISPLAY

    pivots = detect_pivots(df, left=pivot_left, right=pivot_right)
    swings = build_swings(pivots, min_move_pct=min_move_pct)

    structural_trend_context = analyze_trend_structure(
        swings,
        local_points_to_check=trend_points,
        min_score=min_trend_score,
    )
    change_reference_trend = get_change_reference_trend(structural_trend_context)

    # OVB/BOS/3x zmiana trendu liczone względem trendu głównego
    ovb_result = calculate_ovb(swings, change_reference_trend, df.iloc[-1])
    bos_result = calculate_bos(swings, change_reference_trend, df.iloc[-1])
    opposite_structure = check_opposite_structure(swings, change_reference_trend)
    trend_change_summary = build_trend_change_summary(ovb_result, bos_result, opposite_structure)

    trend_context = finalize_trend_context(structural_trend_context, trend_change_summary)
    trend = trend_context["effective_trend"]
    trend_scores = trend_context["local_scores"]

    candle_patterns = detect_recent_candle_patterns(df)
    rsi_signal = get_rsi_signal(df)
    rsi_divergence = detect_rsi_divergence(df, swings)

    elliott = None
    if include_elliott:
        from .elliott import detect_elliott_scenario
        elliott = detect_elliott_scenario(swings, trend)

    zones = build_all_zones(df, swings, trend, df_mtf=df_mtf)
    zones_df = evaluate_zones(
        zones, df, swings, trend,
        candle_patterns, rsi_signal, rsi_divergence,
        trend_change_score=int(trend_context.get("trend_change_score", 0) or 0),
    )
    top_zones_df = select_top_zones(zones_df, top_n=top_zones_n)
    active_zones_df = select_active_zones(zones_df, top_n=3)
    strategic_zones_df = select_strategic_zones(zones_df, top_n=3)

    return {
        "df": df,
        "pivots": pivots,
        "swings": swings,
        "trend_scores": trend_scores,
        "trend_context": trend_context,
        "change_reference_trend": change_reference_trend,
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


def fetch_and_analyze(
    source: str,
    ticker: str,
    exchange_id: str,
    timeframe: str,
    limit: int,
    *,
    pivot_left: int = 3,
    pivot_right: int = 3,
    min_move_pct: float = 1.5,
    trend_points: int = 4,
    min_trend_score: float = 0.67,
    include_elliott: bool = False,
    top_zones_n: int | None = None,
) -> dict[str, Any]:
    """Pobiera dane i uruchamia pełną analizę — wygodny wrapper."""
    df = fetch_ohlcv(source, ticker, exchange_id, timeframe, limit)
    df = add_indicators(df)

    # MTF
    mtf_timeframe = get_mtf_timeframe(timeframe)
    df_mtf = None
    if mtf_timeframe:
        try:
            df_mtf = fetch_ohlcv(source, ticker, exchange_id, mtf_timeframe, limit=min(limit, 1000))
            df_mtf = add_indicators(df_mtf)
        except Exception:
            df_mtf = None

    return run_full_analysis(
        df,
        df_mtf=df_mtf,
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        min_move_pct=min_move_pct,
        trend_points=trend_points,
        min_trend_score=min_trend_score,
        include_elliott=include_elliott,
        top_zones_n=top_zones_n,
    )
