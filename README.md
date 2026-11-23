# Flip 7 bots

A Python implementation of Flip 7 and Flip 7: With A Vengeance for building and
comparing bots. It includes a headless rules engine, example bots, rated
tournaments, and Pygame windows for playing games and watching tournaments.

This is an unofficial fan project, not affiliated with or endorsed by The Op.
Flip 7 is a trademark of its owner; buy the game to play it with friends. The
code is released under the [MIT License](LICENSE), which covers this project's
code and docs only, not the Flip 7 game, name, or artwork.

## Get started

Install [uv](https://docs.astral.sh/uv/). `uv sync` installs Python 3.14 and
the dependencies:

```shell
uv sync
uv run flip7 bots                    # list the available bots
uv run flip7 play                    # play against bots in a window
uv run flip7 tournament --gui        # watch a tournament in a window
uv run flip7 tournament --games 200 --seed 1 --jobs 2   # rate bots in the terminal
```

Every command accepts `--help`, for example `uv run flip7 tournament --help`.

The same tools are available from Python:

```python
from flip_seven_bots.bots import ExpectedValueBot, ThresholdBot
from flip_seven_bots.simulation import play_game

result = play_game([ThresholdBot(30), ExpectedValueBot()], seed=123)
print(result.winners, [player.total_score for player in result.players])
```

## Guides

- [Write and test a bot](docs/writing-bots.md): create, register, compare, and
  debug your own bot.
- [Commands](docs/cli.md): every `flip7` command, in the terminal and in
  windows.
- [Tournaments and ratings](docs/tournaments-and-ratings.md): run reproducible
  tournaments and read the results.
- [Reference](docs/reference.md): game rules, window controls, options, and
  Python APIs. See its [project layout](docs/reference.md#project-layout) for a
  map of the code.

## Development

```shell
uv run pytest               # tests
uv run ruff check           # lint
uv run ruff format --check  # formatting
```

CI runs lint and the tests, and requires at least 80% branch coverage.
Training integrations are not yet implemented.
