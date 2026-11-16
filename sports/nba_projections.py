"""NBA player projections: minutes, points, rebounds, assists, 3-pointers, steals, blocks, turnovers.

Every number used for a game is known before tip-off. The trick that keeps training and live
predictions identical: for each player we compute a running "state" AFTER every game he plays
(decayed averages, per-minute rates, season averages). The pregame state for a game is simply the
state after his previous game; for tonight it is the state after his latest game.

Context added per game (also pregame only):
  opponent    how much of each stat the opponent allows per possession vs the league (season to date)
  pace        both teams' possessions per game vs the league
  teammates   share of the team's usual minutes that is missing (regulars who sat out the last game)
  blowout     how mismatched the two teams are (lopsided games mean fewer starter minutes)
  schedule    home/away, days of rest, back-to-back, returning from an absence
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STATS = ["PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV"]
TARGETS = ["MIN"] + STATS
LABELS = {"MIN": "Minutes", "PTS": "Points", "REB": "Rebounds", "AST": "Assists", "FG3M": "3-pointers",
          "STL": "Steals", "BLK": "Blocks", "TOV": "Turnovers"}
SHORT = {"MIN": "MIN", "PTS": "PTS", "REB": "REB", "AST": "AST", "FG3M": "3PM", "STL": "STL", "BLK": "BLK",
         "TOV": "TOV"}

HL_GAMES = 10          # recent form: a game 10 games ago counts half
HL_RATE = 25           # per-minute skill: slower to change
HL_MIN = 6             # minutes react fastest (role changes)
TEAM_PRIOR_GAMES = 8   # opponent/pace factors start this many games' worth at league average
REST_CAP = 7


def _poss(d: pd.DataFrame) -> pd.Series:
    return d["FGA"] - d["OREB"] + d["TOV"] + 0.44 * d["FTA"]


# ---------------------------------------------------------------- player state (after each game)

def player_games(logs: pd.DataFrame) -> pd.DataFrame:
    d = logs.copy()
    d["date"] = pd.to_datetime(d["GAME_DATE"])
    d["game_id"] = d["GAME_ID"].astype(str).str.zfill(10)
    d["team"] = d["TEAM_ABBREVIATION"]
    d["opp"] = d["MATCHUP"].str[-3:]
    d["home"] = d["MATCHUP"].str.contains("vs.", regex=False).astype(int)
    d["MIN"] = d["MIN"].fillna(0).astype(float)
    d["usage"] = d["FGA"] + 0.44 * d["FTA"] + d["TOV"]
    return d.sort_values(["PLAYER_ID", "date", "game_id"]).reset_index(drop=True)


def player_state(pg: pd.DataFrame) -> pd.DataFrame:
    """Per player-game, the player's numbers AFTER that game (only games he played, MIN > 0)."""
    d = pg[pg["MIN"] > 0].copy()
    g = d.groupby("PLAYER_ID", sort=False)
    out = d[["PLAYER_ID", "PLAYER_NAME", "season", "game_id", "date", "team"]].copy()

    def ewm(col, hl):
        return g[col].transform(lambda s: s.ewm(halflife=hl).mean())

    out["min_ew"] = ewm("MIN", HL_MIN)
    out["min_l3"] = g["MIN"].transform(lambda s: s.rolling(3, min_periods=1).mean())
    long_min = ewm("MIN", HL_RATE)
    for s in STATS + ["usage", "FGA", "FTA"]:
        out[f"{s}_ew"] = ewm(s, HL_GAMES)
        out[f"{s}_rate"] = ewm(s, HL_RATE) / long_min.clip(lower=1)          # per minute
    gs = d.groupby(["PLAYER_ID", "season"], sort=False)
    for s in TARGETS:
        out[f"{s}_season"] = gs[s].transform(lambda x: x.expanding().mean())
    out["season_gp"] = gs.cumcount() + 1
    out["career_gp"] = g.cumcount() + 1
    return out


# ---------------------------------------------------------------- team context (pregame)

def team_totals(pg: pd.DataFrame) -> pd.DataFrame:
    """Per team-game totals and the opponent's totals, plus possessions."""
    cols = STATS + ["FGA", "FTA", "OREB", "MIN"]
    t = pg.groupby(["game_id", "season", "date", "team", "opp"], as_index=False)[cols].sum()
    t["poss"] = _poss(t)
    o = t[["game_id", "team"] + STATS + ["poss"]].rename(columns={"team": "opp", **{c: f"opp_{c}" for c in STATS},
                                                                  "poss": "opp_poss"})
    return t.merge(o, on=["game_id", "opp"], how="left").sort_values(["date", "game_id", "team"]).reset_index(drop=True)


