"""Bot interface and example strategies."""

from .base import Bot
from .monte_carlo import FlipThreeMonteCarloBot
from .simple import RandomBot, ThresholdBot

__all__ = ["Bot", "FlipThreeMonteCarloBot", "RandomBot", "ThresholdBot"]
