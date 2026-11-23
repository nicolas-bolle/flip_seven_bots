"""Interactive tournament setup."""

from dataclasses import dataclass, replace

import pygame

from flip_seven_bots.bots.registry import default_parameters, kinds
from flip_seven_bots.bots.specs import bot_spec, number_duplicates, parse_bot
from flip_seven_bots.tournament.config import TournamentOptions

from ..common.theme import ACCENT, BACKGROUND, MUTED
from ..common.widgets import draw_button, draw_field, draw_text

BASE_BUTTON = pygame.Rect(90, 135, 260, 52)
VENGEANCE_BUTTON = pygame.Rect(365, 135, 330, 52)
BRUTAL_BUTTON = pygame.Rect(710, 135, 270, 52)
GAMES_FIELD = pygame.Rect(90, 243, 180, 48)
TABLE_FIELD = pygame.Rect(300, 243, 180, 48)
SEED_FIELD = pygame.Rect(510, 243, 180, 48)
JOBS_FIELD = pygame.Rect(720, 243, 180, 48)
ADD_BUTTON = pygame.Rect(90, 800, 220, 48)
START_BUTTON = pygame.Rect(1000, 795, 190, 56)
MAX_BOTS = 10
MAX_NAME_LENGTH = 24
MAX_NUMBER_LENGTH = 6


@dataclass
class _BotSetting:
    name: str
    kind: str
    parameter: str = ""

    @property
    def spec(self) -> str:
        if self.parameter:
            return f"{self.kind}:{self.parameter}"
        return self.kind


def _row_rects(index: int) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect]:
    y = 364 + index * 42
    return (
        pygame.Rect(90, y, 320, 38),
        pygame.Rect(425, y, 250, 38),
        pygame.Rect(690, y, 180, 38),
        pygame.Rect(885, y, 150, 38),
    )


