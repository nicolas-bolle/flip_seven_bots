"""Command-line selection of the players at the table."""

import argparse
from collections import Counter
from collections.abc import Sequence

from flip_seven_bots.bots import FlipThreeMonteCarloBot, RandomBot, ThresholdBot

from .table import Seat

MAX_PLAYERS = 6
BOT_KINDS = ("random", "threshold[:SCORE]", "montecarlo[:SAMPLES]")


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


def parse_seats(argv: Sequence[str] | None = None) -> list[Seat]:
    """Seats in the order their options are given; defaults to you and two bots."""
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
    seats: list[Seat] | None = parser.parse_args(argv).seats
    if not seats:
        return default_seats()
    if len(seats) > MAX_PLAYERS:
        parser.error(f"at most {MAX_PLAYERS} players fit on the screen")
    return _number_duplicates(seats)
