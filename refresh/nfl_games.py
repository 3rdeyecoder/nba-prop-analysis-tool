"""Refresh the NFL game files used by Upset Watch (nflverse, CC-BY 4.0).

    python -m refresh.nfl_games                               # current season (the daily job)
    python -m refresh.nfl_games --seasons 2010 2011 ... 2026  # one-time backfill

Writes data/nfl/games.parquet, team_games.parquet and qb_games.parquet. Each run replaces the
requested seasons and keeps the others. Betting columns in the nflverse schedule are never saved.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from core.storage import atomic_write_parquet, require_columns, update_meta, utc_now_iso, with_retries
from refresh.common import USER_AGENT, setup_logging
from sports import nfl_matchup as nm


def _merge(path, new: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    if path.exists():
        old = pd.read_parquet(path)
        new = pd.concat([old[~old["season"].isin(seasons)], new], ignore_index=True)
    return new.sort_values(["season", "week", "game_id"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    import nflreadpy
    from nflreadpy.config import update_config

    update_config(cache_mode="off", timeout=90, verbose=False, user_agent=USER_AGENT)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", nargs="+", type=int, default=[nflreadpy.get_current_season()])
    args = ap.parse_args(argv)
    log = setup_logging()
    seasons = sorted(set(args.seasons))

    sched = with_retries(lambda: nflreadpy.load_schedules(seasons), label="schedules").to_pandas()
    team = with_retries(lambda: nflreadpy.load_team_stats(seasons, summary_level="week"), label="team stats").to_pandas()
    players = with_retries(lambda: nflreadpy.load_player_stats(seasons, summary_level="week"),
                           label="player stats").to_pandas()
    require_columns(sched, nm.GAME_COLS, "schedules")
    require_columns(team, nm.TEAM_STAT_COLS, "team stats")
    require_columns(players, nm.QB_STAT_COLS + ["position"], "player stats")

    games = sched[nm.GAME_COLS]
    qbs = players[(players["position"] == "QB") & players["game_id"].notna()][nm.QB_STAT_COLS]
    atomic_write_parquet(_merge(nm.GAMES_PATH, games, seasons), nm.GAMES_PATH)
    atomic_write_parquet(_merge(nm.TEAM_GAMES_PATH, team[nm.TEAM_STAT_COLS], seasons), nm.TEAM_GAMES_PATH)
    atomic_write_parquet(_merge(nm.QB_GAMES_PATH, qbs, seasons), nm.QB_GAMES_PATH)
    played = games["home_score"].notna().sum()
    log.info("seasons %s: %d games (%d played), %d team-games, %d QB-games", seasons, len(games), played,
             len(team), len(qbs))
    update_meta("nfl_games", last_success_utc=utc_now_iso(), seasons=[str(s) for s in seasons])
    return 0


if __name__ == "__main__":
    sys.exit(main())
