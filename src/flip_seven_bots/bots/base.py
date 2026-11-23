"""The interface implemented by a bot."""

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from flip_seven_bots.game import Action, Observation


@runtime_checkable
class Bot(Protocol):
    """A strategy that chooses a legal decision from a player observation.

    ``observation.decision`` describes what is being decided. A typical bot
    matches on its type and delegates each case to a function from
    ``bots.policies`` or ``bots.rollouts``.
    """

    def choose_action(self, observation: Observation) -> Action:
        """Return one of ``observation.legal_actions`` for the observing player."""
        ...


BotFactory = Callable[[int | None], Bot]
"""Construct a fresh bot with the supplied per-game seed."""
