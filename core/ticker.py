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


def _home_team(matchups: list[str]) -> str | None:
    """Home team from NBA matchup text: 'BOS vs. NYK' -> BOS is home; 'NYK @ BOS' -> BOS is home.
    Uses the answer the rows agree on; None if they disagree or the text is unrecognised."""
    votes = set()
    for m in matchups:
        m = str(m)
        if " vs. " in m:
            votes.add(m.split(" vs. ")[0].strip())
        elif " @ " in m:
            votes.add(m.split(" @ ")[1].strip())
    return votes.pop() if len(votes) == 1 else None


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
                   matchup=("MATCHUP", "first"))
              .reset_index())
    games = []
    for gid, g in teams.groupby("GAME_ID"):
        if len(g) != 2:
            continue
        home_abbr = _home_team(g["matchup"].tolist())
        if home_abbr not in set(g["TEAM_ABBREVIATION"]):
            continue                                       # can't tell home from away: skip just this game
        home = g[g["TEAM_ABBREVIATION"] == home_abbr].iloc[0]
        away = g[g["TEAM_ABBREVIATION"] != home_abbr].iloc[0]
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


def _nba_results() -> list[dict]:
    files = nba.available_files()
    if not files:
        return []
    latest = max(s for s, _, _ in files)
    return _nba_games(tuple((str(p), p.stat().st_mtime) for s, _, p in files if s == latest))


def by_league() -> dict[str, list[dict]]:
    """Recent finals per league. Each league is loaded on its own, so a problem in one league's
    data can never blank out the others."""
    loaders = {
        "NBA": _nba_results,
        "NFL": lambda: _latest(nfl.NFL_DIR.glob("schedule_*.parquet"), nfl.schedule_path, _nfl_games),
        "MLB": lambda: _latest(mlb.MLB_DIR.glob("schedule_*.parquet"), mlb.schedule_path, _mlb_games),
    }
    out = {}
    for league, load in loaders.items():
        try:
            out[league] = load()
        except Exception:  # noqa: BLE001
            out[league] = []
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


# ---------------------------------------------------------------- upcoming games ("today" / "up next")

UPCOMING_WINDOW_DAYS = 7      # mixed ticker: only show a league's next games if they're within a week
IN_PROGRESS_HOURS = 4         # a game that started less than this long ago is still shown (no live scores)
ET = ZoneInfo("America/New_York")


