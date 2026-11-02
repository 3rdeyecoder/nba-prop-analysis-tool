"""Call It: a daily over/under puzzle built from real past NBA games.

Rules (also shown in the app):
- A round is one past regular-season game. The player must have 10+ earlier games that season,
  average 25+ minutes in those 10, and clear a minimum for the stat (e.g. 15+ points).
- Only the 10 games BEFORE the round's game are shown. The line is the MEDIAN of those 10, moved
  to the nearest .5 below when it's a whole number, so about half the shown games are on each side
  and a push is impossible for these whole-number stats. Measured over all 66k playable games in
  2019-20 through 2026-27, this rule goes over 48% of the time (47.8-50.1% per stat). An
  average-based line went over only 44.5%, because a few big nights pull the average up.
- Games are chosen without looking at their results, so the puzzle doesn't lean over or under.
- Everyone gets the same 5 rounds on a given US Eastern date. Rounds only use games at least
  CUTOFF_DAYS old, so a data refresh during the day can't change today's puzzle.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

import numpy as np
import pandas as pd

LAUNCH = date(2026, 11, 1)      # puzzle #1 (US Eastern date)
CUTOFF_DAYS = 3
PRIOR_N = 10
MIN_MINUTES = 25
ROUND_STATS = ["PTS", "PTS", "REB", "AST", "PRA"]
MIN_AVG = {"PTS": 15, "REB": 7, "AST": 5, "PRA": 25, "FG3M": 2}
LABEL = {"PTS": "points", "REB": "rebounds", "AST": "assists", "PRA": "pts + reb + ast", "FG3M": "3-pointers"}


def puzzle_number(day: date) -> int:
    return max(1, (day - LAUNCH).days + 1)


def build_pool(df: pd.DataFrame) -> pd.DataFrame:
    """Every player-game that could be a round, with its prior-10 averages (no result columns used)."""
    d = df.sort_values(["player_id", "season", "game_date", "game_id"], kind="mergesort").copy()
    g = d.groupby(["player_id", "season"], sort=False)
    d["prior_games"] = g.cumcount()
    keys = [d["player_id"], d["season"]]
    for col in ["MIN", *MIN_AVG]:
        # average of the 10 games before each game, via cumulative sums (fast, same result)
        cs = d[col].astype(float).groupby(keys).cumsum()
        before = cs.groupby(keys).shift(1)
        ten_before = cs.groupby(keys).shift(PRIOR_N + 1).fillna(0.0)
        d[f"prior_{col}"] = ((before - ten_before) / PRIOR_N).where(d["prior_games"] >= PRIOR_N)
        if col != "MIN":
            prev = d[col].astype(float).groupby(keys).shift(1)
            d[f"prior_{col}_med"] = (prev.groupby(keys).rolling(PRIOR_N).median()
                                     .reset_index(level=[0, 1], drop=True))
    keep = (d["prior_games"] >= PRIOR_N) & (d["prior_MIN"] >= MIN_MINUTES)
    return d[keep].reset_index(drop=True)


def fair_line(prior_median: float) -> float:
    """Median of the prior games, nudged to the .5 below when it's a whole number."""
    m = float(prior_median)
    return m - 0.5 if m.is_integer() else m


def _seed(day: date) -> int:
    return int(hashlib.sha256(f"callit-{day.isoformat()}".encode()).hexdigest()[:12], 16)


def daily_rounds(pool: pd.DataFrame, day: date) -> list[dict]:
    """The 5 rounds for `day`. Same inputs -> same rounds, for everyone."""
    rng = np.random.default_rng(_seed(day))
    cutoff = pd.Timestamp(day - timedelta(days=CUTOFF_DAYS))
    base = pool[pool["game_date"] < cutoff].sort_values(["game_id", "player_id"], kind="mergesort")
    team_ids = (pool.dropna(subset=["TEAM_ID"]).groupby(["season", "team"])["TEAM_ID"].first().astype(int)
                if "TEAM_ID" in pool else pd.Series(dtype=int))
    rounds, used = [], set()
    for stat in ROUND_STATS:
        cands = base[(base[f"prior_{stat}"] >= MIN_AVG[stat]) & ~base["player_id"].isin(used)]
        if cands.empty:
            continue
        row = cands.iloc[int(rng.integers(len(cands)))]
        used.add(row["player_id"])
        line = fair_line(row[f"prior_{stat}_med"])
        rounds.append({
            "player_id": row["player_id"], "player_name": row["player_name"], "team": row["team"],
            "team_id": int(row["TEAM_ID"]) if "TEAM_ID" in row and pd.notna(row["TEAM_ID"]) else None,
            "opponent": row["opponent"], "venue": row["venue"], "game_id": row["game_id"],
            "opp_team_id": int(team_ids[(row["season"], row["opponent"])])
            if (row["season"], row["opponent"]) in team_ids.index else None,
            "game_date": row["game_date"], "season": row["season"], "stat": stat, "line": line,
            "prior_avg": float(row[f"prior_{stat}"]), "prior_median": float(row[f"prior_{stat}_med"]),
            "actual": float(row[stat]),
            "answer": "Over" if row[stat] > line else "Under",
            "box": {k: row[k] for k in ("PTS", "REB", "AST", "FG3M", "MIN") if k in row},
        })
    return rounds


def prior_games(df: pd.DataFrame, rnd: dict) -> pd.DataFrame:
    """The 10 games shown for a round: same player, same season, strictly before the game."""
    g = df[(df["player_id"] == rnd["player_id"]) & (df["season"] == rnd["season"])
           & (df["game_date"] < rnd["game_date"])]
    return g.sort_values(["game_date", "game_id"]).tail(PRIOR_N)


def share_text(number: int, results: list[bool], url: str) -> str:
    grid = "".join("🟩" if r else "🟥" for r in results)
    return f"Playmaker Lab · Call It #{number} — {sum(results)}/{len(results)}\n{grid}\n{url}"
