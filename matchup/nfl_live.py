"""NFL Upset Watch, live side: daily snapshot, this week's games, predictions, reasons, grading.

The morning job (refresh/upsets.py) saves data/upset_watch/nfl_state.parquet: every team's pregame
numbers as of today, from earlier games only. Games are locked in on their own game day (US Eastern),
so each prediction uses the latest listed starting quarterbacks; later games this week are shown as a
preview until then.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from matchup import track, upset
from matchup.base import Game, GameContext, Prediction, Result, StatRow, Team
from matchup.nba_live import ET, MatchupCall
from sports import nfl as nfl_data
from sports import nfl_matchup as fm
from sports import nfl_model as nfm

STATE_PATH = track.UPSET_DIR / "nfl_state.parquet"
WEEK_DAYS = 7
VOID_AFTER_DAYS = 7

TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


# ---------------------------------------------------------------- snapshot

def build_snapshot(games: pd.DataFrame, stats: pd.DataFrame, qb_stats: pd.DataFrame, as_of: date) -> pd.DataFrame:
    state = fm.current_state(games, stats, qb_stats, pd.Timestamp(as_of)).reset_index(drop=True)
    state["team_name"] = state["team"].map(TEAM_NAMES).fillna(state["team"])
    state["as_of"] = pd.Timestamp(as_of)
    played = games[games["home_score"].notna() & (pd.to_datetime(games["gameday"]) < pd.Timestamp(as_of))]
    state["data_through"] = pd.to_datetime(played["gameday"]).max()
    return state


def save_snapshot(state: pd.DataFrame) -> None:
    from core.storage import atomic_write_parquet
    atomic_write_parquet(state, STATE_PATH)


def load_snapshot() -> pd.DataFrame | None:
    return pd.read_parquet(STATE_PATH).set_index("team", drop=False) if STATE_PATH.exists() else None


# ---------------------------------------------------------------- schedule and predictions

def _start_utc(games: pd.DataFrame) -> pd.Series:
    t = pd.to_datetime(games["gameday"] + " " + games["gametime"].fillna("13:00"), errors="coerce")
    return t.dt.tz_localize(ET, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")


def week_games(games: pd.DataFrame, start: date, days: int = WEEK_DAYS) -> pd.DataFrame:
    """Games with a US Eastern date from `start` through the next `days`-1 days (gametime is Eastern)."""
    g = games.copy()
    g["home"], g["away"] = fm._fix(g["home_team"]), fm._fix(g["away_team"])
    g["start_utc"] = _start_utc(g)
    d = pd.to_datetime(g["gameday"]).dt.date
    g = g[(d >= start) & (d < start + timedelta(days=days))]
    return g.sort_values(["start_utc", "game_id"]).reset_index(drop=True)


def predict(model: dict, state: pd.DataFrame, games: pd.DataFrame, a: str, b: str, home: str | None, game_date,
            threshold: float = upset.DEFAULT_THRESHOLD) -> MatchupCall:
    rest = {t: fm.rest_for(games, t, game_date) for t in (a, b)}
    rows = nfm.matchup_rows(state, a, b, home, rest[a], rest[b])
    p = nfm.predict_pair(model, rows)
    i = int(np.flatnonzero(rows["team_a"].to_numpy() == a)[0])
    p_a, paper_a = float(p[i]), float(rows["paper_a"].iloc[i])
    try:
        chk = upset.check(a, b, paper_a, p_a, threshold)
    except ValueError:
        chk = None
    return MatchupCall(a, b, home, p_a, paper_a, nfm.contributions(model, rows.iloc[i]), chk)


GROUPS = {
    "Quarterback": ["qb_d"],
    "Team strength": ["elo_d", "margin_d"],
    "Offense": ["off_d"],
    "Defense": ["def_d"],
    "Home field": ["home"],
    "Rest": ["rest_d"],
}


def reasons(call: MatchupCall, state: pd.DataFrame, games: pd.DataFrame, game_date, top: int = 3) -> list[dict]:
    a, b = call.team_a, call.team_b
    logit_a = float(np.log(call.p_a / (1 - call.p_a)))
    rest = {t: fm.rest_for(games, t, game_date) for t in (a, b)}
    out = []
    for name, feats in GROUPS.items():
        c = sum(call.drivers.get(f, 0.0) for f in feats)
        if abs(c) < 1e-9:
            continue
        without = 1 / (1 + np.exp(-(logit_a - c)))
        favors = a if c > 0 else b
        other = b if favors == a else a
        out.append({"factor": name, "favors": favors, "points": abs(call.p_a - without) * 100,
                    "fact": _fact(name, favors, other, state, rest, call.home)})
    return sorted(out, key=lambda r: -r["points"])[:top]


def _fact(name: str, t: str, o: str, state: pd.DataFrame, rest: dict, home: str | None) -> str:
    st_, so = state.loc[t], state.loc[o]
    if name == "Quarterback":
        return (f"{st_['qb_name'] or t + ' starter'} has been worth {st_['qb_pre']:+.2f} EPA per play recently; "
                f"{so['qb_name'] or o + ' starter'} {so['qb_pre']:+.2f}.")
    if name == "Team strength":
        return (f"{t}: Elo {st_['elo']:.0f}, {st_['margin_pg']:+.1f} points per game lately; "
                f"{o}: {so['elo']:.0f}, {so['margin_pg']:+.1f}.")
    if name == "Offense":
        return f"Offense EPA per play: {t} {st_['off_epa']:+.3f}, {o} {so['off_epa']:+.3f}."
    if name == "Defense":
        return f"EPA per play allowed: {t} {st_['def_epa']:+.3f}, {o} {so['def_epa']:+.3f} (lower is better)."
    if name == "Home field":
        return f"{home} is at home." if home else "Neutral site."
    if name == "Rest":
        return f"Days of rest: {t} {rest[t]}, {o} {rest[o]}" + (" (off a bye)." if (rest[t] or 0) >= 13 else ".")
    return ""


def prediction_rows(model: dict, state: pd.DataFrame, games: pd.DataFrame, day: date, now_utc: pd.Timestamp,
                    threshold: float = upset.DEFAULT_THRESHOLD) -> list[dict]:
    """Log rows for TODAY's games (US Eastern) that haven't kicked off. Each team's listed starting QB
    for today's game is used."""
    todays = week_games(games, day, days=1)
    rows = []
    through = state["data_through"].iloc[0] if "data_through" in state else None
    for g in todays.itertuples():
        if pd.isna(g.start_utc) or g.start_utc <= now_utc or g.home not in state.index or g.away not in state.index:
            continue
        st_ = state.copy()
        for side in ("home", "away"):                        # today's listed starters
            qid, qname = getattr(g, f"{side}_qb_id"), getattr(g, f"{side}_qb_name")
            if isinstance(qid, str) and qid and qid != st_.loc[getattr(g, side), "qb_id"]:
                st_ = _with_qb(st_, getattr(g, side), qid, qname)
        call = predict(model, st_, games, g.home, g.away, None if g.location == "Neutral" else g.home, day, threshold)
        chk = call.check
        rec = {t: fm.record_text(st_.loc[t, "s_wins"], st_.loc[t, "s_losses"], st_.loc[t, "s_ties"])
               for t in (g.home, g.away)}
        rows.append({
            "sport": "NFL", "game_id": str(g.game_id), "game_date": day.isoformat(),
            "start_utc": g.start_utc.isoformat(), "home": g.home, "away": g.away,
            "underdog": chk.underdog if chk else None, "favorite": chk.favorite if chk else None,
            "underdog_record": rec[chk.underdog] if chk else None, "favorite_record": rec[chk.favorite] if chk else None,
            "paper_prob": chk.paper_prob if chk else 0.5, "model_prob": chk.model_prob if chk else call.p_a,
            "home_model_prob": call.p_a, "home_paper_prob": call.paper_a,
            "edge": chk.edge if chk else 0.0, "threshold": threshold, "flagged": bool(chk and chk.flagged),
            "data_through": str(pd.Timestamp(through).date()) if through is not None and pd.notna(through) else None,
        })
    return rows


