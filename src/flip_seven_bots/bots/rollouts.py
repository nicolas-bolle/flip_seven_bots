"""Evaluate actions by simulating the rest of the round on sampled decks."""

from collections.abc import Sequence
from random import Random
from typing import TYPE_CHECKING

from flip_seven_bots.game import Action, Observation
from flip_seven_bots.simulation import run

from .policies import acting_decision

if TYPE_CHECKING:
    from .base import Bot


def estimate(
    observation: Observation, action: Action, rollout: Bot, seeds: Sequence[int]
) -> float:
    """Average round margin after taking ``action``, over one sampled deck per seed.

    For each seed, the hidden deck order is resampled, ``action`` is applied, and
    the round is played out with ``rollout`` controlling every seat. The margin
    is the observing player's round score minus the best opponent's.
    """
    if not seeds:
        raise ValueError("at least one seed is required")
    me = observation.player
    bots = [rollout] * len(observation.players)
    total = 0
    for seed in seeds:
        game = observation.sample_game(Random(seed))
        round_number = game.round_number
        game.apply(action)
        run(game, bots, stop=lambda g, start=round_number: g.round_number != start)
        result = game.last_round
        assert result is not None and result.round_number == round_number
        opponents = (
            score for player, score in enumerate(result.scores) if player != me
        )
        total += result.scores[me] - max(opponents, default=0)
    return total / len(seeds)


def best_action(
    observation: Observation, rollout: Bot, *, samples: int, rng: Random
) -> Action:
    """Choose the legal action with the best ``estimate``, for any kind of decision.

    Every action is evaluated on the same ``samples`` decks (common random
    numbers). A lone legal action is returned without simulating.
    """
    if samples < 1:
        raise ValueError("samples must be at least one")
    actions = acting_decision(observation).actions
    if len(actions) == 1:
        return actions[0]
    seeds = [rng.getrandbits(64) for _ in range(samples)]
    return max(
        actions, key=lambda action: estimate(observation, action, rollout, seeds)
    )
