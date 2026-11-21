"""Pygame application loop."""

import pygame

from .game_scene import GameScene


def main() -> None:
    pygame.init()
    try:
        screen = pygame.display.set_mode((1280, 900))
        pygame.display.set_caption("Flip 7 - Bots")
        clock = pygame.time.Clock()
        scene = GameScene()

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
                scene.render(screen)
                pygame.display.flip()
                clock.tick(60)
    finally:
        pygame.quit()
