"""Drawing helpers shared by the setup and tournament screens."""

import pygame

from .game_scene import ACTIVE, BUTTON, MUTED, PANEL, PANEL_ALT, TEXT


def draw_text(
    screen: pygame.Surface, font: pygame.font.Font, text: str,
    pos: tuple[int, int], color: tuple[int, int, int] = TEXT,
) -> None:
    screen.blit(font.render(text, True, color), pos)


def draw_button(
    screen: pygame.Surface, font: pygame.font.Font, rect: pygame.Rect, label: str,
    selected: bool = False, *, disabled: bool = False,
) -> None:
    pygame.draw.rect(screen, PANEL if disabled else BUTTON, rect, border_radius=8)
    if selected:
        pygame.draw.rect(screen, ACTIVE, rect, width=2, border_radius=8)
    text = font.render(label, True, MUTED if disabled else TEXT)
    screen.blit(text, text.get_rect(center=rect.center))


def draw_field(
    screen: pygame.Surface, font: pygame.font.Font, rect: pygame.Rect, value: str,
    focused: bool,
) -> None:
    pygame.draw.rect(screen, PANEL_ALT, rect, border_radius=8)
    if focused:
        pygame.draw.rect(screen, ACTIVE, rect, width=2, border_radius=8)
    draw_text(screen, font, value + ("|" if focused else ""), (rect.x + 12, rect.y + 13))
