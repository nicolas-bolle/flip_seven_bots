"""Simple baseline bots for experiments."""

from random import Random
from typing import assert_never

from flip_seven_bots.game import (
    Action,
    ChooseCard,
    ChooseTarget,
    FlipSevenBonus,
    HitOrStay,
    Observation,
)

from .policies import (
    acting_decision,
    first_legal,
    maximize_expected_score,
    prefer_opponent,
    random_legal,
    stay_at_threshold,
)


class RandomBot:
    """Choose uniformly among legal actions, using an independent random seed."""

    def __init__(self, seed: int | None = None):
        self._random = Random(seed)

    def choose_action(self, observation: Observation) -> Action:
        """Choose a legal action at random; reject observations without choices."""
        return random_legal(observation, self._random)


class ThresholdBot:
    """Stay at the threshold round score and otherwise hit when possible.

    For target choices, prefer another player if available. For card choices
    and the Flip 7 bonus, choose the first legal action.
    """

    def __init__(self, threshold: int):
        if threshold < 0:
            raise ValueError("threshold must not be negative")
        self.threshold = threshold

    def choose_action(self, observation: Observation) -> Action:
        """Apply the threshold or choose a legal action for a card effect."""
        decision = acting_decision(observation)
        match decision:
            case HitOrStay():
                return stay_at_threshold(observation, decision, self.threshold)
            case ChooseTarget():
                return prefer_opponent(decision)
            case ChooseCard() | FlipSevenBonus():
                return first_legal(observation)
            case _:
                assert_never(decision)


class ExpectedValueBot:
    """Hit or stay to maximize the expected round score one card ahead.

    Hitting is compared with staying by averaging the outcome of the next card
    over the cards remaining in the deck. Target choices prefer another player,
    and card and bonus choices take the first legal action.
    """

    def choose_action(self, observation: Observation) -> Action:
        """Compare expected scores for hit/stay; use simple rules for card effects."""
        decision = acting_decision(observation)
        match decision:
            case HitOrStay():
                return maximize_expected_score(observation, decision)
            case ChooseTarget():
                return prefer_opponent(decision)
            case ChooseCard() | FlipSevenBonus():
                return first_legal(observation)
            case _:
                assert_never(decision)
