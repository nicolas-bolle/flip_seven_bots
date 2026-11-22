"""Rate bots against each other: a Python API and ``python -m flip_seven_bots.tournament``."""

from .core import GameRecord, TournamentResult, play_tournament, run_tournament
from .ratings import PairwiseResults, elo_update, fit_bradley_terry

__all__ = [
    "GameRecord",
    "PairwiseResults",
    "TournamentResult",
    "elo_update",
    "fit_bradley_terry",
    "play_tournament",
    "run_tournament",
]
