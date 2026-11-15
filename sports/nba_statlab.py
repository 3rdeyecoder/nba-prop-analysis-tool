"""Stat Lab: candidate features, each tested on held-out seasons before it may join the model.

Selection rule (set before looking at results): a candidate is kept only if adding it to the base
model lowers log loss overall AND in at least KEEP_MIN_SEASONS of the held-out seasons.

Every candidate uses only information known before tip-off. Columns are added to the team-game
feature table with an `x_` prefix; nba_model.game_rows turns them into A-minus-B differences.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

KEEP_MIN_SEASONS = 4

# Arena locations (lat, lon), UTC offset in standard time, and altitude flag.
# Games are located at the home team's arena; neutral-site games get no travel value.
ARENAS = {
    "ATL": (33.757, -84.396, -5), "BOS": (42.366, -71.062, -5), "BKN": (40.683, -73.975, -5),
    "CHA": (35.225, -80.839, -5), "CHI": (41.881, -87.674, -6), "CLE": (41.496, -81.688, -5),
    "DAL": (32.790, -96.810, -6), "DEN": (39.749, -105.008, -7), "DET": (42.341, -83.055, -5),
    "GSW": (37.768, -122.388, -8), "HOU": (29.751, -95.362, -6), "IND": (39.764, -86.155, -5),
    "LAC": (33.945, -118.341, -8), "LAL": (34.043, -118.267, -8), "MEM": (35.138, -90.051, -6),
    "MIA": (25.781, -80.188, -5), "MIL": (43.045, -87.917, -6), "MIN": (44.979, -93.276, -6),
    "NOP": (29.949, -90.082, -6), "NYK": (40.751, -73.993, -5), "OKC": (35.463, -97.515, -6),
    "ORL": (28.539, -81.384, -5), "PHI": (39.901, -75.172, -5), "PHX": (33.446, -112.071, -7),
    "POR": (45.532, -122.667, -8), "SAC": (38.580, -121.500, -8), "SAS": (29.427, -98.438, -6),
    "TOR": (43.643, -79.379, -5), "UTA": (40.768, -111.901, -7), "WAS": (38.898, -77.021, -5),
}
ALTITUDE = {"DEN", "UTA"}


def miles(a: str | None, b: str | None) -> float:
    if a not in ARENAS or b not in ARENAS:
        return np.nan
    la1, lo1, _ = ARENAS[a]
    la2, lo2, _ = ARENAS[b]
    p1, p2, dl = math.radians(la1), math.radians(la2), math.radians(lo2 - lo1)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return 3958.8 * math.acos(max(-1.0, min(1.0, c)))


def game_locations(f: pd.DataFrame) -> pd.Series:
    """Arena (home team abbreviation) for each game_id; None for neutral sites."""
    home = f[f["venue"] == 1].set_index("game_id")["team"]
    return pd.Series({gid: home.get(gid) for gid in f["game_id"].unique()})


def add_fatigue(f: pd.DataFrame) -> pd.DataFrame:
    """Travel and altitude features. Distances are between arenas of consecutive games."""
    f = f.sort_values(["team", "date", "game_id"]).copy()
    loc = f["game_id"].map(game_locations(f))
    prev_loc = loc.groupby(f["team"]).shift(1)
    same_season = f["season"].eq(f.groupby("team")["season"].shift(1))
    leg = pd.Series([miles(a, b) for a, b in zip(prev_loc, loc)], index=f.index).where(same_season)
    f["x_travel"] = (leg.fillna(0) / 1000).where(loc.notna(), 0.0)          # thousands of miles since last game
    tz = loc.map(lambda t: ARENAS[t][2] if t in ARENAS else np.nan)
    f["x_tz_shift"] = (tz - tz.groupby(f["team"]).shift(1)).abs().where(same_season).fillna(0)

    # miles in the last 4 days, counting legs into games played within that window (this one included)
    dates = f["date"].values
    teams = f["team"].values
    legs = f["x_travel"].values
    out = np.zeros(len(f))
    start = 0
    for i in range(len(f)):
        if i and teams[i] != teams[i - 1]:
            start = i
        j = i
        total = 0.0
        while j >= start and dates[j] >= dates[i] - np.timedelta64(3, "D"):
            total += legs[j]
            j -= 1
        out[i] = total
    f["x_miles4"] = out
    f["x_road_b2b"] = ((f["b2b"] == 1) & (f["venue"] == -1)).astype(int)
    f["x_altitude_visit"] = ((f["venue"] == -1) & loc.isin(ALTITUDE)).astype(int)
    return f.sort_values(["date", "game_id", "team"]).reset_index(drop=True)


def add_opponent_adjusted_form(f: pd.DataFrame, window: int = 10, shrink_games: int = 10) -> pd.DataFrame:
    """Last-10 average of (margin per 100 possessions + the opponent's pregame net rating).
    Beating good teams counts more than beating bad ones."""
    opp = f[["game_id", "team", "s_net", "gp"]].rename(columns={"team": "opp", "s_net": "o_net", "gp": "o_gp"})
    x = f.merge(opp, on=["game_id", "opp"], how="left")
    x["o_strength"] = x["o_net"].fillna(0) * x["o_gp"] / (x["o_gp"] + shrink_games)
    x["adj_game"] = 100 * x["margin"] / x["poss"] + x["o_strength"]
    x = x.sort_values(["team", "date", "game_id"])
    x["x_adj_form"] = (x.groupby(["team", "season"])["adj_game"]
                         .transform(lambda s: s.shift(1).rolling(window, min_periods=3).mean())).fillna(0)
    return f.merge(x[["game_id", "team", "x_adj_form"]], on=["game_id", "team"], how="left")


def add_roster_features(f: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    """From the available rotation (players in the team's previous game this season):
    x_continuity  share of expected minutes from players who played for this team last season
    x_star        best available player's rating minus the rotation's weighted average"""
    from sports.nba_players import ROTATION

    r = ratings.sort_values(["team", "season", "date", "game_id"]).reset_index(drop=True)
    seasons = sorted(r["season"].unique())
    prev_season = {s: seasons[i - 1] for i, s in enumerate(seasons) if i}
    was_here = set(zip(r["team"], r["season"], r["player_id"]))
    r["returning"] = [(t, prev_season.get(s), p) in was_here for t, s, p in zip(r["team"], r["season"], r["player_id"])]
    r["has_prior"] = r["season"].map(lambda s: s in prev_season)

    rows = []
    for (team, season), tg in r.groupby(["team", "season"], sort=False):
        games = list(dict.fromkeys(tg["game_id"]))
        by_game = {gid: x for gid, x in tg.groupby("game_id", sort=False)}
        for k, gid in enumerate(games):
            if k == 0:
                x = by_game[gid]
                w, gs = x["exp_min"].fillna(x["minutes"]).to_numpy(), x["gs36"].to_numpy()
            else:
                x = by_game[games[k - 1]]
                w, gs = x["exp_min_post"].to_numpy(), x["gs36_post"].to_numpy()
            w = np.clip(np.nan_to_num(w), 0, None)
            if len(w) > ROTATION:
                keep = np.argsort(-w)[:ROTATION]
                x, w, gs = x.iloc[keep], w[keep], gs[keep]
            total = w.sum()
            cont = float((w * x["returning"].to_numpy()).sum() / total) if total > 0 and x["has_prior"].iloc[0] else np.nan
            avg = float((w * gs).sum() / total) if total > 0 else np.nan
            rows.append((gid, team, cont, float(np.max(gs)) - avg if len(gs) else np.nan))
    extra = pd.DataFrame(rows, columns=["game_id", "team", "x_continuity", "x_star"])
    f = f.merge(extra, on=["game_id", "team"], how="left")
    f["x_continuity"] = f["x_continuity"].fillna(f["x_continuity"].mean())
    f["x_star"] = f["x_star"].fillna(0)
    return f


CANDIDATES = {
    "Fatigue Index (travel, time zones, road back-to-backs, altitude)":
        ["x_travel_d", "x_miles4_d", "x_tz_shift_d", "x_road_b2b_d", "x_altitude_visit_d"],
    "Roster continuity": ["x_continuity_d"],
    "Opponent-adjusted form": ["x_adj_form_d"],
    "Star power": ["x_star_d"],
}


def run(rows: pd.DataFrame, base: list[str], test_seasons: list[str]) -> pd.DataFrame:
    """Log loss of base vs base + each candidate, per held-out season, with the keep/drop verdict."""
    from sports import nba_model as nm

    def per_season(features):
        pred = nm.evaluate(rows, features, "logistic", test_seasons)
        return {s: nm.scores(pred[pred["season"] == s])["log_loss"] for s in test_seasons} | \
               {"all": nm.scores(pred)["log_loss"]}

    base_ll = per_season(base)
    out = []
    for name, cols in CANDIDATES.items():
        ll = per_season(base + cols)
        better = sum(ll[s] < base_ll[s] for s in test_seasons)
        out.append({"candidate": name, "base_log_loss": base_ll["all"], "with_candidate": ll["all"],
                    "change": ll["all"] - base_ll["all"], "seasons_better": f"{better} of {len(test_seasons)}",
                    "keep": ll["all"] < base_ll["all"] and better >= KEEP_MIN_SEASONS})
    return pd.DataFrame(out)
