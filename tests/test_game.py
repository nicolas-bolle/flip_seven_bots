from collections import Counter

import pytest

from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardDrawn,
    CardType,
    Deck,
    DiscardShuffled,
    Game,
    PlayerStatus,
    Rules,
)
from flip_seven_bots.game.rules import build_deck, score_cards

HIT = Action(ActionType.HIT)
STAY = Action(ActionType.STAY)
FREEZE = Card(CardType.FREEZE)
FLIP_THREE = Card(CardType.FLIP_THREE)
CHANCE = Card(CardType.SECOND_CHANCE)


def number(value: int) -> Card:
    return Card(CardType.NUMBER, value)


def target(player: int) -> Action:
    return Action(ActionType.CHOOSE_TARGET, player)


def stacked_game(draws: list[Card], player_count: int = 2, **kwargs) -> Game:
    """With the default dealer 0, player 1 is dealt first and acts first."""
    return Game(player_count, deck=Deck.stacked(draws), **kwargs)


def test_deck_has_base_game_composition() -> None:
    counts = Counter(build_deck())
    assert counts.total() == 94
    assert counts[number(0)] == 1
    assert all(counts[number(value)] == value for value in range(1, 13))
    assert counts[FREEZE] == counts[FLIP_THREE] == counts[CHANCE] == 3


def test_multiplier_doubles_numbers_before_adding_modifiers() -> None:
    cards = [number(5), number(11), Card(CardType.MULTIPLY, 2), Card(CardType.ADD, 4)]
    assert score_cards(cards) == 36


@pytest.mark.parametrize(
    ("kind", "target_player"),
    [(ActionType.HIT, 1), (ActionType.STAY, 0), (ActionType.CHOOSE_TARGET, None)],
)
def test_action_has_target_only_when_choosing_one(
    kind: ActionType, target_player: int | None
) -> None:
    with pytest.raises(ValueError, match="target"):
        Action(kind, target_player)


def test_dealer_rotates_and_player_left_of_dealer_starts() -> None:
    game = stacked_game([number(n) for n in range(1, 7)], player_count=3)
    observation = game.observe(0)
    assert observation.dealer == 0
    assert [view.cards for view in observation.players] == [
        (number(3),), (number(1),), (number(2),),
    ]
    assert game.current_player == 1

    for _ in range(3):
        game.apply(STAY)
    observation = game.observe(0)
    assert observation.round_number == 2
    assert observation.dealer == 1
    assert observation.players[2].cards == (number(4),)
    assert game.current_player == 2


def test_deferred_action_and_second_chance_during_flip_three() -> None:
    draws = [number(2), number(4), FLIP_THREE, FREEZE, CHANCE, number(2)]
    game = stacked_game(draws)
    game.apply(HIT)
    game.apply(target(1))

    observation = game.observe(1)
    assert observation.pending_card == FREEZE
    assert observation.players[1].status == PlayerStatus.ACTIVE
    assert observation.discard == (CHANCE, number(2))
    assert CHANCE not in observation.players[1].cards
    assert [e.card for e in observation.events if isinstance(e, CardDrawn)] == draws

    game.apply(target(0))
    assert game.observe(1).players[0].status == PlayerStatus.STAYED
    assert game.current_player == 1


def test_bust_cancels_deferred_actions() -> None:
    game = stacked_game([number(2), number(4), FLIP_THREE, FREEZE, number(2)])
    game.apply(HIT)
    game.apply(target(1))

    observation = game.observe(0)
    assert observation.players[1].status == PlayerStatus.BUSTED
    assert observation.pending_card is None
    assert game.current_player == 0


def test_flip_three_drawn_during_flip_three_resolves_after_the_draws() -> None:
    game = stacked_game(
        [number(2), number(4), FLIP_THREE, FLIP_THREE, number(5), number(6)]
        + [number(7), number(8), number(9)]
    )
    game.apply(HIT)
    game.apply(target(0))

    observation = game.observe(0)
    assert observation.pending_card == FLIP_THREE
    assert observation.current_player == 0
    assert {number(5), number(6)} <= set(observation.players[0].cards)
    assert observation.legal_actions == (target(0), target(1))

    game.apply(target(1))
    assert game.observe(0).players[1].cards[-3:] == (number(7), number(8), number(9))


def test_busted_player_scores_zero() -> None:
    game = stacked_game([number(5), number(3), number(5)])
    game.apply(HIT)
    assert game.observe(0).players[1].round_score == 0

    game.apply(STAY)
    observation = game.observe(0)
    assert observation.last_round is not None
    assert observation.last_round.scores == (3, 0)


def test_second_chance_saves_a_duplicate_number() -> None:
    game = stacked_game([number(7), number(4), CHANCE, number(7)])
    game.apply(HIT)
    game.apply(STAY)
    game.apply(HIT)

    observation = game.observe(1)
    assert observation.players[1].status is PlayerStatus.ACTIVE
    assert observation.players[1].cards == (number(7),)
    assert observation.discard == (CHANCE, number(7))


