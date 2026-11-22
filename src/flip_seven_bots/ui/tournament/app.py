"""Pygame application loop for tournaments."""

import sys
from collections.abc import Sequence

import pygame

from flip_seven_bots.tournament.cli import parse_options

from .run_scene import TournamentScene
from .setup_scene import TournamentSetupScene


def main(argv: Sequence[str] | None = None) -> None:
    """Open tournament setup, or run a tournament directly if any options are given.

    Options are the same as for ``python -m flip_seven_bots.tournament``. A
    running tournament is stopped when the window closes.
    """
    options = parse_options(
        argv,
        prog="python -m flip_seven_bots.ui.tournament",
        description=(
            "Watch a tournament between bots. With no options, configure it on the "
            "setup screen; any options start it immediately."
        ),
    )
    show_setup = not (sys.argv[1:] if argv is None else argv)
    pygame.init()
    scene: TournamentSetupScene | TournamentScene | None = None
    try:
        screen = pygame.display.set_mode((1280, 900))
        pygame.display.set_caption("Flip 7 tournament")
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
