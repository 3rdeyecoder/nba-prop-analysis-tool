"""Player Projections: no future data, live rows == training rows, locking, grading, the page."""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from matchup import nba_live
from matchup import projections_live as pl
from sports import nba_matchup as m
from sports import nba_projections as pj
from tests.test_app import APP

DAY = pd.Timestamp("2025-02-05")


@pytest.fixture(scope="module")
def logs():
    lg = m.load_logs()
    if lg.empty or pj.load_model() is None:
        pytest.skip("needs stored NBA logs and a trained projection model")
    return lg[lg["season"].isin(["2023-24", "2024-25"])]


@pytest.fixture(scope="module")
def rows(logs):
    return pj.build_rows(logs)


def _design_all(r):
    return pd.concat([pj.design(r, s).add_prefix(f"{s}:") for s in pj.TARGETS], axis=1)


def test_features_use_only_earlier_games(logs, rows):
    early = logs[pd.to_datetime(logs["GAME_DATE"]) <= DAY]
    cut = pj.build_rows(early)
    a = rows[rows["date"] == DAY].set_index(["PLAYER_ID", "game_id"]).sort_index()
    b = cut[cut["date"] == DAY].set_index(["PLAYER_ID", "game_id"]).sort_index()
    assert len(a) > 100
    pd.testing.assert_frame_equal(_design_all(a), _design_all(b))


def test_tonights_rows_equal_training_rows(logs, rows):
    day = rows[rows["date"] == DAY]
    slate = day[day["home"] == 1][["game_id", "team", "opp"]].drop_duplicates("game_id") \
        .rename(columns={"team": "home", "opp": "away"})
    live = pj.live_rows(logs, slate, DAY)
    both = day.merge(live[["PLAYER_ID", "game_id"]], on=["PLAYER_ID", "game_id"])
    assert len(both) > 100
    key = ["PLAYER_ID", "game_id"]
    a = day.merge(both[key], on=key).set_index(key).sort_index()
    b = live.merge(both[key], on=key).set_index(key).sort_index()
    pd.testing.assert_frame_equal(_design_all(a), _design_all(b[a.columns.intersection(b.columns)]),
                                  check_dtype=False)


def test_projections_are_sensible(logs, rows):
    model = pj.load_model()
    r = rows[rows["date"] == DAY]
    for stat in pj.TARGETS:
        p = pj.predict(model, r, stat)
        assert np.all(np.isfinite(p)) and np.all(p >= 0)
        lo, hi = pj.predict_range(model, p, stat)
        assert np.all(lo <= p) and np.all(p <= hi)
    assert pj.predict(model, r, "MIN").max() <= 48


def test_lock_once_grade_and_void_dnp(logs, tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "PROJ_DIR", tmp_path)
    monkeypatch.setattr(pl, "RECORD_PATH", tmp_path / "rec.json")
    model = pj.load_model()
    day = DAY.date()
    lg = logs.copy()
    lg["gid"] = lg["GAME_ID"].astype(str).str.zfill(10)
    todays = lg[pd.to_datetime(lg["GAME_DATE"]) == DAY]
    games = todays.assign(home=todays["MATCHUP"].str[:3], away=todays["MATCHUP"].str[-3:])
    games = games[games["MATCHUP"].str.contains("vs.", regex=False)].drop_duplicates("gid")
    games = pd.DataFrame({"game_id": games["gid"], "home": games["home"], "away": games["away"],
                          "start_utc": pd.Timestamp(f"{day} 23:30", tz="UTC")})
    rows = pl.projection_rows(model, logs, games, day, pd.Timestamp(f"{day} 11:00", tz="UTC"))
    assert len(rows) > 100
    assert pl.lock(rows, day) == len(rows) and pl.lock(rows, day) == 0          # never rewritten
    assert pl.projection_rows(model, logs, games, day, pd.Timestamp(f"{day} 23:45", tz="UTC")).empty  # started

    assert pl.grade_day(day, logs, date(2025, 2, 7)) == len(rows)
    d = pl.load_day(day)
    assert set(d["status"]) <= {"graded", "dnp"} and (d["status"] == "dnp").any()
    box = lg.set_index(["gid", "PLAYER_ID"])
    for r in d[d["status"] == "graded"].head(30).itertuples():
        b = box.loc[(r.game_id, r.player_id)]
        assert r.act_PTS == b["PTS"] and r.act_REB == b["REB"] and r.act_AST == b["AST"]
    for r in d[d["status"] == "dnp"].itertuples():
        key = (r.game_id, r.player_id)
        assert key not in box.index or float(box.loc[key, "MIN"]) == 0
    rec = pl.record()
    assert rec["graded"] == int((d["status"] == "graded").sum())
    assert rec["stats"]["PTS"]["mae_model"] > 0


def test_page_shows_tonight_and_record(logs, tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "PROJ_DIR", tmp_path)
    monkeypatch.setattr(pl, "RECORD_PATH", tmp_path / "rec.json")
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.switch_page("views/projections.py").run()
    assert not at.exception, at.exception
    assert any("first projections" in i.value for i in at.info)

    model = pj.load_model()
    today = nba_live.today_et()
    lg = logs[pd.to_datetime(logs["GAME_DATE"]) <= DAY]
    lgd = lg[pd.to_datetime(lg["GAME_DATE"]) == DAY]
    g = lgd[lgd["MATCHUP"].str.contains("vs.", regex=False)].drop_duplicates("GAME_ID")
    games = pd.DataFrame({"game_id": g["GAME_ID"].astype(str).str.zfill(10), "home": g["MATCHUP"].str[:3],
                          "away": g["MATCHUP"].str[-3:], "start_utc": pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=5)})
    rows = pl.projection_rows(model, lg[pd.to_datetime(lg["GAME_DATE"]) < DAY], games, DAY.date(),
                              pd.Timestamp.now(tz="UTC")).assign(game_date=today.isoformat())
    pl.lock(rows, today)
    pl.save_record()
    at.run()
    assert not at.exception, at.exception
    md = " ".join(x.value for x in at.markdown)
    assert "Player Projections" in md
    assert any(h.value == "Top 5 tonight" for h in at.subheader) and "chance of" in md
    assert len(at.dataframe) >= 2                                                   # both teams of a game
    first = at.dataframe[0].value
    assert list(first.columns) == ["Player", "MIN", "PTS", "REB", "AST", "3PM", "STL", "BLK", "TOV"]
    at.text_input(key="pp_find").set_value(rows["player"].iloc[0][:6]).run()
    assert not at.exception, at.exception