def test_seven_numbers_end_round_and_award_bonus() -> None:
    game = stacked_game(
        [number(n) for n in (0, 1, 2, 3, 4, 5, 6, 9)], player_count=1
    )
    for _ in range(6):
        game.apply(HIT)

    observation = game.observe(0)
    assert observation.round_number == 2
    assert observation.last_round is not None
    assert observation.last_round.scores == (36,)
    assert observation.last_round.flip_seven_player == 0


def test_seven_numbers_during_flip_three_end_round_immediately() -> None:
    draws = [number(n) for n in (0, 1, 2, 3)] + [FLIP_THREE]
    draws += [number(n) for n in (4, 5, 6, 9)]
    game = stacked_game(draws, player_count=1)
    for _ in range(4):
        game.apply(HIT)
    game.apply(target(0))

    observation = game.observe(0)
    assert observation.last_round is not None
    assert observation.last_round.flip_seven_player == 0
    assert observation.last_round.scores == (21 + 15,)
    assert observation.players[0].cards == (number(9),)


def test_only_active_player_must_target_themselves() -> None:
    game = stacked_game([number(3), number(4), FREEZE])
    game.apply(STAY)
    game.apply(HIT)

    observation = game.observe(0)
    assert observation.pending_card == FREEZE
    assert observation.legal_actions == (target(0),)
    game.apply(target(0))
    assert game.observe(0).last_round is not None


def test_illegal_decision_is_rejected() -> None:
    game = stacked_game([number(2), number(4)])
    with pytest.raises(ValueError, match="illegal action"):
        game.apply(target(0))


def test_second_chance_must_be_given_to_an_eligible_player() -> None:
    game = stacked_game([CHANCE, number(4), CHANCE])

    game.apply(HIT)
    observation = game.observe(1)
    assert observation.pending_card == CHANCE
    assert observation.legal_actions == (target(0),)

    game.apply(target(0))
    observation = game.observe(0)
    assert observation.players[1].cards.count(CHANCE) == 1
    assert observation.players[0].cards.count(CHANCE) == 1
    assert game.current_player == 0


def test_extra_second_chance_is_discarded_if_no_recipient() -> None:
    game = stacked_game([CHANCE, CHANCE], player_count=1)

    game.apply(HIT)
    observation = game.observe(0)
    assert observation.players[0].cards == (CHANCE,)
    assert observation.discard == (CHANCE,)
    assert observation.pending_card is None
    assert STAY in observation.legal_actions


def test_discard_is_reshuffled_for_next_round() -> None:
    game = stacked_game([number(2), number(4)])
    game.apply(STAY)
    game.apply(STAY)

    observation = game.observe(0)
    assert observation.round_number == 2
    assert observation.last_round is not None
    assert observation.last_round.scores == (4, 2)
    assert observation.discard == ()
    assert {player.cards for player in observation.players} == {(number(2),), (number(4),)}
    assert sum(isinstance(event, DiscardShuffled) for event in observation.events) == 1


@pytest.mark.parametrize(
    ("draws", "winners"),
    [([number(5), number(5)], (0, 1)), ([number(5), number(3)], (1,))],
    ids=["tie", "single-winner"],
)
def test_match_ends_after_round_reaching_target(
    draws: list[Card], winners: tuple[int, ...]
) -> None:
    game = stacked_game(draws, rules=Rules(target_score=5))

    game.apply(STAY)
    assert not game.is_finished
    game.apply(STAY)

    observation = game.observe(0)
    assert game.winners == observation.winners == winners
    assert observation.current_player is None
    assert observation.legal_actions == ()
    with pytest.raises(ValueError, match="illegal action"):
        game.apply(HIT)


@pytest.mark.parametrize(
    ("player_count", "dealer", "seed", "message"),
    [
        (0, 0, None, "player_count"),
        (2, -1, None, "dealer"),
        (2, 2, None, "dealer"),
        (2, 0, 1, "deck or a seed"),
    ],
)
def test_invalid_game_setup(
    player_count: int, dealer: int, seed: int | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Game(player_count, dealer=dealer, seed=seed, deck=Deck.stacked([number(1)] * 2))


@pytest.mark.parametrize("player", [-1, 2])
def test_invalid_observer(player: int) -> None:
    game = Game(2, seed=42)
    with pytest.raises(ValueError, match="player"):
        game.observe(player)


def test_draw_fails_if_deck_and_discard_are_exhausted() -> None:
    game = stacked_game([number(2)], player_count=1)
    with pytest.raises(RuntimeError, match="no cards are available"):
        game.apply(HIT)


def test_freezing_player_during_initial_deal_skips_their_deal() -> None:
    game = stacked_game([FREEZE, number(9)])
    assert game.observe(1).pending_card == FREEZE

    game.apply(target(0))
    observation = game.observe(1)
    assert observation.players[0].status is PlayerStatus.STAYED
    assert observation.players[0].cards == (FREEZE,)
    assert observation.players[1].cards == ()
    assert observation.legal_actions == (HIT,)

    game.apply(HIT)
    assert game.observe(1).players[1].cards == (number(9),)
