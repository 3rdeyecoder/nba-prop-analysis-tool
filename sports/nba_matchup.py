"""NBA matchup features, built only from the stored player game logs (no extra downloads).

Everything a prediction uses is computed from games BEFORE the game being predicted, so the
model never sees the future while training. `tests/test_nba_matchup.py` checks this directly.

Per team, per game:
  possessions  ~ FGA + 0.44*FTA - OREB + TOV, averaged with the opponent's estimate
  ratings      offensive / defensive rating = points scored / allowed per 100 possessions
  four factors eFG% (shooting), TOV% (turnovers), OREB% (offensive rebounding), FT rate (FTM per FGA),
               for the team's offense and for its defense (what opponents did)
  Elo          FiveThirtyEight-style: K=20, home court = 100 Elo points, margin-of-victory multiplier,
               ratings pulled 25% back toward average between seasons
"""
from __future__ import annotations


import numpy as np
import pandas as pd

from sports import nba

BOX = ["PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "AST", "STL", "BLK", "TOV", "PF", "MIN"]

# Elo settings (FiveThirtyEight's published NBA Elo method)
ELO_START, ELO_K, ELO_HOME, ELO_CARRY = 1505.0, 20.0, 100.0, 0.75


# ---------------------------------------------------------------- team-by-game table

def load_logs(season_type: str = "Regular Season") -> pd.DataFrame:
    """Raw stored logs for every season, with a `season` column."""
    frames = []
    for season, stype, path in nba.available_files():
        if stype == season_type:
            frames.append(pd.read_csv(path).assign(season=season))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def team_games(logs: pd.DataFrame) -> pd.DataFrame:
    """One row per team per game: box-score totals, opponent totals, ratings and four factors."""
    d = logs.copy()
    d["GAME_DATE"] = pd.to_datetime(d["GAME_DATE"])
    d["GAME_ID"] = d["GAME_ID"].astype(str).str.zfill(10)
    keys = ["season", "GAME_ID", "GAME_DATE", "TEAM_ID", "TEAM_ABBREVIATION"]
    t = (d.groupby(keys).agg(**{c: (c, "sum") for c in BOX}, MATCHUP=("MATCHUP", "first"), WL=("WL", "first"))
           .reset_index().rename(columns={"TEAM_ABBREVIATION": "team", "TEAM_ID": "team_id",
                                          "GAME_ID": "game_id", "GAME_DATE": "date"}))
    opp = t[["game_id", "team"] + BOX].rename(columns={"team": "opp", **{c: f"opp_{c}" for c in BOX}})
    g = t.merge(opp, on="game_id")
    g = g[g["team"] != g["opp"]]
    g = g[g.groupby("game_id")["team"].transform("size") == 2]           # complete games only

    # home / away / neutral: neutral when both sides are listed the same way
    listed_home = g["MATCHUP"].str.contains(" vs. ", regex=False)
    both_same = g.groupby("game_id")["MATCHUP"].transform(lambda m: m.str.contains(" vs. ", regex=False).nunique() == 1)
    g["venue"] = np.where(both_same, 0, np.where(listed_home, 1, -1))     # +1 home, -1 away, 0 neutral

    g["won"] = (g["WL"] == "W").astype(int)
    g["margin"] = g["PTS"] - g["opp_PTS"]
    own = g["FGA"] + 0.44 * g["FTA"] - g["OREB"] + g["TOV"]
    theirs = g["opp_FGA"] + 0.44 * g["opp_FTA"] - g["opp_OREB"] + g["opp_TOV"]
    g["poss"] = (own + theirs) / 2
    g["team_min"] = g["MIN"]                                             # player minutes summed (~240, more with OT)
    return g.sort_values(["date", "game_id", "team"]).reset_index(drop=True)


def _ratios(s: dict) -> dict:
    """Ratings and four factors from summed box-score totals (works on sums over any set of games)."""
    poss = s["poss"]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = {
            "ortg": 100 * s["PTS"] / poss, "drtg": 100 * s["opp_PTS"] / poss,
            "pace": 48 * 5 * poss / s["team_min"],
            "efg": (s["FGM"] + 0.5 * s["FG3M"]) / s["FGA"],
            "tov_pct": s["TOV"] / poss,
            "oreb_pct": s["OREB"] / (s["OREB"] + s["opp_DREB"]),
            "ft_rate": s["FTM"] / s["FGA"],
            "opp_efg": (s["opp_FGM"] + 0.5 * s["opp_FG3M"]) / s["opp_FGA"],
            "opp_tov_pct": s["opp_TOV"] / poss,
            "dreb_pct": s["DREB"] / (s["DREB"] + s["opp_OREB"]),
            "opp_ft_rate": s["opp_FTM"] / s["opp_FGA"],
        }
    out["net"] = out["ortg"] - out["drtg"]
    return out


SUM_COLS = ["PTS", "opp_PTS", "poss", "team_min", "FGM", "FG3M", "FGA", "TOV", "OREB", "DREB", "FTM",
            "opp_FGM", "opp_FG3M", "opp_FGA", "opp_TOV", "opp_OREB", "opp_DREB", "opp_FTM"]


def season_ratios(g: pd.DataFrame) -> pd.DataFrame:
    """Full-season ratings and four factors per team (for checking against known numbers)."""
    sums = g.groupby(["season", "team"])[SUM_COLS + ["won"]].sum()
    sums["gp"] = g.groupby(["season", "team"]).size()
    r = pd.DataFrame(_ratios({c: sums[c] for c in SUM_COLS}))
    r["gp"], r["wins"] = sums["gp"], sums["won"]
    return r


# ---------------------------------------------------------------- pregame features (no future data)

LAST_N = 10
REST_CAP = 7
PYTHAG_EXP = 14.0


def _prior_sums(g: pd.DataFrame, cols: list[str], group: list[str], window: int | None) -> pd.DataFrame:
    """Sums over each team's PREVIOUS games in the group (season): all of them, or the last `window`.
    The first game of a group has no previous games (NaN for windows, 0 for full sums)."""
    gb = g.groupby(group, sort=False)[cols]
    if window is None:
        return gb.cumsum() - g[cols]                                     # everything before this game
    return gb.transform(lambda s: s.shift(1).rolling(window, min_periods=1).sum())


def _streak(won: pd.Series) -> pd.Series:
    """Signed streak BEFORE each game: +3 = won last three, -2 = lost last two, 0 = first game."""
    out, cur = [], 0
    for w in won:
        out.append(cur)
        cur = (cur + 1 if cur > 0 else 1) if w else (cur - 1 if cur < 0 else -1)
    return pd.Series(out, index=won.index)


def elo_ratings(g: pd.DataFrame) -> pd.Series:
    """Pregame Elo for every team-game, processed game by game in date order."""
    elo, last_season, pre = {}, {}, {}
    games = g.sort_values(["date", "game_id"]).groupby("game_id", sort=False)
    for gid, gg in games:
        a, b = gg.iloc[0], gg.iloc[1]
        for r in (a, b):                                                  # new season: pull toward average
            if last_season.get(r["team"]) not in (None, r["season"]):
                elo[r["team"]] = ELO_CARRY * elo[r["team"]] + (1 - ELO_CARRY) * ELO_START
            last_season[r["team"]] = r["season"]
        ea, eb = elo.get(a["team"], ELO_START), elo.get(b["team"], ELO_START)
        pre[(gid, a["team"])], pre[(gid, b["team"])] = ea, eb
        home_adj = ELO_HOME * a["venue"]                                  # +100 if a at home, -100 away, 0 neutral
        exp_a = 1 / (1 + 10 ** (-(ea + home_adj - eb) / 400))
        mov = abs(a["margin"])
        winner_diff = (ea + home_adj - eb) if a["won"] else (eb - ea - home_adj)
        mult = ((mov + 3) ** 0.8) / (7.5 + 0.006 * winner_diff)
        shift = ELO_K * mult * (a["won"] - exp_a)
        elo[a["team"]], elo[b["team"]] = ea + shift, eb - shift
    return pd.Series([pre[(r.game_id, r.team)] for r in g.itertuples()], index=g.index)


def pregame_features(g: pd.DataFrame) -> pd.DataFrame:
    """Add pregame features to the team-game table. Each row only uses that team's earlier games."""
    g = g.sort_values(["team", "date", "game_id"]).reset_index(drop=True)
    by_season = ["team", "season"]
    ssn = _prior_sums(g, SUM_COLS + ["won"], by_season, None)
    l10 = _prior_sums(g, SUM_COLS + ["won"], by_season, LAST_N)
    gp = g.groupby(by_season).cumcount()
    g["gp"] = gp
    for prefix, sums in (("s_", ssn), ("l10_", l10)):
        for k, v in _ratios({c: sums[c] for c in SUM_COLS}).items():
            g[prefix + k] = v.where(gp > 0)
    g["s_wins"], g["s_losses"] = ssn["won"], gp - ssn["won"]
    # Luck Meter: actual win % minus "deserved" win % from points scored/allowed (Pythagorean, exponent 14).
    # Close-game results barely carry over, so records that outrun the scoring margin tend to fall back.
    with np.errstate(divide="ignore", invalid="ignore"):
        g["s_deserved"] = (1 / (1 + (ssn["opp_PTS"].astype(float) / ssn["PTS"].astype(float)) ** PYTHAG_EXP)).where(gp > 0)
    g["s_luck"] = (ssn["won"] / gp.replace(0, np.nan)) - g["s_deserved"]
    g["l10_wins"] = l10["won"].fillna(0)
    g["l10_games"] = np.minimum(gp, LAST_N)

    # home/away splits (season to date): sums over earlier home games / earlier away games only
    for side, flag in (("home", 1), ("away", -1)):
        mask = (g["venue"] == flag).astype(int)
        part = g[["PTS", "opp_PTS", "poss"]].mul(mask, axis=0)
        sums = part.groupby([g["team"], g["season"]]).cumsum() - part
        n_before = mask.groupby([g["team"], g["season"]]).cumsum() - mask
        g[f"{side}_net"] = (100 * (sums["PTS"] - sums["opp_PTS"]) / sums["poss"]).where(n_before > 0)
        g[f"{side}_games"] = n_before

    # schedule: rest days, back-to-backs, games in the previous 6 days
    prev = g.groupby("team")["date"].shift(1)
    g["rest_days"] = (g["date"] - prev).dt.days.clip(upper=REST_CAP).fillna(REST_CAP)
    g["b2b"] = (g["rest_days"] == 1).astype(int)
    def games_last_6(dates: pd.Series) -> pd.Series:
        vals = dates.values
        return pd.Series([((vals[:i] >= d - np.timedelta64(6, "D")) & (vals[:i] < d)).sum() for i, d in enumerate(vals)],
                         index=dates.index)
    g["games_last6"] = g.groupby("team", group_keys=False)["date"].apply(games_last_6)
    g["streak"] = g.groupby(by_season, group_keys=False)["won"].apply(_streak)
    g["elo"] = elo_ratings(g)
    return g.sort_values(["date", "game_id", "team"]).reset_index(drop=True)


# ---------------------------------------------------------------- availability (missing regulars)

REG_WINDOW, REG_MIN_GAMES, REG_MIN_MINUTES = 10, 5, 24.0


def missing_regulars(logs: pd.DataFrame) -> pd.DataFrame:
    """For each team-game: regulars who did NOT play in the team's previous game (known before tip-off).
    A regular played in >= 5 of the team's previous 10 games, averaging >= 24 minutes when playing.
    Returns game_id, team, missing_count, missing_min_share (their usual minutes / 240), missing_names."""
    d = logs[["season", "GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION", "PLAYER_ID", "PLAYER_NAME", "MIN"]].copy()
    d["GAME_ID"] = d["GAME_ID"].astype(str).str.zfill(10)
    d["GAME_DATE"] = pd.to_datetime(d["GAME_DATE"])
    rows = []
    for (team, season), tg in d.groupby(["TEAM_ABBREVIATION", "season"], sort=False):
        games = tg.groupby("GAME_ID", sort=False).agg(date=("GAME_DATE", "first")).sort_values("date")
        played = {gid: dict(zip(x["PLAYER_ID"], x["MIN"])) for gid, x in tg.groupby("GAME_ID")}
        names = dict(zip(tg["PLAYER_ID"], tg["PLAYER_NAME"]))
        order = list(games.index)
        for i, gid in enumerate(order):
            prev = order[max(0, i - REG_WINDOW):i]
            if not prev:
                rows.append((gid, team, 0, 0.0, ""))
                continue
            mins: dict = {}
            for p in prev:
                for pid, m in played[p].items():
                    mins.setdefault(pid, []).append(float(m))
            regulars = {pid: float(np.mean(m)) for pid, m in mins.items()
                        if len(m) >= REG_MIN_GAMES and np.mean(m) >= REG_MIN_MINUTES}
            last = played[prev[-1]]
            out = {pid: m for pid, m in regulars.items() if pid not in last}
            rows.append((gid, team, len(out), sum(out.values()) / 240,
                         ", ".join(names[p] for p in sorted(out, key=out.get, reverse=True))))
    return pd.DataFrame(rows, columns=["game_id", "team", "missing_count", "missing_min_share", "missing_names"])


def build_features(logs: pd.DataFrame | None = None) -> pd.DataFrame:
    """Everything above, joined: one row per team-game with all pregame features."""
    from sports import nba_players

    logs = load_logs() if logs is None else logs
    f = pregame_features(team_games(logs))
    miss = missing_regulars(logs)
    f = f.merge(miss, on=["game_id", "team"], how="left").fillna(
        {"missing_count": 0, "missing_min_share": 0.0, "missing_names": ""})
    if "PLUS_MINUS" in logs.columns:                                     # player-based roster strength
        strength = nba_players.team_strength(nba_players.player_ratings(logs))
        f = f.merge(strength, on=["game_id", "team"], how="left")
    return f


# ---------------------------------------------------------------- current state & matchup view

STATE_COLS = ["team", "team_id", "season", "gp", "s_wins", "s_losses", "s_net", "s_ortg", "s_drtg", "s_pace",
              "s_efg", "s_tov_pct", "s_oreb_pct", "s_ft_rate", "s_opp_efg", "s_opp_tov_pct", "s_dreb_pct",
              "s_opp_ft_rate", "l10_wins", "l10_games", "l10_net", "home_net", "away_net", "home_games",
              "away_games", "streak", "elo", "missing_count", "missing_min_share", "missing_names", "last_game",
              "s_deserved", "s_luck", "roster_gs36", "roster_pm48", "roster_size"]


def current_state(logs: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Each team's pregame numbers for a game on `as_of`, using only games before that date.
    Implemented by adding one placeholder game per team on `as_of` and reading its pregame row,
    so the page uses exactly the same feature code as model training. Schedule features
    (rest, back-to-back) are left for `schedule_for` since they depend on the actual game date."""
    as_of = pd.Timestamp(as_of).normalize()
    past = logs[pd.to_datetime(logs["GAME_DATE"]) < as_of]
    if past.empty:
        return pd.DataFrame(columns=STATE_COLS)
    season = past["season"].max()
    last = (past[past["season"] == season].sort_values("GAME_DATE")
            .groupby("TEAM_ABBREVIATION").tail(1)[["TEAM_ABBREVIATION", "TEAM_ID", "GAME_DATE"]])
    fake = []
    for i, r in enumerate(last.itertuples(index=False)):
        gid = f"9{i:09d}"
        for team, tid in ((r.TEAM_ABBREVIATION, r.TEAM_ID), (f"_P{i}", -1)):        # placeholder opponent
            fake.append({"season": season, "GAME_ID": gid, "GAME_DATE": as_of.strftime("%Y-%m-%d"),
                         "TEAM_ID": tid, "TEAM_ABBREVIATION": team, "MATCHUP": f"{team} vs. X",
                         "WL": "W", "PLAYER_ID": -1, "PLAYER_NAME": "", "PLUS_MINUS": 0,
                         **{c: 0 for c in BOX}, "FGA": 1})
    f = build_features(pd.concat([past, pd.DataFrame(fake)], ignore_index=True))
    state = f[f["game_id"].str.startswith("9") & ~f["team"].str.startswith("_P")].copy()
    state = state.merge(last.rename(columns={"TEAM_ABBREVIATION": "team", "GAME_DATE": "last_game"})[["team", "last_game"]],
                        on="team")
    state["last_game"] = pd.to_datetime(state["last_game"])
    return state[STATE_COLS].set_index("team", drop=False)


def schedule_for(team_games_df: pd.DataFrame, team: str, game_date: pd.Timestamp) -> dict:
    """Rest days, back-to-back and games in the previous 6 days for a game on `game_date`."""
    d = pd.Timestamp(game_date).normalize()
    played = team_games_df.loc[(team_games_df["team"] == team) & (team_games_df["date"] < d), "date"]
    if played.empty:
        return {"rest_days": REST_CAP, "b2b": 0, "games_last6": 0}
    rest = min((d - played.max()).days, REST_CAP)
    return {"rest_days": rest, "b2b": int(rest == 1), "games_last6": int((played >= d - pd.Timedelta(days=6)).sum())}


def head_to_head(team_games_df: pd.DataFrame, a: str, b: str, before: pd.Timestamp, seasons: int = 3) -> dict:
    """Meetings in the last `seasons` seasons before `before`, from team a's side."""
    g = team_games_df[(team_games_df["team"] == a) & (team_games_df["opp"] == b) & (team_games_df["date"] < before)]
    keep = sorted(team_games_df["season"].unique())[-seasons:]
    g = g[g["season"].isin(keep)].sort_values("date")
    return {"games": len(g), "a_wins": int(g["won"].sum()), "b_wins": int(len(g) - g["won"].sum()),
            "avg_margin_a": float(g["margin"].mean()) if len(g) else None,
            "recent": [(r.date.date().isoformat(), int(r.PTS), int(r.opp_PTS), "home" if r.venue == 1 else
                        ("away" if r.venue == -1 else "neutral")) for r in g.tail(5).itertuples()]}


def _pct(x):
    return None if x is None or pd.isna(x) else 100 * float(x)


def matchup_rows(sa: pd.Series, sb: pd.Series, sched_a: dict, sched_b: dict) -> list:
    """Side-by-side rows for the Matchup page. `better` says which side each stat favours."""
    from matchup.base import StatRow

    def row(section, label, a, b, higher_is_better=True, fmt="{:.1f}", note=""):
        better = None
        if a is not None and b is not None and not (pd.isna(a) or pd.isna(b)) and a != b and higher_is_better is not None:
            better = "a" if (a > b) == higher_is_better else "b"
        return StatRow(section, label, a, b, better, fmt, note)

    def rec(w, l):
        return f"{int(w)}-{int(l)}"

    rows = [
        row("Strength", "Elo rating", sa["elo"], sb["elo"], fmt="{:.0f}",
            note="Carries over between seasons; 1505 is average"),
        StatRow("Strength", "Record", rec(sa["s_wins"], sa["s_losses"]), rec(sb["s_wins"], sb["s_losses"]),
                "a" if sa["s_wins"] / max(sa["gp"], 1) > sb["s_wins"] / max(sb["gp"], 1) else
                ("b" if sa["s_wins"] / max(sa["gp"], 1) < sb["s_wins"] / max(sb["gp"], 1) else None), "{}"),
        row("Strength", "Net rating", sa["s_net"], sb["s_net"], fmt="{:+.1f}", note="Points per 100 possessions"),
        StatRow("Form", "Last 10", rec(sa["l10_wins"], sa["l10_games"] - sa["l10_wins"]),
                rec(sb["l10_wins"], sb["l10_games"] - sb["l10_wins"]),
                "a" if sa["l10_wins"] > sb["l10_wins"] else ("b" if sa["l10_wins"] < sb["l10_wins"] else None), "{}"),
        row("Form", "Net rating, last 10", sa["l10_net"], sb["l10_net"], fmt="{:+.1f}"),
        StatRow("Form", "Streak", _streak_text(sa["streak"]), _streak_text(sb["streak"]),
                "a" if sa["streak"] > sb["streak"] else ("b" if sa["streak"] < sb["streak"] else None), "{}"),
        row("Offense", "Offensive rating", sa["s_ortg"], sb["s_ortg"]),
        row("Offense", "Effective FG%", _pct(sa["s_efg"]), _pct(sb["s_efg"])),
        row("Offense", "Turnover %", _pct(sa["s_tov_pct"]), _pct(sb["s_tov_pct"]), higher_is_better=False),
        row("Offense", "Off. rebound %", _pct(sa["s_oreb_pct"]), _pct(sb["s_oreb_pct"])),
        row("Offense", "Free throw rate", _pct(sa["s_ft_rate"]), _pct(sb["s_ft_rate"]), note="FTM per 100 FGA"),
        row("Defense", "Defensive rating", sa["s_drtg"], sb["s_drtg"], higher_is_better=False),
        row("Defense", "Opponent eFG%", _pct(sa["s_opp_efg"]), _pct(sb["s_opp_efg"]), higher_is_better=False),
        row("Defense", "Forced turnover %", _pct(sa["s_opp_tov_pct"]), _pct(sb["s_opp_tov_pct"])),
        row("Defense", "Def. rebound %", _pct(sa["s_dreb_pct"]), _pct(sb["s_dreb_pct"])),
        row("Defense", "Opponent FT rate", _pct(sa["s_opp_ft_rate"]), _pct(sb["s_opp_ft_rate"]), higher_is_better=False),
        row("Tempo", "Pace", sa["s_pace"], sb["s_pace"], higher_is_better=None, note="Possessions per 48 minutes"),
        row("Splits", "Net rating at home", sa["home_net"], sb["home_net"], fmt="{:+.1f}"),
        row("Splits", "Net rating on the road", sa["away_net"], sb["away_net"], fmt="{:+.1f}"),
        row("Schedule", "Days of rest", sched_a["rest_days"], sched_b["rest_days"], fmt="{:.0f}"),
        StatRow("Schedule", "Back-to-back", "Yes" if sched_a["b2b"] else "No", "Yes" if sched_b["b2b"] else "No",
                "b" if sched_a["b2b"] > sched_b["b2b"] else ("a" if sched_a["b2b"] < sched_b["b2b"] else None), "{}"),
        row("Schedule", "Games in last 6 days", sched_a["games_last6"], sched_b["games_last6"],
            higher_is_better=False, fmt="{:.0f}"),
        row("Availability", "Regulars who missed last game", sa["missing_count"], sb["missing_count"],
            higher_is_better=False, fmt="{:.0f}",
            note=f"{sa['team']}: {sa['missing_names'] or 'none'} · {sb['team']}: {sb['missing_names'] or 'none'}"),
    ]
    return rows


def _streak_text(s) -> str:
    s = int(s)
    return "—" if s == 0 else (f"W{s}" if s > 0 else f"L{-s}")
