"""Pygame application loop."""

from collections.abc import Sequence

import pygame

from .game_scene import GameScene
from .players import parse_seats
from .table import Table


def main(argv: Sequence[str] | None = None) -> None:
    seats = parse_seats(argv)
    pygame.init()
    try:
        screen = pygame.display.set_mode((1280, 900))
        pygame.display.set_caption("Flip 7")
        clock = pygame.time.Clock()
        scene = GameScene(Table(seats))

        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
                ):
                    running = False
                else:
                    scene.handle_event(event)

            if running:
                scene.update(pygame.time.get_ticks())
                scene.render(screen, pygame.mouse.get_pos())
                pygame.display.flip()
                clock.tick(60)
    finally:
        pygame.quit()
