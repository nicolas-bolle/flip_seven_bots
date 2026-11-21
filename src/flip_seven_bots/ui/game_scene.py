"""A playable table for one human and two bots."""

from dataclasses import dataclass

import pygame

from flip_seven_bots.bots import Bot, RandomBot, ThresholdBot
from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    EventType,
    Game,
    GameEvent,
    Observation,
    PlayerStatus,
)
from flip_seven_bots.game.model import PlayerView, RoundResult

HUMAN = 0
NAMES = ("You", "Random bot", "Threshold bot")
BOT_DELAY_MS = 700

BACKGROUND = (15, 30, 35)
PANEL = (28, 52, 55)
PANEL_ALT = (34, 62, 63)
TEXT = (240, 244, 229)
MUTED = (174, 193, 184)
ACCENT = (233, 196, 106)
ACTIVE = (113, 207, 165)
BUTTON = (53, 109, 91)
BUTTON_HOVER = (67, 139, 112)


@dataclass(frozen=True)
class _Button:
    rect: pygame.Rect
    label: str
    action: Action | None = None
    command: str | None = None
    shortcut: int | None = None


def _card_label(card: Card) -> str:
    match card.kind:
        case CardType.NUMBER:
            return str(card.value)
        case CardType.ADD:
            return f"+{card.value}"
        case CardType.MULTIPLY:
            return f"x{card.value}"
        case CardType.FREEZE:
            return "FREEZE"
        case CardType.FLIP_THREE:
            return "FLIP 3"
        case CardType.SECOND_CHANCE:
            return "SECOND CHANCE"
    raise ValueError(f"unknown card type: {card.kind}")


def _event_text(event: GameEvent) -> str:
    if event.kind is EventType.ROUND_STARTED:
        return f"Round {event.round_number} started"
    if event.kind is EventType.DISCARD_SHUFFLED:
        return "Discard pile reshuffled"
    if event.kind is EventType.ROUND_ENDED:
        if event.result is not None and event.result.flip_seven_player is not None:
            return f"{NAMES[event.result.flip_seven_player]} got Flip 7!"
        return f"Round {event.round_number} ended"
    if event.player is None:
        raise ValueError(f"event is missing a player: {event}")
    name = NAMES[event.player]
    if event.kind is EventType.CARD_DRAWN:
        if event.card is None:
            raise ValueError("card-drawn event is missing its card")
        return f"{name} drew {_card_label(event.card)}"
    if event.kind is EventType.ACTION_CHOSEN:
        if event.action is None:
            raise ValueError("action event is missing its action")
        if event.action.kind is ActionType.CHOOSE_TARGET:
            if event.action.target is None:
                raise ValueError("target action is missing its target")
            return f"{name} chose {NAMES[event.action.target]}"
        return f"{name} chose {event.action.kind.name.lower()}"
    raise ValueError(f"unknown event type: {event.kind}")


