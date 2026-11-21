"""Deck and scoring rules for the base game."""

from collections.abc import Iterable

from .model import Card, CardType

TARGET_SCORE = 200
FLIP_SEVEN_BONUS = 15


def build_deck() -> list[Card]:
    cards = [Card(CardType.NUMBER, 0)]
    cards.extend(
        Card(CardType.NUMBER, number) for number in range(1, 13) for _ in range(number)
    )
    cards.extend(Card(CardType.ADD, value) for value in (2, 4, 6, 8, 10))
    cards.append(Card(CardType.MULTIPLY, 2))
    for kind in (CardType.FREEZE, CardType.FLIP_THREE, CardType.SECOND_CHANCE):
        cards.extend(Card(kind) for _ in range(3))
    return cards


def score_cards(cards: Iterable[Card]) -> int:
    cards = tuple(cards)
    number_total = sum(card.value for card in cards if card.kind is CardType.NUMBER)
    multiplier = 2 if any(card.kind is CardType.MULTIPLY for card in cards) else 1
    modifiers = sum(card.value for card in cards if card.kind is CardType.ADD)
    return number_total * multiplier + modifiers
