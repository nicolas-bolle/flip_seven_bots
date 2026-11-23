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
        "k",
        "k-schedule",
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
            "--plots",
        ]
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
def test_unified_cli_help(
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
        "flip_seven_bots.ui.__main__",
        "flip_seven_bots.ui.tournament.__main__",
    ],
)
def test_legacy_module_entry_points_are_removed(module: str) -> None:
    assert find_spec(module) is None


def test_unified_tournament_dispatches_gui_and_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flip_seven_bots.cli import main
    from flip_seven_bots.tournament import cli
    from flip_seven_bots.ui.tournament import app

    calls = []
    monkeypatch.setattr(cli, "main", lambda argv: calls.append(("terminal", argv)))
    monkeypatch.setattr(app, "main", lambda argv: calls.append(("gui", argv)))
    main(["tournament", "--games", "2"])
    main(["tournament", "--gui", "--setup", "--games", "2"])
    assert calls == [
        ("terminal", ["--games", "2"]),
        ("gui", ["--setup", "--games", "2"]),
    ]


def test_tournament_setup_requires_gui(capsys: pytest.CaptureFixture[str]) -> None:
    from flip_seven_bots.cli import main

    with pytest.raises(SystemExit) as result:
        main(["tournament", "--setup"])
    assert result.value.code == 2
    assert "require --gui" in capsys.readouterr().err


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
