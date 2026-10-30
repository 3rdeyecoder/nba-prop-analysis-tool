"""Sport normalization tests. MLB uses small hand-written JSON shaped like the Stats API
(this sandbox cannot reach statsapi.mlb.com); NBA/NFL also run against the stored real data."""
import pandas as pd
import pytest

from sports import mlb, nba, nfl


# ---------------------------------------------------------------- NFL

def _nfl_frames():
    base = {c: 0 for c in nfl.RAW_STATS}
    stats = pd.DataFrame([
        {**base, "player_id": "00-1", "player_display_name": "QB One", "position": "QB", "headshot_url": None,
         "season": 2024, "week": 18, "season_type": "REG", "game_id": "2024_18_KC_DEN", "team": "KC",
         "opponent_team": "DEN", "passing_yards": 250, "rushing_yards": 30, "rushing_tds": 1},
        {**base, "player_id": "00-1", "player_display_name": "QB One", "position": "QB", "headshot_url": None,
         "season": 2024, "week": 22, "season_type": "POST", "game_id": "2024_22_KC_PHI", "team": "KC",
         "opponent_team": "PHI", "passing_yards": 257, "receiving_yards": None},
        {**base, "player_id": "00-9", "player_display_name": "Some LB", "position": "LB", "headshot_url": None,
         "season": 2024, "week": 18, "season_type": "REG", "game_id": "2024_18_KC_DEN", "team": "DEN",
         "opponent_team": "KC"},
    ])
    sched = pd.DataFrame([
        {"game_id": "2024_18_KC_DEN", "gameday": "2025-01-05", "home_team": "DEN", "away_team": "KC",
         "location": "Home", "game_type": "REG"},
        {"game_id": "2024_22_KC_PHI", "gameday": "2025-02-09", "home_team": "PHI", "away_team": "KC",
         "location": "Neutral", "game_type": "SB"},
    ])
    return stats, sched


def test_nfl_normalize_season_labels_and_postseason():
    df = nfl.add_derived(nfl.normalize(*_nfl_frames()))
    assert set(df["player_id"]) == {"00-1"}               # defensive player with no offense dropped
    assert (df["season"] == "2024").all()                 # January/February games stay in 2024 season
    assert df["game_date"].dt.year.tolist() == [2025, 2025]
    post = df[df["season_type"] == "Postseason"]
    reg = df[df["season_type"] == "Regular Season"]
    assert len(post) == 1 and len(reg) == 1
    assert post["venue"].item() == "Neutral" and post["round"].item() == "Super Bowl"
    assert reg["venue"].item() == "Away"


def test_nfl_combos_keep_missing_as_missing():
    df = nfl.add_derived(nfl.normalize(*_nfl_frames()))
    reg = df[df["season_type"] == "Regular Season"].iloc[0]
    assert reg["pass_rush_yards"] == 280 and reg["rush_rec_tds"] == 1
    post = df[df["season_type"] == "Postseason"].iloc[0]
    assert pd.isna(post["rush_rec_yards"])                # missing receiving value is not treated as 0


def test_nfl_stored_data_integrity():
    seasons = nfl.available_seasons()
    if not seasons:
        pytest.skip("no stored NFL data")
    df = pd.concat([nfl.load_season(s) for s in seasons])
    assert not df.duplicated(["player_id", "game_id"]).any()
    assert df["game_date"].notna().all()
    assert set(df["season_type"]) <= {"Regular Season", "Postseason"}
    # every postseason game is dated after that season's regular season
    for s, g in df.groupby("season"):
        if (g.season_type == "Postseason").any():
            assert g[g.season_type == "Postseason"].game_date.min() > g[g.season_type == "Regular Season"].game_date.max()


def test_nfl_players_who_change_teams_keep_one_id():
    seasons = nfl.available_seasons()
    if not seasons:
        pytest.skip("no stored NFL data")
    df = pd.concat([nfl.load_season(s) for s in seasons])
    teams = df.groupby("player_id")["team"].nunique()
    assert (teams > 1).any()  # traded/signed players exist and stay under one player_id


# ---------------------------------------------------------------- MLB

def _team(abbr, tid):
    return {"team": {"id": tid, "abbreviation": abbr}}


SCHEDULE = {"dates": [
    {"date": "2025-07-04", "games": [
        {"gamePk": 1, "gameType": "R", "officialDate": "2025-07-04", "gameNumber": 1, "doubleHeader": "S",
         "status": {"detailedState": "Final"}, "teams": {"home": _team("NYY", 147), "away": _team("BOS", 111)}},
        {"gamePk": 2, "gameType": "R", "officialDate": "2025-07-04", "gameNumber": 2, "doubleHeader": "S",
         "status": {"detailedState": "Final"}, "teams": {"home": _team("NYY", 147), "away": _team("BOS", 111)}},
        {"gamePk": 3, "gameType": "R", "officialDate": "2025-07-04", "gameNumber": 1, "doubleHeader": "N",
         "status": {"detailedState": "Suspended: Rain"}, "teams": {"home": _team("LAD", 119), "away": _team("SD", 135)}},
        {"gamePk": 4, "gameType": "R", "officialDate": "2025-07-04", "gameNumber": 1, "doubleHeader": "N",
         "status": {"detailedState": "Postponed"}, "teams": {"home": _team("CHC", 112), "away": _team("STL", 138)}},
        {"gamePk": 5, "gameType": "S", "officialDate": "2025-07-04", "gameNumber": 1,
         "status": {"detailedState": "Final"}, "teams": {"home": _team("A", 1), "away": _team("B", 2)}},
    ]},
    {"date": "2025-07-05", "games": [
        {"gamePk": 3, "gameType": "R", "officialDate": "2025-07-04", "gameNumber": 1, "doubleHeader": "N",
         "status": {"detailedState": "Final"}, "teams": {"home": _team("LAD", 119), "away": _team("SD", 135)}},
    ]},
    {"date": "2025-10-01", "games": [
        {"gamePk": 6, "gameType": "F", "officialDate": "2025-10-01", "gameNumber": 1,
         "status": {"detailedState": "Final"}, "teams": {"home": _team("LAD", 119), "away": _team("SD", 135)}},
    ]},
]}


