import numpy as np
import pandas as pd
import pytest

from sports import nba_matchup as m

def ID(n: str) -> str:
    return n.zfill(10)                                               # game ids are stored like real NBA ids


PREGAME = ["gp", "s_wins", "s_losses", "s_net", "s_ortg", "s_drtg", "s_pace", "s_efg", "s_tov_pct", "s_oreb_pct",
           "s_ft_rate", "s_opp_efg", "l10_net", "l10_wins", "home_net", "away_net", "rest_days", "b2b",
           "games_last6", "streak", "elo", "missing_count", "missing_min_share",
           "s_deserved", "s_luck", "roster_gs36", "roster_pm48", "roster_size"]


@pytest.fixture(scope="module")
def logs():
    lg = m.load_logs()
    if lg.empty:
        pytest.skip("no stored NBA data")
    return lg[lg["season"].isin(["2024-25", "2025-26"])]


def test_no_feature_uses_future_games(logs):
    """Features computed from all data must equal features computed with everything after the
    cutoff deleted. If any feature peeked at later games, these would differ."""
    cutoff = pd.Timestamp("2026-01-15")
    dates = pd.to_datetime(logs["GAME_DATE"])
    full = m.build_features(logs)
    cut = m.build_features(logs[dates <= cutoff])
    day = cut[cut["date"] == cutoff].set_index(["game_id", "team"])[PREGAME].sort_index()
    assert len(day) >= 10
    same = full.set_index(["game_id", "team"]).loc[day.index, PREGAME].sort_index()
    pd.testing.assert_frame_equal(day.astype(float), same.astype(float), check_exact=False, rtol=1e-9)


def test_season_ratios_match_reality(logs):
    g = m.team_games(logs)
    r = m.season_ratios(g[g["season"] == "2025-26"])
    assert (r["gp"] == 82).all() and len(r) == 30
    assert r["wins"].sum() == r["gp"].sum() / 2                      # every game has one winner
    assert 108 < m._ratios({c: g[c].sum() for c in m.SUM_COLS})["ortg"] < 120
    assert r.loc[("2025-26", "OKC"), "net"] == pytest.approx(r["net"].max())
    assert (g.groupby("game_id")["venue"].sum() == 0).all()          # one home + one away, or two neutral


def _toy():
    """Two teams, five games: A home, A away, neutral, A home (back-to-back), A away after 5 days."""
    rows = []
    games = [("1", "2026-01-01", "A vs. B", "B @ A", 110, 100), ("2", "2026-01-03", "A @ B", "B vs. A", 95, 105),
             ("3", "2026-01-05", "A vs. B", "B vs. A", 120, 90), ("4", "2026-01-06", "A vs. B", "B @ A", 101, 99),
             ("5", "2026-01-11", "A @ B", "B vs. A", 100, 104)]
    for gid, d, ma, mb, pa, pb in games:
        for team, mu, pts, opp in (("A", ma, pa, pb), ("B", mb, pb, pa)):
            rows.append({"season": "2025-26", "GAME_ID": gid, "GAME_DATE": d, "TEAM_ID": 1 if team == "A" else 2,
                         "TEAM_ABBREVIATION": team, "MATCHUP": mu, "WL": "W" if pts > opp else "L",
                         "PLAYER_ID": 10 if team == "A" else 20, "PLAYER_NAME": team + " star", "PLUS_MINUS": pts - opp,
                         **{c: 0 for c in m.BOX}, "PTS": pts, "FGA": 80, "FGM": 40, "MIN": 240})
    return pd.DataFrame(rows)


