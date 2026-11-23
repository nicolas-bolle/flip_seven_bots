"""A turn-based, headless engine for the base and With a Vengeance games.

Automatic effects are queued as tasks. The engine executes them until a player
decision is needed, then resumes the queue when ``Game.apply`` is called.
"""

import copy
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from functools import partial
from random import Random

from .deck import Deck
from .model import (
    Action,
    ActionChosen,
    ActionType,
    Card,
    CardDrawn,
    CardType,
    ChooseCard,
    ChooseTarget,
    Decision,
    DiscardShuffled,
    FlipSevenBonus,
    GameEvent,
    HitOrStay,
    Observation,
    PlayerStatus,
    PlayerView,
    RoundEnded,
    RoundResult,
    RoundStarted,
)
from .rules import Rules, VengeanceRules

_SECOND_CHANCE = Card(CardType.SECOND_CHANCE)
_VENGEANCE_ACTIONS = frozenset(
    (
        CardType.JUST_ONE_MORE,
        CardType.FLIP_FOUR,
        CardType.SWAP,
        CardType.STEAL,
        CardType.DISCARD,
    )
)
_VENGEANCE_MODIFIERS = frozenset((CardType.SUBTRACT, CardType.DIVIDE))
_ROUND_ACTIONS = frozenset((CardType.FREEZE, CardType.FLIP_THREE))
_SINGLE_USE = _VENGEANCE_ACTIONS | _ROUND_ACTIONS

MAX_PLAYERS = 10
"""Most seats a game allows, so the draw and discard piles can never both run out.

Each player holds at most seven number cards, and the one drawing at most six,
so with more seats every number card could be on the table with none to draw.
"""


def _sample_observation(
    snapshot: Game,
    version: list[int],
    expected: int,
    rng: Random,
    next_draws: Sequence[Card],
) -> Game:
    if version[0] != expected:
        raise RuntimeError("observation is out of date; the game has advanced")
    clone = snapshot.determinize(rng)
    clone._deck.stack(next_draws)
    return clone


@dataclass
class _Player:
    total_score: int = 0
    status: PlayerStatus = PlayerStatus.ACTIVE
    cards: list[Card] = field(default_factory=list)
    unresolved: list[Card] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.status is PlayerStatus.ACTIVE

    @property
    def is_busted(self) -> bool:
        return self.status is PlayerStatus.BUSTED

    def number_count(self) -> int:
        return sum(card.is_number for card in self.cards)

    def round_score(self, score_cards: Callable[[Iterable[Card]], int]) -> int:
        return 0 if self.is_busted else score_cards(self.cards)

    def reset(self) -> None:
        self.status = PlayerStatus.ACTIVE
        self.cards.clear()
        self.unresolved.clear()


@dataclass(eq=False)
class _FlipSequence:
    """Track a multi-card flip and effects deferred until its draws finish."""

    player: int
    card: Card
    deferred: list[_Resolve] = field(default_factory=list)


@dataclass(frozen=True)
class _Draw:
    player: int
    sequence: _FlipSequence | None = None
    force: bool = False


@dataclass(frozen=True)
class _Resolve:
    player: int
    card: Card
    sequence: _FlipSequence | None = None


@dataclass(frozen=True)
class _FinishFlip:
    sequence: _FlipSequence


@dataclass(frozen=True)
class _FindTurn:
    start: int


@dataclass(frozen=True)
class _EndRound:
    flip_seven_player: int | None


_Task = _Draw | _Resolve | _FinishFlip | _FindTurn | _EndRound