class TournamentSetupScene:
    """Edit the bots and settings of a tournament, starting from ``defaults``.

    ``result`` remains ``None`` until Start validates the settings; invalid
    input instead sets ``error`` for display. Settings without a field here,
    such as the Elo K-factor, are kept from ``defaults``.
    """

    def __init__(self, defaults: TournamentOptions) -> None:
        self._defaults = defaults
        self.bots = []
        for name, bot in defaults.bots.items():
            kind, _, parameter = bot_spec(bot).partition(":")
            self.bots.append(_BotSetting(name, kind, parameter))
        self.vengeance = defaults.vengeance
        self.brutal = defaults.brutal
        self.numbers = {
            "games": str(defaults.games),
            "table": ""
            if defaults.players_per_game is None
            else str(defaults.players_per_game),
            "seed": "" if defaults.seed is None else str(defaults.seed),
            "jobs": str(defaults.jobs),
        }
        self.result: TournamentOptions | None = None
        self.error: str | None = None
        self._focus: tuple[str, int] | None = None
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
            self._set_focused(self._focused_value() + event.text)
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._start()
            elif self._focus is None:
                return
            elif (
                event.key == pygame.K_a and getattr(event, "mod", 0) & pygame.KMOD_CTRL
            ):
                self._set_focused("")
            elif event.key == pygame.K_BACKSPACE:
                self._set_focused(self._focused_value()[:-1])
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._click(event.pos)

    def _focused_value(self) -> str:
        assert self._focus is not None
        field, index = self._focus
        if field in self.numbers:
            return self.numbers[field]
        bot = self.bots[index]
        return bot.name if field == "name" else bot.parameter

    def _set_focused(self, value: str) -> None:
        assert self._focus is not None
        field, index = self._focus
        if field == "name":
            self.bots[index].name = value[:MAX_NAME_LENGTH]
        elif field in self.numbers:
            digits = "".join(char for char in value if char.isdigit())[
                :MAX_NUMBER_LENGTH
            ]
            self.numbers[field] = digits
        else:
            self.bots[index].parameter = value[:100]
        self.error = None

    def _click(self, pos: tuple[int, int]) -> None:
        self._focus = None
        self.error = None
        fields = {
            "games": GAMES_FIELD,
            "table": TABLE_FIELD,
            "seed": SEED_FIELD,
            "jobs": JOBS_FIELD,
        }
        clicked = next(
            (name for name, rect in fields.items() if rect.collidepoint(pos)), None
        )
        if clicked is not None:
            self._focus = (clicked, 0)
        elif BASE_BUTTON.collidepoint(pos):
            self.vengeance = self.brutal = False
        elif VENGEANCE_BUTTON.collidepoint(pos):
            self.vengeance = True
        elif BRUTAL_BUTTON.collidepoint(pos) and self.vengeance:
            self.brutal = not self.brutal
        elif ADD_BUTTON.collidepoint(pos) and len(self.bots) < MAX_BOTS:
            self.bots.append(_BotSetting("Threshold 30", "threshold", "30"))
        elif START_BUTTON.collidepoint(pos):
            self._start()
        else:
            for index, bot in enumerate(self.bots):
                name, kind, parameter, remove = _row_rects(index)
                if name.collidepoint(pos):
                    self._focus = ("name", index)
                elif kind.collidepoint(pos):
                    definitions = kinds()
                    names = tuple(kind.kind for kind in definitions)
                    definition = definitions[(names.index(bot.kind) + 1) % len(names)]
                    bot.kind = definition.kind
                    bot.parameter = default_parameters(definition)
                elif (
                    parameter.collidepoint(pos)
                    and next(k for k in kinds() if k.kind == bot.kind).parameters
                ):
                    self._focus = ("parameter", index)
                elif remove.collidepoint(pos) and len(self.bots) > 2:
                    self.bots.pop(index)
                else:
                    continue
                break

    def _start(self) -> None:
        try:
            self.result = self._validate()
        except ValueError as error:
            self.error = str(error)

    def _validate(self) -> TournamentOptions:
        if any(not bot.name.strip() for bot in self.bots):
            raise ValueError("every bot needs a name")
        names = number_duplicates([bot.name.strip() for bot in self.bots])
        bots = {
            name: parse_bot(setting.spec)[1] for name, setting in zip(names, self.bots)
        }
        games = int(self.numbers["games"] or 0)
        if games < 1:
            raise ValueError("play at least one game")
        table = int(self.numbers["table"]) if self.numbers["table"] else None
        if table is not None and not 2 <= table <= len(bots):
            raise ValueError(f"players per game must be between 2 and {len(bots)}")
        jobs = int(self.numbers["jobs"] or 0)
        if jobs < 1:
            raise ValueError("use at least one worker")
        return replace(
            self._defaults,
            bots=bots,
            games=games,
            players_per_game=table,
            seed=int(self.numbers["seed"]) if self.numbers["seed"] else None,
            vengeance=self.vengeance,
            brutal=self.vengeance and self.brutal,
            jobs=jobs,
        )

    def update(self, _now: int) -> None:
        """Satisfy the scene interface; setup has no time-dependent updates."""

    def render(
        self, screen: pygame.Surface, _mouse_pos: tuple[int, int] | None = None
    ) -> None:
        """Draw the current settings and any validation error."""
        font, small = self._font, self._small_font
        screen.fill(BACKGROUND)
        draw_text(screen, self._title_font, "TOURNAMENT SETUP", (90, 45), ACCENT)
        draw_text(screen, self._heading_font, "Game mode", (90, 95))
        draw_button(screen, font, BASE_BUTTON, "Flip 7", not self.vengeance)
        draw_button(screen, font, VENGEANCE_BUTTON, "With A Vengeance", self.vengeance)
        draw_button(
            screen,
            font,
            BRUTAL_BUTTON,
            f"Brutal: {'on' if self.brutal else 'off'}",
            self.brutal,
            disabled=not self.vengeance,
        )
        labels = (
            ("games", GAMES_FIELD, "GAMES"),
            ("table", TABLE_FIELD, "PER GAME (BLANK = ALL)"),
            ("seed", SEED_FIELD, "SEED (BLANK = RANDOM)"),
            ("jobs", JOBS_FIELD, "WORKERS"),
        )
        for field, rect, label in labels:
            draw_text(screen, small, label, (rect.x, rect.y - 23), MUTED)
            draw_field(
                screen, font, rect, self.numbers[field], self._focus == (field, 0)
            )

        draw_text(screen, self._heading_font, "Bots", (90, 310))
        draw_text(screen, small, "NAME", (90, 342), MUTED)
        draw_text(screen, small, "TYPE (CLICK TO CHANGE)", (425, 342), MUTED)
        draw_text(screen, small, "PARAMETERS", (690, 342), MUTED)
        for index, bot in enumerate(self.bots):
            name, kind, parameter, remove = _row_rects(index)
            draw_field(screen, font, name, bot.name, self._focus == ("name", index))
            definition = next(k for k in kinds() if k.kind == bot.kind)
            draw_button(screen, font, kind, definition.label)
            if definition.parameters:
                focused = self._focus == ("parameter", index)
                draw_field(screen, font, parameter, bot.parameter, focused)
            else:
                draw_text(
                    screen, font, "-", (parameter.x + 12, parameter.y + 10), MUTED
                )
            draw_button(screen, font, remove, "Remove", disabled=len(self.bots) <= 2)
        draw_button(
            screen, font, ADD_BUTTON, "Add bot", disabled=len(self.bots) >= MAX_BOTS
        )
        draw_button(screen, font, START_BUTTON, "Start  [Enter]", selected=True)
        draw_text(
            screen,
            small,
            "Click a field to edit; Ctrl+A clears it. Esc quits.",
            (340, 816),
            MUTED,
        )
        if self.error is not None:
            draw_text(screen, font, self.error, (90, 862), ACCENT)
