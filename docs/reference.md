# Flip 7 reference

The complete description of the game rules, windows, options, and Python APIs.
For setup and step-by-step guides, start with the [README](../README.md).

- [Interfaces at a glance](#interfaces-at-a-glance)
- [Project layout](#project-layout)
- [Game modes](#game-modes) and [included bots](#included-bots)
- [Playing games](#playing-games): windows, options, Python, and bug reports
- [Writing bots](#writing-bots): decisions, observations, and lookahead
- [Running tournaments](#running-tournaments) and
  [how ratings work](#how-ratings-work)

## Interfaces at a glance

| Task | Window (Pygame) | Terminal | Python |
| --- | --- | --- | --- |
| Play a game | `flip7 play` | `flip7 trace` (prints a game between bots) | `simulation.play_game`, `game.Game` |
| Run a tournament | `flip7 tournament` | `flip7 tournament --games N`, `flip7 compare` | `tournament.run_tournament`, `play_tournament` |
| Rebuild a reported game | | `flip7 replay` | `game.replay.replay` |

Options given to `flip7 play` configure the window; human players always play
in the window. Run every command with `uv run`; each accepts `--help`. The
[commands guide](cli.md) summarizes them all.

## Project layout

| Package | Contents |
| --- | --- |
| `flip_seven_bots.game` | Headless rules engine: `Game`, `Rules`, `VengeanceRules`, cards, decisions, and observations; `game.replay` rebuilds reported games |
| `flip_seven_bots.bots` | The `Bot` interface, the included bots, reusable `policies` and `rollouts`, and the bot `registry` |
| `flip_seven_bots.simulation` | `play_game` and `run` for playing bots against each other |
| `flip_seven_bots.tournament` | Tournaments, ratings, saved results, and tournament option parsing |
| `flip_seven_bots.gui` | Pygame windows: `play`, `tournament`, and shared components in `common` |
| `flip_seven_bots.cli` | The `flip7` command |

## Game modes

Three rule sets are supported, and every interface can select them:

| Mode | Window | Command line | Python |
| --- | --- | --- | --- |
| Flip 7 (base game) | Default | Default | `rules=None` (default) |
| With a Vengeance | Setup screen toggle | `--vengeance` | `rules=VengeanceRules()` |
| With a Vengeance, Brutal Mode | Setup screen toggle | `--brutal` | `rules=VengeanceRules(brutal=True)` |

Rules notes:

- Player IDs are zero-based seat indices. The dealer defaults to player 0, and
  the player to their left is dealt first.
- During the initial deal, a player frozen (or, in With a Vengeance, forced to
  stay by Just One More) before their turn to be dealt gets no deal card; they
  are already out of the round. A player hit with Flip Three or Flip Four
  before their turn is still active, so they are dealt a card as well. The
  rulebook allows for this, noting that after the deal some players may have
  no cards and others three or four.
- Ties for the highest final score produce multiple winners. One- and
  two-player games use the same rules and goal.
- A game seats at most 10 players, so the deck can never run out. The draw
  pile runs out only if every card is in front of a player, and each player
  holds at most seven number cards. With 12 or more players, the table could
  hold every number card and leave nothing to draw. The rulebooks allow up to
  18 players with one deck.
- Staying requires at least one card in your hand, in both games. The base
  rulebook says so; the With a Vengeance rulebook doesn't repeat it, but its
  definition of staying (turning your leftmost card sideways) assumes it.
- In With a Vengeance, the Zero affects the round score, not accumulated
  points. A duplicate number received through a swap or steal causes a bust.
  A modifier drawn during a Flip Four that nobody has received when a Flip 7
  ends the round is discarded and affects no score.
- In With a Vengeance, an Unlucky 7 doesn't discard a modifier that was
  revealed earlier in the same Flip Four and is still waiting to be played.
  You play that modifier on any player afterwards, as usual. The Unlucky 7
  discards only the number and modifier cards "in front of you", which we
  read as your hand.
- A busted player's cards are face down and out of play, so Swap, Steal, and
  Discard cannot choose them. Stayed players' cards can still be chosen.
- In Brutal Mode, a player who gets Flip 7 can take the bonus or subtract it
  from another player. A busted player scores only their modifiers, so
  modifiers can make their round score negative, whether received before or
  after the bust. A player holding the Zero who hasn't busted still scores
  zero, even with negative modifiers.

## Included bots

| Bot | Spec (command line and setup screens) | Strategy |
| --- | --- | --- |
| `RandomBot` | `random` | Picks a random legal action |
| `ThresholdBot` | `threshold:SCORE` | Hits until its round score reaches the threshold |
| `ExpectedValueBot` | `expected` | Hits only if one more card is expected to raise its round score |

All of them support every decision in every game mode.

## Playing games

### In a window

```shell
uv run flip7 play
```

The setup screen starts with a player named Human, a bot that stays at 30 points, and
an expected value bot. Choose the game mode, edit player names and types, add
or remove seats (up to six), then press Start. Click a name or value to edit
it; Ctrl+A clears the field.

During play:

- Use the buttons or their keyboard shortcuts to hit, stay, or choose a player
  when an action card needs a target.
- For Swap, Steal, and Discard, click a highlighted card. Swap needs two cards
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

By default, giving options to the same command skips the setup screen and
starts the game immediately. Use `--setup` to configure the supplied settings
in the window, or `--no-setup` to skip setup explicitly:

```shell
uv run flip7 play --human Ann --human Ben --bot threshold:25
uv run flip7 play --vengeance --human Ann --bot random
uv run flip7 play --brutal --seed 7
```

| Option | Effect |
| --- | --- |
| `--human NAME` | Add a human player |
| `--bot KIND` | Add a bot (see [Included bots](#included-bots)) |
| `--vengeance`, `--brutal` | Choose the game mode |
| `--seed N` | Make the decks repeatable (bots keep their own randomness) |
| `--bug-dir PATH` | Folder for bug and crash reports (default `bug_reports`) |
| `--setup`, `--no-setup` | Show or skip the setup screen explicitly |

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
- `Rules(...)` changes the target score, the Flip 7 bonus, the deck, or the
  scoring.
- `Game(..., deck=Deck.stacked(cards))` deals cards in a fixed order, which is
  useful in tests.

A game raises an error if it exceeds 100,000 decisions (for example, with
custom rules that make the target score unreachable), or if a custom deck runs
out with no discarded cards to reshuffle.

### Bug reports

In the game window, press **Report bug** (or F1) to pause and describe a
problem. Enter saves the message with the game's full state, including the
hidden deck, to a timestamped Markdown file in `bug_reports/` (change it with
`--bug-dir`). If the game crashes, a report with the error is written there
automatically.

Each report ends with replay data, so the game can be rebuilt in a test:

```python
from flip_seven_bots.game.replay import replay

game = replay('bug_reports/2026-11-21_16-30-05.md')
```

## Writing bots

### The bot interface

A bot provides `choose_action(observation)` and returns one of
`observation.legal_actions`. `observation.decision` says what is being decided:

| Decision | When | Actions |
| --- | --- | --- |
| `HitOrStay` | On a player's turn | `hit()`, `stay()` |
| `ChooseTarget` | An action card needs a target; has the `card` and eligible `targets` | `choose(target)` |
| `ChooseCard` | With a Vengeance: Swap, Steal, or Discard picks a card | `choose(owner, card_index)` |
| `FlipSevenBonus` | Brutal Mode: a player got Flip 7; has eligible `targets` | `take()`, `penalize(target)` |

Every decision also has an `actions` tuple. The decision is public, so every
seat can see it, but only the deciding player receives legal actions.

For `ChooseCard`, `card_index` indexes the owner's `cards` in the current
observation. Swap uses two such decisions; during the second,
`decision.first` is the card already picked.

### Observations

Observations contain immutable snapshots of the public cards, scores, and
discard pile, but not the shuffled deck.

- Cards still held after a player stays or busts remain visible, because they
  were revealed earlier in the round.
- Action and modifier cards a player has drawn but not yet resolved are in
  that player's `unresolved`, not `cards`, and do not affect any score.
- A player's `round_score` is the in-progress score, without any Flip 7 bonus.
- `last_round` has the most recently completed round's scores, including any
  Flip 7 bonus.
- `events` has the current round's public draws, decisions, and discard
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
seats a number of bots (default: all of them, up to the 10-player limit in
[Rules notes](#game-modes)), chosen and ordered at random.

### From the command line

```shell
uv run flip7 tournament --bot random --bot careful=threshold:40 \
    --bot expected --games 200 --players-per-game 3 --seed 1 --output results
```

This shows a progress bar, prints the summary with each rating's 95% interval,
and, with `--output`, saves `games.csv`, `summary.csv`, and `settings.json`.

| Option | Effect |
| --- | --- |
| `--bot [NAME=]KIND` | Add a bot (see [Included bots](#included-bots)); duplicate names are numbered. Default lineup: `random`, `threshold:30`, `expected` |
| `--games N` | Number of games (default 100) |
| `--players-per-game N` | Bots seated in each game (default: all, up to 10) |
| `--seed N` | Seed for seating, decks, and bots |
| `--jobs N` | Parallel game workers (default 1) |
| `--gui` | Use the tournament window even when options are given |
| `--setup`, `--no-setup` | Show or skip setup explicitly (with `--gui`) |
| `--vengeance`, `--brutal` | Choose the game mode |
| `--output DIR` | Save results and settings in this folder |
| `--quiet`, `--plots` | Hide progress or save HTML plots (`--plots` requires `--output`) |
| `--k-factor K`, `--k-half-life N`, `--constant-k`, `--initial-rating R` | Elo settings (see [How ratings work](#how-ratings-work)) |

### In a window

```shell
uv run flip7 tournament
```

The setup screen lets you choose the game mode, number of games, players per
game, seed, and up to ten bots. Tournament options run in the terminal unless
you add `--gui`. To prefill setup instead of starting immediately, use
`--gui --setup` with your options.

While it runs, the window shows a progress bar, live standings by Elo, and an
Elo chart. **Stop** schedules no more games and waits for those in progress.
The final standings rank bots by `rating` with its 95% interval. Afterwards:

- With `--output DIR`, results are saved there automatically. Otherwise,
  **Save results** writes them to a timestamped folder in
  `tournament_results/`.
- **New tournament** returns to setup.

### From Python

```python
from flip_seven_bots.bots import ExpectedValueBot, RandomBot, ThresholdBot
from flip_seven_bots.tournament import run_tournament

result = run_tournament(
    {'random': RandomBot(1), 't25': ThresholdBot(25), 'ev': ExpectedValueBot()},
    games=100,
    seed=0,
)
print(result.summary)  # games, wins, win_rate, mean_place, mean_score,
# rating, rating_low, rating_high, elo
result.games  # per game and player: seat, score, place, won, Elo

result.plot_ratings().show()  # each rating with its confidence interval
result.plot_elo().show()  # Elo history, with final ratings and intervals
```

The plot methods return Plotly figures, which display directly in a notebook.
In the Elo chart, each bot's final rating is a dotted line inside a shaded band
for its interval; click a bot in the legend to hide or show all three.

`run_tournament` takes the same settings as the command line:
`players_per_game`, `rules`, `seed`, `jobs`, `k_factor`, `k_half_life`, and
`initial_rating`, plus `confidence` (default 0.95) for the rating intervals. A
progress bar shows the current leader; pass `progress=False` to hide it.

The tournament creates a fresh bot for every game, seeded from the tournament
seed. Pass registered bots as instances, which serve only as configurations,
and other bots as factories taking a seed (see
[Write and test a bot](writing-bots.md#experiment-from-python)).

`play_tournament` takes the same settings but returns an iterator yielding a
`GameRecord` in game order, for showing progress or stopping early. Multiple
games may be in flight when `jobs > 1`; close the iterator if stopping early.
`TournamentResult.from_records` builds the result tables from the records.

### How ratings work

Every game is scored as all of its pairwise matches: the better place wins and
tied scores draw. Two ratings are computed from these, on the same Elo scale:

- **`rating`** (the summary's ranking) is a Bradley-Terry fit to all games at
  once: the model Elo assumes, fitted by maximum likelihood with Newton's
  method. It doesn't depend on game order and becomes more precise as games
  are added, which suits bots that never change. The bots that played average
  `initial_rating`, and each pair gets one virtual drawn game so ratings stay
  finite. `rating_low` and `rating_high` bound a confidence interval from a
  cluster-robust (sandwich) standard error. It treats each game as one
  independent unit, so the related pairwise results within a game aren't
  counted as separate evidence. Intervals are empty with fewer than two games.
  Treat bots whose intervals overlap as indistinguishable.
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
