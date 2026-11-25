"""Command-line options for the game window."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from flip_seven_bots.bots import ExpectedValueBot, ThresholdBot
from flip_seven_bots.bots.registry import kinds
from flip_seven_bots.bots.specs import number_duplicates, parse_named_bot

from .table import Seat

MAX_PLAYERS = 6


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
    """Create the default human, threshold-bot, and expected-value-bot seats."""
    return [
        Seat('Human'),
        Seat('Threshold 30', ThresholdBot(30)),
        Seat('Expected value', ExpectedValueBot()),
    ]


def _bot_seat(spec: str) -> Seat:
    try:
        name, bot = parse_named_bot(spec)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None
    return Seat(name, bot)


def _human_seat(name: str) -> Seat:
    if not name.strip():
        raise argparse.ArgumentTypeError('a human player needs a name')
    return Seat(name.strip())


def _number_duplicates(seats: list[Seat]) -> list[Seat]:
    names = number_duplicates([seat.name for seat in seats])
    return [Seat(name, seat.bot) for name, seat in zip(names, seats)]


def parse_options(argv: Sequence[str] | None = None) -> Options:
    """Parse launch options; ``None`` reads the process command line.

    Seats follow option order, defaulting to a human and two bots. No
    arguments opens setup; any supplied options launch directly. ``--brutal``
    implies With a Vengeance.
    """
    parser = argparse.ArgumentParser(
        prog='flip7 play',
        description=(
            'Play Flip 7 at one screen. Seats are filled in the order the options '
            'are given; players take turns at the same keyboard and mouse. With no '
            'options, configure the game on the setup screen.'
        ),
    )
    parser.add_argument(
        '--human',
        dest='seats',
        action='append',
        type=_human_seat,
        metavar='NAME',
        help='add a human player',
    )
    parser.add_argument(
        '--bot',
        dest='seats',
        action='append',
        type=_bot_seat,
        metavar='[NAME=]KIND',
        help=f'add a bot: {", ".join(kind.key for kind in kinds())}',
    )
    parser.add_argument(
        '--seed',
        type=int,
        help='seed for the decks, so games can be repeated (bots stay random)',
    )
    parser.add_argument(
        '--bug-dir',
        type=Path,
        default=Path('bug_reports'),
        metavar='PATH',
        help='folder for bug and crash reports (default: %(default)s)',
    )
    parser.add_argument(
        '--vengeance', action='store_true', help='play With a Vengeance'
    )
    parser.add_argument(
        '--brutal', action='store_true', help='play With a Vengeance in Brutal Mode'
    )
    setup = parser.add_mutually_exclusive_group()
    setup.add_argument('--setup', action='store_true', help='show the setup screen')
    setup.add_argument('--no-setup', action='store_true', help='start immediately')
    args = parser.parse_args(argv)
    seats: list[Seat] | None = args.seats
    if not seats:
        seats = default_seats()
    elif len(seats) > MAX_PLAYERS:
        parser.error(f'at most {MAX_PLAYERS} players fit on the screen')
    show_setup = args.setup or (
        not args.no_setup and not (sys.argv[1:] if argv is None else argv)
    )
    return Options(
        _number_duplicates(seats),
        args.seed,
        args.bug_dir,
        args.vengeance or args.brutal,
        args.brutal,
        show_setup,
    )
