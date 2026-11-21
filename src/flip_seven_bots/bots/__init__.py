"""Bot interface, reusable decision functions, and example strategies."""

from . import policies, rollouts
from .base import Bot
from .monte_carlo import FlipThreeMonteCarloBot
from .simple import RandomBot, ThresholdBot

__all__ = [
    "Bot",
    "FlipThreeMonteCarloBot",
    "RandomBot",
    "ThresholdBot",
    "policies",
    "rollouts",
]
