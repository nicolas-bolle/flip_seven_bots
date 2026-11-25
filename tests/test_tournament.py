from typing import Any, cast

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from flip_seven_bots.bots import RandomBot, ThresholdBot
from flip_seven_bots.game import Action, Observation
from flip_seven_bots.tournament import (
    PairwiseResults,
    TournamentResult,
    core,
    elo_update,
    fit_bradley_terry,
    play_tournament,
    run_tournament,
)
from flip_seven_bots.tournament.ratings import ELO_SCALE


def threshold_bots(*thresholds: int) -> dict[str, ThresholdBot]:
    return {f't{threshold}': ThresholdBot(threshold) for threshold in thresholds}


class BrokenBot:
    def choose_action(self, observation: Observation) -> Action:
        raise RuntimeError('worker bot failed')


def broken_factory(seed: int | None) -> BrokenBot:
    return BrokenBot()


def traces(figure: go.Figure) -> tuple[Any, ...]:
    # plotly leaves Figure.data untyped, so Pylance can't infer the trace type.
    return cast('tuple[Any, ...]', figure.data)


def test_two_player_elo_is_standard_elo() -> None:
    assert elo_update([1500, 1500], [1, 2]) == [1516, 1484]
    assert elo_update([1500, 1500], [1, 1]) == [1500, 1500]
    # A 400-point favourite is expected to score 10/11, so losing costs 22 * 10/11.
    favourite, underdog = elo_update([1900, 1500], [2, 1], k_factor=22)
    assert (favourite, underdog) == pytest.approx((1880, 1520))


def test_multiplayer_elo_rewards_places_and_conserves_rating() -> None:
    ratings = elo_update([1500, 1500, 1500, 1500], [2, 1, 4, 2])
    assert sum(ratings) == pytest.approx(6000)
    assert ratings[1] > ratings[0] == ratings[3] > ratings[2]
    # Each player's change is K/(n-1) times the sum of their pairwise results.
    assert ratings[1] == pytest.approx(1500 + 32 / 3 * 1.5)


def test_elo_rejects_mismatched_or_solo_games() -> None:
    with pytest.raises(ValueError, match='same length'):
        elo_update([1500, 1500], [1])
    with pytest.raises(ValueError, match='two players'):
        elo_update([1500], [1])


def test_tournament_records_games_and_chains_ratings() -> None:
    result = run_tournament(threshold_bots(10, 20, 30), games=4, seed=3)
    games = result.games

    assert len(games) == 12
    assert list(games.groupby('game')['seat'].apply(list)) == [[0, 1, 2]] * 4
    assert (games.groupby('game')['place'].min() == 1).all()
    assert (games['won'] == (games['place'] == 1)).all()
    assert games['elo'].sub(games['elo_before']).equals(games['elo_change'])
    for _, history in games.groupby('player'):
        assert (
            history['elo_before'].iloc[1:].tolist() == history['elo'].iloc[:-1].tolist()
        )

    summary = result.summary
    assert summary['rating'].is_monotonic_decreasing
    assert summary['rating'].sum() == pytest.approx(
        4500
    )  # centred on the initial rating
    assert (summary['rating_low'] <= summary['rating']).all()
    assert (summary['rating'] <= summary['rating_high']).all()
    last = games.groupby('player')['elo'].last()
    assert summary['elo'].to_dict() == pytest.approx(last.to_dict())
    assert summary['games'].tolist() == [4, 4, 4]
    assert summary['wins'].sum() >= 4
    assert summary['win_rate']['t20'] == summary['wins']['t20'] / 4


def test_tournament_is_reproducible_with_a_seed() -> None:
    first = run_tournament(threshold_bots(10, 20, 30), games=3, seed=8)
    second = run_tournament(threshold_bots(10, 20, 30), games=3, seed=8)
    pd.testing.assert_frame_equal(first.games, second.games)
    pd.testing.assert_frame_equal(first.summary, second.summary)


def test_random_bots_are_reproducible_across_worker_counts() -> None:
    bots = {'random': RandomBot(), 'threshold': ThresholdBot(25)}
    sequential = run_tournament(bots, games=8, seed=42, jobs=1, progress=False)
    parallel = run_tournament(bots, games=8, seed=42, jobs=2, progress=False)
    pd.testing.assert_frame_equal(sequential.games, parallel.games)
    pd.testing.assert_frame_equal(sequential.summary, parallel.summary)


@pytest.mark.parametrize(('cpus', 'expected_workers'), [(2, 2), (100, 3)])
def test_default_workers_use_available_cpus_and_preserve_results(
    monkeypatch: pytest.MonkeyPatch, cpus: int, expected_workers: int
) -> None:
    monkeypatch.setattr(core.os, 'process_cpu_count', lambda: cpus)
    original_executor = core.ProcessPoolExecutor
    counts: list[int] = []

    def executor(*, max_workers: int) -> core.ProcessPoolExecutor:
        counts.append(max_workers)
        return original_executor(max_workers=max_workers)

    monkeypatch.setattr(core, 'ProcessPoolExecutor', executor)
    bots = {'random': RandomBot(), 'threshold': ThresholdBot(25)}
    sequential = list(play_tournament(bots, games=3, seed=42, jobs=1))
    automatic = list(play_tournament(bots, games=3, seed=42))
    assert automatic == sequential
    assert counts == [expected_workers]


