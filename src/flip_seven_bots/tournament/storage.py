"""Persist tournament results and reproducibility information."""

import json
from pathlib import Path

from flip_seven_bots.bots.specs import bot_spec
from flip_seven_bots.provenance import git_commit

from .config import TournamentOptions
from .core import TournamentResult


def save_results(
    result: TournamentResult, directory: Path, options: TournamentOptions | None = None
) -> tuple[Path, Path]:
    """Write result CSVs and, when provided, settings and optional plots."""
    metadata = None
    if options is not None:
        specs = {name: bot_spec(bot) for name, bot in options.bots.items()}
        metadata = {
            'bots': specs,
            'games_requested': options.games,
            'games_played': int(result.games['game'].nunique()),
            'players_per_game': options.players_per_game,
            'seed': options.seed,
            'vengeance': options.vengeance,
            'brutal': options.brutal,
            'k_factor': options.k_factor,
            'k_half_life': options.k_half_life,
            'initial_rating': options.initial_rating,
            'jobs': options.jobs,
            'git_commit': git_commit(),
        }
    directory.mkdir(parents=True, exist_ok=True)
    games, summary = directory / 'games.csv', directory / 'summary.csv'
    result.games.to_csv(games, index=False)
    result.summary.to_csv(summary)
    if metadata is not None and options is not None:
        (directory / 'settings.json').write_text(
            json.dumps(metadata, indent=2) + '\n', encoding='utf-8'
        )
        if options.plots:
            result.plot_ratings().write_html(directory / 'ratings.html')
            result.plot_elo().write_html(directory / 'elo.html')
    return games, summary
