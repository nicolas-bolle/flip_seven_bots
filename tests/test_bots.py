from dataclasses import replace
from random import Random

import pytest

from flip_seven_bots.bots import (
    ExpectedValueBot,
    RandomBot,
    ThresholdBot,
    policies,
    rollouts,
)
from flip_seven_bots.bots.registry import kinds, parse_config
from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    ChooseTarget,
    Deck,
    Game,
    HitOrStay,
    Observation,
    Rules,
    VengeanceRules,
)

HIT = Action(ActionType.HIT)
STAY = Action(ActionType.STAY)
FLIP_THREE = Card(CardType.FLIP_THREE)
FREEZE = Card(CardType.FREEZE)


@pytest.mark.parametrize("kind", [kind.kind for kind in kinds()])
@pytest.mark.parametrize("mode", ["base", "vengeance", "brutal"])
def test_registered_bots_play_legal_reproducible_games(kind: str, mode: str) -> None:
    config = parse_config(kind)
    rules = (
        Rules(target_score=25)
        if mode == "base"
        else VengeanceRules(target_score=25, brutal=mode == "brutal")
    )

    def play() -> list[Action]:
        game = Game(2, seed=13, rules=rules)
        bots = [config(1), config(2)]
        actions = []
        while not game.is_finished:
            assert len(actions) < 1000
            player = game.current_player
            assert player is not None
            observation = game.observe(player)
            action = bots[player].choose_action(observation)
            assert action in observation.legal_actions
            actions.append(action)
            game.apply(action)
        return actions

    assert play() == play()


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
    observation = opening_observation()
    observation = replace(observation, decision=HitOrStay(observation.player, True))
    bot = ThresholdBot(30)

    assert bot.choose_action(with_round_score(observation, 29)) == HIT
    assert bot.choose_action(with_round_score(observation, 30)) == STAY


def test_threshold_bot_hits_when_it_cannot_stay() -> None:
    observation = opening_observation()
    observation = replace(observation, decision=HitOrStay(observation.player, False))
    assert ThresholdBot(30).choose_action(with_round_score(observation, 30)) == HIT


def test_threshold_bot_prefers_an_opponent_but_can_target_itself() -> None:
    observation = opening_observation()
    me, opponent = observation.player, (observation.player + 1) % 3
    bot = ThresholdBot(30)

    both = replace(observation, decision=ChooseTarget(me, FREEZE, (me, opponent)))
    assert bot.choose_action(both) == Action(ActionType.CHOOSE_TARGET, opponent)
    only_me = replace(observation, decision=ChooseTarget(me, FREEZE, (me,)))
    assert bot.choose_action(only_me) == Action(ActionType.CHOOSE_TARGET, me)


@pytest.mark.parametrize(
    "bot", [RandomBot(), ThresholdBot(30)], ids=["random", "threshold"]
)
def test_bots_reject_observations_without_legal_actions(
    bot: RandomBot | ThresholdBot,
) -> None:
    observation = replace(opening_observation(), decision=None)
    with pytest.raises(ValueError, match="no legal actions"):
        bot.choose_action(observation)


def test_threshold_must_not_be_negative() -> None:
    with pytest.raises(ValueError, match="threshold"):
        ThresholdBot(-1)


def test_rollouts_target_self_with_flip_three_when_the_remaining_cards_are_safe() -> (
    None
):
    # Player 1 holds a 7 and the unseen cards are 8, 9, and 10 in some order, so
    # flipping three for itself is worth more than giving the cards to player 0.
    game = Game(
        2,
        deck=Deck.stacked(
            [number(7), number(4), FLIP_THREE, number(8), number(9), number(10)]
        ),
    )
    game.apply(HIT)
    observation = game.observe(1)
    assert observation.decision == ChooseTarget(1, FLIP_THREE, (0, 1))

    assert ThresholdBot(30).choose_action(observation) == Action(
        ActionType.CHOOSE_TARGET, 0
    )
    best = rollouts.best_action(observation, ThresholdBot(0), samples=5, rng=Random(0))
    assert best == Action(ActionType.CHOOSE_TARGET, 1)


def test_rollouts_target_an_opponent_who_would_bust() -> None:
    game = Game(
        2, deck=Deck.stacked([number(7), number(4), FLIP_THREE] + [number(4)] * 6)
    )
    game.apply(HIT)
    observation = game.observe(1)

    best = rollouts.best_action(observation, ThresholdBot(0), samples=5, rng=Random(0))
    assert best == Action(ActionType.CHOOSE_TARGET, 0)


def test_rollouts_evaluate_hit_or_stay_decisions() -> None:
    # Every unseen card duplicates the 7 already held, so hitting always busts.
    game = Game(1, deck=Deck.stacked([number(7)] * 5))
    observation = game.observe(0)
    assert observation.decision == HitOrStay(0, True)

    assert (
        rollouts.best_action(observation, ThresholdBot(0), samples=3, rng=Random(0))
        == STAY
    )


def test_rollouts_need_at_least_one_sample() -> None:
    with pytest.raises(ValueError, match="samples"):
        rollouts.best_action(
            opening_observation(), ThresholdBot(0), samples=0, rng=Random(0)
        )


@pytest.mark.parametrize(
    ("unseen", "expected", "action"),
    [((5, 3), 4, STAY), ((5, 3, 3), 16 / 3, HIT)],
    ids=["bust-risk-too-high", "worth-the-risk"],
)
def test_expected_value_bot_compares_hit_average_with_current_score(
    unseen: tuple[int, ...], expected: float, action: Action
) -> None:
    # Holding a 5: drawing the other 5 busts (0), while a 3 makes 8.
    game = Game(1, deck=Deck.stacked([number(5)] + [number(v) for v in unseen]))
    observation = game.observe(0)
    decision = observation.decision
    assert isinstance(decision, HitOrStay)

    assert policies.expected_hit_score(observation, decision) == pytest.approx(expected)
    assert ExpectedValueBot().choose_action(observation) == action