def test_rest_streak_venue_and_splits_on_a_toy_schedule():
    f = m.build_features(_toy())
    a = f[f.team == "A"].set_index("game_id")
    assert a["venue"].tolist() == [1, -1, 0, 1, -1]                  # game 3 listed "vs." both ways: neutral
    assert a["rest_days"].tolist() == [7, 2, 2, 1, 5]
    assert a["b2b"].tolist() == [0, 0, 0, 1, 0]
    assert a["streak"].tolist() == [0, 1, -1, 1, 2]
    assert a["s_wins"].tolist() == [0, 1, 1, 2, 3] and a["gp"].tolist() == [0, 1, 2, 3, 4]
    assert np.isnan(a.loc[ID("1"), "home_net"]) and a.loc[ID("2"), "home_net"] > 0   # only game 1 was at home
    assert np.isnan(a.loc[ID("2"), "away_net"]) and a.loc[ID("5"), "away_net"] < 0   # only game 2 was away (lost)
    assert a.loc[ID("1"), "elo"] == m.ELO_START and a.loc[ID("2"), "elo"] > m.ELO_START  # won game 1 -> Elo up
    b = f[f.team == "B"].set_index("game_id")
    assert a.loc[ID("2"), "elo"] - m.ELO_START == pytest.approx(m.ELO_START - b.loc[ID("2"), "elo"])  # zero-sum


def test_missing_regulars_uses_only_the_previous_game():
    rows = []
    for i in range(1, 8):                                            # star plays games 1-6, sits game 7
        for pid, name, mins in ((1, "Star", 34), (2, "Bench", 12)):
            if pid == 1 and i == 7:
                continue
            rows.append({"season": "2025-26", "GAME_ID": str(i), "GAME_DATE": f"2026-01-{i:02d}",
                         "TEAM_ABBREVIATION": "A", "PLAYER_ID": pid, "PLAYER_NAME": name, "MIN": mins})
    miss = m.missing_regulars(pd.DataFrame(rows)).set_index("game_id")
    assert miss.loc[ID("7"), "missing_count"] == 0                       # game 7: he played game 6, unknown yet
    rows.append({"season": "2025-26", "GAME_ID": "8", "GAME_DATE": "2026-01-08", "TEAM_ABBREVIATION": "A",
                 "PLAYER_ID": 2, "PLAYER_NAME": "Bench", "MIN": 12})
    miss = m.missing_regulars(pd.DataFrame(rows)).set_index("game_id")
    assert miss.loc[ID("8"), "missing_count"] == 1 and miss.loc[ID("8"), "missing_names"] == "Star"
    assert miss.loc[ID("8"), "missing_min_share"] == pytest.approx(34 / 240)
    assert miss.loc[ID("8"), "missing_count"] == 1 and "Bench" not in miss.loc[ID("8"), "missing_names"]


def test_current_state_matches_the_real_pregame_numbers(logs):
    """A team's 'current state' on a past date must equal its real pregame row from that day."""
    day = pd.Timestamp("2026-01-15")
    full = m.build_features(logs[pd.to_datetime(logs["GAME_DATE"]) <= day])
    real = full[full["date"] == day].set_index("team")
    state = m.current_state(logs, day)
    cols = ["gp", "s_wins", "s_net", "s_efg", "l10_net", "l10_wins", "home_net", "away_net", "streak", "elo",
            "missing_count", "s_luck", "roster_gs36", "roster_pm48", "roster_size"]
    teams = real.index.intersection(state.index)
    assert len(teams) >= 10
    pd.testing.assert_frame_equal(state.loc[teams, cols].astype(float), real.loc[teams, cols].astype(float),
                                  check_exact=False, rtol=1e-9)


def test_schedule_h2h_and_rows(logs):
    g = m.team_games(logs)
    day = pd.Timestamp("2026-01-15")
    s = m.schedule_for(g, "OKC", day)
    assert set(s) == {"rest_days", "b2b", "games_last6"} and 1 <= s["rest_days"] <= 7
    h = m.head_to_head(g, "OKC", "DEN", day)
    assert h["games"] == h["a_wins"] + h["b_wins"] and len(h["recent"]) <= 5
    state = m.current_state(logs, day)
    rows = m.matchup_rows(state.loc["OKC"], state.loc["WAS"], s, m.schedule_for(g, "WAS", day))
    by = {r.label: r for r in rows}
    assert by["Defensive rating"].better == ("a" if state.loc["OKC", "s_drtg"] < state.loc["WAS", "s_drtg"] else "b")
    assert by["Pace"].better is None                                   # pace isn't good or bad
    assert {r.section for r in rows} >= {"Strength", "Form", "Offense", "Defense", "Schedule", "Availability"}



