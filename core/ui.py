"""Shared analysis UI used by every sport page.

Every widget key is prefixed with the sport (nba_, nfl_, mlb_hit_, mlb_pit_) so sports
never share state. Defaults are written to st.session_state before the widget is created
(and no `value=` is passed), which avoids Streamlit's "default + session state" warning
and lets app.py keep selections alive while another sport is open.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.config import (AVG_COLOR, LINE_COLOR, OVER_COLOR, PUSH_COLOR, SMALL_SAMPLE,
                         UNDER_COLOR, WINDOW_OPTIONS)
from core.metrics import OVER, PUSH, UNDER, classify, default_line, fmt, most_recent, summarize
from core.storage import read_meta

RESULT_COLORS = {OVER: OVER_COLOR, UNDER: UNDER_COLOR, PUSH: PUSH_COLOR}


@dataclass
class StatOption:
    group: str
    label: str
    col: str

    @property
    def display(self) -> str:
        return f"{self.group} · {self.label}" if self.group else self.label


@dataclass
class SportView:
    prefix: str
    sport: str                      # meta file name: nba / nfl / mlb
    stats: list[StatOption]
    season_types: list[str]
    participation_note: str
    season_label: Callable[[str], str] = lambda s: s
    extra_cols: list[tuple[str, str]] = field(default_factory=list)  # (column, header) for table + hover
    value_display: Callable[[pd.Series, str], pd.Series] | None = None  # e.g. outs -> "5.2 IP"


@dataclass
class Selection:
    player_id: str
    player_name: str
    stat: StatOption
    line: float
    window_label: str
    seasons: list[str]
    season_type: str
    pool: pd.DataFrame              # every player's games for the selected seasons/type
    player_games: pd.DataFrame      # all of the player's games in the selected seasons/type
    filtered: pd.DataFrame          # after opponent / home-away filters
    window: pd.DataFrame            # most recent N of `filtered`, with RESULT column


# ---------------------------------------------------------------- state helpers

def _ensure(key: str, options: list, default):
    """Keep a stored selection if it's still valid, otherwise fall back to default."""
    if st.session_state.get(key) not in options:
        st.session_state[key] = default


def _player_label_map(pool: pd.DataFrame) -> dict[str, str]:
    latest = pool.sort_values("game_date").groupby("player_id").tail(1)
    labels = dict(zip(latest["player_id"], latest["player_name"] + " · " + latest["team"].astype(str)))
    return dict(sorted(labels.items(), key=lambda kv: kv[1].lower()))


# ---------------------------------------------------------------- main entry

def render_analysis(view: SportView, order: list[str],
                    load: Callable[[tuple[str, ...], str], pd.DataFrame],
                    header: Callable[[Selection], None] | None = None,
                    extras: Callable[[Selection], None] | None = None) -> Selection | None:
    """`order` = stored seasons oldest→newest. `load(seasons, season_type)` reads only those."""
    p = view.prefix
    if not order:
        st.info("No stored seasons yet. See the README for the refresh command.")
        return None

    with st.container(border=True):
        c1, c2 = st.columns([1.6, 1.0])
        key = f"{p}_seasons"
        kept = [s for s in st.session_state.get(key, []) if s in order]
        st.session_state[key] = kept or order[-1:]
        seasons = c1.multiselect("🗓️ Seasons", order, key=key, format_func=view.season_label)
        _ensure(f"{p}_stype", view.season_types, view.season_types[0])
        season_type = c2.selectbox("🏆 Season type", view.season_types, key=f"{p}_stype")

        if not seasons:
            st.info("Pick at least one season.")
            return None
        with st.spinner("Loading stored games..."):
            pool = load(tuple(sorted(seasons)), season_type)
        if pool.empty:
            st.info(f"No stored {season_type.lower()} games for "
                    f"{', '.join(view.season_label(s) for s in seasons)}. Try another season or season type.")
            return None

        labels = _player_label_map(pool)
        first_stat = view.stats[0].col
        top = pool.groupby("player_id")[first_stat].sum().idxmax()
        _ensure(f"{p}_player", list(labels), top)

        c1, c2, c3 = st.columns([1.6, 1.3, 0.9])
        player_id = c1.selectbox("👤 Player (type to search)", list(labels), key=f"{p}_player",
                                 format_func=labels.get)
        stat_map = {s.display: s for s in view.stats}
        _ensure(f"{p}_stat", list(stat_map), view.stats[0].display)
        stat = stat_map[c2.selectbox("📊 Stat", list(stat_map), key=f"{p}_stat")]
        _ensure(f"{p}_window", list(WINDOW_OPTIONS), "Last 10")
        window_label = c3.selectbox("⏱️ Recent games", list(WINDOW_OPTIONS), key=f"{p}_window")

        player_games = pool[pool["player_id"] == player_id].sort_values(["game_date", "game_seq"])
        player_name = player_games["player_name"].iloc[-1]

        c1, c2, c3 = st.columns([1.3, 1.0, 1.0])
        opps = ["All"] + sorted(player_games["opponent"].dropna().astype(str).unique())
        _ensure(f"{p}_opp", opps, "All")
        opponent = c1.selectbox("🛡️ Opponent", opps, key=f"{p}_opp")
        venues = ["All", "Home", "Away"] + (["Neutral"] if player_games["venue"].eq("Neutral").any() else [])
        _ensure(f"{p}_venue", venues, "All")
        venue = c2.selectbox("🏠 Home/Away", venues, key=f"{p}_venue")

        line_key = f"{p}_line_{player_id}_{stat.col}"
        if line_key not in st.session_state:
            st.session_state[line_key] = default_line(player_games[stat.col])
        line = c3.number_input("🎯 Your line", step=0.5, format="%.1f", key=line_key,
                               help="Defaults to the last-10 average snapped to the .5 below it. "
                                    "Enter the line you're researching.")
        st.caption("Filters apply in this order: season → season type → opponent → home/away. "
                   "The recent-games window then takes the most recent games that remain.")

    filtered = player_games
    if opponent != "All":
        filtered = filtered[filtered["opponent"] == opponent]
    if venue != "All":
        filtered = filtered[filtered["venue"] == venue]
    missing = int(filtered[stat.col].isna().sum())
    window = most_recent(filtered.dropna(subset=[stat.col]), WINDOW_OPTIONS[window_label])
    window = window.assign(RESULT=classify(window[stat.col], line))

    sel = Selection(player_id, player_name, stat, float(line), window_label, seasons, season_type,
                    pool, player_games, filtered, window)

    if header:
        header(sel)
    else:
        player_header(sel)

    if window.empty:
        st.info("No games match these filters. Widen the opponent, home/away or season filters.")
        return sel

    summary_cards(sel, missing)
    with st.container(border=True):
        st.subheader("Game by game")
        game_chart(sel, view)
    with st.container(border=True):
        st.subheader("Game log")
        game_table(sel, view)
    if extras:
        extras(sel)
    st.caption(f"**Which games count:** {view.participation_note}")
    return sel


