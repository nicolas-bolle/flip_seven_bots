from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pygame
import pytest

from flip_seven_bots.bots import ThresholdBot
from flip_seven_bots.game import (
    Action,
    ActionChosen,
    ActionType,
    Card,
    CardDrawn,
    CardType,
    ChooseTarget,
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
    VengeanceRules,
)
from flip_seven_bots.gui.common.text import card_label, event_text
from flip_seven_bots.gui.play.game_scene import (
    CARD_ANIMATION_MS,
    Button,
    Command,
    GameScene,
    _card_rects,
)
from flip_seven_bots.gui.play.table import Seat, Table

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
    animate_deal: bool = False,
) -> tuple[GameScene, Table]:
    """Seat 0 is dealt first and acts first; by default it is the only human and bots stay."""
    if seats is None:
        seats = [Seat("You")] + [
            Seat(f"Bot {i}", StayBot()) for i in range(1, player_count)
        ]
    table = Table(
        seats,
        new_game=lambda count, _seed: Game(
            count, dealer=count - 1, deck=Deck.stacked(draws), rules=rules
        ),
        bot_delay_ms=0,
    )
    scene = GameScene(table, report_dir=report_dir)
    if not animate_deal:
        finish_animations(scene)
    return scene, table


def numbers(*values: int) -> list[Card]:
    return [Card(CardType.NUMBER, value) for value in values]


def play_buttons(scene: GameScene) -> list[Button]:
    """The on-screen buttons other than the always-present bug report button."""
    return [b for b in scene.buttons() if b.action is not Command.REPORT_BUG]


def button(scene: GameScene, label: str) -> Button:
    return next(b for b in scene.buttons() if b.label.startswith(label))


def finish_animations(scene: GameScene) -> None:
    if scene._animating:
        scene.update(scene._now)
        scene.update(scene._now + CARD_ANIMATION_MS * len(scene._draws))


def click(scene: GameScene, target: Button) -> None:
    scene.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=target.rect.center)
    )
    finish_animations(scene)


def press(scene: GameScene, key: int) -> None:
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
    if not scene.dialog_open:
        finish_animations(scene)


def test_vengeance_cards_sort_into_number_and_modifier_rows_and_render() -> None:
    cards = [
        Card(CardType.NUMBER, 13),
        Card(CardType.ZERO),
        Card(CardType.UNLUCKY_SEVEN, 7),
        Card(CardType.LUCKY_THIRTEEN, 13),
        Card(CardType.SUBTRACT, 2),
        Card(CardType.SUBTRACT, 10),
        Card(CardType.DIVIDE, 2),
        *(
            Card(kind)
            for kind in (
                CardType.JUST_ONE_MORE,
                CardType.FLIP_FOUR,
                CardType.SWAP,
                CardType.STEAL,
                CardType.DISCARD,
            )
        ),
    ]
    rects = _card_rects(cards, pygame.Rect(30, 112, 895, 570))
    assert rects[1].left < rects[2].left < rects[0].left <= rects[3].left
    assert rects[5].left < rects[4].left and rects[4].top < rects[1].top
    scene, _ = make_scene(numbers(1, 2, 3))
    surface = pygame.Surface((1280, 900))
    for card, rect in zip(cards, rects):
        scene._draw_card(surface, card, rect)


@pytest.mark.parametrize("kind", [CardType.STEAL, CardType.DISCARD])
def test_vengeance_card_selection_uses_highlighted_cards(kind: CardType) -> None:
    scene, table = make_scene(numbers(9, 2, 4) + [Card(kind)], rules=VengeanceRules())
    press(scene, pygame.K_h)
    choices = play_buttons(scene)
    assert choices and all(
        isinstance(choice.action, Action)
        and choice.action.kind is ActionType.CHOOSE_CARD
        for choice in choices
    )
    scene.render(pygame.Surface((1280, 900)), choices[0].rect.center)
    choice = next(
        choice
        for choice in choices
        if isinstance(choice.action, Action) and choice.action.target == 1
    )
    assert isinstance(choice.action, Action) and choice.action.card_index is not None
    selected = table.observation.players[1].cards[choice.action.card_index]
    click(scene, choice)
    assert Card(kind) in table.observation.discard
    if kind is CardType.STEAL:
        assert selected in table.observation.players[0].cards
    else:
        assert selected in table.observation.discard