# ---------------------------------------------------------------- player ratings & roster strength

def _player_rows():
    """Star (id 1) plays 3 games for A, then 2 for B (traded). Bench (2) always plays for A."""
    rows = []
    sched = [("1", "2026-01-01", "A"), ("2", "2026-01-03", "A"), ("3", "2026-01-05", "A"),
             ("4", "2026-01-07", "B"), ("5", "2026-01-09", "B")]
    for gid, d, star_team in sched:
        rows.append({"season": "2025-26", "GAME_ID": gid, "GAME_DATE": d, "TEAM_ABBREVIATION": star_team,
                     "PLAYER_ID": 1, "MIN": 36, "PLUS_MINUS": 10, "PTS": 35, "FGM": 13, "FGA": 22, "FTA": 8,
                     "FTM": 7, "OREB": 1, "DREB": 7, "STL": 2, "AST": 8, "BLK": 1, "PF": 2, "TOV": 3})
        rows.append({"season": "2025-26", "GAME_ID": gid, "GAME_DATE": d, "TEAM_ABBREVIATION": "A",
                     "PLAYER_ID": 2, "MIN": 12, "PLUS_MINUS": -4, "PTS": 3, "FGM": 1, "FGA": 5, "FTA": 0,
                     "FTM": 0, "OREB": 0, "DREB": 1, "STL": 0, "AST": 1, "BLK": 0, "PF": 2, "TOV": 1})
    return pd.DataFrame(rows)


def test_player_ratings_learn_only_from_earlier_games_and_follow_trades():
    from sports import nba_players as np_
    r = np_.player_ratings(_player_rows())
    star = r[r.player_id == 1].sort_values("date")
    assert star["gs36"].iloc[0] == pytest.approx(np_.REPL_GS36)            # first game: replacement level
    assert star["gs36"].is_monotonic_increasing                            # learns from each great game
    assert star["gs36"].iloc[1] == pytest.approx(star["gs36_post"].iloc[0])  # pregame = previous postgame
    assert star["team"].tolist() == ["A", "A", "A", "B", "B"]
    assert star["gs36"].iloc[3] == pytest.approx(star["gs36_post"].iloc[2])  # rating moved with him to B


def test_team_strength_uses_who_played_the_previous_game():
    from sports import nba_players as np_
    r = np_.player_ratings(_player_rows())
    ts = np_.team_strength(r).set_index(["team", "game_id"])
    # game 4: A's previous game (3) had the star -> still counted; game 5: he played for B in game 4 -> gone
    assert ts.loc[("A", ID("4")), "roster_size"] == 2
    assert ts.loc[("A", ID("5")), "roster_size"] == 1
    assert ts.loc[("A", ID("5")), "roster_gs36"] < ts.loc[("A", ID("4")), "roster_gs36"]
    assert ts.loc[("B", ID("5")), "roster_gs36"] > ts.loc[("A", ID("5")), "roster_gs36"]  # B gained him


def test_luck_meter():
    f = m.build_features(_toy())
    a = f[f.team == "A"].set_index("game_id")
    # before game 3, A is 1-1 and has outscored B 205-205 -> deserved .500, luck 0
    assert a.loc[ID("3"), "s_deserved"] == pytest.approx(0.5) and a.loc[ID("3"), "s_luck"] == pytest.approx(0.0)
    # before game 5, A is 3-1 with points 426-394 -> luck = .75 - deserved
    exp = 1 / (1 + (394 / 426) ** m.PYTHAG_EXP)
    assert a.loc[ID("5"), "s_luck"] == pytest.approx(0.75 - exp)
