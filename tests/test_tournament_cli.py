import json
from dataclasses import replace
from importlib.util import find_spec
from pathlib import Path

import pandas as pd
import pytest

from flip_seven_bots.bots import ExpectedValueBot, RandomBot, ThresholdBot
from flip_seven_bots.bots.registry import BotKind, Parameter, register
from flip_seven_bots.bots.specs import bot_spec, parse_bot
from flip_seven_bots.game import VengeanceRules
from flip_seven_bots.tournament import TournamentResult, play_tournament, run_tournament
from flip_seven_bots.tournament.cli import (
    parse_launch,
    parse_options,
    run,
)


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
    careful = options.bots["careful"]
    assert isinstance(careful, ThresholdBot) and careful.threshold == 40
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
        ["--bot", "random"] * 11 + ["--players-per-game", "11"],
        ["--k-factor", "0"],
        ["--constant-k", "--k-half-life", "5"],
    ],
    ids=[
        "one-bot",
        "unknown",
        "blank-name",
        "no-games",
        "table-too-big",
        "table-too-small",
        "table-over-player-limit",
        "k",
        "k-schedule",
    ],
)
def test_invalid_options_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_options(argv)


def test_run_prints_progress_and_summary_and_saves_results(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    run(
        parse_options(
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
                "--plots",
            ]
        )
    )
    out, err = capsys.readouterr()
    assert out.startswith("2 bots, 3 games of 2 players, Flip 7\n")
    assert "win_rate" in out and "Threshold 30" in out and "95% interval" in out
    assert "Tournament" in err and "3/3" in err
    games = pd.read_csv(tmp_path / "out" / "games.csv")
    summary = pd.read_csv(tmp_path / "out" / "summary.csv", index_col="player")
    assert len(games) == 6 and len(summary) == 2
    settings = json.loads((tmp_path / "out" / "settings.json").read_text())
    assert settings["seed"] == 1 and settings["games_played"] == 3
    assert settings["bots"] == {
        "Threshold 10": "threshold:10",
        "Threshold 30": "threshold:30",
    }
    assert "git_commit" in settings
    assert (tmp_path / "out" / "ratings.html").exists()
    assert (tmp_path / "out" / "elo.html").exists()