@st.cache_data(show_spinner=False, max_entries=4)
def _nba_schedule(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_parquet(path)


@st.cache_data(show_spinner=False, max_entries=4)
def _nba_finished_ids(files: tuple[tuple[str, float], ...]) -> frozenset[str]:
    ids = set()
    for p, _ in files:
        ids |= set(pd.read_csv(p, usecols=["GAME_ID"], dtype={"GAME_ID": str})["GAME_ID"].str.zfill(10))
    return frozenset(ids)


def _nba_upcoming_rows() -> list[dict]:
    files = nba.available_files()
    if not files:
        return []
    latest = max(s for s, _, _ in files)
    path = nba.schedule_path(latest)
    if not path.exists():
        return []
    sched = _nba_schedule(str(path), path.stat().st_mtime)
    done = _nba_finished_ids(tuple((str(p), p.stat().st_mtime) for s, _, p in files if s == latest))
    sched = sched[~sched["game_id"].isin(done)]
    return [{"league": "NBA", "start": r["start_utc"], "away": r["away"], "home": r["home"],
             "away_logo": LOGO.format(int(r["away_id"])) if pd.notna(r["away_id"]) else None,
             "home_logo": LOGO.format(int(r["home_id"])) if pd.notna(r["home_id"]) else None,
             "away_record": r.get("away_record"), "home_record": r.get("home_record"), "tv": r.get("tv")}
            for _, r in sched.iterrows()]


def _nfl_upcoming_rows() -> list[dict]:
    seasons = sorted(int(p.stem.rsplit("_", 1)[1]) for p in nfl.NFL_DIR.glob("schedule_*.parquet"))
    if not seasons:
        return []
    s = pd.read_parquet(nfl.schedule_path(seasons[-1]))
    if "gametime" not in s:
        return []                                              # saved before kickoff times were stored
    s = s[s["away_score"].isna() & s["gameday"].notna() & s["gametime"].notna()]
    saved = {}
    if nfl.TEAMS_PATH.exists():
        t = pd.read_parquet(nfl.TEAMS_PATH)
        saved = dict(zip(t["team_abbr"], t["team_logo_espn"]))
    out = []
    for _, r in s.iterrows():
        try:
            start = pd.Timestamp(f"{r['gameday']} {r['gametime']}").tz_localize(ET).tz_convert("UTC")
        except (ValueError, TypeError):
            continue
        out.append({"league": "NFL", "start": start, "away": r["away_team"], "home": r["home_team"],
                    "away_logo": nfl.logo_url(r["away_team"], saved), "home_logo": nfl.logo_url(r["home_team"], saved),
                    "away_record": None, "home_record": None, "tv": None})
    return out


def _next_day(games: list[dict], now: pd.Timestamp, tz) -> list[dict]:
    """Games on the next game day (local to the viewer), including ones that just tipped off."""
    games = [g for g in games if g["start"] >= now - pd.Timedelta(hours=IN_PROGRESS_HOURS)]
    if not games:
        return []
    day = min(g["start"].tz_convert(tz).date() for g in games)
    return sorted((g for g in games if g["start"].tz_convert(tz).date() == day), key=lambda g: (g["start"], g["away"]))


def upcoming(league: str | None = None, now=None, tz=None) -> list[dict]:
    """Today's games (or the next game day) for one league, or a mix of leagues playing within a week."""
    tz = tz or ET
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    sources = {"NBA": _nba_upcoming_rows, "NFL": _nfl_upcoming_rows}
    leagues = [league] if league else list(sources)
    out = []
    for lg in leagues:
        if lg not in sources:
            continue
        try:
            games = _next_day(sources[lg](), now, tz)
        except Exception:  # noqa: BLE001 - schedule problems never break the page
            games = []
        if not league and games and (games[0]["start"] - now).days > UPCOMING_WINDOW_DAYS:
            continue
        out += games[: (PER_LEAGUE if league else PER_LEAGUE_MIXED)]
    return out


def _time_label(start: pd.Timestamp, tz, today) -> str:
    local = start.tz_convert(tz)
    t = f"{local.strftime('%I').lstrip('0')}:{local:%M %p}"
    return t if local.date() == today else f"{local:%a} {t}"


def _upcoming_row(abbr: str, logo, record) -> str:
    img = f'<img src="{logo}" alt="">' if logo else '<span class="tk-dot"></span>'
    rec = f'<span class="tk-rec">{record}</span>' if isinstance(record, str) and record else ""
    return f'<div class="tk-row">{img}<span class="tk-abbr">{abbr}</span>{rec}</div>'


def _team_row(abbr: str, pts: int, logo, won: bool) -> str:
    img = f'<img src="{logo}" alt="">' if logo else '<span class="tk-dot"></span>'
    return f'<div class="tk-row{" tk-win" if won else ""}">{img}<span class="tk-abbr">{abbr}</span><span class="tk-pts">{pts}</span></div>'


def render(league: str | None = None) -> None:
    try:
        games = latest_games(league)
    except Exception:  # noqa: BLE001 - the ticker must never break the page
        games = []
    try:
        from core.ui import viewer_timezone
        tz = viewer_timezone()
        today = pd.Timestamp.now(tz=tz).date()
        coming = upcoming(league, tz=tz)
    except Exception:  # noqa: BLE001
        coming, tz, today = [], ET, None
    if not games and not coming:
        return
    prefix = f"{league} " if league else ""
    up_cells, res_cells = [], []
    is_today = bool(coming) and any(g["start"].tz_convert(tz).date() == today for g in coming)
    if coming:
        label = f"{prefix}TODAY" if is_today else f"{prefix}UP NEXT"
        up_cells.append(f'<div class="tk-label tk-label-up">{label.replace(" ", "<br>", 1) if league else label}</div>')
        for g in coming:
            tv = f'<div class="tk-tv">{g["tv"]}</div>' if isinstance(g.get("tv"), str) and g["tv"] else ""
            up_cells.append(f'<div class="tk-game tk-up"><div class="tk-head">{g["league"]} · '
                            f'{_time_label(g["start"], tz, today)}</div>'
                            + _upcoming_row(g["away"], g["away_logo"], g.get("away_record"))
                            + _upcoming_row(g["home"], g["home_logo"], g.get("home_record")) + tv + "</div>")
    if games:
        title = f"{league}<br>RESULTS" if league else "LATEST<br>RESULTS"
        res_cells.append(f'<div class="tk-label">{title}</div>')
        for g in games:
            d = g["date"]
            when = g.get("label") or f"{d:%b} {d.day}"
            res_cells.append(
                f'<div class="tk-game"><div class="tk-head">{g["league"]} · Final · {when}</div>'
                + _team_row(g["away"], g["away_pts"], g["away_logo"], g["away_pts"] > g["home_pts"])
                + _team_row(g["home"], g["home_pts"], g["home_logo"], g["home_pts"] > g["away_pts"])
                + "</div>")
    # Games today come first. Otherwise the latest results lead and the next game day follows,
    # so a long "up next" list never pushes last night's scores off-screen.
    cells = up_cells + res_cells if is_today else res_cells + up_cells
    st.markdown(f'<div class="pl-ticker">{"".join(cells)}</div>', unsafe_allow_html=True)
