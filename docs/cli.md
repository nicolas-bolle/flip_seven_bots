# Interfaces

All commands below use `uv run`. `flip7 --help` lists commands.

```shell
uv run flip7 play                         # game setup window
uv run flip7 play --human Ann --bot rival=threshold:25 --seed 7
uv run flip7 tournament --gui             # tournament setup window
uv run flip7 tournament --bot random --bot careful=threshold:25 \
    --games 200 --seed 7 --jobs 2 --output results --plots
uv run flip7 compare random threshold:25 --games 200 --seed 7
uv run flip7 bots
uv run flip7 trace --bot threshold:25 --bot random --seat 0 --seed 7 --step
uv run flip7 replay bug_reports/report.md --moves 10
```

`--setup` explicitly opens a window's setup screen; `--no-setup` starts with
the supplied settings. Without either flag, no options opens setup, while
supplying options starts immediately. Use `--vengeance` or `--brutal` for
alternate game modes. The game-window seed controls decks, not bot randomness.

`trace` prints the selected seat's decisions and actions. With `--step`, it
waits for Enter after each decision.

Tournament `--jobs N` sets the number of game workers in the terminal and
window. The setup window also has a Workers field. `--quiet` hides the terminal
progress bar; `--plots` saves HTML plots and requires `--output`. Output includes
`games.csv`, `summary.csv`, and `settings.json`, including bot specifications,
seed, settings and source revision. Supply a seed if the run must be repeatable.
Output paths are overwritten if the files already exist.

In the game window F1 saves a report with replay data. See the
[reference](reference.md#playing-games) for controls and full Python examples.
