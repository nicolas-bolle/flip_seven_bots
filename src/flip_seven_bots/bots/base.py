"""The interface implemented by a bot."""

from typing import Protocol

from flip_seven_bots.game import Action, Observation


class Bot(Protocol):
    """A strategy that chooses a legal decision from a player observation."""

    def choose_action(self, observation: Observation) -> Action:
        """Return one of ``observation.legal_actions`` for the observing player."""
        ...
