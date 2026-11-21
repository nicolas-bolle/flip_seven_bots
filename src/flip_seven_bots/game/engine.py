"""A turn-based, headless implementation of the base game."""

import copy
from collections import deque
from collections.abc import Callable, Iterable
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
    DiscardShuffled,
    GameEvent,
    Observation,
    PlayerStatus,
    PlayerView,
    RoundEnded,
    RoundResult,
    RoundStarted,
)
from .rules import Rules

_SECOND_CHANCE = Card(CardType.SECOND_CHANCE)


@dataclass
class _Player:
    total_score: int = 0
    status: PlayerStatus = PlayerStatus.ACTIVE
    cards: list[Card] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.status is PlayerStatus.ACTIVE

    @property
    def is_busted(self) -> bool:
        return self.status is PlayerStatus.BUSTED

    def number_count(self) -> int:
        return sum(card.kind is CardType.NUMBER for card in self.cards)

    def round_score(self, score_cards: Callable[[Iterable[Card]], int]) -> int:
        return 0 if self.is_busted else score_cards(self.cards)

    def reset(self) -> None:
        self.status = PlayerStatus.ACTIVE
        self.cards.clear()


@dataclass(eq=False)
class _FlipSequence:
    player: int
    card: Card
    deferred: list[_Resolve] = field(default_factory=list)


@dataclass(frozen=True)
class _Draw:
    player: int
    sequence: _FlipSequence | None = None


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


@dataclass(frozen=True)
class _HitOrStay:
    player: int


@dataclass(frozen=True)
class _TargetDecision:
    player: int
    card: Card
    targets: tuple[int, ...]


_Decision = _HitOrStay | _TargetDecision


