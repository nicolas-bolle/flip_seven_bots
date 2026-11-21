import runpy
from unittest.mock import Mock

import pygame
import pytest

from flip_seven_bots.ui import app


def test_module_entry_point_calls_main(monkeypatch: pytest.MonkeyPatch) -> None:
    main = Mock()
    monkeypatch.setattr(app, "main", main)
    runpy.run_module("flip_seven_bots.ui", run_name="__main__")
    main.assert_called_once_with()


@pytest.mark.parametrize(
    "quit_event",
    [pygame.event.Event(pygame.QUIT), pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)],
    ids=["window-close", "escape"],
)
def test_app_dispatches_events_renders_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, quit_event: pygame.event.Event,
) -> None:
    scene = Mock()
    screen = pygame.Surface((1280, 900))
    clock = Mock()
    initialize = Mock()
    cleanup = Mock()
    flip = Mock()
    set_mode = Mock(return_value=screen)
    forwarded = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h)
    events = iter([[forwarded], [quit_event]])
    monkeypatch.setattr(pygame, "init", initialize)
    monkeypatch.setattr(pygame, "quit", cleanup)
    monkeypatch.setattr(pygame.display, "set_mode", set_mode)
    monkeypatch.setattr(pygame.display, "set_caption", Mock())
    monkeypatch.setattr(pygame.display, "flip", flip)
    monkeypatch.setattr(pygame.time, "Clock", lambda: clock)
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: 123)
    monkeypatch.setattr(pygame.event, "get", lambda: next(events))
    monkeypatch.setattr(app, "GameScene", lambda: scene)

    app.main()

    initialize.assert_called_once_with()
    set_mode.assert_called_once_with((1280, 900))
    scene.handle_event.assert_called_once_with(forwarded)
    scene.update.assert_called_once_with(123)
    scene.render.assert_called_once_with(screen)
    flip.assert_called_once_with()
    clock.tick.assert_called_once_with(60)
    cleanup.assert_called_once_with()


def test_app_cleans_up_when_scene_creation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    cleanup = Mock()
    monkeypatch.setattr(pygame, "init", Mock())
    monkeypatch.setattr(pygame, "quit", cleanup)
    monkeypatch.setattr(pygame.display, "set_mode", Mock())
    monkeypatch.setattr(pygame.display, "set_caption", Mock())
    monkeypatch.setattr(pygame.time, "Clock", Mock())
    monkeypatch.setattr(app, "GameScene", Mock(side_effect=RuntimeError("scene failed")))
    with pytest.raises(RuntimeError, match="scene failed"):
        app.main()
    cleanup.assert_called_once_with()
