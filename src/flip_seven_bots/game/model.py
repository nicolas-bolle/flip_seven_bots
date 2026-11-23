"""Public, immutable values shared by the engine, bots, and UI."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum, auto
from random import Random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import Game


class CardType(Enum):
    """Kinds of cards in the base and With a Vengeance decks."""

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
    """An immutable card; equal cards are interchangeable."""

    kind: CardType
    """Kind of card."""

    value: int = 0
    """Printed number for number and modifier cards; generally zero for action cards."""

    @property
    def is_number(self) -> bool:
        """Whether this card counts as a number, including Vengeance special numbers."""
        return self.kind in (
            CardType.NUMBER,
            CardType.ZERO,
            CardType.UNLUCKY_SEVEN,
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

    Constructing an action with fields inappropriate for its kind raises
    ``ValueError``; the engine separately checks whether it is legal.
    """

    kind: ActionType
    """Type of decision."""

    target: int | None = None
    """Chosen player for ``CHOOSE_TARGET``, card owner for ``CHOOSE_CARD``, else ``None``."""

    card_index: int | None = None
    """For ``CHOOSE_CARD``, index into the owner's ``PlayerView.cards``; otherwise ``None``.

    Indexes the current observation's hand order, not the visually sorted UI.
    """

    def __post_init__(self) -> None:
        if (self.kind in (ActionType.CHOOSE_TARGET, ActionType.CHOOSE_CARD)) != (
            self.target is not None
        ):
            raise ValueError(
                "an action has a target exactly when it chooses a target or card"
            )
        if (self.kind is ActionType.CHOOSE_CARD) != (self.card_index is not None):
            raise ValueError(
                "an action has a card index exactly when it chooses a card"
            )


@dataclass(frozen=True)
class HitOrStay:
    """The acting player's turn: draw a card or stay."""

    player: int
    """Seat that must decide."""

    can_stay: bool
    """Whether ``STAY`` is legal in addition to ``HIT``.

    Staying is unavailable with an empty hand, or while holding a Vengeance
    Zero.
    """

    @property
    def actions(self) -> tuple[Action, ...]:
        """Legal actions, in a stable order."""
        return (self.hit(), self.stay()) if self.can_stay else (self.hit(),)

    def hit(self) -> Action:
        return Action(ActionType.HIT)

    def stay(self) -> Action:
        return Action(ActionType.STAY)


@dataclass(frozen=True)
class ChooseTarget:
    """Choose the player who receives ``card``.

    Used for Freeze, Flip Three, giving away a duplicate Second Chance, and
    the targeted Vengeance cards.
    """

    player: int
    """Seat that must decide."""

    card: Card
    """Card being resolved."""

    targets: tuple[int, ...]
    """Eligible seats in seat order; may include ``player`` itself."""

    @property
    def actions(self) -> tuple[Action, ...]:
        """Legal actions, in the order of ``targets``."""
        return tuple(self.choose(target) for target in self.targets)

    def choose(self, target: int) -> Action:
        return Action(ActionType.CHOOSE_TARGET, target)


@dataclass(frozen=True)
class ChooseCard:
    """Choose a card in someone's hand for a Vengeance Swap, Steal, or Discard.

    A Swap takes two such decisions, one per card.
    """

    player: int
    """Seat that must decide."""

    card: Card
    """Card being resolved."""

    choices: tuple[tuple[int, int], ...]
    """Eligible ``(owner, card_index)`` pairs, indexing ``PlayerView.cards``."""

    first: tuple[int, int] | None = None
    """In a Swap's second decision, the ``(owner, card_index)`` picked first; else ``None``."""

    @property
    def actions(self) -> tuple[Action, ...]:
        """Legal actions, in the order of ``choices``."""
        return tuple(self.choose(owner, index) for owner, index in self.choices)

    def choose(self, owner: int, card_index: int) -> Action:
        return Action(ActionType.CHOOSE_CARD, owner, card_index)


@dataclass(frozen=True)
class FlipSevenBonus:
    """Brutal Mode: take the Flip 7 bonus or subtract it from one of ``targets``."""

    player: int
    """Seat that achieved Flip 7 and must decide."""

    targets: tuple[int, ...]
    """Opponents who can receive the penalty."""

    @property
    def actions(self) -> tuple[Action, ...]:
        """Taking the bonus, followed by each penalty target."""
        return (self.take(),) + tuple(self.penalize(target) for target in self.targets)

    def take(self) -> Action:
        return Action(ActionType.TAKE_BONUS)

    def penalize(self, target: int) -> Action:
        return Action(ActionType.CHOOSE_TARGET, target)


Decision = HitOrStay | ChooseTarget | ChooseCard | FlipSevenBonus
"""A pending choice; ``player`` is the seat that must make it."""


