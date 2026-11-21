"""Run bots against each other without a graphical interface."""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from .game import Game, Observation, Rules

if TYPE_CHECKING:
    from .bots.base import Bot


def run(
    game: Game,
    bots: Sequence[Bot],
    *,
    stop: Callable[[Game], bool] | None = None,
    max_decisions: int = 100_000,
) -> None:
    """Let ``bots`` (one per seat) make decisions until the game ends or ``stop`` is true."""
    if max_decisions < 1:
        raise ValueError("max_decisions must be at least one")
    decisions = 0
    while not game.is_finished and not (stop is not None and stop(game)):
        if decisions == max_decisions:
            raise RuntimeError(f"game exceeded {max_decisions} decisions")
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
    max_decisions: int = 100_000,
) -> Observation:
    """Play one game and return the final public observation.

    The seed controls the deck; bots are responsible for their own randomness.
    """
    game = Game(len(bots), rules=rules, seed=seed, dealer=dealer)
    run(game, bots, max_decisions=max_decisions)
    return game.observe(0)
