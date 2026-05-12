from typing import Any
import numpy as np
import pandas as pd
import plotly.graph_objects as go


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

    # uint8 mocno ogranicza rozmiar macierzy w pamięci; w JSON i tak idzie jako liczby.
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

    # Rysujemy tylko najlepsze strefy, żeby wykres nie był zawalony prostokątami.
    if zones_df is not None and not zones_df.empty and max_zones_on_chart > 0:
        zones_to_plot = zones_df.head(max_zones_on_chart).copy()
        x0 = df.index[max(0, len(df) - min(len(df), 250))]
        x1 = df.index[-1]

        label_x = df.index[max(0, len(df) - 5)]
        label_y_values = []
        label_texts = []
        label_customdata = []

        for _, zone in zones_to_plot.iterrows():
            fill_color = "rgba(0, 170, 80, 0.10)" if zone["direction"] == "buy" else "rgba(220, 60, 60, 0.10)"
            line_color = "rgba(0, 170, 80, 0.55)" if zone["direction"] == "buy" else "rgba(220, 60, 60, 0.55)"

            fig.add_shape(
                type="rect",
                xref="x",
                yref="y",
                x0=x0,
                x1=x1,
                y0=zone["low"],
                y1=zone["high"],
                fillcolor=fill_color,
                line={"color": line_color, "width": 1},
                layer="below",
            )

            if show_zone_labels:
                midpoint = (zone["low"] + zone["high"]) / 2
                label_y_values.append(midpoint)
                label_texts.append(
                    f"{zone['direction'].upper()} | {zone['low']:.2f}-{zone['high']:.2f}"
                )
                label_customdata.append(
                    [
                        str(zone.get("direction", "")).upper(),
                        str(zone.get("source", "")),
                        str(zone.get("type", "")),
                        float(zone["low"]),
                        float(zone["high"]),
                        float(zone.get("score", 0)),
                    ]
                )

        if show_zone_labels and label_y_values:
            fig.add_trace(
                go.Scatter(
                    x=[label_x] * len(label_y_values),
                    y=label_y_values,
                    mode="text",
                    text=label_texts,
                    textposition="middle right",
                    name="Etykiety stref",
                    showlegend=False,
                    textfont={"size": 10},
                    customdata=label_customdata,
                    hovertemplate=(
                        "<b>%{customdata[0]} — %{customdata[2]}</b><br>"
                        "Źródło: %{customdata[1]}<br>"
                        "Strefa: %{customdata[3]:.4f} – %{customdata[4]:.4f}<br>"
                        "Score: %{customdata[5]:.0f}"
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
        margin={"l": 40, "r": 65, "t": 70, "b": 40},
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
