from collections.abc import Iterator

import pygame
import pytest

from flip_seven_bots.bots import ThresholdBot
from flip_seven_bots.ui.options import MAX_PLAYERS
from flip_seven_bots.ui.setup_scene import (
    ADD_BUTTON,
    BRUTAL_BUTTON,
    START_BUTTON,
    VENGEANCE_BUTTON,
    SetupScene,
    _row_rects,
)


@pytest.fixture(autouse=True)
def fonts() -> Iterator[None]:
    pygame.font.init()
    yield
    pygame.font.quit()


def click(scene: SetupScene, rect: pygame.Rect) -> None:
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))


def replace_field(scene: SetupScene, rect: pygame.Rect, value: str) -> None:
    click(scene, rect)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=pygame.KMOD_CTRL))
    scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=value))


def test_setup_defaults_and_start() -> None:
    scene = SetupScene()
    scene.render(pygame.Surface((1280, 900)))
    click(scene, START_BUTTON)
    assert scene.result is not None
    assert not scene.result.vengeance and not scene.result.brutal
    assert [seat.name for seat in scene.result.seats] == ["You", "Random bot", "Threshold bot"]
    assert isinstance(scene.result.seats[2].bot, ThresholdBot)
    assert scene.result.seats[2].bot.threshold == 30


def test_setup_edits_mode_seats_and_parameters() -> None:
    scene = SetupScene()
    click(scene, VENGEANCE_BUTTON)
    click(scene, BRUTAL_BUTTON)
    replace_field(scene, _row_rects(0)[0], "Ann")
    click(scene, _row_rects(1)[1])  # random -> threshold
    replace_field(scene, _row_rects(1)[0], "Ann")
    replace_field(scene, _row_rects(1)[2], "25")
    click(scene, _row_rects(2)[3])
    click(scene, ADD_BUTTON)
    click(scene, START_BUTTON)

    assert scene.result is not None
    assert scene.result.vengeance and scene.result.brutal
    assert [seat.name for seat in scene.result.seats] == ["Ann 1", "Ann 2", "Player 3"]
    assert isinstance(scene.result.seats[1].bot, ThresholdBot)
    assert scene.result.seats[1].bot.threshold == 25


def test_setup_validates_names_parameters_and_player_limit() -> None:
    scene = SetupScene()
    replace_field(scene, _row_rects(0)[0], " ")
    click(scene, START_BUTTON)
    assert scene.result is None and scene.error
    replace_field(scene, _row_rects(0)[0], "You")
    click(scene, _row_rects(2)[1])  # threshold -> Monte Carlo
    replace_field(scene, _row_rects(2)[2], "0")
    click(scene, START_BUTTON)
    assert scene.result is None and scene.error == "samples must be at least one"
    for _ in range(MAX_PLAYERS):
        click(scene, ADD_BUTTON)
    assert len(scene.players) == MAX_PLAYERS
