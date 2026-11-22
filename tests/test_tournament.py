import numpy as np
import pandas as pd
import pytest

from flip_seven_bots.bots import ThresholdBot
from flip_seven_bots.tournament import (
    PairwiseResults,
    elo_update,
    fit_bradley_terry,
    run_tournament,
)


def threshold_bots(*thresholds: int) -> dict[str, ThresholdBot]:
    return {f"t{threshold}": ThresholdBot(threshold) for threshold in thresholds}


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
    with pytest.raises(ValueError, match="same length"):
        elo_update([1500, 1500], [1])
    with pytest.raises(ValueError, match="two players"):
        elo_update([1500], [1])


def test_tournament_records_games_and_chains_ratings() -> None:
    result = run_tournament(threshold_bots(10, 20, 30), games=4, seed=3)
    games = result.games

    assert len(games) == 12
    assert list(games.groupby("game")["seat"].apply(list)) == [[0, 1, 2]] * 4
    assert (games.groupby("game")["place"].min() == 1).all()
    assert (games["won"] == (games["place"] == 1)).all()
    assert games["elo"].sub(games["elo_before"]).equals(games["elo_change"])
    for _, history in games.groupby("player"):
        assert (
            history["elo_before"].iloc[1:].tolist() == history["elo"].iloc[:-1].tolist()
        )

    summary = result.summary
    assert summary["rating"].is_monotonic_decreasing
    assert summary["rating"].sum() == pytest.approx(
        4500
    )  # centred on the initial rating
    assert (summary["rating_low"] <= summary["rating"]).all()
    assert (summary["rating"] <= summary["rating_high"]).all()
    last = games.groupby("player")["elo"].last()
    assert summary["elo"].to_dict() == pytest.approx(last.to_dict())
    assert summary["games"].tolist() == [4, 4, 4]
    assert summary["wins"].sum() >= 4
    assert summary.loc["t20", "win_rate"] == summary.loc["t20", "wins"] / 4


def test_tournament_is_reproducible_with_a_seed() -> None:
    first = run_tournament(threshold_bots(10, 20, 30), games=3, seed=8)
    second = run_tournament(threshold_bots(10, 20, 30), games=3, seed=8)
    pd.testing.assert_frame_equal(first.games, second.games)
    pd.testing.assert_frame_equal(first.summary, second.summary)


def test_smaller_tables_seat_a_subset_and_unplayed_bots_are_unrated() -> None:
    result = run_tournament(
        threshold_bots(10, 20, 30),
        games=1,
        players_per_game=2,
        seed=0,
        initial_rating=1000,
    )
    assert len(result.games) == 2
    benched = result.summary[result.summary["games"] == 0]
    assert len(benched) == 1
    assert benched["elo"].item() == 1000
    statistics = [
        "win_rate",
        "mean_place",
        "mean_score",
        "rating",
        "rating_low",
        "rating_high",
    ]
    assert benched[statistics].isna().all(axis=None)
    assert result.summary.index[-1] == benched.index[0]
    assert result.summary["rating"].dropna().mean() == pytest.approx(1000)


@pytest.mark.parametrize(
    ("bots", "options", "message"),
    [
        (threshold_bots(10, 20), {"games": 0}, "games"),
        (threshold_bots(10), {"games": 1}, "players_per_game"),
        (
            threshold_bots(10, 20),
            {"games": 1, "players_per_game": 3},
            "players_per_game",
        ),
        (
            threshold_bots(10, 20),
            {"games": 1, "players_per_game": 1},
            "players_per_game",
        ),
        (
            threshold_bots(10, 20, 30),
            {"games": 4, "rotate_seats": True},
            "multiple of 3",
        ),
        (threshold_bots(10, 20), {"games": 2, "k_half_life": 0}, "k_half_life"),
    ],
    ids=[
        "no-games",
        "one-bot",
        "table-too-big",
        "table-too-small",
        "rotation",
        "half-life",
    ],
)
def test_invalid_tournaments_are_rejected(
    bots: dict[str, ThresholdBot], options: dict[str, int | bool], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_tournament(bots, **options)


def test_progress_bar_can_be_disabled(capsys: pytest.CaptureFixture[str]) -> None:
    run_tournament(threshold_bots(10, 20), games=2, seed=0)
    assert "Tournament" in capsys.readouterr().err
    run_tournament(threshold_bots(10, 20), games=2, seed=0, progress=False)
    assert capsys.readouterr().err == ""


def test_elo_accepts_a_k_factor_per_player() -> None:
    assert elo_update([1500, 1500], [1, 2], k_factor=[32, 8]) == [1516, 1496]
    with pytest.raises(ValueError, match="one K-factor per player"):
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
        return result.games.groupby("game")["elo_change"].max().tolist()

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


def test_ratings_cannot_be_shifted_by_game_order() -> None:
    results = PairwiseResults(["a", "b", "c"])
    games = [
        (("a", "b", "c"), (1, 2, 3)),
        (("b", "c", "a"), (1, 1, 3)),
        (("c", "a", "b"), (2, 1, 3)),
    ]
    for unit, (players, places) in enumerate(games):
        results.add(unit, players, places)
    reversed_results = PairwiseResults(["a", "b", "c"])
    for unit, (players, places) in enumerate(reversed(games)):
        reversed_results.add(unit, players, places)
    np.testing.assert_allclose(results.fit()[0], reversed_results.fit()[0])


def test_bootstrap_intervals_can_be_skipped() -> None:
    result = run_tournament(
        threshold_bots(10, 30), games=3, seed=0, bootstrap=0, progress=False
    )
    assert result.summary[["rating_low", "rating_high"]].isna().all(axis=None)
    assert result.summary["rating"].notna().all()


def test_rotated_seats_replay_each_deal_from_every_seat() -> None:
    result = run_tournament(
        threshold_bots(10, 20, 30, 40),
        games=6,
        players_per_game=3,
        rotate_seats=True,
        seed=2,
        progress=False,
    )
    games = result.games
    assert games["deal"].tolist() == [1] * 9 + [2] * 9
    for _, deal in games.groupby("deal"):
        assert deal["player"].nunique() == 3
        assert deal.groupby("player")["seat"].apply(sorted).tolist() == [[0, 1, 2]] * 3
