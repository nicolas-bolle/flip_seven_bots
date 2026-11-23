# Flip 7 bots

A headless implementation of Flip 7 and Flip 7: With A Vengeance, with bots,
game windows and tools for comparing strategies. This project is private and
unlicensed.

## Get started

Install [uv](https://docs.astral.sh/uv/), then run:

```shell
uv sync
uv run flip7 bots
uv run flip7 play
uv run flip7 tournament --games 200 --seed 1 --jobs 2
uv run flip7 tournament --gui
```

Use `uv run flip7 --help` for the commands, or `uv run flip7 tournament --help`
for tournament options.

## Guides

- [Write and test a bot](docs/writing-bots.md)
- [Command-line and window interfaces](docs/cli.md)
- [Tournaments and ratings](docs/tournaments-and-ratings.md)
- [Full reference, game rules and Python APIs](docs/reference.md)

The code is organized into `game/` (rules and observations), `bots/`
(strategies and registry), `simulation.py`, `tournament/`, and `ui/`.
Shared window components live in `ui/common/`. Replay is available without
the UI through `game.replay`.

## Development

```shell
uv run pytest
uv run ruff check
uv run ruff format --check
```

CI checks lint and tests with at least 80% branch coverage.
