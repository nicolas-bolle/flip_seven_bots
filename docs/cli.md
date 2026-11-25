# Commands

All tools run through one command, `flip7`. Run it with `uv run`; add `--help`
to any command for its full options.

| Command | Purpose |
| --- | --- |
| `flip7 play` | Play a game in a window |
| `flip7 tournament` | Open tournament setup, or pass options to run a tournament in terminal |
| `flip7 compare A B` | Rate two bots against each other |
| `flip7 bots` | List available bots and their required parameter names |
| `flip7 trace` | Print one bot's decisions during a game |
| `flip7 replay REPORT` | Rebuild a game from a bug report |

Bots are given as specs such as `random`, `threshold:25` or
`rival=threshold:25`. All parameters of a configurable bot must be supplied;
see [Included bots](reference.md#included-bots).

## Play

```shell
uv run flip7 play                                  # setup window
uv run flip7 play --human Ann --bot rival=threshold:25 --seed 7
uv run flip7 play --vengeance --human Ann --bot random
```

## Tournament and compare

```shell
uv run flip7 tournament                            # setup window
uv run flip7 tournament --bot random --bot careful=threshold:25 \
    --games 200 --seed 7 --jobs 2 --output results --plots
uv run flip7 compare random threshold:25 --games 200 --seed 7
```

- `compare A B` is shorthand for `tournament --bot A --bot B` and accepts the
  same options, including `--gui`.
- `--jobs N` sets the number of parallel game workers, in the terminal and the
  window. The default, `-1`, uses all available CPUs; use `1` for sequential
  execution. The tournament setup window also has a Workers field.
- `--output DIR` saves `games.csv`, `summary.csv`, and `settings.json` (bot
  specs, seed, settings, and source revision). Existing files are overwritten.
- `--plots` also saves HTML plots, and requires `--output`. `--quiet` hides the
  terminal progress bar.
- Supply `--seed` if the run must be repeatable.

## Windows and setup screens

`flip7 play` and `flip7 tournament` open a setup screen when given no options.
Passing options to `play` starts a game in the window. Passing options to
`tournament` runs in the terminal unless you add `--gui`.
For `play` or `tournament --gui`, `--setup` opens setup prefilled with the
options, and `--no-setup` skips it.

`--vengeance` and `--brutal` choose the game mode for `play`, `tournament`,
`compare`, and `trace`. In the game
window, `--seed` controls the decks but not the bots' randomness; press F1 to
save a bug report with replay data.

## Inspect and debug

```shell
uv run flip7 bots
uv run flip7 trace --bot threshold:25 --bot random --seat 0 --seed 7 --step
uv run flip7 replay bug_reports/report.md --moves 10
```

- `trace` prints the decisions and actions of the bot at `--seat`. With
  `--step`, it waits for Enter after each decision.
- `replay` rebuilds the reported game, optionally only its first `--moves`, and
  prints the round, scores, and current player.

See the [reference](reference.md#playing-games) for window controls, every
option, and the Python equivalents.
