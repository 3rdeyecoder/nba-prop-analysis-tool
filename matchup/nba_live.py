"""NBA Upset Watch, live side: a small daily snapshot, predictions, and plain-English reasons.

The morning job (refresh/upsets.py) saves:
  data/upset_watch/nba_state.parquet        every team's pregame numbers as of today (only earlier games)
  data/upset_watch/nba_team_games.parquet   recent team-games, for rest days and head-to-head
The page reads only these small files, so it never recomputes eight seasons of features.

Predictions use the same feature code as training (sports.nba_model.matchup_rows), which
tests/test_nba_model.py checks against real past games.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from matchup import track, upset
from matchup.base import Game, GameContext, Prediction, Result, StatRow, Team
from sports import nba, nba_matchup as m, nba_model as nm

ET = ZoneInfo("America/New_York")
STATE_PATH = track.UPSET_DIR / "nba_state.parquet"
GAMES_PATH = track.UPSET_DIR / "nba_team_games.parquet"
H2H_SEASONS = 3
TG_COLS = ["season", "game_id", "date", "team", "team_id", "opp", "venue", "won", "margin", "PTS", "opp_PTS"]


def today_et() -> date:
    return datetime.now(ET).date()


# ---------------------------------------------------------------- snapshot

def build_snapshot(logs: pd.DataFrame, as_of: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(state, team_games) for predicting games on `as_of`, using only games before that date."""
    state = m.current_state(logs, pd.Timestamp(as_of)).reset_index(drop=True)
    names = (logs.sort_values("GAME_DATE").groupby("TEAM_ABBREVIATION")["TEAM_NAME"].last()
             if "TEAM_NAME" in logs else pd.Series(dtype=str))
    state["team_name"] = state["team"].map(names).fillna(state["team"])
    state["as_of"] = pd.Timestamp(as_of)
    state["data_through"] = pd.to_datetime(logs["GAME_DATE"]).loc[lambda d: d < pd.Timestamp(as_of)].max()
    tg = m.team_games(logs)
    keep = sorted(tg["season"].unique())[-H2H_SEASONS:]
    tg = tg[tg["season"].isin(keep) & (tg["date"] < pd.Timestamp(as_of))][TG_COLS].reset_index(drop=True)
    return state, tg


def save_snapshot(state: pd.DataFrame, tg: pd.DataFrame) -> None:
    from core.storage import atomic_write_parquet
    atomic_write_parquet(state, STATE_PATH)
    atomic_write_parquet(tg, GAMES_PATH)


def load_snapshot() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    if not (STATE_PATH.exists() and GAMES_PATH.exists()):
        return None
    state = pd.read_parquet(STATE_PATH)
    return state.set_index("team", drop=False), pd.read_parquet(GAMES_PATH)


# ---------------------------------------------------------------- predictions

@dataclass
class MatchupCall:
    team_a: str
    team_b: str
    home: str | None
    p_a: float                   # model chance team A wins
    paper_a: float               # on-paper chance team A wins
    drivers: dict                # feature -> contribution to A's log-odds
    check: upset.UpsetCheck | None


def predict(model: dict, state: pd.DataFrame, tg: pd.DataFrame, a: str, b: str, home: str | None, game_date,
            threshold: float = upset.DEFAULT_THRESHOLD) -> MatchupCall:
    rows = nm.matchup_rows(state, tg, a, b, home, pd.Timestamp(game_date))
    p = nm.predict_pair(model, rows)
    i = int(np.flatnonzero(rows["team_a"].to_numpy() == a)[0])
    p_a, paper_a = float(p[i]), float(rows["paper_a"].iloc[i])
    try:
        chk = upset.check(a, b, paper_a, p_a, threshold)
    except ValueError:                                           # even on paper
        chk = None
    return MatchupCall(a, b, home, p_a, paper_a, nm.contributions(model, rows.iloc[i]), chk)


