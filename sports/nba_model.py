"""NBA win-probability model: game-level dataset, training and honest evaluation.

Every game becomes one row "team A vs team B" built from the two teams' PREGAME features
(see sports/nba_matchup.py; no feature uses later games). Each game is also added with the teams
swapped, so the model has no bias toward whichever team is listed first, and predictions are
averaged over both orientations so P(A) + P(B) = 1 exactly.

Evaluation is rolling: to score a season, train only on the seasons before it.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from core.config import DATA_DIR
from matchup import upset
from sports import nba_matchup as m

NET_SHRINK_GAMES = 10       # season net rating is noisy early: shrink it by gp / (gp + 10)

BASE_FEATURES = ["home", "elo_d", "roster_gs_d", "roster_pm_d", "net_d", "l10_net_d", "rest_d", "b2b_a", "b2b_b",
                 "last6_d", "missing_d"]

PAIR_COLS = ["game_id", "season", "date", "team", "venue", "won", "gp", "s_wins", "s_losses", "s_net", "l10_net",
             "rest_days", "b2b", "games_last6", "missing_min_share", "elo", "roster_gs36", "roster_pm48"]


def game_rows(f: pd.DataFrame) -> pd.DataFrame:
    """One row per game from team A's side, plus the swapped copy. Columns starting with 'x_' in `f`
    (Stat Lab candidates) are carried through as A-minus-B differences named '<col>_d'."""
    extra = [c for c in f.columns if c.startswith("x_")]
    g = f[PAIR_COLS + extra]
    pairs = g.merge(g, on=["game_id", "season", "date"], suffixes=("_a", "_b"))
    pairs = pairs[pairs["team_a"] != pairs["team_b"]].reset_index(drop=True)

    def shrunk(side):
        gp = pairs[f"gp_{side}"]
        return pairs[f"s_net_{side}"].fillna(0) * gp / (gp + NET_SHRINK_GAMES)

    out = pd.DataFrame({
        "game_id": pairs["game_id"], "season": pairs["season"], "date": pairs["date"],
        "team_a": pairs["team_a"], "team_b": pairs["team_b"], "won_a": pairs["won_a"],
        "home": pairs["venue_a"],                                        # +1 A at home, -1 away, 0 neutral
        "elo_d": (pairs["elo_a"] - pairs["elo_b"]) / 100,
        "roster_gs_d": pairs["roster_gs36_a"] - pairs["roster_gs36_b"],
        "roster_pm_d": pairs["roster_pm48_a"] - pairs["roster_pm48_b"],
        "net_d": shrunk("a") - shrunk("b"),
        "l10_net_d": pairs["l10_net_a"].fillna(0) - pairs["l10_net_b"].fillna(0),
        "rest_d": pairs["rest_days_a"] - pairs["rest_days_b"],
        "b2b_a": pairs["b2b_a"], "b2b_b": pairs["b2b_b"],
        "last6_d": pairs["games_last6_a"] - pairs["games_last6_b"],
        "missing_d": pairs["missing_min_share_a"] - pairs["missing_min_share_b"],
        "paper_a": [upset.on_paper((wa, la), (wb, lb), {1: "a", -1: "b"}.get(h)) for wa, la, wb, lb, h in
                    zip(pairs["s_wins_a"], pairs["s_losses_a"], pairs["s_wins_b"], pairs["s_losses_b"],
                        pairs["venue_a"])],
        "elo_raw_a": 1 / (1 + 10 ** (-(pairs["elo_a"] - pairs["elo_b"] + m.ELO_HOME * pairs["venue_a"]) / 400)),
    })
    for c in extra:
        out[f"{c}_d"] = pairs[f"{c}_a"] - pairs[f"{c}_b"]
    return out.dropna(subset=["roster_gs_d", "roster_pm_d"]).reset_index(drop=True)


def make_model(kind: str):
    """Training only (scikit-learn is a dev/refresh dependency; the app predicts with plain math)."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if kind == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
    if kind == "boosting":
        return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, l2_regularization=1.0,
                                              min_samples_leaf=80, random_state=0)
    raise ValueError(kind)


def predict_symmetric(model, rows: pd.DataFrame, features: list[str]) -> np.ndarray:
    """P(A wins), averaged with 1 - P(B wins) from the swapped row, so the two sides sum to 1."""
    p = model.predict_proba(rows[features])[:, 1]
    lookup = dict(zip(rows["game_id"] + "|" + rows["team_a"], p))
    other = np.array([lookup.get(k, np.nan) for k in rows["game_id"] + "|" + rows["team_b"]])
    return np.where(np.isnan(other), p, (p + 1 - other) / 2)


