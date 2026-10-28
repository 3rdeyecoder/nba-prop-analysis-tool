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
    initial_sidebar_state="auto",  # open on desktop, closed on phones
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


.player-name { font-size: 1.85rem !important; font-weight: 700; letter-spacing: -0.01em; line-height: 1.2 !important; }
.player-sub { font-size: 0.98rem !important; opacity: 0.75; margin-top: 2px; }

.hit-grid { display: flex; flex-wrap: wrap; gap: 10px; margin: 6px 0 8px; }
.hit-tile {
  flex: 1 1 105px;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid rgba(128,128,128,0.25);
  border-left: 4px solid rgba(128,128,128,0.45);
  background: rgba(128,128,128,0.06);
}
.hit-tile.over  { border-left-color: #2fbf71; background: rgba(47,191,113,0.10); }
.hit-tile.under { border-left-color: #e5484d; background: rgba(229,72,77,0.10); }
.hit-label { font-size: 0.85rem !important; opacity: 0.8; }
.hit-value { font-size: 1.55rem !important; font-weight: 700; line-height: 1.25 !important; }
.hit-pct   { font-size: 0.9rem !important; opacity: 0.85; }
.streak    { font-size: 1.0rem !important; margin-top: 2px; }

.mobile-hint { display: none; }
@media (max-width: 640px) {
  .mobile-hint {
    display: block;
    padding: 10px 14px;
    border-radius: 12px;
    background: rgba(128,128,128,0.10);
    font-size: 0.95rem !important;
    margin-bottom: 10px;
  }
}
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
    "2026-27",
]
DEFAULT_SEASON = "2026-27"

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

def default_book_line(values: pd.Series) -> float:
    """Sportsbook-style default: last-10 average, snapped to the nearest .5 below it (no pushes)."""
    recent = values.tail(10)
    if recent.empty:
        return 0.5
    return float(np.floor(recent.mean())) + 0.5

OVER_COLOR = "#2fbf71"
AVG_COLOR = "#f59e0b"   # rolling average (amber, visible in light + dark)
LINE_COLOR = "#8b8f98"  # prop line (neutral grey, visible in light + dark)
UNDER_COLOR = "#e5484d"

def hit_tile_html(label: str, values: pd.Series, line: float) -> str:
    n = len(values)
    if n == 0:
        return (f'<div class="hit-tile"><div class="hit-label">{label}</div>'
                f'<div class="hit-value">–</div><div class="hit-pct">no games</div></div>')
    hits = int((values >= line).sum())
    rate = hits / n
    tone = "over" if rate >= 0.6 else "under" if rate <= 0.4 else ""
    return (f'<div class="hit-tile {tone}"><div class="hit-label">{label}</div>'
            f'<div class="hit-value">{hits}/{n}</div><div class="hit-pct">{rate*100:.0f}%</div></div>')

def current_streak(values: pd.Series, line: float):
    sides = (values >= line).tolist()
    if not sides:
        return 0, None
    last, k = sides[-1], 0
    for side in reversed(sides):
        if side != last:
            break
        k += 1
    return k, ("Over" if last else "Under")

def show_chart(fig):
    """Render a Plotly chart that doesn't hijack touch scrolling on phones."""
    fig.update_layout(dragmode=False)
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "scrollZoom": False})

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
import os
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

NBA_HEADERS = {
    "Host": "stats.nba.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "Connection": "keep-alive",
}


def fetch_season_live(season: str, timeout: int = 30, retries: int = 2) -> pd.DataFrame:
    """Pull one season from stats.nba.com. Set NBA_PROXY (env var or st.secrets) to route through a proxy."""
    proxy = os.environ.get("NBA_PROXY")
    if not proxy:
        try:
            proxy = st.secrets.get("NBA_PROXY")
        except Exception:  # no secrets.toml
            proxy = None
    last_err = None
    for attempt in range(retries + 1):
        try:
            logs = leaguegamelog.LeagueGameLog(
                player_or_team_abbreviation="P",
                season=season,
                season_type_all_star="Regular Season",
                headers=NBA_HEADERS,
                timeout=timeout,
                proxy=proxy,
            )
            return logs.get_data_frames()[0]
        except Exception as e:  # ReadTimeout, ConnectionError, JSON errors...
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def load_season_snapshot(season: str):
    path = DATA_DIR / f"league_logs_{season}.csv.gz"
    return pd.read_csv(path) if path.exists() else None


