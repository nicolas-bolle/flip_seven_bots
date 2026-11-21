"""Command-line tournaments: ``python -m flip_seven_bots.tournament``.

The same options configure the tournament window, ``python -m flip_seven_bots.ui.tournament``.
"""

import argparse
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from flip_seven_bots.bots.specs import BOT_KINDS, number_duplicates, parse_bot
from flip_seven_bots.game import Rules, VengeanceRules

from .core import GameRecord, TournamentResult, play_tournament, run_tournament

if TYPE_CHECKING:
    from flip_seven_bots.bots.base import Bot

DEFAULT_BOTS = ("random", "threshold:30", "expected")
DEFAULT_GAMES = 100


@dataclass(frozen=True)
class TournamentOptions:
    """Validated tournament settings."""

    bots: dict[str, Bot]
    """Bots by unique display name."""

    games: int
    players_per_game: int | None
    """Bots seated per game, or ``None`` for all of them."""

    seed: int | None
    vengeance: bool
    brutal: bool
    k_factor: float
    initial_rating: float
    output: Path | None
    """Folder to save ``games.csv`` and ``summary.csv`` in, if any."""

    @property
    def rules(self) -> Rules | None:
        return VengeanceRules(brutal=self.brutal) if self.vengeance else None

    def start(self) -> Iterator[GameRecord]:
        """Validate and return an iterator that plays one game per step."""
        return play_tournament(self.bots, **self._settings())

    def run(self, *, progress: bool = True) -> TournamentResult:
        """Play the whole tournament, optionally showing a terminal progress bar."""
        return run_tournament(self.bots, **self._settings(), progress=progress)

    def describe(self) -> str:
        """A one-line description of the settings."""
        mode = "Flip 7"
        if self.vengeance:
            mode = "With A Vengeance (Brutal)" if self.brutal else "With A Vengeance"
        table = self.players_per_game or len(self.bots)
        return f"{len(self.bots)} bots, {self.games} games of {table} players, {mode}"

    def _settings(self) -> dict:
        return {
            "games": self.games,
            "players_per_game": self.players_per_game,
            "rules": self.rules,
            "seed": self.seed,
            "k_factor": self.k_factor,
            "initial_rating": self.initial_rating,
        }


def named_bot(spec: str) -> tuple[str, Bot]:
    """Parse ``[NAME=]KIND``; without a name, the kind's display name is used."""
    name, separator, kind = spec.rpartition("=")
    if separator and not name.strip():
        raise argparse.ArgumentTypeError("a bot name must not be blank")
    try:
        default_name, bot = parse_bot(kind)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None
    return (name.strip() if separator else default_name), bot


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least one")
    return number


def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def parse_options(
    argv: Sequence[str] | None = None,
    *,
    prog: str = "python -m flip_seven_bots.tournament",
    description: str = "Play a tournament between bots and print their Elo ratings.",
) -> TournamentOptions:
    """Parse tournament options; ``None`` reads the process command line.

    Bots keep the order given and duplicate names are numbered. Without
    ``--bot`` options, the default lineup is used. ``--brutal`` implies With A
    Vengeance.
    """
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument(
        "--bot",
        dest="bots",
        action="append",
        type=named_bot,
        metavar="[NAME=]KIND",
        help=(
            f"add a bot: {', '.join(BOT_KINDS)} (default lineup: "
            f"{', '.join(DEFAULT_BOTS)})"
        ),
    )
    parser.add_argument(
        "--games", type=_positive_int, default=DEFAULT_GAMES, metavar="N",
        help="number of games to play (default: %(default)s)",
    )
    parser.add_argument(
        "--players-per-game", type=_positive_int, metavar="N",
        help="bots seated in each game, chosen at random (default: all)",
    )
    parser.add_argument("--seed", type=int, help="seed for seating and decks")
    parser.add_argument("--vengeance", action="store_true", help="play With A Vengeance")
    parser.add_argument(
        "--brutal", action="store_true", help="play With A Vengeance in Brutal Mode"
    )
    parser.add_argument(
        "--k-factor", type=_positive_float, default=32.0, metavar="K",
        help="Elo K-factor (default: %(default)s)",
    )
    parser.add_argument(
        "--initial-rating", type=float, default=1500.0, metavar="R",
        help="starting Elo rating (default: %(default)s)",
    )
    parser.add_argument(
        "--output", type=Path, metavar="DIR",
        help="save games.csv and summary.csv in this folder",
    )
    args = parser.parse_args(argv)

    named = args.bots or [named_bot(spec) for spec in DEFAULT_BOTS]
    if len(named) < 2:
        parser.error("a tournament needs at least two bots")
    names = number_duplicates([name for name, _ in named])
    bots = {name: bot for name, (_, bot) in zip(names, named)}
    if args.players_per_game is not None and not 2 <= args.players_per_game <= len(bots):
        parser.error(f"--players-per-game must be between 2 and {len(bots)}")
    return TournamentOptions(
        bots=bots,
        games=args.games,
        players_per_game=args.players_per_game,
        seed=args.seed,
        vengeance=args.vengeance or args.brutal,
        brutal=args.brutal,
        k_factor=args.k_factor,
        initial_rating=args.initial_rating,
        output=args.output,
    )


def format_summary(summary: pd.DataFrame) -> str:
    """Render a tournament summary as an aligned text table."""
    return summary.to_string(formatters={
        "win_rate": "{:.0%}".format,
        "mean_place": "{:.2f}".format,
        "mean_score": "{:.1f}".format,
        "rating": "{:.0f}".format,
    })


def save_results(result: TournamentResult, directory: Path) -> tuple[Path, Path]:
    """Write ``games.csv`` and ``summary.csv`` to ``directory``, creating it if needed."""
    directory.mkdir(parents=True, exist_ok=True)
    games, summary = directory / "games.csv", directory / "summary.csv"
    result.games.to_csv(games, index=False)
    result.summary.to_csv(summary)
    return games, summary


def main(argv: Sequence[str] | None = None) -> None:
    """Run a tournament with a progress bar, print the summary and optionally save CSVs."""
    options = parse_options(argv)
    print(options.describe())
    result = options.run()
    print(format_summary(result.summary))
    if options.output is not None:
        games, summary = save_results(result, options.output)
        print(f"Saved {games} and {summary}")
