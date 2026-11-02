from datetime import date, timedelta

import pandas as pd
import pytest

from sports import callit, nba


@pytest.fixture(scope="module")
def data():
    files = [(s, p) for s, t, p in nba.available_files() if t == "Regular Season"]
    if not files:
        pytest.skip("no stored NBA data")
    df = pd.concat([nba.load_file(p, s, "Regular Season") for s, p in files], ignore_index=True)
    return df, callit.build_pool(df)


def test_same_day_same_puzzle_new_day_new_puzzle(data):
    _, pool = data
    a = callit.daily_rounds(pool, date(2026, 11, 2))
    b = callit.daily_rounds(pool, date(2026, 11, 2))
    c = callit.daily_rounds(pool, date(2026, 11, 3))
    key = lambda rs: [(r["player_id"], r["game_id"], r["stat"]) for r in rs]  # noqa: E731
    assert key(a) == key(b) and key(a) != key(c)
    assert len(a) == 5 and len({r["player_id"] for r in a}) == 5               # 5 different players
    assert [r["stat"] for r in a] == callit.ROUND_STATS


def test_rounds_show_only_earlier_games_and_never_push(data):
    df, pool = data
    for day in [date(2026, 11, 2) + timedelta(days=i) for i in range(30)]:
        for r in callit.daily_rounds(pool, day):
            prior = callit.prior_games(df, r)
            assert len(prior) == callit.PRIOR_N
            assert (prior["game_date"] < r["game_date"]).all() and (prior["season"] == r["season"]).all()
            assert r["line"] % 1 == 0.5 and r["actual"] != r["line"]                # no ties possible
            assert r["line"] == callit.fair_line(prior[r["stat"]].median())         # line = shown median
            assert r["game_date"] < pd.Timestamp(day - timedelta(days=callit.CUTOFF_DAYS))


def test_puzzles_are_balanced_over_time(data):
    _, pool = data
    answers = [r["answer"] for i in range(120) for r in callit.daily_rounds(pool, date(2026, 11, 2) + timedelta(days=i))]
    assert 0.40 <= answers.count("Over") / len(answers) <= 0.60


def test_fair_line_and_share_text():
    assert callit.fair_line(22.0) == 21.5 and callit.fair_line(22.5) == 22.5
    assert callit.puzzle_number(date(2026, 11, 1)) == 1 and callit.puzzle_number(date(2026, 11, 2)) == 2
    assert callit.puzzle_number(date(2026, 10, 1)) == 1        # never 0 or negative
    text = callit.share_text(14, [True, True, False, True, True], "https://x.streamlit.app/callit")
    assert text.splitlines() == ["Playmaker Lab · Call It #14 — 4/5", "🟩🟩🟥🟩🟩", "https://x.streamlit.app/callit"]
