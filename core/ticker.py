"""'Latest results' ticker: recent final scores, built from stored data (no network calls).

NBA: team points are the sum of their players' points in the stored game logs (exact).
NFL / MLB: official final scores from the schedules saved by `refresh.nfl` / `refresh.mlb`.

On a sport's page the ticker shows only that league; on Today's Lab and Call It it mixes the
leagues that are in season (played within the last IN_SEASON_DAYS days).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from core.cards import LOGO
from sports import mlb, nba, nfl

PER_LEAGUE = 16          # games shown on a sport's own page
PER_LEAGUE_MIXED = 8     # games per league on the mixed (home / Call It) ticker
IN_SEASON_DAYS = 10


@st.cache_data(show_spinner=False, max_entries=4)
def _nba_games(files: tuple[tuple[str, float], ...]) -> list[dict]:
    frames = [pd.read_csv(p, usecols=["GAME_ID", "GAME_DATE", "TEAM_ID", "TEAM_ABBREVIATION", "MATCHUP", "PTS"])
              for p, _ in files]
    if not frames:
        return []
    d = pd.concat(frames, ignore_index=True)
    d["GAME_DATE"] = pd.to_datetime(d["GAME_DATE"])
    last_days = sorted(d["GAME_DATE"].unique())[-2:]                      # the two most recent game days
    d = d[d["GAME_DATE"].isin(last_days)]
    teams = (d.groupby(["GAME_ID", "TEAM_ABBREVIATION"])
              .agg(pts=("PTS", "sum"), date=("GAME_DATE", "first"), team_id=("TEAM_ID", "first"),
                   home=("MATCHUP", lambda m: " vs. " in m.iloc[0]))
              .reset_index())
    games = []
    for gid, g in teams.groupby("GAME_ID"):
        if len(g) != 2:
            continue
        home, away = g[g["home"]].iloc[0], g[~g["home"]].iloc[0]
        games.append({"league": "NBA", "date": home["date"], "sort": str(gid),
                      "away": away["TEAM_ABBREVIATION"], "away_pts": int(away["pts"]),
                      "away_logo": LOGO.format(int(away["team_id"])),
                      "home": home["TEAM_ABBREVIATION"], "home_pts": int(home["pts"]),
                      "home_logo": LOGO.format(int(home["team_id"]))})
    return sorted(games, key=lambda x: (x["date"], x["sort"]), reverse=True)


@st.cache_data(show_spinner=False, max_entries=4)
def _nfl_games(path: str, mtime: float) -> list[dict]:
    saved = {}
    if nfl.TEAMS_PATH.exists():
        t = pd.read_parquet(nfl.TEAMS_PATH)
        saved = dict(zip(t["team_abbr"], t["team_logo_espn"]))
    s = pd.read_parquet(path).dropna(subset=["away_score", "home_score"])
    if s.empty:
        return []
    s = s[s["week"] == s["week"].max()]                                   # latest week with final scores
    return [{"league": "NFL", "date": pd.Timestamp(r["gameday"]), "sort": r["game_id"],
             "away": r["away_team"], "away_pts": int(r["away_score"]), "away_logo": nfl.logo_url(r["away_team"], saved),
             "home": r["home_team"], "home_pts": int(r["home_score"]), "home_logo": nfl.logo_url(r["home_team"], saved),
             "label": f"Week {int(r['week'])}"}
            for _, r in s.sort_values(["gameday", "game_id"], ascending=False).iterrows()]


def _mlb_logo(r, side: str) -> str | None:
    tid = r.get(f"{side}_id")
    if tid is None or pd.isna(tid):
        tid = mlb.TEAM_IDS.get(r[f"{side}_abbr"])
    return mlb.LOGO.format(int(tid)) if tid else None


@st.cache_data(show_spinner=False, max_entries=4)
def _mlb_games(path: str, mtime: float) -> list[dict]:
    s = pd.read_parquet(path).dropna(subset=["away_score", "home_score"])
    if s.empty:
        return []
    s["game_date"] = pd.to_datetime(s["game_date"])
    days = sorted(s["game_date"].unique())[-3:]                          # last three game days
    s = s[s["game_date"].isin(days)].sort_values(["game_date", "game_number", "game_pk"], ascending=False)
    return [{"league": "MLB", "date": r["game_date"], "sort": str(r["game_pk"]),
             "away": r["away_abbr"], "away_pts": int(r["away_score"]), "away_logo": _mlb_logo(r, "away"),
             "home": r["home_abbr"], "home_pts": int(r["home_score"]), "home_logo": _mlb_logo(r, "home"),
             "label": f"{r['game_date']:%b} {r['game_date'].day}" + (" (G2)" if r["game_number"] == 2 else "")}
            for _, r in s.iterrows()]


def _latest(paths_glob, path_fn, loader):
    seasons = sorted(int(p.stem.rsplit("_", 1)[1]) for p in paths_glob)
    if not seasons:
        return []
    path = path_fn(seasons[-1])
    return loader(str(path), path.stat().st_mtime)


def by_league() -> dict[str, list[dict]]:
    out = {"NBA": [], "NFL": [], "MLB": []}
    files = nba.available_files()
    if files:
        latest = max(s for s, _, _ in files)
        out["NBA"] = _nba_games(tuple((str(p), p.stat().st_mtime) for s, _, p in files if s == latest))
    out["NFL"] = _latest(nfl.NFL_DIR.glob("schedule_*.parquet"), nfl.schedule_path, _nfl_games)
    out["MLB"] = _latest(mlb.MLB_DIR.glob("schedule_*.parquet"), mlb.schedule_path, _mlb_games)
    return out


def latest_games(league: str | None = None, today=None) -> list[dict]:
    """One league's recent finals, or (league=None) a mix of the leagues in season."""
    games = by_league()
    if league:
        return games.get(league, [])[:PER_LEAGUE]
    today = pd.Timestamp(today or datetime.now(ZoneInfo("America/New_York")).date())
    in_season = [lg for lg, gs in games.items()
                 if gs and (today - max(g["date"] for g in gs)).days <= IN_SEASON_DAYS]
    leagues = in_season or [lg for lg, gs in games.items() if gs]      # off-season everywhere: show what we have
    return [g for lg in leagues for g in games[lg][:PER_LEAGUE_MIXED]]


def _team_row(abbr: str, pts: int, logo, won: bool) -> str:
    img = f'<img src="{logo}" alt="">' if logo else '<span class="tk-dot"></span>'
    return f'<div class="tk-row{" tk-win" if won else ""}">{img}<span class="tk-abbr">{abbr}</span><span class="tk-pts">{pts}</span></div>'


def render(league: str | None = None) -> None:
    try:
        games = latest_games(league)
    except Exception:  # noqa: BLE001 - the ticker must never break the page
        return
    if not games:
        return
    cells = []
    for g in games:
        d = g["date"]
        when = g.get("label") or f"{d:%b} {d.day}"
        cells.append(
            f'<div class="tk-game"><div class="tk-head">{g["league"]} · Final · {when}</div>'
            + _team_row(g["away"], g["away_pts"], g["away_logo"], g["away_pts"] > g["home_pts"])
            + _team_row(g["home"], g["home_pts"], g["home_logo"], g["home_pts"] > g["away_pts"])
            + "</div>")
    title = f"{league}<br>RESULTS" if league else "LATEST<br>RESULTS"
    st.markdown(f'<div class="pl-ticker"><div class="tk-label">{title}</div>{"".join(cells)}</div>',
                unsafe_allow_html=True)
