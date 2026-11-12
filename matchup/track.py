"""Upset Watch record: every flag, wins and losses alike.

Rules that keep it honest:
- A flag is written once, when it's made, with the probabilities of that moment, and is never
  edited later except to record its result (one per game).
- Every flag is graded. Postponed games and ties count as 'void' and are left out of the record.
- The record is compared with what was expected: how often those underdogs should have won on
  paper, and how often the model said they would.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.config import DATA_DIR
from core.storage import atomic_write_csv_gz, utc_now_iso

PATH = DATA_DIR / "upset_watch.csv.gz"
COLUMNS = ["flag_id", "created_utc", "sport", "game_id", "game_date", "home", "away", "underdog", "favorite",
           "underdog_record", "favorite_record", "paper_prob", "model_prob", "edge", "threshold",
           "result", "home_score", "away_score", "graded_utc"]
TEXT_COLUMNS = ["flag_id", "created_utc", "sport", "game_id", "game_date", "home", "away", "underdog",
                "favorite", "underdog_record", "favorite_record", "result", "graded_utc"]


def flag_id(sport: str, game_id: str) -> str:
    return f"{sport}-{game_id}"


def load(path: Path = PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS).astype({c: object for c in TEXT_COLUMNS})
    df = pd.read_csv(path, dtype={c: str for c in TEXT_COLUMNS})
    return df.astype({c: object for c in TEXT_COLUMNS})   # text stays text even when a column is all empty


def append_flags(new_rows: list[dict], path: Path = PATH) -> int:
    """Add flags; one per game. The first one written wins, so numbers can't be revised later."""
    old = load(path)
    have = set(old["flag_id"])
    rows = []
    for r in new_rows:
        fid = flag_id(r["sport"], r["game_id"])
        if fid in have:
            continue
        have.add(fid)
        rows.append({**{c: None for c in COLUMNS}, **r, "flag_id": fid,
                     "created_utc": r.get("created_utc") or utc_now_iso()})
    if rows:
        atomic_write_csv_gz(pd.concat([old, pd.DataFrame(rows, columns=COLUMNS)], ignore_index=True), path)
    return len(rows)


def grade(df: pd.DataFrame, results: dict[str, tuple[str | None, int | None, int | None]]) -> pd.DataFrame:
    """Fill in results for ungraded flags. `results[flag_id] = (winner, home_score, away_score)`;
    winner None = void (postponed / tie)."""
    df = df.copy().astype({"result": object, "graded_utc": object})
    for i, r in df[df["result"].isna()].iterrows():
        res = results.get(r["flag_id"])
        if res is None:
            continue
        winner, hs, as_ = res
        outcome = "void" if winner is None else ("upset" if winner == r["underdog"] else "no upset")
        df.loc[i, ["result", "home_score", "away_score", "graded_utc"]] = [outcome, hs, as_, utc_now_iso()]
    return df


def summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per sport (plus 'All'): flags, pending, settled, upsets, upset rate, and what was expected."""
    rows = []
    for sport, g in [("All", df)] + list(df.groupby("sport")):
        settled = g[g["result"].isin(["upset", "no upset"])]
        n = len(settled)
        upsets = int((settled["result"] == "upset").sum())
        rows.append({
            "sport": sport, "flags": len(g), "pending": int(g["result"].isna().sum()), "settled": n,
            "upsets": upsets, "upset_rate": upsets / n if n else None,
            "expected_on_paper": float(settled["paper_prob"].mean()) if n else None,
            "expected_by_model": float(settled["model_prob"].mean()) if n else None,
        })
    return pd.DataFrame(rows)
