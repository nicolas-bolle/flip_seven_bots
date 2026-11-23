from collections import Counter

import pytest

from flip_seven_bots.bots import RandomBot, ThresholdBot
from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    ChooseCard,
    ChooseTarget,
    Deck,
    Game,
    HitOrStay,
    PlayerStatus,
    VengeanceRules,
)
from flip_seven_bots.game.rules import build_vengeance_deck, score_vengeance_cards
from flip_seven_bots.simulation import play_game

HIT = Action(ActionType.HIT)
STAY = Action(ActionType.STAY)
ZERO = Card(CardType.ZERO, 0)
UNLUCKY = Card(CardType.UNLUCKY_SEVEN, 7)
LUCKY = Card(CardType.LUCKY_THIRTEEN, 13)
ONE_MORE = Card(CardType.JUST_ONE_MORE)
FLIP_FOUR = Card(CardType.FLIP_FOUR)
SWAP = Card(CardType.SWAP)
STEAL = Card(CardType.STEAL)
DISCARD = Card(CardType.DISCARD)
DIVIDE = Card(CardType.DIVIDE, 2)


def number(value: int) -> Card:
    return Card(CardType.NUMBER, value)


def subtract(value: int) -> Card:
    return Card(CardType.SUBTRACT, value)


def target(player: int) -> Action:
    return Action(ActionType.CHOOSE_TARGET, player)


def game_with(draws: list[Card], *, players: int = 2, brutal: bool = False) -> Game:
    return Game(
        players,
        deck=Deck.stacked(draws),
        rules=VengeanceRules(brutal=brutal, target_score=1_000),
    )


def choose_card(game: Game, player: int, card: Card) -> None:
    observation = game.observe(game.current_player or 0)
    index = observation.players[player].cards.index(card)
    action = Action(ActionType.CHOOSE_CARD, player, index)
    assert action in observation.legal_actions
    game.apply(action)


def test_vengeance_deck_composition() -> None:
    counts = Counter(build_vengeance_deck())
    assert counts.total() == 108
    assert all(counts[number(n)] == n - (n in (7, 13)) for n in range(1, 14))
    assert counts[ZERO] == counts[UNLUCKY] == counts[LUCKY] == 1
    assert all(counts[subtract(n)] == 1 for n in (2, 4, 6, 8, 10))
    assert counts[DIVIDE] == 1
    assert all(
        counts[card] == 2 for card in (ONE_MORE, FLIP_FOUR, SWAP, STEAL, DISCARD)
    )


def test_vengeance_scoring_applies_division_then_subtractions_and_clamps() -> None:
    assert score_vengeance_cards([number(9), number(4), DIVIDE, subtract(4)]) == 2
    assert score_vengeance_cards([number(1), DIVIDE, subtract(4)]) == 0
    assert score_vengeance_cards([number(1), DIVIDE, subtract(4)], brutal=True) == -4
    assert score_vengeance_cards([number(9), ZERO]) == 0


def test_zero_forces_hit_and_only_zeroes_the_round_score() -> None:
    """Our reading of an unclear rule; see Rules notes in docs/reference.md."""
    game = game_with([ZERO, number(4), number(5)])
    observation = game.observe(1)
    assert observation.legal_actions == (HIT,)
    assert observation.players[1].round_score == 0
    game.apply(HIT)
    assert game.observe(1).players[1].round_score == 0


def test_zero_holder_who_flips_seven_scores_the_hand_and_bonus() -> None:
    draws = [ZERO] + [number(n) for n in range(1, 7)]
    game = Game(
        1,
        deck=Deck.stacked(draws),
        rules=VengeanceRules(target_score=1),
    )
    for _ in range(6):
        assert game.observe(0).legal_actions == (HIT,)
        game.apply(HIT)
    assert game.is_finished
    assert game.last_round is not None
    assert game.last_round.scores == (21 + 15,)


def test_unlucky_seven_discards_existing_numbers_and_modifiers_without_busting() -> (
    None
):
    game = game_with([number(7), number(4), UNLUCKY])
    game.apply(HIT)
    observation = game.observe(0)
    assert observation.players[1].cards == (UNLUCKY,)
    assert observation.players[1].status is PlayerStatus.ACTIVE
    assert number(7) in observation.discard


