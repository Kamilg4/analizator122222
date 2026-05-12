from typing import Any
import pandas as pd
import plotly.graph_objects as go


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
) -> go.Figure:
    """Tworzy czytelniejszy wykres świecowy z OVB, BOS i ograniczoną liczbą stref."""
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
            )
        )

    if ovb_result.get("available"):
        fig.add_hline(
            y=ovb_result["ovb_level"],
            line_dash="dash",
            line_width=1,
            annotation_text="OVB 1.414",
            annotation_position="top left",
        )

    if bos_result.get("available"):
        fig.add_hline(
            y=bos_result["base_price"],
            line_dash="dot",
            line_width=1,
            annotation_text="BOS",
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
                label_y_values.append((zone["low"] + zone["high"]) / 2)
                label_texts.append(
                    f"{zone['direction'].upper()} | {zone['source']} | {zone['score']}"
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
                )
            )

    fig.update_layout(
        title=title,
        xaxis_title="Czas",
        yaxis_title="Cena",
        xaxis_rangeslider_visible=False,
        height=760,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 40, "r": 40, "t": 70, "b": 40},
    )

    return fig
