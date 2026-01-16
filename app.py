# app.py
# NBA Props Lab — Full Streamlit app using REAL nba_api leaguegamelog data
# AUTO-REFRESHES AT MIDNIGHT EST DAILY (date-based cache key)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from nba_api.stats.endpoints import leaguegamelog
from datetime import datetime
import pytz

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
# EST-based cache key (midnight refresh)
# -------------------------
def est_today_key():
    est = pytz.timezone("US/Eastern")
    return datetime.now(est).strftime("%Y-%m-%d")

# -------------------------
# Constants
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

def apply_window(df, label):
    n = WINDOW_MAP[label]
    return df if n is None else df.tail(n)

def half_point_round(x):
    return round(x * 2) / 2

def trend_sentence(player, stat, s):
    if len(s) < 6:
        return f"{player} does not have enough games to describe a trend for {stat}."
    a, b = s.iloc[:len(s)//2].mean(), s.iloc[len(s)//2:].mean()
    slope = np.polyfit(range(len(s)), s.values, 1)[0]
    if abs(b - a) < 0.25:
        return f"{player}'s {stat} trend is relatively stable."
    direction = "upward" if b > a else "downward"
    return f"{player} is trending **{direction}** for **{stat}** ({a:.1f} → {b:.1f}), with {'strong' if abs(slope)>0.1 else 'moderate'} momentum."

@st.cache_data(show_spinner=False)
def player_headshot_url(pid):
    return f"https://cdn.nba.com/headshots/nba/latest/260x190/{int(pid)}.png"

# -------------------------
# Load NBA data (cached by EST date)
# -------------------------
@st.cache_data(show_spinner=False)
def load_league_logs(seasons, refresh_key):
    logs_all = []
    for s in seasons:
        lg = leaguegamelog.LeagueGameLog(
            player_or_team_abbreviation="P",
            season=s,
            season_type_all_star="Regular Season"
        )
        df = lg.get_data_frames()[0]
        df["SEASON"] = s
        logs_all.append(df)

    df_logs = pd.concat(logs_all, ignore_index=True)
    df_logs["GAME_DATE"] = pd.to_datetime(df_logs["GAME_DATE"], errors="coerce")

    for c in NUM_COLS:
        if c in df_logs.columns:
            df_logs[c] = pd.to_numeric(df_logs[c], errors="coerce")

    df_logs["PRA"] = df_logs["PTS"] + df_logs["REB"] + df_logs["AST"]
    df_logs["PR"] = df_logs["PTS"] + df_logs["REB"]
    df_logs["PA"] = df_logs["PTS"] + df_logs["AST"]
    df_logs["RA"] = df_logs["REB"] + df_logs["AST"]
    df_logs["BLK_STL"] = df_logs["BLK"] + df_logs["STL"]

    df_logs["IS_HOME"] = df_logs["MATCHUP"].str.contains("vs")
    df_logs["OPPONENT"] = df_logs["MATCHUP"].str[-3:]

    return df_logs.dropna(subset=["GAME_DATE", "PLAYER_NAME"])

# -------------------------
# Sidebar
# -------------------------
with st.sidebar:
    min_games = st.number_input("Minimum games", 1, 82, 5)
    seasons = st.multiselect("Season", ALL_SEASONS, default=[DEFAULT_SEASON])

# -------------------------
# Load data
# -------------------------
refresh_key = est_today_key()
df_logs = load_league_logs(seasons, refresh_key)

# -------------------------
# UI / Filters
# -------------------------
st.title("🏀 NBA Props Lab")
st.caption(f"Data refreshes daily at midnight EST · Current key: {refresh_key}")

player = st.selectbox("Player", sorted(df_logs["PLAYER_NAME"].unique()))
stat = st.selectbox("Stat", list(STAT_MAP.keys()))
window = st.selectbox("Timeframe", list(WINDOW_MAP.keys()))
home_away = st.selectbox("Home/Away", ["All", "Home", "Away"])
opponent = st.selectbox("Opponent", ["All"] + sorted(df_logs["OPPONENT"].unique()))

df = df_logs[df_logs["PLAYER_NAME"] == player].sort_values("GAME_DATE")

if home_away == "Home":
    df = df[df["IS_HOME"]]
elif home_away == "Away":
    df = df[~df["IS_HOME"]]

if opponent != "All":
    df = df[df["OPPONENT"] == opponent]

df = apply_window(df, window)
df["SELECTED_STAT"] = df[STAT_MAP[stat]]
line = half_point_round(df["SELECTED_STAT"].mean())
df["OU"] = np.where(df["SELECTED_STAT"] >= line, "Over", "Under")

# -------------------------
# Header w/ image
# -------------------------
pid = int(df["PLAYER_ID"].iloc[0])
st.image(player_headshot_url(pid), width=120)
st.subheader(f"{player} — {stat}")

# -------------------------
# Chart (red/green guaranteed)
# -------------------------
colors = np.where(df["OU"] == "Over", "green", "red")

fig = go.Figure()
fig.add_bar(
    x=df["GAME_DATE"].dt.strftime("%b %d"),
    y=df["SELECTED_STAT"],
    marker_color=colors,
    hovertemplate=f"{stat}: %{{y}}<extra></extra>",
)
fig.add_hline(y=line, line_dash="dash")
st.plotly_chart(fig, use_container_width=True)

st.markdown(trend_sentence(player, stat, df["SELECTED_STAT"]))
