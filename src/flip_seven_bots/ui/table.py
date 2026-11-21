"""Screen-independent state for one human playing against bots."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from flip_seven_bots.bots import Bot
from flip_seven_bots.game import Action, Game, Observation, RoundResult

BOT_DELAY_MS = 700


@dataclass(frozen=True)
class Seat:
    name: str
    bot: Bot | None = None
    """The bot playing this seat, or ``None`` for the human player."""


class Table:
    """Run a game for one human seat, pacing bot moves and pausing between rounds.

    Times are in milliseconds from any monotonic clock; bots move once their
    delay has passed since the table first saw that it was their turn.
    """

    def __init__(
        self,
        seats: Sequence[Seat],
        *,
        new_game: Callable[[int], Game] = Game,
        bot_delay_ms: int = BOT_DELAY_MS,
    ):
        humans = [index for index, seat in enumerate(seats) if seat.bot is None]
        if len(humans) != 1:
            raise ValueError("exactly one seat must be played by a human")
        self.seats = tuple(seats)
        self.human = humans[0]
        self._new_game = new_game
        self._bot_delay_ms = bot_delay_ms
        self.restart()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(seat.name for seat in self.seats)

    @property
    def game(self) -> Game:
        return self._game

    @property
    def observation(self) -> Observation:
        return self._game.observe(self.human)

    @property
    def round_summary(self) -> RoundResult | None:
        """The just-completed round, shown until dismissed; play is paused meanwhile."""
        return self._round_summary

    @property
    def awaiting_human(self) -> bool:
        return self._round_summary is None and self._game.current_player == self.human

    def restart(self) -> None:
        self._game = self._new_game(len(self.seats))
        self._shown_round = 0
        self._round_summary: RoundResult | None = None
        self._bot_due: int | None = None
        self._check_round_summary()

    def choose(self, action: Action) -> None:
        if not self.awaiting_human:
            raise ValueError("it is not the human player's turn")
        self._apply(action)

    def dismiss_summary(self) -> None:
        self._round_summary = None

    def update(self, now: int) -> None:
        """Let the current bot move if its delay has passed."""
        player = self._game.current_player
        if self._round_summary is not None or player is None or player == self.human:
            return
        if self._bot_due is None:
            self._bot_due = now + self._bot_delay_ms
        if now < self._bot_due:
            return
        bot = self.seats[player].bot
        assert bot is not None  # only the human seat has no bot
        self._apply(bot.choose_action(self._game.observe(player)))

    def _apply(self, action: Action) -> None:
        self._game.apply(action)
        self._bot_due = None
        self._check_round_summary()

    def _check_round_summary(self) -> None:
        result = self._game.last_round
        if result is not None and result.round_number > self._shown_round:
            self._shown_round = result.round_number
            self._round_summary = result