# ---------------------------------------------------------------- pieces

def player_header(sel: Selection) -> None:
    last = sel.player_games.iloc[-1]
    with st.container(border=True):
        url = last.get("headshot_url")
        if isinstance(url, str) and url:
            left, right = st.columns([0.18, 1.82], vertical_alignment="center")
            left.image(url, width=110)
        else:
            right = st.container()
        right.markdown(
            f'<div class="player-name">{sel.player_name}</div>'
            f'<div class="player-sub">{last["team"]} · {len(sel.player_games)} games in this view · '
            f'{sel.stat.label}</div>',
            unsafe_allow_html=True,
        )


def summary_cards(sel: Selection, missing: int = 0) -> None:
    s = summarize(sel.window[sel.stat.col], sel.line)
    with st.container(border=True):
        st.subheader(f"Historical results: {sel.stat.label} vs {sel.line:g}")
        cols = st.columns(3)
        cols[0].metric("Qualifying games", s.games)
        cols[1].metric("Average", fmt(s.mean))
        cols[2].metric("Median", fmt(s.median))
        cols = st.columns(3)
        cols[0].metric("Std. deviation", fmt(s.std), help="Sample standard deviation of the selected window. Needs 2+ games.")
        cols[1].metric("Over / Under / Push", f"{s.overs} / {s.unders} / {s.pushes}")
        rate = "Unavailable" if s.over_rate is None else f"{s.over_rate * 100:.0f}%"
        cols[2].metric("Historical over rate", rate,
                       help="Overs ÷ (overs + unders). Pushes are excluded.")
        detail = (f"{s.overs} overs out of {s.decided} decided games" if s.decided
                  else "every game was a push, so no rate")
        if s.pushes:
            detail += f"; {s.pushes} push{'es' if s.pushes != 1 else ''} not counted"
        st.caption(f"Over rate = {detail}. These are past results in the selected window, "
                   "not a probability for the next game.")
        if s.games < SMALL_SAMPLE:
            st.caption(f"⚠️ Small sample: {s.games} game{'s' if s.games != 1 else ''}. "
                       "A few games can swing these numbers a lot.")
        if missing:
            st.caption(f"{missing} game(s) had no recorded value for this stat and are excluded.")


def _x_labels(df: pd.DataFrame, multi_season: bool) -> list[str]:
    fmt_ = "%b %d '%y" if multi_season else "%b %d"
    prefix = np.where(df["venue"].eq("Away"), "@ ", "vs ")
    suffix = np.where(df["venue"].eq("Neutral"), " (N)", "")
    labels = (pd.to_datetime(df["game_date"]).dt.strftime(fmt_) + "<br>" + prefix
              + df["opponent"].astype(str) + suffix).tolist()
    seen: set[str] = set()
    out = []
    for lbl, seq in zip(labels, df["game_seq"]):
        if seq > 1:
            lbl = f"{lbl} (G{seq})"   # doubleheader game 2
        while lbl in seen:            # category axes merge identical labels
            lbl += " "
        seen.add(lbl)
        out.append(lbl)
    return out


