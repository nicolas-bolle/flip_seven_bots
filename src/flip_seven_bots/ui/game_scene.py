"""A shared-screen table for any mix of human and bot players."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import pygame

from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    Observation,
    PlayerStatus,
    PlayerView,
    RoundResult,
)

from .bug_report import write_report
from .options import default_seats
from .table import Table
from .text import card_label, event_text

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
DIALOG = pygame.Rect(240, 160, 800, 560)
REPORT_BUTTON = pygame.Rect(1070, 24, 180, 40)
MAX_REPORT_LENGTH = 4000
NOTICE_MS = 6000


class Command(Enum):
    CONTINUE = auto()
    RESTART = auto()
    REPORT_BUG = auto()
    SUBMIT_REPORT = auto()
    CANCEL_REPORT = auto()


@dataclass(frozen=True)
class Button:
    rect: pygame.Rect
    label: str
    action: Action | Command
    shortcut: int | None = None


def _wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
    """Split text into lines that fit ``width``, keeping explicit line breaks."""
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if font.size(candidate)[0] <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            while len(word) > 1 and font.size(word)[0] > width:
                cut = len(word) - 1
                while cut > 1 and font.size(word[:cut])[0] > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


def _player_rects(count: int) -> list[pygame.Rect]:
    height = (PLAYER_AREA.height + PANEL_GAP) // count - PANEL_GAP
    return [
        pygame.Rect(
            PLAYER_AREA.x,
            PLAYER_AREA.y + index * (height + PANEL_GAP),
            PLAYER_AREA.width,
            height,
        )
        for index in range(count)
    ]


def _action_button(action: Action, names: Sequence[str], rect: pygame.Rect) -> Button:
    match action:
        case Action(kind=ActionType.HIT):
            return Button(rect, "Hit  [H]", action, pygame.K_h)
        case Action(kind=ActionType.STAY):
            return Button(rect, "Stay  [S]", action, pygame.K_s)
        case Action(target=int(target)) if target < 9:
            return Button(
                rect, f"{names[target]}  [{target + 1}]", action, pygame.K_1 + target
            )
        case Action(target=int(target)):
            return Button(rect, names[target], action)
    raise ValueError(f"unsupported action: {action}")


class GameScene:
    def __init__(
        self, table: Table | None = None, *, report_dir: Path = Path("bug_reports")
    ) -> None:
        self._table = table if table is not None else Table(default_seats())
        self._report_dir = report_dir
        self._report_text: str | None = None
        self._report_hint: str | None = None
        self._notice: str | None = None
        self._notice_until = 0
        self._now = 0
        self._title_font = pygame.font.Font(None, 42)
        self._heading_font = pygame.font.Font(None, 30)
        self._font = pygame.font.Font(None, 25)
        self._small_font = pygame.font.Font(None, 21)
        self._card_font = pygame.font.Font(None, 25)
        self._compact_card_font = pygame.font.Font(None, 16)

    @property
    def dialog_open(self) -> bool:
        """Whether the bug report dialog is capturing keyboard input, including Esc."""
        return self._report_text is not None

    @property
    def notice(self) -> str | None:
        return self._notice

    def buttons(self) -> tuple[Button, ...]:
        """The buttons currently on screen, derived from the scene's state."""
        if self.dialog_open:
            y = DIALOG.bottom - 76
            return (
                Button(
                    pygame.Rect(DIALOG.x + 28, y, 195, 50),
                    "Submit  [Enter]",
                    Command.SUBMIT_REPORT,
                    pygame.K_RETURN,
                ),
                Button(
                    pygame.Rect(DIALOG.x + 238, y, 195, 50),
                    "Cancel  [Esc]",
                    Command.CANCEL_REPORT,
                    pygame.K_ESCAPE,
                ),
            )
        report = Button(
            REPORT_BUTTON, "Report bug  [F1]", Command.REPORT_BUG, pygame.K_F1
        )
        return (*self._play_buttons(), report)

    def _play_buttons(self) -> tuple[Button, ...]:
        table = self._table
        corner = pygame.Rect(OVERLAY.x + 28, OVERLAY.bottom - 76, 195, 50)
        if table.round_summary is not None:
            return (
                Button(corner, "Continue  [Enter]", Command.CONTINUE, pygame.K_RETURN),
            )
        if table.game.is_finished:
            return (Button(corner, "Play again  [R]", Command.RESTART, pygame.K_r),)
        if table.human_to_act is None:
            return ()
        actions = table.observation.legal_actions
        gap = 15
        width = min(
            195, (CONTROLS.width - 40 - gap * (len(actions) - 1)) // len(actions)
        )
        return tuple(
            _action_button(
                action,
                table.names,
                pygame.Rect(
                    CONTROLS.x + 20 + index * (width + gap), CONTROLS.y + 85, width, 55
                ),
            )
            for index, action in enumerate(actions)
        )

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.dialog_open and self._edit_report(event):
            return
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
            case Button(action=Command.REPORT_BUG):
                self._report_text = ""
                self._report_hint = None
                self._table.pause()
            case Button(action=Command.SUBMIT_REPORT):
                self._submit_report()
            case Button(action=Command.CANCEL_REPORT):
                self._close_report()
            case Button(action=Action() as action):
                self._table.choose(action)

    def update(self, now: int) -> None:
        self._now = now
        if self._notice is not None and now >= self._notice_until:
            self._notice = None
        self._table.update(now)

    def _edit_report(self, event: pygame.event.Event) -> bool:
        """Apply typing to the report message; return whether the event was used."""
        assert self._report_text is not None
        if event.type == pygame.TEXTINPUT:
            room = MAX_REPORT_LENGTH - len(self._report_text)
            self._report_text += event.text[:room]
            return True
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_BACKSPACE:
            self._report_text = self._report_text[:-1]
            return True
        shift = getattr(event, "mod", 0) & pygame.KMOD_SHIFT
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and shift:
            if len(self._report_text) < MAX_REPORT_LENGTH:
                self._report_text += "\n"
            return True
        if event.key == pygame.K_KP_ENTER:
            self._submit_report()
            return True
        return False

    def _submit_report(self) -> None:
        assert self._report_text is not None
        if not self._report_text.strip():
            self._report_hint = "Please describe the problem first."
            return
        try:
            path = write_report(self._table, self._report_text, self._report_dir)
        except OSError as error:
            self._report_hint = f"Could not save the report: {error}"
            return
        self._close_report()
        self._notice = f"Bug report saved to {path}"
        self._notice_until = self._now + NOTICE_MS

    def _close_report(self) -> None:
        self._report_text = None
        self._table.resume()

    def render(
        self, screen: pygame.Surface, mouse_pos: tuple[int, int] | None = None
    ) -> None:
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

        for player, rect in zip(
            observation.players, _player_rects(len(observation.players))
        ):
            self._draw_player(screen, player, rect, observation)
        self._draw_activity(screen, observation)
        self._draw_controls(screen, observation)

        if table.round_summary is not None:
            self._draw_round_summary(screen, table.round_summary)
        elif table.game.is_finished:
            self._draw_game_over(screen, observation)

        if self._report_text is not None:
            self._draw_report_dialog(screen, self._report_text)
        if self._notice is not None:
            self._text(screen, self._small_font, self._notice, (35, 92), ACTIVE)

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
        color = PANEL_ALT if player.player in self._table.humans else PANEL
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
        self._text(
            screen, self._small_font, status, (rect.x + 200, rect.y + 19), ACCENT
        )
        score = f"Round: {player.round_score}    Total: {player.total_score}"
        self._text(screen, self._font, score, (rect.x + 570, rect.y + 16))

        if not player.cards:
            self._text(
                screen,
                self._small_font,
                "No cards yet",
                (rect.x + 18, rect.y + 50),
                MUTED,
            )
            return

        columns = 12
        groups = (
            [card for card in player.cards if card.kind is not CardType.NUMBER],
            [card for card in player.cards if card.kind is CardType.NUMBER],
        )
        rows = sum((len(group) + columns - 1) // columns for group in groups)
        gap = 2
        card_height = min(51, (rect.height - 47 - gap * (rows - 1)) // rows)
        row = 0
        for group in groups:
            for index, card in enumerate(group):
                x = rect.x + 16 + (index % columns) * 70
                y = rect.y + 42 + (row + index // columns) * (card_height + gap)
                self._draw_card(screen, card, pygame.Rect(x, y, 62, card_height))
            row += (len(group) + columns - 1) // columns

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
            text = (
                "2ND CH." if card.kind is CardType.SECOND_CHANCE else card_label(card)
            )
            font = self._compact_card_font if rect.height < 22 else self._card_font
            label = font.render(text, True, (25, 45, 46))
            if label.get_width() > rect.width - 6:
                label = self._compact_card_font.render(text, True, (25, 45, 46))
            screen.blit(label, label.get_rect(center=rect.center))

    def _draw_activity(self, screen: pygame.Surface, observation: Observation) -> None:
        rect = pygame.Rect(945, 112, 305, 558)
        pygame.draw.rect(screen, PANEL, rect, border_radius=12)
        self._text(
            screen, self._heading_font, "Recent activity", (rect.x + 16, rect.y + 16)
        )
        for index, event in enumerate(observation.events[-18:]):
            position = (rect.x + 16, rect.y + 54 + index * 26)
            self._text(
                screen,
                self._small_font,
                event_text(event, self._table.names),
                position,
                MUTED,
            )
        if observation.last_round is not None:
            self._text(
                screen,
                self._small_font,
                f"Last round: {observation.last_round.round_number}",
                (rect.x + 16, rect.bottom - 34),
                ACCENT,
            )

    def _draw_controls(self, screen: pygame.Surface, observation: Observation) -> None:
        pygame.draw.rect(screen, PANEL, CONTROLS, border_radius=12)
        table = self._table
        player = observation.current_player
        if table.game.is_finished:
            message = "Game over"
        elif player is None or player not in table.humans:
            assert player is not None  # unfinished games await a decision
            message = f"{table.names[player]} is deciding..."
        else:
            # With several humans sharing the screen, say whose turn it is.
            turn = (
                "Your turn"
                if len(table.humans) == 1
                else f"{table.names[player]}'s turn"
            )
            if observation.pending_card is not None:
                card = card_label(observation.pending_card)
                message = f"{turn}: choose a player for {card}"
            else:
                message = f"{turn}: hit or stay"
        self._text(
            screen, self._heading_font, message, (CONTROLS.x + 20, CONTROLS.y + 18)
        )
        self._text(
            screen,
            self._small_font,
            "Click a button or use its shortcut. Esc quits.",
            (CONTROLS.x + 20, CONTROLS.y + 52),
            MUTED,
        )

    def _overlay(self, screen: pygame.Surface, title: str) -> pygame.Rect:
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 180))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, PANEL_ALT, OVERLAY, border_radius=15)
        self._text(
            screen, self._title_font, title, (OVERLAY.x + 28, OVERLAY.y + 25), ACCENT
        )
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
                screen,
                self._heading_font,
                f"{names[index]}:  +{score}    total {total}",
                (rect.x + 28, rect.y + 120 + index * spacing),
            )

    def _draw_game_over(self, screen: pygame.Surface, observation: Observation) -> None:
        rect = self._overlay(screen, "Game over")
        names = self._table.names
        winners = ", ".join(names[index] for index in observation.winners)
        self._text(
            screen,
            self._heading_font,
            f"Winner: {winners}",
            (rect.x + 28, rect.y + 90),
            ACTIVE,
        )
        spacing = min(35, 165 // len(names))
        for index, player in enumerate(observation.players):
            self._text(
                screen,
                self._font,
                f"{names[index]}: {player.total_score} points",
                (rect.x + 28, rect.y + 145 + index * spacing),
            )

    def _draw_report_dialog(self, screen: pygame.Surface, message: str) -> None:
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 180))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, PANEL_ALT, DIALOG, border_radius=15)
        x = DIALOG.x + 28
        self._text(screen, self._title_font, "Report a bug", (x, DIALOG.y + 25), ACCENT)
        self._text(
            screen,
            self._small_font,
            "Describe what went wrong. The game's full state is saved with your message.",
            (x, DIALOG.y + 72),
            MUTED,
        )
        self._text(
            screen,
            self._small_font,
            "Enter submits, Shift+Enter starts a new line, Esc cancels.",
            (x, DIALOG.y + 94),
            MUTED,
        )
        box = pygame.Rect(x, DIALOG.y + 125, DIALOG.width - 56, 300)
        pygame.draw.rect(screen, BACKGROUND, box, border_radius=8)
        line_height = self._font.get_linesize()
        visible = (box.height - 20) // line_height
        lines = _wrap(message + "|", self._font, box.width - 24)
        for index, line in enumerate(lines[-visible:]):
            position = (box.x + 12, box.y + 10 + index * line_height)
            self._text(screen, self._font, line, position)
        if self._report_hint is not None:
            self._text(
                screen,
                self._small_font,
                self._report_hint,
                (x, box.bottom + 10),
                ACCENT,
            )

    def _draw_button(
        self, screen: pygame.Surface, button: Button, mouse_pos: tuple[int, int] | None
    ) -> None:
        hovered = mouse_pos is not None and button.rect.collidepoint(mouse_pos)
        pygame.draw.rect(
            screen, BUTTON_HOVER if hovered else BUTTON, button.rect, border_radius=8
        )
        text = self._font.render(button.label, True, TEXT)
        screen.blit(text, text.get_rect(center=button.rect.center))