def evaluate(rows: pd.DataFrame, features: list[str], kind: str, test_seasons: list[str]) -> pd.DataFrame:
    """Rolling evaluation: for each test season, train on all earlier seasons only. One row per game
    (team A = alphabetically first team) with the predicted P(A) and the result."""
    out = []
    for season in test_seasons:
        train, test = rows[rows["season"] < season], rows[rows["season"] == season]
        model = make_model(kind).fit(train[features], train["won_a"])
        t = test.assign(p=predict_symmetric(model, test, features))
        out.append(t[t["team_a"] < t["team_b"]])
    return pd.concat(out, ignore_index=True)


def scores(pred: pd.DataFrame, col: str = "p") -> dict:
    from sklearn.metrics import brier_score_loss, log_loss

    y, p = pred["won_a"].to_numpy(), np.clip(pred[col].to_numpy(), 1e-6, 1 - 1e-6)
    return {"log_loss": log_loss(y, p, labels=[0, 1]), "brier": brier_score_loss(y, p),
            "accuracy": float(((p > 0.5) == y).mean()), "games": len(y)}


def calibration_table(pred: pd.DataFrame, col: str = "p", bins=(0, .2, .3, .4, .5, .6, .7, .8, 1)) -> pd.DataFrame:
    """Predicted vs actual win rate by probability bucket (from the A side of each game)."""
    b = pd.cut(pred[col], bins, include_lowest=True)
    return pred.groupby(b, observed=True).agg(predicted=(col, "mean"), actual=("won_a", "mean"),
                                              games=("won_a", "size"))


# ---------------------------------------------------------------- final model: train, save, predict

MODEL_PATH = DATA_DIR / "models" / "nba_logit.json"


def train_final(rows: pd.DataFrame, features: list[str] = BASE_FEATURES, seasons: list[str] | None = None) -> dict:
    """Fit the logistic model on the given (completed) seasons and return it as plain numbers."""
    train = rows if seasons is None else rows[rows["season"].isin(seasons)]
    pipe = make_model("logistic").fit(train[features], train["won_a"])
    scaler, lr = pipe.named_steps["standardscaler"], pipe.named_steps["logisticregression"]
    return {"features": list(features), "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
            "coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0]),
            "train_seasons": sorted(train["season"].unique().tolist()), "train_games": int(train["game_id"].nunique())}


def save_model(model: dict, path: Path = MODEL_PATH) -> None:
    from core.storage import atomic_write_json
    atomic_write_json(model, path)


def load_model(path: Path = MODEL_PATH) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def _raw_prob(model: dict, x: pd.DataFrame) -> np.ndarray:
    z = (x[model["features"]].to_numpy(float) - np.array(model["mean"])) / np.array(model["scale"])
    return 1 / (1 + np.exp(-(z @ np.array(model["coef"]) + model["intercept"])))


def predict_pair(model: dict, rows: pd.DataFrame) -> np.ndarray:
    """Symmetric P(A wins) for rows that include both orientations of each game (as game_rows makes)."""
    p = _raw_prob(model, rows)
    lookup = dict(zip(rows["game_id"] + "|" + rows["team_a"], p))
    other = np.array([lookup.get(k, np.nan) for k in rows["game_id"] + "|" + rows["team_b"]])
    return np.where(np.isnan(other), p, (p + 1 - other) / 2)


def contributions(model: dict, row: pd.Series) -> dict[str, float]:
    """How much each feature pushed team A's log-odds up or down (for the "why" on the page)."""
    z = (row[model["features"]].to_numpy(float) - np.array(model["mean"])) / np.array(model["scale"])
    return dict(zip(model["features"], (z * np.array(model["coef"])).tolist()))


def matchup_rows(state: pd.DataFrame, team_games_df: pd.DataFrame, a: str, b: str, home: str | None,
                 game_date) -> pd.DataFrame:
    """Build the model rows for an upcoming game exactly like training rows: two pregame team rows
    run through game_rows (both orientations). `state` comes from nba_matchup.current_state."""
    gid = "UPCOMING"
    recs = []
    for team in (a, b):
        s = state.loc[team]
        sched = m.schedule_for(team_games_df, team, game_date)
        venue = 0 if home is None else (1 if home == team else -1)
        recs.append({"game_id": gid, "season": s["season"], "date": pd.Timestamp(game_date), "team": team,
                     "venue": venue, "won": 0, **{c: s[c] for c in PAIR_COLS
                                                  if c in s.index and c not in ("team", "season", "date")},
                     **sched})
    return game_rows(pd.DataFrame(recs))


def predict_matchup(model: dict, state: pd.DataFrame, team_games_df: pd.DataFrame, a: str, b: str,
                    home: str | None, game_date):
    """Prediction for team A vs team B (from matchup.base), with each feature's contribution."""
    from matchup.base import Prediction

    rows = matchup_rows(state, team_games_df, a, b, home, game_date)
    p = predict_pair(model, rows)
    i = int(np.flatnonzero(rows["team_a"].to_numpy() == a)[0])
    return Prediction(a, b, float(p[i]), drivers=contributions(model, rows.iloc[i]))