def game_chart(sel: Selection, view: SportView) -> None:
    d = sel.window
    stat = sel.stat
    x = _x_labels(d, len(sel.seasons) > 1)
    shown = view.value_display(d[stat.col], stat.col) if view.value_display else d[stat.col].map(lambda v: f"{v:g}")
    hover = pd.DataFrame({
        "date": pd.to_datetime(d["game_date"]).dt.strftime("%a %b %d, %Y"),
        "match": d["team"].astype(str) + np.where(d["venue"].eq("Away"), " @ ", " vs ") + d["opponent"].astype(str),
        "venue": d["venue"].fillna("Unknown"),
        "val": shown,
        "res": d["RESULT"],
    })
    extra_tpl = ""
    for i, (col, label) in enumerate(view.extra_cols):
        hover[f"x{i}"] = d[col].astype(object).where(d[col].notna(), "—").astype(str) if col in d else "—"
        extra_tpl += f"<br>{label}: %{{customdata[{5 + i}]}}"
    roll = d[stat.col].rolling(5, min_periods=1).mean()

    fig = go.Figure()
    fig.add_bar(
        x=x, y=d[stat.col], marker_color=d["RESULT"].map(RESULT_COLORS).fillna(LINE_COLOR),
        customdata=hover.to_numpy(),
        text=shown if len(d) <= 15 else None, textposition="outside", cliponaxis=False,
        hovertemplate="%{customdata[0]}<br>%{customdata[1]} (%{customdata[2]})<br>"
                      f"{stat.label}: %{{customdata[3]}} → <b>%{{customdata[4]}}</b>{extra_tpl}<extra></extra>",
        name=stat.label,
    )
    fig.add_scatter(x=x, y=roll, mode="lines+markers", line=dict(color=AVG_COLOR, width=3),
                    marker=dict(size=6, color=AVG_COLOR), name="5-game avg",
                    hovertemplate="5-game avg: %{y:.1f}<extra></extra>")
    fig.add_hline(y=sel.line, line_dash="dash", line_color=LINE_COLOR, line_width=2,
                  annotation_text=f"Line {sel.line:g}", annotation_position="top right")
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), showlegend=False, bargap=0.25,
                      xaxis=dict(type="category", automargin=True),
                      yaxis=dict(title=stat.label, rangemode="tozero"))
    counts = d["RESULT"].value_counts()
    st.caption(f"🟩 Over ({counts.get(OVER, 0)}) · 🟥 Under ({counts.get(UNDER, 0)}) · "
               f"🟦 Push ({counts.get(PUSH, 0)}). Orange = 5-game rolling average; dashed = your line. "
               "Oldest on the left.")
    show_chart(fig)


def show_chart(fig: go.Figure) -> None:
    """Plotly chart that doesn't hijack touch scrolling on phones (from the original app)."""
    fig.update_layout(dragmode=False)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "scrollZoom": False})


def game_table(sel: Selection, view: SportView) -> None:
    d = sel.window.sort_values(["game_date", "game_seq"], ascending=False)
    stat = sel.stat
    table = pd.DataFrame({
        "Date": pd.to_datetime(d["game_date"]).dt.date,
        "Season": d["season"].map(view.season_label),
        "Team": d["team"], "Opp": d["opponent"], "Home/Away": d["venue"],
    })
    for col, label in view.extra_cols:
        if col in d:
            table[label] = d[col]
    table[stat.label] = view.value_display(d[stat.col], stat.col) if view.value_display else d[stat.col]
    table["Result"] = d["RESULT"]
    st.dataframe(table, width="stretch", hide_index=True)

    export = table.copy()
    export.insert(0, "Player", sel.player_name)
    export["Line"] = sel.line
    export["Season type"] = sel.season_type
    if view.value_display:
        export[f"{stat.label} (raw)"] = d[stat.col].to_numpy()
    fname = f"{view.prefix}_{sel.player_name}_{stat.col}_{sel.window_label}".replace(" ", "_").lower()
    st.download_button("⬇️ Download these games (CSV)", export.to_csv(index=False).encode(),
                       file_name=f"{fname}.csv", mime="text/csv", key=f"dl_{view.prefix}")


def data_status(sport: str, df: pd.DataFrame | None, source: str) -> None:
    """Last successful refresh and data coverage, shown separately."""
    meta = read_meta(sport)
    last = meta.get("last_success_utc")
    if last:
        when = datetime.fromisoformat(last).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    else:
        when = "unknown (no refresh recorded yet)"
    cov = "no data loaded"
    if df is not None and not df.empty:
        d = pd.to_datetime(df["game_date"])
        cov = f"{d.min():%b %d, %Y} → {d.max():%b %d, %Y} ({len(df):,} player-games loaded)"
    st.caption(f"🕒 Last successful refresh: {when}  \n📅 Coverage in this view: {cov}  \nSource: {source}")
    if meta.get("last_error"):
        st.caption(f"⚠️ Most recent refresh attempt failed ({meta.get('last_attempt_utc')}); "
                   "showing the last good data.")