@pytest.mark.parametrize(
    "card",
    [
        Card(CardType.SUBTRACT, 4),
        Card(CardType.DIVIDE, 2),
        Card(CardType.JUST_ONE_MORE),
        Card(CardType.FLIP_FOUR),
    ],
)
def test_vengeance_targeted_cards_offer_player_buttons(card: Card) -> None:
    scene, table = make_scene(
        numbers(9, 2, 4) + [card] + numbers(5, 6, 7, 8, 10),
        rules=VengeanceRules(),
    )
    press(scene, pygame.K_h)
    assert isinstance(table.observation.decision, ChooseTarget)
    assert table.observation.decision.card == card
    scene.render(pygame.Surface((1280, 900)))
    press(scene, pygame.K_2)
    assert table.moves[-1].action == Action(ActionType.CHOOSE_TARGET, 1)


def test_swap_uses_two_card_clicks_and_blocks_selection_during_dialog() -> None:
    scene, table = make_scene(
        numbers(9, 2, 4) + [Card(CardType.SWAP)], rules=VengeanceRules()
    )
    press(scene, pygame.K_h)
    first = next(
        b
        for b in play_buttons(scene)
        if isinstance(b.action, Action) and b.action.target == 0
    )
    click(scene, first)
    assert scene._swap_first == (0, 0)
    assert all(
        isinstance(b.action, Action) and b.action.target != 0
        for b in play_buttons(scene)
    )
    scene.render(pygame.Surface((1280, 900)))
    second = next(
        b
        for b in play_buttons(scene)
        if isinstance(b.action, Action) and b.action.target == 1
    )
    press(scene, pygame.K_F1)
    click(scene, second)
    assert scene._swap_first == (0, 0)
    press(scene, pygame.K_ESCAPE)
    click(scene, second)
    assert scene._swap_first is None
    assert numbers(2)[0] in table.observation.players[0].cards
    assert numbers(9)[0] in table.observation.players[1].cards