def test_lucky_thirteen_allows_two_thirteens_but_not_three() -> None:
    game = game_with([LUCKY, number(4), number(13), number(5), number(13)])
    game.apply(HIT)
    assert game.observe(1).players[1].round_score == 26
    game.apply(HIT)
    game.apply(HIT)
    assert game.observe(0).players[1].status is PlayerStatus.BUSTED


def test_both_thirteens_count_toward_flip_seven() -> None:
    draws = [LUCKY, number(13)] + [number(n) for n in range(1, 6)]
    game = Game(1, deck=Deck.stacked(draws), rules=VengeanceRules(target_score=1))
    for _ in range(6):
        game.apply(HIT)
    assert game.last_round is not None
    assert game.last_round.scores == (26 + sum(range(1, 6)) + 15,)


def test_just_one_more_can_target_a_stayed_player_and_they_remain_stayed() -> None:
    game = game_with([number(2), number(3), ONE_MORE, number(4)])
    game.apply(STAY)
    game.apply(HIT)
    assert target(1) in game.observe(0).legal_actions
    game.apply(target(1))
    observation = game.observe(0)
    assert observation.players[1].cards == (number(2), number(4))
    assert observation.players[1].status is PlayerStatus.STAYED
    assert ONE_MORE in observation.discard
    assert game.current_player == 0


def test_drawn_modifier_is_unresolved_and_unscored_until_a_player_receives_it() -> None:
    game = game_with([number(5), number(12), subtract(10)])
    game.apply(HIT)
    drawer = game.observe(1).players[1]
    assert drawer.unresolved == (subtract(10),)
    assert (drawer.cards, drawer.round_score) == ((number(5),), 5)
    game.apply(target(0))
    receiver, drawer = game.observe(1).players
    assert drawer.unresolved == ()
    assert (receiver.cards, receiver.round_score) == ((number(12), subtract(10)), 2)


def test_player_with_no_cards_can_stay_after_giving_away_initial_modifier() -> None:
    game = game_with([subtract(2), number(4)])
    game.apply(target(0))
    observation = game.observe(1)
    assert observation.players[1].cards == ()
    assert observation.legal_actions == (HIT, STAY)


def test_just_one_more_resolves_drawn_action_even_if_everyone_has_stayed() -> None:
    game = game_with([number(2), ONE_MORE, STEAL], players=1)
    game.apply(HIT)
    game.apply(target(0))
    observation = game.observe(0)
    assert observation.last_round is not None
    assert STEAL in observation.discard


def test_flip_four_defers_modifiers_and_actions_until_all_draws() -> None:
    game = game_with(
        [number(2), number(3), FLIP_FOUR, subtract(2), STEAL, number(4), number(5)]
    )
    game.apply(HIT)
    game.apply(target(0))
    observation = game.observe(0)
    assert isinstance(observation.decision, ChooseTarget)
    assert observation.decision.card == subtract(2)
    assert {number(3), number(4), number(5)} <= set(observation.players[0].cards)
    game.apply(target(1))
    decision = game.observe(0).decision
    assert isinstance(decision, ChooseCard) and decision.card == STEAL
    choose_card(game, 1, number(2))
    assert number(2) in game.observe(0).players[0].cards


def test_unlucky_seven_during_flip_four_keeps_unresolved_modifier() -> None:
    game = game_with(
        [number(2), number(3), FLIP_FOUR, subtract(2), UNLUCKY, number(4), number(5)]
    )
    game.apply(HIT)
    game.apply(target(0))
    observation = game.observe(0)
    assert isinstance(observation.decision, ChooseTarget)
    assert observation.decision.card == subtract(2)
    assert number(3) in observation.discard
    game.apply(target(1))
    assert subtract(2) in game.observe(0).players[1].cards


