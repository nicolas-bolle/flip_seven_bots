from collections.abc import Iterator

import pygame
import pytest

from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    EventType,
    Game,
    GameEvent,
    PlayerStatus,
)
from flip_seven_bots.game.model import RoundResult
from flip_seven_bots.ui.game_scene import GameScene, _card_label, _event_text


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


@pytest.mark.parametrize(
    ("card", "label"),
    [
        (Card(CardType.NUMBER, 12), "12"),
        (Card(CardType.ADD, 6), "+6"),
        (Card(CardType.MULTIPLY, 2), "x2"),
        (Card(CardType.FREEZE), "FREEZE"),
        (Card(CardType.FLIP_THREE), "FLIP 3"),
        (Card(CardType.SECOND_CHANCE), "SECOND CHANCE"),
    ],
)
def test_card_labels(card: Card, label: str) -> None:
    assert _card_label(card) == label


@pytest.mark.parametrize(
    ("event", "message"),
    [
        (GameEvent(EventType.ROUND_STARTED, 2), "Round 2 started"),
        (GameEvent(EventType.DISCARD_SHUFFLED, 2), "Discard pile reshuffled"),
        (GameEvent(EventType.CARD_DRAWN, 2, 0, Card(CardType.NUMBER, 4)), "You drew 4"),
        (
            GameEvent(EventType.ACTION_CHOSEN, 2, 1, action=Action(ActionType.STAY)),
            "Random bot chose stay",
        ),
        (
            GameEvent(
                EventType.ACTION_CHOSEN, 2, 0,
                action=Action(ActionType.CHOOSE_TARGET, 2),
            ),
            "You chose Threshold bot",
        ),
        (
            GameEvent(
                EventType.ROUND_ENDED, 2,
                result=RoundResult(2, (0, 40, 0), (0, 40, 0), 1),
            ),
            "Random bot got Flip 7!",
        ),
        (GameEvent(EventType.ROUND_ENDED, 2), "Round 2 ended"),
    ],
)
def test_activity_messages(event: GameEvent, message: str) -> None:
    assert _event_text(event) == message


@pytest.mark.usefixtures("pygame_fonts")
def test_mouse_can_hit_and_choose_a_target(monkeypatch: pytest.MonkeyPatch) -> None:
    draws = [
        Card(CardType.NUMBER, 3), Card(CardType.NUMBER, 1),
        Card(CardType.NUMBER, 2), Card(CardType.FREEZE),
    ]
    with monkeypatch.context() as patch:
        patch.setattr("flip_seven_bots.game.engine.build_deck", lambda: list(reversed(draws)))
        patch.setattr("flip_seven_bots.game.engine.Random.shuffle", lambda _self, _cards: None)
        game = Game(3, dealer=2)

    monkeypatch.setattr("flip_seven_bots.ui.game_scene.Game", lambda _count: game)
    monkeypatch.setattr("pygame.mouse.get_pos", lambda: (0, 0))
    scene = GameScene()
    screen = pygame.Surface((1280, 900))
    scene.render(screen)
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(75, 810)))
    assert game.observe(0).pending_card == Card(CardType.FREEZE)

    scene.render(screen)
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(490, 810)))
    assert game.observe(0).players[2].status is PlayerStatus.STAYED


@pytest.mark.usefixtures("pygame_fonts")
@pytest.mark.parametrize("target_score", [1, 200])
def test_round_summary_continue_and_restart(
    monkeypatch: pytest.MonkeyPatch, target_score: int,
) -> None:
    draws = [Card(CardType.NUMBER, n) for n in (5, 4, 3, 7, 8, 9)]
    monkeypatch.setattr("flip_seven_bots.game.engine.TARGET_SCORE", target_score)
    with monkeypatch.context() as patch:
        patch.setattr("flip_seven_bots.game.engine.build_deck", lambda: list(reversed(draws)))
        patch.setattr("flip_seven_bots.game.engine.Random.shuffle", lambda _self, _cards: None)
        game = Game(3, dealer=2)

    games = [game]

    def create_game(count: int) -> Game:
        if not games:
            games.append(Game(count, seed=10))
        return games.pop()

    monkeypatch.setattr("flip_seven_bots.ui.game_scene.Game", create_game)
    monkeypatch.setattr("pygame.mouse.get_pos", lambda: (0, 0))
    monkeypatch.setattr(
        "flip_seven_bots.ui.game_scene.RandomBot.choose_action",
        lambda _self, _observation: Action(ActionType.STAY),
    )
    monkeypatch.setattr(
        "flip_seven_bots.ui.game_scene.ThresholdBot.choose_action",
        lambda _self, _observation: Action(ActionType.STAY),
    )
    texts: list[str] = []
    monkeypatch.setattr(
        GameScene, "_text",
        staticmethod(lambda _screen, _font, text, _position, _color=None: texts.append(text)),
    )
    scene = GameScene()
    screen = pygame.Surface((1280, 900))
    scene.render(screen)
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(260, 810)))
    scene.update(pygame.time.get_ticks() + 1000)
    scene.update(pygame.time.get_ticks() + 1000)
    assert game.observe(0).last_round is not None
    texts.clear()
    scene.render(screen)
    assert "Round 1 complete" in texts
    assert "You:  +5    total 5" in texts

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    texts.clear()
    scene.render(screen)
    if target_score == 1:
        assert game.is_finished
        assert "Game over" in texts
        assert "Winner: You" in texts
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
        texts.clear()
        scene.render(screen)
        assert "Round 1 complete" not in texts
        assert "Game over" not in texts
    else:
        assert not game.is_finished
        assert "Round 1 complete" not in texts