class Game:
    """Run a match; player IDs are zero-based seat indices.

    The engine advances automatically until a player must make a decision.
    ``observe`` exposes public information, never the shuffled deck. Use
    ``VengeanceRules`` to select the alternate game.

    ``player_count`` must be between one and ``MAX_PLAYERS`` and ``dealer``
    must identify a seat.
    ``seed`` controls the shuffled deck; alternatively, pass a prepared
    ``deck`` (but not both). Initial dealing occurs during construction and
    may itself stop at an action-card decision.
    """

    def __init__(
        self,
        player_count: int,
        *,
        rules: Rules | None = None,
        deck: Deck | None = None,
        seed: int | None = None,
        dealer: int = 0,
    ):
        if not 1 <= player_count <= MAX_PLAYERS:
            raise ValueError(f"player_count must be between 1 and {MAX_PLAYERS}")
        if not 0 <= dealer < player_count:
            raise ValueError("dealer must be a valid player index")
        if deck is not None and seed is not None:
            raise ValueError("pass either a deck or a seed, not both")

        self._rules = rules if rules is not None else Rules()
        self._deck = (
            deck if deck is not None else Deck(self._rules.build_deck(), Random(seed))
        )
        self._players = [_Player() for _ in range(player_count)]
        self._dealer = dealer
        self._round_number = 0
        self._last_round: RoundResult | None = None
        self._winners: tuple[int, ...] = ()
        self._tasks: deque[_Task] = deque()
        self._pending: Decision | None = None
        self._events: list[GameEvent] = []
        self._recent_draws: list[CardDrawn] = []
        self._version = 0
        self._version_token = [0]
        self._start_round()
        self._advance()

    @property
    def current_player(self) -> int | None:
        """Seat whose decision is pending, or ``None`` after the game ends."""
        return self._pending.player if self._pending is not None else None

    @property
    def round_number(self) -> int:
        """The current one-based round number."""
        return self._round_number

    @property
    def last_round(self) -> RoundResult | None:
        """The latest completed round, or ``None`` before the first ends."""
        return self._last_round

    @property
    def rules(self) -> Rules:
        """The rules used for this match."""
        return self._rules

    @property
    def recent_draws(self) -> tuple[CardDrawn, ...]:
        """Cards drawn during initialization or the most recent decision."""
        return tuple(self._recent_draws)

    def hidden_deck(self) -> tuple[Card, ...]:
        """The undrawn cards, next card first. For debugging only; bots must not use it."""
        return self._deck.remaining

    @property
    def is_finished(self) -> bool:
        """Whether the game has ended and winners have been determined."""
        return bool(self._winners)

    @property
    def winners(self) -> tuple[int, ...]:
        """Winning seat IDs, including ties; empty until the game ends."""
        return self._winners

    def observe(self, player: int) -> Observation:
        """Return a public snapshot from the requested seat's perspective.

        ``player`` need not be the current player, but only the current
        player receives legal actions. Raises ``ValueError`` for an invalid
        seat. The returned snapshot can be sampled only until the game advances.
        """
        if not 0 <= player < len(self._players):
            raise ValueError("player must be a valid player index")
        views = tuple(
            PlayerView(
                player=index,
                total_score=state.total_score,
                status=state.status,
                cards=tuple(state.cards),
                unresolved=tuple(state.unresolved),
                round_score=self._round_score(state),
            )
            for index, state in enumerate(self._players)
        )
        return Observation(
            player=player,
            current_player=self.current_player,
            round_number=self._round_number,
            dealer=self._dealer,
            players=views,
            draw_pile=self._deck.composition,
            discard=self._deck.discard_pile,
            decision=self._pending,
            last_round=self._last_round,
            winners=self._winners,
            events=tuple(self._events),
            _sampler=partial(
                _sample_observation,
                self._public_snapshot(),
                self._version_token,
                self._version,
            ),
        )

    def _public_snapshot(self) -> Game:
        snapshot = copy.copy(self)
        snapshot._deck = copy.copy(self._deck)
        snapshot._deck._cards = list(self._deck.composition)
        snapshot._deck._discard = list(self._deck.discard_pile)
        snapshot._deck._random = Random(0)
        snapshot._players = [
            _Player(
                player.total_score,
                player.status,
                list(player.cards),
                list(player.unresolved),
            )
            for player in self._players
        ]
        snapshot._tasks = copy.deepcopy(self._tasks)
        snapshot._events = list(self._events)
        snapshot._recent_draws = list(self._recent_draws)
        snapshot._version_token = [self._version]
        return snapshot

    def determinize(self, rng: Random) -> Game:
        """Return an independent copy with the hidden deck order resampled from ``rng``."""
        # Seeding the memo substitutes ``rng`` for the deck's generator instead of copying it.
        clone = copy.deepcopy(self, {id(self._deck._random): rng})
        clone._deck.resample(rng)
        return clone

    def apply(self, action: Action) -> None:
        """Apply a legal decision and advance to the next decision or game end.

        Raises ``ValueError`` if the action is not currently legal.
        """
        decision = self._pending
        if decision is None or action not in decision.actions:
            raise ValueError(f"illegal action: {action!r}")
        self._pending = None
        self._version += 1
        self._version_token[0] = self._version
        self._events.append(ActionChosen(self._round_number, decision.player, action))

        match decision:
            case ChooseTarget():
                assert action.target is not None  # guaranteed by Action validation
                self._apply_target(decision, action.target)
            case ChooseCard():
                assert action.target is not None and action.card_index is not None
                self._apply_card_choice(decision, action.target, action.card_index)
            case FlipSevenBonus(player=player):
                self._finish_round(player, penalty_target=action.target)
            case HitOrStay(player=player):
                self._tasks.appendleft(_FindTurn((player + 1) % len(self._players)))
                if action.kind is ActionType.STAY:
                    self._players[player].status = PlayerStatus.STAYED
                else:
                    self._tasks.appendleft(_Draw(player))
        self._advance()

    def _start_round(self) -> None:
        self._round_number += 1
        for player in self._players:
            player.reset()
        self._tasks.clear()
        self._pending = None
        self._events.clear()
        self._events.append(RoundStarted(self._round_number))
        first = (self._dealer + 1) % len(self._players)
        for offset in range(len(self._players)):
            self._tasks.append(_Draw((first + offset) % len(self._players)))
        self._tasks.append(_FindTurn(first))

    def _advance(self) -> None:
        """Process queued automatic effects until a decision or game end."""
        self._recent_draws.clear()
        while self._pending is None and not self.is_finished:
            if not isinstance(self._rules, VengeanceRules) and not any(
                player.is_active for player in self._players
            ):
                self._end_round(flip_seven_player=None)
                continue
            match self._tasks.popleft():
                case _Draw(player=player, sequence=sequence, force=force):
                    if self._players[player].is_active or (
                        force and not self._players[player].is_busted
                    ):
                        self._draw(player, sequence)
                case _Resolve(sequence=sequence) as effect:
                    if sequence is None or not self._players[sequence.player].is_busted:
                        self._resolve(effect)
                    elif effect.card.kind not in _ROUND_ACTIONS:
                        self._discard_unresolved(effect.player, effect.card)
                case _FinishFlip(sequence=sequence):
                    if sequence.card.kind not in _ROUND_ACTIONS:
                        self._discard_action(sequence.player, sequence.card)
                    if not self._players[sequence.player].is_busted:
                        self._tasks.extendleft(reversed(sequence.deferred))
                    else:
                        for effect in sequence.deferred:
                            if effect.card.kind not in _ROUND_ACTIONS:
                                self._discard_unresolved(effect.player, effect.card)
                case _FindTurn(start=start):
                    if any(player.is_active for player in self._players):
                        self._find_turn(start)
                    else:
                        self._end_round(flip_seven_player=None)
                case _EndRound(flip_seven_player=flip_seven_player):
                    self._end_round(flip_seven_player)

    def _find_turn(self, start: int) -> None:
        for offset in range(len(self._players)):
            candidate = (start + offset) % len(self._players)
            if self._players[candidate].is_active:
                self._pending = HitOrStay(candidate, self._can_stay(candidate))
                return

    def _can_stay(self, player_index: int) -> bool:
        cards = self._players[player_index].cards
        return bool(cards) and not any(card.kind is CardType.ZERO for card in cards)

    def _draw(self, player_index: int, sequence: _FlipSequence | None) -> None:
        card, reshuffled = self._deck.draw()
        if reshuffled:
            self._events.append(DiscardShuffled(self._round_number))
        event = CardDrawn(self._round_number, player_index, card)
        self._events.append(event)
        self._recent_draws.append(event)
        match card.kind:
            case (
                CardType.NUMBER
                | CardType.ZERO
                | CardType.UNLUCKY_SEVEN
                | CardType.LUCKY_THIRTEEN
            ):
                self._receive_number(player_index, card)
            case CardType.SECOND_CHANCE:
                self._receive_second_chance(player_index, card)
            case (
                CardType.FREEZE
                | CardType.FLIP_THREE
                | CardType.JUST_ONE_MORE
                | CardType.FLIP_FOUR
                | CardType.SWAP
                | CardType.STEAL
                | CardType.DISCARD
                | CardType.SUBTRACT
                | CardType.DIVIDE
            ):
                self._players[player_index].unresolved.append(card)
                effect = _Resolve(player_index, card, sequence)
                if sequence is None:
                    self._tasks.appendleft(effect)
                else:
                    sequence.deferred.append(effect)
            case CardType.ADD | CardType.MULTIPLY:
                self._players[player_index].cards.append(card)

    def _receive_number(self, player_index: int, card: Card) -> None:
        player = self._players[player_index]
        if card.kind is CardType.UNLUCKY_SEVEN:
            for existing in player.cards[:]:
                if existing.is_number or existing.kind in _VENGEANCE_MODIFIERS:
                    player.cards.remove(existing)
                    self._deck.discard((existing,))
            player.cards.append(card)
            return
        matching = [
            existing
            for existing in player.cards
            if existing.is_number and existing.value == card.value
        ]
        lucky_thirteen = (
            card.value == 13
            and len(matching) == 1
            and (
                card.kind is CardType.LUCKY_THIRTEEN
                or matching[0].kind is CardType.LUCKY_THIRTEEN
            )
        )
        if not matching or lucky_thirteen:
            player.cards.append(card)
            if player.number_count() == 7 and not any(
                isinstance(task, _EndRound) for task in self._tasks
            ):
                self._tasks.appendleft(_EndRound(flip_seven_player=player_index))
        elif _SECOND_CHANCE in player.cards:
            player.cards.remove(_SECOND_CHANCE)
            self._deck.discard((_SECOND_CHANCE, card))
        else:
            player.cards.append(card)
            player.status = PlayerStatus.BUSTED

    def _receive_second_chance(self, player_index: int, card: Card) -> None:
        player = self._players[player_index]
        if card not in player.cards:
            player.cards.append(card)
            return
        targets = tuple(
            index
            for index, other in enumerate(self._players)
            if index != player_index and other.is_active and card not in other.cards
        )
        if targets:
            player.unresolved.append(card)
            self._pending = ChooseTarget(player_index, card, targets)
        else:
            self._deck.discard((card,))

    def _resolve(self, effect: _Resolve) -> None:
        if effect.card.kind in (CardType.SWAP, CardType.STEAL, CardType.DISCARD):
            choices = self._card_choices(effect.player, effect.card)
            if choices:
                self._pending = ChooseCard(effect.player, effect.card, choices)
            else:
                self._discard_unresolved(effect.player, effect.card)
            return
        # The loop in _advance ends the round before this runs if nobody is active.
        targets = tuple(
            index
            for index, player in enumerate(self._players)
            if (
                player.is_active
                if not isinstance(self._rules, VengeanceRules)
                else (
                    not player.is_busted
                    or (self._rules.brutal and effect.card.kind in _VENGEANCE_MODIFIERS)
                )
            )
        )
        self._pending = ChooseTarget(effect.player, effect.card, targets)

    def _apply_target(self, decision: ChooseTarget, target: int) -> None:
        self._players[decision.player].unresolved.remove(decision.card)
        recipient = self._players[target]
        if decision.card.kind is CardType.FREEZE:
            recipient.status = PlayerStatus.STAYED
            recipient.cards.append(decision.card)
        elif decision.card.kind is CardType.FLIP_THREE:
            recipient.cards.append(decision.card)
            sequence = _FlipSequence(target, decision.card)
            self._tasks.appendleft(_FinishFlip(sequence))
            for _ in range(3):
                self._tasks.appendleft(_Draw(target, sequence))
        elif decision.card.kind is CardType.JUST_ONE_MORE:
            self._deck.discard((decision.card,))
            recipient.status = PlayerStatus.STAYED
            self._tasks.appendleft(_Draw(target, force=True))
        elif decision.card.kind is CardType.FLIP_FOUR:
            recipient.cards.append(decision.card)
            sequence = _FlipSequence(target, decision.card)
            self._tasks.appendleft(_FinishFlip(sequence))
            for _ in range(4):
                self._tasks.appendleft(_Draw(target, sequence, force=True))
        else:
            recipient.cards.append(decision.card)

    def _card_choices(
        self, player: int, action_card: Card, first: tuple[int, int] | None = None
    ) -> tuple[tuple[int, int], ...]:
        """Find eligible (owner, hand index) pairs for a card-selection effect."""
        choices = tuple(
            (index, card_index)
            for index, state in enumerate(self._players)
            if not state.is_busted
            for card_index, card in enumerate(state.cards)
            if (card.is_number or card.kind in _VENGEANCE_MODIFIERS)
            and (action_card.kind is not CardType.STEAL or index != player)
            and (first is None or index != first[0])
        )
        if action_card.kind is CardType.SWAP and first is None:
            owners = {owner for owner, _ in choices}
            if len(owners) < 2:
                return ()
        return choices

    def _apply_card_choice(self, decision: ChooseCard, owner: int, index: int) -> None:
        if decision.card.kind is CardType.SWAP and decision.first is None:
            first = (owner, index)
            choices = self._card_choices(decision.player, decision.card, first)
            self._pending = ChooseCard(decision.player, decision.card, choices, first)
            return
        card = self._players[owner].cards.pop(index)
        if decision.card.kind is CardType.DISCARD:
            self._deck.discard((card,))
        elif decision.card.kind is CardType.STEAL:
            self._receive_transferred(decision.player, card)
        else:
            assert decision.first is not None
            first_owner, first_index = decision.first
            first_card = self._players[first_owner].cards.pop(first_index)
            self._receive_transferred(first_owner, card)
            self._receive_transferred(owner, first_card)
        self._discard_unresolved(decision.player, decision.card)

    def _receive_transferred(self, player: int, card: Card) -> None:
        if card.is_number:
            self._receive_number(player, card)
        else:
            self._players[player].cards.append(card)

    def _discard_action(self, player: int, card: Card) -> None:
        self._players[player].cards.remove(card)
        self._deck.discard((card,))

    def _discard_unresolved(self, player: int, card: Card) -> None:
        self._players[player].unresolved.remove(card)
        self._deck.discard((card,))

    def _end_round(self, flip_seven_player: int | None) -> None:
        if (
            flip_seven_player is not None
            and isinstance(self._rules, VengeanceRules)
            and self._rules.brutal
            and len(self._players) > 1
        ):
            self._pending = FlipSevenBonus(
                flip_seven_player,
                tuple(p for p in range(len(self._players)) if p != flip_seven_player),
            )
            return
        self._finish_round(flip_seven_player)

    def _round_score(self, player: _Player, *, flip_seven: bool = False) -> int:
        """Score a hand before its Flip 7 bonus or penalty is applied."""
        if isinstance(self._rules, VengeanceRules):
            if player.is_busted:
                if not self._rules.brutal:
                    return 0
                return self._rules.score_cards(
                    card for card in player.cards if card.kind in _VENGEANCE_MODIFIERS
                )
            if flip_seven:
                return self._rules.score_cards(
                    card for card in player.cards if card.kind is not CardType.ZERO
                )
        return player.round_score(self._rules.score_cards)

    def _finish_round(
        self, flip_seven_player: int | None, *, penalty_target: int | None = None
    ) -> None:
        scores = tuple(
            self._round_score(player, flip_seven=index == flip_seven_player)
            + (
                self._rules.flip_seven_bonus
                if index == flip_seven_player and penalty_target is None
                else 0
            )
            - (self._rules.flip_seven_bonus if index == penalty_target else 0)
            for index, player in enumerate(self._players)
        )
        for index, player in enumerate(self._players):
            for card in player.cards[:]:
                if card.kind in _SINGLE_USE:
                    self._discard_action(index, card)
            self._deck.discard(player.unresolved)
            player.unresolved.clear()
        for player, score in zip(self._players, scores):
            player.total_score += score
        totals = tuple(player.total_score for player in self._players)
        self._last_round = RoundResult(
            self._round_number, scores, totals, flip_seven_player
        )
        self._events.append(RoundEnded(self._round_number, self._last_round))
        high_score = max(totals)
        if high_score >= self._rules.target_score:
            self._winners = tuple(
                i for i, total in enumerate(totals) if total == high_score
            )
            self._tasks.clear()
            self._pending = None
        else:
            for player in self._players:
                self._deck.discard(player.cards)
            self._dealer = (self._dealer + 1) % len(self._players)
            self._start_round()