def test_play_tournament_validates_eagerly_and_plays_lazily() -> None:
    bots = {"a": ThresholdBot(10), "b": ThresholdBot(30)}
    with pytest.raises(ValueError, match="games"):
        play_tournament(bots, games=0)
    records = play_tournament(bots, games=3, seed=4)
    first = next(records)
    assert first.game == 1 and sorted(first.players) == ["a", "b"]
    rest = list(records)
    rebuilt = TournamentResult.from_records(
        [first, *rest], list(bots), initial_rating=1500
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
    options = parse_options(["--games", "9", "--constant-k", "--seed", "2"])
    assert options.k_half_life is None
    assert options.describe() == "3 bots, 9 games of 3 players, Flip 7"
    assert parse_options(["--k-half-life", "20"]).k_half_life == 20

    fast = replace(
        options,
        bots={"a": ThresholdBot(10), "b": ThresholdBot(30), "c": ThresholdBot(20)},
    )
    result = fast.run(progress=False)
    assert result.games["game"].max() == 9
    assert (result.summary["rating_low"] < result.summary["rating"]).all()
    assert fast.result(list(fast.start())).games.equals(result.games)


def test_registered_multi_parameter_bot_parses_named_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flip_seven_bots.bots import registry

    class Configurable(ThresholdBot):
        def __init__(self, *, seed: int | None, threshold: int, bonus: int) -> None:
            super().__init__(threshold)
            self.bonus = bonus

    monkeypatch.setattr(registry, "_KINDS", dict(registry._KINDS))
    register(
        BotKind(
            "configurable",
            "Configurable",
            Configurable,
            Configurable,
            (Parameter("threshold", 30), Parameter("bonus", 1)),
        )
    )
    options = parse_options(
        ["--bot", "example=configurable:threshold=12,bonus=3", "--bot", "random"]
    )
    bot = options.bots["example"]
    assert isinstance(bot, Configurable)
    assert (bot.threshold, bot.bonus) == (12, 3)
    assert bot_spec(bot) == "configurable:threshold=12,bonus=3"


def test_trace_reports_seeded_bot_decisions(capsys: pytest.CaptureFixture[str]) -> None:
    from flip_seven_bots.cli import main

    args = ["trace", "--bot", "threshold:0", "--bot", "random", "--seed", "7"]
    main(args)
    first = capsys.readouterr().out
    main(args)
    assert capsys.readouterr().out == first
    assert "seat 0:" in first and "Winners:" in first


@pytest.mark.parametrize(
    ("argv", "usage", "flags"),
    [
        (["play", "--help"], "flip7 play", ("--human", "--setup")),
        (["tournament", "--help"], "flip7 tournament", ("--gui", "--jobs")),
        (
            ["tournament", "--gui", "--help"],
            "flip7 tournament",
            ("--gui", "--setup", "--no-setup"),
        ),
    ],
)
def test_help_lists_each_commands_options(
    argv: list[str],
    usage: str,
    flags: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    from flip_seven_bots.cli import main

    with pytest.raises(SystemExit) as result:
        main(argv)
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert f"usage: {usage}" in help_text
    assert all(flag in help_text for flag in flags)


@pytest.mark.parametrize(
    "module",
    [
        "flip_seven_bots.tournament.__main__",
        "flip_seven_bots.gui.__main__",
        "flip_seven_bots.gui.play.__main__",
        "flip_seven_bots.gui.tournament.__main__",
    ],
)
def test_packages_are_not_cli_entry_points(module: str) -> None:
    assert find_spec(module) is None


def test_unified_play_dispatches_to_game_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flip_seven_bots.cli import main
    from flip_seven_bots.gui.play import app

    calls = []
    monkeypatch.setattr(app, "main", lambda argv: calls.append(argv))
    main(["play", "--bot", "random"])
    assert calls == [["--bot", "random"]]


def test_unified_tournament_dispatches_gui_and_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flip_seven_bots.cli import main
    from flip_seven_bots.gui.tournament import app
    from flip_seven_bots.tournament import cli

    calls = []
    monkeypatch.setattr(cli, "run", lambda options: calls.append(("terminal", options)))
    monkeypatch.setattr(
        app,
        "main",
        lambda options, *, show_setup: calls.append(("gui", options, show_setup)),
    )
    main(["tournament", "--games", "2"])
    main(["tournament", "--gui", "--setup", "--games", "3"])
    main(["compare", "random", "threshold:20", "--gui", "--games", "4"])
    assert [call[0] for call in calls] == ["terminal", "gui", "gui"]
    assert [call[1].games for call in calls] == [2, 3, 4]
    assert calls[1][2] and not calls[2][2]
    assert list(calls[2][1].bots) == ["Random bot", "Threshold 20"]


@pytest.mark.parametrize(
    ("argv", "show_setup"),
    [
        (["--gui"], True),
        (["--gui", "--games", "5"], False),
        (["--gui", "--setup", "--games", "5"], True),
        (["--gui", "--no-setup"], False),
        ([], False),
    ],
)
def test_launch_shows_setup_only_when_requested_or_unconfigured(
    argv: list[str], show_setup: bool
) -> None:
    launch = parse_launch(argv)
    assert launch.show_setup == show_setup
    assert launch.gui == ("--gui" in argv)


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--setup"], "require --gui"),
        (["--gui", "--setup", "--no-setup"], "not allowed with argument"),
    ],
)
def test_invalid_launch_flags_are_rejected(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as result:
        parse_launch(argv)
    assert result.value.code == 2
    assert message in capsys.readouterr().err


def test_settings_parser_rejects_window_flags() -> None:
    with pytest.raises(SystemExit):
        parse_options(["--gui"])


def test_bot_spec_round_trips_reserved_text_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flip_seven_bots.bots import registry

    class TextBot(ThresholdBot):
        def __init__(self, *, seed: int | None, label: str) -> None:
            super().__init__(0)
            self.label = label

    monkeypatch.setattr(registry, "_KINDS", dict(registry._KINDS))
    register(BotKind("text", "Text", TextBot, TextBot, (Parameter("label", "", str),)))
    bot = parse_bot("text:hello%2Cworld%3Dyes")[1]
    assert isinstance(bot, TextBot) and bot.label == "hello,world=yes"
    assert bot_spec(bot) == "text:hello%2Cworld%3Dyes"
    assert bot_spec(parse_bot("text:")[1]) == "text:"
