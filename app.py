# app.py
# NBA Props Lab — Full Streamlit app using REAL nba_api leaguegamelog data
# Includes:
# - Real multi-season leaguegamelog pull (cached)
# - Defaults season selection to 2025-26
# - Player headshot (from PLAYER_ID)
# - Home/Away + Opponent filters derived from MATCHUP
# - Guaranteed red/green Over/Under bars (per-bar colors)
# - Trend summary sentence for the selected stat
# - Tabs + bordered containers + clean captions
#
# Requirements (install in your venv):
#   pip install streamlit nba_api plotly pandas numpy
#
# Run:
#   streamlit run app.py

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz


from nba_api.stats.endpoints import leaguegamelog

# -------------------------
# EST helper functions (STEP 2 GOES HERE)
# -------------------------
def est_now():
    return datetime.now(pytz.timezone("US/Eastern"))

def est_today_key():
    return est_now().strftime("%Y-%m-%d")

# -------------------------
# Page config
# -------------------------
st.set_page_config(
    page_title="NBA Props Lab",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------------
# Design system CSS
# -------------------------
st.markdown(
    """
<style>
.block-container { max-width: 1200px; padding-top: 2.2rem; padding-bottom: 2.2rem; }
h1 { font-size: 2.35rem !important; letter-spacing: -0.02em; }
h2 { font-size: 1.55rem !important; letter-spacing: -0.01em; margin-top: 1.2rem !important; }
h3 { font-size: 1.18rem !important; margin-top: 1.0rem !important; }
p, li, div { font-size: 1.05rem !important; line-height: 1.65 !important; }

section[data-testid="stSidebar"] { border-right: 1px solid rgba(255,255,255,0.07); }
section[data-testid="stSidebar"] * { font-size: 1.02rem !important; }

.card {
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 18px;
  padding: 18px 18px;
  background: rgba(255,255,255,0.03);
  box-shadow: 0 10px 30px rgba(0,0,0,0.25);
  margin: 12px 0;
}
.card-title { font-weight: 700; font-size: 1.05rem; opacity: 0.95; margin: 0 0 6px 0; }
.muted { opacity: 0.85; }

div[data-baseweb="select"] > div { min-height: 48px !important; border-radius: 14px !important; }
input, textarea { min-height: 48px !important; border-radius: 14px !important; }
button[kind="primary"] { border-radius: 14px !important; }

[data-testid="stMetricValue"] { font-size: 2.0rem !important; }
[data-testid="stMetricLabel"] { font-size: 1.0rem !important; opacity: 0.85; }

.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { padding: 10px 14px; border-radius: 14px; }

header[data-testid="stHeader"] { height: 0px !important; }
</style>
    """,
    unsafe_allow_html=True,
)

# -------------------------
# Constants and helpers
# -------------------------
ALL_SEASONS = [
    "2019-20",
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
    "2025-26",
]
DEFAULT_SEASON = "2025-26"

STAT_MAP = {
    "PTS": "PTS",
    "REB": "REB",
    "AST": "AST",
    "3PM": "FG3M",
    "PRA": "PRA",
    "PR": "PR",
    "PA": "PA",
    "RA": "RA",
    "BLK+STL": "BLK_STL",
}
WINDOW_MAP = {"Last 5": 5, "Last 10": 10, "Last 15": 15, "Last 25": 25, "Season": None}

NUM_COLS = [
    "PTS", "REB", "AST", "FGA", "FGM",
    "FG3A", "FG3M",
    "FTA", "FTM",
    "DREB", "OREB",
    "STL", "BLK", "TOV", "PF",
    "MIN",
]

def apply_window(df: pd.DataFrame, window_label: str) -> pd.DataFrame:
    n = WINDOW_MAP[window_label]
    if n is None:
        return df.copy()
    return df.tail(n).copy()

def half_point_round(x: float) -> float:
    return round(x * 2) / 2

def trend_sentence(player_name: str, stat_key: str, s: pd.Series) -> str:
    if len(s) < 6:
        return f"{player_name} does not have enough games in this timeframe to confidently describe a trend for {stat_key}."

    first = s.iloc[: len(s)//2].mean()
    second = s.iloc[len(s)//2 :].mean()
    diff = second - first

    x = np.arange(len(s), dtype=float)
    y = s.astype(float).to_numpy()
    slope = np.polyfit(x, y, 1)[0]

    if diff > 0.25:
        direction = "upward"
    elif diff < -0.25:
        direction = "downward"
    else:
        direction = "flat"

    if direction == "flat":
        return f"{player_name}'s {stat_key} trend looks fairly steady in this timeframe (no strong upward or downward movement)."

    strength = "slightly" if abs(diff) < 1.0 else "clearly" if abs(diff) >= 2.0 else "moderately"
    slope_hint = "with consistent momentum" if abs(slope) > 0.10 else "but with game-to-game swings"
    return (
        f"{player_name} is trending **{direction}** for **{stat_key}** {strength} "
        f"({first:.1f} → {second:.1f} avg from early to late games), {slope_hint}."
    )

@st.cache_data(show_spinner=False)
def player_headshot_url(player_id: int) -> str:
    return f"https://cdn.nba.com/headshots/nba/latest/260x190/{int(player_id)}.png"

# -------------------------
# Load real data (cached)
# -------------------------
@st.cache_data(show_spinner=False)
def load_league_logs(seasons: list[str], refresh_key: str) -> pd.DataFrame:
    all_logs = []
    for s in seasons:
        logs = leaguegamelog.LeagueGameLog(
            player_or_team_abbreviation="P",
            season=s,
            season_type_all_star="Regular Season",
        )
        df_season = logs.get_data_frames()[0]
        df_season["SEASON"] = s
        all_logs.append(df_season)

    df_logs = pd.concat(all_logs, ignore_index=True)
    df_logs["GAME_DATE"] = pd.to_datetime(df_logs["GAME_DATE"], errors="coerce")

    for col in NUM_COLS:
        if col in df_logs.columns:
            df_logs[col] = pd.to_numeric(df_logs[col], errors="coerce")

    # Composite stats
    df_logs["PRA"] = df_logs["PTS"] + df_logs["REB"] + df_logs["AST"]
    df_logs["PR"]  = df_logs["PTS"] + df_logs["REB"]
    df_logs["PA"]  = df_logs["PTS"] + df_logs["AST"]
    df_logs["RA"]  = df_logs["REB"] + df_logs["AST"]
    df_logs["THREES_MADE"] = df_logs["FG3M"]
    df_logs["BLK_STL"] = df_logs["BLK"] + df_logs["STL"]

    # Context from MATCHUP
    df_logs["IS_HOME"] = df_logs["MATCHUP"].astype(str).str.contains("vs")
    df_logs["OPPONENT"] = df_logs["MATCHUP"].astype(str).str[-3:]

    df_logs = df_logs.dropna(subset=["GAME_DATE", "PLAYER_NAME", "MATCHUP"])
    return df_logs

# -------------------------
# Sidebar
# -------------------------
with st.sidebar:
    from datetime import timedelta

    # -------------------------
    # Data refresh (SAFE)
    # -------------------------
    st.markdown("### 🔄 Data Refresh")

    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = None

    can_refresh = (
        st.session_state.last_refresh is None
        or est_now() - st.session_state.last_refresh > timedelta(minutes=15)
    )

    if st.button(
        "Refresh data now",
        disabled=not can_refresh,
        key="refresh_data_now_sidebar"
    ):
        st.session_state.last_refresh = est_now()
        st.cache_data.clear()
        st.rerun()

    if not can_refresh:
        remaining = 15 - int(
            (est_now() - st.session_state.last_refresh).total_seconds() // 60
        )
        st.caption(f"Refresh available again in ~{remaining} min.")

    # -------------------------
    # Settings
    # -------------------------
    st.markdown("### ⚙️ Settings")
    min_games = st.number_input(
        "Minimum games required",
        min_value=1,
        max_value=82,
        value=5,
        step=1
    )
    show_raw_table = st.toggle("Show raw table", value=False)

    # -------------------------
    # Season selector
    # -------------------------
    st.markdown("### 🗓️ Season")
    seasons = st.multiselect(
        "Include seasons",
        options=ALL_SEASONS,
        default=[DEFAULT_SEASON],
        help="Defaults to 2025–26 for now. Older seasons stay available for future ML."
    )


# -------------------------
# Load data
# -------------------------
with st.spinner("Loading NBA game logs..."):
    refresh_key = est_today_key()
    df_logs = load_league_logs(seasons, refresh_key)
    # Store last updated time (EST) when data actually loads
if "last_data_update" not in st.session_state:
    st.session_state.last_data_update = est_now()


# -------------------------
# Hero header
# -------------------------
st.title("🏀 NBA Props Lab")
st.write("Research player props with trends, distributions, and context. Built for decision-making, not picks.")
st.caption("Default view shows the 2025–26 season for now. Historical seasons will be used later for modeling.")

st.markdown(
    """
<div class="card">
  <div class="card-title">✨ Quick Start</div>
  <div class="muted">1) Choose player and stat  ·  2) Filter home/away or opponent  ·  3) Set a line to see red/green Over/Under  ·  4) Read the trend summary</div>
</div>
""",
    unsafe_allow_html=True,
)

# -------------------------
# Filters
# -------------------------
with st.container(border=True):
    r1c1, r1c2, r1c3 = st.columns([1.7, 1.0, 1.0])
    with r1c1:
        player = st.selectbox("👤 Player", sorted(df_logs["PLAYER_NAME"].unique().tolist()))
    with r1c2:
        stat = st.selectbox("📊 Stat", list(STAT_MAP.keys()))
    with r1c3:
        window = st.selectbox("🗓️ Timeframe", list(WINDOW_MAP.keys()))

    r2c1, r2c2 = st.columns([1.0, 1.2])
    with r2c1:
        home_away = st.selectbox("🏠 Home/Away", ["All", "Home", "Away"])
    with r2c2:
        opponent = st.selectbox("🛡️ Opponent", ["All"] + sorted(df_logs["OPPONENT"].unique().tolist()))

# Apply filters
player_df = df_logs[df_logs["PLAYER_NAME"] == player].sort_values("GAME_DATE").copy()

if home_away == "Home":
    player_df = player_df[player_df["IS_HOME"]]
elif home_away == "Away":
    player_df = player_df[~player_df["IS_HOME"]]

if opponent != "All":
    player_df = player_df[player_df["OPPONENT"] == opponent]

player_df = apply_window(player_df, window)

if len(player_df) < min_games:
    st.warning(f"Not enough games after filters. Need at least {min_games}, found {len(player_df)}.")
    st.stop()

# Selected stat values
stat_col = STAT_MAP[stat]
player_df["SELECTED_STAT"] = pd.to_numeric(player_df[stat_col], errors="coerce")
player_df = player_df.dropna(subset=["SELECTED_STAT"])

if len(player_df) < min_games:
    st.warning(f"Not enough valid stat rows after cleaning. Need at least {min_games}, found {len(player_df)}.")
    st.stop()

# Line input after filters, default to half-point rounded mean
suggested_line = half_point_round(float(player_df["SELECTED_STAT"].mean()))
with st.container(border=True):
    c1, c2 = st.columns([1.0, 2.0])
    with c1:
        line = st.number_input(
            "🎯 Line (Over/Under colors)",
            min_value=0.0,
            max_value=200.0,
            value=float(suggested_line),
            step=0.5,
        )
    with c2:
        st.caption("Auto-filled from the average in this view. Change it to match the sportsbook line you are considering.")

player_df["OU"] = np.where(player_df["SELECTED_STAT"] >= line, "Over", "Under")

# -------------------------
# Player picture + header card
# -------------------------
player_id = int(player_df["PLAYER_ID"].iloc[0])
headshot = player_headshot_url(player_id)

left, right = st.columns([0.35, 1.65], vertical_alignment="center")
with left:
    st.image(headshot, width=120)

with right:
    venue_text = "All venues" if home_away == "All" else f"{home_away} only"
    opp_text = "All opponents" if opponent == "All" else f"vs {opponent}"
    st.markdown(
        f"""
<div class="card">
  <div class="card-title">👤 {player} — {stat} ({window})</div>
  <div class="muted">{venue_text} · {opp_text} · Seasons: {", ".join(seasons)}</div>
</div>
""",
        unsafe_allow_html=True,
    )

# -------------------------
# Summary metrics
# -------------------------
games = len(player_df)
avg = player_df["SELECTED_STAT"].mean()
med = player_df["SELECTED_STAT"].median()
last = player_df["SELECTED_STAT"].iloc[-1]
hit_rate = (player_df["SELECTED_STAT"] >= line).mean()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Games", f"{games}")
m2.metric("Average", f"{avg:.1f}")
m3.metric("Median", f"{med:.1f}")
m4.metric("Last Game", f"{last:.0f}")

st.markdown(
    f"""
<div class="card">
  <div class="card-title">✅ Hit Rate vs {line:.1f}</div>
  <div class="muted">{player} hit <b>{stat}</b> at or above <b>{line:.1f}</b> in <b>{hit_rate*100:.1f}%</b> of games in this view.</div>
</div>
""",
    unsafe_allow_html=True,
)

# -------------------------
# Tabs
# -------------------------
tab_overview, tab_trends, tab_matchup = st.tabs(["📌 Overview", "📈 Trends", "🧩 Matchup"])

# ---------- Overview ----------
with tab_overview:
    with st.container(border=True):
        st.subheader("Over / Under by Game")
        st.caption("Green = went over the line. Red = went under. The dashed line is your prop line.")

        chart_df = player_df.copy()
        chart_df["DATE_LABEL"] = chart_df["GAME_DATE"].dt.strftime("%b %d")
        chart_df["VENUE"] = np.where(chart_df["IS_HOME"], "Home", "Away")

        colors = np.where(chart_df["OU"].to_numpy() == "Over", "green", "red")

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=chart_df["DATE_LABEL"],
                y=chart_df["SELECTED_STAT"],
                marker_color=colors,
                customdata=np.stack([chart_df["MATCHUP"], chart_df["MIN"], chart_df["VENUE"]], axis=1),
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    f"{stat}: %{{y}}<br>"
                    "Matchup: %{customdata[0]}<br>"
                    "MIN: %{customdata[1]}<br>"
                    "Venue: %{customdata[2]}<extra></extra>"
                ),
                name=stat,
            )
        )
        fig.add_hline(y=line, line_dash="dash", annotation_text=f"Line: {line:.1f}", annotation_position="top left")
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with st.container(border=True):
        st.subheader("Distribution")
        st.caption("Shows volatility and where outcomes cluster. Useful for understanding risk.")
        hist = go.Figure()
        hist.add_trace(go.Histogram(x=player_df["SELECTED_STAT"], nbinsx=12))
        hist.add_vline(x=line, line_dash="dash", annotation_text=f"Line: {line:.1f}", annotation_position="top")
        hist.update_layout(margin=dict(l=10, r=10, t=40, b=10), xaxis_title=stat, yaxis_title="Games")
        st.plotly_chart(hist, use_container_width=True)

    with st.container(border=True):
        st.subheader("Recent Game Log")
        st.caption("Games included after your filters.")
        view = player_df[["GAME_DATE", "MATCHUP", "OPPONENT", "IS_HOME", "MIN", "SELECTED_STAT", "OU"]].copy()
        view["HOME_AWAY"] = np.where(view["IS_HOME"], "Home", "Away")
        view = view.drop(columns=["IS_HOME"]).rename(columns={"GAME_DATE": "DATE", "SELECTED_STAT": stat})
        view = view.sort_values("DATE", ascending=False)
        st.dataframe(view, use_container_width=True, hide_index=True)

