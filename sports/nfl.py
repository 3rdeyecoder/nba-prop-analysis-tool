"""NFL: normalize nflverse weekly player stats and read the stored Parquet files.

Source: nflverse `stats_player` weekly release via nflreadpy.load_player_stats(summary_level="week"),
joined to nflreadpy.load_schedules() on game_id for date, home/away and neutral-site info.
nflverse data is CC-BY 4.0; attribute "nflverse".

Participation rule (documented in the UI): a qualifying appearance is a row in nflverse's
weekly player stats. nflverse builds those rows from play-by-play, so a row exists when the
player was credited with at least one statistical play (a pass, carry, target, tackle, kick...).
- Bye weeks and games a player missed have no row, so they never enter a game window.
- A row with 0 in a stat is a real zero (e.g. a WR who played but caught nothing after
  being targeted). A missing stat value is shown as unavailable, not zero.
- Limitation: a player who was on the field but never touched the ball or was targeted
  has no row. Snap-count data would be needed to count those games.

Season labels use the official NFL season year (the 2025 season includes Jan/Feb 2026 games).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from core.config import DATA_DIR
from core.metrics import dedupe

NFL_DIR = DATA_DIR / "nfl"
POSITIONS = ["QB", "RB", "WR", "TE"]
OFFENSE_POSITIONS = {"QB", "RB", "FB", "WR", "TE"}

RAW_STATS = [
    "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions",
    "carries", "rushing_yards", "rushing_tds",
    "receptions", "targets", "receiving_yards", "receiving_tds",
]
KEEP = ["player_id", "player_display_name", "position", "headshot_url", "season", "week",
        "season_type", "game_id", "team", "opponent_team"] + RAW_STATS
SCHEDULE_KEEP = ["game_id", "gameday", "home_team", "away_team", "location", "game_type"]

# (group, label, column)
STATS = [
    ("Passing", "Passing yards", "passing_yards"),
    ("Passing", "Passing TDs", "passing_tds"),
    ("Passing", "Pass attempts", "attempts"),
    ("Passing", "Completions", "completions"),
    ("Passing", "Interceptions thrown", "passing_interceptions"),
    ("Rushing", "Rushing yards", "rushing_yards"),
    ("Rushing", "Rush attempts", "carries"),
    ("Rushing", "Rushing TDs", "rushing_tds"),
    ("Receiving", "Receiving yards", "receiving_yards"),
    ("Receiving", "Receptions", "receptions"),
    ("Receiving", "Targets", "targets"),
    ("Receiving", "Receiving TDs", "receiving_tds"),
    ("Combos", "Rush + Rec yards", "rush_rec_yards"),
    ("Combos", "Pass + Rush yards", "pass_rush_yards"),
    ("Combos", "Rush + Rec TDs", "rush_rec_tds"),
]

GAME_TYPE_LABEL = {"REG": "Regular season", "WC": "Wild Card", "DIV": "Divisional",
                   "CON": "Conference", "SB": "Super Bowl"}


def season_path(season: int) -> Path:
    return NFL_DIR / f"player_week_{season}.parquet"


def available_seasons() -> list[int]:
    return sorted(int(p.stem.rsplit("_", 1)[1]) for p in NFL_DIR.glob("player_week_*.parquet"))


def normalize(stats: pd.DataFrame, schedules: pd.DataFrame) -> pd.DataFrame:
    """Build the stored table. Called by refresh/nfl.py; pure function for testing."""
    missing = [c for c in KEEP if c not in stats.columns]
    if missing:
        raise ValueError(f"nflverse player stats schema changed; missing {missing}")
    df = stats[KEEP].copy()
    # Offensive skill players, plus anyone else who recorded one of these stats (trick plays)
    has_offense = df[RAW_STATS].fillna(0).ne(0).any(axis=1)
    df = df[df["position"].isin(OFFENSE_POSITIONS) | has_offense]

    sched = schedules[SCHEDULE_KEEP].drop_duplicates("game_id")
    df = df.merge(sched, on="game_id", how="left", validate="many_to_one")

    df["game_date"] = pd.to_datetime(df["gameday"], errors="coerce")
    df["venue"] = np.select(
        [df["location"].eq("Neutral"), df["team"].eq(df["home_team"]), df["team"].eq(df["away_team"])],
        ["Neutral", "Home", "Away"],
        default=None,
    )
    df["season_type"] = df["season_type"].map({"REG": "Regular Season", "POST": "Postseason"})
    df["round"] = df["game_type"].map(GAME_TYPE_LABEL)
    df = df.rename(columns={"player_display_name": "player_name", "opponent_team": "opponent"})
    df = df.drop(columns=["gameday", "home_team", "away_team", "location", "game_type"])
    df = df.dropna(subset=["game_id", "player_id", "game_date", "season_type"])
    df, _ = dedupe(df, ["player_id", "game_id"])
    return df.reset_index(drop=True)


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Combos plus the shared columns the UI expects. Sums use min_count so NaN stays NaN."""
    df = df.copy()
    df["rush_rec_yards"] = df[["rushing_yards", "receiving_yards"]].sum(axis=1, min_count=2)
    df["pass_rush_yards"] = df[["passing_yards", "rushing_yards"]].sum(axis=1, min_count=2)
    df["rush_rec_tds"] = df[["rushing_tds", "receiving_tds"]].sum(axis=1, min_count=2)
    df["game_seq"] = 1
    df["season_year"] = df["season"].astype(int)
    df["season"] = df["season_year"].astype(str)
    return df


