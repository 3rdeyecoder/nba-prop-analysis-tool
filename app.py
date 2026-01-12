import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st
import streamlit.components.v1 as components

from nba_api.stats.endpoints import leaguegamelog, commonplayerinfo
from nba_api.stats.static import players

# ============================
# GOOGLE ANALYTICS (GA4)
# ============================
st.markdown(
    """
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-P3ML6DEY01"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-P3ML6DEY01');
    </script>
    """,
    unsafe_allow_html=True,
)

# ============================
# PAGE CONFIG
# ============================
st.set_page_config(
    page_title="NBA Betting Tool",
    layout="centered",
)

# ============================
# GLOBAL STYLES
# ============================
st.markdown(
    """
    <style>
      :root{
        --bg1:#0b1020;
        --bg2:#101a33;
        --border:#2a3a66;
        --text:#e8eeff;
        --muted:#a9b7e6;
        --good:#27e98a;
        --bad:#ff4d6d;
      }

      .stApp {
        background:
          radial-gradient(1200px 600px at 20% 0%, rgba(124,92,255,.25), transparent 55%),
          radial-gradient(900px 500px at 85% 15%, rgba(46,233,255,.18), transparent 55%),
          linear-gradient(180deg, var(--bg1), var(--bg2));
        color: var(--text);
      }

      .hero {
        padding: 14px 16px;
        border: 1px solid var(--border);
        border-radius: 18px;
        background: rgba(15,23,48,.6);
        margin-bottom: 12px;
      }

      .pill {
        padding: 6px 12px;
        border-radius: 999px;
        border: 1px solid var(--border);
        background: rgba(15,23,48,.6);
        font-size: 0.9rem;
        display: inline-block;
        margin-right: 8px;
      }

      .good { border-color: var(--good); }
      .bad  { border-color: var(--bad); }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================
# HEADER
# ============================
st.markdown(
    """
    <div class="hero">
      <h1>🏀 NBA Betting Tool</h1>
      <p>Search players, filter by opponent, analyze streaks, and share betting insights.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================
# CONSTANTS
# ============================
APP_BASE_URL = "https://nbabetting.streamlit.app"

STAT_MAP = {
    "Points": "PTS",
    "Rebounds": "REB",
    "Assists": "AST",
    "PRA (Pts+Reb+Ast)": "PRA",
    "PR (Pts+Reb)": "PR",
    "RA (Reb+Ast)": "RA",
    "PA (Pts+Ast)": "PA",
    "3PM": "FG3M",
}

DISPLAY_COLS = [
    "GAME_DATE", "MATCHUP", "MIN",
    "PTS", "REB", "AST", "PRA", "PR", "RA", "PA", "FG3M"
]

# ============================
# HELPERS
# ============================
@st.cache_data(ttl=3600)
def get_players():
    return players.get_players()

@st.cache_data(ttl=1800)
def load_season(season):
    gl = leaguegamelog.LeagueGameLog(
        season=season,
        season_type_all_star="Regular Season",
        player_or_team_abbreviation="P",
    )
    return gl.get_data_frames()[0]

@st.cache_data(ttl=3600)
def get_team_info(player_id):
    info = commonplayerinfo.CommonPlayerInfo(player_id=player_id).get_data_frames()[0]
    if info.empty:
        return {}
    row = info.iloc[0]
    return {
        "team_id": int(row["TEAM_ID"]) if not pd.isna(row["TEAM_ID"]) else 0,
        "team_name": row["TEAM_NAME"],
        "team_abbr": row["TEAM_ABBREVIATION"],
    }

def opponent_from_matchup(matchup):
    return matchup.split()[-1]

def compute_streak(series, line):
    streak = 0
    for v in series:
        if v > line:
            streak += 1
        else:
            break
    return streak

# ============================
# DEFAULTS
# ============================
season = "2025-26"

# ============================
# FILTERS
# ============================
players_list = get_players()
player_names = sorted([p["full_name"] for p in players_list])

with st.expander("🎛 Filters", expanded=True):
    player_name = st.selectbox("Player (searchable)", player_names)
    stat_label = st.selectbox("Stat", list(STAT_MAP.keys()))

    c1, c2 = st.columns(2)
    with c1:
        location = st.selectbox("Location", ["All", "Home", "Away"])
    with c2:
        games = st.selectbox("# Games", [5, 10, 15, 20, "All"])

    line = st.number_input("Line", step=0.5)

# ============================
# DATA LOAD
# ============================
player_id = next(p["id"] for p in players_list if p["full_name"] == player_name)
df = load_season(season)
pdf = df[df["PLAYER_ID"] == player_id].copy()

pdf["GAME_DATE"] = pd.to_datetime(pdf["GAME_DATE"])
pdf["OPPONENT"] = pdf["MATCHUP"].apply(opponent_from_matchup)

pdf["PRA"] = pdf["PTS"] + pdf["REB"] + pdf["AST"]
pdf["PR"] = pdf["PTS"] + pdf["REB"]
pdf["RA"] = pdf["REB"] + pdf["AST"]
pdf["PA"] = pdf["PTS"] + pdf["AST"]

if location == "Home":
    pdf = pdf[pdf["MATCHUP"].str.contains("vs")]
elif location == "Away":
    pdf = pdf[pdf["MATCHUP"].str.contains("@")]

opp_choices = ["All"] + sorted(pdf["OPPONENT"].unique())
opp = st.selectbox("Opponent (searchable)", opp_choices)

if opp != "All":
    pdf = pdf[pdf["OPPONENT"] == opp]

pdf = pdf.sort_values("GAME_DATE", ascending=False)

if games != "All":
    pdf = pdf.head(int(games))

# ============================
# VISUALS
# ============================
team = get_team_info(player_id)
headshot = f"https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"
logo = f"https://cdn.nba.com/logos/nba/{team['team_id']}/primary/L/logo.svg"

c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    st.image(logo, use_container_width=True)
with c2:
    st.image(headshot, use_container_width=True)
with c3:
    st.markdown(f"### {player_name}")
    st.caption(f"{team['team_name']} ({team['team_abbr']})")

# ============================
# METRICS
# ============================
stat_col = STAT_MAP[stat_label]
series = pdf[stat_col]

streak = compute_streak(series, line)
last5_rate = (series.head(5) > line).mean()

st.markdown(
    f"""
    <span class="pill good">🔥 Streak: {streak}</span>
    <span class="pill">Last 5 Over %: {last5_rate:.0%}</span>
    """,
    unsafe_allow_html=True,
)

# ============================
# TABS (CHART DEFAULT)
# ============================
tab_chart, tab_summary, tab_games = st.tabs(["Chart", "Summary", "Games"])

with tab_chart:
    chart_df = pdf.sort_values("GAME_DATE", ascending=True).copy()
    values = chart_df[stat_col].values

    colors = []
    for v in values:
        if v > line:
            colors.append("green")   # Over
        elif v < line:
            colors.append("red")     # Under
        else:
            colors.append("gray")    # Push

    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.bar(range(len(values)), values, color=colors)
    ax.axhline(line, linestyle="--")
    ax.set_xlabel("Game (Oldest → Newest)")
    ax.set_ylabel(stat_label)
    ax.set_title(f"{player_name} • {stat_label} vs Line")

    st.pyplot(fig, use_container_width=True)

with tab_summary:
    st.write(pdf.mean(numeric_only=True))

with tab_games:
    st.dataframe(pdf[DISPLAY_COLS], use_container_width=True)

# ============================
# SHARE LINK
# ============================
share_url = (
    f"{APP_BASE_URL}"
    f"?player_name={player_name}"
    f"&stat={stat_label}"
    f"&line={line}"
)

st.text_input("Share link", share_url)
