"""A shared-screen table for any mix of human and bot players."""

from collections import Counter, deque
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import pygame

from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardDrawn,
    CardType,
    ChooseCard,
    ChooseTarget,
    FlipSevenBonus,
    HitOrStay,
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
CARD_ANIMATION_MS = 600
DECK_RECT = pygame.Rect(855, 22, 42, 60)
NON_NUMBER_ORDER = {
    CardType.ADD: 0,
    CardType.SUBTRACT: 1,
    CardType.MULTIPLY: 2,
    CardType.DIVIDE: 3,
    CardType.SECOND_CHANCE: 4,
    CardType.FREEZE: 5,
    CardType.FLIP_THREE: 6,
    CardType.JUST_ONE_MORE: 7,
    CardType.FLIP_FOUR: 8,
    CardType.SWAP: 9,
    CardType.STEAL: 10,
    CardType.DISCARD: 11,
}


class Command(Enum):
    """UI-only actions that do not directly represent game decisions."""

    CONTINUE = auto()
    RESTART = auto()
    REPORT_BUG = auto()
    SUBMIT_REPORT = auto()
    CANCEL_REPORT = auto()


@dataclass(frozen=True)
class Button:
    """Clickable region for a game action or UI command, with an optional key."""

    rect: pygame.Rect
    label: str
    action: Action | Command
    shortcut: int | None = None


@dataclass(frozen=True)
class _AnimatedDraw:
    """A draw to animate, noting whether the card remains in the current hand."""

    event: CardDrawn
    in_hand: bool


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


