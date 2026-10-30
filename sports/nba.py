"""NBA: read stored LeagueGameLog snapshots and normalize them. No network calls here.

Storage (unchanged from the original app so existing committed data keeps working):
    data/league_logs_<season>.csv.gz            regular season
    data/league_logs_<season>_playoffs.csv.gz   playoffs (written by refresh/nba.py)

Participation rule: a row in stats.nba.com's LeagueGameLog means the player checked
into that game. Rows with MIN == 0 are kept (brief appearances rounded down to 0 min).
DNPs and inactive players have no row, so they never count as games.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from core.config import DATA_DIR
from core.metrics import dedupe

SEASON_TYPES = {"Regular Season": "", "Playoffs": "_playoffs"}

# label -> column. Original app's stats, plus STL, BLK and shooting volume (FGM/FGA/3PA/FTM/FTA).
STATS = {
    "Points": "PTS",
    "Rebounds": "REB",
    "Assists": "AST",
    "3-pointers made": "FG3M",
    "3-pointers attempted": "FG3A",
    "Field goals made": "FGM",
    "Field goals attempted": "FGA",
    "Free throws made": "FTM",
    "Free throws attempted": "FTA",
    "Steals": "STL",
    "Blocks": "BLK",
    "Pts + Reb + Ast (PRA)": "PRA",
    "Pts + Reb (PR)": "PR",
    "Pts + Ast (PA)": "PA",
    "Reb + Ast (RA)": "RA",
    "Blocks + Steals": "BLK_STL",
}

NUM_COLS = ["PTS", "REB", "AST", "FGA", "FGM", "FG3A", "FG3M", "FTA", "FTM",
            "DREB", "OREB", "STL", "BLK", "TOV", "PF", "MIN"]
REQUIRED = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GAME_ID", "GAME_DATE", "MATCHUP",
            "PTS", "REB", "AST", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "STL", "BLK", "MIN"]

_FILE_RE = re.compile(r"league_logs_(\d{4}-\d{2})(_playoffs)?\.csv\.gz$")


def season_path(season: str, season_type: str = "Regular Season") -> Path:
    return DATA_DIR / f"league_logs_{season}{SEASON_TYPES[season_type]}.csv.gz"


def available_files() -> list[tuple[str, str, Path]]:
    """(season, season_type, path) for every stored snapshot."""
    out = []
    for p in sorted(DATA_DIR.glob("league_logs_*.csv.gz")):
        m = _FILE_RE.search(p.name)
        if m:
            out.append((m.group(1), "Playoffs" if m.group(2) else "Regular Season", p))
    return out


def normalize(raw: pd.DataFrame, season: str, season_type: str) -> pd.DataFrame:
    df = raw.copy()
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"NBA {season} {season_type}: missing columns {missing}")
    for col in NUM_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["PRA"] = df["PTS"] + df["REB"] + df["AST"]
    df["PR"] = df["PTS"] + df["REB"]
    df["PA"] = df["PTS"] + df["AST"]
    df["RA"] = df["REB"] + df["AST"]
    df["BLK_STL"] = df["BLK"] + df["STL"]

    matchup = df["MATCHUP"].astype(str)
    df["player_id"] = df["PLAYER_ID"].astype("int64").astype(str)
    df["player_name"] = df["PLAYER_NAME"].astype(str)
    df["team"] = df["TEAM_ABBREVIATION"].astype(str)
    df["opponent"] = matchup.str[-3:]
    df["venue"] = matchup.str.contains(" vs. ", regex=False).map({True: "Home", False: "Away"})
    df["game_id"] = df["GAME_ID"].astype("int64").astype(str).str.zfill(10)
    df["game_date"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
    df["game_seq"] = 1
    df["season"] = season
    df["season_year"] = int(season[:4])
    df["season_type"] = season_type
    df["headshot_url"] = "https://cdn.nba.com/headshots/nba/latest/260x190/" + df["player_id"] + ".png"

    df = df.dropna(subset=["game_date"])
    df, _ = dedupe(df, ["player_id", "game_id"])
    return df


def load_file(path: Path, season: str, season_type: str) -> pd.DataFrame:
    return normalize(pd.read_csv(path), season, season_type)
