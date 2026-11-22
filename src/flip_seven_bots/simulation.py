"""Run bots against each other without a graphical interface."""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from .game import Game, Observation, Rules

if TYPE_CHECKING:
    from .bots.base import Bot

# Far above any real game; guards against rules (e.g. a custom deck) that make
# the target score unreachable, which would otherwise loop forever.
_MAX_DECISIONS = 100_000


def run(
    game: Game,
    bots: Sequence[Bot],
    *,
    stop: Callable[[Game], bool] | None = None,
) -> None:
    """Advance an existing game with one bot per seat, in seat order.

    Stop when the game ends or ``stop(game)`` becomes true, checking the
    predicate before each decision. Raise ``RuntimeError`` if the game still
    needs a decision after 100,000 decisions.
    """
    decisions = 0
    while not game.is_finished and not (stop is not None and stop(game)):
        if decisions == _MAX_DECISIONS:
            raise RuntimeError(f"game exceeded {_MAX_DECISIONS} decisions")
        player = game.current_player
        assert player is not None  # an unfinished game always awaits a decision
        game.apply(bots[player].choose_action(game.observe(player)))
        decisions += 1


def play_game(
    bots: Sequence[Bot],
    *,
    seed: int | None = None,
    dealer: int = 0,
    rules: Rules | None = None,
) -> Observation:
    """Play one game and return the final public observation.

    The seed controls the deck; bots are responsible for their own randomness.
    ``dealer`` is a zero-based seat ID. The returned observation is from seat
    zero's perspective and contains the final scores and winners.
    """
    game = Game(len(bots), rules=rules, seed=seed, dealer=dealer)
    run(game, bots)
    return game.observe(0)
