import pytest

from flip_seven_bots.game import (
    Action,
    ActionType,
    Card,
    CardType,
    EventType,
    Game,
    PlayerStatus,
)
from flip_seven_bots.game.rules import build_deck, score_cards


def number(value: int) -> Card:
    return Card(CardType.NUMBER, value)


def game_with_draws(
    draws: list[Card], monkeypatch: pytest.MonkeyPatch, player_count: int = 2
) -> Game:
    with monkeypatch.context() as patch:
        patch.setattr(
            "flip_seven_bots.game.engine.build_deck", lambda: list(reversed(draws))
        )
        patch.setattr("flip_seven_bots.game.engine.Random.shuffle", lambda _self, _cards: None)
        return Game(player_count)


def test_deck_and_scoring() -> None:
    deck = build_deck()
    assert len(deck) == 94
    assert deck.count(number(0)) == 1
    assert deck.count(number(12)) == 12
    assert score_cards(
        [number(5), number(11), Card(CardType.MULTIPLY, 2), Card(CardType.ADD, 4)]
    ) == 36


def test_deferred_action_and_second_chance_during_flip_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = game_with_draws(
        [
            number(2), number(4), Card(CardType.FLIP_THREE),
            Card(CardType.FREEZE), Card(CardType.SECOND_CHANCE), number(2),
        ],
        monkeypatch,
    )
    game.apply(Action(ActionType.HIT))
    game.apply(Action(ActionType.CHOOSE_TARGET, 1))

    observation = game.observe(1)
    assert observation.pending_card == Card(CardType.FREEZE)
    assert observation.players[1].status == PlayerStatus.ACTIVE
    assert observation.discard_count == 2
    assert Card(CardType.SECOND_CHANCE) not in observation.players[1].cards
    assert [
        event.card for event in observation.events if event.kind is EventType.CARD_DRAWN
    ] == [
        number(2), number(4), Card(CardType.FLIP_THREE),
        Card(CardType.FREEZE), Card(CardType.SECOND_CHANCE), number(2),
    ]

    game.apply(Action(ActionType.CHOOSE_TARGET, 0))
    assert game.observe(1).players[0].status == PlayerStatus.STAYED
    assert game.current_player == 1


def test_bust_cancels_deferred_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    game = game_with_draws(
        [
            number(2), number(4), Card(CardType.FLIP_THREE),
            Card(CardType.FREEZE), number(2),
        ],
        monkeypatch,
    )
    game.apply(Action(ActionType.HIT))
    game.apply(Action(ActionType.CHOOSE_TARGET, 1))

    observation = game.observe(0)
    assert observation.players[1].status == PlayerStatus.BUSTED
    assert observation.pending_card is None
    assert game.current_player == 0


def test_seven_ends_round_and_awards_bonus(monkeypatch: pytest.MonkeyPatch) -> None:
    game = game_with_draws(
        [
            number(0), number(1), number(2), number(3), number(4),
            number(5), number(6), number(9),
        ],
        monkeypatch,
        player_count=1,
    )
    for _ in range(6):
        game.apply(Action(ActionType.HIT))

    observation = game.observe(0)
    assert observation.round_number == 2
    assert observation.last_round is not None
    assert observation.last_round.scores == (36,)
    assert observation.last_round.flip_seven_player == 0


def test_illegal_decision_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    game = game_with_draws([number(2), number(4)], monkeypatch)
    with pytest.raises(ValueError):
        game.apply(Action(ActionType.CHOOSE_TARGET, 0))


def test_second_chance_must_be_given_to_an_eligible_player(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chance = Card(CardType.SECOND_CHANCE)
    game = game_with_draws([chance, number(4), chance], monkeypatch)

    game.apply(Action(ActionType.HIT))
    observation = game.observe(1)
    assert observation.pending_card == chance
    assert observation.legal_actions == (Action(ActionType.CHOOSE_TARGET, 0),)

    game.apply(Action(ActionType.CHOOSE_TARGET, 0))
    observation = game.observe(0)
    assert observation.players[1].cards.count(chance) == 1
    assert observation.players[0].cards.count(chance) == 1
    assert game.current_player == 0


def test_extra_second_chance_is_discarded_if_no_recipient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chance = Card(CardType.SECOND_CHANCE)
    game = game_with_draws([chance, chance], monkeypatch, player_count=1)

    game.apply(Action(ActionType.HIT))
    observation = game.observe(0)
    assert observation.players[0].cards == (chance,)
    assert observation.discard_count == 1
    assert observation.pending_card is None
    assert Action(ActionType.STAY) in observation.legal_actions


def test_discard_is_reshuffled_for_next_round(monkeypatch: pytest.MonkeyPatch) -> None:
    game = game_with_draws([number(2), number(4)], monkeypatch)
    game.apply(Action(ActionType.STAY))
    game.apply(Action(ActionType.STAY))

    observation = game.observe(0)
    assert observation.round_number == 2
    assert observation.last_round is not None
    assert observation.last_round.scores == (4, 2)
    assert observation.discard_count == 0
    assert {player.cards for player in observation.players} == {(number(2),), (number(4),)}
    assert sum(event.kind is EventType.DISCARD_SHUFFLED for event in observation.events) == 1


def test_match_ends_after_round_and_reports_tied_winners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("flip_seven_bots.game.engine.TARGET_SCORE", 5)
    game = game_with_draws([number(5), number(5)], monkeypatch)

    game.apply(Action(ActionType.STAY))
    assert not game.is_finished
    game.apply(Action(ActionType.STAY))

    observation = game.observe(0)
    assert game.is_finished
    assert game.winners == (0, 1)
    assert observation.winners == (0, 1)
    assert observation.last_round is not None
    assert observation.last_round.totals == (5, 5)
    assert observation.current_player is None
    assert observation.legal_actions == ()
    with pytest.raises(ValueError, match="illegal action"):
        game.apply(Action(ActionType.HIT))
