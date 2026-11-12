import pytest

from matchup import track, upset


def test_win_pct_blends_early_season_records():
    assert upset.win_pct(0, 0) == pytest.approx(0.5)
    assert upset.win_pct(2, 0) == pytest.approx(7 / 12)                 # 2-0 isn't treated as unbeatable
    assert upset.win_pct(60, 22) == pytest.approx(65 / 92)              # full season: close to the real 73%


def test_log5_and_home_court():
    assert upset.log5(0.5, 0.5) == pytest.approx(0.5)
    assert upset.log5(0.6, 0.5) == pytest.approx(0.6)                   # vs an average team = own strength
    assert upset.log5(0.7, 0.3) == pytest.approx(0.49 / 0.58)
    assert upset.on_paper((5, 5), (5, 5), home=None) == pytest.approx(0.5)
    assert upset.on_paper((5, 5), (5, 5), home="a") == pytest.approx(upset.NBA_HOME_WIN_RATE)
    assert upset.on_paper((5, 5), (5, 5), home="b") == pytest.approx(1 - upset.NBA_HOME_WIN_RATE)
    p = upset.on_paper((4, 9), (9, 4), home="b")                        # bad road team at a good team
    assert 0.2 < p < 0.4


def test_upset_check_picks_the_underdog_and_respects_the_threshold():
    c = upset.check("CHA", "BOS", paper_a=0.28, model_a=0.41)
    assert (c.underdog, c.favorite) == ("CHA", "BOS")
    assert c.edge == pytest.approx(0.13) and c.flagged
    same = upset.check("BOS", "CHA", paper_a=0.72, model_a=0.59)        # team order doesn't matter
    assert (same.underdog, round(same.edge, 9)) == ("CHA", round(c.edge, 9))
    assert not upset.check("CHA", "BOS", 0.28, 0.31).flagged            # +3 pts: below 5
    assert upset.check("CHA", "BOS", 0.28, 0.31, threshold=0.03).flagged
    assert not upset.check("CHA", "BOS", 0.28, 0.20).flagged            # model likes the favorite even more
    with pytest.raises(ValueError):
        upset.check("A", "B", 0.5, 0.6)                                 # even on paper


def _flag(game_id, sport="NBA", paper=0.30, model=0.40):
    return {"sport": sport, "game_id": game_id, "game_date": "2026-11-12", "home": "BOS", "away": "CHA",
            "underdog": "CHA", "favorite": "BOS", "underdog_record": "4-9", "favorite_record": "9-4",
            "paper_prob": paper, "model_prob": model, "edge": model - paper, "threshold": 0.05}


def test_record_is_append_only_graded_and_compared_with_expectations(tmp_path):
    path = tmp_path / "upsets.csv.gz"
    assert track.append_flags([_flag("1"), _flag("2"), _flag("3", sport="NFL")], path) == 3
    assert track.append_flags([_flag("1", model=0.90)], path) == 0             # can't rewrite a flag later
    df = track.load(path)
    assert df.loc[df.flag_id == "NBA-1", "model_prob"].item() == pytest.approx(0.40)
    df = track.grade(df, {"NBA-1": ("CHA", 104, 108), "NBA-2": ("BOS", 112, 99), "NFL-3": (None, 20, 20)})
    assert dict(zip(df.flag_id, df.result)) == {"NBA-1": "upset", "NBA-2": "no upset", "NFL-3": "void"}
    s = track.summary(df).set_index("sport")
    assert s.loc["NBA", "settled"] == 2 and s.loc["NBA", "upsets"] == 1
    assert s.loc["NBA", "upset_rate"] == 0.5
    assert s.loc["NBA", "expected_on_paper"] == pytest.approx(0.30)
    assert s.loc["NBA", "expected_by_model"] == pytest.approx(0.40)
    assert s.loc["NFL", "settled"] == 0 and s.loc["All", "flags"] == 3
    assert "roi" not in s.columns and "units" not in s.columns                 # a scoreboard, not a P&L
