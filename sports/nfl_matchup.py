"""NFL team features for Upset Watch, all known before kickoff.

Data (nflverse, CC-BY 4.0), saved by refresh/nfl_games.py:
  data/nfl/games.parquet       every game since 2010: teams, scores, rest, listed starting QBs
  data/nfl/team_games.parquet  each team's offense in each game: plays, EPA, turnovers
  data/nfl/qb_games.parquet    each quarterback's dropbacks, runs and EPA in each game

Football seasons are short (17 games), so most ratings here carry over from earlier games with a
decay instead of resetting each September:
  elo        FiveThirtyEight-style Elo with margin of victory; a third regresses to average each offseason
  off_epa    expected points added per offensive play (higher is better)
  def_epa    EPA per play the defense allowed (lower is better)
  margin     points per game margin
  qb_epa     the listed starting quarterback's own EPA per play over his recent games, any team
All of these are averaged over earlier games only (the decay counts games, not days).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.config import DATA_DIR

NFL_DIR = DATA_DIR / "nfl"
GAMES_PATH = NFL_DIR / "games.parquet"
TEAM_GAMES_PATH = NFL_DIR / "team_games.parquet"
QB_GAMES_PATH = NFL_DIR / "qb_games.parquet"

RELOCATED = {"OAK": "LV", "SD": "LAC", "STL": "LA"}     # one franchise, one history

GAME_COLS = ["game_id", "season", "game_type", "week", "gameday", "gametime", "away_team", "home_team",
             "away_score", "home_score", "location", "away_rest", "home_rest", "div_game", "roof",
             "away_qb_id", "home_qb_id", "away_qb_name", "home_qb_name", "stadium"]
TEAM_STAT_COLS = ["game_id", "season", "week", "team", "attempts", "sacks_suffered", "carries", "passing_epa",
                  "rushing_epa", "passing_interceptions", "sack_fumbles_lost", "rushing_fumbles_lost",
                  "receiving_fumbles_lost", "passing_yards", "rushing_yards"]
QB_STAT_COLS = ["game_id", "season", "week", "player_id", "player_display_name", "team", "attempts",
                "sacks_suffered", "carries", "passing_epa", "rushing_epa"]

# rating settings (chosen up front; see the README)
HALF_LIFE = 8              # a game 8 games ago counts half as much
SEASON_CARRY = 0.5         # each offseason, older games' weight is cut in half again
PRIOR_PLAYS = 300          # team EPA starts this many plays' worth at league average (0)
QB_PRIOR_PLAYS = 250       # a quarterback's rating starts this many plays at replacement level
QB_REPLACEMENT = -0.10     # EPA per play of a typical backup
MARGIN_PRIOR_GAMES = 3
ELO_K, ELO_HOME, ELO_MEAN, ELO_KEEP = 20.0, 48.0, 1505.0, 2 / 3
REST_CAP = 14


# ---------------------------------------------------------------- loading

def _fix(s: pd.Series) -> pd.Series:
    return s.replace(RELOCATED)


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(games, team_games stats, qb_games); empty frames if the files aren't there yet."""
    if not GAMES_PATH.exists():
        return pd.DataFrame(columns=GAME_COLS), pd.DataFrame(columns=TEAM_STAT_COLS), pd.DataFrame(columns=QB_STAT_COLS)
    g = pd.read_parquet(GAMES_PATH)
    t = pd.read_parquet(TEAM_GAMES_PATH) if TEAM_GAMES_PATH.exists() else pd.DataFrame(columns=TEAM_STAT_COLS)
    q = pd.read_parquet(QB_GAMES_PATH) if QB_GAMES_PATH.exists() else pd.DataFrame(columns=QB_STAT_COLS)
    return g, t, q


