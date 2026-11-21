Implementing the board games Flip 7 and Flip 7: With A Vengeance and making bots for them. Keeping this project private without a license to dodge any Flip 7 copyright issues.

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
snapshots of public cards and scores, not the shuffled deck. Cards are included
after a player stays or busts because they were revealed earlier in the round.
Only the current player receives legal actions. `last_round` contains the
most recently completed round's scores. `events` retains public draws,
decisions, round results, and discard reshuffles, including events that happen
between decisions. This allows bots to remember revealed cards. A player's
`round_score` is a current score preview; the Flip 7 bonus is reflected in the
completed round's result.

The deck seed and a bot's seed are independent. `play_game` raises an error if
the decision limit is reached, or if the deck is exhausted with no discarded
cards available to reshuffle.

The `ui` package is reserved for a future Pygame interface. With A Vengeance
and training integrations are not implemented yet.