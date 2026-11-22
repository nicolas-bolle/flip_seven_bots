"""Rate bots against each other over a series of games."""

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from random import Random
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from flip_seven_bots.game import Rules
from flip_seven_bots.simulation import play_game

from .ratings import PairwiseResults, elo_update

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

    elo_before: tuple[float, ...]
    """Elo ratings going into the game."""

    elo: tuple[float, ...]
    """Elo ratings after the game."""


@dataclass(frozen=True)
class TournamentResult:
    """Per-game records and an overall summary of a tournament."""

    games: pd.DataFrame
    """One row per player per game, in play order.

    Columns: ``game`` (numbered from one), ``seat`` (zero-based;
    seat 0 deals), ``player``, ``score`` (final total), ``place`` (1 is best;
    tied scores share a place), ``won``, ``elo_before``, ``elo`` (after the
    game) and ``elo_change``.
    """

    summary: pd.DataFrame
    """One row per player, indexed by name and sorted by ``rating``.

    Columns: ``games`` played, ``wins`` (shared wins count fully), ``win_rate``,
    ``mean_place``, ``mean_score``; ``rating``, the Bradley-Terry fit to all
    games on the Elo scale, with ``rating_low`` and ``rating_high`` bounding its
    confidence interval; and ``elo``, the final online Elo rating.
    Statistics are ``NaN`` for a player who never played.
    """

    @classmethod
    def from_records(
        cls,
        records: Sequence[GameRecord],
        players: Sequence[str],
        *,
        initial_rating: float,
        confidence: float = 0.95,
    ) -> TournamentResult:
        """Build the tables from game records; ``players`` lists every bot, played or not.

        ``rating`` is centred so that the players who played average
        ``initial_rating``. Its ``confidence`` interval uses a cluster-robust
        standard error that treats each game as one independent unit; it is
        ``NaN`` with fewer than two games.
        """
        rows = [
            {
                "game": record.game,
                "seat": seat,
                "player": name,
                "score": record.scores[seat],
                "place": record.places[seat],
                "won": record.places[seat] == 1,
                "elo_before": record.elo_before[seat],
                "elo": record.elo[seat],
                "elo_change": record.elo[seat] - record.elo_before[seat],
            }
            for record in records
            for seat, name in enumerate(record.players)
        ]
        played = pd.DataFrame(
            rows,
            columns=[
                "game",
                "seat",
                "player",
                "score",
                "place",
                "won",
                "elo_before",
                "elo",
                "elo_change",
            ],
        )
        elo = dict.fromkeys(players, float(initial_rating))
        for record in records:
            elo.update(zip(record.players, record.elo))

        active = [name for name in players if name in set(played["player"])]
        results = PairwiseResults(active)
        for record in records:
            results.add(record.game, record.players, record.places)
        fitted = pd.DataFrame(
            np.column_stack(results.fit(confidence=confidence)) + initial_rating
            if active
            else np.empty((0, 3)),
            index=active,
            columns=["rating", "rating_low", "rating_high"],
        )
        return cls(played, _summarize(played, list(players), fitted, elo))


def play_tournament(
    bots: Mapping[str, Bot],
    *,
    games: int,
    players_per_game: int | None = None,
    rules: Rules | None = None,
    seed: int | None = None,
    k_factor: float = 32.0,
    k_half_life: float | None = 50.0,
    initial_rating: float = 1500.0,
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
    if k_half_life is not None and k_half_life <= 0:
        raise ValueError("k_half_life must be positive")

    def k(games_played: int) -> float:
        if k_half_life is None:
            return k_factor
        return k_factor * k_half_life / (k_half_life + games_played)

    def generate() -> Iterator[GameRecord]:
        rng = Random(seed)
        elo = dict.fromkeys(names, float(initial_rating))
        played: Counter[str] = Counter()
        for game in range(1, games + 1):
            order = rng.sample(names, table_size)
            final = play_game(
                [bots[name] for name in order],
                seed=rng.getrandbits(64),
                rules=rules,
            )
            scores = tuple(view.total_score for view in final.players)
            places = tuple(
                1 + sum(other > score for other in scores) for score in scores
            )
            before = tuple(elo[name] for name in order)
            factors = [k(played[name]) for name in order]
            after = tuple(elo_update(before, places, k_factor=factors))
            elo.update(zip(order, after))
            played.update(order)
            yield GameRecord(game, tuple(order), scores, places, before, after)

    return generate()


def run_tournament(
    bots: Mapping[str, Bot],
    *,
    games: int,
    players_per_game: int | None = None,
    rules: Rules | None = None,
    seed: int | None = None,
    k_factor: float = 32.0,
    k_half_life: float | None = 50.0,
    initial_rating: float = 1500.0,
    confidence: float = 0.95,
    progress: bool = True,
) -> TournamentResult:
    """Play ``games`` games between named bots and rate them.

    Each game seats ``players_per_game`` bots (default: all of them), chosen
    and ordered at random. ``seed`` controls seating and decks; bots remain
    responsible for their own randomness, and each bot object keeps its state
    across games.

    The summary's ``rating`` is fitted to all games at once (see
    ``TournamentResult``), with a ``confidence`` interval. An online Elo rating
    is also updated after every game with
    ``elo_update``: each player's K-factor is ``k_factor * h / (h + n)`` after
    ``n`` games, where ``h`` is ``k_half_life``, or a constant ``k_factor`` if
    ``k_half_life`` is ``None``. ``progress`` shows a progress bar.
    """
    records = play_tournament(
        bots,
        games=games,
        players_per_game=players_per_game,
        rules=rules,
        seed=seed,
        k_factor=k_factor,
        k_half_life=k_half_life,
        initial_rating=initial_rating,
    )
    elo = dict.fromkeys(bots, float(initial_rating))
    played = []
    bar = tqdm(
        records, total=games, desc="Tournament", unit="game", disable=not progress
    )
    for record in bar:
        played.append(record)
        elo.update(zip(record.players, record.elo))
        leader = max(elo, key=elo.__getitem__)
        bar.set_postfix(leader=leader, elo=round(elo[leader]))
    return TournamentResult.from_records(
        played,
        list(bots),
        initial_rating=initial_rating,
        confidence=confidence,
    )


def _summarize(
    played: pd.DataFrame,
    players: list[str],
    fitted: pd.DataFrame,
    elo: Mapping[str, float],
) -> pd.DataFrame:
    grouped = played.groupby("player")
    summary = pd.DataFrame(
        {
            "games": grouped.size(),
            "wins": grouped["won"].sum(),
            "mean_place": grouped["place"].mean(),
            "mean_score": grouped["score"].mean(),
        }
    ).reindex(players)
    summary["games"] = summary["games"].fillna(0).astype(int)
    summary["wins"] = summary["wins"].fillna(0).astype(int)
    summary["win_rate"] = summary["wins"] / summary["games"].where(summary["games"] > 0)
    summary = summary.join(fitted)
    summary["elo"] = pd.Series(elo)
    summary.index.name = "player"
    columns = [
        "games",
        "wins",
        "win_rate",
        "mean_place",
        "mean_score",
        "rating",
        "rating_low",
        "rating_high",
        "elo",
    ]
    return summary[columns].sort_values("rating", ascending=False, na_position="last")