# ---------- Trends ----------
with tab_trends:
    with st.container(border=True):
        st.subheader("Trend Summary")
        st.caption("Plain-English interpretation of what the trend is showing for the selected stat.")
        st.markdown(trend_sentence(player, stat, player_df["SELECTED_STAT"]))

    with st.container(border=True):
        st.subheader("Trend Line")
        st.caption("Line chart over the selected games. Look for stability vs spikes.")
        line_fig = go.Figure()
        line_fig.add_trace(go.Scatter(x=player_df["GAME_DATE"], y=player_df["SELECTED_STAT"], mode="lines+markers", name=stat))
        line_fig.add_hline(y=line, line_dash="dash", annotation_text=f"Line: {line:.1f}", annotation_position="top left")
        line_fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), xaxis_title="Date", yaxis_title=stat)
        st.plotly_chart(line_fig, use_container_width=True)

    with st.container(border=True):
        st.subheader("Rolling Average (5-game)")
        st.caption("Smoothed trend to reduce noise and show direction more clearly.")
        roll = player_df[["GAME_DATE", "SELECTED_STAT"]].copy()
        roll["ROLL5"] = roll["SELECTED_STAT"].rolling(5, min_periods=1).mean()

        roll_fig = go.Figure()
        roll_fig.add_trace(go.Scatter(x=roll["GAME_DATE"], y=roll["SELECTED_STAT"], mode="lines+markers", name=stat))
        roll_fig.add_trace(go.Scatter(x=roll["GAME_DATE"], y=roll["ROLL5"], mode="lines", name="Rolling Avg (5)"))
        roll_fig.add_hline(y=line, line_dash="dash", annotation_text=f"Line: {line:.1f}", annotation_position="top left")
        roll_fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), xaxis_title="Date", yaxis_title=stat)
        st.plotly_chart(roll_fig, use_container_width=True)

