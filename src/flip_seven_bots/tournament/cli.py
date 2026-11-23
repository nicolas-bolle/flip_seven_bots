"""Options and terminal output for ``flip7 tournament``.

Unlike ``flip7 play``, which only has a window, a tournament runs in the
terminal or the window with the same options, so they are parsed here once and
the window receives the resulting :class:`TournamentOptions`.
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from flip_seven_bots.bots.registry import kinds
from flip_seven_bots.bots.specs import number_duplicates, parse_named_bot

from .config import DEFAULT_K_HALF_LIFE
from .config import TournamentOptions as TournamentOptions  # noqa: PLC0414
from .core import MAX_PLAYERS, max_table_size
from .storage import save_results as save_results  # noqa: PLC0414

if TYPE_CHECKING:
    from flip_seven_bots.bots.base import Bot

DEFAULT_BOTS = ("random", "threshold:30", "expected")
DEFAULT_GAMES = 100


def named_bot(spec: str) -> tuple[str, Bot]:
    """Parse ``[NAME=]KIND``; without a name, the kind's display name is used."""
    try:
        return parse_named_bot(spec)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


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


@dataclass(frozen=True)
class TournamentLaunch:
    """Parsed ``flip7 tournament`` command: settings plus where to show them."""

    options: TournamentOptions
    gui: bool = False
    show_setup: bool = False


def parse_options(argv: Sequence[str] | None = None) -> TournamentOptions:
    """Parse tournament settings; ``None`` reads the process command line.

    Bots keep the order given and duplicate names are numbered. Without
    ``--bot`` options, the default lineup is used. ``--brutal`` implies With A
    Vengeance. Window flags are rejected; use :func:`parse_launch` for those.
    """
    parser = _parser(launch=False)
    return _options(parser, parser.parse_args(argv))


def parse_launch(argv: Sequence[str] | None = None) -> TournamentLaunch:
    """Parse the full ``flip7 tournament`` command, including window flags.

    With ``--gui`` and no other options, the setup screen is shown; any other
    options start the tournament immediately unless ``--setup`` is given.
    """
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = _parser(launch=True)
    args = parser.parse_args(args_list)
    if (args.setup or args.no_setup) and not args.gui:
        parser.error("--setup and --no-setup require --gui")
    options = _options(parser, args)
    settings_given = any(arg != "--gui" for arg in args_list)
    return TournamentLaunch(
        options,
        gui=args.gui,
        show_setup=args.gui
        and (args.setup or (not args.no_setup and not settings_given)),
    )


def _parser(*, launch: bool) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flip7 tournament",
        description=(
            "Play a tournament between bots and print their Elo ratings, or watch "
            "it with --gui. With --gui and no other options, configure it on the "
            "setup screen."
        ),
    )
    if launch:
        parser.add_argument(
            "--gui", action="store_true", help="show the tournament window"
        )
        setup = parser.add_mutually_exclusive_group()
        setup.add_argument(
            "--setup", action="store_true", help="show setup (with --gui)"
        )
        setup.add_argument(
            "--no-setup", action="store_true", help="skip setup (with --gui)"
        )
    parser.add_argument(
        "--bot",
        dest="bots",
        action="append",
        type=named_bot,
        metavar="[NAME=]KIND",
        help=(
            f"add a bot: {', '.join(kind.kind for kind in kinds())} (default lineup: "
            f"{', '.join(DEFAULT_BOTS)})"
        ),
    )
    parser.add_argument(
        "--games",
        type=_positive_int,
        default=DEFAULT_GAMES,
        metavar="N",
        help="number of games to play (default: %(default)s)",
    )
    parser.add_argument(
        "--players-per-game",
        type=_positive_int,
        metavar="N",
        help=(
            "bots seated in each game, chosen at random "
            f"(default: all, up to {MAX_PLAYERS})"
        ),
    )
    parser.add_argument("--seed", type=int, help="seed for seating, decks, and bots")
    parser.add_argument(
        "--jobs",
        type=_positive_int,
        default=1,
        metavar="N",
        help="number of parallel game workers (default: %(default)s)",
    )
    parser.add_argument(
        "--vengeance", action="store_true", help="play With a Vengeance"
    )
    parser.add_argument(
        "--brutal", action="store_true", help="play With a Vengeance in Brutal Mode"
    )
    parser.add_argument(
        "--k-factor",
        type=_positive_float,
        default=32.0,
        metavar="K",
        help="starting Elo K-factor (default: %(default)s)",
    )
    k_schedule = parser.add_mutually_exclusive_group()
    k_schedule.add_argument(
        "--k-half-life",
        type=_positive_float,
        default=DEFAULT_K_HALF_LIFE,
        metavar="N",
        help="games after which a bot's Elo K-factor halves (default: %(default)s)",
    )
    k_schedule.add_argument(
        "--constant-k", action="store_true", help="keep the Elo K-factor constant"
    )
    parser.add_argument(
        "--initial-rating",
        type=float,
        default=1500.0,
        metavar="R",
        help="starting Elo rating (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        metavar="DIR",
        help="save games.csv and summary.csv in this folder",
    )
    parser.add_argument("--quiet", action="store_true", help="hide the progress bar")
    parser.add_argument(
        "--plots", action="store_true", help="save HTML plots (requires --output)"
    )
    return parser


def _options(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> TournamentOptions:
    if args.plots and args.output is None:
        parser.error("--plots requires --output")

    named = args.bots or [named_bot(spec) for spec in DEFAULT_BOTS]
    if len(named) < 2:
        parser.error("a tournament needs at least two bots")
    names = number_duplicates([name for name, _ in named])
    bots = {name: bot for name, (_, bot) in zip(names, named)}
    largest = max_table_size(len(bots))
    if args.players_per_game is not None and not 2 <= args.players_per_game <= largest:
        parser.error(f"--players-per-game must be between 2 and {largest}")
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
        k_half_life=None if args.constant_k else args.k_half_life,
        jobs=args.jobs,
        quiet=args.quiet,
        plots=args.plots,
    )


def format_summary(summary: pd.DataFrame) -> str:
    """Render a tournament summary as an aligned text table, with intervals as ranges."""
    table = summary.drop(columns=["rating_low", "rating_high"])
    table.insert(
        list(table.columns).index("rating") + 1,
        "95% interval",
        [
            "-" if pd.isna(low) else f"{low:.0f}-{high:.0f}"
            for low, high in zip(summary["rating_low"], summary["rating_high"])
        ],
    )
    return table.to_string(
        formatters={
            "win_rate": "{:.0%}".format,
            "mean_place": "{:.2f}".format,
            "mean_score": "{:.1f}".format,
            "rating": "{:.0f}".format,
            "elo": "{:.0f}".format,
        },
        na_rep="-",
    )


def run(options: TournamentOptions) -> None:
    """Run a tournament with a progress bar, print the summary, and optionally save CSVs."""
    print(options.describe())
    result = options.run(progress=not options.quiet)
    print(format_summary(result.summary))
    if options.output is not None:
        games, summary = save_results(result, options.output, options)
        print(f"Saved {games} and {summary}")
