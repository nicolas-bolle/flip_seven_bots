"""Tournament settings shared by the terminal and window."""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from flip_seven_bots.game import Rules, VengeanceRules

from .core import (
    DEFAULT_JOBS,
    GameRecord,
    TournamentResult,
    max_table_size,
    play_tournament,
    run_tournament,
)

if TYPE_CHECKING:
    from flip_seven_bots.bots.base import Bot, BotFactory

DEFAULT_K_HALF_LIFE = 50.0


@dataclass(frozen=True)
class TournamentOptions:
    """Settings for a tournament."""

    bots: Mapping[str, Bot | BotFactory]
    games: int
    players_per_game: int | None
    seed: int | None
    vengeance: bool
    brutal: bool
    k_factor: float
    initial_rating: float
    output: Path | None
    k_half_life: float | None = DEFAULT_K_HALF_LIFE
    jobs: int = DEFAULT_JOBS
    quiet: bool = False
    plots: bool = False

    @property
    def rules(self) -> Rules | None:
        return VengeanceRules(brutal=self.brutal) if self.vengeance else None

    def start(self) -> Iterator[GameRecord]:
        """Validate and return an iterator that plays one game per step."""
        return play_tournament(self.bots, **self._settings())

    def run(self, *, progress: bool = True) -> TournamentResult:
        """Play the whole tournament, optionally showing a terminal progress bar."""
        return run_tournament(self.bots, **self._settings(), progress=progress)

    def result(self, records: Sequence[GameRecord]) -> TournamentResult:
        """Build the result tables for games played with ``start``."""
        return TournamentResult.from_records(
            records, list(self.bots), initial_rating=self.initial_rating
        )

    def describe(self) -> str:
        """A one-line description of the settings."""
        mode = 'Flip 7'
        if self.vengeance:
            mode = 'With a Vengeance (Brutal)' if self.brutal else 'With a Vengeance'
        table = self.players_per_game or max_table_size(len(self.bots))
        return f'{len(self.bots)} bots, {self.games} games of {table} players, {mode}'

    def _settings(self) -> dict:
        return {
            'games': self.games,
            'players_per_game': self.players_per_game,
            'rules': self.rules,
            'seed': self.seed,
            'k_factor': self.k_factor,
            'k_half_life': self.k_half_life,
            'initial_rating': self.initial_rating,
            'jobs': self.jobs,
        }
