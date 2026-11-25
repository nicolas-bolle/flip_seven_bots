import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pygame
import pytest

from flip_seven_bots.bots import ExpectedValueBot, RandomBot, ThresholdBot
from flip_seven_bots.game import Action, Observation
from flip_seven_bots.gui.tournament import app, run_scene
from flip_seven_bots.gui.tournament.run_scene import (
    NEW_BUTTON,
    SAVE_BUTTON,
    STANDINGS,
    STOP_BUTTON,
    TournamentScene,
)
from flip_seven_bots.gui.tournament.setup_scene import (
    ADD_BUTTON,
    GAMES_FIELD,
    JOBS_FIELD,
    MAX_BOTS,
    SEED_FIELD,
    START_BUTTON,
    TABLE_FIELD,
    VENGEANCE_BUTTON,
    TournamentSetupScene,
    _row_rects,
)
from flip_seven_bots.tournament.cli import TournamentOptions, parse_options


@pytest.fixture(autouse=True)
def fonts() -> Iterator[None]:
    pygame.font.init()
    yield
    pygame.font.quit()


def click(scene: TournamentSetupScene | TournamentScene, rect: pygame.Rect) -> None:
    scene.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)
    )


def replace_field(scene: TournamentSetupScene, rect: pygame.Rect, value: str) -> None:
    click(scene, rect)
    scene.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=pygame.KMOD_CTRL)
    )
    scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=value))


def quick_options(**changes: object) -> TournamentOptions:
    options = parse_options(
        ["--bot", "threshold:10", "--bot", "threshold:30", "--games", "5"]
    )
    return replace(options, **changes)


def wait_until(
    scene: TournamentScene, done: Callable[[], bool], timeout: float = 10
) -> None:
    deadline = time.monotonic() + timeout
    while not done():
        assert time.monotonic() < deadline, "tournament did not progress in time"
        scene.update(0)
        time.sleep(0.005)


def test_setup_starts_with_the_given_options() -> None:
    scene = TournamentSetupScene(parse_options([]))
    scene.render(pygame.Surface((1280, 900)))
    click(scene, START_BUTTON)
    assert scene.result is not None
    assert list(scene.result.bots) == [
        "Random bot",
        "Threshold 30",
        "Expected value bot",
    ]
    assert isinstance(scene.result.bots["Threshold 30"], ThresholdBot)
    assert scene.result.bots["Threshold 30"].threshold == 30
    assert isinstance(scene.result.bots["Expected value bot"], ExpectedValueBot)
    assert scene.result.games == 100 and scene.result.players_per_game is None


def test_setup_edits_bots_mode_and_numbers() -> None:
    scene = TournamentSetupScene(parse_options(["--k-factor", "16"]))
    click(scene, VENGEANCE_BUTTON)
    replace_field(scene, GAMES_FIELD, "12")
    replace_field(scene, TABLE_FIELD, "2")
    replace_field(scene, SEED_FIELD, "7x")  # non-digits are ignored
    replace_field(scene, JOBS_FIELD, "2")
    click(scene, _row_rects(0)[1])  # random -> threshold
    click(scene, START_BUTTON)
    assert scene.result is None
    assert scene.error == "missing required parameters for 'threshold': threshold"
    replace_field(scene, _row_rects(0)[2], "15")
    replace_field(scene, _row_rects(2)[0], "Threshold 30")
    click(scene, ADD_BUTTON)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    result = scene.result
    assert result is not None
    assert list(result.bots) == [
        "Random bot",
        "Threshold 30 1",
        "Threshold 30 2",
        "Threshold 30 3",
    ]
    assert isinstance(result.bots["Random bot"], ThresholdBot)
    assert result.bots["Random bot"].threshold == 15
    assert isinstance(result.bots["Threshold 30 2"], ExpectedValueBot)
    assert (result.games, result.players_per_game, result.seed) == (12, 2, 7)
    assert result.jobs == 2
    assert result.vengeance and not result.brutal and result.k_factor == 16


def test_setup_limits_bot_count() -> None:
    scene = TournamentSetupScene(parse_options([]))
    for _ in range(MAX_BOTS):
        click(scene, ADD_BUTTON)
    assert len(scene.bots) == MAX_BOTS
    for _ in range(MAX_BOTS):
        click(scene, _row_rects(0)[3])
    assert len(scene.bots) == 2


def test_setup_fits_the_most_bots_between_the_settings_and_buttons() -> None:
    rows = [rect for index in range(MAX_BOTS) for rect in _row_rects(index)]
    assert all(rect.top > GAMES_FIELD.bottom for rect in rows)
    assert all(not rect.colliderect(ADD_BUTTON) for rect in rows)
    assert all(not rect.colliderect(START_BUTTON) for rect in rows)


