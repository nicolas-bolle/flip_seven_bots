"""Rate bots against each other over a series of games."""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from random import Random
from typing import TYPE_CHECKING

import pandas as pd
from tqdm.auto import tqdm

from flip_seven_bots.game import Rules
from flip_seven_bots.simulation import play_game

if TYPE_CHECKING:
    from flip_seven_bots.bots.base import Bot


@dataclass(frozen=True)
class GameRecord:
    """The outcome of one tournament game, in seat order (seat 0 deals)."""

    game: int
    """Game number, from one."""

    players: tuple[str, ...]
    """Names of the seated bots."""

    scores: tuple[int, ...]
    """Final total scores."""

    places: tuple[int, ...]
    """Finishing places; 1 is best and tied scores share a place."""

    ratings_before: tuple[float, ...]
    """Ratings going into the game."""

    ratings: tuple[float, ...]
    """Ratings after the game."""


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

    @classmethod
    def from_records(
        cls, records: Sequence[GameRecord], players: Sequence[str], *, initial_rating: float
    ) -> TournamentResult:
        """Build the tables from game records; ``players`` lists every bot, played or not."""
        rows = [
            {
                "game": record.game,
                "seat": seat,
                "player": name,
                "score": record.scores[seat],
                "place": record.places[seat],
                "won": record.places[seat] == 1,
                "rating_before": record.ratings_before[seat],
                "rating": record.ratings[seat],
                "rating_change": record.ratings[seat] - record.ratings_before[seat],
            }
            for record in records
            for seat, name in enumerate(record.players)
        ]
        played = pd.DataFrame(rows, columns=[
            "game", "seat", "player", "score", "place", "won",
            "rating_before", "rating", "rating_change",
        ])
        ratings = dict.fromkeys(players, float(initial_rating))
        for record in records:
            ratings.update(zip(record.players, record.ratings))
        return cls(played, _summarize(played, ratings))


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


def play_tournament(
    bots: Mapping[str, Bot],
    *,
    games: int,
    players_per_game: int | None = None,
    rules: Rules | None = None,
    seed: int | None = None,
    k_factor: float = 32.0,
    initial_rating: float = 1500.0,
    max_decisions: int = 100_000,
) -> Iterator[GameRecord]:
    """Validate the settings, then return an iterator that plays one game per step.

    Takes the same settings as ``run_tournament``. Games are only played as the
    iterator is advanced, so a caller can show progress or stop early.
    """
    names = list(bots)
    table_size = len(names) if players_per_game is None else players_per_game
    if games < 1:
        raise ValueError("games must be at least one")
    if not 2 <= table_size <= len(names):
        raise ValueError("players_per_game must be between two and the number of bots")

    def generate() -> Iterator[GameRecord]:
        rng = Random(seed)
        ratings = dict.fromkeys(names, float(initial_rating))
        for game in range(1, games + 1):
            seated = rng.sample(names, table_size)
            final = play_game(
                [bots[name] for name in seated],
                seed=rng.getrandbits(64),
                rules=rules,
                max_decisions=max_decisions,
            )
            scores = tuple(view.total_score for view in final.players)
            places = tuple(1 + sum(other > score for other in scores) for score in scores)
            before = tuple(ratings[name] for name in seated)
            after = tuple(elo_update(before, places, k_factor=k_factor))
            ratings.update(zip(seated, after))
            yield GameRecord(game, tuple(seated), scores, places, before, after)

    return generate()


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
    progress: bool = True,
) -> TournamentResult:
    """Play ``games`` games between named bots and track pairwise Elo ratings.

    Each game seats ``players_per_game`` bots (default: all of them), chosen
    and ordered at random. ``seed`` controls seating and decks; bots remain
    responsible for their own randomness, and each bot object keeps its state
    across games. Ratings are updated after every game with ``elo_update``.
    ``progress`` shows a progress bar with the current leader's rating.
    """
    records = play_tournament(
        bots, games=games, players_per_game=players_per_game, rules=rules, seed=seed,
        k_factor=k_factor, initial_rating=initial_rating, max_decisions=max_decisions,
    )
    ratings = dict.fromkeys(bots, float(initial_rating))
    played = []
    bar = tqdm(records, total=games, desc="Tournament", unit="game", disable=not progress)
    for record in bar:
        played.append(record)
        ratings.update(zip(record.players, record.ratings))
        leader = max(ratings, key=ratings.__getitem__)
        bar.set_postfix(leader=leader, rating=round(ratings[leader]))
    return TournamentResult.from_records(played, list(bots), initial_rating=initial_rating)


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
