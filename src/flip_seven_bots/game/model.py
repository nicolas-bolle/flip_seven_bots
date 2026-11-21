"""Public, immutable values shared by the engine, bots, and UI."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from random import Random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import Game


class CardType(Enum):
    """Kinds of cards in the base and With A Vengeance decks."""

    NUMBER = auto()
    ADD = auto()
    MULTIPLY = auto()
    FREEZE = auto()
    FLIP_THREE = auto()
    SECOND_CHANCE = auto()
    ZERO = auto()
    UNLUCKY_SEVEN = auto()
    LUCKY_THIRTEEN = auto()
    SUBTRACT = auto()
    DIVIDE = auto()
    JUST_ONE_MORE = auto()
    FLIP_FOUR = auto()
    SWAP = auto()
    STEAL = auto()
    DISCARD = auto()


@dataclass(frozen=True)
class Card:
    """An immutable card identified by its kind and, when applicable, value.

    Number and modifier cards carry their printed number in ``value``; action
    cards generally use the default of zero. Equal cards are interchangeable.
    """

    kind: CardType
    value: int = 0

    @property
    def is_number(self) -> bool:
        """Whether this card counts as a number, including Vengeance special numbers."""
        return self.kind in (
            CardType.NUMBER, CardType.ZERO, CardType.UNLUCKY_SEVEN,
            CardType.LUCKY_THIRTEEN,
        )

    def __deepcopy__(self, memo: dict) -> Card:
        return self


class PlayerStatus(Enum):
    """A player's state within the current round."""

    ACTIVE = auto()
    STAYED = auto()
    BUSTED = auto()


class ActionType(Enum):
    """Decision types accepted by the engine."""

    HIT = auto()
    STAY = auto()
    CHOOSE_TARGET = auto()
    CHOOSE_CARD = auto()
    TAKE_BONUS = auto()


@dataclass(frozen=True)
class Action:
    """A decision made by the current player.

    ``CHOOSE_TARGET`` uses ``target`` as a zero-based player ID. For
    ``CHOOSE_CARD``, ``target`` is the card owner's player ID and
    ``card_index`` indexes that owner's ``PlayerView.cards`` in the current
    observation, not the visually sorted UI. Other actions use neither field.
    Constructing an action with fields inappropriate for its kind raises
    ``ValueError``; the engine separately checks whether it is legal.
    """

    kind: ActionType
    """Type of decision."""

    target: int | None = None
    """Selected player or card owner, for target and card choices."""

    card_index: int | None = None
    """Index into the selected owner's current ``PlayerView.cards``."""

    def __post_init__(self) -> None:
        if (self.kind in (ActionType.CHOOSE_TARGET, ActionType.CHOOSE_CARD)) != (
            self.target is not None
        ):
            raise ValueError("an action has a target exactly when it chooses a target or card")
        if (self.kind is ActionType.CHOOSE_CARD) != (self.card_index is not None):
            raise ValueError("an action has a card index exactly when it chooses a card")


@dataclass(frozen=True)
class PlayerView:
    """Public snapshot of one seat's cards, status, and scores.

    ``player`` is the zero-based seat ID. ``total_score`` is the score from
    completed rounds. ``cards`` is in the engine's hand order, not UI display
    order; it can include cards held by a player who stayed or busted.
    ``round_score`` is the score the current hand would receive without a
    Flip 7 bonus or penalty; a busted player's score may be negative in Brutal
    Mode. The score awarded at round end can differ.
    """

    player: int
    """Zero-based seat ID."""

    total_score: int
    """Cumulative score from completed rounds."""

    status: PlayerStatus
    """Whether this player is active, stayed, or busted in the current round."""

    cards: tuple[Card, ...]
    """Revealed cards in engine hand order, including unresolved cards."""
    round_score: int
    """In-progress score, excluding any Flip 7 bonus or penalty."""


@dataclass(frozen=True)
class RoundResult:
    """Scores awarded at the end of one round, in seat order.

    ``scores`` includes any bonus or penalty; ``totals`` contains the updated
    cumulative scores. ``flip_seven_player`` identifies the seat that achieved
    Flip 7, or is ``None`` if nobody did. In Brutal Mode that player may have
    chosen to apply the bonus as a penalty instead of receiving it.
    """

    round_number: int
    scores: tuple[int, ...]
    totals: tuple[int, ...]
    flip_seven_player: int | None


@dataclass(frozen=True)
class RoundStarted:
    """The numbered round has begun, before its initial cards are dealt."""

    round_number: int


@dataclass(frozen=True)
class CardDrawn:
    """A card was drawn for ``player`` in the indicated round."""

    round_number: int
    player: int
    card: Card


@dataclass(frozen=True)
class ActionChosen:
    """A player made a decision; automatic card effects are not decisions."""

    round_number: int
    player: int
    action: Action


@dataclass(frozen=True)
class DiscardShuffled:
    """The discard pile was shuffled into an empty draw pile."""

    round_number: int


@dataclass(frozen=True)
class RoundEnded:
    """A round finished with the given scores and cumulative totals."""

    round_number: int
    result: RoundResult


GameEvent = RoundStarted | CardDrawn | ActionChosen | DiscardShuffled | RoundEnded


@dataclass(frozen=True)
class Observation:
    """Immutable public snapshot from the perspective of one player.

    Player IDs are zero-based seat indices. ``player`` is the player for whom
    ``Game.observe(player)`` was called; ``current_player`` is the player
    whose decision the game is waiting for. They can differ. For example,
    observing seat 0 while seat 1 is deciding gives ``player == 0`` and
    ``current_player == 1``, with no legal actions in that observation.

    All revealed hands and the discard pile are public; the draw pile's order
    is hidden. The tuples are snapshots and do not change as the game advances.
    """

    player: int
    """Seat whose perspective was requested, not necessarily the player to act."""

    current_player: int | None
    """Seat whose decision is pending, or ``None`` when the game is finished."""

    round_number: int
    """Current round, numbered from one."""

    dealer: int
    """Current dealer's seat; dealing starts with the next seat."""

    players: tuple[PlayerView, ...]
    """Public player snapshots in seat order; index with a player ID."""

    cards_remaining: int
    """Number of undrawn cards, excluding the discard pile."""

    discard: tuple[Card, ...]
    """Cards currently in the public discard pile."""

    legal_actions: tuple[Action, ...]
    """Legal decisions for ``player``, empty unless that player must act."""

    pending_card: Card | None
    """Card awaiting a target or card choice, regardless of observer; otherwise ``None``.

    A Brutal Flip 7 bonus decision has no pending card.
    """

    last_round: RoundResult | None
    """Most recently completed round's result, or ``None`` before the first ends."""

    winners: tuple[int, ...]
    """Winning seat IDs after the game ends, including ties; otherwise empty."""

    events: tuple[GameEvent, ...]
    """Public events of the current round, in order; reset when a new round starts."""

    _sampler: Callable[[Random], Game] | None = field(
        default=None, repr=False, compare=False
    )

    def sample_game(self, rng: Random) -> Game:
        """Return an independent game consistent with this observation.

        The hidden deck order and future reshuffles are drawn from ``rng``, so
        the copy can be played forward to simulate possible outcomes. Raises
        ``RuntimeError`` if the original game has advanced since this snapshot,
        or ``ValueError`` if the observation is not linked to a game.
        """
        if self._sampler is None:
            raise ValueError("observation is not linked to a game")
        return self._sampler(rng)
