from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from flip_seven_bots.bots import ExpectedValueBot, RandomBot, ThresholdBot
from flip_seven_bots.bots.specs import bot_spec, parse_bot
from flip_seven_bots.game import VengeanceRules
from flip_seven_bots.tournament import TournamentResult, play_tournament, run_tournament
from flip_seven_bots.tournament.cli import main, parse_options


def test_default_lineup_and_settings() -> None:
    options = parse_options([])
    assert list(options.bots) == ["Random bot", "Threshold 30", "Expected value bot"]
    assert (options.games, options.players_per_game, options.rules) == (100, None, None)


def test_bots_take_optional_names_and_duplicates_are_numbered() -> None:
    options = parse_options(
        [
            "--bot",
            "threshold:20",
            "--bot",
            "threshold:20",
            "--bot",
            "careful=threshold:40",
            "--bot",
            "random",
            "--brutal",
            "--games",
            "7",
            "--players-per-game",
            "3",
        ]
    )
    assert list(options.bots) == [
        "Threshold 20 1",
        "Threshold 20 2",
        "careful",
        "Random bot",
    ]
    assert options.bots["careful"].threshold == 40
    assert isinstance(options.rules, VengeanceRules) and options.rules.brutal
    assert (
        options.describe() == "4 bots, 7 games of 3 players, With A Vengeance (Brutal)"
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["--bot", "random"],
        ["--bot", "chess", "--bot", "random"],
        ["--bot", "=random", "--bot", "random"],
        ["--games", "0"],
        ["--players-per-game", "4"],
        ["--players-per-game", "1"],
        ["--k-factor", "0"],
        ["--rotate-seats", "--games", "10"],
        ["--constant-k", "--k-half-life", "5"],
        ["--bootstrap", "-1"],
    ],
    ids=[
        "one-bot",
        "unknown",
        "blank-name",
        "no-games",
        "table-too-big",
        "table-too-small",
        "k",
        "rotation",
        "k-schedule",
        "bootstrap",
    ],
)
def test_invalid_options_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_options(argv)


def test_main_prints_progress_and_summary_and_saves_csvs(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    main(
        [
            "--bot",
            "threshold:10",
            "--bot",
            "threshold:30",
            "--games",
            "3",
            "--seed",
            "1",
            "--output",
            str(tmp_path / "out"),
        ]
    )
    out, err = capsys.readouterr()
    assert out.startswith("2 bots, 3 games of 2 players, Flip 7\n")
    assert "win_rate" in out and "Threshold 30" in out and "95% interval" in out
    assert "Tournament" in err and "3/3" in err
    games = pd.read_csv(tmp_path / "out" / "games.csv")
    summary = pd.read_csv(tmp_path / "out" / "summary.csv", index_col="player")
    assert len(games) == 6 and len(summary) == 2


def test_play_tournament_validates_eagerly_and_plays_lazily() -> None:
    bots = {"a": ThresholdBot(10), "b": ThresholdBot(30)}
    with pytest.raises(ValueError, match="games"):
        play_tournament(bots, games=0)
    records = play_tournament(bots, games=3, seed=4)
    first = next(records)
    assert first.game == 1 and sorted(first.players) == ["a", "b"]
    rest = list(records)
    rebuilt = TournamentResult.from_records(
        [first, *rest], list(bots), initial_rating=1500, seed=4
    )
    direct = run_tournament(
        {"a": ThresholdBot(10), "b": ThresholdBot(30)}, games=3, seed=4, progress=False
    )
    pd.testing.assert_frame_equal(rebuilt.games, direct.games)
    pd.testing.assert_frame_equal(rebuilt.summary, direct.summary)


@pytest.mark.parametrize("bot", [RandomBot(), ThresholdBot(25), ExpectedValueBot()])
def test_bot_specs_round_trip(bot: RandomBot | ThresholdBot | ExpectedValueBot) -> None:
    rebuilt = parse_bot(bot_spec(bot))[1]
    assert type(rebuilt) is type(bot)
    assert bot_spec(rebuilt) == bot_spec(bot)


def test_rating_options_reach_the_tournament() -> None:
    options = parse_options(
        [
            "--rotate-seats",
            "--games",
            "9",
            "--constant-k",
            "--bootstrap",
            "0",
            "--seed",
            "2",
        ]
    )
    assert (options.rotate_seats, options.k_half_life, options.bootstrap) == (
        True,
        None,
        0,
    )
    assert options.describe().endswith("rotated seats, Flip 7")
    assert parse_options(["--k-half-life", "20"]).k_half_life == 20

    fast = replace(
        options,
        bots={"a": ThresholdBot(10), "b": ThresholdBot(30), "c": ThresholdBot(20)},
    )
    result = fast.run(progress=False)
    assert result.games["deal"].max() == 3
    assert result.summary["rating_low"].isna().all()
    assert fast.result(list(fast.start())).games.equals(result.games)
