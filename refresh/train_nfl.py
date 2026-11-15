"""Train the NFL Upset Watch model and write its report.

    python -m refresh.train_nfl

Writes data/models/nfl_logit.json (plain numbers) and data/models/nfl_report.json (held-out
results, calibration, Upset Watch backtest). Trains on completed seasons only. Held-out results are
rolling: each test season is scored by a model trained only on the seasons before it.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from core.storage import atomic_write_json, utc_now_iso
from refresh.common import setup_logging
from refresh.train_nba import THRESHOLDS
from sports import nfl_matchup as fm
from sports import nfl_model as nfm

FIRST_TEST_SEASON = 2016


def completed_seasons(rows: pd.DataFrame) -> list[int]:
    """Seasons whose Super Bowl has been played (at least 260 games)."""
    counts = rows.groupby("season")["game_id"].nunique()
    return sorted(int(s) for s in counts[counts >= 260].index)


def upset_backtest(pred: pd.DataFrame) -> list[dict]:
    d = pred[np.abs(pred["paper_a"] - 0.5) > 1e-9]
    a_dog = (d["paper_a"] < 0.5).to_numpy()
    paper = np.where(a_dog, d["paper_a"], 1 - d["paper_a"])
    model = np.where(a_dog, d["p"], 1 - d["p"])
    upset = np.where(a_dog, d["won_a"], 1 - d["won_a"])
    weeks = d.assign(w=d["date"].dt.to_period("W")).groupby("season")["w"].nunique().sum()
    seasons = d["season"].to_numpy()
    out = []
    for t in THRESHOLDS:
        k = (model - paper) >= t
        beat = sum(upset[k & (seasons == s)].mean() > paper[k & (seasons == s)].mean() for s in np.unique(seasons))
        alert, live = k & (model >= 0.5), k & (model < 0.5)
        out.append({"threshold": t, "flags": int(k.sum()), "per_night": float(k.sum() / weeks),
                    "upset_rate": float(upset[k].mean()), "expected_on_paper": float(paper[k].mean()),
                    "expected_by_model": float(model[k].mean()), "seasons_beating_paper": int(beat),
                    "seasons": int(len(np.unique(seasons))),
                    "alerts": int(alert.sum()), "alert_upset_rate": float(upset[alert].mean()) if alert.any() else None,
                    "live": int(live.sum()), "live_upset_rate": float(upset[live].mean()) if live.any() else None,
                    "live_expected_on_paper": float(paper[live].mean()) if live.any() else None})
    return out


def main(argv: list[str] | None = None) -> int:
    log = setup_logging()
    games, stats, qbs = fm.load()
    if games.empty:
        log.error("no stored NFL games; run python -m refresh.nfl_games --seasons 2010 ... 2026")
        return 1
    rows = nfm.game_rows(fm.build_features(games, stats, qbs))
    done = completed_seasons(rows)
    tests = [s for s in done if s >= FIRST_TEST_SEASON]
    if not tests:
        log.error("not enough completed seasons: %s", done)
        return 1
    log.info("games: %d | completed seasons: %s..%s | held-out: %s..%s", rows["game_id"].nunique(),
             done[0], done[-1], tests[0], tests[-1])

    pred = nfm.evaluate(rows, nfm.BASE_FEATURES, "logistic", tests)
    boost = nfm.evaluate(rows, nfm.BASE_FEATURES, "boosting", tests)
    report = {
        "created_utc": utc_now_iso(), "held_out_seasons": [str(s) for s in tests], "unit": "week",
        "scores": {"model": nfm.scores(pred), "gradient_boosting": nfm.scores(boost),
                   "on_paper": nfm.scores(pred, "paper_a"), "raw_elo": nfm.scores(pred, "elo_raw_a")},
        "calibration": nfm.calibration_table(pred).reset_index(drop=True).to_dict("records"),
        "upset_watch": upset_backtest(pred),
    }
    model = nfm.train_final(rows, nfm.BASE_FEATURES, seasons=done)
    model.update({"created_utc": utc_now_iso(), "held_out": report["scores"]["model"],
                  "train_seasons": [str(s) for s in model["train_seasons"]]})
    nfm.save_model(model, nfm.MODEL_PATH)
    atomic_write_json(report, nfm.REPORT_PATH)
    s = report["scores"]
    log.info("held-out log loss: model %.4f | on paper %.4f | raw Elo %.4f | accuracy %.1f%%",
             s["model"]["log_loss"], s["on_paper"]["log_loss"], s["raw_elo"]["log_loss"], 100 * s["model"]["accuracy"])
    log.info("saved %s and %s (trained on %d games)", nfm.MODEL_PATH.name, nfm.REPORT_PATH.name, model["train_games"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
