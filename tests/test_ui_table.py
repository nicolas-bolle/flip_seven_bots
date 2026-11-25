import pytest

from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    Deck,
    Game,
    Observation,
    PlayerStatus,
    Rules,
)
from flip_seven_bots.gui.play.table import Seat, Table

HIT = Action(ActionType.HIT)
STAY = Action(ActionType.STAY)


class StayBot:
    def choose_action(self, observation: Observation) -> Action:
        return STAY


def make_table(rules: Rules | None = None, bot_delay_ms: int = 0) -> Table:
    """The human (seat 0) is dealt first and holds a 3; both bots always stay."""
    draws = [Card(CardType.NUMBER, n) for n in (3, 1, 2, 7, 8, 9)]
    return Table(
        [Seat('You'), Seat('A', StayBot()), Seat('B', StayBot())],
        new_game=lambda count, _seed: Game(
            count, dealer=2, deck=Deck.stacked(draws), rules=rules
        ),
        bot_delay_ms=bot_delay_ms,
    )


def finish_first_round(table: Table) -> None:
    table.choose(STAY)
    table.update(0)
    table.update(0)


def test_bot_moves_once_its_delay_has_passed() -> None:
    table = make_table(bot_delay_ms=700)
    table.choose(STAY)

    table.update(1_000)
    table.update(1_699)
    assert table.game.current_player == 1
    table.update(1_700)
    assert table.game.current_player == 2


def test_default_bot_delay_is_at_least_one_second_for_each_decision() -> None:
    draws = [Card(CardType.NUMBER, n) for n in (3, 1, 2)]
    table = Table(
        [Seat('You'), Seat('A', StayBot()), Seat('B', StayBot())],
        new_game=lambda count, _seed: Game(count, dealer=2, deck=Deck.stacked(draws)),
    )
    table.choose(STAY)
    table.update(1_000)
    table.update(1_999)
    assert table.game.current_player == 1
    table.update(2_000)
    assert table.game.current_player == 2
    table.update(2_000)
    table.update(2_999)
    assert table.game.current_player == 2


def test_human_cannot_act_on_a_bot_turn() -> None:
    table = make_table()
    table.choose(STAY)
    assert table.human_to_act is None
    with pytest.raises(ValueError, match="not a human player's turn"):
        table.choose(HIT)


def test_round_summary_pauses_bots_until_dismissed() -> None:
    table = make_table()
    finish_first_round(table)

    summary = table.round_summary
    assert summary is not None
    assert summary.scores == (3, 1, 2)
    assert table.game.current_player == 1

    table.update(0)
    assert table.observation.players[1].status is PlayerStatus.ACTIVE
    table.dismiss_summary()
    table.update(0)
    assert table.observation.players[1].status is PlayerStatus.STAYED


def test_restart_replaces_a_finished_game() -> None:
    table = make_table(rules=Rules(target_score=1))
    finish_first_round(table)
    finished = table.game
    assert finished.is_finished

    table.restart()
    assert table.game is not finished
    assert table.round_summary is None
    assert table.observation.round_number == 1


def test_each_human_acts_on_their_own_turn() -> None:
    draws = [Card(CardType.NUMBER, n) for n in (3, 1, 2)]
    table = Table(
        [Seat('Ann'), Seat('Bot', StayBot()), Seat('Ben')],
        new_game=lambda count, _seed: Game(count, dealer=2, deck=Deck.stacked(draws)),
        bot_delay_ms=0,
    )
    assert table.human_to_act == 0
    table.choose(STAY)
    assert table.human_to_act is None
    table.update(0)
    assert table.human_to_act == 2
    assert table.observation.legal_actions == (HIT, STAY)


def test_bots_play_a_table_without_humans() -> None:
    table = Table(
        [Seat('A', StayBot()), Seat('B', StayBot())],
        new_game=lambda count, _seed: Game(count, seed=1),
        bot_delay_ms=0,
    )
    table.update(0)
    table.update(0)
    assert table.round_summary is not None
    assert table.human_to_act is None


def test_table_needs_a_seat() -> None:
    with pytest.raises(ValueError, match='at least one seat'):
        Table([])


def test_seed_makes_games_repeatable() -> None:
    def deals(seed: int | None) -> list[tuple[Card, ...]]:
        table = Table([Seat('You'), Seat('A', StayBot())], seed=seed)
        first = table.game.hidden_deck()
        table.restart()
        return [first, table.game.hidden_deck()]

    first_game, second_game = deals(5)
    assert deals(5) == [first_game, second_game]
    assert first_game != second_game
    assert deals(6)[0] != first_game


def test_moves_are_recorded_and_reset_on_restart() -> None:
    table = make_table()
    table.choose(STAY)
    table.update(0)
    assert [(move.player, move.action) for move in table.moves] == [
        (0, STAY),
        (1, STAY),
    ]

    table.restart()
    assert table.moves == ()


def test_pause_stops_humans_and_bots_until_resumed() -> None:
    table = make_table()
    table.pause()
    assert table.human_to_act is None
    table.resume()
    table.choose(STAY)

    table.pause()
    table.update(10_000)
    assert table.game.current_player == 1
    table.resume()
    table.update(10_000)
    assert table.game.current_player == 2
