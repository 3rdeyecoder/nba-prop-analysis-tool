# fetch_data.py — run this on YOUR machine (not Streamlit Cloud), then commit data/
#   python fetch_data.py                 # current season only
#   python fetch_data.py 2024-25 2025-26 # specific seasons
import sys
import time
from pathlib import Path

from nba_api.stats.endpoints import leaguegamelog

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

seasons = sys.argv[1:] or ["2026-27"]

for season in seasons:
    print(f"Fetching {season}...")
    df = leaguegamelog.LeagueGameLog(
        player_or_team_abbreviation="P",
        season=season,
        season_type_all_star="Regular Season",
        timeout=60,
    ).get_data_frames()[0]
    out = DATA_DIR / f"league_logs_{season}.csv.gz"
    df.to_csv(out, index=False, compression="gzip")
    print(f"  saved {len(df):,} rows -> {out}")
    time.sleep(1.5)  # be polite to stats.nba.com
