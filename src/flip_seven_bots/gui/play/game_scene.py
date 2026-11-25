"""A shared-screen table for any mix of human and bot players."""

from collections import Counter, deque
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from itertools import pairwise
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
    GameEvent,
    HitOrStay,
    Observation,
    PlayerStatus,
    PlayerView,
    RoundEnded,
    RoundResult,
    RoundStarted,
)

from ..common.text import card_label, event_text
from ..common.theme import (
    ACCENT,
    ACTIVE,
    BACKGROUND,
    BUTTON,
    BUTTON_HOVER,
    MUTED,
    PANEL,
    PANEL_ALT,
    TEXT,
)
from .bug_report import write_report
from .options import default_seats
from .table import Table

TOP_STRIP_Y = 18
TURN_BOX = pygame.Rect(320, TOP_STRIP_Y, 432, 178)
DECK_RECT = pygame.Rect(781, 46, 56, 78)
ACTIVITY = pygame.Rect(866, TOP_STRIP_Y, 384, 178)
REPORT_BUTTON = pygame.Rect(30, 150, 190, 42)
HISTORY_BUTTON = pygame.Rect(ACTIVITY.right - 128, ACTIVITY.y + 10, 116, 32)
PLAYER_AREA = pygame.Rect(30, 210, 1220, 674)
PANEL_GAP = 10
OVERLAY = pygame.Rect(340, 150, 600, 600)
DIALOG = pygame.Rect(240, 160, 800, 560)
HISTORY_DIALOG = pygame.Rect(140, 50, 1000, 800)
HISTORY_LINE = 24
MAX_REPORT_LENGTH = 4000
NOTICE_MS = 6000
CARD_ANIMATION_MS = 600
# Real cards are 63 x 88 mm, close to 5:7.
CARD_ASPECT = 5 / 7
MAX_CARD_HEIGHT = 105
CARD_GAP = 4
GROUP_GAP = 14
# Cards are sized so this many fit side by side; larger hands overlap.
CARDS_WITHOUT_OVERLAP = 9
CARD_INK = (25, 45, 46)
CORNER_LABELS = {
    CardType.SECOND_CHANCE: 'SC',
    CardType.FREEZE: 'FRZ',
    CardType.FLIP_THREE: 'F3',
    CardType.FLIP_FOUR: 'F4',
    CardType.JUST_ONE_MORE: 'ONE',
    CardType.SWAP: 'SWP',
    CardType.STEAL: 'STL',
    CardType.DISCARD: 'DSC',
    CardType.ZERO: '0',
    CardType.UNLUCKY_SEVEN: '7',
    CardType.LUCKY_THIRTEEN: '13',
}
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
    BACK_TO_SETUP = auto()
    REPORT_BUG = auto()
    SUBMIT_REPORT = auto()
    CANCEL_REPORT = auto()
    SHOW_HISTORY = auto()
    CLOSE_HISTORY = auto()


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
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split(' '):
            candidate = f'{line} {word}' if line else word
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
    """Lay out boards top to bottom in one column for up to 3 players, else two.

    Boards are sized for at least three rows, so small tables keep the same
    proportions: 4-6 players use a 2x3 grid, 7-8 use 2x4 and 9-10 use 2x5.
    """
    columns = 1 if count <= 3 else 2
    per_column = -(-count // columns)
    rows = max(3, per_column)
    width = (PLAYER_AREA.width - PANEL_GAP * (columns - 1)) // columns
    height = (PLAYER_AREA.height - PANEL_GAP * (rows - 1)) // rows
    return [
        pygame.Rect(
            PLAYER_AREA.x + index // per_column * (width + PANEL_GAP),
            PLAYER_AREA.y + index % per_column * (height + PANEL_GAP),
            width,
            height,
        )
        for index in range(count)
    ]


def _seat_key(player: int) -> tuple[str, int] | None:
    """The label and key that pick ``player``: 1-9, then 0 for the tenth seat."""
    if player < 9:
        return str(player + 1), pygame.K_1 + player
    if player == 9:
        return '0', pygame.K_0
    return None


def _shown_cards(player: PlayerView) -> tuple[Card, ...]:
    """Cards drawn in a player's panel: the hand, then cards awaiting resolution.

    The hand comes first so that ``CHOOSE_CARD`` indices still address it.
    """
    return player.cards + player.unresolved


def _card_rects(cards: Sequence[Card], rect: pygame.Rect) -> list[pygame.Rect]:
    """Lay out a board's cards in one sorted row, returning them in hand order.

    Non-number cards come first, then numbers. Cards overlap, later ones on
    top, when the row would not otherwise fit. Keeping the original indices
    lets a click map back to ``CHOOSE_CARD`` even though the row is sorted.
    """
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
    if not cards:
        return []
    left, top = rect.x + 16, rect.y + 42
    room = rect.width - 32
    group_gap = GROUP_GAP if all(groups) else 0
    fitted = (room - GROUP_GAP - CARD_GAP * (CARDS_WITHOUT_OVERLAP - 1)) / (
        CARDS_WITHOUT_OVERLAP * CARD_ASPECT
    )
    space = rect.bottom - 8 - top
    height = max(12, int(min(MAX_CARD_HEIGHT, space, fitted)))
    top += max(0, space - height) // 2
    width = round(height * CARD_ASPECT)
    step: float = width + CARD_GAP
    if len(cards) > 1 and len(cards) * step - CARD_GAP + group_gap > room:
        step = (room - width - group_gap) / (len(cards) - 1)
    result = [pygame.Rect(0, 0, 0, 0) for _ in cards]
    x: float = left
    for group in groups:
        for card_index in group:
            result[card_index] = pygame.Rect(round(x), top, width, height)
            x += step
        if group:
            x += group_gap
    return result


def _visible_card_rects(rects: Sequence[pygame.Rect]) -> list[pygame.Rect]:
    """Clip each card to the part not covered by the card drawn after it."""
    visible = [rect.copy() for rect in rects]
    order = sorted(range(len(rects)), key=lambda i: rects[i].x)
    for current, following in pairwise(order):
        visible[current].width = min(
            rects[current].width, rects[following].x - rects[current].x
        )
    return visible


def _history_box() -> pygame.Rect:
    return pygame.Rect(
        HISTORY_DIALOG.x + 28,
        HISTORY_DIALOG.y + 96,
        HISTORY_DIALOG.width - 56,
        HISTORY_DIALOG.height - 96 - 100,
    )


def _history_lines() -> int:
    """How many events fit in the history dialog at once."""
    return (_history_box().height - 16) // HISTORY_LINE


def _action_button(action: Action, rect: pygame.Rect) -> Button:
    match action:
        case Action(kind=ActionType.HIT):
            return Button(rect, 'Hit  [H]', action, pygame.K_h)
        case Action(kind=ActionType.STAY):
            return Button(rect, 'Stay  [S]', action, pygame.K_s)
        case Action(kind=ActionType.TAKE_BONUS):
            return Button(rect, 'Take bonus  [B]', action, pygame.K_b)
    raise ValueError(f'unsupported action: {action}')


def _target_button(action: Action, names: Sequence[str], board: pygame.Rect) -> Button:
    """A player's whole board is the button for choosing them."""
    assert action.target is not None
    key = _seat_key(action.target)
    if key is None:
        return Button(board, names[action.target], action)
    label, shortcut = key
    return Button(board, f'{names[action.target]}  [{label}]', action, shortcut)


class GameScene:
    """Render a table and translate human input into decisions and UI commands.

    Draw animations run in sequence and block play until finished. Round
    summaries and the bug-report dialog also pause decisions; the table
    continues to own the authoritative game state.
    """

    def __init__(
        self, table: Table | None = None, *, report_dir: Path = Path('bug_reports')
    ) -> None:
        self._table = table if table is not None else Table(default_seats())
        self.return_to_setup = False
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
        self._history_open = False
        self._history_scroll = 0
        self._title_font = pygame.font.Font(None, 42)
        self._heading_font = pygame.font.Font(None, 30)
        self._font = pygame.font.Font(None, 25)
        self._small_font = pygame.font.Font(None, 21)
        self._compact_card_font = pygame.font.Font(None, 16)
        self._sized_fonts: dict[int, pygame.font.Font] = {}
        self._queue_draws(None)

    @property
    def dialog_open(self) -> bool:
        """Whether a dialog is capturing keyboard input, including Esc."""
        return self._report_text is not None or self._history_open

    @property
    def notice(self) -> str | None:
        """Temporary status message, such as a saved bug-report path."""
        return self._notice

    def buttons(self) -> tuple[Button, ...]:
        """The buttons currently on screen, derived from the scene's state."""
        if self._report_text is not None:
            y = DIALOG.bottom - 76
            return (
                Button(
                    pygame.Rect(DIALOG.x + 28, y, 195, 50),
                    'Submit  [Enter]',
                    Command.SUBMIT_REPORT,
                    pygame.K_RETURN,
                ),
                Button(
                    pygame.Rect(DIALOG.x + 238, y, 195, 50),
                    'Cancel  [Esc]',
                    Command.CANCEL_REPORT,
                    pygame.K_ESCAPE,
                ),
            )
        if self._history_open:
            return (
                Button(
                    pygame.Rect(
                        HISTORY_DIALOG.x + 28, HISTORY_DIALOG.bottom - 72, 195, 50
                    ),
                    'Close  [L]',
                    Command.CLOSE_HISTORY,
                    pygame.K_l,
                ),
            )
        report = Button(
            REPORT_BUTTON, 'Report bug  [F1]', Command.REPORT_BUG, pygame.K_F1
        )
        history = Button(
            HISTORY_BUTTON, 'History  [L]', Command.SHOW_HISTORY, pygame.K_l
        )
        return (*self._play_buttons(), report, history)

    def _play_buttons(self) -> tuple[Button, ...]:
        """Build currently available controls, including clickable cards and boards."""
        table = self._table
        if self._animating:
            return ()
        corner = pygame.Rect(OVERLAY.x + 28, OVERLAY.bottom - 76, 195, 50)
        if table.round_summary is not None:
            return (
                Button(corner, 'Continue  [Enter]', Command.CONTINUE, pygame.K_RETURN),
            )
        if table.game.is_finished:
            return (
                Button(corner, 'Back to setup  [R]', Command.BACK_TO_SETUP, pygame.K_r),
            )
        if table.human_to_act is None:
            return ()
        observation = table.observation
        boards = _player_rects(len(observation.players))
        buttons = []
        controls = []
        for action in observation.legal_actions:
            match action:
                case Action(
                    kind=ActionType.CHOOSE_CARD,
                    target=int(target),
                    card_index=int(index),
                ):
                    cards = _shown_cards(observation.players[target])
                    rects = _visible_card_rects(_card_rects(cards, boards[target]))
                    buttons.append(Button(rects[index], '', action))
                case Action(kind=ActionType.CHOOSE_TARGET, target=int(target)):
                    buttons.append(_target_button(action, table.names, boards[target]))
                case _:
                    controls.append(action)
        y = TURN_BOX.bottom - 62
        for index, action in enumerate(controls):
            rect = pygame.Rect(TURN_BOX.x + 16 + index * 202, y, 190, 48)
            buttons.append(_action_button(action, rect))
        return tuple(buttons)

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle a click or shortcut, or route input to an open dialog."""
        if self._report_text is not None and self._edit_report(event):
            return
        if self._history_open and self._scroll_history(event):
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
            case Button(action=Command.BACK_TO_SETUP):
                self.return_to_setup = True
            case Button(action=Command.REPORT_BUG):
                self._report_text = ''
                self._report_hint = None
                self._pause()
            case Button(action=Command.SUBMIT_REPORT):
                self._submit_report()
            case Button(action=Command.CANCEL_REPORT):
                self._close_report()
            case Button(action=Command.SHOW_HISTORY):
                self._history_open = True
                self._history_scroll = 0
                self._pause()
            case Button(action=Command.CLOSE_HISTORY):
                self._close_history()
            case Button(action=Action() as action):
                before = self._table.observation
                self._table.choose(action)
                self._queue_draws(before)

    def _scroll_history(self, event: pygame.event.Event) -> bool:
        """Scroll or close the history; return whether the event was used."""
        steps = {
            pygame.K_UP: 1,
            pygame.K_DOWN: -1,
            pygame.K_PAGEUP: 20,
            pygame.K_PAGEDOWN: -20,
        }
        if event.type == pygame.MOUSEWHEEL:
            self._history_scroll += 3 * event.y
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._close_history()
        elif event.type == pygame.KEYDOWN and event.key in steps:
            self._history_scroll += steps[event.key]
        else:
            return False
        newest = len(self._shown_history()) - _history_lines()
        self._history_scroll = min(max(0, newest), max(0, self._history_scroll))
        return True

    def _pause(self) -> None:
        self._pause_started = self._now
        self._table.pause()

    def _resume(self) -> None:
        if self._draw_started is not None and self._pause_started is not None:
            self._draw_started += self._now - self._pause_started
        self._pause_started = None
        self._table.resume()

    def _close_history(self) -> None:
        self._history_open = False
        self._resume()

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
            Counter(_shown_cards(player))
            - (
                Counter(_shown_cards(before.players[player.player]))
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
        shift = getattr(event, 'mod', 0) & pygame.KMOD_SHIFT
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and shift:
            if len(self._report_text) < MAX_REPORT_LENGTH:
                self._report_text += '\n'
            return True
        if event.key == pygame.K_KP_ENTER:
            self._submit_report()
            return True
        return False

    def _submit_report(self) -> None:
        assert self._report_text is not None
        if not self._report_text.strip():
            self._report_hint = 'Please describe the problem first.'
            return
        try:
            path = write_report(self._table, self._report_text, self._report_dir)
        except OSError as error:
            self._report_hint = f'Could not save the report: {error}'
            return
        self._close_report()
        self._notice = f'Bug report saved to {path}'
        self._notice_until = self._now + NOTICE_MS

    def _close_report(self) -> None:
        self._report_text = None
        self._resume()

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
        buttons = self.buttons()
        self._draw_header(screen, observation)
        self._draw_controls(screen, observation)
        self._draw_deck(screen)
        self._draw_activity(screen)

        boards = _player_rects(len(observation.players))
        for player, rect in zip(observation.players, boards):
            self._draw_player(screen, player, rect, observation)
        targets = {
            b.action.target
            for b in buttons
            if isinstance(b.action, Action)
            and b.action.kind is ActionType.CHOOSE_TARGET
        }
        if targets:
            shade = pygame.Surface(boards[0].size, pygame.SRCALPHA)
            shade.fill((0, 0, 0, 120))
            for index, rect in enumerate(boards):
                if index not in targets:
                    screen.blit(shade, rect)
        if self._swap_first is not None and not self._animating:
            owner, index = self._swap_first
            cards = _shown_cards(observation.players[owner])
            rect = _card_rects(cards, boards[owner])[index]
            pygame.draw.rect(
                screen, ACCENT, rect.inflate(4, 4), width=2, border_radius=6
            )
        if self._animating:
            self._draw_animation(screen, observation)

        if table.round_summary is not None and not self._animating:
            self._draw_round_summary(screen, table.round_summary)
        elif table.game.is_finished and not self._animating:
            self._draw_game_over(screen, observation)

        if self._report_text is not None:
            self._draw_report_dialog(screen, self._report_text)
        if self._history_open:
            self._draw_history(screen)
        if self._notice is not None:
            self._draw_notice(screen, self._notice)

        for button in buttons:
            self._draw_button(screen, button, mouse_pos)

    def _draw_header(self, screen: pygame.Surface, observation: Observation) -> None:
        self._text(screen, self._title_font, 'FLIP 7', (35, 22), ACCENT)
        dealer = self._table.names[observation.dealer]
        self._text(
            screen,
            self._font,
            self._fit(
                f'Round {observation.round_number}  |  Dealer: {dealer}',
                self._font,
                TURN_BOX.x - 50,
            ),
            (35, 66),
            MUTED,
        )
        self._text(
            screen,
            self._font,
            f'Deck: {observation.cards_remaining}  |  '
            f'Discard: {len(observation.discard)}',
            (35, 94),
            MUTED,
        )
        self._text(screen, self._small_font, 'Esc quits.', (232, 164), MUTED)

    def _draw_notice(self, screen: pygame.Surface, notice: str) -> None:
        label = self._small_font.render(notice, True, ACTIVE)
        box = label.get_rect(midbottom=(screen.get_width() // 2, PLAYER_AREA.bottom))
        box = box.inflate(28, 16)
        pygame.draw.rect(screen, PANEL_ALT, box, border_radius=8)
        pygame.draw.rect(screen, ACTIVE, box, width=1, border_radius=8)
        screen.blit(label, label.get_rect(center=box.center))

    def _shown_history(self) -> tuple[GameEvent, ...]:
        """The game's events, up to the first draw that is still waiting to animate."""
        history = self._table.game.history
        pending = len(self._draws)
        for index in range(len(history) - 1, -1, -1):
            if not pending:
                break
            if isinstance(history[index], CardDrawn):
                pending -= 1
                if not pending:
                    return history[:index]
        return history

    def _fit(self, text: str, font: pygame.font.Font, width: int) -> str:
        """Shorten ``text`` with an ellipsis until it fits in ``width`` pixels."""
        if font.size(text)[0] <= width:
            return text
        while text and font.size(text + '...')[0] > width:
            text = text[:-1]
        return text.rstrip() + '...'

    def _sized_font(self, size: int) -> pygame.font.Font:
        if size not in self._sized_fonts:
            self._sized_fonts[size] = pygame.font.Font(None, size)
        return self._sized_fonts[size]

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
            PlayerStatus.ACTIVE: 'ACTIVE',
            PlayerStatus.STAYED: 'STAYED',
            PlayerStatus.BUSTED: 'BUSTED',
        }[player.status]
        waiting = any(
            draw.event.player == player.player
            and draw.event.round_number == observation.round_number
            for draw in self._draws
        )
        if waiting:
            status = '...'
        key = _seat_key(player.player)
        if key is not None:
            badge = pygame.Rect(rect.x + 12, rect.y + 10, 24, 24)
            pygame.draw.rect(screen, BUTTON, badge, border_radius=6)
            label = self._small_font.render(key[0], True, TEXT)
            screen.blit(label, label.get_rect(center=badge.center))
        live_score = '...' if waiting else str(player.round_score)
        score = f'Total: {player.total_score}    Live round: {live_score}'
        score_x = rect.right - 14 - self._font.size(score)[0]
        self._text(screen, self._font, score, (score_x, rect.y + 14))
        status_width = self._small_font.size('BUSTED')[0]
        name = self._fit(
            self._table.names[player.player],
            self._heading_font,
            score_x - rect.x - 44 - status_width - 30,
        )
        self._text(screen, self._heading_font, name, (rect.x + 44, rect.y + 12))
        self._text(
            screen,
            self._small_font,
            status,
            (rect.x + 58 + self._heading_font.size(name)[0], rect.y + 18),
            ACCENT,
        )

        cards = _shown_cards(player)
        if not cards:
            self._text(
                screen,
                self._small_font,
                'No cards yet',
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
        # Cards still flying in are the most recently added copies.
        shown = []
        for index in reversed(range(len(cards))):
            if hidden[cards[index]]:
                hidden[cards[index]] -= 1
            else:
                shown.append(index)
        rects = _card_rects(cards, rect)
        visible = _visible_card_rects(rects)
        for index in sorted(shown, key=lambda i: rects[i].x):
            self._draw_card(
                screen, cards[index], rects[index], visible_width=visible[index].width
            )

    def _draw_deck(self, screen: pygame.Surface) -> None:
        self._draw_card_back(screen, DECK_RECT)
        label = self._small_font.render('DECK', True, MUTED)
        screen.blit(
            label, label.get_rect(midtop=(DECK_RECT.centerx, DECK_RECT.bottom + 8))
        )

    def _draw_card_back(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        radius = max(3, rect.width // 8)
        pygame.draw.rect(screen, BUTTON, rect, border_radius=radius)
        pygame.draw.rect(screen, ACCENT, rect, width=2, border_radius=radius)
        inner = rect.inflate(-rect.width // 3, -rect.height // 3)
        if inner.width > 4 and inner.height > 4:
            pygame.draw.rect(screen, ACCENT, inner, width=1, border_radius=radius // 2)

    def _draw_animation(self, screen: pygame.Surface, observation: Observation) -> None:
        draw = self._draws[0]
        event = draw.event
        player = observation.players[event.player]
        panel = _player_rects(len(observation.players))[event.player]
        cards = _shown_cards(player)
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
            self._draw_card_back(card_surface, card_surface.get_rect())
        else:
            self._draw_card(card_surface, event.card, card_surface.get_rect())
        flipped = pygame.transform.smoothscale(
            card_surface, (width, destination.height)
        )
        screen.blit(flipped, flipped.get_rect(center=center))

    def _draw_card(
        self,
        screen: pygame.Surface,
        card: Card,
        rect: pygame.Rect,
        *,
        visible_width: int | None = None,
    ) -> None:
        """Draw a card face; ``visible_width`` is how much the next card leaves showing."""
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
        radius = max(3, rect.width // 8)
        pygame.draw.rect(screen, color, rect, border_radius=radius)
        # The outline keeps overlapping cards distinct.
        pygame.draw.rect(screen, CARD_INK, rect, width=1, border_radius=radius)
        text = card_label(card)
        if rect.height < 40:
            label = self._compact_card_font.render(text, True, CARD_INK)
            screen.blit(label, label.get_rect(center=rect.center))
            return
        # Like a real card, the corner index stays visible when cards overlap.
        corner = self._compact_card_font.render(
            CORNER_LABELS.get(card.kind, text), True, CARD_INK
        )
        screen.blit(corner, (rect.x + 4, rect.y + 4))
        if len(text) <= 3:
            font = self._sized_font(max(16, rect.height // 2))
            lines = [text]
        else:
            font = self._small_font
            lines = text.split()
        if any(font.size(line)[0] > rect.width - 6 for line in lines):
            font = self._compact_card_font
        widest = max(font.size(line)[0] for line in lines)
        if visible_width is not None and (rect.width + widest) // 2 > visible_width - 2:
            return  # covered: like a fanned hand, only the corner index shows
        line_height = font.get_linesize()
        top = rect.centery + 4 - line_height * len(lines) // 2
        for index, line in enumerate(lines):
            label = font.render(line, True, CARD_INK)
            center = (rect.centerx, top + index * line_height + line_height // 2)
            screen.blit(label, label.get_rect(center=center))

    def _draw_activity(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, PANEL, ACTIVITY, border_radius=12)
        self._text(
            screen,
            self._heading_font,
            'Recent activity',
            (ACTIVITY.x + 14, ACTIVITY.y + 16),
        )
        line_height = 20
        top = ACTIVITY.y + 52
        count = (ACTIVITY.bottom - 6 - top) // line_height
        for index, event in enumerate(self._shown_history()[-count:]):
            self._text(
                screen,
                self._small_font,
                self._fit(
                    event_text(event, self._table.names),
                    self._small_font,
                    ACTIVITY.width - 28,
                ),
                (ACTIVITY.x + 14, top + index * line_height),
                ACCENT if isinstance(event, RoundStarted | RoundEnded) else MUTED,
            )

    def _draw_controls(self, screen: pygame.Surface, observation: Observation) -> None:
        pygame.draw.rect(screen, PANEL, TURN_BOX, border_radius=12)
        table = self._table
        player = observation.current_player
        hint = None
        if self._animating:
            message = 'Dealing cards...'
        elif table.game.is_finished:
            message = 'Game over'
        elif player is None or player not in table.humans:
            assert player is not None  # unfinished games await a decision
            message = f'{table.names[player]} is deciding...'
        else:
            # With several humans sharing the screen, say whose turn it is.
            turn = (
                'Your turn'
                if len(table.humans) == 1
                else f"{table.names[player]}'s turn"
            )
            hint = 'Click a button or use its shortcut key.'
            match observation.decision:
                case ChooseCard(card=card, first=first):
                    step = 'second' if first is not None else 'first'
                    choice = (
                        f'the {step} card' if card.kind is CardType.SWAP else 'a card'
                    )
                    message = f'{turn}: choose {choice} for {card_label(card)}'
                    hint = 'Click a highlighted card.'
                case FlipSevenBonus():
                    message = f'{turn}: take the bonus or subtract it from a player'
                    hint = 'Click a player, or press their seat number.'
                case ChooseTarget(card=card) if card.kind is CardType.SECOND_CHANCE:
                    message = (
                        f'{turn}: you already have a Second Chance, '
                        'so give this one to another player'
                    )
                    hint = 'Click a player, or press their seat number.'
                case ChooseTarget(card=card):
                    message = f'{turn}: choose a player for {card_label(card)}'
                    hint = 'Click a player, or press their seat number.'
                case HitOrStay(can_stay=False):
                    message = f'{turn}: you must hit'
                case _:
                    message = f'{turn}: hit or stay'
        lines = _wrap(message, self._heading_font, TURN_BOX.width - 32)[:2]
        for index, line in enumerate(lines):
            position = (TURN_BOX.x + 16, TURN_BOX.y + 16 + index * 26)
            self._text(screen, self._heading_font, line, position)
        if hint is not None:
            self._text(
                screen,
                self._small_font,
                hint,
                (TURN_BOX.x + 16, TURN_BOX.y + 16 + len(lines) * 26 + 6),
                MUTED,
            )

    def _draw_history(self, screen: pygame.Surface) -> None:
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 180))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, PANEL_ALT, HISTORY_DIALOG, border_radius=15)
        x = HISTORY_DIALOG.x + 28
        self._text(
            screen, self._title_font, 'Game history', (x, HISTORY_DIALOG.y + 22), ACCENT
        )
        self._text(
            screen,
            self._small_font,
            'Scroll with the mouse wheel, arrow keys or Page Up/Down. L or Esc closes.',
            (x, HISTORY_DIALOG.y + 66),
            MUTED,
        )
        box = _history_box()
        pygame.draw.rect(screen, BACKGROUND, box, border_radius=8)
        events = self._shown_history()
        visible = _history_lines()
        end = len(events) - min(self._history_scroll, len(events))
        for index, event in enumerate(events[max(0, end - visible) : end]):
            is_round = isinstance(event, RoundStarted | RoundEnded)
            self._text(
                screen,
                self._font,
                event_text(event, self._table.names),
                (box.x + (12 if is_round else 32), box.y + 8 + index * HISTORY_LINE),
                ACCENT if is_round else TEXT,
            )
        if end < len(events):
            self._text(
                screen,
                self._small_font,
                f'{len(events) - end} newer below',
                (box.right - 140, box.bottom + 10),
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
        rect = self._overlay(screen, f'Round {result.round_number} complete')
        names = self._table.names
        if result.flip_seven_player is not None:
            message = f'{names[result.flip_seven_player]} got Flip 7!'
            self._text(screen, self._font, message, (rect.x + 28, rect.y + 75), ACTIVE)
        spacing = min(45, (rect.height - 210) // len(names))
        for index, (score, total) in enumerate(zip(result.scores, result.totals)):
            self._text(
                screen,
                self._heading_font,
                f'{names[index]}:  {score:+d}    total {total}',
                (rect.x + 28, rect.y + 120 + index * spacing),
            )

    def _draw_game_over(self, screen: pygame.Surface, observation: Observation) -> None:
        rect = self._overlay(screen, 'Game over')
        names = self._table.names
        winners = ', '.join(names[index] for index in observation.winners)
        self._text(
            screen,
            self._heading_font,
            f'Winner: {winners}',
            (rect.x + 28, rect.y + 90),
            ACTIVE,
        )
        spacing = min(35, (rect.height - 235) // len(names))
        for index, player in enumerate(observation.players):
            self._text(
                screen,
                self._font,
                f'{names[index]}: {player.total_score} points',
                (rect.x + 28, rect.y + 145 + index * spacing),
            )

    def _draw_report_dialog(self, screen: pygame.Surface, message: str) -> None:
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 180))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, PANEL_ALT, DIALOG, border_radius=15)
        x = DIALOG.x + 28
        self._text(screen, self._title_font, 'Report a bug', (x, DIALOG.y + 25), ACCENT)
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
            'Enter submits, Shift+Enter starts a new line, Esc cancels.',
            (x, DIALOG.y + 94),
            MUTED,
        )
        box = pygame.Rect(x, DIALOG.y + 125, DIALOG.width - 56, 300)
        pygame.draw.rect(screen, BACKGROUND, box, border_radius=8)
        line_height = self._font.get_linesize()
        visible = (box.height - 20) // line_height
        lines = _wrap(message + '|', self._font, box.width - 24)
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
            and button.action.kind is ActionType.CHOOSE_TARGET
        ):
            if hovered:
                glow = pygame.Surface(button.rect.size, pygame.SRCALPHA)
                pygame.draw.rect(glow, (*ACCENT, 40), glow.get_rect(), border_radius=12)
                screen.blit(glow, button.rect)
            pygame.draw.rect(
                screen,
                ACCENT,
                button.rect,
                width=4 if hovered else 2,
                border_radius=12,
            )
            return
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
