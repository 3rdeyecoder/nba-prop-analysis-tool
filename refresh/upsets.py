"""Upset Watch daily job (NBA): snapshot, today's predictions, grading.

    python -m refresh.upsets                 # run after `python -m refresh.nba`
    python -m refresh.upsets --date 2026-11-20

1. Saves a snapshot of every team's numbers as of today (games before today only).
2. Logs a prediction for each of today's games that hasn't tipped off yet (US Eastern date).
   A game's prediction is written once and never changed.
3. Grades earlier predictions whose results are now in the stored game logs.

The GitHub bot runs this every morning; you can also run it from your Mac after refreshing NBA data.
Predictions use whatever data is stored at that moment; each row records its `data_through` date.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from core.storage import update_meta, utc_now_iso
from matchup import nba_live, track
from refresh.common import setup_logging
from sports import nba_matchup as m
from sports import nba_model as nm


def run(day: date, now_utc: pd.Timestamp, log) -> int:
    model = nm.load_model()
    if model is None:
        log.error("no model at %s; run python -m refresh.train_nba", nm.MODEL_PATH)
        return 1
    logs = m.load_logs()
    if logs.empty:
        log.error("no stored NBA data; run python -m refresh.nba")
        return 1

    state, tg = nba_live.build_snapshot(logs, day)
    if state.empty:
        log.error("no games before %s to build a snapshot from", day)
        return 1
    nba_live.save_snapshot(state, tg)
    log.info("snapshot as of %s: %d teams, data through %s", day, len(state),
             pd.Timestamp(state["data_through"].iloc[0]).date())

    path = track.log_path("NBA")
    games = nba_live.todays_games(day)
    rows = nba_live.prediction_rows(model, state.set_index("team", drop=False), tg, games, day, now_utc)
    added = track.append(rows, path)
    log.info("%s: %d games scheduled, %d new predictions (%d flagged)", day, len(games), added,
             sum(r["flagged"] for r in rows[:added]) if added else 0)

    pred = track.load(path)
    results = nba_live.results_from_logs(pred, logs, day)
    if results:
        from core.storage import atomic_write_csv_gz
        atomic_write_csv_gz(track.grade(pred, results), path)
    log.info("graded %d earlier games", len(results))
    update_meta("upset_watch", last_success_utc=utc_now_iso(), snapshot_as_of=str(day))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", type=date.fromisoformat, default=None, help="US Eastern date (default: today)")
    args = ap.parse_args(argv)
    log = setup_logging()
    return run(args.date or nba_live.today_et(), pd.Timestamp.now(tz="UTC"), log)


if __name__ == "__main__":
    sys.exit(main())
