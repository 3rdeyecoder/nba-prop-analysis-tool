import numpy as np
import pandas as pd
import pytest

from sports import nba_matchup as m
from sports import nba_model as nm


@pytest.fixture(scope="module")
def data():
    logs = m.load_logs()
    if logs.empty:
        pytest.skip("no stored NBA data")
    logs = logs[logs["season"].isin(["2023-24", "2024-25", "2025-26"])]
    f = m.build_features(logs)
    rows = nm.game_rows(f)
    return logs, f, rows


def test_upcoming_game_features_match_training_features(data):
    """Predicting a game 'live' from current_state must use exactly the features the model trained on."""
    logs, f, rows = data
    day = pd.Timestamp("2026-01-15")
    state = m.current_state(logs, day)
    g = m.team_games(logs)
    real = rows[(rows["date"] == day) & (rows["home"] == 1)]
    assert len(real) >= 3
    for _, r in real.iterrows():
        live = nm.matchup_rows(state, g, r["team_a"], r["team_b"], r["team_a"], day)
        live = live[live["team_a"] == r["team_a"]].iloc[0]
        for c in nm.BASE_FEATURES + ["paper_a"]:
            assert live[c] == pytest.approx(r[c], rel=1e-9, abs=1e-9), (r["team_a"], r["team_b"], c)


def test_saved_model_matches_sklearn_and_is_symmetric(data):
    _, _, rows = data
    model = nm.train_final(rows, seasons=["2023-24", "2024-25"])
    pipe = nm.make_model("logistic").fit(rows[rows.season < "2025-26"][nm.BASE_FEATURES],
                                         rows[rows.season < "2025-26"]["won_a"])
    test = rows[rows.season == "2025-26"]
    assert np.allclose(nm._raw_prob(model, test), pipe.predict_proba(test[nm.BASE_FEATURES])[:, 1])
    p = pd.Series(nm.predict_pair(model, test), index=test.index)
    key = test["game_id"] + "|" + test["team_a"]
    swapped = dict(zip(key, p))
    other = (test["game_id"] + "|" + test["team_b"]).map(swapped)
    assert np.allclose(p + other, 1.0)                                      # P(A) + P(B) = 1 for every game


def test_predict_matchup_home_court_and_order(data):
    logs, f, rows = data
    model = nm.train_final(rows, seasons=["2023-24", "2024-25"])
    day = pd.Timestamp("2026-01-15")
    state, g = m.current_state(logs, day), m.team_games(logs)
    at_home = nm.predict_matchup(model, state, g, "OKC", "WAS", "OKC", day)
    on_road = nm.predict_matchup(model, state, g, "OKC", "WAS", "WAS", day)
    neutral = nm.predict_matchup(model, state, g, "OKC", "WAS", None, day)
    assert at_home.p_a > neutral.p_a > on_road.p_a                       # home court helps
    flipped = nm.predict_matchup(model, state, g, "WAS", "OKC", "OKC", day)
    assert flipped.p_a == pytest.approx(1 - at_home.p_a)                  # team order doesn't matter
    assert at_home.p_a > 0.5 and set(at_home.drivers) == set(model["features"])


def test_training_uses_only_the_seasons_it_is_given(data):
    _, _, rows = data
    model = nm.train_final(rows, seasons=["2023-24"])
    assert model["train_seasons"] == ["2023-24"]
    assert model["train_games"] == rows[rows.season == "2023-24"]["game_id"].nunique()
