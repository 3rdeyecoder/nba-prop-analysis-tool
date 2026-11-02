import pandas as pd

from core import links
from sports import insights


def _games(pid, name, pts, start="2026-01-01", season_year=2026, minutes=30, opp="BOS", team="NYK"):
    dates = pd.date_range(start, periods=len(pts), freq="2D")
    return pd.DataFrame({"player_id": pid, "player_name": name, "team": team, "opponent": opp,
                         "game_id": [f"{pid}-{i}" for i in range(len(pts))], "game_date": dates,
                         "season_year": season_year, "season": f"{season_year}-{(season_year + 1) % 100:02d}",
                         "PTS": pts, "MIN": minutes})


def _two_seasons(pid, name, old_pts, new_pts, **kw):
    old = _games(pid, name, old_pts, start="2025-01-01", season_year=2025, **kw)
    new = _games(pid, name, new_pts, start="2026-01-01", season_year=2026, **kw)
    return pd.concat([old, new], ignore_index=True)


def test_heating_up_ranks_by_recent_jump_and_reports_samples():
    df = pd.concat([_two_seasons("1", "Hot", [15] * 30, [15] * 5 + [30] * 5),
                    _two_seasons("2", "Flat", [20] * 30, [20] * 10)])
    out = insights.heating_up(df)
    assert out.iloc[0]["player_name"] == "Hot"
    assert out.iloc[0]["change"] == 15 and out.iloc[0]["recent_n"] == 5 and out.iloc[0]["baseline_n"] == 30
    assert out.iloc[0]["recent_min"] == 30 and out.iloc[0]["baseline_min"] == 30


def test_heating_up_requires_recent_games_in_current_season_and_minutes():
    few_new = _two_seasons("1", "TwoGames", [10] * 30, [40, 40])          # only 2 games this season
    bench = _two_seasons("2", "Bench", [2] * 30, [20] * 6, minutes=8)       # low minutes
    assert insights.heating_up(pd.concat([few_new, bench])).empty


def test_consistency_prefers_low_spread_and_applies_minimum():
    steady = _two_seasons("1", "Steady", [20] * 10, [20, 21, 19, 20, 21, 19, 20, 20, 21, 19])
    wild = _two_seasons("2", "Wild", [20] * 10, [5, 35, 10, 30, 8, 32, 12, 28, 15, 25])
    low = _two_seasons("3", "Low", [5] * 10, [5] * 10)                    # under 15 ppg
    out = insights.consistency(pd.concat([steady, wild, low]))
    assert out["player_name"].tolist() == ["Steady", "Wild"]


def test_matchup_history_needs_min_games_and_one_row_per_player():
    base = _two_seasons("1", "A", [20] * 20, [20] * 10)
    vs_mia = _games("1", "A", [35] * 6, start="2026-03-01", opp="MIA")
    vs_chi = _games("1", "A", [30] * 6, start="2026-04-01", opp="CHI")
    tiny = _games("1", "A", [60] * 2, start="2026-05-01", opp="LAL")        # only 2 games: ignored
    out = insights.matchup_history(pd.concat([base, vs_mia, vs_chi, tiny], ignore_index=True))
    assert len(out) == 1 and out.iloc[0]["opponent"] == "MIA" and out.iloc[0]["n"] == 6


def test_links_roundtrip_values():
    p = links.build(sport="nba", player_id="1629029", stat_col="PTS", seasons=["2025-26", "2026-27"],
                    season_type="Regular Season", window_label="All games", opponent="BOS", venue="Home", line=27.5)
    assert p == {"sport": "nba", "player": "1629029", "stat": "PTS", "seasons": "2025-26,2026-27",
                 "type": "regular", "window": "all", "opp": "BOS", "venue": "home", "line": "27.5"}
    assert links.SLUG_TO_WINDOW["all"] == "All games" and links.type_slug("Postseason") == "postseason"


def test_players_who_missed_their_teams_last_game_are_left_out():
    star = _two_seasons("1", "Injured Star", [25] * 20, [25] * 6 + [45] * 5)      # last played Jan 21
    healthy = _two_seasons("2", "Healthy", [15] * 20, [15] * 6 + [25] * 6)        # played Jan 23, team's latest
    df = pd.concat([star, healthy], ignore_index=True)
    assert insights.available_players(df) == {"2"}
    assert "Injured Star" not in insights.heating_up(df)["player_name"].tolist()
    assert insights.missed_last_game(df[df.season_year == 2026])["player_name"].tolist() == ["Injured Star"]


def test_manual_unavailable_list_excludes_and_expires(tmp_path, monkeypatch):
    from datetime import date
    from core import unavailable
    f = tmp_path / "unavailable.csv"
    f.write_text("sport,player_id,player_name,until,note\n"
                 "nba,1,Out Guy,2027-01-05,Injury\n"
                 "nba,2,Back Guy,2026-10-01,Was hurt\n"
                 "nfl,3,Other Sport,,\n")
    monkeypatch.setattr(unavailable, "PATH", f)
    assert unavailable.ids("nba", date(2026, 11, 2)) == {"1"}          # expired row ignored
    assert unavailable.ids("nba", date(2027, 1, 6)) == frozenset()     # after the return date
    assert unavailable.ids("nfl", date(2026, 11, 2)) == {"3"}          # no date = until removed

    healthy = _two_seasons("1", "Out Guy", [15] * 20, [15] * 5 + [30] * 5)
    assert insights.heating_up(healthy, exclude=frozenset({"1"})).empty


def test_missing_or_broken_unavailable_file_means_nobody(tmp_path, monkeypatch):
    from core import unavailable
    monkeypatch.setattr(unavailable, "PATH", tmp_path / "nope.csv")
    assert unavailable.ids("nba") == frozenset()
    bad = tmp_path / "bad.csv"
    bad.write_text("name\nsomebody\n")
    monkeypatch.setattr(unavailable, "PATH", bad)
    assert unavailable.ids("nba") == frozenset()
