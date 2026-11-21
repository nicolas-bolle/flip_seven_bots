"""Build bots from short text specifications, as used on command lines."""

from collections import Counter
from collections.abc import Sequence

from .base import Bot
from .simple import ExpectedValueBot, RandomBot, ThresholdBot

BOT_KINDS = ("random", "threshold[:SCORE]", "expected")
"""Accepted specifications; bracketed parts are optional."""

DEFAULT_THRESHOLD = 30


def parse_bot(spec: str) -> tuple[str, Bot]:
    """Return a display name and a new bot for a specification such as ``threshold:25``.

    Raises ``ValueError`` with a user-facing message for an invalid specification.
    """
    kind, _, value = spec.partition(":")
    try:
        number = int(value) if value else None
    except ValueError:
        raise ValueError(f"{value!r} is not a whole number") from None
    match kind, number:
        case "random", None:
            return "Random bot", RandomBot()
        case "threshold", _:
            threshold = DEFAULT_THRESHOLD if number is None else number
            if threshold < 0:
                raise ValueError("threshold must not be negative")
            return f"Threshold {threshold}", ThresholdBot(threshold)
        case "expected", None:
            return "Expected value bot", ExpectedValueBot()
    raise ValueError(f"unknown bot {spec!r}; choose from {', '.join(BOT_KINDS)}")


def bot_spec(bot: Bot) -> str:
    """Return the specification ``parse_bot`` accepts for a new bot like ``bot``.

    Raises ``ValueError`` for bots that have no specification.
    """
    match bot:
        case RandomBot():
            return "random"
        case ThresholdBot(threshold=threshold):
            return f"threshold:{threshold}"
        case ExpectedValueBot():
            return "expected"
    raise ValueError(f"no specification for {bot!r}")


def number_duplicates(names: Sequence[str]) -> list[str]:
    """Make names unique by numbering repeats in order: ``A, A, B`` becomes ``A 1, A 2, B``."""
    counts = Counter(names)
    seen: Counter[str] = Counter()
    numbered = []
    for name in names:
        if counts[name] > 1:
            seen[name] += 1
            name = f"{name} {seen[name]}"
        numbered.append(name)
    return numbered
