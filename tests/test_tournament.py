import pandas as pd
import pytest

from flip_seven_bots.bots import ThresholdBot
from flip_seven_bots.tournament import elo_update, run_tournament


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
    assert games["rating"].sub(games["rating_before"]).equals(games["rating_change"])
    for _, history in games.groupby("player"):
        assert history["rating_before"].iloc[1:].tolist() == history["rating"].iloc[:-1].tolist()

    summary = result.summary
    assert summary["rating"].is_monotonic_decreasing
    assert summary["rating"].sum() == pytest.approx(4500)
    last = games.groupby("player")["rating"].last()
    assert summary["rating"].to_dict() == pytest.approx(last.to_dict())
    assert summary["games"].tolist() == [4, 4, 4]
    assert summary["wins"].sum() >= 4
    assert summary.loc["t20", "win_rate"] == summary.loc["t20", "wins"] / 4


def test_tournament_is_reproducible_with_a_seed() -> None:
    first = run_tournament(threshold_bots(10, 20, 30), games=3, seed=8)
    second = run_tournament(threshold_bots(10, 20, 30), games=3, seed=8)
    pd.testing.assert_frame_equal(first.games, second.games)
    pd.testing.assert_frame_equal(first.summary, second.summary)


def test_smaller_tables_seat_a_subset_and_unplayed_bots_keep_their_rating() -> None:
    result = run_tournament(
        threshold_bots(10, 20, 30), games=1, players_per_game=2, seed=0, initial_rating=1000
    )
    assert len(result.games) == 2
    benched = result.summary[result.summary["games"] == 0]
    assert len(benched) == 1
    assert benched["rating"].item() == 1000
    assert benched[["win_rate", "mean_place", "mean_score"]].isna().all(axis=None)


@pytest.mark.parametrize(
    ("bots", "options", "message"),
    [
        (threshold_bots(10, 20), {"games": 0}, "games"),
        (threshold_bots(10), {"games": 1}, "players_per_game"),
        (threshold_bots(10, 20), {"games": 1, "players_per_game": 3}, "players_per_game"),
        (threshold_bots(10, 20), {"games": 1, "players_per_game": 1}, "players_per_game"),
    ],
    ids=["no-games", "one-bot", "table-too-big", "table-too-small"],
)
def test_invalid_tournaments_are_rejected(
    bots: dict[str, ThresholdBot], options: dict[str, int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_tournament(bots, **options)


def test_progress_bar_can_be_disabled(capsys: pytest.CaptureFixture[str]) -> None:
    run_tournament(threshold_bots(10, 20), games=2, seed=0)
    assert "Tournament" in capsys.readouterr().err
    run_tournament(threshold_bots(10, 20), games=2, seed=0, progress=False)
    assert capsys.readouterr().err == ""
