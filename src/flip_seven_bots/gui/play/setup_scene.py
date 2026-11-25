"""Interactive game and player setup."""

import argparse
from dataclasses import dataclass

import pygame

from flip_seven_bots.bots.registry import config_for, kinds

from ..common.theme import ACCENT, BACKGROUND, MUTED, TEXT
from ..common.widgets import draw_button, draw_field, draw_text
from .options import (
    MAX_PLAYERS,
    _bot_seat,
    _human_seat,
    _number_duplicates,
    default_seats,
)
from .table import Seat

BASE_BUTTON = pygame.Rect(90, 150, 260, 52)
VENGEANCE_BUTTON = pygame.Rect(365, 150, 330, 52)
BRUTAL_BUTTON = pygame.Rect(710, 150, 270, 52)
ADD_BUTTON = pygame.Rect(90, 735, 220, 52)
START_BUTTON = pygame.Rect(1000, 790, 190, 60)
MAX_NAME_LENGTH = 24
MAX_PARAMETER_LENGTH = 100


@dataclass
class _PlayerSetting:
    name: str
    kind: str
    parameter: str = ''


@dataclass(frozen=True)
class SetupResult:
    """Validated seats and game mode returned when the user starts a game."""

    seats: list[Seat]
    vengeance: bool
    brutal: bool


def _initial_player(seat: Seat) -> _PlayerSetting:
    if seat.bot is None:
        return _PlayerSetting(seat.name, 'human')
    kind, _, parameter = config_for(seat.bot).spec.partition(':')
    return _PlayerSetting(seat.name, kind, parameter)


def _row_rects(index: int) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect]:
    y = 310 + index * 64
    return (
        pygame.Rect(90, y, 320, 48),
        pygame.Rect(425, y, 250, 48),
        pygame.Rect(690, y, 180, 48),
        pygame.Rect(885, y, 150, 48),
    )


