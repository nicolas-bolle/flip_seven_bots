"""Public, immutable values shared by the engine, bots, and UI."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from random import Random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import Game


class CardType(Enum):
    NUMBER = auto()
    ADD = auto()
    MULTIPLY = auto()
    FREEZE = auto()
    FLIP_THREE = auto()
    SECOND_CHANCE = auto()


@dataclass(frozen=True)
class Card:
    kind: CardType
    value: int = 0

    def __deepcopy__(self, memo: dict) -> Card:
        return self


class PlayerStatus(Enum):
    ACTIVE = auto()
    STAYED = auto()
    BUSTED = auto()


class ActionType(Enum):
    HIT = auto()
    STAY = auto()
    CHOOSE_TARGET = auto()


@dataclass(frozen=True)
class Action:
    kind: ActionType
    target: int | None = None

    def __post_init__(self) -> None:
        if (self.kind is ActionType.CHOOSE_TARGET) != (self.target is not None):
            raise ValueError("an action has a target exactly when it chooses a target")


@dataclass(frozen=True)
class PlayerView:
    player: int
    total_score: int
    status: PlayerStatus
    cards: tuple[Card, ...]
    round_score: int
    """In-progress score for the current round, excluding any Flip 7 bonus."""


@dataclass(frozen=True)
class RoundResult:
    round_number: int
    scores: tuple[int, ...]
    totals: tuple[int, ...]
    flip_seven_player: int | None


@dataclass(frozen=True)
class RoundStarted:
    round_number: int


@dataclass(frozen=True)
class CardDrawn:
    round_number: int
    player: int
    card: Card


@dataclass(frozen=True)
class ActionChosen:
    round_number: int
    player: int
    action: Action


@dataclass(frozen=True)
class DiscardShuffled:
    round_number: int


@dataclass(frozen=True)
class RoundEnded:
    round_number: int
    result: RoundResult


GameEvent = RoundStarted | CardDrawn | ActionChosen | DiscardShuffled | RoundEnded


@dataclass(frozen=True)
class Observation:
    player: int
    current_player: int | None
    round_number: int
    dealer: int
    players: tuple[PlayerView, ...]
    cards_remaining: int
    discard: tuple[Card, ...]
    legal_actions: tuple[Action, ...]
    pending_card: Card | None
    last_round: RoundResult | None
    winners: tuple[int, ...]
    events: tuple[GameEvent, ...]
    """Public events of the current round."""
    _sampler: Callable[[Random], Game] | None = field(
        default=None, repr=False, compare=False
    )

    def sample_game(self, rng: Random) -> Game:
        """Return an independent game consistent with this observation.

        The hidden deck order and future reshuffles are drawn from ``rng``, so the
        copy can be played forward to simulate possible outcomes.
        """
        if self._sampler is None:
            raise ValueError("observation is not linked to a game")
        return self._sampler(rng)