def team_context(tt: pd.DataFrame) -> pd.DataFrame:
    """Per team-game, BEFORE the game: pace and how much of each stat the team allows per possession,
    both relative to the league so far this season (1.0 = average), shrunk toward average early on."""
    t = tt.copy()
    t["pace_g"] = (t["poss"] + t["opp_poss"]) / 2
    g = t.groupby(["team", "season"], sort=False)
    n = g.cumcount()                                                     # games before this one
    prior = lambda c: g[c].transform(lambda s: s.cumsum().shift(1, fill_value=0))  # noqa: E731

    # league so far this season, strictly before each date
    daily = t.groupby(["season", "date"])[["pace_g"] + [f"opp_{s}" for s in STATS] + ["opp_poss"]].sum()
    daily["n"] = t.groupby(["season", "date"]).size()
    cum = daily.groupby(level=0).cumsum().groupby(level=0).shift(1)
    lg = cum.reindex(pd.MultiIndex.from_frame(t[["season", "date"]]))
    lg.index = t.index
    lg_pace = (lg["pace_g"] / lg["n"]).fillna(t.groupby("season")["pace_g"].transform("mean"))
    out = t[["game_id", "season", "date", "team", "opp"]].copy()
    k = TEAM_PRIOR_GAMES
    out["pace"] = ((prior("pace_g") + k * lg_pace) / (n + k)) / lg_pace
    poss_allowed = prior("opp_poss")
    for s in STATS:
        lg_rate = (lg[f"opp_{s}"] / lg["opp_poss"]).fillna((t[f"opp_{s}"].groupby(t["season"]).transform("sum")
                                                            / t["opp_poss"].groupby(t["season"]).transform("sum")))
        out[f"allow_{s}"] = ((prior(f"opp_{s}") + k * 100 * lg_rate) / (poss_allowed + k * 100)) / lg_rate
    out["gp"] = n
    return out


# ---------------------------------------------------------------- the training / prediction table

def design(rows: pd.DataFrame, stat: str) -> pd.DataFrame:
    """Model inputs for one stat. Mostly logs, so effects multiply (e.g. a defense that allows 10%
    more rebounds raises a projection by about 10%)."""
    eps = 0.05
    x = pd.DataFrame(index=rows.index)
    x["log_min_ew"] = np.log(rows["min_ew"].clip(lower=1))
    x["log_min_l3"] = np.log(rows["min_l3"].clip(lower=1))
    if stat == "MIN":
        x["log_min_season"] = np.log(rows["MIN_season"].clip(lower=1))
        x["log_usage_rate"] = np.log(rows["usage_rate"].clip(lower=0.01))
    else:
        x["log_rate"] = np.log(rows[f"{stat}_rate"].clip(lower=0.002))
        x["log_ew"] = np.log(rows[f"{stat}_ew"] + eps)
        x["log_season"] = np.log(rows[f"{stat}_season"] + eps)
        x["log_allow"] = np.log(rows[f"opp_allow_{stat}"])
        x["log_usage_rate"] = np.log(rows["usage_rate"].clip(lower=0.01))
    x["log_pace"] = np.log(rows["pace_team"] * rows["pace_opp"])
    x["missing"] = rows["missing_min_share"]
    x["missing_x_usage"] = rows["missing_min_share"] * rows["usage_rate"] * 10
    x["home"] = rows["home"]
    x["rest"] = rows["rest"].clip(upper=REST_CAP)
    x["b2b"] = (rows["rest"] <= 1).astype(int)
    x["returning"] = rows["returning"]
    x["blowout"] = rows["mismatch"].abs()
    x["log_career"] = np.log1p(rows["career_gp"])
    x["early_season"] = 1 / (1 + rows["season_gp"])
    return x


