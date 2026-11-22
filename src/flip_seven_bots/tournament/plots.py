"""Plotly charts of tournament results."""

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative


def _colors(players: list[str]) -> dict[str, str]:
    palette = qualitative.Plotly
    return {name: palette[index % len(palette)] for index, name in enumerate(players)}


def _rgba(color: str, alpha: float) -> str:
    red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {alpha})"


def plot_ratings(summary: pd.DataFrame) -> go.Figure:
    """Each player's rating with its confidence interval, best first."""
    rated = summary.dropna(subset=["rating"])
    colors = _colors(list(summary.index))
    figure = go.Figure()
    for name, row in rated.iterrows():
        figure.add_trace(
            go.Scatter(
                x=[name],
                y=[row["rating"]],
                mode="markers",
                name=name,
                marker={"color": colors[str(name)], "size": 12},
                error_y={
                    "type": "data",
                    "array": [row["rating_high"] - row["rating"]],
                    "arrayminus": [row["rating"] - row["rating_low"]],
                    "thickness": 2,
                    "width": 8,
                },
                customdata=[[row["rating_low"], row["rating_high"], row["games"]]],
                hovertemplate=(
                    "%{x}: %{y:.0f} (%{customdata[0]:.0f} to %{customdata[1]:.0f})"
                    "<br>%{customdata[2]} games<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        title="Rating with confidence interval",
        xaxis_title="Player",
        yaxis_title="Rating (Elo scale)",
        showlegend=False,
    )
    return figure


def plot_elo(games: pd.DataFrame, summary: pd.DataFrame) -> go.Figure:
    """Online Elo after each game, over each player's final rating and interval.

    Each player's rating is a dotted line inside a shaded band spanning its
    confidence interval, in the player's colour. Players are listed best first.
    """
    colors = _colors(list(summary.index))
    figure = go.Figure()
    start = games["game"].min() - 1 if len(games) else 0
    end = games["game"].max() if len(games) else 0
    for name in summary.index:
        played = games[games["player"] == name]
        if played.empty:
            continue
        rating = summary.loc[name]
        color = colors[name]
        if pd.notna(rating["rating_low"]):
            figure.add_trace(
                go.Scatter(
                    x=[start, end, end, start],
                    y=[rating["rating_low"]] * 2 + [rating["rating_high"]] * 2,
                    fill="toself",
                    fillcolor=_rgba(color, 0.15),
                    mode="lines",
                    line={"width": 0},
                    legendgroup=name,
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
        figure.add_trace(
            go.Scatter(
                x=[start, end],
                y=[rating["rating"]] * 2,
                mode="lines",
                line={"color": color, "dash": "dot", "width": 1},
                legendgroup=name,
                showlegend=False,
                hovertemplate=f"{name} rating: %{{y:.0f}}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[start, *played["game"]],
                y=[played["elo_before"].iloc[0], *played["elo"]],
                mode="lines",
                name=name,
                line={"color": color, "shape": "hv"},
                legendgroup=name,
                hovertemplate=f"{name}<br>game %{{x}}: %{{y:.0f}}<extra></extra>",
            )
        )
    figure.update_layout(
        title="Elo after each game (dotted: final rating; band: its interval)",
        xaxis_title="Game",
        yaxis_title="Elo",
        hovermode="closest",
    )
    return figure
