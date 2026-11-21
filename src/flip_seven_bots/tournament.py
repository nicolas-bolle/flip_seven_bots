"""Rate bots against each other over a series of games."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from random import Random
from typing import TYPE_CHECKING

import pandas as pd

from .game import Rules
from .simulation import play_game

if TYPE_CHECKING:
    from .bots.base import Bot


@dataclass(frozen=True)
class TournamentResult:
    """Per-game records and an overall summary of a tournament."""

    games: pd.DataFrame
    """One row per player per game, in play order.

    Columns: ``game`` (numbered from one), ``seat`` (zero-based; seat 0 deals),
    ``player``, ``score`` (final total), ``place`` (1 is best; tied scores share
    a place), ``won``, ``rating_before``, ``rating`` (after the game) and
    ``rating_change``.
    """

    summary: pd.DataFrame
    """One row per player, indexed by name and sorted by final rating.

    Columns: ``games`` played, ``wins`` (shared wins count fully), ``win_rate``,
    ``mean_place``, ``mean_score`` and final ``rating``. Averages are ``NaN``
    for a player who never played.
    """


def elo_update(
    ratings: Sequence[float], places: Sequence[int], *, k_factor: float = 32.0
) -> list[float]:
    """Return new ratings after one game, treating it as every pairwise match.

    For each pair of players the better place wins and equal places draw. A
    player's change is ``k_factor / (n - 1)`` times the sum over opponents of
    actual minus expected result, so two players get standard Elo and the total
    rating is unchanged.
    """
    if len(ratings) != len(places):
        raise ValueError("ratings and places must have the same length")
    if len(ratings) < 2:
        raise ValueError("a rated game needs at least two players")
    deltas = [0.0] * len(ratings)
    for i, j in combinations(range(len(ratings)), 2):
        expected = 1 / (1 + 10 ** ((ratings[j] - ratings[i]) / 400))
        actual = 1.0 if places[i] < places[j] else 0.5 if places[i] == places[j] else 0.0
        deltas[i] += actual - expected
        deltas[j] -= actual - expected
    scale = k_factor / (len(ratings) - 1)
    return [rating + scale * delta for rating, delta in zip(ratings, deltas)]


def run_tournament(
    bots: Mapping[str, Bot],
    *,
    games: int,
    players_per_game: int | None = None,
    rules: Rules | None = None,
    seed: int | None = None,
    k_factor: float = 32.0,
    initial_rating: float = 1500.0,
    max_decisions: int = 100_000,
) -> TournamentResult:
    """Play ``games`` games between named bots and track pairwise Elo ratings.

    Each game seats ``players_per_game`` bots (default: all of them), chosen
    and ordered at random. ``seed`` controls seating and decks; bots remain
    responsible for their own randomness, and each bot object keeps its state
    across games. Ratings are updated after every game with ``elo_update``.
    """
    names = list(bots)
    table_size = len(names) if players_per_game is None else players_per_game
    if games < 1:
        raise ValueError("games must be at least one")
    if not 2 <= table_size <= len(names):
        raise ValueError("players_per_game must be between two and the number of bots")

    rng = Random(seed)
    ratings = dict.fromkeys(names, float(initial_rating))
    rows = []
    for game in range(1, games + 1):
        seated = rng.sample(names, table_size)
        final = play_game(
            [bots[name] for name in seated],
            seed=rng.getrandbits(64),
            rules=rules,
            max_decisions=max_decisions,
        )
        scores = [view.total_score for view in final.players]
        places = [1 + sum(other > score for other in scores) for score in scores]
        before = [ratings[name] for name in seated]
        after = elo_update(before, places, k_factor=k_factor)
        for seat, name in enumerate(seated):
            ratings[name] = after[seat]
            rows.append({
                "game": game,
                "seat": seat,
                "player": name,
                "score": scores[seat],
                "place": places[seat],
                "won": seat in final.winners,
                "rating_before": before[seat],
                "rating": after[seat],
                "rating_change": after[seat] - before[seat],
            })
    played = pd.DataFrame(rows)
    return TournamentResult(played, _summarize(played, ratings))


def _summarize(played: pd.DataFrame, ratings: Mapping[str, float]) -> pd.DataFrame:
    grouped = played.groupby("player")
    summary = pd.DataFrame({
        "games": grouped.size(),
        "wins": grouped["won"].sum(),
        "mean_place": grouped["place"].mean(),
        "mean_score": grouped["score"].mean(),
    }).reindex(list(ratings))
    summary["games"] = summary["games"].fillna(0).astype(int)
    summary["wins"] = summary["wins"].fillna(0).astype(int)
    summary["win_rate"] = summary["wins"] / summary["games"].where(summary["games"] > 0)
    summary["rating"] = pd.Series(ratings)
    summary.index.name = "player"
    columns = ["games", "wins", "win_rate", "mean_place", "mean_score", "rating"]
    return summary[columns].sort_values("rating", ascending=False)