class SetupScene:
    """Edit game mode and seats before constructing the table.

    ``result`` remains ``None`` until Start validates the settings; invalid
    input instead sets ``error`` for display.
    """

    def __init__(
        self,
        seats: list[Seat] | None = None,
        *,
        vengeance: bool = False,
        brutal: bool = False,
    ) -> None:
        self.players = [_initial_player(seat) for seat in (seats or default_seats())]
        self.vengeance = vengeance
        self.brutal = brutal
        self.result: SetupResult | None = None
        self.error: str | None = None
        self._focus: tuple[int, str] | None = None
        self._title_font = pygame.font.Font(None, 52)
        self._heading_font = pygame.font.Font(None, 32)
        self._font = pygame.font.Font(None, 26)
        self._small_font = pygame.font.Font(None, 21)

    @property
    def dialog_open(self) -> bool:
        """Setup has no modal dialog, so Escape may quit the application."""
        return False

    def handle_event(self, event: pygame.event.Event) -> None:
        """Apply input to the selected field, settings, or Start action."""
        if event.type == pygame.TEXTINPUT and self._focus is not None:
            index, field = self._focus
            player = self.players[index]
            if field == 'name':
                player.name = (player.name + event.text)[:MAX_NAME_LENGTH]
            else:
                player.parameter = (player.parameter + event.text)[
                    :MAX_PARAMETER_LENGTH
                ]
            self.error = None
            return
        if event.type == pygame.KEYDOWN:
            if (
                event.key == pygame.K_a
                and getattr(event, 'mod', 0) & pygame.KMOD_CTRL
                and self._focus is not None
            ):
                index, field = self._focus
                if field == 'name':
                    self.players[index].name = ''
                else:
                    self.players[index].parameter = ''
                self.error = None
            elif event.key == pygame.K_BACKSPACE and self._focus is not None:
                index, field = self._focus
                player = self.players[index]
                if field == 'name':
                    player.name = player.name[:-1]
                else:
                    player.parameter = player.parameter[:-1]
                self.error = None
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._start()
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        pos = event.pos
        self._focus = None
        if BASE_BUTTON.collidepoint(pos):
            self.vengeance = self.brutal = False
        elif VENGEANCE_BUTTON.collidepoint(pos):
            self.vengeance = True
        elif BRUTAL_BUTTON.collidepoint(pos) and self.vengeance:
            self.brutal = not self.brutal
        elif ADD_BUTTON.collidepoint(pos) and len(self.players) < MAX_PLAYERS:
            self.players.append(
                _PlayerSetting(f'Player {len(self.players) + 1}', 'human')
            )
        elif START_BUTTON.collidepoint(pos):
            self._start()
        else:
            for index, player in enumerate(self.players):
                name, kind, parameter, remove = _row_rects(index)
                if name.collidepoint(pos):
                    self._focus = (index, 'name')
                elif kind.collidepoint(pos):
                    names = ('human', *(kind.key for kind in kinds()))
                    player.kind = names[(names.index(player.kind) + 1) % len(names)]
                    player.parameter = ''
                elif (
                    parameter.collidepoint(pos)
                    and player.kind != 'human'
                    and next(k for k in kinds() if k.key == player.kind).parameters
                ):
                    self._focus = (index, 'parameter')
                elif remove.collidepoint(pos) and len(self.players) > 1:
                    self.players.pop(index)
                else:
                    continue
                self.error = None
                break

    def _start(self) -> None:
        seats = []
        try:
            for player in self.players:
                name = _human_seat(player.name).name
                spec = player.kind
                if player.parameter and player.kind != 'human':
                    spec += f':{player.parameter}'
                bot = None if player.kind == 'human' else _bot_seat(spec).bot
                seats.append(Seat(name, bot))
        except argparse.ArgumentTypeError as error:
            self.error = str(error)
            return
        self.result = SetupResult(
            _number_duplicates(seats), self.vengeance, self.brutal
        )

    def update(self, _now: int) -> None:
        """Satisfy the scene interface; setup has no time-dependent updates."""

    def render(
        self, screen: pygame.Surface, _mouse_pos: tuple[int, int] | None = None
    ) -> None:
        """Draw the current settings and any validation error."""
        screen.fill(BACKGROUND)
        self._text(screen, self._title_font, 'GAME SETUP', (90, 45), ACCENT)
        self._text(screen, self._heading_font, 'Game mode', (90, 110))
        self._button(screen, BASE_BUTTON, 'Flip 7', self.vengeance is False)
        self._button(screen, VENGEANCE_BUTTON, 'With a Vengeance', self.vengeance)
        self._button(
            screen,
            BRUTAL_BUTTON,
            f'Brutal: {"on" if self.brutal else "off"}',
            self.brutal,
            disabled=not self.vengeance,
        )
        self._text(screen, self._heading_font, 'Players', (90, 235))
        self._text(screen, self._small_font, 'NAME', (90, 282), MUTED)
        self._text(
            screen, self._small_font, 'TYPE (CLICK TO CHANGE)', (425, 282), MUTED
        )
        self._text(screen, self._small_font, 'PARAMETERS', (690, 282), MUTED)
        for index, player in enumerate(self.players):
            name, kind, parameter, remove = _row_rects(index)
            self._field(screen, name, player.name, self._focus == (index, 'name'))
            definition = next((k for k in kinds() if k.key == player.kind), None)
            self._button(screen, kind, definition.key if definition else 'Human')
            if definition and definition.parameters:
                self._field(
                    screen,
                    parameter,
                    player.parameter,
                    self._focus == (index, 'parameter'),
                )
            else:
                self._text(
                    screen, self._font, '-', (parameter.x + 12, parameter.y + 13), MUTED
                )
            self._button(screen, remove, 'Remove', disabled=len(self.players) == 1)
        self._button(
            screen, ADD_BUTTON, 'Add player', disabled=len(self.players) >= MAX_PLAYERS
        )
        self._button(screen, START_BUTTON, 'Start  [Enter]', selected=True)
        self._text(
            screen,
            self._small_font,
            'Click a name or value to edit. Esc quits.',
            (90, 805),
            MUTED,
        )
        if self.error is not None:
            self._text(screen, self._font, self.error, (90, 850), ACCENT)

    def _text(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        text: str,
        pos: tuple[int, int],
        color: tuple[int, int, int] = TEXT,
    ) -> None:
        draw_text(screen, font, text, pos, color)

    def _button(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        selected: bool = False,
        *,
        disabled: bool = False,
    ) -> None:
        draw_button(screen, self._font, rect, label, selected, disabled=disabled)

    def _field(
        self, screen: pygame.Surface, rect: pygame.Rect, value: str, focused: bool
    ) -> None:
        draw_field(screen, self._font, rect, value, focused)
