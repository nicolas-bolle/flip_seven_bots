"""Screen-independent state for a game with human and bot players."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from random import Random

from flip_seven_bots.bots import Bot
from flip_seven_bots.game import Action, Game, Observation, RoundResult, Rules

MINIMUM_BOT_TIME_SECONDS = 1


def seeded_game(player_count: int, seed: int, *, rules: Rules | None = None) -> Game:
    return Game(player_count, seed=seed, rules=rules)


@dataclass(frozen=True)
class Move:
    player: int
    action: Action


@dataclass(frozen=True)
class Seat:
    name: str
    bot: Bot | None = None
    """The bot playing this seat, or ``None`` for the human player."""


class Table:
    """Run a shared-screen game for any mix of human and bot seats.

    Bot moves are paced and play pauses between rounds. Every card in Flip 7 is
    public, so humans take turns at one screen without hiding anything.

    Times are in milliseconds from any monotonic clock; bots move once their
    delay has passed since the table first saw that it was their turn.

    ``seed`` makes the sequence of game seeds, and so every deck, reproducible.
    ``new_game(player_count, game_seed)`` creates each game; only the default
    factory guarantees a game can be rebuilt from its seed and moves.
    """

    def __init__(
        self,
        seats: Sequence[Seat],
        *,
        seed: int | None = None,
        new_game: Callable[[int, int], Game] = seeded_game,
        bot_delay_ms: int = MINIMUM_BOT_TIME_SECONDS * 1000,
        rules: Rules | None = None,
    ):
        if not seats:
            raise ValueError("a table needs at least one seat")
        if rules is not None and new_game is not seeded_game:
            raise ValueError("pass rules to the custom game factory instead")
        self.seats = tuple(seats)
        self.humans = tuple(
            index for index, seat in enumerate(seats) if seat.bot is None
        )
        self.seed = seed
        self.replayable = new_game is seeded_game
        self._random = Random(seed)
        self._new_game = new_game
        self._rules = rules
        self._bot_delay_ms = bot_delay_ms
        self._paused = False
        self.restart()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(seat.name for seat in self.seats)

    @property
    def game(self) -> Game:
        return self._game

    @property
    def observation(self) -> Observation:
        """The public view, including legal actions when a human is to act."""
        return self._game.observe(self._game.current_player or 0)

    @property
    def round_summary(self) -> RoundResult | None:
        """The just-completed round, shown until dismissed; play is paused meanwhile."""
        return self._round_summary

    @property
    def game_seed(self) -> int:
        """The seed the current game was created with."""
        return self._game_seed

    @property
    def starting_dealer(self) -> int:
        return self._starting_dealer

    @property
    def moves(self) -> tuple[Move, ...]:
        """Every decision made in the current game, in order."""
        return tuple(self._moves)

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def human_to_act(self) -> int | None:
        """The human seat whose decision play is waiting for, if any."""
        player = self._game.current_player
        if (
            self._round_summary is None
            and not self._paused
            and player is not None
            and player in self.humans
        ):
            return player
        return None

    def pause(self) -> None:
        """Stop all play, e.g. while a dialog is open."""
        self._paused = True

    def resume(self) -> None:
        self._paused = False
        self._bot_due = None

    def restart(self) -> None:
        self._game_seed = self._random.getrandbits(64)
        if self._new_game is seeded_game:
            self._game = seeded_game(len(self.seats), self._game_seed, rules=self._rules)
        else:
            self._game = self._new_game(len(self.seats), self._game_seed)
        self._starting_dealer = self._game.observe(0).dealer
        self._moves: list[Move] = []
        self._shown_round = 0
        self._round_summary: RoundResult | None = None
        self._bot_due: int | None = None
        self._check_round_summary()

    def choose(self, action: Action) -> None:
        if self.human_to_act is None:
            raise ValueError("it is not a human player's turn")
        self._apply(action)

    def dismiss_summary(self) -> None:
        self._round_summary = None

    def update(self, now: int) -> None:
        """Let the current bot move if its delay has passed."""
        player = self._game.current_player
        if (
            self._round_summary is not None
            or self._paused
            or player is None
            or player in self.humans
        ):
            return
        if self._bot_due is None:
            self._bot_due = now + self._bot_delay_ms
        if now < self._bot_due:
            return
        bot = self.seats[player].bot
        assert bot is not None  # only human seats have no bot
        self._apply(bot.choose_action(self._game.observe(player)))

    def _apply(self, action: Action) -> None:
        player = self._game.current_player
        assert player is not None  # callers only apply actions on someone's turn
        # Recorded first so a report written after a crash includes the failing move.
        self._moves.append(Move(player, action))
        self._game.apply(action)
        self._bot_due = None
        self._check_round_summary()

    def _check_round_summary(self) -> None:
        result = self._game.last_round
        if result is not None and result.round_number > self._shown_round:
            self._shown_round = result.round_number
            self._round_summary = result
