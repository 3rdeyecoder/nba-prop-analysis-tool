"""Refresh stored NBA game logs from stats.nba.com.

    python -m refresh.nba                          # current season, regular season + playoffs
    python -m refresh.nba --seasons 2024-25 2025-26
    python -m refresh.nba --types regular

Run this on your own machine (stats.nba.com often blocks or times out cloud hosts such as
Streamlit Cloud), then commit data/. Each season is one request and is fully re-pulled, so
reruns are idempotent and pick up stat corrections. Set NBA_PROXY to route through a proxy;
its value is never printed.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date

import pandas as pd

from core.storage import atomic_write_csv_gz, coverage, require_columns, with_retries
from refresh.common import record_result, setup_logging
from sports import nba

API_TYPES = {"regular": ("Regular Season", "Regular Season"), "playoffs": ("Playoffs", "Playoffs")}
HEADERS = {
    "Host": "stats.nba.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
}


def current_season(today: date | None = None) -> str:
    today = today or date.today()
    start = today.year if today.month >= 10 else today.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def fetch(season: str, api_type: str, proxy: str | None) -> pd.DataFrame:
    from nba_api.stats.endpoints import leaguegamelog

    return leaguegamelog.LeagueGameLog(
        player_or_team_abbreviation="P", season=season, season_type_all_star=api_type,
        timeout=60, proxy=proxy,
    ).get_data_frames()[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", nargs="+", default=[current_season()])
    ap.add_argument("--types", nargs="+", choices=list(API_TYPES), default=["regular", "playoffs"])
    args = ap.parse_args(argv)
    log = setup_logging()
    proxy = os.environ.get("NBA_PROXY") or None

    ok, failed, cov = [], {}, {}
    for season in args.seasons:
        for t in args.types:
            label, api_type = API_TYPES[t]
            key = f"{season} {label}"
            try:
                raw = with_retries(lambda: fetch(season, api_type, proxy), attempts=3, base_delay=5, label=key)
                if raw.empty and t == "playoffs":
                    log.info("%s: no playoff games yet; skipping", key)
                    continue
                require_columns(raw, nba.REQUIRED, key)
                normalized = nba.normalize(raw, season, label)  # validates before writing
                path = nba.season_path(season, label)
                atomic_write_csv_gz(raw, path)
                cov[key] = coverage(normalized)
                ok.append(key)
                log.info("%s: saved %s rows -> %s", key, f"{len(raw):,}", path.name)
            except Exception as e:  # noqa: BLE001
                msg = str(e).replace(proxy, "***") if proxy else str(e)
                failed[key] = f"{type(e).__name__}: {msg[:300]}"
            time.sleep(1.5)  # be polite to stats.nba.com
    return record_result("nba", ok, failed, cov)


if __name__ == "__main__":
    sys.exit(main())
