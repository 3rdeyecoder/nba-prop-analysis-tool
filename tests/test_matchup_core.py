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


def _row(game_id, sport="NBA", paper=0.30, model=0.40, flagged=True, home_model=0.60, home_paper=0.70):
    return {"sport": sport, "game_id": game_id, "game_date": "2026-11-12", "start_utc": "2026-11-13T00:30:00+00:00",
            "home": "BOS", "away": "CHA", "underdog": "CHA", "favorite": "BOS", "underdog_record": "4-9",
            "favorite_record": "9-4", "paper_prob": paper, "model_prob": model, "home_model_prob": home_model,
            "home_paper_prob": home_paper, "edge": model - paper, "threshold": 0.05, "flagged": flagged}


def test_record_is_append_only_graded_and_compared_with_expectations(tmp_path):
    path = tmp_path / "upsets.csv.gz"
    assert track.append([_row("1"), _row("2"), _row("3", sport="NFL"), _row("4", flagged=False)], path) == 4
    assert track.append([_row("1", model=0.90)], path) == 0                     # can't rewrite a prediction later
    df = track.load(path)
    assert df.loc[df.flag_id == "NBA-1", "model_prob"].item() == pytest.approx(0.40)
    assert df["flagged"].tolist() == [True, True, True, False]                  # booleans survive the file
    df = track.grade(df, {"NBA-1": ("CHA", 104, 108), "NBA-2": ("BOS", 112, 99), "NFL-3": (None, 20, 20),
                          "NBA-4": ("BOS", 110, 90)})
    assert dict(zip(df.flag_id, df.result)) == {"NBA-1": "upset", "NBA-2": "no upset", "NFL-3": "void",
                                                "NBA-4": "no upset"}
    s = track.summary(df).set_index("sport")
    assert s.loc["NBA", "flags"] == 2 and s.loc["NBA", "settled"] == 2      # unflagged game not in the record
    assert s.loc["NBA", "upsets"] == 1 and s.loc["NBA", "upset_rate"] == 0.5
    assert s.loc["NBA", "expected_on_paper"] == pytest.approx(0.30)
    assert s.loc["NBA", "expected_by_model"] == pytest.approx(0.40)
    assert s.loc["NBA", "games_graded"] == 3                                  # every graded game counts here
    assert s.loc["NBA", "model_correct"] == 2 and s.loc["NBA", "paper_correct"] == 2  # both picked BOS
    assert s.loc["NFL", "settled"] == 0 and s.loc["All", "flags"] == 3
    assert "roi" not in s.columns and "units" not in s.columns                 # a scoreboard, not a P&L


def test_empty_log_works_everywhere(tmp_path):
    df = track.load(tmp_path / "none.csv.gz")
    assert df.empty and df["flagged"].dtype == bool
    assert df[df["flagged"]].empty
    s = track.summary(df)
    assert s.loc[0, "flags"] == 0 and s.loc[0, "games_graded"] == 0
