"""Small, reusable decision rules for composing bots.

Each function is pure given its arguments: randomness comes only from an
explicit ``rng``. Functions for a specific kind of decision take that decision,
already narrowed by the caller, alongside the observation.
"""

from collections import Counter
from random import Random

from flip_seven_bots.game import (
    Action,
    ChooseTarget,
    Decision,
    FlipSevenBonus,
    Game,
    HitOrStay,
    Observation,
)


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


def expected_hit_score(observation: Observation, decision: HitOrStay) -> float:
    """Average round score from hitting once and then staying, over the possible next cards.

    Each distinct card that could be drawn next is weighted by its count in
    ``draw_pile`` (or in ``discard`` if an empty draw pile would be reshuffled),
    and its effect is scored by the engine. Busting scores what the engine
    awards a busted hand, and Flip 7 includes the bonus. An action card that
    needs a target is scored as the hand before the action resolves.
    """
    pool = observation.draw_pile or observation.discard
    if not pool:
        raise ValueError("no cards are available to draw")
    total = 0
    for card, count in Counter(pool).items():
        # Only the forced card is drawn, so the sampled order of the rest is irrelevant.
        game = observation.sample_game(Random(0), next_draws=(card,))
        game.apply(decision.hit())
        total += count * _round_score_after(game, decision.player, observation.round_number)
    return total / len(pool)


def maximize_expected_score(observation: Observation, decision: HitOrStay) -> Action:
    """Hit only if ``expected_hit_score`` beats the current round score; otherwise stay."""
    if not decision.can_stay:
        return decision.hit()
    stay_score = observation.players[decision.player].round_score
    if expected_hit_score(observation, decision) > stay_score:
        return decision.hit()
    return decision.stay()


def _round_score_after(game: Game, player: int, round_number: int) -> int:
    if isinstance(game.observe(player).decision, FlipSevenBonus):
        game.apply(FlipSevenBonus(player, ()).take())
    result = game.last_round
    if result is not None and result.round_number == round_number:
        return result.scores[player]
    return game.observe(player).players[player].round_score
