from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go


# =========================================================
# KURSOR / HOVER
# =========================================================

def _add_cursor_price_overlay(
    fig: go.Figure,
    df: pd.DataFrame,
    x_grid_points: int = 320,
    y_grid_points: int = 720,
) -> None:
    """
    Dodaje niewidoczną, hoverowalną siatkę do odczytu ceny pod kursorem.

    Plotly standardowo pokazuje wartość najbliższego punktu danych, np. OHLC świecy.
    Ta warstwa daje alternatywny tryb: po najechaniu pokazuje przybliżony poziom osi Y,
    czyli cenę pod kursorem, a nie cenę świecy.
    """
    if df.empty:
        return

    y_min = float(df["low"].min())
    y_max = float(df["high"].max())
    if y_max <= y_min:
        y_max = y_min + 1.0

    y_padding = max((y_max - y_min) * 0.05, 1e-9)
    y_grid = np.linspace(y_min - y_padding, y_max + y_padding, y_grid_points)

    x_min = pd.Timestamp(df.index.min())
    x_max = pd.Timestamp(df.index.max())
    if x_max <= x_min:
        x_max = x_min + pd.Timedelta(days=1)

    x_grid = pd.date_range(start=x_min, end=x_max, periods=x_grid_points)
    z_grid = np.zeros((len(y_grid), len(x_grid)), dtype=np.uint8)

    fig.add_trace(
        go.Heatmap(
            x=x_grid,
            y=y_grid,
            z=z_grid,
            showscale=False,
            opacity=0.001,
            zmin=0,
            zmax=1,
            colorscale=[
                [0.0, "rgba(0,0,0,0.001)"],
                [1.0, "rgba(0,0,0,0.001)"],
            ],
            name="Cena pod kursorem",
            hovertemplate=(
                "<b>Cena pod kursorem:</b> %{y:.4f}<br>"
                "<b>Czas:</b> %{x|%Y-%m-%d %H:%M}"
                "<extra></extra>"
            ),
        )
    )


# =========================================================
# STREFY
# =========================================================

def _quality_opacity(quality_score: float) -> float:
    """Ciemniejszy prostokąt = wyższa jakość strefy."""
    if quality_score >= 32:
        return 0.26
    if quality_score >= 26:
        return 0.21
    if quality_score >= 20:
        return 0.16
    return 0.10


def _zone_colors(direction: str, quality_score: float) -> tuple[str, str]:
    opacity = _quality_opacity(quality_score)
    if direction == "buy":
        return f"rgba(0, 170, 80, {opacity:.2f})", "rgba(0, 190, 95, 0.78)"
    return f"rgba(220, 60, 60, {opacity:.2f})", "rgba(230, 75, 75, 0.78)"


def _overlap_bounds(a: dict[str, Any], b: dict[str, Any]) -> tuple[float, float] | None:
    low = max(float(a["low"]), float(b["low"]))
    high = min(float(a["high"]), float(b["high"]))
    if high <= low:
        return None
    return low, high


def _add_conflict_overlays(
    fig: go.Figure,
    zones_to_plot: pd.DataFrame,
    x0: Any,
    x1: Any,
) -> None:
    """Rysuje żółte pasy tam, gdzie strefy BUY i SELL nakładają się na siebie."""
    if zones_to_plot.empty:
        return

    rows = [row.to_dict() for _, row in zones_to_plot.iterrows()]
    drawn: set[tuple[float, float]] = set()

    for i, first in enumerate(rows):
        for second in rows[i + 1 :]:
            if str(first.get("direction")) == str(second.get("direction")):
                continue

            bounds = _overlap_bounds(first, second)
            if bounds is None:
                continue

            low, high = bounds
            key = (round(low, 6), round(high, 6))
            if key in drawn:
                continue
            drawn.add(key)

            fig.add_shape(
                type="rect",
                xref="x",
                yref="y",
                x0=x0,
                x1=x1,
                y0=low,
                y1=high,
                fillcolor="rgba(255, 193, 7, 0.18)",
                line={"color": "rgba(255, 193, 7, 0.88)", "width": 1, "dash": "dash"},
                layer="below",
            )

            fig.add_annotation(
                x=x1,
                y=(low + high) / 2,
                xanchor="right",
                yanchor="middle",
                text="KONFLIKT",
                showarrow=False,
                font={"size": 9, "color": "rgba(255, 219, 88, 0.95)"},
                bgcolor="rgba(0, 0, 0, 0.35)",
            )