def test_automatic_workers_handle_unknown_cpu_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(core.os, 'process_cpu_count', lambda: None)
    bots = threshold_bots(10, 20)
    assert len(list(play_tournament(bots, games=1, jobs=-1))) == 1


@pytest.mark.parametrize('jobs', [0, -2])
def test_tournament_rejects_invalid_worker_counts(jobs: int) -> None:
    with pytest.raises(ValueError, match='jobs'):
        play_tournament(threshold_bots(10, 20), games=1, jobs=jobs)


def test_factory_gets_fresh_seed_and_bot_for_every_game() -> None:
    seeds: list[int | None] = []

    def factory(seed: int | None) -> RandomBot:
        seeds.append(seed)
        return RandomBot(seed)

    run_tournament(
        {'random': factory, 'threshold': ThresholdBot(30)},
        games=5,
        seed=7,
        progress=False,
        jobs=1,
    )
    assert len(seeds) == 5 and len(set(seeds)) == 5


def test_bot_class_is_accepted_as_a_seeded_factory() -> None:
    result = run_tournament(
        {'random': RandomBot, 'threshold': ThresholdBot(30)},
        games=2,
        seed=3,
        progress=False,
    )
    assert len(result.games) == 4


def test_parallel_worker_errors_reach_the_caller() -> None:
    with pytest.raises(RuntimeError, match='worker bot failed'):
        run_tournament(
            {'broken': broken_factory, 'other': ThresholdBot(0)},
            games=3,
            seed=3,
            jobs=2,
            progress=False,
        )


def test_smaller_tables_seat_a_subset_and_unplayed_bots_are_unrated() -> None:
    result = run_tournament(
        threshold_bots(10, 20, 30),
        games=1,
        players_per_game=2,
        seed=0,
        initial_rating=1000,
    )
    assert len(result.games) == 2
    benched = result.summary[result.summary['games'] == 0]
    assert len(benched) == 1
    assert benched['elo'].item() == 1000
    statistics = [
        'win_rate',
        'mean_place',
        'mean_score',
        'rating',
        'rating_low',
        'rating_high',
    ]
    assert benched[statistics].isna().all(axis=None)
    assert result.summary.index[-1] == benched.index[0]
    assert result.summary['rating'].dropna().mean() == pytest.approx(1000)


def test_default_table_seats_every_bot_up_to_the_player_limit() -> None:
    result = run_tournament(threshold_bots(*range(11)), games=1, seed=0, progress=False)
    assert len(result.games) == 10


