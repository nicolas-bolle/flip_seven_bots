"""Bot interface, reusable decision functions, and example strategies."""

from . import policies, rollouts
from .base import Bot
from .simple import RandomBot, ThresholdBot

__all__ = [
    "Bot",
    "RandomBot",
    "ThresholdBot",
    "policies",
    "rollouts",
]
