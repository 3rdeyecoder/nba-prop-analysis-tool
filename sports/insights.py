"""Today's Lab findings, computed from stored NBA regular-season game logs.

Each function returns a small DataFrame of the top players for one card, with the sample
behind every number (game counts and date ranges) so the UI can show where it came from.
Thresholds keep tiny samples and bench cameos out; findings describe past games only.
"""
from __future__ import annotations

import pandas as pd

# Minimum average for a player to appear on Consistency / Matchup cards, per stat.
MIN_AVG = {"PTS": 15, "REB": 6, "AST": 4, "FG3M": 1.5, "PRA": 25, "PR": 20, "PA": 20, "RA": 10}
ACTIVE_DAYS = 10        # played within this many days of the latest game in the data
MIN_MINUTES = 20        # average minutes in the sample


def available_players(df: pd.DataFrame, exclude: frozenset[str] = frozenset()) -> set[str]:
    """Players who appeared in their team's most recent game (so anyone currently out with an
    injury, rest or suspension is left off), minus anyone on the manual unavailable list."""
    latest = df["game_date"].max()
    team_last = df.groupby("team")["game_date"].max()
    last = df.sort_values(["game_date", "game_id"]).groupby("player_id").tail(1)
    played_last = last["game_date"] >= last["team"].map(team_last)
    recent = last["game_date"] >= latest - pd.Timedelta(days=ACTIVE_DAYS)
    return set(last.loc[played_last & recent, "player_id"]) - set(exclude)


def missed_last_game(df: pd.DataFrame) -> pd.DataFrame:
    """Recent regulars who sat out their team's latest game (for the 'who's left out' note)."""
    latest = df["game_date"].max()
    team_last = df.groupby("team")["game_date"].max()
    last = df.sort_values(["game_date", "game_id"]).groupby("player_id").tail(1)
    recent = last["game_date"] >= latest - pd.Timedelta(days=ACTIVE_DAYS)
    out = last[recent & (last["game_date"] < last["team"].map(team_last))]
    mins = df[df["player_id"].isin(out["player_id"])].groupby("player_id")["MIN"].mean()
    out = out.assign(avg_min=out["player_id"].map(mins))
    return out[out["avg_min"] >= MIN_MINUTES].sort_values("avg_min", ascending=False)


def _active(df: pd.DataFrame, exclude: frozenset[str] = frozenset(), playing: dict | None = None) -> pd.DataFrame:
    """Available players; with `playing` (team -> tonight's opponent), only players whose CURRENT team
    (the team of their latest game) plays tonight."""
    d = df[df["player_id"].isin(available_players(df, exclude))]
    if playing is not None:
        d = d[d["player_id"].isin(current_team(d).loc[lambda t: t.isin(set(playing))].index)]
    return d


def current_team(df: pd.DataFrame) -> pd.Series:
    """player_id -> team of his most recent game (so a traded player shows his new team)."""
    return df.sort_values(["game_date", "game_id"]).groupby("player_id")["team"].last()


def _ordered(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["player_id", "game_date", "game_id"], kind="mergesort")


def _team_id(g: pd.DataFrame):
    return int(g["TEAM_ID"].iloc[-1]) if "TEAM_ID" in g and pd.notna(g["TEAM_ID"].iloc[-1]) else None


def _seasons(g: pd.DataFrame) -> list[str]:
    return sorted(g["season"].unique())


def heating_up(df: pd.DataFrame, stat: str = "PTS", recent_n: int = 5, baseline_n: int = 30,
               min_baseline: int = 15, top: int = 5, exclude: frozenset[str] = frozenset(),
               playing: dict | None = None) -> pd.DataFrame:
    """Biggest jump: average of the last `recent_n` games (all this season) vs the
    `baseline_n` games before them (which may reach into last season)."""
    current = df["season_year"].max()
    rows = []
    for pid, g in _ordered(_active(df, exclude, playing)).groupby("player_id", sort=False):
        if len(g) < recent_n + min_baseline:
            continue
        recent = g.tail(recent_n)
        base = g.iloc[-(recent_n + baseline_n):-recent_n]
        if (recent["season_year"] != current).any() or len(base) < min_baseline:
            continue
        if recent["MIN"].mean() < MIN_MINUTES:
            continue
        r, b = recent[stat].mean(), base[stat].mean()
        rows.append({
            "player_id": pid, "player_name": recent["player_name"].iloc[-1], "team": recent["team"].iloc[-1],
            "team_id": _team_id(recent), "recent_avg": r, "baseline_avg": b, "change": r - b,
            "recent_min": recent["MIN"].mean(), "baseline_min": base["MIN"].mean(),
            "recent_n": len(recent), "recent_first": recent["game_date"].min(), "recent_last": recent["game_date"].max(),
            "baseline_n": len(base), "baseline_first": base["game_date"].min(), "baseline_last": base["game_date"].max(),
            "seasons": _seasons(recent),
        })
    out = pd.DataFrame(rows)
    return out.nlargest(top, "change").reset_index(drop=True) if not out.empty else out


