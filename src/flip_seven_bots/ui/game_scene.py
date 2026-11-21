"""A playable table for one human and any number of bots."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto

import pygame

from flip_seven_bots.bots import RandomBot, ThresholdBot
from flip_seven_bots.game import (
    Action,
    ActionChosen,
    ActionType,
    Card,
    CardDrawn,
    CardType,
    DiscardShuffled,
    GameEvent,
    Observation,
    PlayerStatus,
    PlayerView,
    RoundEnded,
    RoundResult,
    RoundStarted,
)

from .table import Seat, Table

BACKGROUND = (15, 30, 35)
PANEL = (28, 52, 55)
PANEL_ALT = (34, 62, 63)
TEXT = (240, 244, 229)
MUTED = (174, 193, 184)
ACCENT = (233, 196, 106)
ACTIVE = (113, 207, 165)
BUTTON = (53, 109, 91)
BUTTON_HOVER = (67, 139, 112)

PLAYER_AREA = pygame.Rect(30, 112, 895, 570)
PANEL_GAP = 12
CONTROLS = pygame.Rect(30, 700, 1220, 170)
OVERLAY = pygame.Rect(360, 240, 560, 400)


def default_seats() -> list[Seat]:
    return [
        Seat("You"),
        Seat("Random bot", RandomBot()),
        Seat("Threshold bot", ThresholdBot(30)),
    ]


class Command(Enum):
    CONTINUE = auto()
    RESTART = auto()


@dataclass(frozen=True)
class Button:
    rect: pygame.Rect
    label: str
    action: Action | Command
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


def _event_text(event: GameEvent, names: Sequence[str]) -> str:
    match event:
        case RoundStarted(round_number=round_number):
            return f"Round {round_number} started"
        case DiscardShuffled():
            return "Discard pile reshuffled"
        case RoundEnded(result=result):
            if result.flip_seven_player is not None:
                return f"{names[result.flip_seven_player]} got Flip 7!"
            return f"Round {result.round_number} ended"
        case CardDrawn(player=player, card=card):
            return f"{names[player]} drew {_card_label(card)}"
        case ActionChosen(player=player, action=action):
            if action.target is not None:
                return f"{names[player]} chose {names[action.target]}"
            return f"{names[player]} chose {action.kind.name.lower()}"


def _player_rects(count: int) -> list[pygame.Rect]:
    height = (PLAYER_AREA.height + PANEL_GAP) // count - PANEL_GAP
    return [
        pygame.Rect(PLAYER_AREA.x, PLAYER_AREA.y + index * (height + PANEL_GAP),
                    PLAYER_AREA.width, height)
        for index in range(count)
    ]


def _action_button(action: Action, names: Sequence[str], rect: pygame.Rect) -> Button:
    match action:
        case Action(kind=ActionType.HIT):
            return Button(rect, "Hit  [H]", action, pygame.K_h)
        case Action(kind=ActionType.STAY):
            return Button(rect, "Stay  [S]", action, pygame.K_s)
        case Action(target=int(target)) if target < 9:
            return Button(rect, f"{names[target]}  [{target + 1}]", action, pygame.K_1 + target)
        case Action(target=int(target)):
            return Button(rect, names[target], action)
    raise ValueError(f"unsupported action: {action}")


class GameScene:
    def __init__(self, table: Table | None = None) -> None:
        self._table = table if table is not None else Table(default_seats())
        self._title_font = pygame.font.Font(None, 42)
        self._heading_font = pygame.font.Font(None, 30)
        self._font = pygame.font.Font(None, 25)
        self._small_font = pygame.font.Font(None, 21)
        self._card_font = pygame.font.Font(None, 25)

    def buttons(self) -> tuple[Button, ...]:
        """The buttons currently on screen, derived from the table's state."""
        table = self._table
        corner = pygame.Rect(OVERLAY.x + 28, OVERLAY.bottom - 76, 195, 50)
        if table.round_summary is not None:
            return (Button(corner, "Continue  [Enter]", Command.CONTINUE, pygame.K_RETURN),)
        if table.game.is_finished:
            return (Button(corner, "Play again  [R]", Command.RESTART, pygame.K_r),)
        if not table.awaiting_human:
            return ()
        actions = table.observation.legal_actions
        gap = 15
        width = min(195, (CONTROLS.width - 40 - gap * (len(actions) - 1)) // len(actions))
        return tuple(
            _action_button(
                action,
                table.names,
                pygame.Rect(CONTROLS.x + 20 + index * (width + gap), CONTROLS.y + 85, width, 55),
            )
            for index, action in enumerate(actions)
        )

    def handle_event(self, event: pygame.event.Event) -> None:
        buttons = self.buttons()
        button: Button | None = None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            button = next((b for b in buttons if b.rect.collidepoint(event.pos)), None)
        elif event.type == pygame.KEYDOWN:
            button = next((b for b in buttons if b.shortcut == event.key), None)

        match button:
            case None:
                pass
            case Button(action=Command.CONTINUE):
                self._table.dismiss_summary()
            case Button(action=Command.RESTART):
                self._table.restart()
            case Button(action=Action() as action):
                self._table.choose(action)

    def update(self, now: int) -> None:
        self._table.update(now)

    def render(self, screen: pygame.Surface, mouse_pos: tuple[int, int] | None = None) -> None:
        table = self._table
        observation = table.observation
        screen.fill(BACKGROUND)
        self._text(screen, self._title_font, "FLIP 7", (35, 24), ACCENT)
        self._text(
            screen,
            self._font,
            f"Round {observation.round_number}  |  Dealer: {table.names[observation.dealer]}"
            f"  |  Deck: {observation.cards_remaining}  |  Discard: {len(observation.discard)}",
            (35, 69),
            MUTED,
        )

        for player, rect in zip(observation.players, _player_rects(len(observation.players))):
            self._draw_player(screen, player, rect, observation)
        self._draw_activity(screen, observation)
        self._draw_controls(screen, observation)

        if table.round_summary is not None:
            self._draw_round_summary(screen, table.round_summary)
        elif table.game.is_finished:
            self._draw_game_over(screen, observation)

        for button in self.buttons():
            self._draw_button(screen, button, mouse_pos)

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
        color = PANEL_ALT if player.player == self._table.human else PANEL
        pygame.draw.rect(screen, color, rect, border_radius=12)
        if player.player == observation.current_player:
            pygame.draw.rect(screen, ACTIVE, rect, width=2, border_radius=12)

        status = {
            PlayerStatus.ACTIVE: "ACTIVE",
            PlayerStatus.STAYED: "STAYED",
            PlayerStatus.BUSTED: "BUSTED",
        }[player.status]
        name = self._table.names[player.player]
        self._text(screen, self._heading_font, name, (rect.x + 16, rect.y + 13))
        self._text(screen, self._small_font, status, (rect.x + 200, rect.y + 19), ACCENT)
        score = f"Round: {player.round_score}    Total: {player.total_score}"
        self._text(screen, self._font, score, (rect.x + 570, rect.y + 16))

        if not player.cards:
            self._text(screen, self._small_font, "No cards yet", (rect.x + 18, rect.y + 50), MUTED)
            return

        # Up to 12 cards per row; extra rows overlap if a hand outgrows its panel.
        card_height = max(24, min(51, rect.height - 58))
        available = rect.height - 58 - card_height
        columns = 12
        rows = (len(player.cards) + columns - 1) // columns
        spacing_y = min(card_height + 6, available // (rows - 1)) if rows > 1 else 0
        for index, card in enumerate(player.cards):
            x = rect.x + 16 + (index % columns) * 70
            y = rect.y + 50 + (index // columns) * spacing_y
            self._draw_card(screen, card, pygame.Rect(x, y, 62, card_height))

    def _draw_card(self, screen: pygame.Surface, card: Card, rect: pygame.Rect) -> None:
        if card.kind is CardType.NUMBER:
            color = (232, 224, 193)
        elif card.kind in (CardType.ADD, CardType.MULTIPLY):
            color = (236, 195, 106)
        else:
            color = (147, 205, 196)
        pygame.draw.rect(screen, color, rect, border_radius=6)
        if card.kind is CardType.SECOND_CHANCE and rect.height >= 40:
            for index, line in enumerate(("SECOND", "CHANCE")):
                label = self._small_font.render(line, True, (25, 45, 46))
                center = (rect.centerx, rect.centery - 9 + index * 19)
                screen.blit(label, label.get_rect(center=center))
        else:
            text = "2ND CH." if card.kind is CardType.SECOND_CHANCE else _card_label(card)
            label = self._card_font.render(text, True, (25, 45, 46))
            if label.get_width() > rect.width - 6:
                label = self._small_font.render(text, True, (25, 45, 46))
            screen.blit(label, label.get_rect(center=rect.center))

    def _draw_activity(self, screen: pygame.Surface, observation: Observation) -> None:
        rect = pygame.Rect(945, 112, 305, 558)
        pygame.draw.rect(screen, PANEL, rect, border_radius=12)
        self._text(screen, self._heading_font, "Recent activity", (rect.x + 16, rect.y + 16))
        for index, event in enumerate(observation.events[-18:]):
            position = (rect.x + 16, rect.y + 54 + index * 26)
            self._text(
                screen, self._small_font, _event_text(event, self._table.names), position, MUTED
            )
        if observation.last_round is not None:
            self._text(
                screen, self._small_font, f"Last round: {observation.last_round.round_number}",
                (rect.x + 16, rect.bottom - 34), ACCENT,
            )

    def _draw_controls(self, screen: pygame.Surface, observation: Observation) -> None:
        pygame.draw.rect(screen, PANEL, CONTROLS, border_radius=12)
        if self._table.game.is_finished:
            message = "Game over"
        elif observation.current_player != self._table.human:
            assert observation.current_player is not None  # unfinished games await a decision
            message = f"{self._table.names[observation.current_player]} is deciding..."
        elif observation.pending_card is not None:
            message = f"Choose a player for {_card_label(observation.pending_card)}"
        else:
            message = "Your turn: hit or stay"
        self._text(screen, self._heading_font, message, (CONTROLS.x + 20, CONTROLS.y + 18))
        self._text(
            screen, self._small_font, "Click a button or use its shortcut. Esc quits.",
            (CONTROLS.x + 20, CONTROLS.y + 52), MUTED,
        )

    def _overlay(self, screen: pygame.Surface, title: str) -> pygame.Rect:
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 180))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, PANEL_ALT, OVERLAY, border_radius=15)
        self._text(screen, self._title_font, title, (OVERLAY.x + 28, OVERLAY.y + 25), ACCENT)
        return OVERLAY

    def _draw_round_summary(self, screen: pygame.Surface, result: RoundResult) -> None:
        rect = self._overlay(screen, f"Round {result.round_number} complete")
        names = self._table.names
        if result.flip_seven_player is not None:
            message = f"{names[result.flip_seven_player]} earned the Flip 7 bonus!"
            self._text(screen, self._font, message, (rect.x + 28, rect.y + 75), ACTIVE)
        spacing = min(45, 190 // len(names))
        for index, (score, total) in enumerate(zip(result.scores, result.totals)):
            self._text(
                screen, self._heading_font, f"{names[index]}:  +{score}    total {total}",
                (rect.x + 28, rect.y + 120 + index * spacing),
            )

    def _draw_game_over(self, screen: pygame.Surface, observation: Observation) -> None:
        rect = self._overlay(screen, "Game over")
        names = self._table.names
        winners = ", ".join(names[index] for index in observation.winners)
        self._text(
            screen, self._heading_font, f"Winner: {winners}", (rect.x + 28, rect.y + 90), ACTIVE
        )
        spacing = min(35, 165 // len(names))
        for index, player in enumerate(observation.players):
            self._text(
                screen, self._font, f"{names[index]}: {player.total_score} points",
                (rect.x + 28, rect.y + 145 + index * spacing),
            )

    def _draw_button(
        self, screen: pygame.Surface, button: Button, mouse_pos: tuple[int, int] | None
    ) -> None:
        hovered = mouse_pos is not None and button.rect.collidepoint(mouse_pos)
        pygame.draw.rect(screen, BUTTON_HOVER if hovered else BUTTON, button.rect, border_radius=8)
        text = self._font.render(button.label, True, TEXT)
        screen.blit(text, text.get_rect(center=button.rect.center))