def test_mlb_schedule_doubleheader_suspended_postponed():
    g = mlb.parse_schedule(SCHEDULE).set_index("game_pk")
    assert set(g.index) == {1, 2, 3, 6}             # postponed + spring training excluded
    assert g.loc[1, "game_number"] == 1 and g.loc[2, "game_number"] == 2
    assert g.loc[3, "game_date"] == "2025-07-04"     # suspended game dated by the day it began
    assert g.loc[3, "resumed_date"] == "2025-07-05"
    assert pd.isna(g.loc[1, "resumed_date"])
    assert mlb.GAME_TYPES[g.loc[6, "game_type"]] == "Postseason"


def _player(pid, name, batting=None, pitching=None, order=None):
    p = {"person": {"id": pid, "fullName": name}, "position": {"abbreviation": "X"},
         "stats": {"batting": batting or {}, "pitching": pitching or {}}}
    if order:
        p["battingOrder"] = order
    return p


def _box():
    bat = {"plateAppearances": 4, "atBats": 3, "hits": 2, "doubles": 1, "triples": 0, "homeRuns": 1,
           "runs": 1, "rbi": 2, "baseOnBalls": 1, "strikeOuts": 1, "stolenBases": 0}
    return {"teams": {
        "home": {"players": {
            "ID660271": _player(660271, "Two Way", batting=bat, order="200",
                                pitching={"outs": 17, "inningsPitched": "5.2", "battersFaced": 22, "strikeOuts": 9,
                                          "hits": 4, "earnedRuns": 2, "baseOnBalls": 1, "homeRuns": 0,
                                          "gamesStarted": 1, "numberOfPitches": 92}),
            "ID2": _player(2, "Bench Guy", batting={"plateAppearances": 0}),            # defensive sub only
            "ID3": _player(3, "Pinch Hitter", batting={**bat, "plateAppearances": 1}, order="901"),
        }},
        "away": {"players": {
            "ID4": _player(4, "Reliever", pitching={"inningsPitched": "1.1", "battersFaced": 5, "strikeOuts": 2,
                                                    "gamesStarted": 0}),
            "ID5": _player(5, "Pickoff Only", pitching={"battersFaced": 0, "outs": 0}),
        }},
    }}


def test_mlb_boxscore_rules_two_way_and_strikeouts():
    games = mlb.parse_schedule(SCHEDULE).set_index("game_pk")
    game = {"game_pk": 2, **games.loc[2].to_dict()}
    hit, pit = mlb.parse_boxscore(_box(), game)
    hitters = {r["player_name"]: r for r in hit}
    pitchers = {r["player_name"]: r for r in pit}

    assert set(hitters) == {"Two Way", "Pinch Hitter"}          # 0-PA sub excluded
    assert set(pitchers) == {"Two Way", "Reliever"}             # faced nobody -> excluded
    tw = hitters["Two Way"]
    assert tw["started"] and not hitters["Pinch Hitter"]["started"]
    assert tw["singles"] == 0 and tw["total_bases"] == 2 + 4     # 1 double + 1 HR
    assert tw["so"] == 1 and pitchers["Two Way"]["k"] == 9       # batter vs pitcher strikeouts kept apart
    assert pitchers["Two Way"]["outs"] == 17 and pitchers["Two Way"]["started"]
    assert pitchers["Reliever"]["outs"] == 4 and not pitchers["Reliever"]["started"]  # derived from 1.1 IP
    assert tw["game_seq"] == 2 and tw["venue"] == "Home" and tw["opponent"] == "BOS"


def test_mlb_finalize_and_display():
    games = mlb.parse_schedule(SCHEDULE).set_index("game_pk")
    rows_h, rows_p = [], []
    for pk in (1, 2):
        h, p = mlb.parse_boxscore(_box(), {"game_pk": pk, **games.loc[pk].to_dict()})
        rows_h += h + h                                     # duplicate on purpose
        rows_p += p
    hit = mlb.add_derived(mlb.finalize(rows_h, 2025), "hitting")
    pit = mlb.add_derived(mlb.finalize(rows_p, 2025), "pitching")
    assert not hit.duplicated(["player_id", "game_id"]).any()
    assert hit[hit.player_name == "Two Way"]["game_id"].tolist() == ["1", "2"]   # doubleheader = 2 games
    assert pit.loc[pit.player_name == "Two Way", "ip"].tolist() == ["5.2", "5.2"]
    assert (hit["season_type"] == "Regular Season").all()


# ---------------------------------------------------------------- NBA

def test_nba_stored_snapshot_normalizes():
    files = nba.available_files()
    if not files:
        pytest.skip("no stored NBA data")
    season, stype, path = files[-1]
    df = nba.load_file(path, season, stype)
    assert not df.duplicated(["player_id", "game_id"]).any()
    assert set(df["venue"]) <= {"Home", "Away"}
    row = df.iloc[0]
    assert row["PRA"] == row["PTS"] + row["REB"] + row["AST"]
    assert row["BLK_STL"] == row["BLK"] + row["STL"]


def test_nba_rejects_changed_schema():
    with pytest.raises(ValueError):
        nba.normalize(pd.DataFrame({"PLAYER_ID": [1]}), "2025-26", "Regular Season")
