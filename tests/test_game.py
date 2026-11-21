import unittest
from unittest.mock import patch

from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    EventType,
    Game,
    PlayerStatus,
)
from flip_seven_bots.game.rules import build_deck, score_cards


def number(value: int) -> Card:
    return Card(CardType.NUMBER, value)


def game_with_draws(draws: list[Card], player_count: int = 2) -> Game:
    with (
        patch("flip_seven_bots.game.engine.build_deck", return_value=list(reversed(draws))),
        patch("flip_seven_bots.game.engine.Random.shuffle"),
    ):
        return Game(player_count)


class RulesTests(unittest.TestCase):
    def test_deck_and_scoring(self) -> None:
        deck = build_deck()
        self.assertEqual(len(deck), 94)
        self.assertEqual(deck.count(number(0)), 1)
        self.assertEqual(deck.count(number(12)), 12)
        self.assertEqual(
            score_cards([number(5), number(11), Card(CardType.MULTIPLY, 2), Card(CardType.ADD, 4)]),
            36,
        )

    def test_deferred_action_and_second_chance_during_flip_three(self) -> None:
        game = game_with_draws([
            number(2), number(4), Card(CardType.FLIP_THREE),
            Card(CardType.FREEZE), Card(CardType.SECOND_CHANCE), number(2),
        ])
        game.apply(Action(ActionType.HIT))
        game.apply(Action(ActionType.CHOOSE_TARGET, 1))

        observation = game.observe(1)
        self.assertEqual(observation.pending_card, Card(CardType.FREEZE))
        self.assertEqual(observation.players[1].status, PlayerStatus.ACTIVE)
        self.assertEqual(observation.discard_count, 2)
        self.assertNotIn(Card(CardType.SECOND_CHANCE), observation.players[1].cards)
        self.assertEqual(
            [event.card for event in observation.events if event.kind is EventType.CARD_DRAWN],
            [number(2), number(4), Card(CardType.FLIP_THREE),
             Card(CardType.FREEZE), Card(CardType.SECOND_CHANCE), number(2)],
        )

        game.apply(Action(ActionType.CHOOSE_TARGET, 0))
        self.assertEqual(game.observe(1).players[0].status, PlayerStatus.STAYED)
        self.assertEqual(game.current_player, 1)

    def test_bust_cancels_deferred_actions(self) -> None:
        game = game_with_draws([
            number(2), number(4), Card(CardType.FLIP_THREE),
            Card(CardType.FREEZE), number(2),
        ])
        game.apply(Action(ActionType.HIT))
        game.apply(Action(ActionType.CHOOSE_TARGET, 1))

        observation = game.observe(0)
        self.assertEqual(observation.players[1].status, PlayerStatus.BUSTED)
        self.assertIsNone(observation.pending_card)
        self.assertEqual(game.current_player, 0)

    def test_seven_ends_round_and_awards_bonus(self) -> None:
        game = game_with_draws(
            [number(0), number(1), number(2), number(3), number(4),
             number(5), number(6), number(9)],
            player_count=1,
        )
        for _ in range(6):
            game.apply(Action(ActionType.HIT))

        observation = game.observe(0)
        self.assertEqual(observation.round_number, 2)
        self.assertIsNotNone(observation.last_round)
        assert observation.last_round is not None
        self.assertEqual(observation.last_round.scores, (36,))
        self.assertEqual(observation.last_round.flip_seven_player, 0)

    def test_illegal_decision_is_rejected(self) -> None:
        game = game_with_draws([number(2), number(4)])
        with self.assertRaises(ValueError):
            game.apply(Action(ActionType.CHOOSE_TARGET, 0))


if __name__ == "__main__":
    unittest.main()
