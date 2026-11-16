"""Player Projections daily job (NBA): lock tonight's projections before tip-off, grade earlier
days from the stored game logs, update the record.

    python -m refresh.projections                 # run after `python -m refresh.nba`
    python -m refresh.projections --date 2026-11-20
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from core.storage import update_meta, utc_now_iso
from matchup import nba_live
from matchup import projections_live as pl
from refresh.common import setup_logging
from sports import nba_matchup as m
from sports import nba_projections as pj


def run(day: date, now_utc: pd.Timestamp, log) -> int:
    model = pj.load_model()
    if model is None:
        log.error("no projection model at %s; run python -m refresh.train_projections", pj.MODEL_PATH)
        return 1
    logs = m.load_logs()
    if logs.empty:
        log.error("no stored NBA data; run python -m refresh.nba")
        return 1
    games = nba_live.todays_games(day)
    if games.empty:
        log.info("%s: no NBA games", day)
    else:
        rows = pl.projection_rows(model, logs, games, day, now_utc)
        added = pl.lock(rows, day)
        flags = sum((rows[f"flag_{s}"] != "").sum() for s in pl.FLAG_STATS) if added else 0
        log.info("%s: %d games, %d players projected (%d new), %d ⬆️/⬇️ flags", day, len(games), len(rows), added, flags)

    graded = sum(pl.grade_day(d, logs, day) for d in pl.all_days() if d < day)
    rec = pl.save_record()
    log.info("graded %d player-games; record now covers %d graded player-games", graded, rec.get("graded", 0))
    update_meta("projections", last_success_utc=utc_now_iso(), last_day=str(day))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", type=date.fromisoformat, default=None, help="game day (US Eastern); default today")
    args = ap.parse_args(argv)
    return run(args.date or nba_live.today_et(), pd.Timestamp.now(tz="UTC"), setup_logging())


if __name__ == "__main__":
    sys.exit(main())
