# Flip 7 bots

An implementation of the card games Flip 7 and Flip 7: With A Vengeance, with
bots to play them and tools to rate bots against each other. The project is
kept private and unlicensed to avoid any Flip 7 copyright issues.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/); `uv sync` installs Python 3.14 and
the dependencies.

```shell
uv sync

# Play against bots in a window
uv run python -m flip_seven_bots.ui

# Watch bots play a tournament in a window
uv run python -m flip_seven_bots.ui.tournament

# Run a tournament in the terminal and print the ratings
uv run python -m flip_seven_bots.tournament --games 200
```

Or from Python:

```python
from flip_seven_bots.bots import ExpectedValueBot, ThresholdBot
from flip_seven_bots.simulation import play_game

result = play_game([ThresholdBot(30), ExpectedValueBot()], seed=123)
print(result.winners, [player.total_score for player in result.players])
```

## Interfaces at a glance

| Task | Window (Pygame) | Command line | Python |
| --- | --- | --- | --- |
| Play a game | `python -m flip_seven_bots.ui` | Same command with options, which skip setup | `simulation.play_game`, `game.Game` |
| Run a tournament | `python -m flip_seven_bots.ui.tournament` | `python -m flip_seven_bots.tournament` | `tournament.run_tournament`, `play_tournament` |

Every command accepts `--help`. All commands are run with `uv run`.

## Project layout

| Package | Contents |
| --- | --- |
| `flip_seven_bots.game` | Headless rules engine: `Game`, `Rules`, `VengeanceRules`, cards, decisions and observations |
| `flip_seven_bots.bots` | The `Bot` interface, the included bots, and reusable `policies` and `rollouts` |
| `flip_seven_bots.simulation` | `play_game` and `run` for playing bots against each other |
| `flip_seven_bots.tournament` | Tournaments, ratings and the tournament command line |
| `flip_seven_bots.ui` | Pygame windows for playing games and watching tournaments |

## Game modes

Three rule sets are supported, and every interface can select them:

| Mode | Window | Command line | Python |
| --- | --- | --- | --- |
| Flip 7 (base game) | Default | Default | `rules=None` (default) |
| With A Vengeance | Setup screen toggle | `--vengeance` | `rules=VengeanceRules()` |
| With A Vengeance, Brutal Mode | Setup screen toggle | `--brutal` | `rules=VengeanceRules(brutal=True)` |

Rules notes:

- Player IDs are zero-based seat indices. The dealer defaults to player 0, and
  the player to their left is dealt first.
- Ties for the highest final score produce multiple winners. One- and
  two-player games use the same rules and goal.
- In With A Vengeance, the Zero affects the round score, not accumulated
  points. A duplicate number received through a swap or steal causes a bust.
- In Brutal Mode, a player who gets Flip 7 can take the bonus or subtract it
  from another player, and modifiers can give a busted player a negative round
  score.

## Included bots

| Bot | Spec (command line and setup screens) | Strategy |
| --- | --- | --- |
| `RandomBot` | `random` | Picks a random legal action |
| `ThresholdBot` | `threshold[:SCORE]` (default 30) | Hits until its round score reaches the threshold |
| `ExpectedValueBot` | `expected` | Hits only if one more card is expected to raise its round score |

All of them support every decision in every game mode.

## Playing games

### In a window

```shell
uv run python -m flip_seven_bots.ui
```

The setup screen starts with a human (Me), a bot that stays at 30 points, and
an expected value bot. Choose the game mode, edit player names and types, add
or remove seats (up to six), then press Start. Click a name or value to edit
it; Ctrl+A clears the field.

During play:

- Use the buttons or their keyboard shortcuts to hit, stay, or choose a player
  when an action card needs a target.
- For Swap, Steal and Discard, click a highlighted card. Swap needs two cards
  from different players.
- Press Escape or close the window to quit.

Every card is public, so several humans can share the screen and take turns,
and a table of only bots can be watched. Bot decisions take at least one second
each, and play waits for the dealing animations to finish.

Each hand shows number cards below modifiers and action cards, sorted by
value. A player's total score appears beside their live round score, which
excludes any Flip 7 bonus. The activity panel shows the current round's draws
and decisions, and a summary appears after each round.

### From the command line

Giving any options to the same command skips the setup screen and starts the
game immediately:

```shell
uv run python -m flip_seven_bots.ui --human Ann --human Ben --bot threshold:25
uv run python -m flip_seven_bots.ui --vengeance --human Ann --bot random
uv run python -m flip_seven_bots.ui --brutal --seed 7
```

