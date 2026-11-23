from pathlib import Path

import pytest

from flip_seven_bots.bots import ExpectedValueBot, RandomBot, ThresholdBot
from flip_seven_bots.ui.options import MAX_PLAYERS, parse_options


def test_no_options_gives_the_default_table() -> None:
    options = parse_options([])
    assert options.seed is None
    assert options.bug_dir == Path("bug_reports")
    seats = options.seats
    assert [seat.name for seat in seats] == ["Me", "Threshold 30", "Expected value"]
    assert [seat.bot is None for seat in seats] == [True, False, False]
    assert options.show_setup and not options.vengeance and not options.brutal


def test_seats_follow_option_order() -> None:
    seats = parse_options(
        [
            "--bot",
            "random",
            "--human",
            "Ann",
            "--bot",
            "threshold:20",
            "--human",
            "Ben",
            "--bot",
            "expected",
        ]
    ).seats
    assert [seat.name for seat in seats] == [
        "Random bot",
        "Ann",
        "Threshold 20",
        "Ben",
        "Expected value bot",
    ]
    assert isinstance(seats[0].bot, RandomBot)
    assert seats[1].bot is None
    assert isinstance(seats[2].bot, ThresholdBot) and seats[2].bot.threshold == 20
    assert isinstance(seats[4].bot, ExpectedValueBot)


def test_a_table_can_be_all_bots() -> None:
    seats = parse_options(["--bot", "random", "--bot", "threshold"]).seats
    assert all(seat.bot is not None for seat in seats)


def test_duplicate_names_are_numbered() -> None:
    seats = parse_options(["--human", "Ann", "--human", "Ann", "--bot", "random"]).seats
    assert [seat.name for seat in seats] == ["Ann 1", "Ann 2", "Random bot"]


@pytest.mark.parametrize(
    "argv",
    [
        ["--bot", "chess"],
        ["--bot", "random:3"],
        ["--bot", "expected:3"],
        ["--bot", "threshold:lots"],
        ["--bot", "threshold:-1"],
        ["--human", " "],
        ["--bot", "random"] * (MAX_PLAYERS + 1),
    ],
    ids=[
        "unknown",
        "random-param",
        "expected-param",
        "not-a-number",
        "negative",
        "blank-name",
        "too-many",
    ],
)
def test_invalid_options_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_options(argv)


def test_seed_and_bug_folder_can_be_set() -> None:
    options = parse_options(["--seed", "7", "--bug-dir", "reports/flip"])
    assert options.seed == 7
    assert options.bug_dir == Path("reports/flip")
    assert not options.show_setup


def test_explicit_setup_flag_and_named_bot() -> None:
    options = parse_options(["--setup", "--bot", "rival=threshold:25", "--seed", "7"])
    assert options.show_setup
    assert options.seats[0].name == "rival"
    assert not parse_options(["--no-setup"]).show_setup


@pytest.mark.parametrize(
    ("flag", "brutal"), [("--vengeance", False), ("--brutal", True)]
)
def test_mode_flags_skip_setup_with_default_players(flag: str, brutal: bool) -> None:
    options = parse_options([flag])
    assert options.vengeance and options.brutal is brutal
    assert not options.show_setup
    assert [seat.name for seat in options.seats] == [
        "Me",
        "Threshold 30",
        "Expected value",
    ]
