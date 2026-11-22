"""The draw and discard piles."""

from collections.abc import Iterable, Sequence
from random import Random

from .model import Card


def _card_order(card: Card) -> tuple[int, int]:
    return card.kind.value, card.value


class Deck:
    """Manage draw and discard piles, with a supplied random generator.

    Cards are shuffled on construction unless ``shuffle`` is false. The draw
    pile's order is hidden from observations; the discard pile is public.
    """

    def __init__(self, cards: Iterable[Card], rng: Random, *, shuffle: bool = True):
        self._random = rng
        self._cards = list(cards)
        self._discard: list[Card] = []
        self._reshuffled = False
        if shuffle:
            self._random.shuffle(self._cards)

    @classmethod
    def stacked(cls, draws: Iterable[Card], rng: Random | None = None) -> Deck:
        """A deck that deals ``draws`` in order; reshuffles use ``rng`` (seeded by default)."""
        return cls(reversed(list(draws)), rng or Random(0), shuffle=False)

    def __len__(self) -> int:
        return len(self._cards)

    @property
    def discard_pile(self) -> tuple[Card, ...]:
        """Return a snapshot of the public discard pile."""
        return tuple(self._discard)

    @property
    def composition(self) -> tuple[Card, ...]:
        """The draw pile's cards in a fixed sorted order that reveals nothing about the draw order."""
        return tuple(sorted(self._cards, key=_card_order))

    @property
    def remaining(self) -> tuple[Card, ...]:
        """The hidden draw pile, next card first."""
        return tuple(reversed(self._cards))

    def draw(self) -> tuple[Card, bool]:
        """Draw the top card, reshuffling the discard pile first if needed.

        Returns the card and whether a reshuffle happened. Raises
        ``RuntimeError`` if both piles are empty.
        """
        reshuffled, self._reshuffled = self._reshuffled, False
        if not self._cards:
            if not self._discard:
                raise RuntimeError("cannot draw: no cards are available to reshuffle")
            self._reshuffle()
            reshuffled = True
        return self._cards.pop(), reshuffled

    def stack(self, cards: Sequence[Card]) -> None:
        """Move ``cards`` from the draw pile to its top so they are drawn next, in order.

        If the draw pile is empty, the discard pile is reshuffled into it first,
        as the next draw would do; that draw still reports the reshuffle.
        Raises ``ValueError`` if the pile does not contain the cards.
        """
        if cards and not self._cards and self._discard:
            self._reshuffle()
            self._reshuffled = True
        remaining = list(self._cards)
        for card in cards:
            if card not in remaining:
                raise ValueError(f"{card!r} is not available to draw")
            remaining.remove(card)
        self._cards = remaining + list(reversed(cards))

    def _reshuffle(self) -> None:
        self._cards, self._discard = self._discard, []
        self._random.shuffle(self._cards)

    def discard(self, cards: Iterable[Card]) -> None:
        """Add cards to the discard pile for a future reshuffle."""
        self._discard.extend(cards)

    def resample(self, rng: Random) -> None:
        """Reorder the hidden draw pile from ``rng`` alone and use it for future shuffles.

        Shuffling starts from the sorted composition, so the result does not
        depend on (and cannot be inverted to reveal) the previous order.
        """
        self._random = rng
        self._cards = list(self.composition)
        self._random.shuffle(self._cards)