def _card_rects(cards: Sequence[Card], rect: pygame.Rect) -> list[pygame.Rect]:
    """Lay out cards in sorted rows while returning rectangles in hand-index order.

    Keeping the original indices lets a click map back to ``CHOOSE_CARD`` even
    though the displayed cards are sorted.
    """
    columns = 12
    groups = (
        sorted(
            (i for i, card in enumerate(cards) if not card.is_number),
            key=lambda i: (
                NON_NUMBER_ORDER[cards[i].kind],
                -cards[i].value
                if cards[i].kind is CardType.SUBTRACT
                else cards[i].value,
            ),
        ),
        sorted(
            (i for i, card in enumerate(cards) if card.is_number),
            key=lambda i: cards[i].value,
        ),
    )
    rows = sum((len(group) + columns - 1) // columns for group in groups)
    if not rows:
        return []
    gap = 2
    card_height = min(51, (rect.height - 47 - gap * (rows - 1)) // rows)
    result = [pygame.Rect(0, 0, 0, 0) for _ in cards]
    row = 0
    for group in groups:
        for index, card_index in enumerate(group):
            x = rect.x + 16 + (index % columns) * 70
            y = rect.y + 42 + (row + index // columns) * (card_height + gap)
            result[card_index] = pygame.Rect(x, y, 62, card_height)
        row += (len(group) + columns - 1) // columns
    return result


def _action_button(action: Action, names: Sequence[str], rect: pygame.Rect) -> Button:
    match action:
        case Action(kind=ActionType.HIT):
            return Button(rect, "Hit  [H]", action, pygame.K_h)
        case Action(kind=ActionType.STAY):
            return Button(rect, "Stay  [S]", action, pygame.K_s)
        case Action(kind=ActionType.TAKE_BONUS):
            return Button(rect, "Take bonus  [B]", action, pygame.K_b)
        case Action(kind=ActionType.CHOOSE_TARGET, target=int(target)) if target < 9:
            return Button(
                rect, f"{names[target]}  [{target + 1}]", action, pygame.K_1 + target
            )
        case Action(kind=ActionType.CHOOSE_TARGET, target=int(target)):
            return Button(rect, names[target], action)
    raise ValueError(f"unsupported action: {action}")


class GameScene:
    """Render a table and translate human input into decisions and UI commands.

    Draw animations run in sequence and block play until finished. Round
    summaries and the bug-report dialog also pause decisions; the table
    continues to own the authoritative game state.
    """

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
        self._pause_started: int | None = None
        self._draws: deque[_AnimatedDraw] = deque()
        self._draw_started: int | None = None
        self._previous_round: Observation | None = None
        self._title_font = pygame.font.Font(None, 42)
        self._heading_font = pygame.font.Font(None, 30)
        self._font = pygame.font.Font(None, 25)
        self._small_font = pygame.font.Font(None, 21)
        self._card_font = pygame.font.Font(None, 25)
        self._compact_card_font = pygame.font.Font(None, 16)
        self._queue_draws(None)

    @property
    def dialog_open(self) -> bool:
        """Whether the bug report dialog is capturing keyboard input, including Esc."""
        return self._report_text is not None

    @property
    def notice(self) -> str | None:
        """Temporary status message, such as a saved bug-report path."""
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
        """Build currently available controls, including clickable card regions."""
        table = self._table
        if self._animating:
            return ()
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
        if actions and actions[0].kind is ActionType.CHOOSE_CARD:
            observation = table.observation
            panels = _player_rects(len(observation.players))
            return tuple(
                Button(
                    _card_rects(
                        observation.players[action.target].cards, panels[action.target]
                    )[action.card_index],
                    "",
                    action,
                )
                for action in actions
                if action.target is not None and action.card_index is not None
            )
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
        """Handle a click or shortcut, or route text input to the report dialog."""
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
                self._draws.clear()
                self._draw_started = None
                self._previous_round = None
                self._queue_draws(None)
            case Button(action=Command.REPORT_BUG):
                self._report_text = ""
                self._report_hint = None
                self._pause_started = self._now
                self._table.pause()
            case Button(action=Command.SUBMIT_REPORT):
                self._submit_report()
            case Button(action=Command.CANCEL_REPORT):
                self._close_report()
            case Button(action=Action() as action):
                before = self._table.observation
                self._table.choose(action)
                self._queue_draws(before)

    def update(self, now: int) -> None:
        """Advance animations and, when unblocked, let the table process a bot move.

        ``now`` is a monotonic time in milliseconds.
        """
        self._now = now
        if self._notice is not None and now >= self._notice_until:
            self._notice = None
        if self.dialog_open:
            return
        if self._animating:
            if self._draw_started is None:
                self._draw_started = now
            while self._animating and now - self._draw_started >= CARD_ANIMATION_MS:
                self._draws.popleft()
                self._draw_started += CARD_ANIMATION_MS
            if not self._animating:
                self._draw_started = None
            return
        before = self._table.observation
        moves = len(self._table.moves)
        self._table.update(now)
        if len(self._table.moves) != moves:
            self._queue_draws(before)

    @property
    def _swap_first(self) -> tuple[int, int] | None:
        """The first card chosen for a pending Swap, kept highlighted until the second."""
        match self._table.observation.decision:
            case ChooseCard(first=first):
                return first
        return None

    @property
    def _animating(self) -> bool:
        summary = self._table.round_summary
        return bool(
            self._draws
            and (
                summary is None
                or self._draws[0].event.round_number <= summary.round_number
            )
        )

    def _queue_draws(self, before: Observation | None) -> None:
        """Queue recent draws and identify cards still present in the new hand.

        A draw can be resolved or discarded before animation starts. Comparing
        hand counts with the previous observation distinguishes those cards
        from draws that should remain visible after their animation.
        """
        after = self._table.observation
        if before is not None and before.round_number != after.round_number:
            self._previous_round = before
        added = [
            Counter(player.cards)
            - (
                Counter(before.players[player.player].cards)
                if before is not None and before.round_number == after.round_number
                else Counter()
            )
            for player in after.players
        ]
        queued: list[_AnimatedDraw] = []
        for event in reversed(self._table.game.recent_draws):
            in_hand = (
                event.round_number == after.round_number
                and added[event.player][event.card] > 0
            )
            if in_hand:
                added[event.player][event.card] -= 1
            queued.append(_AnimatedDraw(event, in_hand))
        self._draws.extend(reversed(queued))

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
        if self._draw_started is not None and self._pause_started is not None:
            self._draw_started += self._now - self._pause_started
        self._pause_started = None
        self._table.resume()

    def render(
        self, screen: pygame.Surface, mouse_pos: tuple[int, int] | None = None
    ) -> None:
        """Draw the current table, pending animations, overlays, and controls."""
        table = self._table
        observation = table.observation
        if (
            self._animating
            and self._previous_round is not None
            and self._draws[0].event.round_number == self._previous_round.round_number
        ):
            observation = self._previous_round
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
        self._draw_deck(screen)

        for player, rect in zip(
            observation.players, _player_rects(len(observation.players))
        ):
            self._draw_player(screen, player, rect, observation)
        if self._swap_first is not None and not self._animating:
            owner, index = self._swap_first
            panel = _player_rects(len(observation.players))[owner]
            rect = _card_rects(observation.players[owner].cards, panel)[index]
            pygame.draw.rect(
                screen, ACCENT, rect.inflate(4, 4), width=2, border_radius=6
            )
        self._draw_activity(screen, observation)
        self._draw_controls(screen, observation)
        if self._animating:
            self._draw_animation(screen, observation)

        if table.round_summary is not None and not self._animating:
            self._draw_round_summary(screen, table.round_summary)
        elif table.game.is_finished and not self._animating:
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
        waiting = any(
            draw.event.player == player.player
            and draw.event.round_number == observation.round_number
            for draw in self._draws
        )
        if waiting:
            status = "..."
        name = self._table.names[player.player]
        self._text(screen, self._heading_font, name, (rect.x + 16, rect.y + 13))
        self._text(
            screen, self._small_font, status, (rect.x + 200, rect.y + 19), ACCENT
        )
        live_score = "..." if waiting else str(player.round_score)
        score = f"Total: {player.total_score}    Live round: {live_score}"
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

        hidden = Counter(
            draw.event.card
            for draw in self._draws
            if draw.in_hand
            and draw.event.round_number == observation.round_number
            and draw.event.player == player.player
        )
        rects = _card_rects(player.cards, rect)
        for card, card_rect in reversed(list(zip(player.cards, rects))):
            if hidden[card]:
                hidden[card] -= 1
            else:
                self._draw_card(screen, card, card_rect)

    def _draw_deck(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, BUTTON, DECK_RECT, border_radius=6)
        pygame.draw.rect(screen, ACCENT, DECK_RECT, width=2, border_radius=6)
        self._text(
            screen,
            self._compact_card_font,
            "DECK",
            (DECK_RECT.x + 6, DECK_RECT.y + 23),
            TEXT,
        )

    def _draw_animation(self, screen: pygame.Surface, observation: Observation) -> None:
        draw = self._draws[0]
        event = draw.event
        player = observation.players[event.player]
        panel = _player_rects(len(observation.players))[event.player]
        cards = player.cards
        if draw.in_hand:
            hidden_count = sum(
                queued.in_hand
                and queued.event.player == event.player
                and queued.event.round_number == event.round_number
                and queued.event.card == event.card
                for queued in self._draws
            )
            indices = [i for i, card in enumerate(cards) if card == event.card]
            destination = _card_rects(cards, panel)[indices[-hidden_count]]
        else:
            destination = _card_rects((*cards, event.card), panel)[-1]
        progress = (
            min(1.0, max(0.0, (self._now - self._draw_started) / CARD_ANIMATION_MS))
            if self._draw_started is not None and CARD_ANIMATION_MS
            else 0.0
        )
        eased = progress * progress * (3 - 2 * progress)
        center = (
            round(
                DECK_RECT.centerx + (destination.centerx - DECK_RECT.centerx) * eased
            ),
            round(
                DECK_RECT.centery + (destination.centery - DECK_RECT.centery) * eased
            ),
        )
        width = max(1, round(destination.width * abs(1 - 2 * progress)))
        card_surface = pygame.Surface(destination.size, pygame.SRCALPHA)
        if progress < 0.5:
            card_surface.fill(BUTTON)
            pygame.draw.rect(
                card_surface, ACCENT, card_surface.get_rect(), width=2, border_radius=6
            )
        else:
            self._draw_card(card_surface, event.card, card_surface.get_rect())
        flipped = pygame.transform.smoothscale(
            card_surface, (width, destination.height)
        )
        screen.blit(flipped, flipped.get_rect(center=center))

    def _draw_card(self, screen: pygame.Surface, card: Card, rect: pygame.Rect) -> None:
        if card.is_number:
            color = (232, 224, 193)
        elif card.kind in (
            CardType.ADD,
            CardType.MULTIPLY,
            CardType.SUBTRACT,
            CardType.DIVIDE,
        ):
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
        pending = Counter(
            draw.event
            for draw in self._draws
            if observation is not self._previous_round
        )
        visible = []
        for event in reversed(observation.events):
            if isinstance(event, CardDrawn) and pending[event]:
                pending[event] -= 1
            else:
                visible.append(event)
        for index, event in enumerate(list(reversed(visible))[-18:]):
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
        if self._animating:
            message = "Dealing cards..."
        elif table.game.is_finished:
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
            match observation.decision:
                case ChooseCard(card=card, first=first):
                    step = "second" if first is not None else "first"
                    choice = (
                        f"the {step} card" if card.kind is CardType.SWAP else "a card"
                    )
                    message = f"{turn}: choose {choice} for {card_label(card)}"
                case FlipSevenBonus():
                    message = f"{turn}: take the bonus or subtract it from a player"
                case ChooseTarget(card=card):
                    message = f"{turn}: choose a player for {card_label(card)}"
                case HitOrStay(can_stay=False):
                    message = f"{turn}: you must hit"
                case _:
                    message = f"{turn}: hit or stay"
        self._text(
            screen, self._heading_font, message, (CONTROLS.x + 20, CONTROLS.y + 18)
        )
        self._text(
            screen,
            self._small_font,
            "Click a button or highlighted card, or use a shortcut. Esc quits.",
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
            message = f"{names[result.flip_seven_player]} got Flip 7!"
            self._text(screen, self._font, message, (rect.x + 28, rect.y + 75), ACTIVE)
        spacing = min(45, 190 // len(names))
        for index, (score, total) in enumerate(zip(result.scores, result.totals)):
            self._text(
                screen,
                self._heading_font,
                f"{names[index]}:  {score:+d}    total {total}",
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
        if (
            isinstance(button.action, Action)
            and button.action.kind is ActionType.CHOOSE_CARD
        ):
            pygame.draw.rect(
                screen,
                ACCENT if hovered else ACTIVE,
                button.rect,
                width=2,
                border_radius=6,
            )
            return
        pygame.draw.rect(
            screen, BUTTON_HOVER if hovered else BUTTON, button.rect, border_radius=8
        )
        text = self._font.render(button.label, True, TEXT)
        screen.blit(text, text.get_rect(center=button.rect.center))
