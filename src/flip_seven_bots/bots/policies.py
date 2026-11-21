"""Small, reusable decision rules for composing bots.

Each function is pure given its arguments: randomness comes only from an
explicit ``rng``. Functions for a specific kind of decision take that decision,
already narrowed by the caller, alongside the observation.
"""

from random import Random

from flip_seven_bots.game import Action, ChooseTarget, Decision, HitOrStay, Observation


def acting_decision(observation: Observation) -> Decision:
    """Return the decision ``observation.player`` must make.

    Raises ``ValueError`` when that player has nothing to decide.
    """
    decision = observation.decision
    if decision is None or decision.player != observation.player:
        raise ValueError("the observation has no legal actions")
    return decision


def first_legal(observation: Observation) -> Action:
    """Choose the first legal action."""
    return acting_decision(observation).actions[0]


def random_legal(observation: Observation, rng: Random) -> Action:
    """Choose uniformly among the legal actions."""
    return rng.choice(acting_decision(observation).actions)


def stay_at_threshold(observation: Observation, decision: HitOrStay, threshold: int) -> Action:
    """Stay once the round score reaches ``threshold`` if allowed; otherwise hit."""
    if decision.can_stay and observation.players[decision.player].round_score >= threshold:
        return decision.stay()
    return decision.hit()


def prefer_opponent(decision: ChooseTarget) -> Action:
    """Target the first eligible opponent, or the deciding player if no one else is eligible."""
    target = next((t for t in decision.targets if t != decision.player), decision.targets[0])
    return decision.choose(target)
