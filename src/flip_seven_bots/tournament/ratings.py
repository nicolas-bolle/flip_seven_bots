"""Rating calculations: online Elo updates and an order-independent Bradley-Terry fit."""

from collections.abc import Sequence
from itertools import combinations

import numpy as np

ELO_SCALE = 400 / np.log(10)
"""Elo points per unit of natural-log strength: a 400-point gap means 10:1 odds."""


def elo_update(
    ratings: Sequence[float],
    places: Sequence[int],
    *,
    k_factor: float | Sequence[float] = 32.0,
) -> list[float]:
    """Return new ratings after one game, treating it as every pairwise match.

    For each pair of players the better place wins and equal places draw. A
    player's change is their K-factor divided by ``n - 1``, times the sum over
    opponents of actual minus expected result, so two players get standard Elo.
    ``k_factor`` may give one value per player; with a single value the total
    rating is unchanged.
    """
    if len(ratings) != len(places):
        raise ValueError("ratings and places must have the same length")
    if len(ratings) < 2:
        raise ValueError("a rated game needs at least two players")
    factors = (
        [k_factor] * len(ratings)
        if isinstance(k_factor, int | float)
        else list(k_factor)
    )
    if len(factors) != len(ratings):
        raise ValueError("give one K-factor per player")
    deltas = [0.0] * len(ratings)
    for i, j in combinations(range(len(ratings)), 2):
        expected = 1 / (1 + 10 ** ((ratings[j] - ratings[i]) / 400))
        actual = (
            1.0 if places[i] < places[j] else 0.5 if places[i] == places[j] else 0.0
        )
        deltas[i] += actual - expected
        deltas[j] -= actual - expected
    return [
        rating + factor / (len(ratings) - 1) * delta
        for rating, factor, delta in zip(ratings, factors, deltas)
    ]


def fit_bradley_terry(
    wins: np.ndarray,
    *,
    prior: float = 0.5,
    tolerance: float = 1e-9,
    max_iterations: int = 10_000,
) -> np.ndarray:
    """Fit Elo-scale ratings (mean zero) to a matrix of pairwise results.

    ``wins[i, j]`` is how often player ``i`` beat ``j``, with draws counting a
    half to each. This is the model Elo assumes, fitted to all results at once
    by maximum likelihood (minorization-maximization). ``prior`` adds that many
    wins each way to every pair, like one drawn game per pair at the default,
    which keeps ratings finite when a player always wins or always loses.
    """
    count = len(wins)
    wins = np.asarray(wins, dtype=float) + prior * (1 - np.eye(count))
    games = wins + wins.T
    total = wins.sum(axis=1)
    strength = np.ones(count)
    for _ in range(max_iterations):
        updated = total / (games / (strength[:, None] + strength[None, :])).sum(axis=1)
        updated /= np.exp(np.log(updated).mean())
        converged = np.abs(np.log(updated) - np.log(strength)).max() < tolerance
        strength = updated
        if converged:
            break
    return ELO_SCALE * np.log(strength)


class PairwiseResults:
    """Pairwise outcomes grouped into independent units, for fitting and resampling.

    Each unit (a game, or a set of seat-rotated games sharing a deck) adds its
    pairwise results; ``wins`` sums them with optional per-unit weights.
    """

    def __init__(self, players: Sequence[str]) -> None:
        self.players = list(players)
        self._index = {name: index for index, name in enumerate(self.players)}
        self._cells: list[int] = []
        self._scores: list[float] = []
        self._units: list[int] = []
        self._unit_ids: dict[object, int] = {}

    @property
    def unit_count(self) -> int:
        return len(self._unit_ids)

    def add(self, unit: object, players: Sequence[str], places: Sequence[int]) -> None:
        """Record every pair in one game; games with the same ``unit`` resample together."""
        unit_index = self._unit_ids.setdefault(unit, len(self._unit_ids))
        size = len(self.players)
        for i, j in combinations(range(len(players)), 2):
            a, b = self._index[players[i]], self._index[players[j]]
            score = (
                1.0 if places[i] < places[j] else 0.5 if places[i] == places[j] else 0.0
            )
            self._cells += [a * size + b, b * size + a]
            self._scores += [score, 1 - score]
            self._units += [unit_index, unit_index]

    def wins(self, weights: np.ndarray | None = None) -> np.ndarray:
        """The win matrix, counting each unit ``weights[unit]`` times (default once)."""
        size = len(self.players)
        scores = np.asarray(self._scores)
        if weights is not None:
            scores = scores * weights[np.asarray(self._units, dtype=int)]
        flat = np.bincount(
            np.asarray(self._cells, dtype=int), scores, minlength=size * size
        )
        return flat.reshape(size, size)

    def fit(
        self, *, bootstrap: int = 0, confidence: float = 0.95, seed: int | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return Bradley-Terry ratings (mean zero) with lower and upper interval bounds.

        Intervals are percentiles over ``bootstrap`` refits on units resampled
        with replacement; they are ``NaN`` when ``bootstrap`` is zero.
        """
        rating = fit_bradley_terry(self.wins())
        if bootstrap < 1 or self.unit_count == 0:
            nan = np.full(len(self.players), np.nan)
            return rating, nan, nan.copy()
        rng = np.random.default_rng(seed)
        units = self.unit_count
        samples = np.array(
            [
                fit_bradley_terry(
                    self.wins(rng.multinomial(units, np.full(units, 1 / units)))
                )
                for _ in range(bootstrap)
            ]
        )
        tail = (1 - confidence) / 2 * 100
        low, high = np.percentile(samples, [tail, 100 - tail], axis=0)
        return rating, low, high