QB_RATINGS_PATH = track.UPSET_DIR / "nfl_qbs.parquet"


def qb_ratings(qb_stats: pd.DataFrame, games: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Every quarterback's rating after his latest game before `as_of` (for a changed starter)."""
    g = games[pd.to_datetime(games["gameday"]) < pd.Timestamp(as_of)]
    q = qb_stats[qb_stats["game_id"].isin(set(g["game_id"]))]
    tg = fm.team_games(g, pd.DataFrame(columns=fm.TEAM_STAT_COLS))
    rows = tg[["game_id", "season", "date", "gametime"]].drop_duplicates("game_id").merge(fm.qb_table(q), on="game_id")
    rows = rows.sort_values(["date", "gametime", "game_id"]).reset_index(drop=True)
    rows["_use"] = True
    qd = fm._decayed(rows.rename(columns={"player_id": "pid"}), "pid", "epa", "plays")
    rows["qb_pre"] = (qd["n"] + fm.QB_PRIOR_PLAYS * fm.QB_REPLACEMENT) / (qd["d"] + fm.QB_PRIOR_PLAYS)
    rows["qb_plays_w"] = qd["d"]
    latest = fm._qb_latest(rows)
    names = qb_stats.drop_duplicates("player_id", keep="last").set_index("player_id")["player_display_name"]
    return latest.assign(name=names.reindex(latest.index)).rename_axis("qb_id").reset_index()


def _with_qb(state: pd.DataFrame, team: str, qid: str, name: str) -> pd.DataFrame:
    st_ = state.copy()
    qbs = pd.read_parquet(QB_RATINGS_PATH).set_index("qb_id") if QB_RATINGS_PATH.exists() else pd.DataFrame()
    rating = float(qbs.loc[qid, "rating"]) if qid in qbs.index else fm.QB_REPLACEMENT
    st_.loc[team, ["qb_id", "qb_name", "qb_pre"]] = [qid, name, rating]
    return st_


def results_from_games(log: pd.DataFrame, games: pd.DataFrame, today: date) -> dict:
    pending = log[log["result"].isna()]
    if pending.empty:
        return {}
    g = games.set_index("game_id")
    out = {}
    for r in pending.itertuples():
        if r.game_id in g.index and pd.notna(g.loc[r.game_id, "home_score"]):
            hs, as_ = int(g.loc[r.game_id, "home_score"]), int(g.loc[r.game_id, "away_score"])
            out[r.flag_id] = (r.home if hs > as_ else (r.away if as_ > hs else None), hs, as_)
            if hs == as_:
                out[r.flag_id] = (None, hs, as_)                # a tie: nobody wins, the row is voided
        elif (today - date.fromisoformat(r.game_date)).days > VOID_AFTER_DAYS:
            out[r.flag_id] = (None, None, None)
    return out


# ---------------------------------------------------------------- the shared interface + what the page uses

class NflModule:
    sport = "NFL"
    slate_title = "This week"
    unit = "week"
    report_path = nfm.REPORT_PATH

    @staticmethod
    def model_path():
        return nfm.MODEL_PATH

    @staticmethod
    def state_paths():
        return (STATE_PATH, fm.GAMES_PATH)

    @property
    def log_path(self):
        return track.log_path(self.sport)
    home_word = "home field"

    def __init__(self, model: dict | None = None, state: pd.DataFrame | None = None, games: pd.DataFrame | None = None):
        self.model = model if model is not None else nfm.load_model(nfm.MODEL_PATH)
        self.state = state if state is not None else load_snapshot()
        self.games = games if games is not None else fm.load()[0]

    @property
    def ready(self) -> bool:
        return self.model is not None and self.state is not None

    def logo(self, team: str) -> str | None:
        return nfl_data.logo_url(team)

    def record(self, team: str) -> str:
        s = self.state.loc[team]
        return fm.record_text(s["s_wins"], s["s_losses"], s["s_ties"])

    def slate(self, today: date) -> pd.DataFrame:
        g = week_games(self.games, today)
        g = g[g["home"].isin(self.state.index) & g["away"].isin(self.state.index)]
        g["neutral"] = g["location"].eq("Neutral")
        return g[["game_id", "home", "away", "start_utc", "neutral"]]

    def predict(self, a, b, home, day, threshold=upset.DEFAULT_THRESHOLD) -> MatchupCall:
        return predict(self.model, self.state, self.games, a, b, home, day, threshold)

    def reasons(self, call, day):
        return reasons(call, self.state, self.games, day)

    def get_teams(self) -> list[Team]:
        return [Team(t, TEAM_NAMES.get(t, t), self.logo(t)) for t in sorted(self.state.index)]

    def get_games(self, day: date) -> list[Game]:
        g = week_games(self.games, day, days=1)
        return [Game("NFL", str(r.game_id), r.start_utc.isoformat(), r.home, r.away) for r in g.itertuples()]

    def get_matchup_stats(self, a: str, b: str, as_of: date) -> list[StatRow]:
        return fm.matchup_rows(self.state.loc[a], self.state.loc[b], fm.rest_for(self.games, a, as_of),
                               fm.rest_for(self.games, b, as_of))

    def head_to_head(self, a: str, b: str, day: date) -> dict:
        return fm.head_to_head(self.games, a, b, day)

    h2h_label = "last 4 seasons"

    def predict_win_prob(self, a: str, b: str, ctx: GameContext) -> Prediction:
        call = self.predict(a, b, ctx.home, ctx.game_date)
        return Prediction(a, b, call.p_a, call.drivers)

    def game_result(self, game: Game) -> Result | None:
        g = self.games[self.games["game_id"] == game.game_id]
        if g.empty or pd.isna(g["home_score"].iloc[0]):
            return None
        hs, as_ = int(g["home_score"].iloc[0]), int(g["away_score"].iloc[0])
        return Result(game.home if hs > as_ else (game.away if as_ > hs else None), hs, as_)
