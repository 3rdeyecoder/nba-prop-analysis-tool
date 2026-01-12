import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st

from nba_api.stats.endpoints import leaguegamelog
from nba_api.stats.static import players

# ----------------------------
# Page setup
# ----------------------------
st.set_page_config(page_title="NBA Props Tool", layout="wide")
st.title("NBA Props Tool (Live Web App)")

# ----------------------------
# Config / Maps
# ----------------------------
STAT_MAP = {
    "Points": "PTS",
    "Rebounds": "REB",
    "Assists": "AST",
    "PRA (Pts+Reb+Ast)": "PRA",
    "PR (Pts+Reb)": "PR",
    "RA (Reb+Ast)": "RA",
    "PA (Pts+Ast)": "PA",
    "3PM": "FG3M",
    "Steals": "STL",
    "Blocks": "BLK",
    "Turnovers": "TOV",
}

DISPLAY_COLS = [
    "GAME_DATE", "MATCHUP", "WL", "MIN",
    "PTS", "REB", "AST",
    "PRA", "PR", "RA", "PA",
    "FG3M", "STL", "BLK", "TOV"
]

# ----------------------------
# Helpers (cached)
# ----------------------------
@st.cache_data(ttl=60 * 60)
def get_all_players():
    return players.get_players()

@st.cache_data(ttl=60 * 30)
def fetch_player_gamelog(season: str) -> pd.DataFrame:
    """
    Fetch PLAYER game logs for an entire season.
    This can be large, so caching matters.
    """
    gl = leaguegamelog.LeagueGameLog(
        season=season,
        season_type_all_star="Regular Season",
        player_or_team_abbreviation="P"  # important: PLAYER logs
    )
    df = gl.get_data_frames()[0]
    return df

def season_options():
    return ["2025-26", "2024-25", "2023-24", "2022-23", "2021-22", "2020-21", "2019-20"]

def get_player_id(player_list, name: str):
    for p in player_list:
        if p["full_name"] == name:
            return p["id"]
    return None

# ----------------------------
# Sidebar UI
# ----------------------------
with st.sidebar:
    st.header("Filters")

    season = st.selectbox("Season", season_options(), index=1, key="season_select")

    player_list = get_all_players()
    player_names = sorted([p["full_name"] for p in player_list])
    player_name = st.selectbox("Player", player_names, key="player_select")

    stat_label = st.selectbox("Stat", list(STAT_MAP.keys()), key="stat_select")
    stat_col = STAT_MAP[stat_label]

    num_games = st.selectbox("# Games", [5, 10, 15, 20, "All"], index=1, key="num_games_select")
    location = st.selectbox("Location", ["All", "Home", "Away"], index=0, key="location_select")

    line_value = st.number_input("Line (for Over/Under)", value=0.0, step=0.5, key="line_value")

# ----------------------------
# Load data
# ----------------------------
df = fetch_player_gamelog(season)

if df is None or df.empty:
    st.error("No data returned from NBA API for this season.")
    st.stop()

if "PLAYER_ID" not in df.columns:
    st.error(f"PLAYER_ID missing from data. Columns returned: {list(df.columns)}")
    st.stop()

player_id = get_player_id(player_list, player_name)
if player_id is None:
    st.error("Player not found.")
    st.stop()

# ----------------------------
# Build base dataframe for dropdowns
# ----------------------------
base_pdf = df[df["PLAYER_ID"] == player_id].copy()

if base_pdf.empty:
    st.warning("No games found for this player in this season (or NBA API returned no rows).")
    st.stop()

# Add GAME_DATE as datetime
base_pdf["GAME_DATE"] = pd.to_datetime(base_pdf["GAME_DATE"], errors="coerce")

# Home/Away filtering (apply before opponent list so it matches)
if location == "Home":
    # Many logs use "vs." for home
    base_pdf = base_pdf[base_pdf["MATCHUP"].str.contains("vs", na=False)]
