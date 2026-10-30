"""Refresh stored MLB hitter and pitcher game logs from the MLB Stats API.

    python -m refresh.mlb                          # current season, incremental
    python -m refresh.mlb --seasons 2024 2025 2026
    python -m refresh.mlb --recent-days 5          # re-pull the last 5 days for stat corrections
    python -m refresh.mlb --max-games 20           # quick smoke test

How it works: one schedule request per season, then one boxscore request per completed
game that isn't stored yet (plus games in the recent-days window, re-pulled for corrections).
Requests are spaced out (--delay, default 0.5s). A first full season is ~2,500 games and
takes roughly 25-40 minutes; later runs only fetch new games. Rerunning is idempotent: rows
are keyed by player + gamePk. If the API stops answering, the run stops and keeps what is
stored. Use is subject to MLB Advanced Media's notice (individual, non-commercial, non-bulk).
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta

import pandas as pd
import requests

from core.storage import (SourceUnavailable, atomic_write_parquet, coverage, require_columns,
                          with_retries)
from refresh.common import USER_AGENT, record_result, setup_logging
from sports import mlb

BASE = "https://statsapi.mlb.com/api/v1"
MAX_CONSECUTIVE_FAILURES = 5


def get_json(session: requests.Session, path: str, params: dict | None = None) -> dict:
    def call():
        r = session.get(f"{BASE}{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    return with_retries(call, attempts=3, base_delay=3, label=path)


def _read(kind: str, season: int) -> pd.DataFrame:
    p = mlb.path_for(kind, season)
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def refresh_season(session, season: int, recent_days: int, delay: float, max_games: int | None, log) -> dict:
    sched = get_json(session, "/schedule", {"sportId": 1, "season": season,
                                            "gameType": "R,F,D,L,W", "hydrate": "team"})
    games = mlb.parse_schedule(sched)
    if games.empty:
        raise ValueError(f"no completed games in the {season} schedule")

    old_hit, old_pit = _read("hitting", season), _read("pitching", season)
    stored = set(old_hit.get("game_id", pd.Series(dtype=str))) | set(old_pit.get("game_id", pd.Series(dtype=str)))
    cutoff = (date.today() - timedelta(days=recent_days)).isoformat()
    todo = games[~games["game_pk"].astype(str).isin(stored) | (games["game_date"] >= cutoff)]
    todo = todo.sort_values(["game_date", "game_number"])
    if max_games:
        todo = todo.head(max_games)
    log.info("%s: %d completed games, %d stored, fetching %d", season, len(games), len(stored), len(todo))

    hit_rows, pit_rows, fetched, streak = [], [], [], 0
    for i, g in enumerate(todo.to_dict("records"), 1):
        try:
            box = get_json(session, f"/game/{g['game_pk']}/boxscore")
            h, p = mlb.parse_boxscore(box, g)
            hit_rows += h
            pit_rows += p
            fetched.append(str(g["game_pk"]))
            streak = 0
        except Exception as e:  # noqa: BLE001
            streak += 1
            log.warning("game %s skipped: %s", g["game_pk"], str(e)[:200])
            if streak >= MAX_CONSECUTIVE_FAILURES:
                log.error("%d failures in a row; stopping early and saving what was fetched", streak)
                break
        if i % 100 == 0:
            log.info("  %d/%d games", i, len(todo))
        time.sleep(delay)

    if not fetched and len(todo):
        raise SourceUnavailable("no boxscores could be fetched")

    out = {}
    for kind, old, rows in (("hitting", old_hit, hit_rows), ("pitching", old_pit, pit_rows)):
        new = mlb.finalize(rows, season)
        keep = old[~old["game_id"].isin(fetched)] if not old.empty else old
        merged = pd.concat([keep, new], ignore_index=True) if not new.empty else keep
        if merged.empty:
            continue
        require_columns(merged, ["player_id", "game_id", "game_date", "season_type"], f"{kind} {season}")
        merged = merged.drop_duplicates(["player_id", "game_id"], keep="last")
        merged = merged.sort_values(["game_date", "game_seq", "game_id"]).reset_index(drop=True)
        atomic_write_parquet(merged, mlb.path_for(kind, season))
        out[f"{season} {kind}"] = coverage(merged)
        log.info("%s %s: %s rows stored", season, kind, f"{len(merged):,}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", nargs="+", type=int, default=[date.today().year])
    ap.add_argument("--recent-days", type=int, default=3)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args(argv)
    log = setup_logging()

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    ok, failed, cov = [], {}, {}
    for season in args.seasons:
        try:
            cov.update(refresh_season(session, season, args.recent_days, args.delay, args.max_games, log))
            ok.append(str(season))
        except Exception as e:  # noqa: BLE001
            failed[str(season)] = f"{type(e).__name__}: {str(e)[:300]}"
    return record_result("mlb", ok, failed, cov)


if __name__ == "__main__":
    sys.exit(main())
