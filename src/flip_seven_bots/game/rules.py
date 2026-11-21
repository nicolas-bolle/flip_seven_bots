"""Deck and scoring rules for the base game."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial

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


def build_vengeance_deck() -> list[Card]:
    cards = [
        Card(CardType.NUMBER, number)
        for number in range(1, 14)
        for _ in range(number - 1 if number in (7, 13) else number)
    ]
    cards.extend((
        Card(CardType.ZERO, 0),
        Card(CardType.UNLUCKY_SEVEN, 7),
        Card(CardType.LUCKY_THIRTEEN, 13),
    ))
    cards.extend(Card(CardType.SUBTRACT, value) for value in (2, 4, 6, 8, 10))
    cards.append(Card(CardType.DIVIDE, 2))
    for kind in (
        CardType.JUST_ONE_MORE, CardType.FLIP_FOUR, CardType.SWAP,
        CardType.STEAL, CardType.DISCARD,
    ):
        cards.extend(Card(kind) for _ in range(2))
    return cards


def score_vengeance_cards(cards: Iterable[Card], *, brutal: bool = False) -> int:
    cards = tuple(cards)
    if any(card.kind is CardType.ZERO for card in cards):
        return 0
    total = sum(card.value for card in cards if card.is_number)
    if any(card.kind is CardType.DIVIDE for card in cards):
        total //= 2
    total -= sum(card.value for card in cards if card.kind is CardType.SUBTRACT)
    return total if brutal else max(0, total)


@dataclass(frozen=True)
class Rules:
    """Settings for a match; the defaults are the base game."""

    target_score: int = TARGET_SCORE
    flip_seven_bonus: int = FLIP_SEVEN_BONUS
    build_deck: Callable[[], list[Card]] = build_deck
    score_cards: Callable[[Iterable[Card]], int] = score_cards

    def __deepcopy__(self, memo: dict) -> Rules:
        return self


@dataclass(frozen=True)
class VengeanceRules(Rules):
    """Settings for With A Vengeance, including its optional Brutal Mode."""

    build_deck: Callable[[], list[Card]] = build_vengeance_deck
    score_cards: Callable[[Iterable[Card]], int] = score_vengeance_cards
    brutal: bool = False

    def __post_init__(self) -> None:
        if self.brutal and self.score_cards is score_vengeance_cards:
            object.__setattr__(self, "score_cards", partial(score_vengeance_cards, brutal=True))