elif location == "Away":
    base_pdf = base_pdf[base_pdf["MATCHUP"].str.contains("@", na=False)]

# Opponent extraction (robust)
# MATCHUP examples: "LAL vs. BOS" or "LAL @ BOS" -> opponent is last token
base_pdf["OPPONENT"] = base_pdf["MATCHUP"].astype(str).str.split().str[-1]

# Combo stats
base_pdf["PTS"] = base_pdf["PTS"].astype(float)
base_pdf["REB"] = base_pdf["REB"].astype(float)
base_pdf["AST"] = base_pdf["AST"].astype(float)

base_pdf["PRA"] = base_pdf["PTS"] + base_pdf["REB"] + base_pdf["AST"]
base_pdf["PR"] = base_pdf["PTS"] + base_pdf["REB"]
base_pdf["RA"] = base_pdf["REB"] + base_pdf["AST"]
base_pdf["PA"] = base_pdf["PTS"] + base_pdf["AST"]

# Sort newest -> oldest
base_pdf = base_pdf.sort_values("GAME_DATE", ascending=False)

# ----------------------------
# Opponent dropdown (must come AFTER we know base_pdf)
# ----------------------------
opp_choices = ["All"] + sorted(base_pdf["OPPONENT"].dropna().unique().tolist())
opp = st.sidebar.selectbox("Opponent", opp_choices, index=0, key="opponent_filter")

# Now apply opponent filter to working df
pdf = base_pdf.copy()
if opp != "All":
    pdf = pdf[pdf["OPPONENT"] == opp]

# Limit games after opponent selection
if num_games != "All":
    pdf = pdf.head(int(num_games))

if pdf.empty:
    st.warning("No games found with these filters.")
    st.stop()

# ----------------------------
# Calculate Over/Under
# ----------------------------
series = pd.to_numeric(pdf[stat_col], errors="coerce").dropna()
if series.empty:
    st.warning("Selected stat has no numeric values for these filters.")
    st.stop()

over = int((series > line_value).sum())
under = int((series < line_value).sum())
push = int((series == line_value).sum())
total = int(series.shape[0])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Over", f"{over}", f"{(over/total):.0%}")
c2.metric("Under", f"{under}", f"{(under/total):.0%}")
c3.metric("Push", f"{push}", f"{(push/total):.0%}")
c4.metric("Games", f"{total}")

# ----------------------------
# Games table
# ----------------------------
st.subheader("Filtered Games")
existing_cols = [c for c in DISPLAY_COLS if c in pdf.columns]
st.dataframe(
    pdf[existing_cols].sort_values("GAME_DATE", ascending=True),
    use_container_width=True
)

# ----------------------------
# Chart
# ----------------------------
st.subheader(f"{player_name} — {stat_label} vs Line {line_value}")

chart_df = pdf.sort_values("GAME_DATE", ascending=True).copy()
values = pd.to_numeric(chart_df[stat_col], errors="coerce").fillna(0).values

colors = []
for v in values:
    if v > line_value:
        colors.append("green")
    elif v < line_value:
        colors.append("red")
    else:
        colors.append("gray")

fig, ax = plt.subplots(figsize=(10, 4))
ax.bar(np.arange(len(values)), values, color=colors)
ax.axhline(line_value, linestyle="--")
ax.set_xlabel("Game (Oldest → Newest)")
ax.set_ylabel(stat_label)
ax.set_title("Game-by-game results (color: over/under/push)")
st.pyplot(fig)

# ----------------------------
# Averages
# ----------------------------
st.subheader("Averages (Filtered)")
avg_cols = ["PTS", "REB", "AST", "PRA", "PR", "RA", "PA", "FG3M", "STL", "BLK", "TOV", "MIN"]
avg_cols = [c for c in avg_cols if c in pdf.columns]
avg = pdf[avg_cols].mean(numeric_only=True).round(2)
st.write(avg)