| Option | Effect |
| --- | --- |
| `--human NAME` | Add a human player |
| `--bot KIND` | Add a bot (see [Included bots](#included-bots)) |
| `--vengeance`, `--brutal` | Choose the game mode |
| `--seed N` | Make the decks repeatable (bots keep their own randomness) |
| `--bug-dir PATH` | Folder for bug and crash reports (default `bug_reports`) |

Seats are filled in the order given, up to six players. With only a mode flag,
the default players are used.

### From Python

`play_game` plays one game between bots and returns the final observation, from
seat 0's perspective:

```python
from flip_seven_bots.bots import RandomBot, ThresholdBot
from flip_seven_bots.game import VengeanceRules
from flip_seven_bots.simulation import play_game

result = play_game(
    [ThresholdBot(30), RandomBot(seed=1), ThresholdBot(40)],
    seed=123,  # deck seed; independent of the bots' seeds
    rules=VengeanceRules(),  # omit for the base game
)
print(result.winners)
print([player.total_score for player in result.players])
```

For finer control, create a `Game` and advance it with
`simulation.run(game, bots, stop=...)`, which stops when the game ends or
`stop(game)` becomes true. Options:

- `Game(..., dealer=N)` chooses the dealer.
- `Rules(...)` changes the target score, the Flip 7 bonus, the deck or the
  scoring.
- `Game(..., deck=Deck.stacked(cards))` deals cards in a fixed order, which is
  useful in tests.

A game raises an error if it exceeds 100,000 decisions (for example, with
custom rules that make the target score unreachable), or if the deck runs out
with no discarded cards to reshuffle.

### Bug reports

In the game window, press **Report bug** (or F1) to pause and describe a
problem. Enter saves the message with the game's full state, including the
hidden deck, to a timestamped Markdown file in `bug_reports/` (change it with
`--bug-dir`). If the game crashes, a report with the error is written there
automatically.

Each report ends with replay data, so the game can be rebuilt in a test:

```python
from flip_seven_bots.ui.bug_report import replay

game = replay("bug_reports/2026-11-21_16-30-05.md")
```

## Writing bots

### The bot interface

A bot provides `choose_action(observation)` and returns one of
`observation.legal_actions`. `observation.decision` says what is being decided:

| Decision | When | Actions |
| --- | --- | --- |
| `HitOrStay` | On a player's turn | `hit()`, `stay()` |
| `ChooseTarget` | An action card needs a target; has the `card` and eligible `targets` | `choose(target)` |
| `ChooseCard` | With A Vengeance: Swap, Steal or Discard picks a card | `choose(owner, card_index)` |
| `FlipSevenBonus` | Brutal Mode: a player got Flip 7; has eligible `targets` | `take()`, `penalize(target)` |

Every decision also has an `actions` tuple. The decision is public, so every
seat can see it, but only the deciding player receives legal actions.

For `ChooseCard`, `card_index` indexes the owner's `cards` in the current
observation. Swap uses two such decisions; during the second,
`decision.first` is the card already picked.

### Observations

Observations contain immutable snapshots of the public cards, scores and
discard pile, but not the shuffled deck.

- Cards still held after a player stays or busts remain visible, because they
  were revealed earlier in the round.
- A player's `round_score` is the in-progress score, without any Flip 7 bonus.
- `last_round` has the most recently completed round's scores, including any
  Flip 7 bonus.
- `events` has the current round's public draws, decisions and discard
  reshuffles, plus the final round result once the game ends.

### Building a bot

The intended structure is to match on the decision and hand each case to a
reusable function from `bots.policies` (simple rules) or `bots.rollouts`
(simulation). These functions take any randomness as an explicit `rng`.

```python
from random import Random

from flip_seven_bots.bots import ThresholdBot, policies, rollouts
from flip_seven_bots.game import Card, CardType, ChooseTarget, HitOrStay


class MyBot:
    def __init__(self, seed=None):
        self.rng = Random(seed)

    def choose_action(self, observation):
        decision = policies.acting_decision(observation)
        match decision:
            case HitOrStay():
                return policies.stay_at_threshold(observation, decision, 25)
            case ChooseTarget(card=Card(kind=CardType.FLIP_THREE)):
                return rollouts.best_action(
                    observation, ThresholdBot(25), samples=50, rng=self.rng
                )
            case ChooseTarget():
                return policies.prefer_opponent(decision)
            case _:
                return policies.first_legal(observation)
```

### Looking ahead

The deck order is the only hidden information.

- `observation.draw_pile` lists the undrawn cards in a fixed sorted order.
- `observation.sample_game(rng)` returns an independent `Game` that matches the
  observation, with the remaining deck reshuffled by `rng`. Pass
  `next_draws=(card, ...)` to fix the next cards drawn. An observation can only
  be sampled until the real game advances.
- Bots can apply candidate actions to a sampled game and play it forward with
  `simulation.run(game, bots, stop=...)`.

`ExpectedValueBot` hits only when the expected round score after one more card,
averaged over `draw_pile` and scored by the engine, beats its current score
(`policies.expected_hit_score`). For any decision, `rollouts.best_action`
instead plays sampled games to the end of the round and picks the action with
the best average margin over the leading opponent; the example bot above uses
it for Flip Three targets.

## Running tournaments

A tournament plays many games between named bots and rates them. Each game
seats a number of bots (default: all of them), chosen and ordered at random.

### From the command line

```shell
uv run python -m flip_seven_bots.tournament --bot random --bot careful=threshold:40 \
    --bot expected --games 200 --players-per-game 3 --seed 1 --output results
```

This shows a progress bar, prints the summary with each rating's 95% interval,
and, with `--output`, saves `games.csv` and `summary.csv`.

| Option | Effect |
| --- | --- |
| `--bot [NAME=]KIND` | Add a bot (see [Included bots](#included-bots)); duplicate names are numbered. Default lineup: `random`, `threshold:30`, `expected` |
| `--games N` | Number of games (default 100) |
| `--players-per-game N` | Bots seated in each game (default: all) |
| `--rotate-seats` | Replay each deal once per seat rotation (see [Reducing card luck](#reducing-card-luck)) |
| `--seed N` | Seed for seating, decks and resampling |
| `--vengeance`, `--brutal` | Choose the game mode |
| `--output DIR` | Save `games.csv` and `summary.csv` in this folder |
| `--bootstrap N` | Resamples for the confidence interval; 0 skips it (default 200) |
| `--k-factor K`, `--k-half-life N`, `--constant-k`, `--initial-rating R` | Elo settings (see [How ratings work](#how-ratings-work)) |

### In a window

```shell
uv run python -m flip_seven_bots.ui.tournament
```

The setup screen lets you choose the game mode, number of games, players per
game, seed, seat rotation and up to eight bots. Giving any of the command-line
options above skips setup and starts immediately.

While it runs, the window shows a progress bar, live standings by Elo and an
Elo chart; Stop ends the tournament after the current game. The final
standings rank bots by `rating` with its 95% interval. Afterwards:

- **Save results** writes the CSV files to `--output` if given (which also
  saves them automatically), or otherwise to a timestamped folder in
  `tournament_results/`.
- **New tournament** returns to setup.

### From Python

```python
from flip_seven_bots.bots import ExpectedValueBot, RandomBot, ThresholdBot
from flip_seven_bots.tournament import run_tournament

result = run_tournament(
    {"random": RandomBot(1), "t25": ThresholdBot(25), "ev": ExpectedValueBot()},
    games=100,
    seed=0,
)
print(result.summary)  # games, wins, win_rate, mean_place, mean_score,
# rating, rating_low, rating_high, elo
result.games  # per game and player: deal, seat, score, place, won, Elo
```

`run_tournament` takes the same settings as the command line:
`players_per_game`, `rotate_seats`, `rules`, `seed`, `bootstrap`,
`confidence` (default 0.95), `k_factor`, `k_half_life` and `initial_rating`.
A progress bar shows the current leader; pass `progress=False` to hide it.
Each bot object keeps its state across games.

`play_tournament` takes the same settings but returns an iterator that plays
one game per step and yields a `GameRecord`, for showing progress or stopping
early. `TournamentResult.from_records` builds the result tables from the
records.

### How ratings work

Every game is scored as all of its pairwise matches: the better place wins and
tied scores draw. Two ratings are computed from these, on the same Elo scale:

- **`rating`** (the summary's ranking) is a Bradley-Terry fit to all games at
  once: the model Elo assumes, fitted by maximum likelihood. It doesn't depend
  on game order and becomes more precise as games are added, which suits bots
  that never change. The bots that played average `initial_rating`, and each
  pair gets one virtual drawn game so ratings stay finite. `rating_low` and
  `rating_high` bound a confidence interval from `bootstrap` refits on
  resampled games. Treat bots whose intervals overlap as indistinguishable.
- **`elo`** is an online Elo rating updated after every game, shown in
  `result.games` and the tournament window's chart. Each player's change is
  their K-factor divided by `n - 1`, times the sum of actual minus expected
  results, so two-player games use standard Elo. The K-factor starts at
  `k_factor` and shrinks to `k_factor * h / (h + games played)`, where `h` is
  `k_half_life` (default 50), so ratings settle instead of drifting. Use
  `k_half_life=None` (`--constant-k`) for a constant K.

Ratings assume a bot's strength doesn't depend on its opponents or the table
size, which may not hold in Flip 7. Only compare ratings between tournaments
that use the same number of players per game.

### Reducing card luck

Most of the noise in a game comes from the cards. With seat rotation
(`--rotate-seats` or `rotate_seats=True`), each deal is replayed with the same
deck once per seat rotation, so every seated bot gets the same cards from
every seat. The `deal` column groups these games, and the number of games must
be a multiple of the players per game.

## Development

```shell
uv run pytest      # tests
uv run ruff check  # lint
uv run ruff format # format
```

CI runs ruff and the tests, and requires at least 80% branch coverage.

Training integrations are not yet implemented.