# ---------- Matchup ----------
with tab_matchup:
    with st.container(border=True):
        st.subheader("Opponent Split (in this view)")
        st.caption("How the selected stat has performed by opponent in the filtered games.")
        opp_summary = (
            player_df.groupby("OPPONENT")["SELECTED_STAT"]
            .agg(games="count", avg="mean", median="median")
            .sort_values(["games", "avg"], ascending=False)
        )
        st.dataframe(opp_summary, use_container_width=True)

    with st.container(border=True):
        st.subheader("Home vs Away Summary (in this view)")
        st.caption("Quick comparison between home and away games after filters.")
        ha = (
            player_df.assign(HomeAway=np.where(player_df["IS_HOME"], "Home", "Away"))
            .groupby("HomeAway")["SELECTED_STAT"]
            .agg(games="count", avg="mean", median="median")
            .sort_values("games", ascending=False)
        )
        st.dataframe(ha, use_container_width=True)

# Raw table
if show_raw_table:
    with st.container(border=True):
        st.subheader("Raw Data (Debug)")
        st.caption("Use this to confirm columns and troubleshoot.")
        st.dataframe(df_logs.head(200), use_container_width=True, hide_index=True)

st.markdown("---")

if "last_data_update" in st.session_state:
    st.caption(
        f"🕒 Last updated: "
        f"{st.session_state.last_data_update.strftime('%Y-%m-%d %I:%M %p')} ET"
    )

