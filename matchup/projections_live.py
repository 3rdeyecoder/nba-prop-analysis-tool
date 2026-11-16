"""NBA Player Projections, live side: lock tonight's projections, grade them, keep the record.

Files (small, one per game day, so the repo doesn't grow by rewriting one big file every day):
  data/projections/nba/<YYYY-MM-DD>.csv.gz   that day's projections, then the actual stats once graded
  data/projections/nba_record.json           running record: model vs season average, flags
Projections are written once, before tip-off, and never changed except to add the actual stats.
Players who don't play (injured, rested, coach's decision) are voided, never counted as misses.
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from core.config import DATA_DIR
from core.storage import atomic_write_csv_gz, atomic_write_json, utc_now_iso
from sports import nba_projections as pj

PROJ_DIR = DATA_DIR / "projections" / "nba"
RECORD_PATH = DATA_DIR / "projections" / "nba_record.json"
VOID_AFTER_DAYS = 7
REASON_STATS = ["MIN", "PTS", "REB", "AST"]       # stats whose reasons are saved for the pop-up
FLAG_STATS = ["PTS", "REB", "AST"]                 # ⬆️/⬇️ flags (backtested well for these three)


def day_path(day: date):
    return PROJ_DIR / f"{day.isoformat()}.csv.gz"


def baseline(rows: pd.DataFrame, stat: str) -> pd.Series:
    ew = rows["min_ew"] if stat == "MIN" else rows[f"{stat}_ew"]
    return rows[f"{stat}_season"].where(rows["season_gp"] >= 3, ew)


def projection_rows(model: dict, logs: pd.DataFrame, games: pd.DataFrame, day: date,
                    now_utc: pd.Timestamp) -> pd.DataFrame:
    """Projections for `day`'s games that haven't started. `games`: game_id, home, away, start_utc."""
    g = games.copy()
    g["start_utc"] = pd.to_datetime(g["start_utc"], utc=True)
    g = g[g["start_utc"] > now_utc]
    if g.empty:
        return pd.DataFrame()
    rows = pj.live_rows(logs, g[["game_id", "home", "away"]], pd.Timestamp(day))
    if rows.empty:
        return rows
    flag, min_avg = model.get("flag", 0.25), model.get("flag_min_avg", {})
    out = pd.DataFrame({
        "created_utc": utc_now_iso(), "game_date": day.isoformat(), "game_id": rows["game_id"],
        "player_id": rows["PLAYER_ID"].astype(int), "player": rows["PLAYER_NAME"], "team": rows["team"],
        "opp": rows["opp"], "home": rows["home"].astype(int), "returning": rows["returning"].astype(int),
        "season_gp": rows["season_gp"].astype(int),
        "data_through": str(pd.to_datetime(logs["GAME_DATE"]).loc[lambda x: x < pd.Timestamp(day)].max().date()),
    })
    out = out.merge(g[["game_id", "start_utc"]].assign(game_id=lambda d: d["game_id"].astype(str),
                                                       start_utc=lambda d: d["start_utc"].map(pd.Timestamp.isoformat)),
                    on="game_id", how="left")
    for stat in pj.TARGETS:
        mu = pj.predict(model, rows, stat)
        lo, hi = pj.predict_range(model, mu, stat)
        out[f"p_{stat}"], out[f"lo_{stat}"], out[f"hi_{stat}"] = mu.round(2), lo.round(2), hi.round(2)
        out[f"avg_{stat}"] = baseline(rows, stat).round(2).to_numpy()
        if stat in FLAG_STATS:
            avg = out[f"avg_{stat}"]
            ok = avg >= min_avg.get(stat, 0)
            out[f"flag_{stat}"] = np.where(ok & (mu >= avg * (1 + flag)), "up",
                                           np.where(ok & (mu <= avg * (1 - flag)), "down", ""))
        if stat in pj.CHANCE_STATS:
            avg = out[f"avg_{stat}"].to_numpy()
            out[f"over_{stat}"] = pj.chance(model, mu, avg, stat, "over").round(3)
            out[f"under_{stat}"] = pj.chance(model, mu, avg, stat, "under").round(3)
        if stat in REASON_STATS:
            eff = pj.context_effects(model, rows, stat)
            for name in eff.columns:
                out[f"eff_{stat}_{name}"] = eff[name].round(3).to_numpy()
    # facts for the reasons
    out["opp_def_PTS"] = rows["opp_allow_PTS"].round(3).to_numpy()
    out["opp_def_REB"] = rows["opp_allow_REB"].round(3).to_numpy()
    out["opp_def_AST"] = rows["opp_allow_AST"].round(3).to_numpy()
    out["pace"] = (rows["pace_team"] * rows["pace_opp"]).round(3).to_numpy()
    out["missing_share"] = rows["missing_min_share"].round(3).to_numpy()
    out["rest"] = rows["rest"].astype(int).to_numpy()
    out["mismatch"] = rows["mismatch"].round(1).to_numpy()
    out["min_l3"] = rows["min_l3"].round(1).to_numpy()
    for stat in pj.TARGETS:
        out[f"act_{stat}"] = np.nan
    out["status"] = ""
    return out.sort_values(["game_id", "team", "p_MIN"], ascending=[True, True, False]).reset_index(drop=True)


TOP_N = 5


def top_picks(d: pd.DataFrame, n: int = TOP_N) -> pd.DataFrame:
    """The day's most likely calls: highest chance of finishing above or below his season average, among
    points/rebounds/assists with a meaningful average, at most one per player, skipping players who
    missed their team's last game (they might not play)."""
    if d.empty or "over_PTS" not in d:
        return pd.DataFrame(columns=["i", "stat", "dir", "chance"])
    c = []
    for s in pj.CHANCE_STATS:
        ok = (d["season_gp"] >= 5) & (d[f"avg_{s}"] >= pj.PICK_MIN_AVG[s]) & (d["returning"] == 0)
        for direction in ("over", "under"):
            c.append(pd.DataFrame({"i": d.index[ok], "player_id": d.loc[ok, "player_id"], "stat": s,
                                   "dir": direction, "chance": d.loc[ok, f"{direction}_{s}"]}))
    c = pd.concat(c).sort_values(["chance", "player_id"], ascending=[False, True])
    return c.drop_duplicates("player_id").head(n).reset_index(drop=True)


