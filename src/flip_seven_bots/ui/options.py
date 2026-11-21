"""Command-line options for the game window."""

import argparse
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from flip_seven_bots.bots import FlipThreeMonteCarloBot, RandomBot, ThresholdBot

from .table import Seat

MAX_PLAYERS = 6
BOT_KINDS = ("random", "threshold[:SCORE]", "montecarlo[:SAMPLES]")


@dataclass(frozen=True)
class Options:
    seats: list[Seat]
    seed: int | None
    bug_dir: Path


def default_seats() -> list[Seat]:
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
        case "montecarlo", _:
            samples = 50 if number is None else number
            if samples < 1:
                raise argparse.ArgumentTypeError("samples must be at least one")
            return Seat(
                "Monte Carlo bot",
                FlipThreeMonteCarloBot(ThresholdBot(25), samples=samples),
            )
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
    """Seats are in the order their options are given; default: you and two bots."""
    parser = argparse.ArgumentParser(
        prog="python -m flip_seven_bots.ui",
        description=(
            "Play Flip 7 at one screen. Seats are filled in the order the options "
            "are given; players take turns at the same keyboard and mouse. With no "
            "options, you play against a random bot and a threshold bot."
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
    args = parser.parse_args(argv)
    seats: list[Seat] | None = args.seats
    if not seats:
        seats = default_seats()
    elif len(seats) > MAX_PLAYERS:
        parser.error(f"at most {MAX_PLAYERS} players fit on the screen")
    return Options(_number_duplicates(seats), args.seed, args.bug_dir)
