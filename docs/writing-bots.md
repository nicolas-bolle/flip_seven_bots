# Write and test a bot

A bot is any object with a `choose_action(observation)` method that returns
one of `observation.legal_actions`. The observation contains everything public
at the table, but not the order of the deck. The
[reference](reference.md#writing-bots) describes decisions, observations, and
the lookahead tools in full.

## 1. Write the bot

Add a module such as `src/flip_seven_bots/bots/careful.py`:

```python
from flip_seven_bots.bots import policies
from flip_seven_bots.bots.registry import BotKind, Parameter, register
from flip_seven_bots.game import HitOrStay


class CarefulBot:
    def __init__(self, *, seed, threshold=25):
        # A bot that uses randomness should create its own Random(seed).
        self.threshold = threshold

    def choose_action(self, observation):
        decision = policies.acting_decision(observation)
        if isinstance(decision, HitOrStay):
            return policies.stay_at_threshold(observation, decision, self.threshold)
        return policies.first_legal(observation)


register(
    BotKind(
        kind="careful",
        label="Careful bot",
        constructor=CarefulBot,
        bot_type=CarefulBot,
        parameters=(Parameter("threshold", 25),),
    )
)
```

`observation.decision` says what is being decided: hit or stay, a target for an
action card, a card to swap, steal, or discard, or a Brutal Mode bonus. A good
structure is to match on it and hand each case to a function from
`bots.policies` (simple rules) or `bots.rollouts` (simulation); see
[Building a bot](reference.md#building-a-bot).

## 2. Register it

Import the module from `src/flip_seven_bots/bots/__init__.py` so registration
runs when the package loads:

```python
from . import careful as careful
```

Registration makes the bot available as the spec `careful` or
`careful:threshold=20` in every command and setup screen. The rules:

- The constructor takes `seed` as a keyword argument, even if it ignores it.
  `seed` is reserved and cannot be a parameter.
- Each parameter is also an instance attribute of the same name, so bots can
  be described and saved.
- Parameters are integers unless `Parameter` gets another parser, for example
  `Parameter("style", "safe", str)`. With several parameters, use
  `kind:name=value,other=value`; percent-encode reserved characters in text
  values, for example `%2C` for a comma.
- The constructor, parsers, and any `display_name` function must be defined at
  module level, so that parallel tournament workers can import them.

## 3. Try it

```shell
uv run flip7 bots
uv run flip7 compare careful:25 threshold:30 --games 100 --seed 42 --jobs 2
uv run flip7 trace --bot careful --bot random --seed 1 --step
```

## 4. Test it

```shell
uv run pytest tests/test_bots.py
```

The conformance test there plays every registered bot in all three game modes,
and checks that its actions are legal and that seeded games repeat exactly.
Add focused tests for your strategy's own decisions; build exact situations
with `Game(..., deck=Deck.stacked(cards))`.

## Experiment from Python

`run_tournament` accepts two kinds of bot:

- An instance of a registered bot, used only as a configuration. A fresh,
  seeded copy is built for every game.
- A factory that takes one positional seed and returns a new bot. Use this for
  unregistered bots; their instances are rejected.

```python
from flip_seven_bots.bots import ThresholdBot
from flip_seven_bots.bots.careful import CarefulBot
from flip_seven_bots.tournament import run_tournament


def make_careful(seed):
    return CarefulBot(seed=seed, threshold=25)


if __name__ == "__main__":
    result = run_tournament(
        {"careful": make_careful, "baseline": ThresholdBot(30)},
        games=100,
        seed=42,
        jobs=2,
    )
    print(result.summary)
```

With `jobs > 1`, games run in separate processes, so factories and rules must
be importable from a module, and scripts need the `if __name__ == "__main__"`
guard shown above.

A bot lasts for one game: it keeps any state between rounds, but not between
games. It can also define `on_game_start(seat, player_count, rules)` and
`on_game_end(observation)`; the end hook runs only for a game that finishes
normally.

The `rollouts` helpers use the bot you supply for every seat and every sample.
Prefer a stateless rollout bot, or allow for its shared state and randomness
when interpreting the estimates.

## Debug a game

Press F1 in the game window to save a bug report, then rebuild the game with
`uv run flip7 replay REPORT --moves N`, or from Python with
`flip_seven_bots.game.replay.replay` and inspect the returned `Game`. Reports
include the hidden deck order, so they reveal upcoming cards.
