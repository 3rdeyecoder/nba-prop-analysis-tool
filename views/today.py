"""Today's Lab: starting points built from the stored NBA data. Every card links into the
NBA page with the right player, stat and filters already selected."""
from datetime import datetime

import pandas as pd
import streamlit as st

from core import cards as card_ui
from core import links, unavailable
from core.storage import read_meta
from core.ui import local_time, viewer_timezone
from sports import insights, nba

STATS = {"Points": "PTS", "Rebounds": "REB", "Assists": "AST", "3-pointers made": "FG3M",
         "Pts + Reb + Ast": "PRA"}
UNIT = {"PTS": "pts", "REB": "reb", "AST": "ast", "FG3M": "3PM", "PRA": "PRA"}


@st.cache_data(show_spinner=False, max_entries=8)
def _load(paths: tuple[tuple[str, str, float], ...]) -> pd.DataFrame:
    from pathlib import Path
    return pd.concat([nba.load_file(Path(p), s, "Regular Season") for s, p, _ in paths], ignore_index=True)


@st.cache_data(show_spinner=False, max_entries=24)
def _cards(paths: tuple, stat: str, exclude: frozenset[str]) -> dict[str, pd.DataFrame]:
    df = _load(paths)
    last_two = df[df["season_year"] >= df["season_year"].max() - 1]
    return {"heat": insights.heating_up(last_two, stat, top=6, exclude=exclude),
            "steady": insights.consistency(last_two, stat, top=6, exclude=exclude),
            "matchup": insights.matchup_history(df, stat, top=6, exclude=exclude)}


def _d(ts) -> str:
    return f"{ts:%b} {ts.day}, {ts:%Y}"


def _range(a, b) -> str:
    return f"{a:%b} {a.day}, {a:%Y} – {b:%b} {b.day}, {b:%Y}" if a.year != b.year else f"{a:%b} {a.day} – {b:%b} {b.day}, {b:%Y}"


def player_card(key: str, rank: int, row: pd.Series, big: str, unit_label: str, pill: str, pill_kind: str,
                sub: str, meta: str, link: dict, team_line: str | None = None) -> None:
    team_id = row.get("team_id")
    card_ui.player_card(key, player_id=row["player_id"], name=row["player_name"], team=row["team"],
                      team_id=team_id if pd.notna(team_id) else None, badge=f"#{rank}", big=big,
                      unit_label=unit_label, pill=pill, pill_kind=pill_kind, sub=sub, meta=meta, link=link,
                      team_line=team_line)


def section(title: str, how: str, rows: pd.DataFrame, draw, empty: str) -> None:
    with st.container(border=True):
        st.subheader(title)
        st.caption(how)
        if rows.empty:
            st.info(empty)
            return
        with st.container(horizontal=True, gap="small"):
            for i, (_, row) in enumerate(rows.head(3).iterrows(), 1):
                draw(i, row)
        if len(rows) > 3:
            with st.expander(f"Show {len(rows) - 3} more"):
                with st.container(horizontal=True, gap="small"):
                    for i, (_, row) in enumerate(rows.iloc[3:].iterrows(), 4):
                        draw(i, row)


# ---------------------------------------------------------------- page

files = [(s, p) for s, t, p in nba.available_files() if t == "Regular Season"][-3:]
if not files:
    st.warning("No NBA data is stored yet. Run `python -m refresh.nba` to get started.")
    st.stop()

paths = tuple((s, str(p), p.stat().st_mtime) for s, p in files)
st.header("🧪 Today's Lab")
today = datetime.now(viewer_timezone())
c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
c1.markdown(f"**{today:%A, %B} {today.day}, {today:%Y}** · Starting points from recent NBA games. "
            "Pick one to open the full analysis.")
st.session_state.setdefault("today_stat", "Points")
label = c2.selectbox("Stat for these cards", list(STATS), key="today_stat")
stat, unit = STATS[label], UNIT[STATS[label]]

out_list = unavailable.load("nba", today.date())
with st.spinner("Crunching recent games..."):
    df = _load(paths)
    cards = _cards(paths, stat, frozenset(out_list["player_id"]))

meta = read_meta("nba")
st.caption(f"📅 Data through **{_d(df['game_date'].max())}** (latest game stored) · "
           f"🕒 Last refresh: {local_time(meta.get('last_success_utc'))} · "
           "Findings describe past games. They are not predictions.")

card_ui.apply_css()

