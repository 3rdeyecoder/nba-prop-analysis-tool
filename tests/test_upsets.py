from datetime import date

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from matchup import nba_live, track, upset
from sports import nba_matchup as m
from sports import nba_model as nm
from tests.test_app import APP

DAY = date(2026, 1, 15)


@pytest.fixture(scope="module")
def setup():
    logs = m.load_logs()
    model = nm.load_model()
    if logs.empty or model is None:
        pytest.skip("needs stored NBA data and a trained model")
    logs = logs[logs["season"].isin(["2023-24", "2024-25", "2025-26"])]
    state, tg = nba_live.build_snapshot(logs, DAY)
    real = m.team_games(logs)
    real = real[(real["date"] == pd.Timestamp(DAY)) & (real["venue"] == 1)]
    sched = pd.DataFrame({"game_id": real["game_id"].values, "home": real["team"].values, "away": real["opp"].values,
                          "start_utc": pd.Timestamp(f"{DAY} 19:00", tz="America/New_York").tz_convert("UTC")})
    return logs, model, state.set_index("team", drop=False), tg, sched


def test_snapshot_uses_only_earlier_games(setup):
    logs, _, state, tg, _ = setup
    assert len(state) == 30 and (tg["date"] < pd.Timestamp(DAY)).all()
    assert pd.Timestamp(state["data_through"].iloc[0]) < pd.Timestamp(DAY)


def test_predictions_only_before_tipoff_and_never_rewritten(setup, tmp_path):
    _, model, state, tg, sched = setup
    before = pd.Timestamp(f"{DAY} 08:00", tz="America/New_York").tz_convert("UTC")
    after = pd.Timestamp(f"{DAY} 23:00", tz="America/New_York").tz_convert("UTC")
    assert nba_live.prediction_rows(model, state, tg, sched, DAY, after) == []         # games already started
    rows = nba_live.prediction_rows(model, state, tg, sched, DAY, before)
    assert len(rows) == len(sched) >= 3
    for r in rows:
        assert r["home_model_prob"] == pytest.approx(
            nba_live.predict(model, state, tg, r["home"], r["away"], r["home"], DAY).p_a)
        assert r["flagged"] == (r["edge"] >= 0.05 - 1e-12 and r["paper_prob"] < 0.5)
    path = tmp_path / "log.csv.gz"
    assert track.append(rows, path) == len(rows)
    assert track.append(rows, path) == 0


def test_grading_from_the_game_logs(setup, tmp_path):
    logs, model, state, tg, sched = setup
    before = pd.Timestamp(f"{DAY} 08:00", tz="America/New_York").tz_convert("UTC")
    path = tmp_path / "log.csv.gz"
    track.append(nba_live.prediction_rows(model, state, tg, sched, DAY, before), path)
    log = track.load(path)
    res = nba_live.results_from_logs(log, logs, date(2026, 1, 16))
    graded = track.grade(log, res)
    assert graded["result"].notna().all() and graded["winner"].notna().all()
    real = m.team_games(logs).set_index(["game_id", "team"])
    for r in graded.itertuples():
        assert bool(real.loc[(r.game_id, r.home), "won"]) == (r.winner == r.home)
    # a game that never shows up is voided after a week, not counted as a miss
    ghost = log.iloc[:1].assign(game_id="0029999999", flag_id="NBA-0029999999")
    assert nba_live.results_from_logs(ghost, logs, date(2026, 1, 20)) == {}
    assert nba_live.results_from_logs(ghost, logs, date(2026, 1, 30)) == {"NBA-0029999999": (None, None, None)}


def test_reasons_are_sized_and_explained(setup):
    _, model, state, tg, _ = setup
    call = nba_live.predict(model, state, tg, "OKC", "WAS", "OKC", DAY)
    why = nba_live.reasons(call, state, tg, DAY)
    assert 1 <= len(why) <= 3 and why == sorted(why, key=lambda r: -r["points"])
    assert all(r["favors"] in ("OKC", "WAS") and r["fact"] for r in why)


def test_page_with_and_without_a_snapshot(setup, tmp_path, monkeypatch):
    logs, model, state, tg, sched = setup
    monkeypatch.setattr(track, "UPSET_DIR", tmp_path)
    monkeypatch.setattr(nba_live, "STATE_PATH", tmp_path / "nba_state.parquet")
    monkeypatch.setattr(nba_live, "GAMES_PATH", tmp_path / "nba_team_games.parquet")
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.switch_page("views/upsets.py").run()
    assert not at.exception, at.exception
    assert any("isn't set up yet" in i.value for i in at.info)                 # no snapshot: setup message

    nba_live.save_snapshot(state.reset_index(drop=True), tg)
    at.run()
    assert not at.exception, at.exception
    assert at.selectbox(key="uw_a").options and at.selectbox(key="uw_b").options
    at.selectbox(key="uw_a").set_value("OKC").run()
    at.selectbox(key="uw_b").set_value("WAS").run()
    assert not at.exception, at.exception
    md = " ".join(x.value for x in at.markdown)
    assert "uw-bar" in md and "Why the model leans this way" in md
    assert any("1-800-GAMBLER" in c.value for c in at.caption)


def test_cards_show_both_kinds_of_flags(setup, tmp_path, monkeypatch):
    """A locked-in night with one upset alert, one live underdog and one calm game."""
    logs, model, state, tg, sched = setup
    monkeypatch.setattr(track, "UPSET_DIR", tmp_path)
    monkeypatch.setattr(nba_live, "STATE_PATH", tmp_path / "nba_state.parquet")
    monkeypatch.setattr(nba_live, "GAMES_PATH", tmp_path / "nba_team_games.parquet")
    nba_live.save_snapshot(state.reset_index(drop=True), tg)
    today = nba_live.today_et().isoformat()
    teams = list(state.index)[:6]
    base = {"sport": "NBA", "game_date": today, "threshold": 0.05}
    rows = []
    for i, (home_model, home_paper) in enumerate([(0.38, 0.51), (0.70, 0.75), (0.60, 0.61)]):
        home, away = teams[2 * i], teams[2 * i + 1]
        chk = upset.check(home, away, home_paper, home_model, 0.05)
        rows.append({**base, "game_id": f"00226{i:05d}", "start_utc": f"{today}T23:{i}0:00+00:00",
                     "home": home, "away": away, "underdog": chk.underdog, "favorite": chk.favorite,
                     "paper_prob": chk.paper_prob, "model_prob": chk.model_prob, "home_model_prob": home_model,
                     "home_paper_prob": home_paper, "edge": chk.edge, "flagged": chk.flagged})
    track.append(rows, track.log_path("NBA"))
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.switch_page("views/upsets.py").run()
    assert not at.exception, at.exception
    md = " ".join(x.value for x in at.markdown)
    assert md.count("UPSET ALERT") == 1 and md.count("LIVE UNDERDOG") == 1
    assert f"Model picks {teams[1]} to win" in md
    assert f"Model still favors {teams[2]}, but gives {teams[3]} a better shot" in md