@pytest.mark.parametrize(
    ('bots', 'options', 'message'),
    [
        (threshold_bots(10, 20), {'games': 0}, 'games'),
        (threshold_bots(10), {'games': 1}, 'players_per_game'),
        (
            threshold_bots(10, 20),
            {'games': 1, 'players_per_game': 3},
            'players_per_game',
        ),
        (
            threshold_bots(10, 20),
            {'games': 1, 'players_per_game': 1},
            'players_per_game',
        ),
        (
            threshold_bots(*range(11)),
            {'games': 1, 'players_per_game': 11},
            'players_per_game',
        ),
        (threshold_bots(10, 20), {'games': 2, 'k_half_life': 0}, 'k_half_life'),
    ],
    ids=[
        'no-games',
        'one-bot',
        'table-too-big',
        'table-too-small',
        'table-over-player-limit',
        'half-life',
    ],
)
def test_invalid_tournaments_are_rejected(
    bots: dict[str, ThresholdBot], options: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_tournament(bots, **options)


def test_progress_bar_can_be_disabled(capsys: pytest.CaptureFixture[str]) -> None:
    run_tournament(threshold_bots(10, 20), games=2, seed=0)
    assert 'Tournament' in capsys.readouterr().err
    run_tournament(threshold_bots(10, 20), games=2, seed=0, progress=False)
    assert capsys.readouterr().err == ''


def test_elo_accepts_a_k_factor_per_player() -> None:
    assert elo_update([1500, 1500], [1, 2], k_factor=[32, 8]) == [1516, 1496]
    with pytest.raises(ValueError, match='one K-factor per player'):
        elo_update([1500, 1500], [1, 2], k_factor=[32])


def test_elo_k_factor_decays_with_games_played() -> None:
    def changes(k_half_life: float | None) -> list[float]:
        result = run_tournament(
            threshold_bots(10, 30),
            games=2,
            seed=1,
            k_half_life=k_half_life,
            progress=False,
        )
        return result.games.groupby('game')['elo_change'].max().tolist()

    constant, dynamic = changes(None), changes(4)
    # Both start at K=32, so the second game starts from the same ratings and
    # only the K-factor, 32 * 4 / (4 + 1), differs.
    assert constant[0] == dynamic[0] == pytest.approx(16)
    assert dynamic[1] == pytest.approx(constant[1] * 4 / 5)


def test_bradley_terry_matches_the_closed_form_for_two_players() -> None:
    wins = np.array([[0, 30], [10, 0]])
    ratings = fit_bradley_terry(wins, prior=0)
    assert ratings[0] - ratings[1] == pytest.approx(400 * np.log10(3))
    assert ratings.sum() == pytest.approx(0)
    # The prior keeps an unbeaten player's rating finite.
    assert np.isfinite(fit_bradley_terry(np.array([[0, 5], [0, 0]]))).all()
    # Full Newton steps diverge on results this lopsided.
    lopsided = fit_bradley_terry(np.array([[0, 10**7], [1, 0]]))
    assert lopsided[0] - lopsided[1] == pytest.approx(400 * np.log10(10**7 / 1.5))


def test_ratings_cannot_be_shifted_by_game_order() -> None:
    results = PairwiseResults(['a', 'b', 'c'])
    games = [
        (('a', 'b', 'c'), (1, 2, 3)),
        (('b', 'c', 'a'), (1, 1, 3)),
        (('c', 'a', 'b'), (2, 1, 3)),
    ]
    for unit, (players, places) in enumerate(games):
        results.add(unit, players, places)
    reversed_results = PairwiseResults(['a', 'b', 'c'])
    for unit, (players, places) in enumerate(reversed(games)):
        reversed_results.add(unit, players, places)
    np.testing.assert_allclose(results.fit()[0], reversed_results.fit()[0])


def two_player_results(
    games: int, a_wins: int, copies: int = 1, *, shared: bool
) -> PairwiseResults:
    """``a`` beats ``b`` in the first ``a_wins`` games; each game is recorded
    ``copies`` times, in the same unit if ``shared`` and otherwise separately."""
    results = PairwiseResults(['a', 'b'])
    for game in range(games):
        for copy in range(copies):
            unit = game if shared else (game, copy)
            results.add(unit, ['a', 'b'], [1, 2] if game < a_wins else [2, 1])
    return results


def test_rating_interval_matches_the_closed_form_for_two_players() -> None:
    rating, low, high = two_player_results(40, 30, shared=True).fit(prior=0)
    # The rating gap has the logit's standard error, 1 / sqrt(n p (1 - p)), with
    # an n / (n - 1) small-sample correction; each player carries half of it.
    error = ELO_SCALE * np.sqrt(40 / 39 / (40 * 0.75 * 0.25)) / 2
    np.testing.assert_allclose(high - rating, 1.96 * error, rtol=1e-3)
    np.testing.assert_allclose(rating - low, 1.96 * error, rtol=1e-3)


def test_rating_interval_counts_each_unit_once() -> None:
    def width(results: PairwiseResults) -> float:
        _, low, high = results.fit(prior=0)
        return high[0] - low[0]

    single = width(two_player_results(40, 30, shared=True))
    # Repeating results within a unit adds no information...
    assert width(two_player_results(40, 30, 2, shared=True)) == pytest.approx(single)
    # ...but independent repeats narrow the interval by about sqrt(2).
    separate = width(two_player_results(40, 30, 2, shared=False))
    assert separate == pytest.approx(single / np.sqrt(2), rel=0.02)
    # One unit gives no interval.
    _, low, high = two_player_results(1, 1, shared=True).fit()
    assert np.isnan(low).all() and np.isnan(high).all()


def test_plots_show_ratings_intervals_and_elo_history() -> None:
    records = list(play_tournament(threshold_bots(10, 30), games=4, seed=1))
    result = TournamentResult.from_records(
        records, ['t10', 't30', 'idle'], initial_rating=1500
    )
    summary = result.summary.dropna(subset=['rating'])

    ratings = result.plot_ratings()
    assert [trace.x[0] for trace in traces(ratings)] == list(summary.index)
    for trace, (_, row) in zip(traces(ratings), summary.iterrows()):
        assert trace.y[0] == row['rating']
        assert trace.y[0] + trace.error_y.array[0] == pytest.approx(row['rating_high'])
        assert trace.y[0] - trace.error_y.arrayminus[0] == pytest.approx(
            row['rating_low']
        )

    elo = result.plot_elo()
    assert {trace.legendgroup for trace in traces(elo)} == set(summary.index)
    for name, row in summary.iterrows():
        band, rating, history = (t for t in traces(elo) if t.legendgroup == name)
        assert (min(band.y), max(band.y)) == (row['rating_low'], row['rating_high'])
        assert set(rating.y) == {row['rating']}
        assert (history.x[0], history.y[0]) == (0, 1500)
        assert (history.x[-1], history.y[-1]) == (4, row['elo'])
