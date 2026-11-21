"""The draw and discard piles."""

from collections.abc import Iterable
from random import Random

from .model import Card


class Deck:
    """Draw and discard piles; the draw pile's order is the game's only hidden information."""

    def __init__(self, cards: Iterable[Card], rng: Random, *, shuffle: bool = True):
        self._random = rng
        self._cards = list(cards)
        self._discard: list[Card] = []
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
        return tuple(self._discard)

    def draw(self) -> tuple[Card, bool]:
        """Draw the top card, reshuffling the discard pile first if needed.

        Returns the card and whether a reshuffle happened.
        """
        reshuffled = False
        if not self._cards:
            if not self._discard:
                raise RuntimeError("cannot draw: no cards are available to reshuffle")
            self._cards, self._discard = self._discard, []
            self._random.shuffle(self._cards)
            reshuffled = True
        return self._cards.pop(), reshuffled

    def discard(self, cards: Iterable[Card]) -> None:
        self._discard.extend(cards)

    def resample(self, rng: Random) -> None:
        """Shuffle the hidden draw pile and use ``rng`` for all future shuffles."""
        self._random = rng
        self._random.shuffle(self._cards)
