import pytest

from flip_seven_bots.bots import ThresholdBot
from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    Game,
    Observation,
    Rules,
)
from flip_seven_bots.simulation import play_game, run


def test_seeded_game_completes_reproducibly() -> None:
    first = play_game([ThresholdBot(0), ThresholdBot(0)], seed=42)
    second = play_game([ThresholdBot(0), ThresholdBot(0)], seed=42)

    assert first == second
    assert first.winners
    assert max(player.total_score for player in first.players) >= 200
    assert first.current_player is None


def test_simulation_rejects_illegal_bot_action() -> None:
    class IllegalBot:
        def choose_action(self, observation: Observation) -> Action:
            return Action(ActionType.CHOOSE_TARGET, target=99)

    with pytest.raises(ValueError, match="illegal action"):
        play_game([IllegalBot()], seed=42)


def test_simulation_stops_at_decision_limit() -> None:
    with pytest.raises(RuntimeError, match="exceeded 1 decisions"):
        play_game([ThresholdBot(0)], seed=42, max_decisions=1)


def test_decision_limit_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_decisions"):
        play_game([ThresholdBot(0)], max_decisions=0)


def test_game_finishes_on_last_permitted_decision() -> None:
    rules = Rules(target_score=1, build_deck=lambda: [Card(CardType.NUMBER, 2)])
    result = play_game([ThresholdBot(0)], seed=42, rules=rules, max_decisions=1)
    assert result.winners == (0,)
    assert result.players[0].total_score == 2


def test_run_stops_when_condition_is_met() -> None:
    game = Game(2, seed=42)
    run(game, [ThresholdBot(10), ThresholdBot(10)], stop=lambda g: g.round_number > 1)
    assert game.round_number == 2
    assert not game.is_finished