# feature groups for the "why" (contributions are on team A's log-odds scale)
GROUPS = {
    "Roster strength": ["roster_gs_d", "roster_pm_d"],
    "Home court": ["home"],
    "Season performance": ["net_d", "elo_d"],
    "Recent form": ["l10_net_d"],
    "Rest and schedule": ["rest_d", "b2b_a", "b2b_b", "last6_d"],
    "Missing regulars": ["missing_d"],
}


def reasons(call: MatchupCall, state: pd.DataFrame, tg: pd.DataFrame, game_date, top: int = 3) -> list[dict]:
    """Biggest factors, each with the team it favours, its size in win-chance points, and a fact."""
    a, b = call.team_a, call.team_b
    sched = {t: m.schedule_for(tg, t, pd.Timestamp(game_date)) for t in (a, b)}
    logit_a = float(np.log(call.p_a / (1 - call.p_a)))
    out = []
    for name, feats in GROUPS.items():
        c = sum(call.drivers.get(f, 0.0) for f in feats)
        if abs(c) < 1e-9:
            continue
        without = 1 / (1 + np.exp(-(logit_a - c)))              # A's chance with this factor removed
        favors = a if c > 0 else b
        other = b if favors == a else a
        out.append({"factor": name, "favors": favors, "points": abs(call.p_a - without) * 100,
                    "fact": _fact(name, favors, other, state, sched, call.home)})
    return sorted(out, key=lambda r: -r["points"])[:top]


def _fact(name: str, t: str, o: str, state: pd.DataFrame, sched: dict, home: str | None) -> str:
    st_, so = state.loc[t], state.loc[o]
    if name == "Roster strength":
        return (f"{t}'s available rotation rates higher by player ratings "
                f"(impact {st_['roster_pm48']:+.1f} vs {so['roster_pm48']:+.1f} per 48 minutes).")
    if name == "Home court":
        return f"{home} is at home." if home else "Neutral site."
    if name == "Season performance":
        return f"{t}: {int(st_['s_wins'])}-{int(st_['s_losses'])}, net rating {st_['s_net']:+.1f}; " \
               f"{o}: {int(so['s_wins'])}-{int(so['s_losses'])}, {so['s_net']:+.1f}."
    if name == "Recent form":
        return f"Last 10 net rating: {t} {st_['l10_net']:+.1f}, {o} {so['l10_net']:+.1f}."
    if name == "Rest and schedule":
        if sched[o]["b2b"] and not sched[t]["b2b"]:
            return f"{o} is on the second night of a back-to-back."
        return f"Days of rest: {t} {sched[t]['rest_days']}, {o} {sched[o]['rest_days']}; games in the last " \
               f"6 days: {t} {sched[t]['games_last6']}, {o} {sched[o]['games_last6']}."
    if name == "Missing regulars":
        return f"{o} missed {so['missing_names'] or 'regulars'} in their last game."
    return ""


# ---------------------------------------------------------------- schedule, predictions log, grading

def todays_games(day: date, schedule: pd.DataFrame | None = None) -> pd.DataFrame:
    """Regular-season games (game id 002...) whose tip-off falls on `day`, US Eastern."""
    if schedule is None:
        files = sorted(nba.DATA_DIR.glob("nba_schedule_*.parquet"))
        if not files:
            return pd.DataFrame()
        schedule = pd.read_parquet(files[-1])
    s = schedule[schedule["game_id"].astype(str).str.startswith("002")].copy()
    s["date_et"] = pd.to_datetime(s["start_utc"], utc=True).dt.tz_convert(ET).dt.date
    return s[s["date_et"] == day].sort_values(["start_utc", "game_id"]).reset_index(drop=True)


