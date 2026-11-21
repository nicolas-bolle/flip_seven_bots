Implementing the board games Flip 7 and Flip 7: With A Vengeance and making bots for them. Keeping this project private without a license to dodge any Flip 7 copyright issues.

## Play against bots

Run the Pygame interface with:

```shell
uv run python -m flip_seven_bots.ui
```

You play the base game against a random bot and a bot that stays at 30 points.
Use the buttons or their displayed keyboard shortcuts to hit, stay, or choose
a player when an action card requires a target. Press Escape or close the
window to quit. The activity panel shows the current round's draws and
decisions; a summary appears after each round.

Choose the players with `--human NAME` and `--bot KIND` options; seats are
filled in the order given, up to six players. Bot kinds are `random`,
`threshold[:SCORE]` (default 30), and `montecarlo[:SAMPLES]` (default 50).
Every card is public, so several humans can share the screen and take turns.
A table of only bots can be watched.

```shell
uv run python -m flip_seven_bots.ui --human Ann --human Ben --bot threshold:25
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
`observation.legal_actions`. The engine pauses both for hit/stay decisions and
for selecting targets for action cards. Observations contain immutable
snapshots of public cards, scores, and the discard pile, but not the shuffled
deck. Cards are included after a player stays or busts because they were
revealed earlier in the round. Only the current player receives legal actions.
`last_round` contains the most recently completed round's scores, including any
Flip 7 bonus; a player's `round_score` is the in-progress score without it.
`events` contains the current round's public draws, decisions, discard
reshuffles, and (once the game ends) the final round result.

The deck seed and a bot's seed are independent. `play_game` raises an error if
the decision limit is reached, or if the deck is exhausted with no discarded
cards available to reshuffle. Pass `rules=Rules(...)` to change the target
score, bonus, deck, or scoring, and `deck=Deck.stacked(cards)` to `Game` to deal
cards in a fixed order (useful in tests).

### Looking ahead

The deck order is the only hidden information, so
`observation.sample_game(rng)` returns an independent `Game` that matches the
observation with the remaining deck reshuffled by `rng`. Bots can apply
candidate actions to it and play it forward with
`flip_seven_bots.simulation.run(game, bots, stop=...)`. An observation can only
be sampled until the real game advances. `FlipThreeMonteCarloBot` uses this to
choose Flip Three targets and delegates other decisions to a fallback bot.

With A Vengeance and training integrations are not implemented yet.

## Tests

Run the pytest suite with `uv run pytest`.