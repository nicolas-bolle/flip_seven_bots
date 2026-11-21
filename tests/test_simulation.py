import pytest

from flip_seven_bots.bots import ThresholdBot
from flip_seven_bots.game import Action, ActionType, Card, CardType, Observation
from flip_seven_bots.simulation import play_game


def test_seeded_game_completes_reproducibly() -> None:
    first = play_game([ThresholdBot(0), ThresholdBot(0)], seed=42)
    second = play_game([ThresholdBot(0), ThresholdBot(0)], seed=42)

    assert first == second
    assert first.winners
    assert max(player.total_score for player in first.players) >= 200
    assert first.last_round is not None
    assert first.current_player is None


def test_simulation_rejects_illegal_bot_action() -> None:
    class IllegalBot:
        def choose_action(self, observation: Observation) -> Action:
            return Action(ActionType.CHOOSE_TARGET, target=99)

    with pytest.raises(ValueError, match="illegal action"):
        play_game([IllegalBot()], seed=42)


def test_simulation_decision_limit_and_validation() -> None:
    with pytest.raises(RuntimeError, match="exceeded 1 decisions"):
        play_game([ThresholdBot(0)], seed=42, max_decisions=1)
    with pytest.raises(ValueError, match="max_decisions"):
        play_game([ThresholdBot(0)], max_decisions=0)


def test_game_finishes_on_last_permitted_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("flip_seven_bots.game.engine.TARGET_SCORE", 1)
    monkeypatch.setattr(
        "flip_seven_bots.game.engine.build_deck",
        lambda: [Card(CardType.NUMBER, 2)],
    )
    result = play_game([ThresholdBot(0)], seed=42, max_decisions=1)
    assert result.winners == (0,)
    assert result.players[0].total_score == 2


def test_unfinished_game_without_current_player_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenGame:
        def __init__(self, _players: int, *, seed: int | None, dealer: int) -> None:
            self.is_finished = False
            self.current_player = None

    monkeypatch.setattr("flip_seven_bots.simulation.Game", BrokenGame)
    with pytest.raises(RuntimeError, match="unfinished but has no player decision"):
        play_game([ThresholdBot(0)])