def pick_hit(r: pd.Series, stat: str, direction: str) -> bool | None:
    if r.get("status") != "graded":
        return None
    return bool(r[f"act_{stat}"] > r[f"avg_{stat}"]) if direction == "over" else bool(r[f"act_{stat}"] < r[f"avg_{stat}"])


def load_day(day: date) -> pd.DataFrame:
    p = day_path(day)
    return pd.read_csv(p, dtype={"game_id": str, "status": str, "flag_PTS": str, "flag_REB": str, "flag_AST": str},
                       keep_default_na=False, na_values=[""]) if p.exists() else pd.DataFrame()


def lock(rows: pd.DataFrame, day: date) -> int:
    """Write the day's projections once; players already saved for that day are never rewritten."""
    if rows.empty:
        return 0
    old = load_day(day)
    if not old.empty:
        have = set(zip(old["game_id"].astype(str), old["player_id"].astype(int)))
        rows = rows[[(g, p) not in have for g, p in zip(rows["game_id"].astype(str), rows["player_id"])]]
        if rows.empty:
            return 0
        rows = pd.concat([old, rows], ignore_index=True)
        added = len(rows) - len(old)
    else:
        added = len(rows)
    atomic_write_csv_gz(rows, day_path(day))
    return added


def grade_day(day: date, logs: pd.DataFrame, today: date) -> int:
    """Fill in actual stats for a locked day. A player who didn't play (game in the logs, him not)
    is 'dnp' (void). A game missing from the logs for over a week is 'void'."""
    d = load_day(day)
    if d.empty or (d["status"].fillna("") != "").all():
        return 0
    lg = logs.copy()
    lg["gid"] = lg["GAME_ID"].astype(str).str.zfill(10)
    lg = lg[lg["gid"].isin(set(d["game_id"].astype(str)))]
    have_games = set(lg["gid"])
    box = lg.set_index(["gid", "PLAYER_ID"])
    n = 0
    for i, r in d[d["status"].fillna("") == ""].iterrows():
        gid = str(r["game_id"])
        if gid not in have_games:
            if (today - day).days > VOID_AFTER_DAYS:
                d.loc[i, "status"] = "void"
                n += 1
            continue
        key = (gid, int(r["player_id"]))
        if key not in box.index or float(np.nan_to_num(box.loc[key, "MIN"])) <= 0:
            d.loc[i, "status"] = "dnp"
        else:
            b = box.loc[key]
            for stat in pj.TARGETS:
                d.loc[i, f"act_{stat}"] = float(b[stat])
            d.loc[i, "status"] = "graded"
        n += 1
    if n:
        atomic_write_csv_gz(d, day_path(day))
    return n


def all_days() -> list[date]:
    return sorted(date.fromisoformat(p.name[:10]) for p in PROJ_DIR.glob("*.csv.gz"))


def record() -> dict:
    """Running record over every graded player-game: typical miss of the model vs season average,
    per stat, and how often ⬆️/⬇️ flags landed on the right side."""
    frames = [load_day(d) for d in all_days()]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return {"graded": 0}
    d = pd.concat(frames, ignore_index=True)
    g = d[d["status"] == "graded"]
    out = {"updated_utc": utc_now_iso(), "graded": int(len(g)), "dnp": int((d["status"] == "dnp").sum()),
           "days": int(g["game_date"].nunique()), "stats": {}}
    # Top 5: picked from each day's locked projections, graded like everything else (DNP = voided)
    t5 = {"picks": 0, "hits": 0, "voided": 0, "nights": 0, "said": 0.0}
    for f in frames:
        if (f["status"].fillna("") == "").any():
            continue                                             # day not fully graded yet
        picks = top_picks(f)
        if picks.empty:
            continue
        t5["nights"] += 1
        for p in picks.itertuples():
            hit = pick_hit(f.loc[p.i], p.stat, p.dir)
            if hit is None:
                t5["voided"] += 1
            else:
                t5["picks"] += 1
                t5["hits"] += int(hit)
                t5["said"] += float(p.chance)
    t5["said"] = t5["said"] / t5["picks"] if t5["picks"] else None
    out["top5"] = t5
    for stat in pj.TARGETS:
        y, p, b = g[f"act_{stat}"], g[f"p_{stat}"], g[f"avg_{stat}"]
        s = {"mae_model": float((p - y).abs().mean()) if len(g) else None,
             "mae_season_avg": float((b - y).abs().mean()) if len(g) else None,
             "in_range": float(((y >= np.floor(g[f"lo_{stat}"])) & (y <= np.ceil(g[f"hi_{stat}"]))).mean()) if len(g) else None}
        if stat in FLAG_STATS:
            f = g[f"flag_{stat}"].fillna("")
            up, dn = f == "up", f == "down"
            s.update({"up": int(up.sum()), "up_hit": int((y[up] > b[up]).sum()),
                      "down": int(dn.sum()), "down_hit": int((y[dn] < b[dn]).sum())})
        out["stats"][stat] = s
    return out


def save_record() -> dict:
    r = record()
    atomic_write_json(r, RECORD_PATH)
    return r


def load_record() -> dict | None:
    return json.loads(RECORD_PATH.read_text()) if RECORD_PATH.exists() else None
