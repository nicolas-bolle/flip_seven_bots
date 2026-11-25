from collections.abc import Iterator

import pygame
import pytest

from flip_seven_bots.bots import ExpectedValueBot, ThresholdBot
from flip_seven_bots.gui.play.options import MAX_PLAYERS
from flip_seven_bots.gui.play.setup_scene import (
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
    scene.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)
    )


def replace_field(scene: SetupScene, rect: pygame.Rect, value: str) -> None:
    click(scene, rect)
    scene.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=pygame.KMOD_CTRL)
    )
    scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=value))


def test_setup_starts_a_base_game_with_the_default_seats() -> None:
    scene = SetupScene()
    scene.render(pygame.Surface((1280, 900)))
    click(scene, START_BUTTON)
    assert scene.result is not None
    assert not scene.result.vengeance and not scene.result.brutal
    assert [seat.name for seat in scene.result.seats] == [
        "Human",
        "Threshold 30",
        "Expected value",
    ]
    assert isinstance(scene.result.seats[1].bot, ThresholdBot)
    assert scene.result.seats[1].bot.threshold == 30
    assert isinstance(scene.result.seats[2].bot, ExpectedValueBot)


def test_setup_edits_mode_seats_and_parameters() -> None:
    scene = SetupScene()
    click(scene, VENGEANCE_BUTTON)
    click(scene, BRUTAL_BUTTON)
    replace_field(scene, _row_rects(0)[0], "Ann")
    replace_field(scene, _row_rects(1)[0], "Ann")
    replace_field(scene, _row_rects(1)[2], "25")
    click(scene, _row_rects(2)[3])
    click(scene, ADD_BUTTON)
    for _ in range(3):  # human -> random -> threshold -> expected value
        click(scene, _row_rects(2)[1])
    click(scene, START_BUTTON)

    assert scene.result is not None
    assert scene.result.vengeance and scene.result.brutal
    assert [seat.name for seat in scene.result.seats] == ["Ann 1", "Ann 2", "Player 3"]
    assert isinstance(scene.result.seats[1].bot, ThresholdBot)
    assert scene.result.seats[1].bot.threshold == 25
    assert isinstance(scene.result.seats[2].bot, ExpectedValueBot)


def test_setup_validates_names_and_player_limit() -> None:
    scene = SetupScene()
    replace_field(scene, _row_rects(0)[0], " ")
    click(scene, START_BUTTON)
    assert scene.result is None and scene.error
    replace_field(scene, _row_rects(0)[0], "You")
    for _ in range(MAX_PLAYERS):
        click(scene, ADD_BUTTON)
    assert len(scene.players) == MAX_PLAYERS


def test_switching_to_threshold_requires_a_value() -> None:
    scene = SetupScene()
    _, kind, parameter, _ = _row_rects(0)
    click(scene, kind)  # human -> random
    click(scene, kind)  # random -> threshold
    click(scene, START_BUTTON)
    assert scene.result is None
    assert scene.error == "missing required parameters for 'threshold': threshold"

    replace_field(scene, parameter, "21")
    click(scene, START_BUTTON)
    assert scene.result is not None
    assert isinstance(scene.result.seats[0].bot, ThresholdBot)
    assert scene.result.seats[0].bot.threshold == 21
