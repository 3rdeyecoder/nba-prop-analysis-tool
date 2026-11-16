"""Train the NBA player projection models (minutes, points, rebounds, assists, 3PM, steals, blocks,
turnovers) and write their report.

    python -m refresh.train_projections

Writes data/models/nba_proj.json (plain numbers; the app needs no scikit-learn) and
data/models/nba_proj_report.json. Held-out results are rolling: each test season is scored by
models trained only on earlier seasons. The baseline is the player's season average so far.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from core.storage import atomic_write_json, utc_now_iso
from refresh.common import setup_logging
from sports import nba_matchup as m
from sports import nba_projections as pj

FLAG = 0.25                      # ⬆️/⬇️ when the projection is 25%+ above/below the season average
FLAG_MIN_AVG = {"MIN": 10, "PTS": 4, "REB": 2, "AST": 2, "FG3M": 1}


def baseline(rows: pd.DataFrame, stat: str) -> pd.Series:
    ew = rows["min_ew"] if stat == "MIN" else rows[f"{stat}_ew"]
    return rows[f"{stat}_season"].where(rows["season_gp"] >= 3, ew)


def main(argv: list[str] | None = None) -> int:
    log = setup_logging()
    logs = m.load_logs()
    rows = pj.build_rows(logs)
    rows = rows[rows["career_gp"] >= pj.MIN_CAREER_GAMES]
    counts = rows.groupby("season").size()
    done = [s for s in sorted(counts.index) if counts[s] >= 20000]          # completed seasons
    tests = done[-2:] + [s for s in counts.index if s not in done][-1:]      # last 2 full + current
    log.info("player-games: %d | completed seasons %s..%s | held-out %s", len(rows), done[0], done[-1], tests)

    held = []
    for s in tests:
        model = pj.train(rows, [x for x in done if x < s])
        te = rows[rows["season"] == s]
        held.append(te[["season", "PLAYER_ID", "date", "season_gp"] + pj.TARGETS].assign(
            **{f"p_{t}": pj.predict(model, te, t) for t in pj.TARGETS},
            **{f"b_{t}": baseline(te, t).to_numpy() for t in pj.TARGETS}))
    h = pd.concat(held, ignore_index=True)

    stats = []
    for t in pj.TARGETS:
        y, p, b = h[t], h[f"p_{t}"], h[f"b_{t}"]
        lo, hi = pj.predict_range(model, p.to_numpy(), t)
        row = {"stat": t, "label": pj.LABELS[t], "games": int(len(h)),
               "mae_model": float((p - y).abs().mean()), "mae_season_avg": float((b - y).abs().mean()),
               "rmse_model": float(np.sqrt(((p - y) ** 2).mean())), "rmse_season_avg": float(np.sqrt(((b - y) ** 2).mean())),
               "range_coverage": float(((y >= np.floor(lo)) & (y <= np.ceil(hi))).mean())}
        if t in FLAG_MIN_AVG:
            ok = b >= FLAG_MIN_AVG[t]
            up, dn = ok & (p >= b * (1 + FLAG)), ok & (p <= b * (1 - FLAG))
            row.update({"up_flags": int(up.sum()), "up_hit": float((y[up] > b[up]).mean()),
                        "down_flags": int(dn.sum()), "down_hit": float((y[dn] < b[dn]).mean()),
                        "above_avg_normally": float((y[ok] > b[ok]).mean())})
        stats.append(row)

    # calibration of "chance to finish above/below his season average", from the held-out seasons
    calibration, top5 = {}, {}
    for t in pj.CHANCE_STATS:
        ok = (h["season_gp"] >= 5) if "season_gp" in h else np.ones(len(h), bool)
        y, p, b = h.loc[ok, t].to_numpy(), h.loc[ok, f"p_{t}"].to_numpy(), h.loc[ok, f"b_{t}"].to_numpy()
        calibration[t] = {d: pj.calibrate_table(pj.raw_chance(model, p, b, t, d), (y > b) if d == "over" else (y < b))
                          for d in ("over", "under")}
    final_cal = {"calibration": calibration}
    # Top 5 per night, as the page picks them, on the held-out seasons
    cand = []
    for t in pj.CHANCE_STATS:
        ok = (h["season_gp"] >= 5) & (h[f"b_{t}"] >= pj.PICK_MIN_AVG[t])
        x = h[ok]
        for d in ("over", "under"):
            c = pj.chance({**model, **final_cal}, x[f"p_{t}"], x[f"b_{t}"], t, d)
            hit = (x[t] > x[f"b_{t}"]) if d == "over" else (x[t] < x[f"b_{t}"])
            cand.append(pd.DataFrame({"date": x["date"].to_numpy(), "player": x["PLAYER_ID"].to_numpy(), "c": c,
                                      "hit": hit.to_numpy()}))
    cand = pd.concat(cand).sort_values("c", ascending=False).drop_duplicates(["date", "player"])
    picks = cand.groupby("date").head(5)
    nightly = picks.groupby("date")["hit"].sum()
    top5 = {"nights": int(nightly.size), "picks": int(len(picks)), "hit_rate": float(picks["hit"].mean()),
            "said": float(picks["c"].mean()), "five_for_five": float((nightly == 5).mean()),
            "four_plus": float((nightly >= 4).mean())}

    final = pj.train(rows, done)
    final.update({"created_utc": utc_now_iso(), "flag": FLAG, "flag_min_avg": FLAG_MIN_AVG, **final_cal})
    atomic_write_json(final, pj.MODEL_PATH)
    atomic_write_json({"created_utc": utc_now_iso(), "held_out_seasons": tests, "stats": stats, "top5": top5,
                       "calibration": calibration}, pj.REPORT_PATH)
    log.info("Top 5 per night (held out): %.1f%% hit (model said %.1f%%); 5-for-5 on %.0f%% of nights, 4+ on %.0f%%",
             100 * top5["hit_rate"], 100 * top5["said"], 100 * top5["five_for_five"], 100 * top5["four_plus"])
    for r in stats:
        log.info("%-10s typical miss %.2f (season avg %.2f) | middle-half range holds %.0f%%%s", r["label"],
                 r["mae_model"], r["mae_season_avg"], 100 * r["range_coverage"],
                 f" | up flags {100*r['up_hit']:.0f}% / down {100*r['down_hit']:.0f}%" if "up_hit" in r else "")
    log.info("saved %s (trained on %d player-games)", pj.MODEL_PATH.name, final["train_rows"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
