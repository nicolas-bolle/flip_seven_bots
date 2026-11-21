"""Public, immutable values shared by the engine, bots, and future UI."""

from dataclasses import dataclass
from enum import Enum, auto


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


@dataclass(frozen=True)
class PlayerView:
    player: int
    total_score: int
    status: PlayerStatus
    cards: tuple[Card, ...]
    round_score: int


@dataclass(frozen=True)
class RoundResult:
    round_number: int
    scores: tuple[int, ...]
    totals: tuple[int, ...]
    flip_seven_player: int | None


class EventType(Enum):
    ROUND_STARTED = auto()
    CARD_DRAWN = auto()
    ACTION_CHOSEN = auto()
    DISCARD_SHUFFLED = auto()
    ROUND_ENDED = auto()


@dataclass(frozen=True)
class GameEvent:
    kind: EventType
    round_number: int
    player: int | None = None
    card: Card | None = None
    action: Action | None = None
    result: RoundResult | None = None


@dataclass(frozen=True)
class Observation:
    player: int
    current_player: int | None
    round_number: int
    dealer: int
    players: tuple[PlayerView, ...]
    cards_remaining: int
    discard_count: int
    legal_actions: tuple[Action, ...]
    pending_card: Card | None
    last_round: RoundResult | None
    winners: tuple[int, ...]
    events: tuple[GameEvent, ...]
