"""Run bots against each other without a graphical interface."""

from collections.abc import Sequence

from .bots.base import Bot
from .game import Game
from .game.model import Observation


def play_game(
    bots: Sequence[Bot],
    *,
    seed: int | None = None,
    dealer: int = 0,
    max_decisions: int = 100_000,
) -> Observation:
    """Play one game and return the final public observation.

    The seed controls the deck; bots are responsible for their own randomness.
    """
    if max_decisions < 1:
        raise ValueError("max_decisions must be at least one")
    game = Game(len(bots), seed=seed, dealer=dealer)
    for _ in range(max_decisions):
        if game.is_finished:
            return game.observe(0)
        player = game.current_player
        if player is None:
            raise RuntimeError("game is unfinished but has no player decision")
        observation = game.observe(player)
        game.apply(bots[player].choose_action(observation))
    if game.is_finished:
        return game.observe(0)
    raise RuntimeError(f"game exceeded {max_decisions} decisions")
