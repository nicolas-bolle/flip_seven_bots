"""Registry of bot configurations shared by the interfaces."""

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote, unquote

from .base import Bot
from .simple import ExpectedValueBot, RandomBot, ThresholdBot


@dataclass(frozen=True)
class Parameter:
    """A bot parameter, its default, and its text parser."""

    name: str
    default: object
    parse: Callable[[str], object] = int


@dataclass(frozen=True)
class BotKind:
    """A registered bot and its configurable constructor parameters.

    The constructor must accept ``seed`` as a keyword argument. Deterministic
    bots may ignore it. Parameter values must also be readable as attributes.
    """

    kind: str
    label: str
    constructor: Callable[..., Bot]
    bot_type: type
    parameters: tuple[Parameter, ...] = ()
    display_name: Callable[..., str] | None = None


_KINDS: dict[str, BotKind] = {}


def register(kind: BotKind) -> None:
    """Register a bot kind, rejecting duplicate or invalid names."""
    if not kind.kind or any(c in kind.kind for c in ":,="):
        raise ValueError("invalid bot kind")
    if kind.kind in _KINDS:
        raise ValueError(f"bot kind {kind.kind!r} is already registered")
    if len({parameter.name for parameter in kind.parameters}) != len(kind.parameters):
        raise ValueError("duplicate bot parameter")
    if any(not p.name.isidentifier() or p.name == "seed" for p in kind.parameters):
        raise ValueError("invalid or reserved bot parameter name")
    _KINDS[kind.kind] = kind


def kinds() -> tuple[BotKind, ...]:
    """Return registered kinds in display order."""
    return tuple(_KINDS.values())


@dataclass(frozen=True)
class BotConfig:
    """A picklable factory for a configured bot."""

    definition: BotKind
    values: tuple[object, ...]

    def __call__(self, seed: int | None) -> Bot:
        kwargs: dict[str, object] = dict(
            zip(
                (parameter.name for parameter in self.definition.parameters),
                self.values,
            )
        )
        return self.definition.constructor(seed=seed, **kwargs)

    @property
    def name(self) -> str:
        if self.definition.display_name:
            return self.definition.display_name(*self.values)
        return self.definition.label

    @property
    def spec(self) -> str:
        if not self.values:
            return self.definition.kind
        if len(self.values) == 1:
            return f"{self.definition.kind}:{quote(str(self.values[0]), safe='')}"
        values = ",".join(
            f"{parameter.name}={quote(str(value), safe='')}"
            for parameter, value in zip(self.definition.parameters, self.values)
        )
        return f"{self.definition.kind}:{values}"


def default_parameters(kind: BotKind) -> str:
    """Return editable default parameters for a setup screen."""
    if len(kind.parameters) == 1:
        return quote(str(kind.parameters[0].default), safe="")
    return ",".join(
        f"{p.name}={quote(str(p.default), safe='')}" for p in kind.parameters
    )


def parse_config(spec: str) -> BotConfig:
    """Parse ``kind``, ``kind:value`` or ``kind:name=value,...``."""
    name, separator, text = spec.partition(":")
    if name not in _KINDS:
        raise ValueError(f"unknown bot {spec!r}; choose from {', '.join(_KINDS)}")
    definition = _KINDS[name]
    parameters = definition.parameters
    values = {parameter.name: parameter.default for parameter in parameters}
    if separator:
        if not parameters:
            raise ValueError(f"invalid parameters for {name!r}")
        if "=" not in text and len(parameters) == 1:
            entries = [(parameters[0].name, text)]
        else:
            entries = []
            for entry in text.split(","):
                key, equals, value = entry.partition("=")
                if not equals or not key:
                    raise ValueError(f"invalid parameter {entry!r}")
                entries.append((key, value))
        seen: set[str] = set()
        for key, value in entries:
            parameter = next((p for p in parameters if p.name == key), None)
            if parameter is None or key in seen:
                raise ValueError(f"unknown or duplicate parameter {key!r}")
            seen.add(key)
            try:
                values[key] = parameter.parse(unquote(value, errors="strict"))
            except ValueError as error:
                raise ValueError(f"invalid {key}: {error}") from error
    config = BotConfig(definition, tuple(values[p.name] for p in parameters))
    # Validate constructor constraints at input time.
    config(None)
    return config


def config_for(bot: Bot) -> BotConfig:
    """Get a registered configuration from a bot instance."""
    for definition in kinds():
        if type(bot) is definition.bot_type:
            return BotConfig(
                definition,
                tuple(getattr(bot, p.name) for p in definition.parameters),
            )
    raise ValueError(f"no registered configuration for {bot!r}; pass a bot factory")


def _random(*, seed: int | None) -> Bot:
    return RandomBot(seed)


def _threshold(*, seed: int | None, threshold: int) -> Bot:
    return ThresholdBot(threshold)


def _expected(*, seed: int | None) -> Bot:
    return ExpectedValueBot()


def _threshold_name(threshold: int) -> str:
    return f"Threshold {threshold}"


register(BotKind("random", "Random bot", _random, RandomBot))
register(
    BotKind(
        "threshold",
        "Threshold bot",
        _threshold,
        ThresholdBot,
        (Parameter("threshold", 30),),
        _threshold_name,
    )
)
register(BotKind("expected", "Expected value bot", _expected, ExpectedValueBot))
