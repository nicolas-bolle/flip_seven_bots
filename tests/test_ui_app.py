from pathlib import Path
from unittest.mock import Mock

import pygame
import pytest

from flip_seven_bots.game import VengeanceRules
from flip_seven_bots.gui.play import app


@pytest.mark.parametrize(
    'quit_event',
    [
        pygame.event.Event(pygame.QUIT),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE),
    ],
    ids=['window-close', 'escape'],
)
def test_app_forwards_events_until_quit_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    quit_event: pygame.event.Event,
    tmp_path: Path,
) -> None:
    scene = Mock(dialog_open=False, return_to_setup=False)
    screen = pygame.Surface((1280, 900))
    clock = Mock()
    cleanup = Mock()
    forwarded = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h)
    events = iter([[forwarded], [quit_event]])
    monkeypatch.setattr(pygame, 'init', Mock())
    monkeypatch.setattr(pygame, 'quit', cleanup)
    monkeypatch.setattr(pygame.display, 'set_mode', Mock(return_value=screen))
    monkeypatch.setattr(pygame.display, 'set_caption', Mock())
    monkeypatch.setattr(pygame.display, 'flip', Mock())
    monkeypatch.setattr(pygame.time, 'Clock', lambda: clock)
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 123)
    monkeypatch.setattr(pygame.event, 'get', lambda: next(events))
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (4, 5))
    monkeypatch.setattr(app, 'GameScene', lambda _table, report_dir: scene)

    app.main(['--bug-dir', str(tmp_path)])

    scene.handle_event.assert_called_once_with(forwarded)
    scene.update.assert_called_once_with(123)
    scene.render.assert_called_once_with(screen, (4, 5))
    cleanup.assert_called_once_with()


def test_app_cleans_up_when_scene_creation_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cleanup = Mock()
    monkeypatch.setattr(pygame, 'init', Mock())
    monkeypatch.setattr(pygame, 'quit', cleanup)
    monkeypatch.setattr(pygame.display, 'set_mode', Mock())
    monkeypatch.setattr(pygame.display, 'set_caption', Mock())
    monkeypatch.setattr(pygame.time, 'Clock', Mock())
    monkeypatch.setattr(
        app, 'GameScene', Mock(side_effect=RuntimeError('scene failed'))
    )
    with pytest.raises(RuntimeError, match='scene failed'):
        app.main(['--bug-dir', str(tmp_path)])
    cleanup.assert_called_once_with()


def run_app(
    monkeypatch: pytest.MonkeyPatch, scene: Mock, frames: list[list[pygame.event.Event]]
) -> None:
    scene.return_to_setup = False
    events = iter(frames)
    monkeypatch.setattr(pygame, 'init', Mock())
    monkeypatch.setattr(pygame, 'quit', Mock())
    monkeypatch.setattr(
        pygame.display, 'set_mode', Mock(return_value=pygame.Surface((1280, 900)))
    )
    monkeypatch.setattr(pygame.display, 'set_caption', Mock())
    monkeypatch.setattr(pygame.display, 'flip', Mock())
    monkeypatch.setattr(pygame.time, 'Clock', Mock())
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 0)
    monkeypatch.setattr(pygame.mouse, 'get_pos', lambda: (0, 0))
    monkeypatch.setattr(pygame.event, 'get', lambda: next(events))
    monkeypatch.setattr(app, 'GameScene', lambda _table, report_dir: scene)


def test_escape_goes_to_an_open_dialog_instead_of_quitting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    escape = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
    scene = Mock(dialog_open=True)
    run_app(monkeypatch, scene, [[escape], [pygame.event.Event(pygame.QUIT)]])

    app.main(['--bug-dir', str(tmp_path)])
    scene.handle_event.assert_called_once_with(escape)


def test_crash_writes_a_report_and_reraises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scene = Mock(dialog_open=False)
    scene.update.side_effect = RuntimeError('engine exploded')
    run_app(monkeypatch, scene, [[]])

    with pytest.raises(RuntimeError, match='engine exploded'):
        app.main(['--bug-dir', str(tmp_path)])
    [report] = tmp_path.iterdir()
    assert report.name.endswith('_crash.md')
    assert 'RuntimeError: engine exploded' in report.read_text()
    assert str(report) in capsys.readouterr().err


def test_crash_is_reraised_even_if_the_report_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocked = tmp_path / 'file'
    blocked.write_text('not a folder')
    scene = Mock(dialog_open=False)
    scene.update.side_effect = RuntimeError('engine exploded')
    run_app(monkeypatch, scene, [[]])

    with pytest.raises(RuntimeError, match='engine exploded'):
        app.main(['--bug-dir', str(blocked)])
    assert 'Could not save a crash report' in capsys.readouterr().err


@pytest.mark.parametrize(
    ('flag', 'brutal'), [('--vengeance', False), ('--brutal', True)]
)
def test_mode_flags_create_vengeance_game_directly(
    monkeypatch: pytest.MonkeyPatch, flag: str, brutal: bool
) -> None:
    scene = Mock(dialog_open=False)
    run_app(monkeypatch, scene, [[pygame.event.Event(pygame.QUIT)]])
    constructor = Mock(return_value=scene)
    monkeypatch.setattr(app, 'GameScene', constructor)
    app.main([flag])
    table = constructor.call_args.args[0]
    assert isinstance(table.game.rules, VengeanceRules)
    assert table.game.rules.brutal is brutal


def test_app_returns_to_setup_with_the_previous_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pygame.font.init()
    try:
        scene = Mock(dialog_open=False)
        from flip_seven_bots.gui.play.setup_scene import (
            BRUTAL_BUTTON,
            START_BUTTON,
            VENGEANCE_BUTTON,
        )

        def click(rect: pygame.Rect) -> pygame.event.Event:
            return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)

        def request_setup(_event: pygame.event.Event) -> None:
            scene.return_to_setup = True

        scene.handle_event.side_effect = request_setup
        run_app(
            monkeypatch,
            scene,
            [
                [click(VENGEANCE_BUTTON), click(BRUTAL_BUTTON), click(START_BUTTON)],
                [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)],
                [click(START_BUTTON)],
                [pygame.event.Event(pygame.QUIT)],
            ],
        )
        constructor = Mock(return_value=scene)
        monkeypatch.setattr(app, 'GameScene', constructor)
        app.main([])
        first, second = [call.args[0] for call in constructor.call_args_list]
        assert first is not second
        for table in (first, second):
            assert (
                isinstance(table.game.rules, VengeanceRules) and table.game.rules.brutal
            )
            assert table.names == ('Human', 'Threshold 30', 'Expected value')
    finally:
        pygame.font.quit()
