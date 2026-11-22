Implementing the board games Flip 7 and Flip 7: With A Vengeance and making
bots for them. Keeping this project private without a license to dodge any
Flip 7 copyright issues.

## Play against bots

Run the Pygame interface with:

```shell
uv run python -m flip_seven_bots.ui
```

The Game setup screen defaults to the base game against a random bot and a bot
that stays at 30 points. Choose With A Vengeance and optionally Brutal Mode,
edit player names and types, add or remove seats, then press Start. Click a
name or value to edit it; Ctrl+A clears the field.

Use the buttons or their displayed keyboard shortcuts to hit, stay, or choose
a player when an action card requires a target. For Swap, Steal, and Discard,
click a highlighted card; Swap requires two cards from different players. In
Brutal Mode, a player who gets Flip 7 can take the bonus or subtract it from
another player. Press Escape or close the window to quit. The activity panel
shows the current round's draws and decisions; a summary appears after each
round.

Any command-line options skip setup and start immediately. Choose players with
`--human NAME` and `--bot KIND`; seats are filled in the order given, up to six
players. Bot kinds are `random`, `threshold[:SCORE]` (default 30), and
`expected` (`ExpectedValueBot`).
Every card is public, so several humans can share the screen and take turns. A
table of only bots can be watched. Bot decisions take at least one second each.
Number cards appear below modifiers and other cards and are sorted by value.
Other cards are ordered by modifier and action type; modifiers of the same type
are ordered by value. Each player's total score appears beside their live round
score, which excludes any Flip 7 bonus. Busted players normally score zero,
but can score negatively in Brutal Mode. Cards flip over and move from the deck
to each hand as they are dealt. Play waits for the animations to finish.

```shell
uv run python -m flip_seven_bots.ui --human Ann --human Ben --bot threshold:25
uv run python -m flip_seven_bots.ui --vengeance --human Ann --bot random
uv run python -m flip_seven_bots.ui --brutal
```

`--vengeance` selects With A Vengeance; `--brutal` selects it with Brutal Mode.
Either flag alone uses the default players. `--seed N` makes the decks
repeatable; bots keep their own randomness.

### Bug reports

Press **Report bug** (or F1) to pause the game and describe a problem. Enter
saves the message with the game's full state, including the hidden deck, to a
timestamped Markdown file in `bug_reports/` (change it with `--bug-dir`).
If the game crashes, a report with the error is written there automatically.
Each report ends with replay data, so the game can be rebuilt in a test:

```python
from flip_seven_bots.ui.bug_report import replay

game = replay("bug_reports/2026-11-21_16-30-05.md")
```

## Headless base game

The `game` package implements the original Flip 7 rules without Pygame. Player
IDs are zero-based seat indices. The dealer defaults to player 0; the player
to their left is dealt first. Ties for the highest final score are reported as
multiple winners. One- and two-player games use the same rules and goal.

```python
from flip_seven_bots.bots import RandomBot, ThresholdBot
from flip_seven_bots.simulation import play_game

result = play_game(
    [ThresholdBot(30), RandomBot(seed=1), ThresholdBot(40)],
    seed=123,
)
print(result.winners)
print([player.total_score for player in result.players])
```

To implement a bot, provide `choose_action(observation)` and return one of
`observation.legal_actions`. `observation.decision` says what is being decided:
`HitOrStay`, `ChooseTarget` (with the action `card` and eligible `targets`),
`ChooseCard`, or `FlipSevenBonus`. Each has an `actions` tuple and helpers such
as `hit()`, `stay()` and `choose(target)`. The decision is public, so every
seat can see it, but only the deciding player receives legal actions.

The intended way to build a bot is to match on the decision and hand each case
to a reusable function from `bots.policies` (simple rules) or `bots.rollouts`
(simulation). These functions take any randomness as an explicit `rng`.

```python
from random import Random

from flip_seven_bots.bots import policies, rollouts, ThresholdBot
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

Observations contain immutable
snapshots of public cards, scores, and the discard pile, but not the shuffled
deck. Cards still held after a player stays or busts remain visible because
they were revealed earlier in the round. `last_round` contains the most recently completed round's scores,
including any Flip 7 bonus; a player's `round_score` is the in-progress score
without it. `events` contains the current round's public draws, decisions,
discard reshuffles, and (once the game ends) the final round result.

The deck seed and a bot's seed are independent. `play_game` raises an error if
a game exceeds 100,000 decisions (for example, with custom rules that make the
target score unreachable), or if the deck is exhausted with no discarded
cards available to reshuffle. Pass `rules=Rules(...)` to change the target
score, bonus, deck, or scoring, and `deck=Deck.stacked(cards)` to `Game` to deal
cards in a fixed order (useful in tests).

### With A Vengeance

The headless engine also supports With A Vengeance.

```python
from flip_seven_bots.bots import ThresholdBot
from flip_seven_bots.game import VengeanceRules
from flip_seven_bots.simulation import play_game

