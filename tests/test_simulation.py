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


def test_optional_game_hooks_receive_seat_and_final_observation() -> None:
    class ObservingBot(ThresholdBot):
        def __init__(self) -> None:
            super().__init__(0)
            self.started = None
            self.finished = None

        def on_game_start(self, seat: int, count: int, rules: Rules) -> None:
            self.started = (seat, count, rules.target_score)

        def on_game_end(self, observation: Observation) -> None:
            self.finished = observation

    bot = ObservingBot()
    play_game([ThresholdBot(0), bot], seed=2, rules=Rules(target_score=20))
    assert bot.started == (1, 2, 20)
    assert bot.finished is not None
    assert bot.finished.player == 1 and bot.finished.winners


def test_simulation_rejects_illegal_bot_action() -> None:
    class IllegalBot:
        def choose_action(self, observation: Observation) -> Action:
            return Action(ActionType.CHOOSE_TARGET, target=99)

    with pytest.raises(ValueError, match="illegal action"):
        play_game([IllegalBot()], seed=42)


def test_simulation_stops_endless_game() -> None:
    rules = Rules(build_deck=lambda: [Card(CardType.NUMBER, 0)] * 20)
    with pytest.raises(RuntimeError, match="exceeded 100000 decisions"):
        play_game([ThresholdBot(10), ThresholdBot(10)], seed=1, rules=rules)


def test_run_stops_when_condition_is_met() -> None:
    game = Game(2, seed=42)
    run(game, [ThresholdBot(10), ThresholdBot(10)], stop=lambda g: g.round_number > 1)
    assert game.round_number == 2
    assert not game.is_finished