def build_rows(logs: pd.DataFrame, team_feats: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per player-game played (MIN > 0) with that player's pregame state + game context +
    the actual result (for training)."""
    pg = player_games(logs)
    st = player_state(pg)
    state_cols = [c for c in st.columns if c not in ("PLAYER_ID", "PLAYER_NAME", "season", "game_id", "date", "team")]
    pre = st.copy()
    pre[state_cols] = st.groupby("PLAYER_ID")[state_cols].shift(1)       # state after the PREVIOUS game
    pre["prev_date"] = st.groupby("PLAYER_ID")["date"].shift(1)
    played = pg[pg["MIN"] > 0]
    rows = played[["PLAYER_ID", "PLAYER_NAME", "season", "game_id", "date", "team", "opp", "home"] + TARGETS] \
        .merge(pre.drop(columns=["PLAYER_NAME", "season", "date", "team"]), on=["PLAYER_ID", "game_id"])
    rows = rows.dropna(subset=["min_ew"])
    rows["rest"] = (rows["date"] - rows["prev_date"]).dt.days
    rows = add_context(rows, pg, team_feats)
    return rows.reset_index(drop=True)


def add_context(rows: pd.DataFrame, pg: pd.DataFrame, team_feats: pd.DataFrame | None) -> pd.DataFrame:
    """Opponent, pace, missing teammates, blowout risk and 'returning' for each player-game row.
    `rows` needs game_id, team, opp, PLAYER_ID; team-game context comes from games before each game."""
    ctx = team_context(team_totals(pg))
    c = ctx.set_index(["game_id", "team"])
    rows = rows.join(c[["pace"]].rename(columns={"pace": "pace_team"}), on=["game_id", "team"])
    opp = c[["pace"] + [f"allow_{s}" for s in STATS]].rename(
        columns={"pace": "pace_opp", **{f"allow_{s}": f"opp_allow_{s}" for s in STATS}})
    rows = rows.merge(opp.reset_index().rename(columns={"team": "opp"}), on=["game_id", "opp"], how="left")
    rows = rows.merge(_team_extras(pg, team_feats), on=["game_id", "team"], how="left")
    rows = rows.merge(_returning(pg), on=["game_id", "PLAYER_ID"], how="left")
    rows["returning"] = rows["returning"].fillna(0)
    rows["missing_min_share"] = rows["missing_min_share"].fillna(0)
    rows["mismatch"] = rows["mismatch"].fillna(0)
    for col in ["pace_team", "pace_opp"] + [f"opp_allow_{s}" for s in STATS]:
        rows[col] = rows[col].fillna(1.0)
    return rows


def _team_extras(pg: pd.DataFrame, team_feats: pd.DataFrame | None) -> pd.DataFrame:
    """Missing regulars (minute share) and the pregame team mismatch (shrunk net rating difference)."""
    from sports import nba_matchup as m
    if team_feats is None:
        logs = pg.drop(columns=["date", "game_id", "team", "opp", "home", "usage"])
        f = m.pregame_features(m.team_games(logs))
        miss = m.missing_regulars(logs)
        f = f.merge(miss, on=["game_id", "team"], how="left")
    else:
        f = team_feats
    f = f[["game_id", "team", "opp", "gp", "s_net", "missing_min_share"]].copy()
    f["net_shrunk"] = f["s_net"].fillna(0) * f["gp"] / (f["gp"] + 10)
    o = f[["game_id", "team", "net_shrunk"]].rename(columns={"team": "opp", "net_shrunk": "opp_net"})
    f = f.merge(o, on=["game_id", "opp"], how="left")
    f["mismatch"] = f["net_shrunk"] - f["opp_net"].fillna(0)
    return f[["game_id", "team", "missing_min_share", "mismatch"]]


def _returning(pg: pd.DataFrame) -> pd.DataFrame:
    """1 if the player did not play in his team's previous game this season (back from an absence)."""
    rows = []
    for (team, season), tg in pg.groupby(["team", "season"], sort=False):
        order = tg.groupby("game_id")["date"].first().sort_values().index.tolist()
        played = {gid: set(x.loc[x["MIN"] > 0, "PLAYER_ID"]) for gid, x in tg.groupby("game_id")}
        for i, gid in enumerate(order[1:], start=1):
            prev = played[order[i - 1]]
            for pid in played[gid]:
                if pid not in prev:
                    rows.append((gid, pid, 1))
    return pd.DataFrame(rows, columns=["game_id", "PLAYER_ID", "returning"]).drop_duplicates()


# ---------------------------------------------------------------- tonight's rows (same code as training)

ROTATION_WINDOW = 10      # a player is projected if he played in one of his team's last 10 games
MIN_MINUTES = 8.0         # ... and his recent minutes average at least this


def live_rows(logs: pd.DataFrame, slate: pd.DataFrame, as_of) -> pd.DataFrame:
    """Rows for tonight's games (`slate`: game_id, home, away), built with only games before `as_of`.
    Each game gets a placeholder box score so team context (pace, opponent defense, missing
    regulars, mismatch) comes from exactly the same functions as training."""
    from sports.nba_matchup import BOX

    as_of = pd.Timestamp(as_of).normalize()
    past = logs[pd.to_datetime(logs["GAME_DATE"]) < as_of]
    season = past["season"].max()
    team_ids = past.groupby("TEAM_ABBREVIATION")["TEAM_ID"].last()
    fake = []
    for g in slate.itertuples():
        for team, opp, word in ((g.home, g.away, "vs."), (g.away, g.home, "@")):
            fake.append({"season": season, "GAME_ID": str(g.game_id), "GAME_DATE": as_of.strftime("%Y-%m-%d"),
                         "TEAM_ID": team_ids.get(team, -1), "TEAM_ABBREVIATION": team, "MATCHUP": f"{team} {word} {opp}",
                         "WL": "W", "PLAYER_ID": -1, "PLAYER_NAME": "", "PLUS_MINUS": 0,
                         **{c: 0 for c in BOX}, "FGA": 1})
    pg = player_games(pd.concat([past, pd.DataFrame(fake)], ignore_index=True))

    real = pg[pg["MIN"] > 0]
    st = player_state(real)
    last = st.groupby("PLAYER_ID").tail(1)
    last = last[(last["season"] == season)]
    team_games_order = real[real["season"] == season].groupby("team")["game_id"].apply(
        lambda s: list(dict.fromkeys(s[real.loc[s.index, "date"].sort_values().index])))
    rows = []
    sides = {g.home: (str(g.game_id), g.away, 1) for g in slate.itertuples()} | \
            {g.away: (str(g.game_id), g.home, 0) for g in slate.itertuples()}
    for team, (gid, opp, home) in sides.items():
        recent = team_games_order.get(team, [])[-ROTATION_WINDOW:]
        if not recent:
            continue
        in_recent = set(real.loc[real["game_id"].isin(recent) & (real["team"] == team), "PLAYER_ID"])
        last_game_players = set(real.loc[(real["game_id"] == recent[-1]) & (real["team"] == team), "PLAYER_ID"])
        cand = last[(last["team"] == team) & last["PLAYER_ID"].isin(in_recent) & (last["min_ew"] >= MIN_MINUTES)]
        for r in cand.itertuples(index=False):
            rows.append({**r._asdict(), "game_id": gid, "date": as_of, "opp": opp, "home": home,
                         "rest": (as_of - r.date).days, "returning": int(r.PLAYER_ID not in last_game_players)})
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).drop(columns=["returning"])
    ret = pd.DataFrame(rows)[["PLAYER_ID", "game_id", "returning"]]
    out = add_context(out, pg, None).drop(columns=["returning"]).merge(ret, on=["PLAYER_ID", "game_id"])
    return out.reset_index(drop=True)


