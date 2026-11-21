"""A turn-based, headless implementation of the base game."""

from collections import deque
from dataclasses import dataclass, field
from random import Random

from .model import (
    Action,
    ActionType,
    Card,
    CardType,
    EventType,
    GameEvent,
    Observation,
    PlayerStatus,
    PlayerView,
    RoundResult,
)
from .rules import FLIP_SEVEN_BONUS, TARGET_SCORE, build_deck, score_cards


@dataclass
class _Player:
    total_score: int = 0
    status: PlayerStatus = PlayerStatus.ACTIVE
    cards: list[Card] = field(default_factory=list)


@dataclass
class _FlipSequence:
    player: int
    deferred: list["_Resolve"] = field(default_factory=list)


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


_Task = _Draw | _Resolve | _FinishFlip | _FindTurn


@dataclass(frozen=True)
class _TargetDecision:
    player: int
    card: Card
    targets: tuple[int, ...]


class Game:
    """Run a base-game match; player IDs are zero-based seat indices.

    The engine advances automatically until a player must make a decision.
    ``observe`` exposes public information, never the shuffled deck.
    """

    def __init__(self, player_count: int, *, seed: int | None = None, dealer: int = 0):
        if player_count < 1:
            raise ValueError("player_count must be at least one")
        if not 0 <= dealer < player_count:
            raise ValueError("dealer must be a valid player index")

        self._random = Random(seed)
        self._players = [_Player() for _ in range(player_count)]
        self._deck = build_deck()
        self._random.shuffle(self._deck)
        self._discard: list[Card] = []
        self._dealer = dealer
        self._round_number = 0
        self._last_round: RoundResult | None = None
        self._winners: tuple[int, ...] = ()
        self._tasks: deque[_Task] = deque()
        self._current_player: int | None = None
        self._target_decision: _TargetDecision | None = None
        self._events: list[GameEvent] = []
        self._start_round()
        self._advance()

    @property
    def current_player(self) -> int | None:
        return self._current_player

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
                round_score=(
                    self._last_round.scores[index]
                    if self.is_finished and self._last_round is not None
                    else 0 if state.status is PlayerStatus.BUSTED
                    else score_cards(state.cards)
                ),
            )
            for index, state in enumerate(self._players)
        )
        return Observation(
            player=player,
            current_player=self._current_player,
            round_number=self._round_number,
            dealer=self._dealer,
            players=views,
            cards_remaining=len(self._deck),
            discard_count=len(self._discard),
            legal_actions=self._legal_actions() if player == self._current_player else (),
            pending_card=self._target_decision.card if self._target_decision else None,
            last_round=self._last_round,
            winners=self._winners,
            events=tuple(self._events),
        )

    def apply(self, action: Action) -> None:
        """Apply one legal decision and advance to the next decision or game end."""
        if action not in self._legal_actions():
            raise ValueError(f"illegal action: {action!r}")
        player = self._current_player
        if player is None:
            raise RuntimeError("no player is awaiting a decision")
        self._events.append(
            GameEvent(EventType.ACTION_CHOSEN, self._round_number, player, action=action)
        )
        self._current_player = None

        if self._target_decision is not None:
            decision = self._target_decision
            self._target_decision = None
            if action.target is None:
                raise RuntimeError("target decision is missing a target")
            self._apply_target(decision, action.target)
        elif action.kind is ActionType.STAY:
            self._players[player].status = PlayerStatus.STAYED
            self._tasks.appendleft(_FindTurn((player + 1) % len(self._players)))
        else:
            self._tasks.appendleft(_FindTurn((player + 1) % len(self._players)))
            self._tasks.appendleft(_Draw(player))
        self._advance()

    def _legal_actions(self) -> tuple[Action, ...]:
        if self._current_player is None:
            return ()
        if self._target_decision is not None:
            return tuple(
                Action(ActionType.CHOOSE_TARGET, target)
                for target in self._target_decision.targets
            )
        player = self._players[self._current_player]
        actions = [Action(ActionType.HIT)]
        if player.cards:
            actions.append(Action(ActionType.STAY))
        return tuple(actions)

    def _start_round(self) -> None:
        self._round_number += 1
        for player in self._players:
            player.status = PlayerStatus.ACTIVE
            player.cards.clear()
        self._tasks.clear()
        self._target_decision = None
        self._current_player = None
        self._events.append(GameEvent(EventType.ROUND_STARTED, self._round_number))
        first = (self._dealer + 1) % len(self._players)
        for offset in range(len(self._players)):
            self._tasks.append(_Draw((first + offset) % len(self._players)))
        self._tasks.append(_FindTurn(first))

    def _advance(self) -> None:
        while self._current_player is None and not self.is_finished:
            if not any(p.status is PlayerStatus.ACTIVE for p in self._players):
                self._end_round()
                continue
            if not self._tasks:
                raise RuntimeError("game has no pending task or player decision")
            task = self._tasks.popleft()
            if isinstance(task, _Draw):
                if self._players[task.player].status is PlayerStatus.ACTIVE:
                    self._draw(task.player, task.sequence)
            elif isinstance(task, _Resolve):
                if (
                    task.sequence is None
                    or self._players[task.sequence.player].status is not PlayerStatus.BUSTED
                ):
                    self._resolve(task)
            elif isinstance(task, _FinishFlip):
                if self._players[task.sequence.player].status is not PlayerStatus.BUSTED:
                    self._tasks.extendleft(reversed(task.sequence.deferred))
            else:
                for offset in range(len(self._players)):
                    candidate = (task.start + offset) % len(self._players)
                    if self._players[candidate].status is PlayerStatus.ACTIVE:
                        self._current_player = candidate
                        break

    def _draw(self, player_index: int, sequence: _FlipSequence | None) -> None:
        if not self._deck:
            if not self._discard:
                raise RuntimeError("cannot draw: no cards are available to reshuffle")
            self._deck, self._discard = self._discard, []
            self._random.shuffle(self._deck)
            self._events.append(GameEvent(EventType.DISCARD_SHUFFLED, self._round_number))
        card = self._deck.pop()
        self._events.append(
            GameEvent(EventType.CARD_DRAWN, self._round_number, player_index, card=card)
        )
        player = self._players[player_index]

        if card.kind is CardType.NUMBER and card in player.cards:
            chance = Card(CardType.SECOND_CHANCE)
            if chance in player.cards:
                player.cards.remove(chance)
                self._discard.extend((chance, card))
            else:
                player.cards.append(card)
                player.status = PlayerStatus.BUSTED
            return

        player.cards.append(card)
        if card.kind is CardType.NUMBER:
            if sum(c.kind is CardType.NUMBER for c in player.cards) == 7:
                self._end_round(flip_seven_player=player_index)
        elif card.kind is CardType.SECOND_CHANCE:
            if player.cards.count(card) > 1:
                targets = tuple(
                    i for i, other in enumerate(self._players)
                    if i != player_index
                    and other.status is PlayerStatus.ACTIVE
                    and card not in other.cards
                )
                if targets:
                    self._target_decision = _TargetDecision(player_index, card, targets)
                    self._current_player = player_index
                else:
                    player.cards.remove(card)
                    self._discard.append(card)
        elif card.kind in (CardType.FREEZE, CardType.FLIP_THREE):
            effect = _Resolve(player_index, card, sequence)
            if sequence is None:
                self._tasks.appendleft(effect)
            else:
                sequence.deferred.append(effect)

    def _resolve(self, effect: _Resolve) -> None:
        targets = tuple(
            i for i, player in enumerate(self._players)
            if player.status is PlayerStatus.ACTIVE
        )
        if not targets:
            raise RuntimeError("action card has no active target")
        self._target_decision = _TargetDecision(effect.player, effect.card, targets)
        self._current_player = effect.player

    def _apply_target(self, decision: _TargetDecision, target: int) -> None:
        owner = self._players[decision.player]
        recipient = self._players[target]
        owner.cards.remove(decision.card)
        recipient.cards.append(decision.card)
        if decision.card.kind is CardType.FREEZE:
            recipient.status = PlayerStatus.STAYED
        elif decision.card.kind is CardType.FLIP_THREE:
            sequence = _FlipSequence(target)
            self._tasks.appendleft(_FinishFlip(sequence))
            for _ in range(3):
                self._tasks.appendleft(_Draw(target, sequence))

    def _end_round(self, flip_seven_player: int | None = None) -> None:
        scores = tuple(
            0 if player.status is PlayerStatus.BUSTED else (
                score_cards(player.cards)
                + (FLIP_SEVEN_BONUS if index == flip_seven_player else 0)
            )
            for index, player in enumerate(self._players)
        )
        for player, score in zip(self._players, scores):
            player.total_score += score
        totals = tuple(player.total_score for player in self._players)
        self._last_round = RoundResult(
            self._round_number, scores, totals, flip_seven_player
        )
        self._events.append(
            GameEvent(EventType.ROUND_ENDED, self._round_number, result=self._last_round)
        )
        if max(totals) >= TARGET_SCORE:
            high_score = max(totals)
            self._winners = tuple(i for i, total in enumerate(totals) if total == high_score)
            self._tasks.clear()
            self._current_player = None
            self._target_decision = None
        else:
            for player in self._players:
                self._discard.extend(player.cards)
            self._dealer = (self._dealer + 1) % len(self._players)
            self._start_round()