def load_season(season: int) -> pd.DataFrame:
    return add_derived(pd.read_parquet(season_path(season)))


# ---------------------------------------------------------------- stats by position

# Stat groups shown for each position, most relevant first.
POSITION_GROUPS = {
    "QB": ["Passing", "Rushing"],
    "RB": ["Rushing", "Receiving"],
    "FB": ["Rushing", "Receiving"],
    "WR": ["Receiving", "Rushing"],
    "TE": ["Receiving", "Rushing"],
}
DEFAULT_STAT = {"QB": "passing_yards", "RB": "rushing_yards", "FB": "rushing_yards",
                "WR": "receiving_yards", "TE": "receiving_yards"}
GROUP_ACTIVITY = {"Passing": "attempts", "Rushing": "carries", "Receiving": "targets"}
COMBO_NEEDS = {"pass_rush_yards": "Passing", "rush_rec_yards": "Receiving", "rush_rec_tds": "Receiving"}


def stats_for_player(player_games: pd.DataFrame, show_all: bool = False) -> tuple[list[tuple], str, set[str]]:
    """(stat tuples that fit this player, default stat col, core stat cols for the position).

    Starts from the player's position, then adds any other group the player actually
    recorded in the selected games (e.g. a WR with carries, a TE who threw a pass).
    """
    position = str(player_games["position"].iloc[-1]) if len(player_games) else ""
    default = DEFAULT_STAT.get(position, STATS[0][2])
    core_groups = POSITION_GROUPS.get(position, [])
    # Stats that carry over when switching to this player. Trick-play groups are listed
    # but never auto-selected (a WR's one pass attempt shouldn't keep "Passing yards").
    core = {c for g, _, c in STATS if g in core_groups}
    core |= {c for c, need in COMBO_NEEDS.items() if need in core_groups}
    if show_all or position not in POSITION_GROUPS:
        return list(STATS), default, core or {c for _, _, c in STATS}
    groups = list(core_groups)
    for group, col in GROUP_ACTIVITY.items():
        if group not in groups and player_games[col].fillna(0).gt(0).any():
            groups.append(group)
    order = {g: i for i, g in enumerate(groups)}
    picked = [s for s in STATS if s[0] in order]
    picked.sort(key=lambda s: order[s[0]])  # stable: keeps the order within each group
    picked += [s for s in STATS if s[0] == "Combos" and COMBO_NEEDS[s[2]] in order]
    return picked, default, core