# ---------------------------------------------------------------- model: train, save, predict (plain numbers)

from core.config import DATA_DIR  # noqa: E402

MODEL_PATH = DATA_DIR / "models" / "nba_proj.json"
REPORT_PATH = DATA_DIR / "models" / "nba_proj_report.json"
MIN_CAREER_GAMES = 3
RANGE_Z = 0.674           # middle half: 25th to 75th percentile


def train(rows: pd.DataFrame, seasons: list[str]) -> dict:
    """One Poisson regression per stat (log link) on design(); saved as plain numbers."""
    from sklearn.linear_model import PoissonRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    tr = rows[rows["season"].isin(seasons) & (rows["career_gp"] >= MIN_CAREER_GAMES)]
    models = {}
    for stat in TARGETS:
        x = design(tr, stat)
        pipe = make_pipeline(StandardScaler(), PoissonRegressor(alpha=1e-4, max_iter=1000)).fit(x, tr[stat])
        sc, lr = pipe.named_steps["standardscaler"], pipe.named_steps["poissonregressor"]
        mu = pipe.predict(x)
        models[stat] = {"features": list(x.columns), "mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(),
                        "coef": lr.coef_.tolist(), "intercept": float(lr.intercept_),
                        "dispersion": float(np.mean((tr[stat] - mu) ** 2 / np.clip(mu, 0.05, None)))}
    return {"stats": models, "train_seasons": list(seasons), "train_rows": int(len(tr))}


