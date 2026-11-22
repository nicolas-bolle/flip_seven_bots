"""Rating calculations: online Elo updates and an order-independent Bradley-Terry fit."""

from collections.abc import Sequence
from itertools import combinations
from statistics import NormalDist

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
    tolerance: float = 1e-10,
    max_iterations: int = 100,
) -> np.ndarray:
    """Fit Elo-scale ratings (mean zero) to a matrix of pairwise results.

    ``wins[i, j]`` is how often player ``i`` beat ``j``, with draws counting a
    half to each. This is the model Elo assumes, fitted to all results at once
    by maximum likelihood (Newton's method). ``prior`` adds that many wins each
    way to every pair, like one drawn game per pair at the default, which keeps
    ratings finite when a player always wins or always loses.
    """
    wins = _with_prior(wins, prior)
    strength = np.zeros(len(wins))
    for _ in range(max_iterations):
        likelihood, gradient, information = _likelihood(strength, wins)
        step = np.linalg.pinv(information) @ gradient
        # Halve overlong steps so the likelihood never decreases.
        while (
            _likelihood(strength + step, wins)[0] < likelihood
            and np.abs(step).max() > tolerance
        ):
            step /= 2
        strength += step
        strength -= strength.mean()
        if np.abs(step).max() < tolerance:
            break
    return ELO_SCALE * strength


def _with_prior(wins: np.ndarray, prior: float) -> np.ndarray:
    return np.asarray(wins, dtype=float) + prior * (1 - np.eye(len(wins)))


def _likelihood(
    strength: np.ndarray, wins: np.ndarray
) -> tuple[float, np.ndarray, np.ndarray]:
    """Log-likelihood of natural-log strengths, its gradient, and the information matrix.

    The information matrix is the negative Hessian; it is singular along equal
    shifts of every strength, which leave the likelihood unchanged.
    """
    gaps = strength[:, None] - strength[None, :]
    win_chance = 1 / (1 + np.exp(-gaps))
    games = wins + wins.T
    likelihood = -(wins * np.logaddexp(0, -gaps)).sum()
    gradient = (wins - games * win_chance).sum(axis=1)
    variance = games * win_chance * (1 - win_chance)
    np.fill_diagonal(variance, 0)
    return likelihood, gradient, np.diag(variance.sum(axis=1)) - variance


class PairwiseResults:
    """Pairwise outcomes grouped into independent units, for fitting with intervals.

    Each unit (a game) adds its pairwise results. Results within a unit may be
    correlated, but units are assumed independent of each other.
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
        """Record every pair in one game; games with the same ``unit`` are grouped."""
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

    def wins(self) -> np.ndarray:
        """The win matrix: ``wins[i, j]`` is how often ``i`` beat ``j``, draws counting half."""
        size = len(self.players)
        flat = np.bincount(
            np.asarray(self._cells, dtype=int),
            np.asarray(self._scores),
            minlength=size * size,
        )
        return flat.reshape(size, size)

    def fit(
        self, *, confidence: float = 0.95, prior: float = 0.5
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return Bradley-Terry ratings (mean zero) with lower and upper interval bounds.

        Intervals use a cluster-robust (sandwich) standard error, which allows
        for correlated results within a unit, and a normal approximation. They
        are ``NaN`` with fewer than two units.
        """
        wins = self.wins()
        rating = fit_bradley_terry(wins, prior=prior)
        units = self.unit_count
        if units < 2:
            nan = np.full(len(self.players), np.nan)
            return rating, nan, nan.copy()
        strength = rating / ELO_SCALE
        _, _, information = _likelihood(strength, _with_prior(wins, prior))
        bread = np.linalg.pinv(information)
        rows, columns = np.divmod(np.asarray(self._cells, dtype=int), len(strength))
        gaps = strength[rows] - strength[columns]
        # Each unit's contribution to the log-likelihood gradient.
        slopes = np.asarray(self._scores) / (1 + np.exp(gaps))
        unit_index = np.asarray(self._units, dtype=int)
        unit_gradients = np.zeros((units, len(strength)))
        np.add.at(unit_gradients, (unit_index, rows), slopes)
        np.add.at(unit_gradients, (unit_index, columns), -slopes)
        meat = unit_gradients.T @ unit_gradients * units / (units - 1)
        error = ELO_SCALE * np.sqrt(np.diag(bread @ meat @ bread))
        margin = NormalDist().inv_cdf((1 + confidence) / 2) * error
        return rating, rating - margin, rating + margin
