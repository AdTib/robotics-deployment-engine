"""Shared Plotly chart helpers. Pure presentation -- inputs are already-computed series."""

from __future__ import annotations

import plotly.graph_objects as go

from app.theme import ACCENT_AMBER, ACCENT_RUST, ACCENT_STEEL

_BG = "#1b2126"
_GRID = "#2c353c"
_TEXT = "#e6eaec"
_TEXT_MUTED = "#8b969e"
_FONT_MONO = "IBM Plex Mono, ui-monospace, monospace"
_FONT_BODY = "IBM Plex Sans, system-ui, sans-serif"

# Cycled across traces so multi-series charts stay inside the same palette
# as the rest of the app instead of falling back to Plotly's default colors.
_TRACE_COLORS = [ACCENT_STEEL, ACCENT_AMBER, ACCENT_RUST, "#5a9e6f", "#8b969e"]


def _apply_theme(fig: go.Figure, title: str, yaxis_title: str, xaxis_title: str = "Month") -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(family=_FONT_BODY, size=14, color=_TEXT)),
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font=dict(family=_FONT_MONO, size=12, color=_TEXT_MUTED),
        xaxis=dict(gridcolor=_GRID, zerolinecolor=_GRID, linecolor=_GRID),
        yaxis=dict(gridcolor=_GRID, zerolinecolor=_GRID, linecolor=_GRID),
        legend=dict(orientation="h", y=-0.2, font=dict(color=_TEXT_MUTED, size=11)),
        margin=dict(t=44, b=44),
    )
    return fig


def monthly_line_chart(months: list[int], series: dict[str, list[float]], title: str, yaxis_title: str) -> go.Figure:
    fig = go.Figure()
    for i, (name, values) in enumerate(series.items()):
        color = _TRACE_COLORS[i % len(_TRACE_COLORS)]
        fig.add_trace(go.Scatter(x=months, y=values, mode="lines+markers", name=name, line=dict(color=color, width=2), marker=dict(size=5, color=color)))
    return _apply_theme(fig, title, yaxis_title)


def stage_bar_chart(labels: list[str], values: list[float], title: str, yaxis_title: str) -> go.Figure:
    fig = go.Figure(data=[go.Bar(x=labels, y=values, marker_color=ACCENT_STEEL)])
    fig.update_layout(margin=dict(t=44, b=80))
    return _apply_theme(fig, title, yaxis_title, xaxis_title="")
