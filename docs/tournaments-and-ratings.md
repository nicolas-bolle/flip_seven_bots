# Tournaments and ratings

A tournament plays many complete games between named bots and rates them.

## Run a tournament

```shell
uv run flip7 tournament --bot random --bot careful=threshold:25 \
    --games 500 --seed 7 --jobs 4 --output results
uv run flip7 compare expected threshold:30 --games 500 --seed 7
uv run flip7 tournament  # open the setup window
```

From Python, use `run_tournament`, or `play_tournament` to receive games as
they finish; see the [reference](reference.md#running-tournaments) for every
setting.

## Read the results

The summary has one row per bot, ranked by `rating`:

- `rating`, with its 95% interval: the main result. It considers all games at
  once, so game order doesn't matter. Treat bots whose intervals overlap as
  indistinguishable, and add games to narrow the intervals.
- `elo`: an online Elo updated after each game, useful for watching a run
  progress. It depends on game order, so prefer `rating` for conclusions.
- `wins`, `win_rate`, `mean_place`, and `mean_score`: raw results. Tied winners
  each count a win; in the ratings, tied places count as draws.

Ratings assume a bot's strength doesn't depend on its opponents or the table
size, so only compare ratings from tournaments with the same players per game.
See [How ratings work](reference.md#how-ratings-work) for the calculations.

## Reproducibility

Each game seats bots in a random order and builds a fresh bot for each seat
from the tournament seed. Bots keep state between the rounds of a game, but
not between games.

With `--seed`, a tournament repeats exactly: the seed controls seating, decks,
and every bot's seed. Changing `--jobs` doesn't change the results, because
games are rated in schedule order rather than finishing order. This requires
bots to draw all randomness from their seed; a bot that uses another random
source must seed it itself. Without a seed, the run can't be repeated, even
from saved settings.

`--output` saves `settings.json` with the bot specs, seed, settings, and source
revision, so a saved run records how to reproduce it.

## Parallel runs

`--jobs N` (or `jobs=N` in Python) plays games in `N` worker processes. The
default, `-1`, uses all available CPUs, up to the number of games; `1` runs
games sequentially in the current process. Parallel runs require picklable bot
factories and rules. At most one game per worker is in flight. Errors in a
worker stop the tournament and are reported rather than retried. Stopping the
window waits for games in progress, and the results include only the games
finished before stopping.