def predict(model: dict, rows: pd.DataFrame, stat: str) -> np.ndarray:
    m = model["stats"][stat]
    x = design(rows, stat)[m["features"]].to_numpy(float)
    z = (x - np.array(m["mean"])) / np.array(m["scale"])
    return np.exp(z @ np.array(m["coef"]) + m["intercept"])


def predict_range(model: dict, mu: np.ndarray, stat: str) -> tuple[np.ndarray, np.ndarray]:
    """Middle half of likely outcomes (25th-75th percentile), from the stat's spread."""
    sd = np.sqrt(model["stats"][stat]["dispersion"] * mu)
    return np.clip(mu - RANGE_Z * sd, 0, None), mu + RANGE_Z * sd


# what each reason switches back to "neutral" (an average opponent, normal rest, nobody missing...)
CONTEXT = {
    "Opponent": {"log_allow": 0.0},
    "Pace": {"log_pace": 0.0},
    "Teammates out": {"missing": 0.0, "missing_x_usage": 0.0},
    "Home/away": {"home": 0.5},
    "Rest": {"rest": 2.0, "b2b": 0.0},
    "Back from absence": {"returning": 0.0},
    "Blowout risk": {"blowout": 0.0},
}


def context_effects(model: dict, rows: pd.DataFrame, stat: str) -> pd.DataFrame:
    """For each row: % change in the projection caused by each context reason vs a neutral setting."""
    m = model["stats"][stat]
    x = design(rows, stat)[m["features"]]
    w = np.array(m["coef"]) / np.array(m["scale"])
    out = pd.DataFrame(index=rows.index)
    for name, neutral in CONTEXT.items():
        cols = [c for c in neutral if c in m["features"]]
        if not cols:
            continue
        idx = [m["features"].index(c) for c in cols]
        delta = sum(w[i] * (x[c].to_numpy(float) - neutral[c]) for i, c in zip(idx, cols))
        out[name] = np.exp(delta) - 1
    return out


def save_model(model: dict, path=MODEL_PATH) -> None:
    from core.storage import atomic_write_json
    atomic_write_json(model, path)


def load_model(path=MODEL_PATH) -> dict | None:
    import json
    return json.loads(path.read_text()) if path.exists() else None


# ---------------------------------------------------------------- chance of finishing above / below his average

CAL_BINS = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
CHANCE_STATS = ["PTS", "REB", "AST"]
PICK_MIN_AVG = {"PTS": 8.0, "REB": 2.0, "AST": 2.0}     # Top 5 only considers meaningful averages


def raw_chance(model: dict, mu, avg, stat: str, direction: str) -> np.ndarray:
    """Model's chance (before calibration) that the stat finishes above ('over') or below ('under') `avg`,
    from the projection and the stat's spread (normal approximation with a half-point correction)."""
    from math import erf, sqrt
    mu, avg = np.asarray(mu, float), np.asarray(avg, float)
    sd = np.sqrt(np.maximum(model["stats"][stat]["dispersion"] * mu, 1e-6))
    phi = np.vectorize(lambda z: 0.5 * (1 + erf(z / sqrt(2))))
    if direction == "over":
        return 1 - phi((np.ceil(avg + 1e-9) - 0.5 - mu) / sd)
    return phi((np.floor(avg - 1e-9) + 0.5 - mu) / sd)


def calibrate_table(p: np.ndarray, hit: np.ndarray) -> list[list[float]]:
    """[(bin_mid_predicted, actual_rate, count)] on held-out seasons."""
    out = []
    for lo, hi in zip(CAL_BINS[:-1], CAL_BINS[1:]):
        k = (p > lo) & (p <= hi)
        if k.sum() >= 30:
            out.append([float(p[k].mean()), float(hit[k].mean()), int(k.sum())])
    return out


def chance(model: dict, mu, avg, stat: str, direction: str) -> np.ndarray:
    """Calibrated chance: the raw chance mapped onto how often such calls came true on past seasons."""
    raw = raw_chance(model, mu, avg, stat, direction)
    cal = model.get("calibration", {}).get(stat, {}).get(direction)
    if not cal:
        return raw
    xs, ys = [c[0] for c in cal], [c[1] for c in cal]
    ys = np.maximum.accumulate(ys)                               # never let a higher raw chance map lower
    return np.interp(raw, [0.0] + xs + [1.0], [0.0] + list(ys) + [max(ys[-1], xs[-1])])