result = play_game(
    [ThresholdBot(25), ThresholdBot(25), ThresholdBot(25)],
    seed=42,
    rules=VengeanceRules(),  # Use VengeanceRules(brutal=True) for Brutal Mode.
)
print(result.winners)
print([player.total_score for player in result.players])
```

In addition to target decisions, a Vengeance bot may receive `ChooseCard`
decisions, whose `CHOOSE_CARD` actions use `target` for the card owner and
`card_index` to index that player's `cards` in the current observation. Swap
uses two such decisions; during the second, `decision.first` is the card
already picked. In Brutal Mode a `FlipSevenBonus` decision offers `TAKE_BONUS`
or a `CHOOSE_TARGET` action to subtract the bonus from another player. The
included bots support these choices.

The Zero affects the round score, not accumulated points. A duplicate number
received through a swap or steal causes a bust, and Brutal Mode modifiers can
give a busted player a negative round score.

### Looking ahead

The deck order is the only hidden information. `observation.draw_pile` lists
the undrawn cards in a fixed sorted order, and
`observation.sample_game(rng)` returns an independent `Game` that matches the
observation with the remaining deck reshuffled by `rng`. Bots can apply
candidate actions to it and play it forward with
`flip_seven_bots.simulation.run(game, bots, stop=...)`. An observation can only
be sampled until the real game advances. Pass `next_draws=(card, ...)` to fix
the next cards drawn in the sample.

`ExpectedValueBot` uses this to hit only when the expected round score after
one more card, averaged over `draw_pile` and scored by the engine, beats its
current score (`policies.expected_hit_score`). For any decision,
`bots.rollouts.best_action` instead plays sampled games to the end of the round
and picks the action with the best average margin over the leading opponent;
the example bot above uses it for Flip Three targets.

### Tournaments

`run_tournament` plays a series of games between named bots and rates them.
Each game seats `players_per_game` bots (default: all), chosen and ordered at
random; `seed` controls seating, decks and the confidence intervals. A progress
bar shows the current leader; pass `progress=False` to hide it.

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

Every game is scored as all of its pairwise matches: the better place wins and
tied scores draw. Two ratings are computed from them, on the same Elo scale:

- `rating` (the summary's ranking) is a Bradley-Terry fit to all games at once:
  the model Elo assumes, fitted by maximum likelihood. It does not depend on
  game order and becomes more precise as games are added, which suits bots
  that never change. The bots that played average `initial_rating`, and each
  pair gets one virtual drawn game so ratings stay finite. `rating_low` and
  `rating_high` bound a `confidence` (default 95%) interval from `bootstrap`
  (default 200) refits on resampled games; pass `bootstrap=0` to skip it. Treat
  bots whose intervals overlap as indistinguishable.
- `elo` is an online Elo rating updated after every game, shown in
  `result.games` and the tournament window's chart. Each player's change is
  their K-factor divided by `n - 1` times the sum of actual minus expected
  results, so two-player games use standard Elo. The K-factor starts at
  `k_factor` and shrinks to `k_factor * h / (h + games played)`, where `h` is
  `k_half_life` (default 50), so ratings settle instead of drifting; pass
  `k_half_life=None` for a constant K.

Most of the noise in a game is the cards. With `rotate_seats=True`, each deal
is replayed with the same deck once per seat rotation, so every seated bot
gets the same cards from every seat; the `deal` column groups these games, and
`games` must be a multiple of the players per game.

Ratings assume a bot's strength does not depend on its opponents or the table
size, which may not hold in Flip 7, so compare ratings between tournaments
only when they use the same `players_per_game`.

`play_tournament` takes the same settings but returns an iterator that plays
one game per step and yields a `GameRecord`, for showing progress or stopping
early; `TournamentResult.from_records` builds the tables from the records.

From the command line, run a tournament with a progress bar, print the summary,
and optionally save `games.csv` and `summary.csv`:

```shell
uv run python -m flip_seven_bots.tournament --bot random --bot careful=threshold:40 \
    --bot expected --games 200 --players-per-game 3 --seed 1 --output results
```

`--bot [NAME=]KIND` accepts the same kinds as the game (`random`,
`threshold[:SCORE]`, `expected`); duplicate names are numbered. Without `--bot`,
a random, a threshold 30 and an expected value bot play. The summary shows each
rating with its 95% interval. Other options are `--rotate-seats`,
`--bootstrap`, `--k-factor`, `--k-half-life` or `--constant-k`,
`--initial-rating`, `--vengeance` and `--brutal`; see `--help`.

To watch a tournament in a window, run:

```shell
uv run python -m flip_seven_bots.ui.tournament
```

With no options, a setup screen lets you choose the mode, number of games,
players per game, seed, seat rotation, and up to eight bots. Any of the
command-line options above skip setup and start immediately. The tournament
screen shows a progress bar, live standings by Elo and an Elo chart; Stop ends
it after the current game. The final standings rank bots by `rating` with its
95% interval.
Afterwards, Save results writes the CSV files (to `--output`, if given, which
also saves them automatically, or otherwise to a timestamped folder in
`tournament_results`), and New tournament returns to setup.

Training integrations are not implemented yet.

## Tests

Run the pytest suite with `uv run pytest`.