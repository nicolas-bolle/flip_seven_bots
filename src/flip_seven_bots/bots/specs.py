"""Build bots from short text specifications, as used on command lines."""

from collections import Counter
from collections.abc import Sequence

from .base import Bot
from .registry import config_for, parse_config


def parse_bot(spec: str) -> tuple[str, Bot]:
    """Return a display name and a new bot for a specification such as ``threshold:25``.

    Raises ``ValueError`` with a user-facing message for an invalid specification.
    """
    config = parse_config(spec)
    return config.name, config(None)


def parse_named_bot(spec: str) -> tuple[str, Bot]:
    """Parse ``[NAME=]KIND`` with optional parameters."""
    prefix, colon, parameters = spec.partition(":")
    name, separator, kind = prefix.partition("=")
    if separator and not name.strip():
        raise ValueError("a bot name must not be blank")
    kind = (kind if separator else name) + (colon + parameters if colon else "")
    default_name, bot = parse_bot(kind)
    return (name.strip() if separator else default_name), bot


def bot_spec(bot: Bot) -> str:
    """Return the specification ``parse_bot`` accepts for a new bot like ``bot``.

    Raises ``ValueError`` for bots that have no specification.
    """
    return config_for(bot).spec


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
