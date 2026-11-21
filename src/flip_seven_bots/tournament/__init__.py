"""Rate bots against each other: a Python API and ``python -m flip_seven_bots.tournament``."""

from .core import (
    GameRecord,
    TournamentResult,
    elo_update,
    play_tournament,
    run_tournament,
)

__all__ = ["GameRecord", "TournamentResult", "elo_update", "play_tournament", "run_tournament"]
