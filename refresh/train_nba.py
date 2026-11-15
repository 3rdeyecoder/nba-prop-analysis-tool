"""Train the NBA Upset Watch model and write its report.

    python -m refresh.train_nba              # train on all completed seasons, save model + report
    python -m refresh.train_nba --no-lab     # skip the (slower) Stat Lab re-run

Writes:
  data/models/nba_logit.json    the model as plain numbers (the app needs no ML library)
  data/models/nba_report.json   held-out results, calibration, Stat Lab verdicts, Upset Watch backtest

Only completed seasons are used for training. Held-out results come from rolling evaluation:
each test season is scored by a model trained only on the seasons before it.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from core.storage import atomic_write_json, utc_now_iso
from refresh.common import setup_logging
from sports import nba_matchup as m
from sports import nba_model as nm
from sports import nba_players, nba_statlab

REPORT_PATH = nm.MODEL_PATH.with_name("nba_report.json")
THRESHOLDS = [0.03, 0.05, 0.08, 0.10, 0.15]


def completed_seasons(rows: pd.DataFrame) -> list[str]:
    """Seasons with (nearly) a full schedule played: at least 1,000 games."""
    counts = rows.groupby("season")["game_id"].nunique()
    return sorted(counts[counts >= 1000].index)


def upset_backtest(pred: pd.DataFrame) -> list[dict]:
    d = pred[np.abs(pred["paper_a"] - 0.5) > 1e-9]
    a_dog = d["paper_a"] < 0.5
    paper = np.where(a_dog, d["paper_a"], 1 - d["paper_a"])
    model = np.where(a_dog, d["p"], 1 - d["p"])
    upset = np.where(a_dog, d["won_a"], 1 - d["won_a"])
    nights = d["date"].nunique()
    out = []
    for t in THRESHOLDS:
        k = (model - paper) >= t
        seasons_beat = sum(upset[k & (d["season"] == s).to_numpy()].mean() > paper[k & (d["season"] == s).to_numpy()].mean()
                           for s in d["season"].unique())
        out.append({"threshold": t, "flags": int(k.sum()), "per_night": float(k.sum() / nights),
                    "upset_rate": float(upset[k].mean()), "expected_on_paper": float(paper[k].mean()),
                    "expected_by_model": float(model[k].mean()),
                    "seasons_beating_paper": int(seasons_beat), "seasons": int(d["season"].nunique())})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-lab", action="store_true", help="skip re-running the Stat Lab candidates")
    args = ap.parse_args(argv)
    log = setup_logging()

    logs = m.load_logs()
    if logs.empty:
        log.error("no stored NBA data; run python -m refresh.nba first")
        return 1
    f = m.build_features(logs)
    rows = nm.game_rows(f)
    done = completed_seasons(rows)
    if len(done) < 3:
        log.error("need at least 3 completed seasons, found %s", done)
        return 1
    tests = done[2:]
    log.info("games: %d | completed seasons: %s | held-out: %s", rows["game_id"].nunique(), done, tests)

    pred = nm.evaluate(rows, nm.BASE_FEATURES, "logistic", tests)
    boost = nm.evaluate(rows, nm.BASE_FEATURES, "boosting", tests)
    calib = nm.calibration_table(pred).reset_index(drop=True)
    report = {
        "created_utc": utc_now_iso(), "held_out_seasons": tests,
        "scores": {"model": nm.scores(pred), "gradient_boosting": nm.scores(boost),
                   "on_paper": nm.scores(pred, "paper_a"), "raw_elo": nm.scores(pred, "elo_raw_a")},
        "calibration": calib.to_dict("records"),
        "upset_watch": upset_backtest(pred),
    }
    if not args.no_lab:
        lab_f = nba_statlab.add_fatigue(f)
        lab_f = nba_statlab.add_opponent_adjusted_form(lab_f)
        lab_f = nba_statlab.add_roster_features(lab_f, nba_players.player_ratings(logs))
        report["stat_lab"] = nba_statlab.run(nm.game_rows(lab_f), nm.BASE_FEATURES, tests).to_dict("records")

    model = nm.train_final(rows, seasons=done)
    model.update({"created_utc": utc_now_iso(), "held_out": report["scores"]["model"]})
    nm.save_model(model)
    atomic_write_json(report, REPORT_PATH)
    s = report["scores"]
    log.info("held-out log loss: model %.4f | on paper %.4f | raw Elo %.4f | accuracy %.1f%%",
             s["model"]["log_loss"], s["on_paper"]["log_loss"], s["raw_elo"]["log_loss"], 100 * s["model"]["accuracy"])
    log.info("saved %s and %s (trained on %d games)", nm.MODEL_PATH.name, REPORT_PATH.name, model["train_games"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