def team_games(games: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    """Two rows per game (one per team), with the team's offense and its opponent's offense
    (= this team's defense). Unplayed games are kept with empty results, so upcoming games get
    their pregame numbers from exactly the same code as past games."""
    g = games.copy()
    g["date"] = pd.to_datetime(g["gameday"])
    for c in ("home_team", "away_team"):
        g[c] = _fix(g[c])
    neutral = g["location"].eq("Neutral")
    sides = []
    for side, other, venue in (("home", "away", 1), ("away", "home", -1)):
        sides.append(pd.DataFrame({
            "game_id": g["game_id"], "season": g["season"], "week": g["week"], "game_type": g["game_type"],
            "date": g["date"], "gametime": g["gametime"], "team": g[f"{side}_team"], "opp": g[f"{other}_team"],
            "venue": np.where(neutral, 0, venue), "pts": g[f"{side}_score"], "opp_pts": g[f"{other}_score"],
            "rest": g[f"{side}_rest"], "qb_id": g[f"{side}_qb_id"], "qb_name": g[f"{side}_qb_name"],
            "div_game": g["div_game"],
        }))
    tg = pd.concat(sides, ignore_index=True)
    s = stats.copy()
    s["team"] = _fix(s["team"])
    s["plays"] = s["attempts"].fillna(0) + s["sacks_suffered"].fillna(0) + s["carries"].fillna(0)
    s["epa"] = s["passing_epa"].fillna(0) + s["rushing_epa"].fillna(0)
    s["turnovers"] = s[["passing_interceptions", "sack_fumbles_lost", "rushing_fumbles_lost",
                        "receiving_fumbles_lost"]].fillna(0).sum(axis=1)
    s["yards"] = s["passing_yards"].fillna(0) + s["rushing_yards"].fillna(0)
    s = s[["game_id", "team", "plays", "epa", "turnovers", "yards"]].drop_duplicates(["game_id", "team"])
    tg = tg.merge(s, on=["game_id", "team"], how="left")
    opp = s.rename(columns={"team": "opp", "plays": "opp_plays", "epa": "opp_epa", "turnovers": "opp_turnovers",
                            "yards": "opp_yards"})
    tg = tg.merge(opp, on=["game_id", "opp"], how="left")
    tg["played"] = tg["pts"].notna() & tg["opp_pts"].notna()
    tg["margin"] = tg["pts"] - tg["opp_pts"]
    tg["won"] = np.where(tg["margin"] > 0, 1.0, np.where(tg["margin"] < 0, 0.0, 0.5))
    return tg.sort_values(["date", "gametime", "game_id", "team"], na_position="last").reset_index(drop=True)


# ---------------------------------------------------------------- ratings

def elo_ratings(tg: pd.DataFrame) -> pd.Series:
    """Pregame Elo for every team-game row (played and upcoming)."""
    elo: dict[str, float] = {}
    season_of: dict[str, object] = {}
    out = pd.Series(np.nan, index=tg.index)
    home_rows = tg[tg["venue"] >= 0].drop_duplicates("game_id")      # one row per game (home side, or first)
    pair = tg.set_index(["game_id", "team"]).index
    idx = dict(zip(pair, tg.index))
    for r in home_rows.itertuples():
        if r.opp is None or (isinstance(r.opp, float) and np.isnan(r.opp)):      # placeholder for "next game"
            if r.team not in elo:
                elo[r.team], season_of[r.team] = ELO_MEAN, r.season
            elif season_of[r.team] != r.season:
                elo[r.team] = ELO_MEAN + ELO_KEEP * (elo[r.team] - ELO_MEAN)
                season_of[r.team] = r.season
            out[idx[(r.game_id, r.team)]] = elo[r.team]
            continue
        for t in (r.team, r.opp):
            if t not in elo:
                elo[t], season_of[t] = ELO_MEAN, r.season
            elif season_of[t] != r.season:
                elo[t] = ELO_MEAN + ELO_KEEP * (elo[t] - ELO_MEAN)
                season_of[t] = r.season
        ea, eb = elo[r.team], elo[r.opp]
        out[idx[(r.game_id, r.team)]], out[idx[(r.game_id, r.opp)]] = ea, eb
        if not r.played:
            continue
        diff = ea - eb + ELO_HOME * r.venue
        exp = 1 / (1 + 10 ** (-diff / 400))
        mov = abs(r.margin)
        winner_diff = diff if r.margin > 0 else -diff
        mult = np.log(mov + 1) * 2.2 / (winner_diff * 0.001 + 2.2) if mov else 1.0
        shift = ELO_K * mult * (r.won - exp)
        elo[r.team], elo[r.opp] = ea + shift, eb - shift
    return out


def _decayed(tg: pd.DataFrame, key: str, num: str, den: str | None) -> pd.Series:
    """Pregame decayed average of num (per den, or per game) for each row's `key` (team or QB),
    using only that key's earlier played games. Returns (sum_num, sum_den) as two columns."""
    d = 0.5 ** (1 / HALF_LIFE)
    sn: dict = {}
    sd: dict = {}
    season_of: dict = {}
    out_n, out_d = np.zeros(len(tg)), np.zeros(len(tg))
    keys, seasons, played = tg[key].to_numpy(), tg["season"].to_numpy(), tg["_use"].to_numpy()
    nums = tg[num].to_numpy(float)
    dens = tg[den].to_numpy(float) if den else np.ones(len(tg))
    for i in range(len(tg)):
        k = keys[i]
        if k is None or (isinstance(k, float) and np.isnan(k)):
            continue
        if k in season_of and season_of[k] != seasons[i]:
            sn[k] *= SEASON_CARRY
            sd[k] *= SEASON_CARRY
        season_of[k] = seasons[i]
        out_n[i], out_d[i] = sn.get(k, 0.0), sd.get(k, 0.0)
        if played[i] and not np.isnan(nums[i]) and not np.isnan(dens[i]):
            sn[k] = sn.get(k, 0.0) * d + nums[i]
            sd[k] = sd.get(k, 0.0) * d + dens[i]
    return pd.DataFrame({"n": out_n, "d": out_d}, index=tg.index)


def qb_table(qb_stats: pd.DataFrame) -> pd.DataFrame:
    q = qb_stats.copy()
    q["plays"] = q["attempts"].fillna(0) + q["sacks_suffered"].fillna(0) + q["carries"].fillna(0)
    q["epa"] = q["passing_epa"].fillna(0) + q["rushing_epa"].fillna(0)
    return q.groupby(["game_id", "player_id"], as_index=False)[["plays", "epa"]].sum()


def pregame_features(tg: pd.DataFrame, qb_stats: pd.DataFrame) -> pd.DataFrame:
    """Adds pregame columns to every team-game row. Uses only earlier games."""
    f = tg.copy()
    f["_use"] = f["played"] & f["plays"].notna()
    f["elo"] = elo_ratings(f)

    off = _decayed(f, "team", "epa", "plays")
    f["off_epa"] = off["n"] / (off["d"] + PRIOR_PLAYS)
    f["off_plays_w"] = off["d"]
    f["_def_epa"] = f["opp_epa"]
    f["_def_plays"] = f["opp_plays"]
    de = _decayed(f, "team", "_def_epa", "_def_plays")
    f["def_epa"] = de["n"] / (de["d"] + PRIOR_PLAYS)
    f["_use"] = f["played"]
    mg = _decayed(f, "team", "margin", None)
    f["margin_pg"] = mg["n"] / (mg["d"] + MARGIN_PRIOR_GAMES)

    # quarterback: rate every QB on his own plays (any team), then look up the listed starter
    q = qb_table(qb_stats)
    qrows = f[["game_id", "season", "date", "gametime"]].drop_duplicates("game_id").merge(q, on="game_id")
    qrows = qrows.sort_values(["date", "gametime", "game_id"]).reset_index(drop=True)
    qrows["_use"] = True
    qd = _decayed(qrows.rename(columns={"player_id": "pid"}), "pid", "epa", "plays")
    qrows["qb_pre"] = (qd["n"] + QB_PRIOR_PLAYS * QB_REPLACEMENT) / (qd["d"] + QB_PRIOR_PLAYS)
    qrows["qb_plays_w"] = qd["d"]
    f = f.merge(qrows[["game_id", "player_id", "qb_pre", "qb_plays_w"]]
                .rename(columns={"player_id": "qb_id"}), on=["game_id", "qb_id"], how="left")
    # a listed starter with no stats row in this game (upcoming game, or listed but didn't play):
    # his rating after his last game BEFORE this date
    miss = f["qb_pre"].isna() & f["qb_id"].notna()
    if miss.any():
        post = _qb_post(qrows).sort_values("date")
        look = f.loc[miss, ["qb_id", "date"]].reset_index().sort_values("date")
        got = pd.merge_asof(look, post.rename(columns={"player_id": "qb_id"}), on="date", by="qb_id",
                            allow_exact_matches=False).set_index("index")
        f.loc[got.index, "qb_pre"] = got["rating"]
        f.loc[got.index, "qb_plays_w"] = got["plays_w"]
    f["qb_pre"] = f["qb_pre"].fillna(QB_REPLACEMENT)
    f["qb_plays_w"] = f["qb_plays_w"].fillna(0)

    f["rest"] = f["rest"].clip(upper=REST_CAP)
    f["bye"] = (f["rest"] >= 13).astype(int)
    f = _records(f)
    return f.drop(columns=[c for c in f.columns if c.startswith("_")])


def _qb_post(qrows: pd.DataFrame) -> pd.DataFrame:
    """Each QB's rating right AFTER each of his games: (player_id, date, rating, plays_w)."""
    d = 0.5 ** (1 / HALF_LIFE)
    n = qrows["qb_pre"] * (qrows["qb_plays_w"] + QB_PRIOR_PLAYS) - QB_PRIOR_PLAYS * QB_REPLACEMENT
    post_n = n * d + qrows["epa"]
    post_d = qrows["qb_plays_w"] * d + qrows["plays"]
    return pd.DataFrame({"player_id": qrows["player_id"], "date": qrows["date"],
                         "rating": (post_n + QB_PRIOR_PLAYS * QB_REPLACEMENT) / (post_d + QB_PRIOR_PLAYS),
                         "plays_w": post_d})


def _qb_latest(qrows: pd.DataFrame) -> pd.DataFrame:
    """Each QB's rating after his most recent game in `qrows` (callers pass only earlier games)."""
    return _qb_post(qrows).groupby("player_id").tail(1).set_index("player_id")[["rating", "plays_w"]]


def _records(f: pd.DataFrame) -> pd.DataFrame:
    """Season record before each game (regular season and playoffs counted together), ties as half,
    plus the team's most common starting QB so far this season."""
    f = f.copy()
    grp = f.groupby(["team", "season"])
    playedf = f["played"].astype(float)
    f["gp"] = grp["played"].transform(lambda s: s.astype(int).cumsum().shift(1, fill_value=0))
    w = (f["won"] == 1).astype(float) * playedf
    t = (f["won"] == 0.5).astype(float) * playedf
    f["s_wins"] = w.groupby([f["team"], f["season"]]).transform(lambda s: s.cumsum().shift(1, fill_value=0))
    f["s_ties"] = t.groupby([f["team"], f["season"]]).transform(lambda s: s.cumsum().shift(1, fill_value=0))
    f["s_losses"] = f["gp"] - f["s_wins"] - f["s_ties"]
    pf = (f["pts"].fillna(0) * playedf).groupby([f["team"], f["season"]]).transform(lambda s: s.cumsum().shift(1, fill_value=0))
    pa = (f["opp_pts"].fillna(0) * playedf).groupby([f["team"], f["season"]]).transform(lambda s: s.cumsum().shift(1, fill_value=0))
    f["s_pf"], f["s_pa"] = pf, pa
    return f


def build_features(games: pd.DataFrame | None = None, stats: pd.DataFrame | None = None,
                   qb_stats: pd.DataFrame | None = None) -> pd.DataFrame:
    if games is None:
        games, stats, qb_stats = load()
    return pregame_features(team_games(games, stats), qb_stats)


# ---------------------------------------------------------------- state for any matchup

STATE_COLS = ["team", "season", "gp", "s_wins", "s_losses", "s_ties", "s_pf", "s_pa", "elo", "off_epa", "def_epa",
              "margin_pg", "qb_id", "qb_name", "qb_pre", "qb_plays_w"]


def record_text(w, l, t=0) -> str:
    return f"{int(w)}-{int(l)}" + (f"-{int(t)}" if t else "")


def current_state(games: pd.DataFrame, stats: pd.DataFrame, qb_stats: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Every team's numbers for a game on `as_of`, from games before that date only. Each team gets a
    placeholder game on `as_of`; its listed QB is the one listed for the team's next game within a
    week if nflverse has one, otherwise last game's starter."""
    as_of = pd.Timestamp(as_of)
    g = games[pd.to_datetime(games["gameday"]) < as_of]
    tg = team_games(g, stats[stats["game_id"].isin(set(g["game_id"]))])
    season = int(tg.loc[tg["played"], "season"].max()) if tg["played"].any() else int(games["season"].max())
    cur = games[(games["season"] == season)]
    teams = sorted(set(_fix(cur["home_team"])) | set(_fix(cur["away_team"])))
    nxt = _next_listed_qb(games, as_of)
    last_qb = tg[tg["played"]].groupby("team")[["qb_id", "qb_name"]].last()
    ph = []
    for t in teams:
        qb = nxt.get(t) or (tuple(last_qb.loc[t]) if t in last_qb.index else (None, None))
        ph.append({"game_id": f"NEXT_{t}", "season": season, "week": 99, "game_type": "REG", "date": as_of,
                   "gametime": "00:00", "team": t, "opp": None, "venue": 0, "pts": np.nan, "opp_pts": np.nan,
                   "rest": np.nan, "qb_id": qb[0], "qb_name": qb[1], "div_game": 0, "played": False})
    tg = pd.concat([tg, pd.DataFrame(ph)], ignore_index=True)
    tg = tg.sort_values(["date", "gametime", "game_id", "team"]).reset_index(drop=True)
    f = pregame_features(tg, qb_stats[qb_stats["game_id"].isin(set(g["game_id"]))])
    state = f[f["game_id"].str.startswith("NEXT_")][STATE_COLS].copy()
    return state.set_index("team", drop=False)


def _next_listed_qb(games: pd.DataFrame, as_of: pd.Timestamp, days: int = 7) -> dict:
    d = pd.to_datetime(games["gameday"])
    up = games[(d >= as_of) & (d < as_of + pd.Timedelta(days=days))].sort_values("gameday")
    out = {}
    for r in up.itertuples():
        for side in ("home", "away"):
            t = RELOCATED.get(getattr(r, f"{side}_team"), getattr(r, f"{side}_team"))
            qid = getattr(r, f"{side}_qb_id")
            if t not in out and isinstance(qid, str) and qid:
                out[t] = (qid, getattr(r, f"{side}_qb_name"))
    return out


def rest_for(games: pd.DataFrame, team: str, game_date) -> int | None:
    """Days since the team's previous game (capped), counted to `game_date`."""
    d = pd.to_datetime(games["gameday"])
    mine = games[((_fix(games["home_team"]) == team) | (_fix(games["away_team"]) == team)) & (d < pd.Timestamp(game_date))]
    if mine.empty:
        return None
    return int(min((pd.Timestamp(game_date) - pd.to_datetime(mine["gameday"]).max()).days, REST_CAP))


def head_to_head(games: pd.DataFrame, a: str, b: str, before, seasons: int = 4) -> dict:
    g = games.copy()
    g["home_team"], g["away_team"] = _fix(g["home_team"]), _fix(g["away_team"])
    g = g[g["home_score"].notna() & (pd.to_datetime(g["gameday"]) < pd.Timestamp(before))]
    g = g[g["season"] >= g["season"].max() - seasons + 1]
    g = g[((g["home_team"] == a) & (g["away_team"] == b)) | ((g["home_team"] == b) & (g["away_team"] == a))]
    g = g.sort_values("gameday")
    pts_a = np.where(g["home_team"] == a, g["home_score"], g["away_score"])
    pts_b = np.where(g["home_team"] == a, g["away_score"], g["home_score"])
    return {"games": len(g), "a_wins": int((pts_a > pts_b).sum()), "b_wins": int((pts_a < pts_b).sum()),
            "avg_margin_a": float((pts_a - pts_b).mean()) if len(g) else None,
            "recent": [(d, int(x), int(y), "home" if h == a else "away")
                       for d, x, y, h in list(zip(g["gameday"], pts_a, pts_b, g["home_team"]))[-5:]]}


def matchup_rows(sa: pd.Series, sb: pd.Series, rest_a, rest_b) -> list:
    """Side-by-side rows for the Upset Watch comparison."""
    from matchup.base import StatRow

    def row(section, label, a, b, higher_is_better=True, fmt="{:.1f}", note=""):
        better = None
        if a is not None and b is not None and not (pd.isna(a) or pd.isna(b)) and a != b and higher_is_better is not None:
            better = "a" if (a > b) == higher_is_better else "b"
        return StatRow(section, label, a, b, better, fmt, note)

    def pct(s):
        return (s["s_wins"] + s["s_ties"] / 2) / s["gp"] if s["gp"] else 0.5

    pa, pb = pct(sa), pct(sb)
    return [
        row("Strength", "Elo rating", sa["elo"], sb["elo"], fmt="{:.0f}", note="Carries over between seasons; 1505 is average"),
        StatRow("Strength", "Record", record_text(sa["s_wins"], sa["s_losses"], sa["s_ties"]),
                record_text(sb["s_wins"], sb["s_losses"], sb["s_ties"]),
                "a" if pa > pb else ("b" if pb > pa else None), "{}"),
        row("Strength", "Point margin per game", sa["margin_pg"], sb["margin_pg"], fmt="{:+.1f}",
            note="Recent games count more; last season counts a little"),
        row("Offense", "Points per game", sa["s_pf"] / max(sa["gp"], 1), sb["s_pf"] / max(sb["gp"], 1)),
        row("Offense", "EPA per play", sa["off_epa"], sb["off_epa"], fmt="{:+.3f}",
            note="Expected points added per snap; recent games count more"),
        row("Defense", "Points allowed per game", sa["s_pa"] / max(sa["gp"], 1), sb["s_pa"] / max(sb["gp"], 1),
            higher_is_better=False),
        row("Defense", "EPA per play allowed", sa["def_epa"], sb["def_epa"], higher_is_better=False, fmt="{:+.3f}"),
        StatRow("Quarterback", "Expected starter", sa["qb_name"] or "—", sb["qb_name"] or "—", None, "{}"),
        row("Quarterback", "Starter's EPA per play", sa["qb_pre"], sb["qb_pre"], fmt="{:+.3f}",
            note="His own recent plays on any team; new or little-used QBs start near backup level"),
        row("Schedule", "Days of rest", rest_a, rest_b, fmt="{:.0f}", note="14 or more = coming off a bye"),
    ]
