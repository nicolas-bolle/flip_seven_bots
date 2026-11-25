"""Drawing helpers shared by the game and tournament screens."""

import pygame

from .theme import (
    ACCENT,
    ACTIVE,
    BACKGROUND,
    BUTTON,
    MUTED,
    PANEL,
    PANEL_ALT,
    TEXT,
)

CARD_FACE = (232, 224, 193)
CARD_INK = (25, 45, 46)


def make_icon(size: int = 64, *, crown: bool = False) -> pygame.Surface:
    """Draw the window icon: a cream "7" card fanned over a gold card.

    With ``crown``, a small gold crown sits tilted on the 7 (the tournament
    icon). Shapes are drawn with lines and polygons rather than a font, so
    this works before ``pygame.font`` is initialized.
    """
    icon = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(icon, BACKGROUND, icon.get_rect(), border_radius=size // 5)
    width, height = size * 9 // 20, size * 13 // 20
    seven = [
        (width * 0.25, height * 0.28),
        (width * 0.75, height * 0.28),
        (width * 0.42, height * 0.75),
    ]
    for color, angle, offset in ((ACCENT, 14, -size // 9), (CARD_FACE, -8, size // 12)):
        card = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(card, color, card.get_rect(), border_radius=size // 12)
        if color == CARD_FACE:
            pygame.draw.lines(card, CARD_INK, False, seven, max(2, size // 11))
        card = pygame.transform.rotozoom(card, angle, 1)
        center = (size // 2 + offset, size // 2)
        icon.blit(card, card.get_rect(center=center))
    if crown:
        _draw_crown(icon, size)
    return icon


def _draw_crown(icon: pygame.Surface, size: int) -> None:
    width, height = size * 0.34, size * 0.24
    points = [
        (0.0, 1.0),
        (0.0, 0.2),
        (0.27, 0.55),
        (0.5, 0.0),
        (0.73, 0.55),
        (1.0, 0.2),
        (1.0, 1.0),
    ]
    crown = pygame.Surface((width + 2, height + 2), pygame.SRCALPHA)
    outline = [(1 + x * width, 1 + y * height) for x, y in points]
    pygame.draw.polygon(crown, ACCENT, outline)
    pygame.draw.polygon(crown, CARD_INK, outline, max(1, size // 40))
    crown = pygame.transform.rotozoom(crown, -25, 1)
    icon.blit(crown, crown.get_rect(center=(size * 0.74, size * 0.18)))


def draw_text(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    pos: tuple[int, int],
    color: tuple[int, int, int] = TEXT,
) -> None:
    screen.blit(font.render(text, True, color), pos)


def draw_button(
    screen: pygame.Surface,
    font: pygame.font.Font,
    rect: pygame.Rect,
    label: str,
    selected: bool = False,
    *,
    disabled: bool = False,
) -> None:
    pygame.draw.rect(screen, PANEL if disabled else BUTTON, rect, border_radius=8)
    if selected:
        pygame.draw.rect(screen, ACTIVE, rect, width=2, border_radius=8)
    text = font.render(label, True, MUTED if disabled else TEXT)
    screen.blit(text, text.get_rect(center=rect.center))


def draw_field(
    screen: pygame.Surface,
    font: pygame.font.Font,
    rect: pygame.Rect,
    value: str,
    focused: bool,
) -> None:
    pygame.draw.rect(screen, PANEL_ALT, rect, border_radius=8)
    if focused:
        pygame.draw.rect(screen, ACTIVE, rect, width=2, border_radius=8)
    draw_text(
        screen, font, value + ('|' if focused else ''), (rect.x + 12, rect.y + 13)
    )