def consistency(df: pd.DataFrame, stat: str = "PTS", n: int = 10, top: int = 5,
                exclude: frozenset[str] = frozenset(), playing: dict | None = None) -> pd.DataFrame:
    """Steadiest producers: lowest coefficient of variation (std ÷ average) over the last
    `n` games, among players averaging at least MIN_AVG[stat]."""
    floor = MIN_AVG.get(stat, 0)
    rows = []
    for pid, g in _ordered(_active(df, exclude, playing)).groupby("player_id", sort=False):
        if len(g) < n:
            continue
        w = g.tail(n)
        avg = w[stat].mean()
        if avg < floor or avg <= 0 or w["MIN"].mean() < MIN_MINUTES:
            continue
        sd = w[stat].std(ddof=1)
        rows.append({
            "player_id": pid, "player_name": w["player_name"].iloc[-1], "team": w["team"].iloc[-1],
            "team_id": _team_id(w), "avg": avg, "std": sd, "cv": sd / avg, "low": w[stat].min(), "high": w[stat].max(),
            "n": n, "first": w["game_date"].min(), "last": w["game_date"].max(), "seasons": _seasons(w),
        })
    out = pd.DataFrame(rows)
    return out.nsmallest(top, "cv").reset_index(drop=True) if not out.empty else out


def matchup_history(df: pd.DataFrame, stat: str = "PTS", min_games: int = 6, top: int = 5,
                    exclude: frozenset[str] = frozenset(), playing: dict | None = None) -> pd.DataFrame:
    """Largest gap between a player's average against one opponent and their overall average,
    over the seasons in `df`. Needs `min_games` games vs that opponent. With `playing`
    (team -> tonight's opponent), only players whose current team plays tonight, and only against
    tonight's opponent (their history vs that team, on any team they've played for)."""
    floor = MIN_AVG.get(stat, 0)
    current = df["season_year"].max()
    this_season = df[df["season_year"] == current]
    keep = available_players(this_season, exclude)
    now_team = current_team(this_season)
    if playing is not None:
        keep = {p for p in keep if now_team.get(p) in playing}
    d = _ordered(df[df["player_id"].isin(keep)])
    overall = d.groupby("player_id").agg(overall=(stat, "mean"), overall_n=(stat, "size"),
                                         player_name=("player_name", "last"))
    overall["team"] = overall.index.map(now_team)
    overall = overall[overall["overall"] >= floor]
    vs = (d[d["player_id"].isin(overall.index)]
          .groupby(["player_id", "opponent"])
          .agg(opp_avg=(stat, "mean"), n=(stat, "size"), first=("game_date", "min"), last=("game_date", "max"))
          .reset_index())
    vs = vs[vs["n"] >= min_games].join(overall, on="player_id")
    if playing is not None:
        vs = vs[vs["opponent"] == vs["team"].map(playing)]
    if vs.empty:
        return vs
    vs["change"] = vs["opp_avg"] - vs["overall"]
    if "TEAM_ID" in df:   # logo ids for the player's team and the opponent
        ids = df.dropna(subset=["TEAM_ID"]).groupby("team")["TEAM_ID"].last().astype(int)
        vs["team_id"] = vs["team"].map(ids)
        vs["opp_team_id"] = vs["opponent"].map(ids)
    vs["seasons"] = [sorted(df["season"].unique())] * len(vs)
    best = vs.sort_values("change", ascending=False).drop_duplicates("player_id")   # one row per player
    return best.head(top).reset_index(drop=True)