@pytest.mark.parametrize("take_bonus", [True, False])
def test_brutal_flip_seven_can_take_or_subtract_the_bonus(
    take_bonus: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene, table = make_scene(
        numbers(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
        player_count=2,
        rules=VengeanceRules(brutal=True, target_score=1000),
    )
    for _ in range(6):
        press(scene, pygame.K_h)
        if table.human_to_act is None and table.round_summary is None:
            scene.update(scene._now)
    assert any(b.label.startswith("Take bonus") for b in play_buttons(scene))
    scene.render(pygame.Surface((1280, 900)))
    press(scene, pygame.K_b if take_bonus else pygame.K_2)
    assert table.round_summary is not None
    assert table.round_summary.scores[1] == (2 if take_bonus else -13)
    texts: list[str] = []
    monkeypatch.setattr(
        scene,
        "_text",
        lambda _screen, _font, text, _position, _color=None: texts.append(text),
    )
    scene.render(pygame.Surface((1280, 900)))
    assert any("Bot 1:  -13" in text for text in texts) is not take_bonus


@pytest.mark.parametrize("brutal", [False, True])
def test_vengeance_game_completes_through_scene(brutal: bool) -> None:
    table = Table(
        [Seat("Bot 1", ThresholdBot(25)), Seat("Bot 2", ThresholdBot(25))],
        seed=42,
        rules=VengeanceRules(brutal=brutal),
        bot_delay_ms=0,
    )
    scene = GameScene(table)
    for tick in range(10000):
        scene.update(tick * 100000)
        if table.round_summary is not None and not scene._animating:
            press(scene, pygame.K_RETURN)
        if (
            table.game.is_finished
            and table.round_summary is None
            and not scene._animating
        ):
            break
    assert table.game.is_finished


def test_buttons_offer_the_legal_actions_with_seat_names() -> None:
    scene, _ = make_scene(numbers(3, 1, 2) + [FREEZE])
    assert [b.label for b in play_buttons(scene)] == ["Hit  [H]", "Stay  [S]"]

    press(scene, pygame.K_h)
    assert [(b.label, b.shortcut) for b in play_buttons(scene)] == [
        ("You  [1]", pygame.K_1),
        ("Bot 1  [2]", pygame.K_2),
        ("Bot 2  [3]", pygame.K_3),
    ]


def test_clicking_buttons_hits_and_chooses_a_target() -> None:
    scene, table = make_scene(numbers(3, 1, 2) + [FREEZE])
    click(scene, button(scene, "Hit"))
    assert isinstance(table.observation.decision, ChooseTarget)
    assert table.observation.decision.card == FREEZE

    click(scene, button(scene, "Bot 2"))
    assert table.observation.players[2].status is PlayerStatus.STAYED
    assert FREEZE in table.observation.players[2].cards
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
    scene.update(scene._now)
    scene.update(scene._now)
    assert [b.label for b in play_buttons(scene)] == ["Continue  [Enter]"]
    scene.render(pygame.Surface((1280, 900)))

    press(scene, pygame.K_RETURN)
    assert table.round_summary is None


def test_play_again_restarts_finished_game() -> None:
    scene, table = make_scene(numbers(3, 1, 2), rules=Rules(target_score=1))
    press(scene, pygame.K_s)
    scene.update(scene._now)
    scene.update(scene._now)
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
        scene,
        "_text",
        lambda _screen, _font, text, _position, _color=None: texts.append(text),
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
    scene, table = make_scene(
        numbers(*range(1, player_count + 1)) + [FREEZE], player_count
    )
    press(scene, pygame.K_h)
    assert isinstance(table.observation.decision, ChooseTarget)
    assert table.observation.decision.card == FREEZE

    scene.render(pygame.Surface((1280, 900)), mouse_pos=(0, 0))
    screen = pygame.Rect(0, 0, 1280, 900)
    assert len(play_buttons(scene)) == player_count
    assert all(screen.contains(b.rect) for b in scene.buttons())


def test_large_hand_renders_in_smallest_panel() -> None:
    hand = numbers(*range(1, 7)) + [Card(CardType.SECOND_CHANCE), Card(CardType.ADD, 4)]
    scene, table = make_scene(
        hand[:1] + numbers(*range(1, 6)) + hand[1:], player_count=6
    )
    for _ in hand[1:]:
        press(scene, pygame.K_h)
        while table.human_to_act is None:
            scene.update(scene._now)

    assert len(table.observation.players[0].cards) == len(hand)
    scene.render(pygame.Surface((1280, 900)))


@pytest.mark.parametrize("player_count", [3, 6])
def test_non_number_cards_are_above_numbers(
    player_count: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene, table = make_scene(numbers(*range(1, player_count + 1)), player_count)
    player = table.observation.players[0]
    player = replace(
        player,
        cards=(
            Card(CardType.NUMBER, 1),
            Card(CardType.ADD, 4),
            Card(CardType.NUMBER, 2),
        ),
    )
    cards: list[tuple[Card, pygame.Rect]] = []
    monkeypatch.setattr(
        scene, "_draw_card", lambda _screen, card, rect: cards.append((card, rect))
    )
    panel = pygame.Rect(30, 112, 895, (582 // player_count) - 12)
    scene._draw_player(pygame.Surface((1280, 900)), player, panel, table.observation)

    modifier = next(rect for card, rect in cards if card.kind is CardType.ADD)
    number_rects = [rect for card, rect in cards if card.kind is CardType.NUMBER]
    assert all(modifier.bottom <= rect.top for rect in number_rects)
    assert all(panel.contains(rect) for _, rect in cards)


def test_hand_cards_are_sorted_within_each_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene, table = make_scene(numbers(3, 1, 2))
    hand = (
        Card(CardType.NUMBER, 12),
        Card(CardType.FLIP_THREE),
        Card(CardType.ADD, 10),
        Card(CardType.NUMBER, 2),
        Card(CardType.SECOND_CHANCE),
        Card(CardType.ADD, 2),
        Card(CardType.NUMBER, 0),
        Card(CardType.FREEZE),
        Card(CardType.MULTIPLY, 2),
    )
    player = replace(table.observation.players[0], cards=hand)
    drawn: list[tuple[Card, pygame.Rect]] = []
    monkeypatch.setattr(
        scene, "_draw_card", lambda _screen, card, rect: drawn.append((card, rect))
    )
    scene._draw_player(
        pygame.Surface((1280, 900)),
        player,
        pygame.Rect(30, 112, 895, 180),
        table.observation,
    )

    ordered = [
        card for card, _ in sorted(drawn, key=lambda item: (item[1].y, item[1].x))
    ]
    assert ordered == [
        Card(CardType.ADD, 2),
        Card(CardType.ADD, 10),
        Card(CardType.MULTIPLY, 2),
        Card(CardType.SECOND_CHANCE),
        Card(CardType.FREEZE),
        Card(CardType.FLIP_THREE),
        *numbers(0, 2, 12),
    ]


def test_live_score_uses_round_scoring_and_total_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene, table = make_scene(
        numbers(5) + [Card(CardType.ADD, 4), Card(CardType.MULTIPLY, 2)] + numbers(9),
        player_count=1,
    )
    press(scene, pygame.K_h)
    press(scene, pygame.K_h)
    texts: list[str] = []
    monkeypatch.setattr(
        scene,
        "_text",
        lambda _screen, _font, text, _position, _color=None: texts.append(text),
    )
    scene.render(pygame.Surface((1280, 900)))
    assert table.observation.players[0].round_score == 14
    assert "Total: 0    Live round: 14" in texts

    press(scene, pygame.K_s)
    press(scene, pygame.K_RETURN)
    texts.clear()
    scene.render(pygame.Surface((1280, 900)))
    assert "Total: 14    Live round: 9" in texts


def test_busted_hand_live_score_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    scene, table = make_scene(numbers(3, 2, 3), seats=[Seat("Ann"), Seat("Ben")])
    press(scene, pygame.K_h)
    texts: list[str] = []
    monkeypatch.setattr(
        scene,
        "_text",
        lambda _screen, _font, text, _position, _color=None: texts.append(text),
    )
    scene.render(pygame.Surface((1280, 900)))
    assert table.observation.players[0].status is PlayerStatus.BUSTED
    assert "Total: 0    Live round: 0" in texts


def test_sorted_number_cards_wrap_in_ascending_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene, table = make_scene(numbers(3, 1, 2))
    player = replace(
        table.observation.players[0], cards=tuple(numbers(*range(12, -1, -1)))
    )
    drawn: list[tuple[Card, pygame.Rect]] = []
    monkeypatch.setattr(
        scene, "_draw_card", lambda _screen, card, rect: drawn.append((card, rect))
    )
    scene._draw_player(
        pygame.Surface((1280, 900)),
        player,
        pygame.Rect(30, 112, 895, 180),
        table.observation,
    )
    ordered = [
        card.value for card, _ in sorted(drawn, key=lambda item: (item[1].y, item[1].x))
    ]
    assert ordered == list(range(13))
    assert len({rect.y for _, rect in drawn}) == 2


def test_animation_lands_at_new_cards_sorted_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene, table = make_scene(numbers(9, 1), player_count=1)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
    scene.update(scene._now)
    scene.update(scene._now + CARD_ANIMATION_MS - 1)
    frame = pygame.Surface((1280, 900), pygame.SRCALPHA)
    scene._draw_animation(frame, table.observation)
    arriving = frame.get_bounding_rect()
    scene.update(scene._now + 1)

    drawn: list[tuple[Card, pygame.Rect]] = []
    monkeypatch.setattr(
        scene, "_draw_card", lambda _screen, card, rect: drawn.append((card, rect))
    )
    scene._draw_player(
        pygame.Surface((1280, 900)),
        table.observation.players[0],
        pygame.Rect(30, 112, 895, 570),
        table.observation,
    )
    one = next(rect for card, rect in drawn if card.value == 1)
    nine = next(rect for card, rect in drawn if card.value == 9)
    assert one.x < nine.x
    assert abs(arriving.centerx - one.centerx) <= 1
    assert abs(arriving.centery - one.centery) <= 1


def test_deal_flips_and_moves_cards_before_revealing_their_hands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene, table = make_scene(numbers(3, 1, 2), animate_deal=True)
    scene.update(0)
    assert play_buttons(scene) == []
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
    assert table.moves == ()
    texts: list[str] = []
    monkeypatch.setattr(
        scene,
        "_text",
        lambda _screen, _font, text, _position, _color=None: texts.append(text),
    )
    scene.render(pygame.Surface((1280, 900)))
    assert "Total: 0    Live round: ..." in texts
    assert not any("drew" in text for text in texts)

    def frame() -> pygame.Rect:
        screen = pygame.Surface((1280, 900), pygame.SRCALPHA)
        scene._draw_animation(screen, table.observation)
        return screen.get_bounding_rect()

    start = frame()
    scene.update(150)
    moving = frame()
    assert moving.center != start.center
    assert moving.width < start.width

    drawn: list[Card] = []
    monkeypatch.setattr(
        scene, "_draw_card", lambda _screen, card, _rect: drawn.append(card)
    )
    scene.update(450)
    scene.render(pygame.Surface((1280, 900)))
    assert drawn == [Card(CardType.NUMBER, 3)]

    drawn.clear()
    scene.update(600)
    scene.render(pygame.Surface((1280, 900)))
    assert drawn == [Card(CardType.NUMBER, 3)]
    finish_animations(scene)
    assert [b.label for b in play_buttons(scene)] == ["Hit  [H]", "Stay  [S]"]


def test_flip_three_animates_each_draw_in_order() -> None:
    flip_three = Card(CardType.FLIP_THREE)
    scene, table = make_scene(
        numbers(1, 2) + [flip_three] + numbers(3, 4, 5),
        seats=[Seat("Ann"), Seat("Ben")],
    )
    press(scene, pygame.K_h)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
    assert [draw.event.card for draw in scene._draws] == numbers(3, 4, 5)
    assert play_buttons(scene) == []
    scene.update(scene._now)
    scene.update(scene._now + CARD_ANIMATION_MS)
    assert [draw.event.card for draw in scene._draws] == numbers(4, 5)
    assert table.observation.players[1].cards == (
        *numbers(2),
        flip_three,
        *numbers(3, 4, 5),
    )
    finish_animations(scene)
    assert play_buttons(scene)


def test_bot_delay_starts_after_deal_animation() -> None:
    table = Table(
        [Seat("Bot", StayBot())],
        new_game=lambda count, _seed: Game(count, deck=Deck.stacked(numbers(3, 4))),
    )
    scene = GameScene(table)
    scene.update(0)
    scene.update(CARD_ANIMATION_MS)
    scene.update(CARD_ANIMATION_MS)
    scene.update(CARD_ANIMATION_MS + 999)
    assert table.moves == ()
    scene.update(CARD_ANIMATION_MS + 1000)
    assert len(table.moves) == 1


def test_animations_do_not_hide_an_existing_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene, table = make_scene(numbers(3, 2, 3), seats=[Seat("Ann"), Seat("Ben")])
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
    drawn: list[Card] = []
    monkeypatch.setattr(
        scene, "_draw_card", lambda _screen, card, _rect: drawn.append(card)
    )
    player = table.observation.players[0]
    scene._draw_player(
        pygame.Surface((1280, 900)),
        player,
        pygame.Rect(30, 112, 895, 279),
        table.observation,
    )
    assert drawn == [Card(CardType.NUMBER, 3)]


def test_round_summary_waits_for_last_draw_then_next_deal_waits_for_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene, table = make_scene(numbers(0, 1, 2, 3, 4, 5, 6, 9), player_count=1)
    for _ in range(5):
        press(scene, pygame.K_h)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
    assert table.round_summary is not None
    assert [
        (draw.event.round_number, draw.event.card.value) for draw in scene._draws
    ] == [(1, 6), (2, 9)]
    assert play_buttons(scene) == []
    texts: list[str] = []
    monkeypatch.setattr(
        scene,
        "_text",
        lambda _screen, _font, text, _position, _color=None: texts.append(text),
    )
    scene.render(pygame.Surface((1280, 900)))
    assert any(text.startswith("Round 1  |") for text in texts)
    scene.update(scene._now)
    scene.update(scene._now + CARD_ANIMATION_MS)
    assert [b.label for b in play_buttons(scene)] == ["Continue  [Enter]"]

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert table.round_summary is None
    assert play_buttons(scene) == []
    finish_animations(scene)
    assert play_buttons(scene)


def test_bug_report_pauses_animation_without_skipping_it() -> None:
    scene, _ = make_scene(numbers(3), player_count=1, animate_deal=True)
    scene.update(0)
    scene.update(200)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1))
    scene.update(5_000)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    scene.update(5_399)
    assert play_buttons(scene) == []
    scene.update(5_400)
    assert play_buttons(scene)


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
def test_card_labels_show_values_signs_and_action_names(card: Card, label: str) -> None:
    assert card_label(card) == label


@pytest.mark.parametrize(
    ("event", "message"),
    [
        (RoundStarted(2), "Round 2 started"),
        (DiscardShuffled(2), "Discard pile reshuffled"),
        (CardDrawn(2, 0, Card(CardType.NUMBER, 4)), "You drew 4"),
        (ActionChosen(2, 1, Action(ActionType.STAY)), "Random bot chose stay"),
        (
            ActionChosen(2, 0, Action(ActionType.CHOOSE_TARGET, 2)),
            "You chose Threshold bot",
        ),
        (
            RoundEnded(2, RoundResult(2, (0, 40, 0), (0, 40, 0), 1)),
            "Random bot got Flip 7!",
        ),
        (RoundEnded(2, RoundResult(2, (0, 0, 0), (0, 0, 0), None)), "Round 2 ended"),
    ],
)
def test_events_are_described_with_seat_names(event: GameEvent, message: str) -> None:
    assert event_text(event, NAMES) == message
