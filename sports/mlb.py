"""MLB: parse MLB Stats API schedule + boxscore JSON into hitter and pitcher game logs.

Source: MLB Stats API (statsapi.mlb.com), MLB Advanced Media's public JSON service.
Its copyright notice permits individual, non-commercial, non-bulk use only. The refresh
script requests one boxscore per completed game, politely rate-limited, and only fetches
games it doesn't already have (plus a short recent window for stat corrections).
Pitch-level Statcast data is NOT downloaded: boxscores already contain every game-log stat.

Rules (shown in the UI):
- One row per player per gamePk. Doubleheader games are separate games (different gamePk)
  and are ordered by MLB's gameNumber (1, then 2) on the same date.
- Suspended/resumed games keep one gamePk. They are dated by the date the game began
  (MLB's official date, which is how MLB credits the stats) and only stored once Final.
  `resumed_date` records when it was completed.
- Hitter appearance: at least one plate appearance. Defensive-only substitutions are excluded.
  "Starter" = listed in the starting lineup (battingOrder ending in 00).
- Pitcher appearance: faced at least one batter or recorded at least one out.
  "Start" = credited with a game started.
- Pitching workload is stored as integer outs. Innings are derived for display only (5.2 = 17 outs).
- Batter strikeouts (`so`) and pitcher strikeouts (`k`) are separate columns in separate tables.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.config import DATA_DIR
from core.metrics import dedupe, ip_to_outs, outs_to_ip, total_bases

MLB_DIR = DATA_DIR / "mlb"

GAME_TYPES = {"R": "Regular Season", "F": "Postseason", "D": "Postseason", "L": "Postseason", "W": "Postseason"}
ROUND_LABEL = {"R": "Regular season", "F": "Wild Card", "D": "Division Series", "L": "LCS", "W": "World Series"}
FINAL_PREFIXES = ("Final", "Game Over", "Completed Early")

HITTER_STATS = [
    ("Hitting", "Hits", "hits"),
    ("Hitting", "Home runs", "home_runs"),
    ("Hitting", "Total bases", "total_bases"),
    ("Hitting", "Runs", "runs"),
    ("Hitting", "RBIs", "rbi"),
    ("Hitting", "Walks", "walks"),
    ("Hitting", "Strikeouts (batter)", "so"),
    ("Hitting", "Stolen bases", "stolen_bases"),
    ("Combos", "Hits + Runs + RBIs", "h_r_rbi"),
]
PITCHER_STATS = [
    ("Pitching", "Strikeouts (pitcher)", "k"),
    ("Pitching", "Outs recorded", "outs"),
    ("Pitching", "Hits allowed", "hits_allowed"),
    ("Pitching", "Earned runs", "earned_runs"),
    ("Pitching", "Walks allowed", "walks_allowed"),
    ("Pitching", "Home runs allowed", "hr_allowed"),
]


def path_for(kind: str, season: int) -> Path:
    return MLB_DIR / f"{kind}_{season}.parquet"


def available_seasons(kind: str) -> list[int]:
    return sorted(int(p.stem.rsplit("_", 1)[1]) for p in MLB_DIR.glob(f"{kind}_*.parquet"))


def is_final(game: dict) -> bool:
    return str(game.get("status", {}).get("detailedState", "")).startswith(FINAL_PREFIXES)


def parse_schedule(schedule: dict) -> pd.DataFrame:
    """One row per completed regular-season/postseason gamePk."""
    rows = []
    for day in schedule.get("dates", []):
        for g in day.get("games", []):
            gt = g.get("gameType")
            if gt not in GAME_TYPES:
                continue
            teams = g.get("teams", {})
            rows.append({
                "game_pk": int(g["gamePk"]),
                "official_date": g.get("officialDate") or day.get("date"),
                "listing_date": day.get("date"),
                "game_number": int(g.get("gameNumber") or 1),
                "double_header": g.get("doubleHeader", "N"),
                "game_type": gt,
                "final": is_final(g),
                "home_abbr": _abbr(teams.get("home", {}).get("team", {})),
                "away_abbr": _abbr(teams.get("away", {}).get("team", {})),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # A suspended game can be listed on its start date and its resume date. Date it by
    # the earliest official date; keep it only if some listing shows it as Final.
    agg = df.groupby("game_pk").agg(
        game_date=("official_date", "min"),
        resumed_date=("listing_date", "max"),
        final=("final", "any"),
        game_number=("game_number", "first"),
        double_header=("double_header", "first"),
        game_type=("game_type", "first"),
        home_abbr=("home_abbr", "first"),
        away_abbr=("away_abbr", "first"),
    ).reset_index()
    agg.loc[agg["resumed_date"] == agg["game_date"], "resumed_date"] = None
    return agg[agg["final"]].drop(columns="final").reset_index(drop=True)


def _abbr(team: dict) -> str:
    return team.get("abbreviation") or team.get("teamCode", "").upper() or team.get("name", "?")


def _i(d: dict, key: str):
    v = d.get(key)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_boxscore(box: dict, game: dict) -> tuple[list[dict], list[dict]]:
    """Return (hitter_rows, pitcher_rows) for one game. `game` is a parse_schedule row."""
    hitters, pitchers = [], []
    for side, opp_side in (("home", "away"), ("away", "home")):
        team_box = box.get("teams", {}).get(side, {})
        team = game[f"{side}_abbr"]
        opp = game[f"{opp_side}_abbr"]
        for p in team_box.get("players", {}).values():
            person = p.get("person", {})
            if "id" not in person:
                continue
            base = {
                "player_id": str(person["id"]),
                "player_name": person.get("fullName", str(person["id"])),
                "team": team, "opponent": opp, "venue": "Home" if side == "home" else "Away",
                "game_id": str(game["game_pk"]), "game_date": game["game_date"],
                "game_seq": int(game["game_number"]), "game_type": game["game_type"],
                "double_header": game["double_header"], "resumed_date": game.get("resumed_date"),
                "position": p.get("position", {}).get("abbreviation"),
            }
            stats = p.get("stats", {})
            bat = stats.get("batting") or {}
            pa = _i(bat, "plateAppearances")
            if pa and pa > 0:
                order = str(p.get("battingOrder") or "")
                h, d2, d3, hr = (_i(bat, k) for k in ("hits", "doubles", "triples", "homeRuns"))
                singles = None if None in (h, d2, d3, hr) else h - d2 - d3 - hr
                hitters.append({
                    **base,
                    "started": order.isdigit() and int(order) % 100 == 0,
                    "batting_order": int(order) // 100 if order.isdigit() else None,
                    "pa": pa, "ab": _i(bat, "atBats"), "hits": h, "doubles": d2, "triples": d3,
                    "home_runs": hr, "singles": singles,
                    "total_bases": None if singles is None else total_bases(singles, d2, d3, hr),
                    "runs": _i(bat, "runs"), "rbi": _i(bat, "rbi"), "walks": _i(bat, "baseOnBalls"),
                    "so": _i(bat, "strikeOuts"), "stolen_bases": _i(bat, "stolenBases"),
                })
            pit = stats.get("pitching") or {}
            if pit:
                outs = _i(pit, "outs")
                if outs is None and pit.get("inningsPitched") is not None:
                    outs = ip_to_outs(pit["inningsPitched"])
                bf = _i(pit, "battersFaced")
                if (bf or 0) > 0 or (outs or 0) > 0:
                    pitchers.append({
                        **base,
                        "started": _i(pit, "gamesStarted") == 1,
                        "outs": outs, "batters_faced": bf, "pitches": _i(pit, "numberOfPitches"),
                        "k": _i(pit, "strikeOuts"), "hits_allowed": _i(pit, "hits"),
                        "earned_runs": _i(pit, "earnedRuns"), "walks_allowed": _i(pit, "baseOnBalls"),
                        "hr_allowed": _i(pit, "homeRuns"),
                    })
    return hitters, pitchers


def finalize(rows: list[dict], season: int) -> pd.DataFrame:
    """Typed, de-duplicated table ready to store."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["season"] = int(season)
    df["season_type"] = df["game_type"].map(GAME_TYPES)
    df["round"] = df["game_type"].map(ROUND_LABEL)
    df, _ = dedupe(df, ["player_id", "game_id"])
    return df


def add_derived(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    df = df.copy()
    df["season_year"] = df["season"].astype(int)
    df["season"] = df["season_year"].astype(str)
    df["headshot_url"] = None
    if kind == "hitting":
        df["h_r_rbi"] = df[["hits", "runs", "rbi"]].sum(axis=1, min_count=3)
    else:
        df["ip"] = df["outs"].map(outs_to_ip)
    return df


def load_season(kind: str, season: int) -> pd.DataFrame:
    return add_derived(pd.read_parquet(path_for(kind, season)), kind)
