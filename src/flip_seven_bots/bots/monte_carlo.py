"""A bot that simulates the rest of the round to choose Flip Three targets."""

from random import Random
from typing import TYPE_CHECKING, assert_never

from flip_seven_bots.game import (
    Action,
    Card,
    CardType,
    ChooseCard,
    ChooseTarget,
    FlipSevenBonus,
    HitOrStay,
    Observation,
)

from . import rollouts
from .policies import acting_decision, first_legal, prefer_opponent, stay_at_threshold
from .simple import ThresholdBot

if TYPE_CHECKING:
    from .base import Bot


class FlipThreeMonteCarloBot:
    """Pick Flip Three targets by simulation and play like a threshold bot otherwise.

    Flip Three targets are chosen with ``rollouts.best_action`` using ``samples``
    sampled decks, with ``rollout`` controlling every seat during simulation.
    Hit/stay uses ``threshold``; other targets prefer an opponent, and card and
    bonus choices take the first legal action.
    """

    def __init__(
        self,
        threshold: int = 25,
        *,
        samples: int = 100,
        rollout: Bot | None = None,
        seed: int | None = None,
    ):
        if threshold < 0:
            raise ValueError("threshold must not be negative")
        if samples < 1:
            raise ValueError("samples must be at least one")
        self.threshold = threshold
        self.samples = samples
        self.rollout = rollout if rollout is not None else ThresholdBot(25)
        self._random = Random(seed)

    def choose_action(self, observation: Observation) -> Action:
        """Simulate Flip Three targets; use simple rules for everything else."""
        decision = acting_decision(observation)
        match decision:
            case ChooseTarget(card=Card(kind=CardType.FLIP_THREE)):
                return rollouts.best_action(
                    observation, self.rollout, samples=self.samples, rng=self._random
                )
            case ChooseTarget():
                return prefer_opponent(decision)
            case HitOrStay():
                return stay_at_threshold(observation, decision, self.threshold)
            case ChooseCard() | FlipSevenBonus():
                return first_legal(observation)
            case _:
                assert_never(decision)