def test_flip_four_stops_on_bust_and_discards_deferred_effects() -> None:
    game = game_with(
        [number(2), number(3), FLIP_FOUR, subtract(2), number(3), number(9)]
    )
    game.apply(HIT)
    game.apply(target(0))
    observation = game.observe(1)
    assert observation.players[0].status is PlayerStatus.BUSTED
    assert isinstance(observation.decision, HitOrStay)
    assert FLIP_FOUR in observation.discard
    assert subtract(2) in observation.discard
    assert game.hidden_deck() == (number(9),)


def test_flip_seven_during_flip_four_does_not_score_a_modifier_not_yet_played() -> None:
    low = [number(value) for value in range(2, 7)]
    game = game_with([number(1), number(12), *low, FLIP_FOUR, subtract(10), number(8)])
    game.apply(HIT)
    game.apply(STAY)
    for _ in range(4):
        game.apply(HIT)
    game.apply(HIT)
    game.apply(target(1))
    assert game.last_round is not None
    assert game.last_round.flip_seven_player == 1
    assert game.last_round.scores == (12, 29 + 15)


def test_flip_seven_before_a_deferred_modifier_resolves_does_not_score_it() -> None:
    game = game_with(
        [
            *(number(value) for value in (1, 12, 2, 3, 4)),
            FLIP_FOUR,
            STEAL,
            subtract(10),
            number(5),
            number(6),
        ]
    )
    game.apply(HIT)
    game.apply(STAY)
    game.apply(HIT)
    game.apply(HIT)
    game.apply(HIT)
    game.apply(target(1))
    choose_card(game, 0, number(12))
    assert game.last_round is not None
    assert game.last_round.flip_seven_player == 1
    assert game.last_round.scores == (0, 33 + 15)


def test_swapped_unlucky_seven_does_not_discard_unresolved_modifier() -> None:
    game = game_with(
        [UNLUCKY, number(3), FLIP_FOUR, SWAP, subtract(2), number(4), number(5)]
    )
    game.apply(HIT)
    game.apply(target(0))
    decision = game.observe(0).decision
    assert isinstance(decision, ChooseCard) and decision.card == SWAP
    first = (1, game.observe(0).players[1].cards.index(UNLUCKY))
    choose_card(game, 1, UNLUCKY)
    # The pending second Swap choice is public, but only the chooser may act on it.
    bystander = game.observe(1)
    assert isinstance(bystander.decision, ChooseCard)
    assert (bystander.decision.player, bystander.decision.first) == (0, first)
    assert bystander.legal_actions == ()
    choose_card(game, 0, number(4))
    observation = game.observe(0)
    assert isinstance(observation.decision, ChooseTarget)
    assert observation.decision.card == subtract(2)
    assert number(3) in observation.discard
    assert number(5) in observation.discard
    game.apply(target(1))
    assert subtract(2) in game.observe(0).players[1].cards


def test_stealing_duplicate_busts_the_recipient() -> None:
    """Our reading of an unclear rule; see Rules notes in docs/reference.md."""
    game = game_with([number(2), number(2), STEAL])
    game.apply(HIT)
    choose_card(game, 0, number(2))
    assert game.observe(0).players[1].status is PlayerStatus.BUSTED
    assert STEAL in game.observe(0).discard


def test_stealing_zero_moves_its_effect_to_the_new_owner() -> None:
    game = game_with([ZERO, number(1), number(5), STEAL])
    game.apply(HIT)
    game.apply(HIT)
    choose_card(game, 1, ZERO)
    observation = game.observe(1)
    assert observation.players[0].round_score == 0
    assert observation.players[1].round_score == 5
    assert STAY in observation.legal_actions
    game.apply(STAY)
    assert game.observe(0).legal_actions == (HIT,)


def test_swap_selects_cards_from_distinct_players() -> None:
    game = game_with([number(2), number(4), SWAP])
    game.apply(HIT)
    choose_card(game, 1, number(2))
    assert all(action.target == 0 for action in game.observe(1).legal_actions)
    choose_card(game, 0, number(4))
    observation = game.observe(0)
    assert observation.players[1].cards == (number(4),)
    assert observation.players[0].cards == (number(2),)
    assert SWAP in observation.discard


