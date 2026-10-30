"""Refresh stored NFL weekly player stats from nflverse (via nflreadpy).

    python -m refresh.nfl                                # current season only
    python -m refresh.nfl --seasons 2022 2023 2024 2025 2026

nflverse publishes one file per season, so each season is re-downloaded in full. That makes
reruns idempotent and picks up nflverse's stat corrections for recent weeks. Data is
CC-BY 4.0: credit "nflverse" when you display it.
"""
from __future__ import annotations

import argparse
import sys

from core.storage import atomic_write_parquet, coverage, require_columns, with_retries
from refresh.common import USER_AGENT, record_result, setup_logging
from sports import nfl


def main(argv: list[str] | None = None) -> int:
    import nflreadpy
    from nflreadpy.config import update_config

    # Always fetch fresh copies; nflreadpy's own cache would hide updates.
    update_config(cache_mode="off", timeout=60, verbose=False, user_agent=USER_AGENT)

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", nargs="+", type=int, default=[nflreadpy.get_current_season()])
    args = ap.parse_args(argv)
    log = setup_logging()

    ok, failed, cov = [], {}, {}
    for season in args.seasons:
        key = str(season)
        try:
            stats = with_retries(lambda: nflreadpy.load_player_stats([season], summary_level="week"),
                                 label=f"player stats {season}").to_pandas()
            sched = with_retries(lambda: nflreadpy.load_schedules([season]),
                                 label=f"schedules {season}").to_pandas()
            require_columns(stats, nfl.KEEP, f"player stats {season}")
            require_columns(sched, nfl.SCHEDULE_KEEP, f"schedules {season}")
            df = nfl.normalize(stats, sched)
            require_columns(df, ["player_id", "game_id", "game_date"], f"normalized {season}")
            unmatched = stats["game_id"].notna().sum() - df["game_id"].notna().sum()
            atomic_write_parquet(df, nfl.season_path(season))
            cov[key] = coverage(df)
            ok.append(key)
            log.info("%s: saved %s player-games (weeks %s-%s, %s rows dropped as non-offense or unmatched)",
                     key, f"{len(df):,}", int(df["week"].min()), int(df["week"].max()), f"{unmatched:,}")
        except Exception as e:  # noqa: BLE001
            failed[key] = f"{type(e).__name__}: {str(e)[:300]}"
    return record_result("nfl", ok, failed, cov)


if __name__ == "__main__":
    sys.exit(main())