def test_standings_fit_the_most_bots_in_distinct_colors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = [f"bot {index}" for index in range(MAX_BOTS)]
    argv = [arg for name in names for arg in ("--bot", f"{name}=random")]
    scene = TournamentScene(parse_options([*argv, "--games", "1"]))
    drawn: dict[str, tuple[int, int]] = {}
    colors: set[object] = set()
    monkeypatch.setattr(
        run_scene,
        "draw_text",
        lambda _screen, _font, text, position, _color=None: drawn.setdefault(
            text, position
        ),
    )
    monkeypatch.setattr(
        run_scene.pygame.draw,
        "rect",
        lambda _screen, color, *_args, **_kwargs: colors.add(tuple(color)),
    )
    try:
        scene.render(pygame.Surface((1280, 900)))
    finally:
        scene.close()
    # Each row's stripe spans 8 pixels above its text to 32 below.
    assert all(drawn[name][1] + 32 <= STANDINGS.bottom for name in names)
    assert len(colors & set(run_scene.LINE_COLORS)) == MAX_BOTS


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        (GAMES_FIELD, "0", "play at least one game"),
        (TABLE_FIELD, "4", "players per game must be between 2 and 3"),
        (_row_rects(1)[0], " ", "every bot needs a name"),
    ],
    ids=["no-games", "table-too-big", "blank-name"],
)
def test_setup_rejects_invalid_settings(
    field: pygame.Rect, value: str, error: str
) -> None:
    scene = TournamentSetupScene(parse_options([]))
    replace_field(scene, field, value)
    click(scene, START_BUTTON)
    assert scene.result is None and scene.error == error


def test_tournament_runs_in_the_background_and_shows_results(tmp_path: Path) -> None:
    scene = TournamentScene(quick_options(seed=3), save_dir=tmp_path / "saved")
    surface = pygame.Surface((1280, 900))
    scene.render(surface)
    wait_until(scene, lambda: scene.finished)
    scene.render(surface)

    assert scene.error is None and len(scene.records) == 5
    assert scene.result is not None
    summary = scene.result.summary
    assert summary["games"].sum() == 10
    assert summary["rating_low"].notna().all()
    click(scene, SAVE_BUTTON)
    assert scene.saved is not None
    games_csv, summary_csv = scene.saved
    assert (
        games_csv.parent.parent == tmp_path / "saved"
    )  # a timestamped folder per save
    assert games_csv.exists() and summary_csv.exists()
    click(scene, NEW_BUTTON)
    assert scene.restart


def test_tournament_window_runs_with_parallel_workers() -> None:
    scene = TournamentScene(quick_options(seed=3, jobs=2))
    wait_until(scene, lambda: scene.finished)
    assert scene.error is None and len(scene.records) == 5


def test_tournament_saves_automatically_to_the_output_folder(tmp_path: Path) -> None:
    scene = TournamentScene(quick_options(output=tmp_path))
    wait_until(scene, lambda: scene.finished)
    assert scene.saved is not None and (tmp_path / "summary.csv").exists()


def test_stop_ends_the_tournament_early() -> None:
    scene = TournamentScene(quick_options(games=100_000))
    wait_until(scene, lambda: len(scene.records) > 0)
    click(scene, STOP_BUTTON)
    wait_until(scene, lambda: scene.finished)
    scene.render(pygame.Surface((1280, 900)))
    assert 0 < len(scene.records) < 100_000 and scene.error is None


def test_bot_errors_are_shown_instead_of_crashing() -> None:
    class Broken:
        def choose_action(self, observation: Observation) -> Action:
            raise RuntimeError("boom")

    scene = TournamentScene(
        quick_options(bots={"broken": lambda seed: Broken(), "random": RandomBot()})
    )
    wait_until(scene, lambda: scene.finished)
    scene.render(pygame.Surface((1280, 900)))
    assert scene.error == "RuntimeError: boom" and scene.records == []
    assert scene.result is None


def test_app_moves_from_setup_to_tournament_and_stops_it_on_quit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenes: list[TournamentScene] = []

    class Recording(TournamentScene):
        def __init__(self, options: TournamentOptions) -> None:
            super().__init__(options)
            scenes.append(self)

    frames = iter(
        [
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)],
            [pygame.event.Event(pygame.QUIT)],
        ]
    )
    cleanup = Mock()
    monkeypatch.setattr(pygame, "init", Mock())
    monkeypatch.setattr(pygame, "quit", cleanup)
    monkeypatch.setattr(
        pygame.display, "set_mode", Mock(return_value=pygame.Surface((1280, 900)))
    )
    monkeypatch.setattr(pygame.display, "set_caption", Mock())
    monkeypatch.setattr(pygame.display, "flip", Mock())
    monkeypatch.setattr(pygame.time, "Clock", Mock())
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: 0)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (0, 0))
    monkeypatch.setattr(pygame.event, "get", lambda: next(frames))
    monkeypatch.setattr(app, "TournamentScene", Recording)

    app.main(parse_options([]), show_setup=True)

    assert len(scenes) == 1 and scenes[0]._stop.is_set()
    cleanup.assert_called_once_with()
