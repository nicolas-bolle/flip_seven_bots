from dataclasses import replace
from random import Random

import pytest

from flip_seven_bots.game import Action, ActionType, CardDrawn, Game, Observation

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
