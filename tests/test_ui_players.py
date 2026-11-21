import pytest

from flip_seven_bots.bots import FlipThreeMonteCarloBot, RandomBot, ThresholdBot
from flip_seven_bots.ui.players import MAX_PLAYERS, parse_seats


def test_no_options_gives_the_default_table() -> None:
    seats = parse_seats([])
    assert [seat.name for seat in seats] == ["You", "Random bot", "Threshold bot"]
    assert [seat.bot is None for seat in seats] == [True, False, False]


def test_seats_follow_option_order() -> None:
    seats = parse_seats(
        ["--bot", "random", "--human", "Ann", "--bot", "threshold:20",
         "--human", "Ben", "--bot", "montecarlo:10"]
    )
    assert [seat.name for seat in seats] == [
        "Random bot", "Ann", "Threshold 20", "Ben", "Monte Carlo bot",
    ]
    assert isinstance(seats[0].bot, RandomBot)
    assert seats[1].bot is None
    assert isinstance(seats[2].bot, ThresholdBot) and seats[2].bot.threshold == 20
    assert isinstance(seats[4].bot, FlipThreeMonteCarloBot) and seats[4].bot.samples == 10


def test_a_table_can_be_all_bots() -> None:
    seats = parse_seats(["--bot", "random", "--bot", "threshold"])
    assert all(seat.bot is not None for seat in seats)


def test_duplicate_names_are_numbered() -> None:
    seats = parse_seats(["--human", "Ann", "--human", "Ann", "--bot", "random"])
    assert [seat.name for seat in seats] == ["Ann 1", "Ann 2", "Random bot"]


@pytest.mark.parametrize(
    "argv",
    [
        ["--bot", "chess"],
        ["--bot", "random:3"],
        ["--bot", "threshold:lots"],
        ["--bot", "threshold:-1"],
        ["--bot", "montecarlo:0"],
        ["--human", " "],
        ["--bot", "random"] * (MAX_PLAYERS + 1),
    ],
    ids=["unknown", "random-param", "not-a-number", "negative", "no-samples",
         "blank-name", "too-many"],
)
def test_invalid_options_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_seats(argv)
