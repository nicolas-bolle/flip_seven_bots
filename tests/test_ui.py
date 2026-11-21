import unittest
from unittest.mock import patch

import pygame

from flip_seven_bots.game import Action, ActionType, Card, CardType, Game, PlayerStatus
from flip_seven_bots.ui.game_scene import GameScene


class GameSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.font.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.font.quit()

    def test_human_target_and_bot_turn(self) -> None:
        draws = [
            Card(CardType.NUMBER, 3),
            Card(CardType.NUMBER, 1),
            Card(CardType.NUMBER, 2),
            Card(CardType.FREEZE),
        ]
        with (
            patch("flip_seven_bots.game.engine.build_deck", return_value=list(reversed(draws))),
            patch("flip_seven_bots.game.engine.Random.shuffle"),
        ):
            game = Game(3, dealer=2)

        with (
            patch("flip_seven_bots.ui.game_scene.Game", return_value=game),
            patch("pygame.mouse.get_pos", return_value=(0, 0)),
        ):
            scene = GameScene()
            screen = pygame.Surface((1280, 900))
            scene.render(screen)
            scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
            self.assertEqual(game.observe(0).pending_card, Card(CardType.FREEZE))

            scene.render(screen)
            scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3))
            self.assertEqual(game.observe(0).players[2].status, PlayerStatus.STAYED)
            self.assertEqual(game.current_player, 1)

            scene.render(screen)
            scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
            self.assertEqual(game.current_player, 1)

            with patch(
                "flip_seven_bots.ui.game_scene.RandomBot.choose_action",
                return_value=Action(ActionType.STAY),
            ):
                scene.update(pygame.time.get_ticks() + 1_000)
            self.assertEqual(game.current_player, 0)
            self.assertEqual(game.observe(0).players[1].status, PlayerStatus.STAYED)


if __name__ == "__main__":
    unittest.main()
