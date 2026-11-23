"""Rate bots against each other over a series of games."""

from collections import Counter
from collections.abc import Generator, Iterator, Mapping, Sequence
from concurrent.futures import Future, ProcessPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from random import Random
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from tqdm.auto import tqdm

from flip_seven_bots.bots.base import Bot
from flip_seven_bots.bots.registry import config_for
from flip_seven_bots.game import Rules
from flip_seven_bots.simulation import play_game

from . import plots
from .ratings import PairwiseResults, elo_update

if TYPE_CHECKING:
    from flip_seven_bots.bots.base import BotFactory


@dataclass(frozen=True)
class _GamePlan:
    game: int
    order: tuple[str, ...]
    deck_seed: int
    bot_seeds: tuple[int, ...]
    factories: tuple[BotFactory, ...]
    rules: Rules | None


def _play_plan(plan: _GamePlan) -> tuple[int, ...]:
    bots = [factory(seed) for factory, seed in zip(plan.factories, plan.bot_seeds)]
    final = play_game(bots, seed=plan.deck_seed, rules=plan.rules)
    return tuple(view.total_score for view in final.players)


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
    game), and ``elo_change``.
    """

    summary: pd.DataFrame
    """One row per player, indexed by name and sorted by ``rating``.

    Columns: ``games`` played, ``wins`` (shared wins count fully), ``win_rate``,
    ``mean_place``, ``mean_score``; ``rating``, the Bradley-Terry fit to all
    games on the Elo scale, with ``rating_low`` and ``rating_high`` bounding its
    confidence interval; and ``elo``, the final online Elo rating.
    Statistics are ``NaN`` for a player who never played.
    """

    def plot_ratings(self) -> go.Figure:
        """Plot each player's ``rating`` with its confidence interval, best first."""
        return plots.plot_ratings(self.summary)

    def plot_elo(self) -> go.Figure:
        """Plot the online Elo after each game, over each final ``rating`` and interval."""
        return plots.plot_elo(self.games, self.summary)

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
    bots: Mapping[str, Bot | BotFactory],
    *,
    games: int,
    players_per_game: int | None = None,
    rules: Rules | None = None,
    seed: int | None = None,
    k_factor: float = 32.0,
    k_half_life: float | None = 50.0,
    initial_rating: float = 1500.0,
    jobs: int = 1,
) -> Generator[GameRecord]:
    """Validate the settings, then return an iterator of games in scheduled order.

    With multiple workers, up to ``jobs`` games may be in flight. Close the
    iterator when stopping early to wait for workers and release resources.
    """
    names = list(bots)
    table_size = len(names) if players_per_game is None else players_per_game
    if games < 1:
        raise ValueError("games must be at least one")
    if not 2 <= table_size <= len(names):
        raise ValueError("players_per_game must be between two and the number of bots")
    if k_half_life is not None and k_half_life <= 0:
        raise ValueError("k_half_life must be positive")
    if jobs < 1:
        raise ValueError("jobs must be at least one")
    factories = {
        name: config_for(bot)
        if isinstance(bot, Bot) and not isinstance(bot, type)
        else bot
        for name, bot in bots.items()
    }

    def k(games_played: int) -> float:
        if k_half_life is None:
            return k_factor
        return k_factor * k_half_life / (k_half_life + games_played)

    def generate() -> Generator[GameRecord]:
        rng = Random(seed)
        elo = dict.fromkeys(names, float(initial_rating))
        played: Counter[str] = Counter()

        def plans() -> Iterator[_GamePlan]:
            for game in range(1, games + 1):
                order = tuple(rng.sample(names, table_size))
                yield _GamePlan(
                    game,
                    order,
                    rng.getrandbits(64),
                    tuple(rng.getrandbits(64) for _ in order),
                    tuple(factories[name] for name in order),
                    rules,
                )

        def results() -> Generator[tuple[_GamePlan, tuple[int, ...]]]:
            if jobs == 1:
                for plan in plans():
                    yield plan, _play_plan(plan)
                return
            with ProcessPoolExecutor(max_workers=jobs) as pool:
                pending: list[tuple[_GamePlan, Future[tuple[int, ...]]]] = []
                source = iter(plans())
                for _ in range(min(jobs, games)):
                    plan = next(source)
                    pending.append((plan, pool.submit(_play_plan, plan)))
                while pending:
                    plan, future = pending.pop(0)
                    scores = future.result()
                    yield plan, scores
                    next_plan = next(source, None)
                    if next_plan is not None:
                        pending.append((next_plan, pool.submit(_play_plan, next_plan)))

        with closing(results()) as outcomes:
            for plan, scores in outcomes:
                order = plan.order
                places = tuple(
                    1 + sum(other > score for other in scores) for score in scores
                )
                before = tuple(elo[name] for name in order)
                factors = [k(played[name]) for name in order]
                after = tuple(elo_update(before, places, k_factor=factors))
                elo.update(zip(order, after))
                played.update(order)
                yield GameRecord(plan.game, order, scores, places, before, after)

    return generate()


def run_tournament(
    bots: Mapping[str, Bot | BotFactory],
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
    jobs: int = 1,
) -> TournamentResult:
    """Play ``games`` games between named bots and rate them.

    Each game seats ``players_per_game`` bots (default: all of them), chosen
    and ordered at random. ``seed`` controls seating, decks, and bot seeds.
    Each game constructs fresh bots from factories accepting a seed. Registered
    bot instances are also accepted as configurations. Factories and rules
    must be picklable when ``jobs`` is greater than one.

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
        jobs=jobs,
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
