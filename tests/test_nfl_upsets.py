"""NFL Upset Watch: no future data, live numbers match training numbers, grading, and the page."""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from matchup import nba_live, nfl_live, track
from sports import nfl_matchup as fm
from sports import nfl_model as nfm
from tests.test_app import APP

CUT = pd.Timestamp("2024-11-10")       # a Sunday in the middle of a finished season


@pytest.fixture(scope="module")
def data():
    games, stats, qbs = fm.load()
    model = nfm.load_model(nfm.MODEL_PATH)
    if games.empty or model is None:
        pytest.skip("needs stored NFL games and a trained model")
    games = games[games["season"] >= 2021]
    return games, stats[stats["season"] >= 2021], qbs[qbs["season"] >= 2021], model


def test_features_use_only_earlier_games(data):
    games, stats, qbs, _ = data
    full = fm.build_features(games, stats, qbs)
    early = games[pd.to_datetime(games["gameday"]) <= CUT]
    cut = fm.build_features(early, stats[stats["game_id"].isin(early["game_id"])],
                            qbs[qbs["game_id"].isin(early["game_id"])])
    cols = ["elo", "off_epa", "def_epa", "margin_pg", "qb_pre", "s_wins", "s_losses", "gp"]
    on_day = lambda f: f[f["date"] == CUT].set_index(["game_id", "team"])[cols].sort_index()  # noqa: E731
    a, b = on_day(full), on_day(cut)
    assert len(a) >= 20
    pd.testing.assert_frame_equal(a, b)


def test_live_prediction_equals_training_row(data):
    """A game predicted from the snapshot taken that morning = the same game in the training table."""
    games, stats, qbs, model = data
    f = fm.build_features(games, stats, qbs)
    rows = nfm.game_rows(f)
    state = fm.current_state(games, stats, qbs, CUT)
    g = games[(pd.to_datetime(games["gameday"]) == CUT) & (games["location"] == "Home")].iloc[0]
    call = nfl_live.predict(model, state, games, g.home_team, g.away_team, g.home_team, CUT)
    r = rows[(rows["game_id"] == g.game_id) & (rows["team_a"] == g.home_team)].iloc[0]
    assert call.p_a == pytest.approx(float(nfm.predict_pair(model, rows[rows["game_id"] == g.game_id])[0]
                                           if rows[rows["game_id"] == g.game_id]["team_a"].iloc[0] == g.home_team
                                           else 1 - nfm.predict_pair(model, rows[rows["game_id"] == g.game_id])[0]),
                                     abs=1e-9)
    assert call.paper_a == pytest.approx(r["paper_a"])


def test_model_beats_on_paper_and_is_symmetric(data):
    games, stats, qbs, model = data
    rows = nfm.game_rows(fm.build_features(games, stats, qbs))
    p = nfm.predict_pair(model, rows)
    lookup = dict(zip(rows["game_id"] + rows["team_a"], p))
    other = np.array([lookup[k] for k in rows["game_id"] + rows["team_b"]])
    assert np.allclose(p + other, 1)
    assert model["held_out"]["log_loss"] < 0.64


def test_only_todays_games_locked_and_graded(data, tmp_path, monkeypatch):
    games, stats, qbs, model = data
    monkeypatch.setattr(track, "UPSET_DIR", tmp_path)
    monkeypatch.setattr(nfl_live, "QB_RATINGS_PATH", tmp_path / "nfl_qbs.parquet")
    day = CUT.date()
    state = nfl_live.build_snapshot(games, stats, qbs, day).set_index("team", drop=False)
    before = pd.Timestamp(f"{day} 08:00", tz="America/New_York").tz_convert("UTC")
    rows = nfl_live.prediction_rows(model, state, games, day, before)
    todays = games[pd.to_datetime(games["gameday"]) == CUT]
    assert len(rows) == len(todays) and {r["game_date"] for r in rows} == {day.isoformat()}
    for r in rows:
        assert r["flagged"] == (r["paper_prob"] < 0.5 and r["edge"] >= 0.05 - 1e-12)
    late = pd.Timestamp(f"{day} 18:00", tz="America/New_York").tz_convert("UTC")
    assert len(nfl_live.prediction_rows(model, state, games, day, late)) < len(rows)      # started games skipped

    path = track.log_path("NFL")
    track.append(rows, path)
    log = track.load(path)
    graded = track.grade(log, nfl_live.results_from_games(log, games, date(2024, 11, 12)))
    assert graded["result"].notna().all()
    g = games.set_index("game_id")
    for r in graded.itertuples():
        hs, as_ = g.loc[r.game_id, "home_score"], g.loc[r.game_id, "away_score"]
        assert r.winner == (r.home if hs > as_ else r.away)


def test_tie_is_void_and_relocated_teams_share_history():
    g = pd.DataFrame({"game_id": ["x"], "home_score": [20], "away_score": [20]})
    log = pd.DataFrame({"flag_id": ["NFL-x"], "game_id": ["x"], "home": ["A"], "away": ["B"], "game_date": ["2024-01-01"],
                        "result": [None]})
    assert nfl_live.results_from_games(log, g, date(2024, 1, 2)) == {"NFL-x": (None, 20, 20)}
    assert list(fm._fix(pd.Series(["OAK", "SD", "STL", "KC"]))) == ["LV", "LAC", "LA", "KC"]


def test_nfl_page(data, tmp_path, monkeypatch):
    games, stats, qbs, model = data
    monkeypatch.setattr(track, "UPSET_DIR", tmp_path)
    monkeypatch.setattr(nfl_live, "STATE_PATH", tmp_path / "nfl_state.parquet")
    monkeypatch.setattr(nfl_live, "QB_RATINGS_PATH", tmp_path / "nfl_qbs.parquet")
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.switch_page("views/upsets.py").run()
    at.segmented_control(key="uw_sport").set_value("NFL").run()
    assert not at.exception, at.exception
    assert any("NFL Upset Watch isn't set up yet" in i.value for i in at.info)

    full_games = fm.load()[0]
    nfl_live.save_snapshot(nfl_live.build_snapshot(full_games, *fm.load()[1:], nba_live.today_et()))
    at.run()
    assert not at.exception, at.exception
    at.selectbox(key="uw_a_NFL").set_value("KC").run()
    at.selectbox(key="uw_b_NFL").set_value("BUF").run()
    assert not at.exception, at.exception
    md = " ".join(x.value for x in at.markdown)
    assert "uw-bar" in md and "Why the model leans this way" in md and "Quarterback" in md
    assert any("nflverse" in c.value for c in at.caption)
