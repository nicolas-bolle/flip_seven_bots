"""Registry of bot configurations shared by the interfaces."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial
from urllib.parse import quote, unquote

from .base import Bot
from .simple import ExpectedValueBot, RandomBot, ThresholdBot


@dataclass(frozen=True)
class Parameter:
    """A required bot parameter and its text parser."""

    name: str
    parse: Callable[[str], object]


@dataclass(frozen=True)
class BotKind:
    """A registered bot and its configurable constructor parameters.

    The constructor must accept ``seed`` as a keyword argument. Deterministic
    bots may ignore it. Parameter values must also be readable as attributes.
    Pass an empty parameter tuple for bots without parameters. The display name
    is either a fixed string or a callable taking the parameter values in order.
    """

    key: str
    bot_type: type
    parameters: tuple[Parameter, ...]
    constructor: Callable[..., Bot]
    display_name: str | Callable[..., str]


_KINDS: dict[str, BotKind] = {}


def _fixed_name(name: str, *_values: object) -> str:
    return name


def register(kind: BotKind) -> None:
    """Register a bot kind, normalizing a fixed display name to a callable."""
    if not kind.key or any(c in kind.key for c in ':,='):
        raise ValueError('invalid bot kind')
    if kind.key in _KINDS:
        raise ValueError(f'bot kind {kind.key!r} is already registered')
    if len({parameter.name for parameter in kind.parameters}) != len(kind.parameters):
        raise ValueError('duplicate bot parameter')
    if any(not p.name.isidentifier() or p.name == 'seed' for p in kind.parameters):
        raise ValueError('invalid or reserved bot parameter name')
    if isinstance(kind.display_name, str):
        kind = replace(kind, display_name=partial(_fixed_name, kind.display_name))
    _KINDS[kind.key] = kind


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
        display_name = self.definition.display_name
        if not callable(display_name):
            raise TypeError('bot configuration requires a registered display name')
        return display_name(*self.values)

    @property
    def spec(self) -> str:
        if not self.values:
            return self.definition.key
        # A named empty value stays distinct from a blank setup field.
        if len(self.values) == 1 and str(self.values[0]):
            return f'{self.definition.key}:{quote(str(self.values[0]), safe="")}'
        values = ','.join(
            f'{parameter.name}={quote(str(value), safe="")}'
            for parameter, value in zip(self.definition.parameters, self.values)
        )
        return f'{self.definition.key}:{values}'


def parse_config(spec: str) -> BotConfig:
    """Parse a bot spec with explicit values for all its parameters."""
    name, separator, text = spec.partition(':')
    if name not in _KINDS:
        raise ValueError(f'unknown bot {spec!r}; choose from {", ".join(_KINDS)}')
    definition = _KINDS[name]
    parameters = definition.parameters
    values: dict[str, object] = {}
    if separator:
        if not parameters:
            raise ValueError(f'invalid parameters for {name!r}')
        if '=' not in text and len(parameters) == 1:
            entries = [(parameters[0].name, text)]
        else:
            entries = []
            for entry in text.split(','):
                key, equals, value = entry.partition('=')
                if not equals or not key:
                    raise ValueError(f'invalid parameter {entry!r}')
                entries.append((key, value))
        for key, value in entries:
            parameter = next((p for p in parameters if p.name == key), None)
            if parameter is None or key in values:
                raise ValueError(f'unknown or duplicate parameter {key!r}')
            try:
                values[key] = parameter.parse(unquote(value, errors='strict'))
            except ValueError as error:
                raise ValueError(f'invalid {key}: {error}') from error
    missing = [p.name for p in parameters if p.name not in values]
    if missing:
        raise ValueError(
            f'missing required parameters for {name!r}: {", ".join(missing)}'
        )
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
    raise ValueError(f'no registered configuration for {bot!r}; pass a bot factory')


def _construct_random(*, seed: int | None) -> Bot:
    return RandomBot(seed)


def _construct_threshold(*, seed: int | None, threshold: int) -> Bot:
    return ThresholdBot(threshold)


def _construct_expected(*, seed: int | None) -> Bot:
    return ExpectedValueBot()


def _threshold_name(threshold: int) -> str:
    return f'Threshold {threshold}'


register(
    BotKind(
        key='random',
        bot_type=RandomBot,
        parameters=(),
        constructor=_construct_random,
        display_name='Random',
    )
)
register(
    BotKind(
        key='threshold',
        bot_type=ThresholdBot,
        parameters=(Parameter('threshold', int),),
        constructor=_construct_threshold,
        display_name=_threshold_name,
    )
)
register(
    BotKind(
        key='expected',
        bot_type=ExpectedValueBot,
        parameters=(),
        constructor=_construct_expected,
        display_name='Expected value',
    )
)