def test_chances_are_calibrated_and_top5_is_sensible(logs, tmp_path, monkeypatch):
    model = pj.load_model()
    assert "calibration" in model and set(model["calibration"]) == set(pj.CHANCE_STATS)
    mu = np.array([5.0, 10.0, 20.0, 30.0])
    for s in pj.CHANCE_STATS:
        over = pj.chance(model, mu, np.full(4, 15.0), s, "over")
        assert np.all(np.diff(over) >= 0) and np.all((over >= 0) & (over <= 1))     # more projected = more likely over
        under = pj.chance(model, mu, np.full(4, 15.0), s, "under")
        assert np.all(np.diff(under) <= 0)
    rep = __import__("json").loads(pj.REPORT_PATH.read_text())["top5"]
    assert 0.65 < rep["hit_rate"] < 0.9 and abs(rep["hit_rate"] - rep["said"]) < 0.05       # honest chances

    monkeypatch.setattr(pl, "PROJ_DIR", tmp_path)
    monkeypatch.setattr(pl, "RECORD_PATH", tmp_path / "rec.json")
    day = DAY.date()
    lg = logs.copy()
    g = lg[(pd.to_datetime(lg["GAME_DATE"]) == DAY) & lg["MATCHUP"].str.contains("vs.", regex=False)].drop_duplicates("GAME_ID")
    games = pd.DataFrame({"game_id": g["GAME_ID"].astype(str).str.zfill(10), "home": g["MATCHUP"].str[:3],
                          "away": g["MATCHUP"].str[-3:], "start_utc": pd.Timestamp(f"{day} 23:30", tz="UTC")})
    rows = pl.projection_rows(model, logs, games, day, pd.Timestamp(f"{day} 11:00", tz="UTC"))
    pl.lock(rows, day)
    d = pl.load_day(day)
    top = pl.top_picks(d)
    assert len(top) == 5 and top["player_id"].is_unique
    assert top["chance"].is_monotonic_decreasing
    for p in top.itertuples():
        r = d.loc[p.i]
        assert r["returning"] == 0 and r[f"avg_{p.stat}"] >= pj.PICK_MIN_AVG[p.stat]
        assert p.chance == r[f"{p.dir}_{p.stat}"]
    pl.grade_day(day, logs, date(2025, 2, 7))
    rec = pl.save_record()
    t5 = rec["top5"]
    assert t5["nights"] == 1 and t5["picks"] + t5["voided"] == 5 and 0 <= t5["hits"] <= t5["picks"]


def test_expected_value_for_the_stat_picked_on_the_player_page():
    from core.projection_ui import expected
    r = pd.Series({**{f"p_{s}": v for s, v in zip(["PTS", "REB", "AST"], [25.0, 7.0, 5.0])},
                   **{f"avg_{s}": v for s, v in zip(["PTS", "REB", "AST"], [22.0, 8.0, 5.5])},
                   **{f"lo_{s}": v - 3 for s, v in zip(["PTS", "REB", "AST"], [25.0, 7.0, 5.0])},
                   **{f"hi_{s}": v + 3 for s, v in zip(["PTS", "REB", "AST"], [25.0, 7.0, 5.0])},
                   "over_PTS": 0.66, "under_PTS": 0.30, "status": np.nan})
    e = expected(r, "PTS", "Points")
    assert e["mu"] == 25 and e["avg"] == 22 and e["chance"] == ("above", 0.66) and e["act"] is None
    pra = expected(r, "PRA", "Pts + Reb + Ast (PRA)")
    assert pra["mu"] == 37 and pra["avg"] == 35.5 and pra["label"] == "points + rebounds + assists"
    assert pra["lo"] < 37 < pra["hi"] and (pra["hi"] - 37) > 3          # a sum is more spread out than any part
    assert expected(r, "FTM", "Free throws made") is None
    done = pd.concat([r.drop("status"), pd.Series({"status": "graded", "act_PTS": 30.0, "act_REB": 9.0,
                                                   "act_AST": 4.0})])
    graded = expected(done, "PRA", "PRA")
    assert graded["act"] == 43


def test_next_game_for_the_no_projection_note():
    from core.projection_ui import next_game
    from matchup import nba_live as nl
    sched = sorted(__import__("sports.nba", fromlist=["DATA_DIR"]).DATA_DIR.glob("nba_schedule_*.parquet"))
    if not sched:
        pytest.skip("no stored schedule")
    s = pd.read_parquet(sched[-1])
    s = s[s["game_id"].astype(str).str.startswith("002")]
    first = pd.to_datetime(s["start_utc"], utc=True).dt.tz_convert(nl.ET).dt.date.min()
    g = s.iloc[0]
    ng = next_game(g["home"], first)
    assert ng is not None and ng[0] >= first and isinstance(ng[2], (bool, np.bool_))
    assert next_game("", first) is None