class Game:
    """Run a base-game match; player IDs are zero-based seat indices.

    The engine advances automatically until a player must make a decision.
    ``observe`` exposes public information, never the shuffled deck.
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
        if player_count < 1:
            raise ValueError("player_count must be at least one")
        if not 0 <= dealer < player_count:
            raise ValueError("dealer must be a valid player index")
        if deck is not None and seed is not None:
            raise ValueError("pass either a deck or a seed, not both")

        self._rules = rules if rules is not None else Rules()
        self._deck = deck if deck is not None else Deck(self._rules.build_deck(), Random(seed))
        self._players = [_Player() for _ in range(player_count)]
        self._dealer = dealer
        self._round_number = 0
        self._last_round: RoundResult | None = None
        self._winners: tuple[int, ...] = ()
        self._tasks: deque[_Task] = deque()
        self._pending: _Decision | None = None
        self._events: list[GameEvent] = []
        self._recent_draws: list[CardDrawn] = []
        self._version = 0
        self._start_round()
        self._advance()

    @property
    def current_player(self) -> int | None:
        return self._pending.player if self._pending is not None else None

    @property
    def round_number(self) -> int:
        return self._round_number

    @property
    def last_round(self) -> RoundResult | None:
        return self._last_round

    @property
    def rules(self) -> Rules:
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
        return bool(self._winners)

    @property
    def winners(self) -> tuple[int, ...]:
        return self._winners

    def observe(self, player: int) -> Observation:
        if not 0 <= player < len(self._players):
            raise ValueError("player must be a valid player index")
        views = tuple(
            PlayerView(
                player=index,
                total_score=state.total_score,
                status=state.status,
                cards=tuple(state.cards),
                round_score=state.round_score(self._rules.score_cards),
            )
            for index, state in enumerate(self._players)
        )
        pending = self._pending
        return Observation(
            player=player,
            current_player=self.current_player,
            round_number=self._round_number,
            dealer=self._dealer,
            players=views,
            cards_remaining=len(self._deck),
            discard=self._deck.discard_pile,
            legal_actions=(
                self._legal_actions(pending)
                if pending is not None and pending.player == player
                else ()
            ),
            pending_card=pending.card if isinstance(pending, _TargetDecision) else None,
            last_round=self._last_round,
            winners=self._winners,
            events=tuple(self._events),
            _sampler=partial(self._sample, self._version),
        )

    def determinize(self, rng: Random) -> Game:
        """Return an independent copy with the hidden deck order resampled from ``rng``."""
        # Seeding the memo substitutes ``rng`` for the deck's generator instead of copying it.
        clone = copy.deepcopy(self, {id(self._deck._random): rng})
        clone._deck.resample(rng)
        return clone

    def apply(self, action: Action) -> None:
        """Apply one legal decision and advance to the next decision or game end."""
        decision = self._pending
        if decision is None or action not in self._legal_actions(decision):
            raise ValueError(f"illegal action: {action!r}")
        self._pending = None
        self._version += 1
        self._events.append(ActionChosen(self._round_number, decision.player, action))

        match decision:
            case _TargetDecision():
                assert action.target is not None  # guaranteed by Action validation
                self._apply_target(decision, action.target)
            case _HitOrStay(player=player):
                self._tasks.appendleft(_FindTurn((player + 1) % len(self._players)))
                if action.kind is ActionType.STAY:
                    self._players[player].status = PlayerStatus.STAYED
                else:
                    self._tasks.appendleft(_Draw(player))
        self._advance()

    def _sample(self, version: int, rng: Random) -> Game:
        if version != self._version:
            raise RuntimeError("observation is out of date; the game has advanced")
        return self.determinize(rng)

    def _legal_actions(self, decision: _Decision) -> tuple[Action, ...]:
        match decision:
            case _TargetDecision(targets=targets):
                return tuple(Action(ActionType.CHOOSE_TARGET, target) for target in targets)
            case _HitOrStay(player=player):
                if self._players[player].cards:
                    return (Action(ActionType.HIT), Action(ActionType.STAY))
                return (Action(ActionType.HIT),)

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
        self._recent_draws.clear()
        while self._pending is None and not self.is_finished:
            if not any(player.is_active for player in self._players):
                self._end_round(flip_seven_player=None)
                continue
            match self._tasks.popleft():
                case _Draw(player=player, sequence=sequence):
                    if self._players[player].is_active:
                        self._draw(player, sequence)
                case _Resolve(sequence=sequence) as effect:
                    if sequence is None or not self._players[sequence.player].is_busted:
                        self._resolve(effect)
                    else:
                        self._discard_action(effect.player, effect.card)
                case _FinishFlip(sequence=sequence):
                    self._discard_action(sequence.player, sequence.card)
                    if not self._players[sequence.player].is_busted:
                        self._tasks.extendleft(reversed(sequence.deferred))
                    else:
                        for effect in sequence.deferred:
                            self._discard_action(effect.player, effect.card)
                case _FindTurn(start=start):
                    self._find_turn(start)
                case _EndRound(flip_seven_player=flip_seven_player):
                    self._end_round(flip_seven_player)

    def _find_turn(self, start: int) -> None:
        for offset in range(len(self._players)):
            candidate = (start + offset) % len(self._players)
            if self._players[candidate].is_active:
                self._pending = _HitOrStay(candidate)
                return

    def _draw(self, player_index: int, sequence: _FlipSequence | None) -> None:
        card, reshuffled = self._deck.draw()
        if reshuffled:
            self._events.append(DiscardShuffled(self._round_number))
        event = CardDrawn(self._round_number, player_index, card)
        self._events.append(event)
        self._recent_draws.append(event)
        match card.kind:
            case CardType.NUMBER:
                self._receive_number(player_index, card)
            case CardType.SECOND_CHANCE:
                self._receive_second_chance(player_index, card)
            case CardType.FREEZE | CardType.FLIP_THREE:
                self._players[player_index].cards.append(card)
                effect = _Resolve(player_index, card, sequence)
                if sequence is None:
                    self._tasks.appendleft(effect)
                else:
                    sequence.deferred.append(effect)
            case CardType.ADD | CardType.MULTIPLY:
                self._players[player_index].cards.append(card)

    def _receive_number(self, player_index: int, card: Card) -> None:
        player = self._players[player_index]
        if card not in player.cards:
            player.cards.append(card)
            if player.number_count() == 7:
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
            index for index, other in enumerate(self._players)
            if index != player_index and other.is_active and card not in other.cards
        )
        if targets:
            player.cards.append(card)
            self._pending = _TargetDecision(player_index, card, targets)
        else:
            self._deck.discard((card,))

    def _resolve(self, effect: _Resolve) -> None:
        # The loop in _advance ends the round before this runs if nobody is active.
        targets = tuple(
            index for index, player in enumerate(self._players) if player.is_active
        )
        self._pending = _TargetDecision(effect.player, effect.card, targets)

    def _apply_target(self, decision: _TargetDecision, target: int) -> None:
        self._players[decision.player].cards.remove(decision.card)
        recipient = self._players[target]
        if decision.card.kind is CardType.FREEZE:
            recipient.status = PlayerStatus.STAYED
            self._deck.discard((decision.card,))
        elif decision.card.kind is CardType.FLIP_THREE:
            recipient.cards.append(decision.card)
            sequence = _FlipSequence(target, decision.card)
            self._tasks.appendleft(_FinishFlip(sequence))
            for _ in range(3):
                self._tasks.appendleft(_Draw(target, sequence))
        else:
            recipient.cards.append(decision.card)

    def _discard_action(self, player: int, card: Card) -> None:
        self._players[player].cards.remove(card)
        self._deck.discard((card,))

    def _end_round(self, flip_seven_player: int | None) -> None:
        for index, player in enumerate(self._players):
            for card in player.cards[:]:
                if card.kind in (CardType.FREEZE, CardType.FLIP_THREE):
                    self._discard_action(index, card)
        scores = tuple(
            player.round_score(self._rules.score_cards)
            + (self._rules.flip_seven_bonus if index == flip_seven_player else 0)
            for index, player in enumerate(self._players)
        )
        for player, score in zip(self._players, scores):
            player.total_score += score
        totals = tuple(player.total_score for player in self._players)
        self._last_round = RoundResult(self._round_number, scores, totals, flip_seven_player)
        self._events.append(RoundEnded(self._round_number, self._last_round))
        high_score = max(totals)
        if high_score >= self._rules.target_score:
            self._winners = tuple(i for i, total in enumerate(totals) if total == high_score)
            self._tasks.clear()
            self._pending = None
        else:
            for player in self._players:
                self._deck.discard(player.cards)
            self._dealer = (self._dealer + 1) % len(self._players)
            self._start_round()