class GameScene:
    def __init__(self) -> None:
        self._title_font = pygame.font.Font(None, 42)
        self._heading_font = pygame.font.Font(None, 30)
        self._font = pygame.font.Font(None, 25)
        self._small_font = pygame.font.Font(None, 21)
        self._card_font = pygame.font.Font(None, 25)
        self._buttons: list[_Button] = []
        self._new_game()

    def _new_game(self) -> None:
        self._game = Game(len(NAMES))
        self._bots: dict[int, Bot] = {1: RandomBot(), 2: ThresholdBot(30)}
        self._shown_round = 0
        self._round_summary: RoundResult | None = None
        self._bot_at = pygame.time.get_ticks() + BOT_DELAY_MS
        self._check_round_summary()

    def _check_round_summary(self) -> None:
        result = self._game.observe(HUMAN).last_round
        if result is not None and result.round_number > self._shown_round:
            self._shown_round = result.round_number
            self._round_summary = result

    def _apply(self, action: Action) -> None:
        self._game.apply(action)
        self._check_round_summary()
        self._bot_at = pygame.time.get_ticks() + BOT_DELAY_MS

    def handle_event(self, event: pygame.event.Event) -> None:
        button: _Button | None = None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            button = next((b for b in self._buttons if b.rect.collidepoint(event.pos)), None)
        elif event.type == pygame.KEYDOWN:
            button = next((b for b in self._buttons if b.shortcut == event.key), None)

        if button is None:
            return
        if button.command == "continue":
            self._round_summary = None
            self._bot_at = pygame.time.get_ticks() + BOT_DELAY_MS
        elif button.command == "restart":
            self._new_game()
        elif button.action is not None:
            observation = self._game.observe(HUMAN)
            if button.action in observation.legal_actions and self._round_summary is None:
                self._apply(button.action)
        self._buttons = []

    def update(self, now: int) -> None:
        if self._round_summary is not None or self._game.is_finished:
            return
        player = self._game.current_player
        if player is None:
            raise RuntimeError("unfinished game has no player awaiting a decision")
        if player != HUMAN and now >= self._bot_at:
            observation = self._game.observe(player)
            self._apply(self._bots[player].choose_action(observation))

    def render(self, screen: pygame.Surface) -> None:
        observation = self._game.observe(HUMAN)
        self._buttons = []
        screen.fill(BACKGROUND)
        self._text(screen, self._title_font, "FLIP 7", (35, 24), ACCENT)
        self._text(
            screen,
            self._font,
            f"Round {observation.round_number}  |  Dealer: {NAMES[observation.dealer]}"
            f"  |  Deck: {observation.cards_remaining}  |  Discard: {observation.discard_count}",
            (35, 69),
            MUTED,
        )

        for index, player in enumerate(observation.players):
            rect = pygame.Rect(30, 112 + index * 190, 895, 178)
            self._draw_player(screen, player, rect, observation)
        self._draw_activity(screen, observation)
        self._draw_controls(screen, observation)

        if self._round_summary is not None:
            self._draw_round_summary(screen, self._round_summary)
        elif self._game.is_finished:
            self._draw_game_over(screen, observation)

        for button in self._buttons:
            self._draw_button(screen, button)

    @staticmethod
    def _text(
        screen: pygame.Surface,
        font: pygame.font.Font,
        text: str,
        position: tuple[int, int],
        color: tuple[int, int, int] = TEXT,
    ) -> None:
        screen.blit(font.render(text, True, color), position)

    def _draw_player(
        self,
        screen: pygame.Surface,
        player: PlayerView,
        rect: pygame.Rect,
        observation: Observation,
    ) -> None:
        color = PANEL_ALT if player.player == HUMAN else PANEL
        pygame.draw.rect(screen, color, rect, border_radius=12)
        if player.player == observation.current_player:
            pygame.draw.rect(screen, ACTIVE, rect, width=2, border_radius=12)

        status = {
            PlayerStatus.ACTIVE: "ACTIVE",
            PlayerStatus.STAYED: "STAYED",
            PlayerStatus.BUSTED: "BUSTED",
        }[player.status]
        self._text(screen, self._heading_font, NAMES[player.player], (rect.x + 16, rect.y + 13))
        self._text(screen, self._small_font, status, (rect.x + 200, rect.y + 19), ACCENT)
        score = f"Round: {player.round_score}    Total: {player.total_score}"
        self._text(screen, self._font, score, (rect.x + 570, rect.y + 16))

        if not player.cards:
            self._text(screen, self._small_font, "No cards yet", (rect.x + 18, rect.y + 63), MUTED)
            return

        # Cards wrap to a second row, with overlapping cards if a hand grows unusually large.
        columns = min(12, max(1, (len(player.cards) + 1) // 2))
        rows = (len(player.cards) + columns - 1) // columns
        spacing_y = min(57, 110 // max(1, rows))
        for index, card in enumerate(player.cards):
            x = rect.x + 16 + (index % columns) * 70
            y = rect.y + 50 + (index // columns) * spacing_y
            self._draw_card(screen, card, pygame.Rect(x, y, 62, 51))

    def _draw_card(self, screen: pygame.Surface, card: Card, rect: pygame.Rect) -> None:
        if card.kind is CardType.NUMBER:
            color = (232, 224, 193)
        elif card.kind in (CardType.ADD, CardType.MULTIPLY):
            color = (236, 195, 106)
        else:
            color = (147, 205, 196)
        pygame.draw.rect(screen, color, rect, border_radius=6)
        if card.kind is CardType.SECOND_CHANCE:
            for index, line in enumerate(("SECOND", "CHANCE")):
                label = self._small_font.render(line, True, (25, 45, 46))
                center = (rect.centerx, rect.y + 16 + index * 19)
                screen.blit(label, label.get_rect(center=center))
        else:
            label = self._card_font.render(_card_label(card), True, (25, 45, 46))
            screen.blit(label, label.get_rect(center=rect.center))

    def _draw_activity(self, screen: pygame.Surface, observation: Observation) -> None:
        rect = pygame.Rect(945, 112, 305, 558)
        pygame.draw.rect(screen, PANEL, rect, border_radius=12)
        self._text(screen, self._heading_font, "Recent activity", (rect.x + 16, rect.y + 16))
        events = observation.events[-18:]
        for index, event in enumerate(events):
            position = (rect.x + 16, rect.y + 54 + index * 26)
            self._text(screen, self._small_font, _event_text(event), position, MUTED)
        if observation.last_round is not None:
            result = observation.last_round
            self._text(
                screen, self._small_font, f"Last round: {result.round_number}",
                (rect.x + 16, rect.bottom - 34), ACCENT,
            )

    def _draw_controls(self, screen: pygame.Surface, observation: Observation) -> None:
        rect = pygame.Rect(30, 700, 1220, 170)
        pygame.draw.rect(screen, PANEL, rect, border_radius=12)
        if self._game.is_finished:
            message = "Game over"
        elif observation.current_player != HUMAN:
            if observation.current_player is None:
                raise RuntimeError("unfinished game has no player awaiting a decision")
            message = f"{NAMES[observation.current_player]} is deciding..."
        elif observation.pending_card is not None:
            message = f"Choose a player for {_card_label(observation.pending_card)}"
        else:
            message = "Your turn: hit or stay"
        self._text(screen, self._heading_font, message, (rect.x + 20, rect.y + 18))
        self._text(
            screen, self._small_font, "Click a button or use its shortcut. Esc quits.",
            (rect.x + 20, rect.y + 52), MUTED,
        )

        if self._round_summary is not None or self._game.is_finished:
            return
        for index, action in enumerate(observation.legal_actions):
            if action.kind is ActionType.HIT:
                label, shortcut = "Hit  [H]", pygame.K_h
            elif action.kind is ActionType.STAY:
                label, shortcut = "Stay  [S]", pygame.K_s
            elif action.target is not None:
                label = f"{NAMES[action.target]}  [{action.target + 1}]"
                shortcut = (pygame.K_1, pygame.K_2, pygame.K_3)[action.target]
            else:
                raise ValueError(f"target action is missing its target: {action}")
            self._buttons.append(
                _Button(
                    pygame.Rect(rect.x + 20 + index * 210, rect.y + 85, 195, 55),
                    label, action, shortcut=shortcut,
                )
            )

    def _overlay(self, screen: pygame.Surface, title: str) -> pygame.Rect:
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 180))
        screen.blit(shade, (0, 0))
        rect = pygame.Rect(360, 240, 560, 400)
        pygame.draw.rect(screen, PANEL_ALT, rect, border_radius=15)
        self._text(screen, self._title_font, title, (rect.x + 28, rect.y + 25), ACCENT)
        return rect

    def _draw_round_summary(self, screen: pygame.Surface, result: RoundResult) -> None:
        rect = self._overlay(screen, f"Round {result.round_number} complete")
        if result.flip_seven_player is not None:
            message = f"{NAMES[result.flip_seven_player]} earned the Flip 7 bonus!"
            self._text(screen, self._font, message, (rect.x + 28, rect.y + 75), ACTIVE)
        for index, (score, total) in enumerate(zip(result.scores, result.totals)):
            self._text(
                screen, self._heading_font,
                f"{NAMES[index]}:  +{score}    total {total}",
                (rect.x + 28, rect.y + 120 + index * 45),
            )
        self._buttons.append(
            _Button(
                pygame.Rect(rect.x + 28, rect.bottom - 76, 195, 50),
                "Continue  [Enter]", command="continue", shortcut=pygame.K_RETURN,
            )
        )

    def _draw_game_over(self, screen: pygame.Surface, observation: Observation) -> None:
        rect = self._overlay(screen, "Game over")
        winners = ", ".join(NAMES[index] for index in observation.winners)
        self._text(screen, self._heading_font, f"Winner: {winners}", (rect.x + 28, rect.y + 90), ACTIVE)
        for index, player in enumerate(observation.players):
            self._text(
                screen, self._font, f"{NAMES[index]}: {player.total_score} points",
                (rect.x + 28, rect.y + 145 + index * 35),
            )
        self._buttons.append(
            _Button(
                pygame.Rect(rect.x + 28, rect.bottom - 76, 195, 50),
                "Play again  [R]", command="restart", shortcut=pygame.K_r,
            )
        )

    def _draw_button(self, screen: pygame.Surface, button: _Button) -> None:
        color = BUTTON_HOVER if button.rect.collidepoint(pygame.mouse.get_pos()) else BUTTON
        pygame.draw.rect(screen, color, button.rect, border_radius=8)
        text = self._font.render(button.label, True, TEXT)
        screen.blit(text, text.get_rect(center=button.rect.center))
