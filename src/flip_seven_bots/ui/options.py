"""Command-line options for the game window."""

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from flip_seven_bots.bots import ExpectedValueBot, RandomBot, ThresholdBot

from .table import Seat

MAX_PLAYERS = 6
BOT_KINDS = ("random", "threshold[:SCORE]", "expected")


@dataclass(frozen=True)
class Options:
    """Parsed launch settings, including whether to show interactive setup."""

    seats: list[Seat]
    seed: int | None
    bug_dir: Path
    vengeance: bool
    brutal: bool
    show_setup: bool


def default_seats() -> list[Seat]:
    """Create the default human, random-bot, and threshold-bot seats."""
    return [
        Seat("You"),
        Seat("Random bot", RandomBot()),
        Seat("Threshold bot", ThresholdBot(30)),
    ]


def _bot_seat(spec: str) -> Seat:
    kind, _, value = spec.partition(":")
    try:
        number = int(value) if value else None
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number") from None
    match kind, number:
        case "random", None:
            return Seat("Random bot", RandomBot())
        case "threshold", _:
            threshold = 30 if number is None else number
            if threshold < 0:
                raise argparse.ArgumentTypeError("threshold must not be negative")
            return Seat(f"Threshold {threshold}", ThresholdBot(threshold))
        case "expected", None:
            return Seat("Expected value bot", ExpectedValueBot())
    raise argparse.ArgumentTypeError(
        f"unknown bot {spec!r}; choose from {', '.join(BOT_KINDS)}"
    )


def _human_seat(name: str) -> Seat:
    if not name.strip():
        raise argparse.ArgumentTypeError("a human player needs a name")
    return Seat(name.strip())


def _number_duplicates(seats: list[Seat]) -> list[Seat]:
    counts = Counter(seat.name for seat in seats)
    seen: Counter[str] = Counter()
    numbered = []
    for seat in seats:
        if counts[seat.name] > 1:
            seen[seat.name] += 1
            seat = Seat(f"{seat.name} {seen[seat.name]}", seat.bot)
        numbered.append(seat)
    return numbered


def parse_options(argv: Sequence[str] | None = None) -> Options:
    """Parse launch options; ``None`` reads the process command line.

    Seats follow option order, defaulting to a human and two bots. No
    arguments opens setup; any supplied options launch directly. ``--brutal``
    implies With A Vengeance.
    """
    parser = argparse.ArgumentParser(
        prog="python -m flip_seven_bots.ui",
        description=(
            "Play Flip 7 at one screen. Seats are filled in the order the options "
            "are given; players take turns at the same keyboard and mouse. With no "
            "options, configure the game on the setup screen."
        ),
    )
    parser.add_argument(
        "--human",
        dest="seats",
        action="append",
        type=_human_seat,
        metavar="NAME",
        help="add a human player",
    )
    parser.add_argument(
        "--bot",
        dest="seats",
        action="append",
        type=_bot_seat,
        metavar="KIND",
        help=f"add a bot: {', '.join(BOT_KINDS)}",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="seed for the decks, so games can be repeated (bots stay random)",
    )
    parser.add_argument(
        "--bug-dir",
        type=Path,
        default=Path("bug_reports"),
        metavar="PATH",
        help="folder for bug and crash reports (default: %(default)s)",
    )
    parser.add_argument(
        "--vengeance", action="store_true", help="play With A Vengeance"
    )
    parser.add_argument(
        "--brutal", action="store_true", help="play With A Vengeance in Brutal Mode"
    )
    args = parser.parse_args(argv)
    seats: list[Seat] | None = args.seats
    if not seats:
        seats = default_seats()
    elif len(seats) > MAX_PLAYERS:
        parser.error(f"at most {MAX_PLAYERS} players fit on the screen")
    show_setup = not (sys.argv[1:] if argv is None else argv)
    return Options(
        _number_duplicates(seats), args.seed, args.bug_dir,
        args.vengeance or args.brutal, args.brutal, show_setup,
    )
