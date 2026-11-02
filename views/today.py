"""Today's Lab: starting points built from the stored NBA data. Every card links into the
NBA page with the right player, stat and filters already selected."""
from datetime import datetime

import pandas as pd
import streamlit as st

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


HEADSHOT = "https://cdn.nba.com/headshots/nba/latest/260x190/{}.png"
LOGO = "https://cdn.nba.com/logos/nba/{}/global/L/logo.svg"

CARD_CSS = """
<style>
[class*="st-key-pc_"] { padding: 0 !important; overflow: hidden; }
[class*="st-key-pc_"] [data-testid="stPageLink"] { padding: 0 12px 10px; }
.pc-top { position: relative; height: 112px; display: flex; align-items: flex-end; justify-content: center;
  background: linear-gradient(160deg, rgba(107,138,253,0.22), rgba(47,191,113,0.12)); }
.pc-shot { height: 104px; width: auto; display: block; }
.pc-logo { position: absolute; top: 8px; right: 8px; width: 30px; height: 30px; }
.pc-rank { position: absolute; top: 8px; left: 10px; font-weight: 800; font-size: 0.85rem; opacity: 0.75; }
.pc-body { padding: 10px 12px 4px; }
.pc-name { font-weight: 800; font-size: 1.02rem; line-height: 1.2; }
.pc-team { font-size: 0.8rem; opacity: 0.7; margin-bottom: 6px; }
.pc-body .pc-big { font-size: 2.1rem !important; font-weight: 800; line-height: 1.05 !important;
  letter-spacing: -0.02em; margin: 2px 0; }
.pc-body .pc-big span { font-size: 0.85rem !important; font-weight: 600; opacity: 0.7; margin-left: 4px;
  letter-spacing: 0; }
.pc-body .pc-name { font-size: 1.05rem !important; }
.pc-pill { display: inline-block; margin: 6px 0 4px; padding: 2px 9px; border-radius: 999px;
  font-size: 0.8rem; font-weight: 700; }
.pc-pill.up { color: #1f9d5c; background: rgba(47,191,113,0.15); }
.pc-pill.steady { color: #4f6fe0; background: rgba(107,138,253,0.15); }
.pc-sub { font-size: 0.83rem; opacity: 0.85; }
.pc-meta { font-size: 0.72rem; opacity: 0.6; margin-top: 6px; line-height: 1.35; }
.pc-vs { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; opacity: 0.8; margin-bottom: 6px; }
.pc-vs img { width: 20px; height: 20px; }
@media (max-width: 640px) {   /* phones: one full-width card per row */
  div:has(> [class*="st-key-pc_"]), [class*="st-key-pc_"] {
    width: 100% !important; max-width: 100% !important; flex: 1 1 100% !important; }
  .pc-top { height: 128px; }
  .pc-shot { height: 120px; }
}
</style>
"""


def player_card(key: str, rank: int, row: pd.Series, big: str, unit_label: str, pill: str, pill_kind: str,
                sub: str, meta: str, link: dict, team_line: str | None = None) -> None:
    """One player card: headshot, team logo, headline number, change pill, sample, link."""
    team_id = row.get("team_id")
    logo = f'<img class="pc-logo" src="{LOGO.format(int(team_id))}" alt="">' if pd.notna(team_id) else ""
    team_line = team_line or f'<div class="pc-team">{row["team"]}</div>'
    with st.container(border=True, width=232, key=f"pc_{key}"):
        st.markdown(
            f'<div class="pc-top"><span class="pc-rank">#{rank}</span>'
            f'<img class="pc-shot" src="{HEADSHOT.format(row["player_id"])}" alt="">{logo}</div>'
            f'<div class="pc-body"><div class="pc-name">{row["player_name"]}</div>{team_line}'
            f'<div class="pc-big">{big}<span>{unit_label}</span></div>'
            f'<div class="pc-pill {pill_kind}">{pill}</div>'
            f'<div class="pc-sub">{sub}</div><div class="pc-meta">{meta}</div></div>',
            unsafe_allow_html=True)
        st.page_link("views/nba.py", label="Open analysis →", query_params=link)


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

st.markdown(CARD_CSS, unsafe_allow_html=True)

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
    opp_logo = (f'<img src="{LOGO.format(int(r["opp_team_id"]))}" alt="">'
                if pd.notna(r.get("opp_team_id")) else "")
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
