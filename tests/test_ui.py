from collections.abc import Iterator
from pathlib import Path

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
    Observation,
    PlayerStatus,
    RoundEnded,
    RoundResult,
    RoundStarted,
    Rules,
)
from flip_seven_bots.ui.game_scene import Button, Command, GameScene
from flip_seven_bots.ui.table import Seat, Table
from flip_seven_bots.ui.text import card_label, event_text

NAMES = ("You", "Random bot", "Threshold bot")
FREEZE = Card(CardType.FREEZE)


@pytest.fixture(autouse=True)
def pygame_fonts() -> Iterator[None]:
    was_initialized = pygame.font.get_init()
    pygame.font.init()
    yield
    if not was_initialized:
        pygame.font.quit()


class StayBot:
    def choose_action(self, observation: Observation) -> Action:
        return Action(ActionType.STAY)


def make_scene(
    draws: list[Card],
    player_count: int = 3,
    rules: Rules | None = None,
    seats: list[Seat] | None = None,
    report_dir: Path = Path("unused-bug-reports"),
) -> tuple[GameScene, Table]:
    """Seat 0 is dealt first and acts first; by default it is the only human and bots stay."""
    if seats is None:
        seats = [Seat("You")] + [Seat(f"Bot {i}", StayBot()) for i in range(1, player_count)]
    table = Table(
        seats,
        new_game=lambda count, _seed: Game(
            count, dealer=count - 1, deck=Deck.stacked(draws), rules=rules
        ),
        bot_delay_ms=0,
    )
    return GameScene(table, report_dir=report_dir), table


def numbers(*values: int) -> list[Card]:
    return [Card(CardType.NUMBER, value) for value in values]


def play_buttons(scene: GameScene) -> list[Button]:
    """The on-screen buttons other than the always-present bug report button."""
    return [b for b in scene.buttons() if b.action is not Command.REPORT_BUG]


def button(scene: GameScene, label: str) -> Button:
    return next(b for b in scene.buttons() if b.label.startswith(label))


def click(scene: GameScene, target: Button) -> None:
    scene.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=target.rect.center)
    )


def press(scene: GameScene, key: int) -> None:
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_buttons_offer_the_legal_actions_with_seat_names() -> None:
    scene, _ = make_scene(numbers(3, 1, 2) + [FREEZE])
    assert [b.label for b in play_buttons(scene)] == ["Hit  [H]", "Stay  [S]"]

    press(scene, pygame.K_h)
    assert [(b.label, b.shortcut) for b in play_buttons(scene)] == [
        ("You  [1]", pygame.K_1), ("Bot 1  [2]", pygame.K_2), ("Bot 2  [3]", pygame.K_3),
    ]


def test_clicking_buttons_hits_and_chooses_a_target() -> None:
    scene, table = make_scene(numbers(3, 1, 2) + [FREEZE])
    click(scene, button(scene, "Hit"))
    assert table.observation.pending_card == FREEZE

    click(scene, button(scene, "Bot 2"))
    assert table.observation.players[2].status is PlayerStatus.STAYED
    assert play_buttons(scene) == []


def test_shortcut_keys_hit_and_choose_a_target() -> None:
    scene, table = make_scene(numbers(3, 1, 2) + [FREEZE])
    press(scene, pygame.K_h)
    press(scene, pygame.K_3)
    assert table.observation.players[2].status is PlayerStatus.STAYED


def test_input_away_from_buttons_is_ignored() -> None:
    scene, table = make_scene(numbers(3, 1, 2))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5)))
    press(scene, pygame.K_x)
    assert table.human_to_act == 0
    assert table.observation.events[-1] == CardDrawn(1, 2, Card(CardType.NUMBER, 2))


def test_continue_dismisses_round_summary() -> None:
    scene, table = make_scene(numbers(3, 1, 2, 7, 8, 9))
    press(scene, pygame.K_s)
    scene.update(0)
    scene.update(0)
    assert [b.label for b in play_buttons(scene)] == ["Continue  [Enter]"]
    scene.render(pygame.Surface((1280, 900)))

    press(scene, pygame.K_RETURN)
    assert table.round_summary is None


def test_play_again_restarts_finished_game() -> None:
    scene, table = make_scene(numbers(3, 1, 2), rules=Rules(target_score=1))
    press(scene, pygame.K_s)
    scene.update(0)
    scene.update(0)
    press(scene, pygame.K_RETURN)
    finished = table.game
    assert [b.label for b in play_buttons(scene)] == ["Play again  [R]"]
    scene.render(pygame.Surface((1280, 900)))

    press(scene, pygame.K_r)
    assert table.game is not finished


