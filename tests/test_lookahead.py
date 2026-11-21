from dataclasses import replace
from random import Random

import pytest

from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardDrawn,
    CardType,
    Deck,
    Game,
    Observation,
)

HIT = Action(ActionType.HIT)


def hit_or_stay_observation() -> tuple[Game, Observation]:
    game = Game(3, seed=7)
    assert game.current_player is not None
    observation = game.observe(game.current_player)
    assert HIT in observation.legal_actions
    return game, observation


def cards_drawn_after_hit(game: Game) -> tuple[CardDrawn, ...]:
    player = game.current_player
    assert player is not None
    before = len(game.observe(player).events)
    game.apply(HIT)
    events = game.observe(player).events[before:]
    return tuple(event for event in events if isinstance(event, CardDrawn))


def test_sampled_game_matches_the_observation() -> None:
    _, observation = hit_or_stay_observation()
    sample = observation.sample_game(Random(1))
    assert sample.observe(observation.player) == observation


def test_playing_a_sampled_game_does_not_change_the_original() -> None:
    game, observation = hit_or_stay_observation()
    observation.sample_game(Random(1)).apply(HIT)
    assert game.observe(observation.player) == observation


def test_samples_draw_the_hidden_deck_order_from_the_given_rng() -> None:
    _, observation = hit_or_stay_observation()
    draws = [cards_drawn_after_hit(observation.sample_game(Random(seed))) for seed in range(5)]
    assert len(set(draws)) > 1
    assert cards_drawn_after_hit(observation.sample_game(Random(0))) == draws[0]


def test_stale_observation_cannot_be_sampled() -> None:
    game, observation = hit_or_stay_observation()
    game.apply(HIT)
    with pytest.raises(RuntimeError, match="out of date"):
        observation.sample_game(Random(1))


def test_unlinked_observation_cannot_be_sampled() -> None:
    _, observation = hit_or_stay_observation()
    with pytest.raises(ValueError, match="not linked"):
        replace(observation, _sampler=None).sample_game(Random(1))


def test_draw_pile_is_the_sorted_hidden_composition() -> None:
    game, observation = hit_or_stay_observation()
    assert sorted(observation.draw_pile, key=repr) == sorted(game.hidden_deck(), key=repr)
    assert observation.draw_pile != game.hidden_deck()
    assert observation.cards_remaining == len(game.hidden_deck())


def test_next_draws_fix_the_upcoming_cards() -> None:
    _, observation = hit_or_stay_observation()
    rare = min(set(observation.draw_pile), key=observation.draw_pile.count)
    for seed in range(3):
        sample = observation.sample_game(Random(seed), next_draws=(rare,))
        assert cards_drawn_after_hit(sample)[0].card == rare


def test_next_draws_must_be_available() -> None:
    _, observation = hit_or_stay_observation()
    with pytest.raises(ValueError, match="not available"):
        observation.sample_game(Random(0), next_draws=(Card(CardType.ZERO),))


def test_stacking_an_empty_draw_pile_reshuffles_the_discard_first() -> None:
    deck = Deck.stacked([])
    cards = [Card(CardType.NUMBER, value) for value in (1, 2, 3)]
    deck.discard(cards)
    deck.stack([cards[1]])
    assert deck.draw() == (cards[1], True)
    assert deck.draw()[1] is False


def test_samples_reveal_nothing_about_the_true_deck_order() -> None:
    # Same public state, different hidden order: a sample must not depend on which.
    rest = [Card(CardType.NUMBER, value) for value in range(1, 9)]
    observations = [
        Game(1, deck=Deck.stacked([Card(CardType.NUMBER, 12), *order])).observe(0)
        for order in (rest, rest[::-1])
    ]
    assert observations[0] == observations[1]
    first, second = (o.sample_game(Random(5)).hidden_deck() for o in observations)
    assert first == second
