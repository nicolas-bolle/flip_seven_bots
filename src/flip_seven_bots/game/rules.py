"""Deck construction and hand scoring for both game modes."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial

from .model import Card, CardType

TARGET_SCORE = 200
FLIP_SEVEN_BONUS = 15


def build_deck() -> list[Card]:
    """Build the unshuffled base-game deck, including duplicate cards."""
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
    """Score a base-game hand: multiply the number sum, then add modifiers.

    This function does not account for busts or the Flip 7 bonus; the engine
    handles those separately.
    """
    cards = tuple(cards)
    number_total = sum(card.value for card in cards if card.kind is CardType.NUMBER)
    multiplier = 2 if any(card.kind is CardType.MULTIPLY for card in cards) else 1
    modifiers = sum(card.value for card in cards if card.kind is CardType.ADD)
    return number_total * multiplier + modifiers


def build_vengeance_deck() -> list[Card]:
    """Build the unshuffled With A Vengeance deck, including special cards."""
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
    """Score a Vengeance hand before bust and Flip 7 adjustments.

    Zero makes the hand worth zero. Otherwise, divide the number sum by two
    when applicable, rounding down, then subtract modifiers. Normal mode
    clamps the result at zero; Brutal Mode permits negative scores.
    """
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
    """Match settings, defaulting to the base game's deck and hand scoring.

    ``target_score`` ends the match after a round reaches it, and
    ``flip_seven_bonus`` is applied by the engine. ``build_deck`` returns a
    fresh collection of cards; ``score_cards`` scores a hand before bust and
    bonus adjustments.
    """

    target_score: int = TARGET_SCORE
    flip_seven_bonus: int = FLIP_SEVEN_BONUS
    build_deck: Callable[[], list[Card]] = build_deck
    score_cards: Callable[[Iterable[Card]], int] = score_cards

    def __deepcopy__(self, memo: dict) -> Rules:
        return self


@dataclass(frozen=True)
class VengeanceRules(Rules):
    """Use the Vengeance deck and scoring, optionally enabling Brutal Mode.

    Brutal Mode allows negative scores, permits modifiers on busted players,
    and lets a Flip 7 player choose an opponent to receive a bonus penalty.
    A custom ``score_cards`` callable is left unchanged.
    """

    build_deck: Callable[[], list[Card]] = build_vengeance_deck
    score_cards: Callable[[Iterable[Card]], int] = score_vengeance_cards
    brutal: bool = False

    def __post_init__(self) -> None:
        if self.brutal and self.score_cards is score_vengeance_cards:
            object.__setattr__(self, "score_cards", partial(score_vengeance_cards, brutal=True))