@dataclass(frozen=True)
class PlayerView:
    """Public snapshot of one seat's cards, status, and scores."""

    player: int
    """Zero-based seat ID."""

    total_score: int
    """Cumulative score from completed rounds."""

    status: PlayerStatus
    """Whether this player is active, stayed, or busted in the current round."""

    cards: tuple[Card, ...]
    """The player's hand in engine hand order, not UI display order.

    Includes cards kept after staying or busting, but not ``unresolved`` cards.
    """

    unresolved: tuple[Card, ...]
    """Action and modifier cards this player revealed that are awaiting resolution.

    They wait for a target, a card choice, or the end of a multi-card flip.
    They are in nobody's hand, so they affect no score and cannot be chosen
    by a Swap, Steal, or Discard.
    """

    round_score: int
    """Score the current hand would receive, excluding any Flip 7 bonus or penalty.

    A busted player's score may be negative in Brutal Mode. The score awarded
    at round end can differ.
    """


@dataclass(frozen=True)
class RoundResult:
    """Scores awarded at the end of one round."""

    round_number: int
    """Round that ended, numbered from one."""

    scores: tuple[int, ...]
    """Round scores in seat order, including any Flip 7 bonus or penalty."""

    totals: tuple[int, ...]
    """Updated cumulative scores in seat order."""

    flip_seven_player: int | None
    """Seat that achieved Flip 7, or ``None`` if nobody did.

    In Brutal Mode that player may have applied the bonus as a penalty to
    another player instead of receiving it.
    """


@dataclass(frozen=True)
class RoundStarted:
    """A round has begun, before its initial cards are dealt."""

    round_number: int
    """Round that began, numbered from one."""


@dataclass(frozen=True)
class CardDrawn:
    """A card was drawn from the deck for a player."""

    round_number: int
    """Round in which the card was drawn."""

    player: int
    """Seat that received the card."""

    card: Card
    """Card drawn."""


@dataclass(frozen=True)
class ActionChosen:
    """A player made a decision; automatic card effects are not decisions."""

    round_number: int
    """Round in which the decision was made."""

    player: int
    """Seat that decided."""

    action: Action
    """Decision made."""


@dataclass(frozen=True)
class DiscardShuffled:
    """The discard pile was shuffled into an empty draw pile."""

    round_number: int
    """Round in which the reshuffle happened."""


@dataclass(frozen=True)
class RoundEnded:
    """A round finished."""

    round_number: int
    """Round that ended."""

    result: RoundResult
    """Scores and cumulative totals for the round."""


GameEvent = RoundStarted | CardDrawn | ActionChosen | DiscardShuffled | RoundEnded


@dataclass(frozen=True)
class Observation:
    """Immutable public snapshot from the perspective of one player.

    Player IDs are zero-based seat indices. ``player`` is the player for whom
    ``Game.observe(player)`` was called; ``current_player`` is the player
    whose decision the game is waiting for. They can differ. For example,
    observing seat 0 while seat 1 is deciding gives ``player == 0`` and
    ``current_player == 1``, with no legal actions in that observation. The
    pending ``decision`` is public, so it is visible from every seat.

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

    draw_pile: tuple[Card, ...]
    """Undrawn cards, excluding the discard pile, in a fixed sorted order.

    The composition is public because the full deck and every revealed card
    are known; the order in which the cards will be drawn is hidden.
    """

    discard: tuple[Card, ...]
    """Cards currently in the public discard pile."""

    decision: Decision | None
    """Choice the game is waiting for, regardless of observer; ``None`` once finished."""

    last_round: RoundResult | None
    """Most recently completed round's result, or ``None`` before the first ends."""

    winners: tuple[int, ...]
    """Winning seat IDs after the game ends, including ties; otherwise empty."""

    events: tuple[GameEvent, ...]
    """Public events of the current round, in order; reset when a new round starts."""

    _sampler: Callable[[Random, Sequence[Card]], Game] | None = field(
        default=None, repr=False, compare=False
    )

    @property
    def cards_remaining(self) -> int:
        """Number of undrawn cards, excluding the discard pile."""
        return len(self.draw_pile)

    @property
    def legal_actions(self) -> tuple[Action, ...]:
        """Legal actions for ``player``, empty unless that player must act."""
        decision = self.decision
        if decision is None or decision.player != self.player:
            return ()
        return decision.actions

    def sample_game(self, rng: Random, *, next_draws: Sequence[Card] = ()) -> Game:
        """Return an independent game consistent with this observation.

        The hidden deck order and future reshuffles are drawn from ``rng``, so
        the copy can be played forward to simulate possible outcomes.
        ``next_draws`` fixes the next cards drawn, in order; they must be in
        ``draw_pile``, or in ``discard`` when the draw pile is empty and the
        next draw would reshuffle it.

        Raises ``RuntimeError`` if the original game has advanced since this
        snapshot, or ``ValueError`` if the observation is not linked to a game
        or ``next_draws`` are unavailable.
        """
        if self._sampler is None:
            raise ValueError("observation is not linked to a game")
        return self._sampler(rng, next_draws)
