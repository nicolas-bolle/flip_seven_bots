# Writing bots

A bot implements `choose_action(observation)` and returns an action from
`observation.legal_actions`. The bot receives public information, not the
actual deck order. The [reference](reference.md#writing-bots) explains the
decision types, observations, policies and lookahead.

## Create a bot

For example, add this module as `src/flip_seven_bots/bots/careful.py`:

```python
from flip_seven_bots.bots import policies
from flip_seven_bots.bots.registry import BotKind, Parameter, register
from flip_seven_bots.game import HitOrStay


class CarefulBot:
    def __init__(self, *, seed, threshold=25):
        self.threshold = threshold
        # If using randomness, initialize a private random generator with seed.

    def choose_action(self, observation):
        decision = policies.acting_decision(observation)
        if isinstance(decision, HitOrStay):
            return policies.stay_at_threshold(observation, decision, self.threshold)
        return policies.first_legal(observation)


register(
    BotKind(
        "careful",
        "Careful bot",
        CarefulBot,
        CarefulBot,
        (Parameter("threshold", 25),),
    )
)
```

Import the module from `bots/__init__.py` so registration runs when the package
loads, for example `from . import careful as careful`. The constructor accepts
`seed` even if it is unused, and each parameter must be available as an
same-named instance attribute. Parameters are integers by default; `Parameter`
also accepts a text parser. Multiple parameters use
`kind:name=value,other=value`. Registered constructors, parsers and display-name
functions must be importable at module scope for parallel tournaments.
Percent-encode reserved characters in text values (for example `%2C` for a
comma). `seed` is reserved for the factory.

```shell
uv run flip7 bots
uv run flip7 compare careful:25 threshold:30 --games 100 --seed 42 --jobs 2
uv run pytest tests/test_bots.py
```

The registered-bot conformance test plays each registered kind in all three
game modes, checks actions are legal and checks seeded replay. Add focused
tests for your strategy's own decisions and edge cases.

## Experiment from Python

Registered instances can be used as configurations. For other bots, provide a
factory accepting one positional seed and returning a new bot:

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

For `jobs > 1`, factories and rules must be picklable and importable by worker
processes; guard standalone script entry points as above. Instances of
unregistered bots are not accepted as tournament configurations: use a
factory instead. A fresh bot is created per game and retains its state across
that game's rounds. A bot can optionally implement
`on_game_start(seat, player_count, rules)` and `on_game_end(observation)`.
The end hook runs only when a game finishes successfully.

The existing `rollouts` helpers reuse their supplied rollout bot across seats
and samples. Use a stateless rollout policy, or account for that shared state
and its randomness when interpreting estimates.

To debug a reported game, use `uv run flip7 replay REPORT --moves N` or
`from flip_seven_bots.game.replay import replay`, then inspect the returned
`Game`. The report contains the hidden deck and should be treated accordingly.
