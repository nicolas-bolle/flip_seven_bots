"""Bot interface and example strategies."""

from .base import Bot
from .simple import RandomBot, ThresholdBot

__all__ = ["Bot", "RandomBot", "ThresholdBot"]
