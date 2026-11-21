"""Simple baseline bots for experiments."""

from random import Random

from flip_seven_bots.game import Action, ActionType, Observation


class RandomBot:
    """Choose uniformly among legal actions, using an independent random seed."""

    def __init__(self, seed: int | None = None):
        self._random = Random(seed)

    def choose_action(self, observation: Observation) -> Action:
        """Choose a legal action at random; reject observations without choices."""
        if not observation.legal_actions:
            raise ValueError("the observation has no legal actions")
        return self._random.choice(observation.legal_actions)


class ThresholdBot:
    """Stay at the threshold round score and otherwise hit when possible.

    For target choices, prefer another player if available. For other
    non-hit/stay decisions, choose the first legal action.
    """

    def __init__(self, threshold: int):
        if threshold < 0:
            raise ValueError("threshold must not be negative")
        self.threshold = threshold

    def choose_action(self, observation: Observation) -> Action:
        """Apply the threshold or choose a legal action for a card effect."""
        actions = observation.legal_actions
        if not actions:
            raise ValueError("the observation has no legal actions")
        if actions[0].kind is ActionType.CHOOSE_TARGET:
            return next(
                (action for action in actions if action.target != observation.player),
                actions[0],
            )
        if actions[0].kind is not ActionType.HIT:
            return actions[0]
        stay = Action(ActionType.STAY)
        if (
            stay in actions
            and observation.players[observation.player].round_score >= self.threshold
        ):
            return stay
        return Action(ActionType.HIT)
