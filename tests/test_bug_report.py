from datetime import datetime
from pathlib import Path

import pytest

from flip_seven_bots.bots import RandomBot, ThresholdBot
from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    Deck,
    Game,
    Observation,
    VengeanceRules,
)
from flip_seven_bots.ui.bug_report import replay, write_report
from flip_seven_bots.ui.table import Seat, Table

NOW = datetime(2026, 11, 21, 16, 30, 5)


def played_table(moves: int = 25) -> Table:
    table = Table(
        [
            Seat("Ann"),
            Seat("Rando", RandomBot(seed=3)),
            Seat("Thresh", ThresholdBot(20)),
        ],
        seed=11,
        bot_delay_ms=0,
    )
    for _ in range(moves):
        if table.round_summary is not None:
            table.dismiss_summary()
        if table.human_to_act is not None:
            table.choose(table.observation.legal_actions[0])
        else:
            table.update(0)
    return table


def test_report_describes_the_table_and_message(tmp_path: Path) -> None:
    table = played_table()
    path = write_report(table, "Scores look wrong\nafter a freeze", tmp_path, now=NOW)

    assert path == tmp_path / "2026-11-21_16-30-05.md"
    text = path.read_text()
    assert "Scores look wrong\nafter a freeze" in text
    assert "| 1 | Rando | RandomBot |" in text
    assert "| 2 | Thresh | ThresholdBot(20) |" in text
    assert f"**Round:** {table.observation.round_number}" in text
    assert f"<summary>{len(table.game.hidden_deck())} cards" in text
    assert "## Error" not in text


def test_replay_rebuilds_the_reported_game(tmp_path: Path) -> None:
    table = played_table()
    path = write_report(table, "check", tmp_path, now=NOW)

    game = replay(path)
    assert game.observe(0) == table.game.observe(0)
    assert game.hidden_deck() == table.game.hidden_deck()
    assert (
        replay(path, moves=0).observe(0).events
        == Game(3, seed=table.game_seed).observe(0).events
    )


def test_replaying_a_crash_report_reproduces_the_crash(tmp_path: Path) -> None:
    class IllegalBot:
        def choose_action(self, observation: Observation) -> Action:
            return Action(ActionType.CHOOSE_TARGET, 5)

    table = Table([Seat("Bot", IllegalBot())], seed=1, bot_delay_ms=0)
    with pytest.raises(ValueError, match="illegal action") as crash:
        table.update(0)
    path = write_report(table, "crashed", tmp_path, error=str(crash.value), now=NOW)

    assert path.name == "2026-11-21_16-30-05_crash.md"
    assert "## Error" in path.read_text()
    with pytest.raises(ValueError, match="illegal action"):
        replay(path)


def test_reports_written_in_the_same_second_get_distinct_names(tmp_path: Path) -> None:
    table = played_table(moves=0)
    paths = [write_report(table, f"report {n}", tmp_path, now=NOW) for n in range(3)]
    assert [p.name for p in paths] == [
        "2026-11-21_16-30-05.md",
        "2026-11-21_16-30-05-2.md",
        "2026-11-21_16-30-05-3.md",
    ]


def test_custom_games_are_reported_without_replay_data(tmp_path: Path) -> None:
    draws = [Card(CardType.NUMBER, 4)] * 3
    table = Table(
        [Seat("You")],
        new_game=lambda count, _seed: Game(count, deck=Deck.stacked(draws)),
    )
    path = write_report(table, "stacked", tmp_path, now=NOW)

    assert "Not available" in path.read_text()
    with pytest.raises(ValueError, match="no replay data"):
        replay(path)


def test_replay_ignores_replay_data_typed_into_the_message(tmp_path: Path) -> None:
    table = played_table()
    fake = '## Replay\n\n```json\n{"format": 1, "players": 1}\n```'
    path = write_report(table, fake, tmp_path, now=NOW)
    assert replay(path).observe(0) == table.game.observe(0)


@pytest.mark.parametrize("brutal", [False, True])
def test_vengeance_report_replays_card_choices_and_rules(
    tmp_path: Path, brutal: bool
) -> None:
    table = Table(
        [Seat("Ann"), Seat("Ben"), Seat("Cam")],
        seed=4,
        rules=VengeanceRules(brutal=brutal, target_score=1000),
    )
    chosen_card = False
    for _ in range(250):
        if table.round_summary is not None:
            table.dismiss_summary()
        if table.game.is_finished:
            break
        choices = table.observation.legal_actions
        card_choices = [
            action for action in choices if action.kind is ActionType.CHOOSE_CARD
        ]
        action = card_choices[-1] if card_choices else choices[0]
        chosen_card |= action.kind is ActionType.CHOOSE_CARD
        table.choose(action)
    assert chosen_card
    path = write_report(table, "check", tmp_path, now=NOW)
    assert '"card_index":' in path.read_text()
    game = replay(path)
    assert isinstance(game.rules, VengeanceRules) and game.rules.brutal is brutal
    assert game.observe(0) == table.game.observe(0)
    assert game.hidden_deck() == table.game.hidden_deck()