# =========================================================
# WYKRES
# =========================================================

def make_chart(
    df: pd.DataFrame,
    swings: pd.DataFrame,
    ovb_result: dict[str, Any],
    bos_result: dict[str, Any],
    zones_df: pd.DataFrame,
    title: str,
    show_swings: bool = True,
    show_pivot_labels: bool = False,
    show_zone_labels: bool = True,
    max_zones_on_chart: int = 8,
    show_crosshair: bool = True,
    hover_readout_mode: str = "candle",
) -> go.Figure:
    """
    Tworzy wykres świecowy z OVB, BOS i strefami.

    hover_readout_mode:
    - "candle"       -> klasyczny podgląd świecy OHLC / swingów / stref,
    - "cursor_price" -> podgląd przybliżonej ceny osi Y pod kursorem.
    """
    cursor_price_mode = hover_readout_mode == "cursor_price"
    standard_hover = not cursor_price_mode

    fig = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Cena",
            increasing_line_width=1,
            decreasing_line_width=1,
            hoverinfo="all" if standard_hover else "skip",
        )
    )

    if show_swings and not swings.empty:
        highs = swings[swings["type"] == "high"]
        lows = swings[swings["type"] == "low"]

        fig.add_trace(
            go.Scatter(
                x=swings["time"],
                y=swings["price"],
                mode="lines",
                name="Swingi",
                line={"width": 1.5},
                hovertemplate="Swing: %{y:.4f}<extra></extra>" if standard_hover else None,
                hoverinfo="all" if standard_hover else "skip",
            )
        )

        high_mode = "markers+text" if show_pivot_labels else "markers"
        low_mode = "markers+text" if show_pivot_labels else "markers"

        fig.add_trace(
            go.Scatter(
                x=highs["time"],
                y=highs["price"],
                mode=high_mode,
                text=["H"] * len(highs) if show_pivot_labels else None,
                textposition="top center",
                name="Szczyty",
                marker={"size": 5},
                hovertemplate="Szczyt: %{y:.4f}<extra></extra>" if standard_hover else None,
                hoverinfo="all" if standard_hover else "skip",
            )
        )

        fig.add_trace(
            go.Scatter(
                x=lows["time"],
                y=lows["price"],
                mode=low_mode,
                text=["L"] * len(lows) if show_pivot_labels else None,
                textposition="bottom center",
                name="Dołki",
                marker={"size": 5},
                hovertemplate="Dołek: %{y:.4f}<extra></extra>" if standard_hover else None,
                hoverinfo="all" if standard_hover else "skip",
            )
        )

    if ovb_result.get("available"):
        fig.add_hline(
            y=ovb_result["ovb_level"],
            line_dash="dash",
            line_width=1,
            annotation_text=f"OVB 1.414: {ovb_result['ovb_level']:.4f}",
            annotation_position="top left",
        )

    if bos_result.get("available"):
        fig.add_hline(
            y=bos_result["base_price"],
            line_dash="dot",
            line_width=1,
            annotation_text=f"BOS: {bos_result['base_price']:.4f}",
            annotation_position="bottom left",
        )

    # Rysujemy tylko najlepsze strefy wybrane przez ranking.
    if zones_df is not None and not zones_df.empty and max_zones_on_chart > 0:
        zones_to_plot = zones_df.head(max_zones_on_chart).copy()
        x0 = df.index[max(0, len(df) - min(len(df), 250))]
        x1 = df.index[-1]
        label_x = df.index[max(0, len(df) - 5)]

        label_groups: dict[str, dict[str, list[Any]]] = {
            "buy": {"y": [], "text": [], "customdata": []},
            "sell": {"y": [], "text": [], "customdata": []},
        }

        for position, (_, zone) in enumerate(zones_to_plot.iterrows(), start=1):
            direction = str(zone.get("direction", "")).lower()
            quality_score = float(zone.get("quality_score", zone.get("score", 0)))
            fill_color, line_color = _zone_colors(direction, quality_score)
            line_dash = "dash" if bool(zone.get("conflict", False)) else "solid"
            zone_code = str(zone.get("zone_code", f"Z{position}"))

            fig.add_shape(
                type="rect",
                xref="x",
                yref="y",
                x0=x0,
                x1=x1,
                y0=float(zone["low"]),
                y1=float(zone["high"]),
                fillcolor=fill_color,
                line={"color": line_color, "width": 1.2, "dash": line_dash},
                layer="below",
            )

            if show_zone_labels:
                midpoint = (float(zone["low"]) + float(zone["high"])) / 2
                direction_label = "BUY" if direction == "buy" else "SELL"
                conflict_marker = " ⚠" if bool(zone.get("conflict", False)) else ""
                label_groups[direction]["y"].append(midpoint)
                label_groups[direction]["text"].append(
                    f"{zone_code} {direction_label}{conflict_marker} | {float(zone['low']):.2f}-{float(zone['high']):.2f}"
                )
                label_groups[direction]["customdata"].append(
                    [
                        zone_code,
                        direction_label,
                        str(zone.get("source", "")),
                        str(zone.get("type", "")),
                        float(zone["low"]),
                        float(zone["high"]),
                        float(zone.get("quality_score", 0)),
                        float(zone.get("setup_score", 0)),
                        str(zone.get("freshness", "")),
                        str(zone.get("decision", "")),
                        bool(zone.get("conflict", False)),
                    ]
                )

        _add_conflict_overlays(fig, zones_to_plot, x0, x1)

        if show_zone_labels:
            for direction, color in [("buy", "rgba(140, 255, 185, 0.98)"), ("sell", "rgba(255, 170, 170, 0.98)")]:
                group = label_groups[direction]
                if not group["y"]:
                    continue
                fig.add_trace(
                    go.Scatter(
                        x=[label_x] * len(group["y"]),
                        y=group["y"],
                        mode="text",
                        text=group["text"],
                        textposition="middle right",
                        name="Etykiety stref",
                        showlegend=False,
                        textfont={"size": 10, "color": color},
                        customdata=group["customdata"],
                        hovertemplate=(
                            "<b>%{customdata[0]} — %{customdata[1]} — %{customdata[3]}</b><br>"
                            "Źródło: %{customdata[2]}<br>"
                            "Strefa: %{customdata[4]:.4f} – %{customdata[5]:.4f}<br>"
                            "Quality: %{customdata[6]:.0f} | Setup: %{customdata[7]:.0f}<br>"
                            "Świeżość: %{customdata[8]}<br>"
                            "Decyzja: %{customdata[9]}<br>"
                            "Konflikt: %{customdata[10]}"
                            "<extra></extra>"
                        ) if standard_hover else None,
                        hoverinfo="all" if standard_hover else "skip",
                    )
                )

    if cursor_price_mode:
        _add_cursor_price_overlay(fig, df)

    fig.update_layout(
        title=title,
        xaxis_title="Czas",
        yaxis_title="Cena",
        xaxis_rangeslider_visible=False,
        height=760,
        hovermode="closest" if cursor_price_mode else "x unified",
        hoverdistance=-1 if cursor_price_mode else 100,
        spikedistance=-1,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 40, "r": 100, "t": 70, "b": 40},
    )

    if show_crosshair:
        fig.update_xaxes(
            showspikes=True,
            spikesnap="cursor",
            spikemode="across+toaxis",
            spikedash="dot",
            spikethickness=1,
            spikecolor="rgba(220, 220, 220, 0.75)",
            showline=True,
            mirror=True,
        )
        fig.update_yaxes(
            showspikes=True,
            spikesnap="cursor",
            spikemode="across+toaxis",
            spikedash="dot",
            spikethickness=1,
            spikecolor="rgba(220, 220, 220, 0.75)",
            showline=True,
            mirror=True,
        )
    else:
        fig.update_xaxes(showspikes=False)
        fig.update_yaxes(showspikes=False)

    return fig
