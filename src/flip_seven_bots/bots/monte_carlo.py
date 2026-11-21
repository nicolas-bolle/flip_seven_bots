"""A bot that simulates the rest of the round to choose Flip Three targets."""

from random import Random

from flip_seven_bots.game import Action, Card, CardType, Observation
from flip_seven_bots.simulation import run

from .base import Bot
from .simple import ThresholdBot

_FLIP_THREE = Card(CardType.FLIP_THREE)


class FlipThreeMonteCarloBot:
    """Pick the Flip Three target with the best simulated round outcome.

    Each target is scored by sampling the hidden deck order, applying the choice,
    and playing out the round with ``rollout`` controlling every seat. The value of
    a sample is this player's round score minus the best opponent's. All other
    decisions are delegated to ``fallback``.
    """

    def __init__(
        self,
        fallback: Bot,
        *,
        samples: int = 100,
        rollout: Bot | None = None,
        seed: int | None = None,
    ):
        if samples < 1:
            raise ValueError("samples must be at least one")
        self.fallback = fallback
        self.samples = samples
        self.rollout = rollout if rollout is not None else ThresholdBot(25)
        self._random = Random(seed)

    def choose_action(self, observation: Observation) -> Action:
        actions = observation.legal_actions
        if observation.pending_card != _FLIP_THREE or len(actions) < 2:
            return self.fallback.choose_action(observation)
        # Common random numbers: every target is evaluated on the same sampled decks.
        seeds = [self._random.getrandbits(64) for _ in range(self.samples)]
        return max(actions, key=lambda action: self._estimate(observation, action, seeds))

    def _estimate(self, observation: Observation, action: Action, seeds: list[int]) -> float:
        me = observation.player
        bots = [self.rollout] * len(observation.players)
        total = 0
        for seed in seeds:
            game = observation.sample_game(Random(seed))
            round_number = game.round_number
            game.apply(action)
            run(game, bots, stop=lambda g, start=round_number: g.round_number != start)
            result = game.last_round
            assert result is not None and result.round_number == round_number
            opponents = (score for player, score in enumerate(result.scores) if player != me)
            total += result.scores[me] - max(opponents, default=0)
        return total / len(seeds)