def test_humans_take_turns_and_are_named_in_the_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seats = [Seat("Ann"), Seat("Ben"), Seat("Bot", StayBot())]
    scene, table = make_scene(numbers(3, 1, 2), seats=seats)
    texts: list[str] = []
    monkeypatch.setattr(
        scene, "_text", lambda _screen, _font, text, _position, _color=None: texts.append(text)
    )

    scene.render(pygame.Surface((1280, 900)))
    assert "Ann's turn: hit or stay" in texts
    press(scene, pygame.K_s)

    texts.clear()
    scene.render(pygame.Surface((1280, 900)))
    assert table.human_to_act == 1
    assert "Ben's turn: hit or stay" in texts
    press(scene, pygame.K_s)
    assert table.human_to_act is None
    assert play_buttons(scene) == []


@pytest.mark.parametrize("player_count", range(1, 7))
def test_target_buttons_fit_on_screen_for_any_player_count(player_count: int) -> None:
    scene, table = make_scene(numbers(*range(1, player_count + 1)) + [FREEZE], player_count)
    press(scene, pygame.K_h)
    assert table.observation.pending_card == FREEZE

    scene.render(pygame.Surface((1280, 900)), mouse_pos=(0, 0))
    screen = pygame.Rect(0, 0, 1280, 900)
    assert len(play_buttons(scene)) == player_count
    assert all(screen.contains(b.rect) for b in scene.buttons())


def test_large_hand_renders_in_smallest_panel() -> None:
    hand = numbers(*range(1, 7)) + [Card(CardType.SECOND_CHANCE), Card(CardType.ADD, 4)]
    scene, table = make_scene(hand[:1] + numbers(*range(1, 6)) + hand[1:], player_count=6)
    for _ in hand[1:]:
        press(scene, pygame.K_h)
        while table.human_to_act is None:
            scene.update(0)

    assert len(table.observation.players[0].cards) == len(hand)
    scene.render(pygame.Surface((1280, 900)))


def type_text(scene: GameScene, text: str) -> None:
    scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=text))


def test_bug_report_dialog_saves_message_and_resumes_play(tmp_path: Path) -> None:
    scene, table = make_scene(numbers(3, 1, 2), report_dir=tmp_path)
    press(scene, pygame.K_s)
    press(scene, pygame.K_F1)
    assert scene.dialog_open

    scene.update(10_000)
    assert table.game.current_player == 1  # bots wait while the dialog is open
    type_text(scene, "Bot skippedd")
    press(scene, pygame.K_BACKSPACE)
    scene.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=pygame.KMOD_LSHIFT)
    )
    type_text(scene, "its turn")
    scene.render(pygame.Surface((1280, 900)))
    press(scene, pygame.K_RETURN)

    [report] = tmp_path.iterdir()
    assert "Bot skipped\nits turn" in report.read_text()
    assert not scene.dialog_open
    assert scene.notice == f"Bug report saved to {report}"
    scene.update(10_000)
    assert table.game.current_player == 2


def test_typing_in_the_dialog_does_not_trigger_game_shortcuts(tmp_path: Path) -> None:
    scene, table = make_scene(numbers(3, 1, 2), report_dir=tmp_path)
    press(scene, pygame.K_F1)
    press(scene, pygame.K_h)
    type_text(scene, "h")
    assert table.moves == ()


def test_empty_bug_report_is_not_saved(tmp_path: Path) -> None:
    scene, _ = make_scene(numbers(3, 1, 2), report_dir=tmp_path)
    press(scene, pygame.K_F1)
    type_text(scene, "   ")
    press(scene, pygame.K_RETURN)
    assert scene.dialog_open
    assert list(tmp_path.iterdir()) == []


def test_cancelling_the_dialog_saves_nothing(tmp_path: Path) -> None:
    scene, table = make_scene(numbers(3, 1, 2), report_dir=tmp_path)
    click(scene, button(scene, "Report bug"))
    type_text(scene, "never mind")
    press(scene, pygame.K_ESCAPE)
    assert not scene.dialog_open
    assert not table.paused
    assert list(tmp_path.iterdir()) == []


def test_save_failure_keeps_the_dialog_open(tmp_path: Path) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")
    scene, _ = make_scene(numbers(3, 1, 2), report_dir=blocked)
    press(scene, pygame.K_F1)
    type_text(scene, "help")
    press(scene, pygame.K_RETURN)
    assert scene.dialog_open


def test_long_report_messages_wrap_in_the_dialog() -> None:
    scene, _ = make_scene(numbers(3, 1, 2))
    press(scene, pygame.K_F1)
    type_text(scene, "word " * 400 + "x" * 300)
    scene.render(pygame.Surface((1280, 900)))


@pytest.mark.parametrize(
    ("card", "label"),
    [
        (Card(CardType.NUMBER, 12), "12"),
        (Card(CardType.ADD, 6), "+6"),
        (Card(CardType.MULTIPLY, 2), "x2"),
        (FREEZE, "FREEZE"),
        (Card(CardType.FLIP_THREE), "FLIP 3"),
        (Card(CardType.SECOND_CHANCE), "SECOND CHANCE"),
    ],
)
def test_card_labels(card: Card, label: str) -> None:
    assert card_label(card) == label


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
    assert event_text(event, NAMES) == message
