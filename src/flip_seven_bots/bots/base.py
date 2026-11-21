"""The interface implemented by a bot."""

from typing import Protocol

from flip_seven_bots.game import Action, Observation


class Bot(Protocol):
    def choose_action(self, observation: Observation) -> Action:
        """Return one of the observation's legal actions."""
        ...
