from collections.abc import Iterator

import pygame
import pytest

from flip_seven_bots.game import (
    Action,
    ActionChosen,
    ActionType,
    Card,
    CardDrawn,
    CardType,
    Deck,
    DiscardShuffled,
    Game,
    GameEvent,
    PlayerStatus,
    RoundEnded,
    RoundResult,
    RoundStarted,
    Rules,
)
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
    game = Game(3, dealer=2, deck=Deck.stacked(draws))

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
        (RoundStarted(2), "Round 2 started"),
        (DiscardShuffled(2), "Discard pile reshuffled"),
        (CardDrawn(2, 0, Card(CardType.NUMBER, 4)), "You drew 4"),
        (ActionChosen(2, 1, Action(ActionType.STAY)), "Random bot chose stay"),
        (ActionChosen(2, 0, Action(ActionType.CHOOSE_TARGET, 2)), "You chose Threshold bot"),
        (
            RoundEnded(2, RoundResult(2, (0, 40, 0), (0, 40, 0), 1)),
            "Random bot got Flip 7!",
        ),
        (RoundEnded(2, RoundResult(2, (0, 0, 0), (0, 0, 0), None)), "Round 2 ended"),
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
    game = Game(3, dealer=2, deck=Deck.stacked(draws))

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


def play_first_round(
    monkeypatch: pytest.MonkeyPatch, rules: Rules
) -> tuple[GameScene, Game, pygame.Surface, list[str]]:
    """Everyone stays after the deal; returns the scene showing the round summary."""
    draws = [Card(CardType.NUMBER, n) for n in (5, 4, 3, 7, 8, 9)]
    game = Game(3, dealer=2, deck=Deck.stacked(draws), rules=rules)
    games = [game]

    def create_game(count: int) -> Game:
        return games.pop() if games else Game(count, seed=10)

    monkeypatch.setattr("flip_seven_bots.ui.game_scene.Game", create_game)
    monkeypatch.setattr("pygame.mouse.get_pos", lambda: (0, 0))
    for bot in ("RandomBot", "ThresholdBot"):
        monkeypatch.setattr(
            f"flip_seven_bots.ui.game_scene.{bot}.choose_action",
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
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s))
    scene.update(pygame.time.get_ticks() + 1000)
    scene.update(pygame.time.get_ticks() + 1000)
    texts.clear()
    scene.render(screen)
    assert "Round 1 complete" in texts
    assert "You:  +5    total 5" in texts
    texts.clear()
    return scene, game, screen, texts


@pytest.mark.usefixtures("pygame_fonts")
def test_continuing_after_round_summary_resumes_play(monkeypatch: pytest.MonkeyPatch) -> None:
    scene, game, screen, texts = play_first_round(monkeypatch, Rules())

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    scene.render(screen)
    assert not game.is_finished
    assert "Round 1 complete" not in texts


@pytest.mark.usefixtures("pygame_fonts")
def test_game_over_screen_and_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    scene, game, screen, texts = play_first_round(monkeypatch, Rules(target_score=1))

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    scene.render(screen)
    assert game.is_finished
    assert "Game over" in texts
    assert "Winner: You" in texts

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
    texts.clear()
    scene.render(screen)
    assert "Round 1 complete" not in texts
    assert "Game over" not in texts