@st.cache_data(show_spinner=False, ttl=60 * 60)
def load_league_logs(seasons: list[str], refresh_key: str) -> pd.DataFrame:
    all_logs = []
    failed = []
    for s in seasons:
        df_season = load_season_snapshot(s)          # 1) committed snapshot (fast, always works)
        if df_season is None:
            try:
                df_season = fetch_season_live(s)     # 2) live API as a fallback
            except Exception:
                failed.append(s)
                continue
        df_season["SEASON"] = s
        all_logs.append(df_season)

    if failed:
        st.warning(
            f"Couldn't reach stats.nba.com for: {', '.join(failed)}. "
            "Run `python fetch_data.py` locally and commit the data/ folder."
        )
    if not all_logs:
        st.error("No data available for the selected season(s).")
        st.stop()

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
    st.markdown(
        '<div class="mobile-hint">Done with settings? Tap <b>«</b> at the top of this menu to close it.</div>',
        unsafe_allow_html=True,
    )
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
st.caption("Pick a player and stat, enter the sportsbook line, and see how often they've cleared it.")
st.markdown(
    '<div class="mobile-hint">Seasons and settings are in the menu. Tap <b>»</b> at the top left to open it.</div>',
    unsafe_allow_html=True,
)

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

    # Every game for this player in the selected seasons (used by the header + hit-rate strip)
    stat_col = STAT_MAP[stat]
    player_all = df_logs[df_logs["PLAYER_NAME"] == player].sort_values("GAME_DATE").copy()
    player_all["SELECTED_STAT"] = pd.to_numeric(player_all[stat_col], errors="coerce")
    player_all = player_all.dropna(subset=["SELECTED_STAT"])
    if player_all.empty:
        st.warning(f"No {stat} data for {player} in the selected seasons.")
        st.stop()

    r2c1, r2c2, r2c3 = st.columns([1.0, 1.2, 1.0])
    with r2c1:
        home_away = st.selectbox("🏠 Home/Away", ["All", "Home", "Away"])
    with r2c2:
        opponent = st.selectbox("🛡️ Opponent", ["All"] + sorted(df_logs["OPPONENT"].unique().tolist()))
    with r2c3:
        line = st.number_input(
            "🎯 Line",
            min_value=0.0,
            max_value=200.0,
            value=default_book_line(player_all["SELECTED_STAT"]),
            step=0.5,
            key=f"line_{player}_{stat}",
            help="Defaults to the last-10 average. Change it to the sportsbook line you're looking at.",
        )


# -------------------------
# Player header card
# -------------------------
player_id = int(player_all["PLAYER_ID"].iloc[-1])
team = player_all["TEAM_ABBREVIATION"].iloc[-1] if "TEAM_ABBREVIATION" in player_all else ""
vals_all = player_all["SELECTED_STAT"]
season_avg = vals_all.mean()
l5_avg = vals_all.tail(5).mean()
l10_avg = vals_all.tail(10).mean()
min_season = player_all["MIN"].mean()
min_l5 = player_all["MIN"].tail(5).mean()
season_text = seasons[0] if len(seasons) == 1 else f"{len(seasons)} seasons"