# Who's left out, and why (so a missing star doesn't look like a bug)
current = df[df["season_year"] == df["season_year"].max()]
sat_out = insights.missed_last_game(current)
sat_out = sat_out[~sat_out["player_id"].isin(out_list["player_id"])]
with st.expander(f"Who's left out? ({len(out_list) + len(sat_out)} players)"):
    st.caption("Cards only include players who played in their team's most recent game, so anyone "
               "currently out (injury, rest or suspension) is skipped until they play again.")
    if len(out_list):
        st.markdown("**Listed as unavailable:** " + ", ".join(
            f"{r['player_name'] or r['player_id']}" + (f" (until {r['until']})" if r["until"] else "")
            + (f" · {r['note']}" if r["note"] else "") for _, r in out_list.iterrows()))
    if len(sat_out):
        st.markdown("**Missed their team's last game:** " + ", ".join(
            f"{r['player_name']} ({r['team']}, last played {_d(r['game_date'])})" for _, r in sat_out.iterrows()))
    if not len(out_list) and not len(sat_out):
        st.caption("Nobody right now.")


def _arrow(change: float) -> str:
    return f"{'▲' if change >= 0 else '▼'} {abs(change):.1f}"


def _link(row, window, opponent="All"):
    return links.build(sport="nba", player_id=row["player_id"], stat_col=stat, seasons=list(row["seasons"]),
                       season_type="Regular Season", window_label=window, opponent=opponent)


def heat_card(i, r):
    player_card(f"heat_{i}", i, r, f"{r['recent_avg']:.1f}", f"{unit} · last {r['recent_n']}",
                f"{_arrow(r['change'])} vs before", "up",
                f"Before: {r['baseline_avg']:.1f} · Min {r['recent_min']:.0f} vs {r['baseline_min']:.0f}",
                f"Last {r['recent_n']}: {_range(r['recent_first'], r['recent_last'])}<br>"
                f"Baseline: {r['baseline_n']} games, {_range(r['baseline_first'], r['baseline_last'])}",
                _link(r, "Last 5"))


def steady_card(i, r):
    player_card(f"steady_{i}", i, r, f"{r['avg']:.1f}", f"{unit} / game",
                f"± {r['std']:.1f} typical swing", "steady",
                f"Range {r['low']:g}–{r['high']:g} over {r['n']} games",
                f"Last {r['n']}: {_range(r['first'], r['last'])}", _link(r, "Last 10"))


def matchup_card(i, r):
    opp_logo = card_ui.logo_img(r.get("opp_team_id") if pd.notna(r.get("opp_team_id")) else None, cls="")
    team_line = f'<div class="pc-vs">{r["team"]} vs {opp_logo}<b>{r["opponent"]}</b></div>'
    player_card(f"match_{i}", i, r, f"{r['opp_avg']:.1f}", f"{unit} vs {r['opponent']}",
                f"{_arrow(r['change'])} vs overall", "up",
                f"Overall: {r['overall']:.1f} · {r['n']} games vs {r['opponent']}",
                f"vs {r['opponent']}: {_range(r['first'], r['last'])}<br>Overall: {r['overall_n']} games",
                _link(r, "All games", opponent=r["opponent"]), team_line=team_line)


section("🔥 Heating up",
        "Biggest increase: average of the last 5 games (all this season) vs the 30 games before them. "
        f"Requires 15+ baseline games and {insights.MIN_MINUTES}+ minutes a night. A minutes jump usually means "
        "a bigger role; without one, hot stretches often cool off.",
        cards["heat"], heat_card, "Not enough games yet this season. Check back after a few more games.")

section("🎯 Consistency corner",
        "Steadiest production over each player's last 10 games: smallest spread relative to their average. "
        f"Minimum {insights.MIN_AVG.get(stat, 0):g} {unit} per game. Early in a season the 10 games can include "
        "last season; dates are shown.",
        cards["steady"], steady_card, "No players meet the minimums for this stat.")

section("🧩 Matchup history",
        f"Largest gap between a player's average against one team and their overall average across the last "
        f"{len(files)} seasons. Needs 6+ games vs that team. With hundreds of player-team pairs, some big gaps "
        "happen by chance, so treat these as leads to check, not trends.",
        cards["matchup"], matchup_card, "No player has enough games against one team yet.")

st.caption("Data: stats.nba.com via nba_api. NFL and MLB cards are coming next.")
