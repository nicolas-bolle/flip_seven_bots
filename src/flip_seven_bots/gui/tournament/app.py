"""Pygame application loop for tournaments."""

import pygame

from flip_seven_bots.tournament.config import TournamentOptions

from ..common.widgets import make_icon
from .run_scene import TournamentScene
from .setup_scene import TournamentSetupScene


def main(options: TournamentOptions, *, show_setup: bool = False) -> None:
    """Open the tournament window with these settings, on setup or running.

    A running tournament is stopped when the window closes. Command-line
    options are parsed by ``flip7 tournament`` (see ``tournament.cli``).
    """
    pygame.init()
    scene: TournamentSetupScene | TournamentScene | None = None
    try:
        pygame.display.set_icon(make_icon(crown=True))
        screen = pygame.display.set_mode((1280, 900))
        pygame.display.set_caption('Flip 7 tournament')
        clock = pygame.time.Clock()
        scene = (
            TournamentSetupScene(options) if show_setup else TournamentScene(options)
        )
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN
                    and event.key == pygame.K_ESCAPE
                    and not scene.dialog_open
                ):
                    running = False
                else:
                    scene.handle_event(event)
            if not running:
                break
            if isinstance(scene, TournamentSetupScene) and scene.result is not None:
                options = scene.result
                scene = TournamentScene(options)
            elif isinstance(scene, TournamentScene) and scene.restart:
                scene = TournamentSetupScene(options)
            scene.update(pygame.time.get_ticks())
            scene.render(screen, pygame.mouse.get_pos())
            pygame.display.flip()
            clock.tick(60)
    finally:
        if isinstance(scene, TournamentScene):
            scene.close()
        pygame.quit()
