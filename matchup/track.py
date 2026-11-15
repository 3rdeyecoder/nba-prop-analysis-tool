"""Upset Watch prediction log and record. Shared by every sport.

Every game gets one row, written once BEFORE tip-off with the numbers of that moment, and never
edited afterwards except to record the result. Flagged rows (model gives the on-paper underdog at
least the official threshold more) make up the Upset Watch record. Logging every game (not only
flags) keeps the record honest and lets the page compare the model with "on paper" on all games.

Results: 'upset' (on-paper underdog won), 'no upset', 'void' (postponed / no result), or empty.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.config import DATA_DIR
from core.storage import atomic_write_csv_gz, utc_now_iso

UPSET_DIR = DATA_DIR / "upset_watch"
COLUMNS = ["flag_id", "created_utc", "sport", "game_id", "game_date", "start_utc", "home", "away", "underdog",
           "favorite", "underdog_record", "favorite_record", "paper_prob", "model_prob", "home_model_prob",
           "home_paper_prob", "edge", "threshold", "flagged", "data_through", "result", "winner", "home_score",
           "away_score", "graded_utc"]
TEXT_COLUMNS = ["flag_id", "created_utc", "sport", "game_id", "game_date", "start_utc", "home", "away", "underdog",
                "favorite", "underdog_record", "favorite_record", "data_through", "result", "winner", "graded_utc"]


def log_path(sport: str) -> Path:
    return UPSET_DIR / f"{sport.lower()}_predictions.csv.gz"


def flag_id(sport: str, game_id: str) -> str:
    return f"{sport}-{game_id}"


def load(path: Path) -> pd.DataFrame:
    if not path.exists():
        df = pd.DataFrame(columns=COLUMNS).astype({c: object for c in TEXT_COLUMNS})
    else:
        df = pd.read_csv(path, dtype={c: str for c in TEXT_COLUMNS})
        df = df.astype({c: object for c in TEXT_COLUMNS})      # text stays text even when a column is all empty
    df["flagged"] = df["flagged"].astype(str).str.lower().isin(["true", "1"]).astype(bool)   # always yes/no
    return df


def append(new_rows: list[dict], path: Path) -> int:
    """Add predictions; one per game. The first one written wins, so numbers can't be revised later."""
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
        new = pd.DataFrame(rows, columns=COLUMNS)
        atomic_write_csv_gz(new if old.empty else pd.concat([old, new], ignore_index=True), path)
    return len(rows)


def grade(df: pd.DataFrame, results: dict[str, tuple[str | None, int | None, int | None]]) -> pd.DataFrame:
    """Fill in results for ungraded rows. `results[flag_id] = (winner, home_score, away_score)`;
    winner None = void (postponed / no result)."""
    df = df.copy().astype({"result": object, "winner": object, "graded_utc": object})
    for i, r in df[df["result"].isna()].iterrows():
        res = results.get(r["flag_id"])
        if res is None:
            continue
        winner, hs, as_ = res
        if winner is None:
            outcome = "void"
        elif pd.isna(r["underdog"]):
            outcome = "even"                                      # even on paper: no underdog
        else:
            outcome = "upset" if winner == r["underdog"] else "no upset"
        df.loc[i, ["result", "winner", "home_score", "away_score", "graded_utc"]] = [outcome, winner, hs, as_, utc_now_iso()]
    return df


def summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per sport (plus 'All'): Upset Watch flags, upsets, upset rate vs what was expected, and how often
    the model and 'on paper' picked the winner across every graded game."""
    rows = []
    for sport, g in [("All", df)] + list(df.groupby("sport")):
        flags = g[g["flagged"]]
        settled = flags[flags["result"].isin(["upset", "no upset"])]
        n = len(settled)
        upsets = int((settled["result"] == "upset").sum())
        games = g[g["winner"].notna() & g["result"].ne("void")]
        model_pick = games["home"].where(games["home_model_prob"] >= 0.5, games["away"])
        paper_pick = games["home"].where(games["home_paper_prob"] >= 0.5, games["away"])
        rows.append({
            "sport": sport, "flags": len(flags), "pending": int(flags["result"].isna().sum()), "settled": n,
            "upsets": upsets, "upset_rate": upsets / n if n else None,
            "expected_on_paper": float(settled["paper_prob"].mean()) if n else None,
            "expected_by_model": float(settled["model_prob"].mean()) if n else None,
            "games_graded": len(games),
            "model_correct": int((model_pick == games["winner"]).sum()),
            "paper_correct": int((paper_pick == games["winner"]).sum()),
        })
    return pd.DataFrame(rows)
