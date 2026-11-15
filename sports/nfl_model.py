"""NFL win-probability model. Same approach as the NBA one (sports/nba_model.py): one row per game
from each side, logistic regression on A-minus-B pregame numbers, predictions averaged over both
sides so the two chances add up to 100%, and rolling evaluation (each season scored by a model
trained only on earlier seasons). The training, scoring and plain-numbers prediction helpers are
shared with the NBA model.
"""
from __future__ import annotations

import pandas as pd

from core.config import DATA_DIR
from matchup import upset
from sports import nfl_matchup as fm
from sports.nba_model import (calibration_table, contributions, evaluate, load_model, make_model,
                              predict_pair, save_model, scores, train_final)

__all__ = ["calibration_table", "contributions", "evaluate", "load_model", "make_model", "predict_pair",
           "save_model", "scores", "train_final", "game_rows", "matchup_rows", "paper", "BASE_FEATURES"]

FIRST_SEASON = 2012          # 2010-11 only warm up the ratings
MODEL_PATH = DATA_DIR / "models" / "nfl_logit.json"
REPORT_PATH = DATA_DIR / "models" / "nfl_report.json"

BASE_FEATURES = ["home", "elo_d", "off_d", "def_d", "margin_d", "qb_d", "rest_d"]

PAIR_COLS = ["game_id", "season", "date", "team", "venue", "won", "played", "s_wins", "s_losses", "s_ties", "elo",
             "off_epa", "def_epa", "margin_pg", "qb_pre", "rest"]


def game_rows(f: pd.DataFrame, played_only: bool = True) -> pd.DataFrame:
    g = f[PAIR_COLS + [c for c in f.columns if c.startswith("x_")]]
    if played_only:
        g = g[g["played"] & (g["season"] >= FIRST_SEASON)]
    pairs = g.merge(g, on=["game_id", "season", "date"], suffixes=("_a", "_b"))
    pairs = pairs[pairs["team_a"] != pairs["team_b"]].reset_index(drop=True)
    out = pd.DataFrame({
        "game_id": pairs["game_id"], "season": pairs["season"], "date": pairs["date"],
        "team_a": pairs["team_a"], "team_b": pairs["team_b"], "won_a": pairs["won_a"],
        "home": pairs["venue_a"],
        "elo_d": (pairs["elo_a"] - pairs["elo_b"]) / 100,
        "off_d": (pairs["off_epa_a"] - pairs["off_epa_b"]) * 10,            # tenths of a point per play
        "def_d": (pairs["def_epa_b"] - pairs["def_epa_a"]) * 10,            # positive = A's defense is better
        "margin_d": pairs["margin_pg_a"] - pairs["margin_pg_b"],
        "qb_d": (pairs["qb_pre_a"] - pairs["qb_pre_b"]) * 10,
        "rest_d": pairs["rest_a"].fillna(7) - pairs["rest_b"].fillna(7),
        "paper_a": [paper(wa, la, ta, wb, lb, tb, h) for wa, la, ta, wb, lb, tb, h in
                    zip(pairs["s_wins_a"], pairs["s_losses_a"], pairs["s_ties_a"], pairs["s_wins_b"],
                        pairs["s_losses_b"], pairs["s_ties_b"], pairs["venue_a"])],
        "elo_raw_a": 1 / (1 + 10 ** (-(pairs["elo_a"] - pairs["elo_b"] + fm.ELO_HOME * pairs["venue_a"]) / 400)),
    })
    for c in [c for c in g.columns if c.startswith("x_")]:
        out[f"{c}_d"] = pairs[f"{c}_a"] - pairs[f"{c}_b"]
    out["won_a"] = out["won_a"].round()           # ties (rare) count as losses for both orientations' targets
    if played_only:
        out = out[pairs["won_a"] != 0.5]           # drop the handful of tied games from training/scoring
    return out.reset_index(drop=True)


def paper(wa, la, ta, wb, lb, tb, venue_a) -> float:
    """On-paper chance A wins: records (ties as half a win) + home field."""
    return upset.on_paper((wa + ta / 2, la + ta / 2), (wb + tb / 2, lb + tb / 2), {1: "a", -1: "b"}.get(venue_a),
                          home_win_rate=upset.NFL_HOME_WIN_RATE, prior_games=upset.NFL_PRIOR_GAMES)


def matchup_rows(state: pd.DataFrame, a: str, b: str, home: str | None, rest_a, rest_b) -> pd.DataFrame:
    """Model rows for an upcoming game, built by the same game_rows code as training."""
    recs = []
    for team, rest in ((a, rest_a), (b, rest_b)):
        s = state.loc[team]
        recs.append({**{c: s[c] for c in PAIR_COLS if c in s.index},
                     "game_id": "UPCOMING", "date": pd.Timestamp(0), "team": team, "won": 0, "played": True,
                     "venue": 0 if home is None else (1 if home == team else -1),
                     "rest": rest if rest is not None else 7})
    return game_rows(pd.DataFrame(recs), played_only=False)
