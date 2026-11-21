from dataclasses import replace

import pytest

from flip_seven_bots.bots import RandomBot, ThresholdBot
from flip_seven_bots.game import Action, ActionType, Game


def test_random_bot_selects_legal_actions_reproducibly() -> None:
    game = Game(3, seed=10)
    assert game.current_player is not None
    observation = game.observe(game.current_player)
    first = RandomBot(seed=42)
    second = RandomBot(seed=42)

    first_choices = [first.choose_action(observation) for _ in range(10)]
    assert all(action in observation.legal_actions for action in first_choices)
    assert first_choices == [second.choose_action(observation) for _ in range(10)]


def test_threshold_bot_hits_below_threshold_and_stays_at_threshold() -> None:
    game = Game(3, seed=10)
    assert game.current_player is not None
    observation = game.observe(game.current_player)
    player = observation.player
    hit = Action(ActionType.HIT)
    stay = Action(ActionType.STAY)
    players = tuple(
        replace(view, round_score=29) if view.player == player else view
        for view in observation.players
    )
    observation = replace(observation, players=players, legal_actions=(hit, stay))
    bot = ThresholdBot(30)

    assert bot.choose_action(observation) == hit
    players = tuple(
        replace(view, round_score=30) if view.player == player else view
        for view in observation.players
    )
    assert bot.choose_action(replace(observation, players=players)) == stay
    assert bot.choose_action(replace(observation, players=players, legal_actions=(hit,))) == hit


def test_threshold_bot_prefers_an_opponent_but_can_target_itself() -> None:
    game = Game(3, seed=10)
    assert game.current_player is not None
    observation = game.observe(game.current_player)
    self_target = Action(ActionType.CHOOSE_TARGET, observation.player)
    opponent = Action(ActionType.CHOOSE_TARGET, (observation.player + 1) % 3)
    bot = ThresholdBot(30)

    assert bot.choose_action(
        replace(observation, legal_actions=(self_target, opponent))
    ) == opponent
    assert bot.choose_action(replace(observation, legal_actions=(self_target,))) == self_target


def test_bots_reject_observations_without_legal_actions() -> None:
    game = Game(3, seed=10)
    assert game.current_player is not None
    observation = replace(game.observe(game.current_player), legal_actions=())
    for bot in (RandomBot(), ThresholdBot(30)):
        with pytest.raises(ValueError, match="no legal actions"):
            bot.choose_action(observation)
    with pytest.raises(ValueError, match="threshold"):
        ThresholdBot(-1)
