"""The interface implemented by a bot."""

from typing import Protocol

from flip_seven_bots.game import Action, Observation


class Bot(Protocol):
    """A strategy that chooses a legal decision from a player observation.

    ``observation.decision`` describes what is being decided. A typical bot
    matches on its type and delegates each case to a function from
    ``bots.policies`` or ``bots.rollouts``.
    """

    def choose_action(self, observation: Observation) -> Action:
        """Return one of ``observation.legal_actions`` for the observing player."""
        ...
