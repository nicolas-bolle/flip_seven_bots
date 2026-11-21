from collections.abc import Iterator

import pygame
import pytest

from flip_seven_bots.game import Action, ActionType, Card, CardType, Game, PlayerStatus
from flip_seven_bots.ui.game_scene import GameScene


@pytest.fixture
def pygame_fonts() -> Iterator[None]:
    was_initialized = pygame.font.get_init()
    pygame.font.init()
    yield
    if not was_initialized:
        pygame.font.quit()


@pytest.mark.usefixtures("pygame_fonts")
def test_human_target_and_bot_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    draws = [
        Card(CardType.NUMBER, 3),
        Card(CardType.NUMBER, 1),
        Card(CardType.NUMBER, 2),
        Card(CardType.FREEZE),
    ]
    with monkeypatch.context() as patch:
        patch.setattr(
            "flip_seven_bots.game.engine.build_deck", lambda: list(reversed(draws))
        )
        patch.setattr("flip_seven_bots.game.engine.Random.shuffle", lambda _self, _cards: None)
        game = Game(3, dealer=2)

    monkeypatch.setattr("flip_seven_bots.ui.game_scene.Game", lambda _player_count: game)
    monkeypatch.setattr("pygame.mouse.get_pos", lambda: (0, 0))
    scene = GameScene()
    screen = pygame.Surface((1280, 900))
    scene.render(screen)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
    assert game.observe(0).pending_card == Card(CardType.FREEZE)

    scene.render(screen)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3))
    assert game.observe(0).players[2].status == PlayerStatus.STAYED
    assert game.current_player == 1

    scene.render(screen)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
    assert game.current_player == 1

    monkeypatch.setattr(
        "flip_seven_bots.ui.game_scene.RandomBot.choose_action",
        lambda _self, _observation: Action(ActionType.STAY),
    )
    scene.update(pygame.time.get_ticks() + 1_000)
    assert game.current_player == 0
    assert game.observe(0).players[1].status == PlayerStatus.STAYED
