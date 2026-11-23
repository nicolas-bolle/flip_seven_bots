"""Pygame application loop."""

import sys
import traceback
from collections.abc import Sequence
from pathlib import Path

import pygame

from flip_seven_bots.game import VengeanceRules

from .bug_report import write_report
from .common.widgets import make_icon
from .game_scene import GameScene
from .options import parse_options
from .setup_scene import SetupScene
from .table import Table


def _report_crash(table: Table, directory: Path) -> None:
    try:
        path = write_report(
            table,
            "Automatic report: the game crashed.",
            directory,
            error=traceback.format_exc(),
        )
    # The original crash matters more than a failure to report it.
    except Exception as error:  # noqa: BLE001
        print(f"Could not save a crash report: {error!r}", file=sys.stderr)
    else:
        print(f"Crash report saved to {path}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> None:
    """Run setup or a direct game, then process Pygame events until quit.

    A crash after a table is created attempts to save a report before the
    exception is reraised. After initialization, Pygame is shut down on exit.
    """
    options = parse_options(argv)
    table: Table | None = None
    pygame.init()
    try:
        pygame.display.set_icon(make_icon())
        screen = pygame.display.set_mode((1280, 900))
        pygame.display.set_caption("Flip 7")
        clock = pygame.time.Clock()
        if options.show_setup:
            scene: SetupScene | GameScene = SetupScene(
                options.seats, vengeance=options.vengeance, brutal=options.brutal
            )
        else:
            rules = VengeanceRules(brutal=options.brutal) if options.vengeance else None
            table = Table(options.seats, seed=options.seed, rules=rules)
            scene = GameScene(table, report_dir=options.bug_dir)

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
                    if isinstance(scene, SetupScene) and scene.result is not None:
                        result = scene.result
                        rules = (
                            VengeanceRules(brutal=result.brutal)
                            if result.vengeance
                            else None
                        )
                        table = Table(result.seats, seed=options.seed, rules=rules)
                        scene = GameScene(table, report_dir=options.bug_dir)

            if running:
                scene.update(pygame.time.get_ticks())
                scene.render(screen, pygame.mouse.get_pos())
                pygame.display.flip()
                clock.tick(60)
    except Exception:
        if table is not None:
            _report_crash(table, options.bug_dir)
        raise
    finally:
        pygame.quit()
