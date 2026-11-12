"""Player-based team strength: ratings follow players across teams, and a team is rated by who's
actually available. Everything is computed from games BEFORE the one being predicted.

Player rating, updated after every game:
  box     Game Score per 36 minutes (John Hollinger's fixed formula; nothing fitted on future data)
  impact  on-court plus-minus per 48 minutes (noisy alone, but sees defense and spacing)
Each past game's weight halves every HALF_LIFE games the player plays; at a new season all past
games are discounted again by SEASON_CARRY. Small samples are pulled toward a replacement-level
player by mixing in PRIOR_MINUTES of replacement play.

Team strength for a game = expected-minutes-weighted average rating of the available rotation:
players who played in the team's previous game this season (regulars who missed it are out, and
their minutes go to everyone else). For a team's first game of a season the roster is the players
who played that night, since historical opening-night rosters aren't in the stored data.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

HALF_LIFE = 40            # games
SEASON_CARRY = 0.7        # extra discount on everything before a new season
PRIOR_MINUTES = 400.0     # replacement-level minutes mixed into every rating
ROTATION = 10             # players counted in team strength
REPL_GS36, REPL_PM48 = 8.0, -3.0      # replacement level (bench-player territory)

_DECAY = 0.5 ** (1 / HALF_LIFE)


def game_score(r) -> np.ndarray:
    """Hollinger Game Score for each player-game row."""
    return (r["PTS"] + 0.4 * r["FGM"] - 0.7 * r["FGA"] - 0.4 * (r["FTA"] - r["FTM"]) + 0.7 * r["OREB"]
            + 0.3 * r["DREB"] + r["STL"] + 0.7 * r["AST"] + 0.7 * r["BLK"] - 0.4 * r["PF"] - r["TOV"])


def player_ratings(logs: pd.DataFrame) -> pd.DataFrame:
    """Pregame rating for every player-game (game_id, player_id, team, gs36, pm48, exp_min)."""
    d = logs[["season", "GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION", "PLAYER_ID", "MIN", "PLUS_MINUS",
              "PTS", "FGM", "FGA", "FTA", "FTM", "OREB", "DREB", "STL", "AST", "BLK", "PF", "TOV"]].copy()
    d["GAME_ID"] = d["GAME_ID"].astype(str).str.zfill(10)
    d["GAME_DATE"] = pd.to_datetime(d["GAME_DATE"])
    d["MIN"] = pd.to_numeric(d["MIN"], errors="coerce").fillna(0.0)
    d["PLUS_MINUS"] = pd.to_numeric(d["PLUS_MINUS"], errors="coerce").fillna(0.0)
    d["gs"] = game_score(d).astype(float)
    d = d.sort_values(["GAME_DATE", "GAME_ID", "PLAYER_ID"]).reset_index(drop=True)

    w_min = defaultdict(float)       # decayed minutes
    w_gs = defaultdict(float)        # decayed game score
    w_pm = defaultdict(float)        # decayed plus-minus
    w_n = defaultdict(float)         # decayed game count (for expected minutes)
    last_season: dict = {}
    out = np.empty((len(d), 6))                                          # pregame (0-2) and postgame (3-5)
    for i, (pid, season, mins, gs, pm) in enumerate(zip(d["PLAYER_ID"].values, d["season"].values, d["MIN"].values,
                                                          d["gs"].values, d["PLUS_MINUS"].values)):
        if last_season.get(pid) not in (None, season):                 # new season: fade the past
            for acc in (w_min, w_gs, w_pm, w_n):
                acc[pid] *= SEASON_CARRY
        last_season[pid] = season
        m = w_min[pid]
        out[i, 0] = (w_gs[pid] + REPL_GS36 / 36 * PRIOR_MINUTES) / (m + PRIOR_MINUTES) * 36   # pregame
        out[i, 1] = (w_pm[pid] + REPL_PM48 / 48 * PRIOR_MINUTES) / (m + PRIOR_MINUTES) * 48
        out[i, 2] = m / w_n[pid] if w_n[pid] > 0 else np.nan
        for acc, v in ((w_min, mins), (w_gs, gs), (w_pm, pm), (w_n, 1.0)):    # then learn from this game
            acc[pid] = acc[pid] * _DECAY + v
        m = w_min[pid]
        out[i, 3] = (w_gs[pid] + REPL_GS36 / 36 * PRIOR_MINUTES) / (m + PRIOR_MINUTES) * 36   # after this game
        out[i, 4] = (w_pm[pid] + REPL_PM48 / 48 * PRIOR_MINUTES) / (m + PRIOR_MINUTES) * 48
        out[i, 5] = m / w_n[pid]
    return pd.DataFrame({"game_id": d["GAME_ID"], "player_id": d["PLAYER_ID"], "team": d["TEAM_ABBREVIATION"],
                         "date": d["GAME_DATE"], "season": d["season"], "minutes": d["MIN"],
                         "gs36": out[:, 0], "pm48": out[:, 1], "exp_min": out[:, 2],
                         "gs36_post": out[:, 3], "pm48_post": out[:, 4], "exp_min_post": out[:, 5]})


def _weighted(gs: np.ndarray, pm: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    """Expected-minutes-weighted average of the top ROTATION players' ratings."""
    w = np.clip(np.nan_to_num(w), 0, None)
    if len(w) > ROTATION:
        keep = np.argpartition(-w, ROTATION - 1)[:ROTATION]
        gs, pm, w = gs[keep], pm[keep], w[keep]
    total = w.sum()
    if total <= 0:
        return np.nan, np.nan
    return float((gs * w).sum() / total), float((pm * w).sum() / total)


def team_strength(ratings: pd.DataFrame) -> pd.DataFrame:
    """Pregame roster strength for every team-game: (game_id, team, roster_gs36, roster_pm48, roster_size).
    Roster = players who played the team's previous game this season, rated as of right after that game
    (fully known before tip-off). First game of a season: players who played that night, pregame ratings."""
    r = ratings.sort_values(["team", "season", "date", "game_id"]).reset_index(drop=True)
    first_w = r["exp_min"].fillna(r["minutes"]).to_numpy()
    cols = {k: r[k].to_numpy() for k in ("gs36", "pm48", "gs36_post", "pm48_post", "exp_min_post")}
    keys = r["team"].astype(str) + "|" + r["season"].astype(str) + "|" + r["game_id"].astype(str)
    starts = np.flatnonzero(np.r_[True, keys.values[1:] != keys.values[:-1]])
    ends = np.r_[starts[1:], len(r)]
    rows, prev = [], None
    for s0, e0 in zip(starts, ends):
        team, season, gid = r.at[s0, "team"], r.at[s0, "season"], r.at[s0, "game_id"]
        if prev is None or prev[0] != (team, season):
            gs, pm = _weighted(cols["gs36"][s0:e0], cols["pm48"][s0:e0], first_w[s0:e0])
            size = e0 - s0
        else:
            p0, p1 = prev[1]
            gs, pm = _weighted(cols["gs36_post"][p0:p1], cols["pm48_post"][p0:p1], cols["exp_min_post"][p0:p1])
            size = p1 - p0
        rows.append((gid, team, gs, pm, size))
        prev = ((team, season), (s0, e0))
    return pd.DataFrame(rows, columns=["game_id", "team", "roster_gs36", "roster_pm48", "roster_size"])