with st.container(border=True):
    left, right = st.columns([0.22, 1.78], vertical_alignment="center")
    with left:
        st.image(player_headshot_url(player_id), width=130)
    with right:
        st.markdown(
            f'''<div class="player-name">{player}</div>
<div class="player-sub">{team}, {len(player_all)} games in {season_text}. Showing {stat}.</div>''',
            unsafe_allow_html=True,
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{stat} avg", f"{season_avg:.1f}")
    m2.metric("Last 5", f"{l5_avg:.1f}", delta=f"{l5_avg - season_avg:+.1f} vs avg")
    m3.metric("Last 10", f"{l10_avg:.1f}", delta=f"{l10_avg - season_avg:+.1f} vs avg")
    m4.metric("Minutes (L5)", f"{min_l5:.1f}", delta=f"{min_l5 - min_season:+.1f} vs avg")

# -------------------------
# Hit-rate strip
# -------------------------
with st.container(border=True):
    st.subheader(f"Hit rate: {stat} over {line:.1f}")

    tiles = [
        ("Last 5", vals_all.tail(5)),
        ("Last 10", vals_all.tail(10)),
        ("Last 20", vals_all.tail(20)),
        ("Season" if len(seasons) == 1 else "All games", vals_all),
        ("Home", player_all.loc[player_all["IS_HOME"], "SELECTED_STAT"]),
        ("Away", player_all.loc[~player_all["IS_HOME"], "SELECTED_STAT"]),
    ]
    if opponent != "All":
        tiles.append((f"vs {opponent}", player_all.loc[player_all["OPPONENT"] == opponent, "SELECTED_STAT"]))

    st.markdown(
        '<div class="hit-grid">' + "".join(hit_tile_html(lbl, v, line) for lbl, v in tiles) + "</div>",
        unsafe_allow_html=True,
    )

    streak_len, streak_side = current_streak(vals_all, line)
    if streak_len >= 2:
        color = OVER_COLOR if streak_side == "Over" else UNDER_COLOR
        st.markdown(
            f'<div class="streak">Went <b style="color:{color}">{streak_side}</b> in each of the last <b>{streak_len}</b> games.</div>',
            unsafe_allow_html=True,
        )
    st.caption("Counts every game in the selected seasons. The timeframe, home/away and opponent filters only change the charts below.")

# -------------------------
# Filtered view for the charts below
# -------------------------
# Apply filters
player_df = player_all.copy()

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

player_df["OU"] = np.where(player_df["SELECTED_STAT"] >= line, "Over", "Under")

# -------------------------
# Tabs
# -------------------------
tab_overview, tab_trends, tab_matchup = st.tabs(["📌 Overview", "📈 Trends", "🧩 Matchup"])

# ---------- Overview ----------
with tab_overview:
    with st.container(border=True):
        st.subheader("Over / Under by Game")

        chart_df = player_df.copy()
        date_fmt = "%b %d" if len(seasons) == 1 else "%b %d '%y"
        chart_df["X_LABEL"] = (
            chart_df["GAME_DATE"].dt.strftime(date_fmt) + "<br>"
            + np.where(chart_df["IS_HOME"], "vs ", "@ ") + chart_df["OPPONENT"]
        )
        chart_df["VENUE"] = np.where(chart_df["IS_HOME"], "Home", "Away")
        chart_df["ROLL5"] = chart_df["SELECTED_STAT"].rolling(5, min_periods=1).mean()
        colors = np.where(chart_df["OU"].to_numpy() == "Over", OVER_COLOR, UNDER_COLOR)
        show_text = len(chart_df) <= 15

        overs = int((chart_df["OU"] == "Over").sum())
        st.caption(
            f"Over in {overs} of {len(chart_df)} games shown. "
            "Green cleared the line, red fell short; the orange line is the 5-game rolling average, the dashed grey line is your prop line."
        )

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=chart_df["X_LABEL"],
                y=chart_df["SELECTED_STAT"],
                marker_color=colors,
                text=chart_df["SELECTED_STAT"].round(0).astype(int) if show_text else None,
                textposition="outside",
                cliponaxis=False,
                customdata=np.stack([chart_df["MATCHUP"], chart_df["MIN"], chart_df["VENUE"]], axis=1),
                hovertemplate=(
                    f"{stat}: %{{y}}<br>"
                    "Matchup: %{customdata[0]}<br>"
                    "MIN: %{customdata[1]}<br>"
                    "Venue: %{customdata[2]}<extra></extra>"
                ),
                name=stat,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=chart_df["X_LABEL"],
                y=chart_df["ROLL5"],
                mode="lines+markers",
                line=dict(color=AVG_COLOR, width=3),
                marker=dict(size=7, color=AVG_COLOR),
                hovertemplate="5-game avg: %{y:.1f}<extra></extra>",
                name="5-game avg",
            )
        )
        fig.add_hline(
            y=line,
            line_dash="dash",
            line_color=LINE_COLOR,
            line_width=2,
            annotation_text=f"Line {line:.1f}",
            annotation_position="top right",
        )
        fig.update_layout(
            margin=dict(l=10, r=10, t=30, b=10),
            showlegend=False,
            bargap=0.25,
            xaxis=dict(type="category", automargin=True),
            yaxis=dict(title=stat, rangemode="tozero"),
        )
        show_chart(fig)

    with st.container(border=True):
        st.subheader("Distribution")
        st.caption("Shows volatility and where outcomes cluster. Useful for understanding risk.")
        if len(player_df) < 8:
            st.info(f"Only {len(player_df)} games in this view. This chart gets useful around 8 or more, so try a longer timeframe.")
        else:
            counts = player_df["SELECTED_STAT"].round(0).astype(int).value_counts().sort_index()
            bar_colors = [OVER_COLOR if v >= line else UNDER_COLOR for v in counts.index]
            hist = go.Figure(go.Bar(
                x=counts.index, y=counts.values, marker_color=bar_colors,
                hovertemplate=f"{stat} %{{x}}: %{{y}} game(s)<extra></extra>",
            ))
            hist.add_vline(x=line, line_dash="dash", line_color=LINE_COLOR, line_width=2,
                           annotation_text=f"Line {line:.1f}", annotation_position="top")
            hist.update_layout(margin=dict(l=10, r=10, t=40, b=10), xaxis_title=stat,
                               yaxis_title="Games", bargap=0.15, showlegend=False)
            hist.update_yaxes(dtick=1, rangemode="tozero")
            show_chart(hist)

    with st.container(border=True):
        st.subheader("Recent Game Log")
        st.caption("Games included after your filters.")
        view = player_df[["GAME_DATE", "MATCHUP", "OPPONENT", "IS_HOME", "MIN", "SELECTED_STAT", "OU"]].copy()
        view["HOME_AWAY"] = np.where(view["IS_HOME"], "Home", "Away")
        view = view.drop(columns=["IS_HOME"]).rename(columns={"GAME_DATE": "DATE", "SELECTED_STAT": stat})
        view = view.sort_values("DATE", ascending=False)
        st.dataframe(view, width="stretch", hide_index=True)

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
        show_chart(line_fig)

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
        show_chart(roll_fig)

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
        st.dataframe(opp_summary, width="stretch")

    with st.container(border=True):
        st.subheader("Home vs Away Summary (in this view)")
        st.caption("Quick comparison between home and away games after filters.")
        ha = (
            player_df.assign(HomeAway=np.where(player_df["IS_HOME"], "Home", "Away"))
            .groupby("HomeAway")["SELECTED_STAT"]
            .agg(games="count", avg="mean", median="median")
            .sort_values("games", ascending=False)
        )
        st.dataframe(ha, width="stretch")

# Raw table
if show_raw_table:
    with st.container(border=True):
        st.subheader("Raw Data (Debug)")
        st.caption("Use this to confirm columns and troubleshoot.")
        st.dataframe(df_logs.head(200), width="stretch", hide_index=True)

st.markdown("---")

if "last_data_update" in st.session_state:
    st.caption(
        f"🕒 Last updated: "
        f"{st.session_state.last_data_update.strftime('%Y-%m-%d %I:%M %p')} ET"
    )

