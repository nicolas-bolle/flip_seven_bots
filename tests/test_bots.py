from dataclasses import replace

import pytest

from flip_seven_bots.bots import FlipThreeMonteCarloBot, RandomBot, ThresholdBot
from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    Deck,
    Game,
    Observation,
)

HIT = Action(ActionType.HIT)
STAY = Action(ActionType.STAY)
FLIP_THREE = Card(CardType.FLIP_THREE)


def number(value: int) -> Card:
    return Card(CardType.NUMBER, value)


def opening_observation() -> Observation:
    game = Game(3, seed=10)
    assert game.current_player is not None
    return game.observe(game.current_player)


def with_round_score(observation: Observation, score: int) -> Observation:
    players = tuple(
        replace(view, round_score=score) if view.player == observation.player else view
        for view in observation.players
    )
    return replace(observation, players=players)


def test_random_bot_selects_legal_actions_reproducibly() -> None:
    observation = opening_observation()
    first = RandomBot(seed=42)
    second = RandomBot(seed=42)

    first_choices = [first.choose_action(observation) for _ in range(10)]
    assert all(action in observation.legal_actions for action in first_choices)
    assert first_choices == [second.choose_action(observation) for _ in range(10)]


def test_threshold_bot_hits_below_threshold_and_stays_at_threshold() -> None:
    observation = replace(opening_observation(), legal_actions=(HIT, STAY))
    bot = ThresholdBot(30)

    assert bot.choose_action(with_round_score(observation, 29)) == HIT
    assert bot.choose_action(with_round_score(observation, 30)) == STAY


def test_threshold_bot_hits_when_it_cannot_stay() -> None:
    observation = replace(opening_observation(), legal_actions=(HIT,))
    assert ThresholdBot(30).choose_action(with_round_score(observation, 30)) == HIT


def test_threshold_bot_prefers_an_opponent_but_can_target_itself() -> None:
    observation = opening_observation()
    self_target = Action(ActionType.CHOOSE_TARGET, observation.player)
    opponent = Action(ActionType.CHOOSE_TARGET, (observation.player + 1) % 3)
    bot = ThresholdBot(30)

    assert bot.choose_action(
        replace(observation, legal_actions=(self_target, opponent))
    ) == opponent
    assert bot.choose_action(replace(observation, legal_actions=(self_target,))) == self_target


@pytest.mark.parametrize("bot", [RandomBot(), ThresholdBot(30)], ids=["random", "threshold"])
def test_bots_reject_observations_without_legal_actions(bot: RandomBot | ThresholdBot) -> None:
    observation = replace(opening_observation(), legal_actions=())
    with pytest.raises(ValueError, match="no legal actions"):
        bot.choose_action(observation)


def test_threshold_must_not_be_negative() -> None:
    with pytest.raises(ValueError, match="threshold"):
        ThresholdBot(-1)


def test_monte_carlo_bot_targets_itself_when_the_remaining_cards_are_safe() -> None:
    # Player 1 holds a 7 and the unseen cards are 8, 9 and 10 in some order, so
    # flipping three for itself is worth more than giving the cards to player 0.
    game = Game(2, deck=Deck.stacked([number(7), number(4), FLIP_THREE, number(8), number(9), number(10)]))
    game.apply(HIT)
    observation = game.observe(1)
    assert observation.pending_card == FLIP_THREE

    bot = FlipThreeMonteCarloBot(ThresholdBot(30), samples=5, rollout=ThresholdBot(0), seed=0)
    assert ThresholdBot(30).choose_action(observation) == Action(ActionType.CHOOSE_TARGET, 0)
    assert bot.choose_action(observation) == Action(ActionType.CHOOSE_TARGET, 1)


def test_monte_carlo_bot_targets_an_opponent_who_would_bust() -> None:
    game = Game(2, deck=Deck.stacked([number(7), number(4), FLIP_THREE] + [number(4)] * 6))
    game.apply(HIT)
    observation = game.observe(1)

    bot = FlipThreeMonteCarloBot(ThresholdBot(30), samples=5, rollout=ThresholdBot(0), seed=0)
    assert bot.choose_action(observation) == Action(ActionType.CHOOSE_TARGET, 0)


def test_monte_carlo_bot_delegates_other_decisions() -> None:
    class AlwaysStay:
        def choose_action(self, observation: Observation) -> Action:
            return STAY

    observation = replace(opening_observation(), legal_actions=(HIT, STAY))
    assert FlipThreeMonteCarloBot(AlwaysStay()).choose_action(observation) == STAY


def test_monte_carlo_bot_needs_at_least_one_sample() -> None:
    with pytest.raises(ValueError, match="samples"):
        FlipThreeMonteCarloBot(ThresholdBot(30), samples=0)