def test_steal_can_complete_flip_seven() -> None:
    draws = [number(1), number(7)] + [number(n) for n in range(2, 7)] + [STEAL]
    game = Game(2, deck=Deck.stacked(draws), rules=VengeanceRules(target_score=1))
    game.apply(HIT)
    game.apply(STAY)
    for _ in range(4):
        game.apply(HIT)
    game.apply(HIT)
    choose_card(game, 0, number(7))
    assert game.is_finished
    assert game.last_round is not None
    assert game.last_round.flip_seven_player == 1
    assert game.last_round.scores[1] == sum(range(1, 8)) + 15


def test_discard_selects_a_face_up_card_and_changes_score() -> None:
    game = game_with([number(2), number(4), DISCARD])
    game.apply(HIT)
    choose_card(game, 0, number(4))
    observation = game.observe(0)
    assert observation.players[0].cards == ()
    assert number(4) in observation.discard
    assert DISCARD in observation.discard


@pytest.mark.parametrize("card", [SWAP, STEAL, DISCARD])
def test_untargetable_action_is_discarded(card: Card) -> None:
    game = game_with([card, number(2)], players=1)
    observation = game.observe(0)
    assert isinstance(observation.decision, HitOrStay)
    assert card in observation.discard


def test_brutal_mode_modifier_can_give_busted_player_negative_score() -> None:
    """Our reading of an unclear rule; see Rules notes in docs/reference.md."""
    game = game_with([number(2), number(3), number(2), subtract(4)], brutal=True)
    game.apply(HIT)
    game.apply(HIT)
    assert target(1) in game.observe(0).legal_actions
    game.apply(target(1))
    observation = game.observe(0)
    assert observation.players[1].status is PlayerStatus.BUSTED
    assert observation.players[1].round_score == -4


def test_brutal_mode_can_subtract_flip_seven_bonus_from_another_player() -> None:
    draws = [number(0), number(9)] + [number(n) for n in range(1, 7)]
    game = Game(
        2, deck=Deck.stacked(draws), rules=VengeanceRules(brutal=True, target_score=1)
    )
    game.apply(HIT)
    game.apply(STAY)
    for _ in range(5):
        game.apply(HIT)
    assert game.observe(1).legal_actions == (Action(ActionType.TAKE_BONUS), target(0))
    game.apply(target(0))
    assert game.last_round is not None
    assert game.last_round.scores == (-6, 21)
    assert game.is_finished


def test_brutal_mode_can_keep_flip_seven_bonus() -> None:
    draws = [number(0), number(9)] + [number(n) for n in range(1, 7)]
    game = Game(
        2, deck=Deck.stacked(draws), rules=VengeanceRules(brutal=True, target_score=1)
    )
    game.apply(HIT)
    game.apply(STAY)
    for _ in range(5):
        game.apply(HIT)
    game.apply(Action(ActionType.TAKE_BONUS))
    assert game.last_round is not None
    assert game.last_round.scores == (9, 36)


@pytest.mark.parametrize("brutal", [False, True])
def test_seeded_vengeance_game_finishes_with_a_winner(brutal: bool) -> None:
    result = play_game(
        [ThresholdBot(25), ThresholdBot(25), ThresholdBot(25)],
        seed=42,
        rules=VengeanceRules(brutal=brutal),
    )
    assert result.winners
    assert result.current_player is None
    assert max(player.total_score for player in result.players) >= 200


@pytest.mark.parametrize("brutal", [False, True])
def test_vengeance_card_conservation_through_a_game(brutal: bool) -> None:
    game = Game(3, seed=7, rules=VengeanceRules(brutal=brutal))
    bots = [RandomBot(seed) for seed in range(3)]
    expected = Counter(build_vengeance_deck())
    for _ in range(10_000):
        observation = game.observe(game.current_player or 0)
        cards = Counter(game.hidden_deck()) + Counter(observation.discard)
        for player in observation.players:
            cards.update(player.cards)
            cards.update(player.unresolved)
        assert cards == expected
        if game.is_finished:
            break
        player = game.current_player
        assert player is not None
        game.apply(bots[player].choose_action(game.observe(player)))
    else:
        pytest.fail("game did not finish")