def prediction_rows(model: dict, state: pd.DataFrame, tg: pd.DataFrame, games: pd.DataFrame, day: date,
                    now_utc: pd.Timestamp, threshold: float = upset.DEFAULT_THRESHOLD) -> list[dict]:
    """Log rows for games that haven't started yet. Teams missing from the snapshot are skipped."""
    rows = []
    through = state["data_through"].iloc[0] if "data_through" in state else None
    for g in games.itertuples():
        start = pd.Timestamp(g.start_utc)
        start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
        if start <= now_utc or g.home not in state.index or g.away not in state.index:
            continue
        call = predict(model, state, tg, g.home, g.away, g.home, day, threshold)
        chk = call.check
        rec = {t: f"{int(state.loc[t, 's_wins'])}-{int(state.loc[t, 's_losses'])}" for t in (g.home, g.away)}
        rows.append({
            "sport": "NBA", "game_id": str(g.game_id), "game_date": day.isoformat(), "start_utc": start.isoformat(),
            "home": g.home, "away": g.away,
            "underdog": chk.underdog if chk else None, "favorite": chk.favorite if chk else None,
            "underdog_record": rec[chk.underdog] if chk else None, "favorite_record": rec[chk.favorite] if chk else None,
            "paper_prob": chk.paper_prob if chk else 0.5, "model_prob": chk.model_prob if chk else call.p_a,
            "home_model_prob": call.p_a, "home_paper_prob": call.paper_a,
            "edge": chk.edge if chk else 0.0, "threshold": threshold, "flagged": bool(chk and chk.flagged),
            "data_through": str(pd.Timestamp(through).date()) if through is not None and pd.notna(through) else None,
        })
    return rows


VOID_AFTER_DAYS = 7


def results_from_logs(log: pd.DataFrame, logs: pd.DataFrame, today: date) -> dict:
    """Winner and score for each ungraded game, from the stored game logs. Games that never appear
    within VOID_AFTER_DAYS of their date are voided (postponed)."""
    pending = log[log["result"].isna()]
    if pending.empty:
        return {}
    d = logs.copy()
    d["gid"] = d["GAME_ID"].astype(str).str.zfill(10)
    d = d[d["gid"].isin(set(pending["game_id"]))]
    pts = d.groupby(["gid", "TEAM_ABBREVIATION"])["PTS"].sum()
    out = {}
    for r in pending.itertuples():
        if r.game_id in pts.index.get_level_values(0):
            s = pts.loc[r.game_id]
            if r.home in s.index and r.away in s.index:
                hs, as_ = int(s[r.home]), int(s[r.away])
                out[r.flag_id] = (r.home if hs > as_ else r.away, hs, as_)
        elif (today - date.fromisoformat(r.game_date)).days > VOID_AFTER_DAYS:
            out[r.flag_id] = (None, None, None)
    return out


# ---------------------------------------------------------------- the shared SportModule interface

class NbaModule:
    """NBA implementation of matchup.base.SportModule, backed by the daily snapshot."""
    sport = "NBA"

    def __init__(self, model: dict | None = None, snapshot=None):
        self.model = model if model is not None else nm.load_model()
        self.snapshot = snapshot if snapshot is not None else load_snapshot()

    @property
    def ready(self) -> bool:
        return self.model is not None and self.snapshot is not None

    def get_teams(self) -> list[Team]:
        from core.cards import LOGO
        state = self.snapshot[0]
        return [Team(r.team, r.team_name, LOGO.format(int(r.team_id)) if pd.notna(r.team_id) else None)
                for r in state.sort_values("team_name").itertuples()]

    def get_games(self, day: date) -> list[Game]:
        g = todays_games(day)
        return [Game("NBA", str(r.game_id), pd.Timestamp(r.start_utc).isoformat(), r.home, r.away)
                for r in g.itertuples()]

    def get_matchup_stats(self, a: str, b: str, as_of: date) -> list[StatRow]:
        state, tg = self.snapshot
        d = pd.Timestamp(as_of)
        return m.matchup_rows(state.loc[a], state.loc[b], m.schedule_for(tg, a, d), m.schedule_for(tg, b, d))

    def predict_win_prob(self, a: str, b: str, ctx: GameContext) -> Prediction:
        call = predict(self.model, *self.snapshot, a, b, ctx.home, ctx.game_date)
        return Prediction(a, b, call.p_a, call.drivers)

    def game_result(self, game: Game) -> Result | None:
        log = track.load(track.log_path("NBA"))
        row = log[(log["game_id"] == game.game_id) & log["winner"].notna()]
        if row.empty:
            return None
        r = row.iloc[0]
        return Result(r["winner"], r["home_score"], r["away_score"])
