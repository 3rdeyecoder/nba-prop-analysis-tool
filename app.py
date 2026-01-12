import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st
import streamlit.components.v1 as components

from nba_api.stats.endpoints import leaguegamelog, commonplayerinfo
from nba_api.stats.static import players

# =========================================================
# GOOGLE ANALYTICS (GA4) + "tiny ping" event (app_load)
# - Injected via st.markdown (NOT components iframe)
# - Sends a one-time-per-browser-tab ping using sessionStorage
# =========================================================
GA_MEASUREMENT_ID = "G-P3ML6DEY01"

st.markdown(
    f"""
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());

      // Standard config
      gtag('config', '{GA_MEASUREMENT_ID}', {{
        'send_page_view': true
      }});

      // Tiny ping (one time per tab/session)
      try {{
        const key = 'ga_app_load_sent_v1';
        if (!sessionStorage.getItem(key)) {{
          gtag('event', 'app_load', {{
            'event_category': 'engagement',
            'event_label': window.location.pathname + window.location.search
          }});
          sessionStorage.setItem(key, '1');
        }}
      }} catch (e) {{
        // If sessionStorage blocked, just do nothing
      }}
    </script>
    """,
    unsafe_allow_html=True,
)

# ============================
# PAGE CONFIG
# ============================
st.set_page_config(page_title="NBA Betting Tool", layout="centered")

# ============================
# STYLES (mobile friendly + chips)
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
        --mid:#a0a0b8;
      }

      .stApp {
        background: radial-gradient(1200px 600px at 20% 0%, rgba(124,92,255,.25), transparent 55%),
                    radial-gradient(900px 500px at 85% 15%, rgba(46,233,255,.18), transparent 55%),
                    linear-gradient(180deg, var(--bg1), var(--bg2));
        color: var(--text);
      }

      .block-container { padding-top: 1rem; padding-bottom: 2rem; }

      .hero {
        padding: 14px 16px;
        border: 1px solid var(--border);
        border-radius: 18px;
        background: linear-gradient(135deg, rgba(124,92,255,.18), rgba(46,233,255,.10));
        box-shadow: 0 10px 30px rgba(0,0,0,.25);
        margin-bottom: 10px;
      }
      .hero h1 { margin: 0; font-size: 1.55rem; line-height: 1.2; }
      .hero p  { margin: 6px 0 0 0; color: var(--muted); font-size: 0.95rem; }

      details {
        border-radius: 18px !important;
        border: 1px solid var(--border) !important;
        background: rgba(15, 23, 48, .55) !important;
        padding: 8px 10px !important;
      }

      div[data-testid="stMetric"] {
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 10px 12px;
        background: rgba(15, 23, 48, .65);
      }
      div[data-testid="stMetric"] label { color: var(--muted) !important; }

      .pill-row { display:flex; gap:10px; flex-wrap:wrap; margin: 6px 0 8px 0; }
      .pill {
        border: 1px solid var(--border);
        background: rgba(15, 23, 48, .55);
        padding: 7px 10px;
        border-radius: 999px;
        font-size: 0.92rem;
        color: var(--text);
      }
      .pill.good { border-color: rgba(39,233,138,.4); }
      .pill.bad  { border-color: rgba(255,77,109,.45); }
      .pill.mid  { border-color: rgba(160,160,184,.35); }

      .stButton>button {
        border-radius: 14px;
        border: 1px solid var(--border);
        background: linear-gradient(135deg, rgba(124,92,255,.85), rgba(46,233,255,.45));
        color: white;
        font-weight: 700;
      }

      @media (max-width: 768px) {
        .block-container { padding-left: 0.9rem; padding-right: 0.9rem; }
      }
    </style>
    """,
    unsafe_allow_html=True
)

APP_BASE_URL = "https://nbabetting.streamlit.app"

st.markdown(
    """
    <div class="hero">
      <h1>🏀 NBA Betting Tool</h1>
      <p>Tip: all dropdowns are searchable. Tap a dropdown, then type.</p>
    </div>
    """,
    unsafe_allow_html=True
)

# ============================
# CONFIG
# ============================
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

def season_options():
    return ["2025-26", "2024-25", "2023-24", "2022-23", "2021-22", "2020-21", "2019-20"]

# ============================
# HELPERS
# ============================
@st.cache_data(ttl=60 * 60)
def get_all_players():
    return players.get_players()

@st.cache_data(ttl=60 * 30)
def fetch_league_player_gamelog(season: str) -> pd.DataFrame:
    gl = leaguegamelog.LeagueGameLog(
        season=season,
        season_type_all_star="Regular Season",
        player_or_team_abbreviation="P"
    )
    return gl.get_data_frames()[0]

@st.cache_data(ttl=60 * 60)
def fetch_player_team_info(player_id: int) -> dict:
    info = commonplayerinfo.CommonPlayerInfo(player_id=player_id).get_data_frames()[0]
    if info is None or info.empty:
        return {}
    row = info.iloc[0].to_dict()
    team_id = row.get("TEAM_ID", 0)
    try:
        team_id = int(team_id) if pd.notna(team_id) else 0
    except Exception:
        team_id = 0
    return {
        "TEAM_ID": team_id,
        "TEAM_ABBREVIATION": str(row.get("TEAM_ABBREVIATION", "")),
        "TEAM_NAME": str(row.get("TEAM_NAME", "")),
    }

def make_opponent(df: pd.DataFrame) -> pd.Series:
    return df["MATCHUP"].astype(str).str.split().str[-1]

def compute_streak(values: pd.Series, line_value: float) -> tuple[str, int]:
    if values.empty:
        return ("None", 0)
    latest = values.iloc[0]
    if latest > line_value:
        label = "Over"
        cond = values > line_value
    elif latest < line_value:
        label = "Under"
        cond = values < line_value
    else:
        label = "Push"
        cond = values == line_value

    count = 0
    for ok in cond.tolist():
        if ok:
            count += 1
        else:
            break
    return (label, count)

def pill_html(text: str, cls: str = "mid") -> str:
    return f'<span class="pill {cls}">{text}</span>'

def build_share_url(base_url: str, params: dict) -> str:
    from urllib.parse import urlencode
    return base_url.rstrip("/") + "/?" + urlencode(params)

def copy_to_clipboard_button(text: str, button_label: str = "Copy share link"):
    safe = text.replace("\\", "\\\\").replace("`", "\\`")
    html = f"""
    <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
      <button id="copyBtn"
        style="
          padding:10px 14px; border-radius:14px; border:1px solid rgba(42,58,102,.9);
          background: linear-gradient(135deg, rgba(124,92,255,.85), rgba(46,233,255,.45));
          color:white; font-weight:700; cursor:pointer;">
        {button_label}
      </button>
      <span id="copyMsg" style="color: rgba(169,183,230,1); font-size: 0.92rem;"></span>
    </div>
    <script>
      const btn = document.getElementById("copyBtn");
      const msg = document.getElementById("copyMsg");
      btn.onclick = async () => {{
        try {{
          await navigator.clipboard.writeText(`{safe}`);
          msg.textContent = "Copied ✅";
          setTimeout(() => msg.textContent = "", 1500);
        }} catch (e) {{
          msg.textContent = "Copy failed — select the link and copy manually.";
        }}
      }};
    </script>
    """
    components.html(html, height=55)

# ============================
# SHARE LINK PARAMS
# ============================
qp = dict(st.query_params)

def qp_get(key: str, default: str):
    v = qp.get(key, default)
    if isinstance(v, list):
        return v[0] if v else default
    return v

default_season = qp_get("season", "2025-26")
default_stat = qp_get("stat", "Points")
default_loc = qp_get("loc", "All")
default_games = qp_get("games", "10")
default_player_name = qp_get("player_name", "")
default_line = qp_get("line", "0")
default_opp = qp_get("opp", "All")

# ============================
# PLAYER LISTS
# ============================
player_list = get_all_players()
player_names = sorted([p["full_name"] for p in player_list])

# Defaults -> indices
seasons = season_options()
default_season_index = seasons.index(default_season) if default_season in seasons else 0

stat_keys = list(STAT_MAP.keys())
default_stat_index = stat_keys.index(default_stat) if default_stat in stat_keys else 0

loc_options = ["All", "Home", "Away"]
default_loc_index = loc_options.index(default_loc) if default_loc in loc_options else 0

games_options = [5, 10, 15, 20, "All"]
if str(default_games).isdigit() and int(default_games) in [5, 10, 15, 20]:
    default_games_index = games_options.index(int(default_games))
elif default_games == "All":
    default_games_index = games_options.index("All")
else:
    default_games_index = 1

try:
    default_line_value = float(default_line)
except Exception:
    default_line_value = 0.0

default_player_index = player_names.index(default_player_name) if default_player_name in player_names else 0

# ============================
# FILTERS (Opponent visible + searchable)
# ============================
with st.expander("🎛️ Filters", expanded=True):
    season = st.selectbox("Season", seasons, index=default_season_index, key="season_select")
    player_name = st.selectbox("Player (tap + type to search)", player_names, index=default_player_index, key="player_select")
    stat_label = st.selectbox("Stat", stat_keys, index=default_stat_index, key="stat_select")

    c1, c2 = st.columns(2)
    with c1:
        num_games = st.selectbox("# Games", games_options, index=default_games_index, key="games_select")
    with c2:
        location = st.selectbox("Location", loc_options, index=default_loc_index, key="loc_select")

    line_value = st.number_input("Line (for Over/Under)", value=default_line_value, step=0.5, key="line_input")

    st.caption("Opponent is searchable too: tap it and type (BOS, LAL, DEN, etc.)")
    opp_placeholder = st.empty()

# Find player_id
player_id = None
for p in player_list:
    if p["full_name"] == player_name:
        player_id = p["id"]
        break

if player_id is None:
    st.error("Player not found.")
    st.stop()

# ============================
# LOAD SEASON DATA
# ============================
df = fetch_league_player_gamelog(season)
if df is None or df.empty:
    st.error("No data returned from NBA API for this season.")
    st.stop()

if "PLAYER_ID" not in df.columns:
    st.error(f"PLAYER_ID missing from data. Columns returned: {list(df.columns)}")
    st.stop()

pdf_all = df[df["PLAYER_ID"] == player_id].copy()
if pdf_all.empty:
    st.warning("No games found for this player in this season.")
    st.stop()

pdf_all["GAME_DATE"] = pd.to_datetime(pdf_all["GAME_DATE"], errors="coerce")
pdf_all["OPPONENT"] = make_opponent(pdf_all)

# Apply location first for opponent list
pdf_loc = pdf_all.copy()
if location == "Home":
    pdf_loc = pdf_loc[pdf_loc["MATCHUP"].str.contains("vs", na=False)]
elif location == "Away":
    pdf_loc = pdf_loc[pdf_loc["MATCHUP"].str.contains("@", na=False)]

opp_list = sorted(pdf_loc["OPPONENT"].dropna().unique().tolist())
if len(opp_list) == 0:
    opp_list = sorted(pdf_all["OPPONENT"].dropna().unique().tolist())

opp_choices = ["All"] + opp_list

with opp_placeholder.container():
    opp_default_index = opp_choices.index(default_opp) if default_opp in opp_choices else 0
    opp = st.selectbox("Opponent (tap + type to search)", opp_choices, index=opp_default_index, key="opp_select")

# ============================
# HEADSHOT + TEAM LOGO
# ============================
team_info = fetch_player_team_info(player_id)
team_id = int(team_info.get("TEAM_ID", 0) or 0)
team_abbr = team_info.get("TEAM_ABBREVIATION", "")
team_name = team_info.get("TEAM_NAME", "")

headshot_url = f"https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"
logo_url = f"https://cdn.nba.com/logos/nba/{team_id}/primary/L/logo.svg" if team_id else ""

c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    if logo_url:
        st.image(logo_url, use_container_width=True)
with c2:
    st.image(headshot_url, use_container_width=True)
with c3:
    st.markdown(f"### {player_name}")
    if team_name or team_abbr:
        st.caption(f"{team_name} {f'({team_abbr})' if team_abbr else ''}")
    st.caption(f"Season: {season} • Stat: {stat_label} • Location: {location} • Opp: {opp}")

# ============================
# BUILD ANALYSIS DF
# ============================
for col in ["PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV", "MIN"]:
    if col in pdf_all.columns:
        pdf_all[col] = pd.to_numeric(pdf_all[col], errors="coerce")

pdf_all["PRA"] = pdf_all["PTS"] + pdf_all["REB"] + pdf_all["AST"]
pdf_all["PR"]  = pdf_all["PTS"] + pdf_all["REB"]
pdf_all["RA"]  = pdf_all["REB"] + pdf_all["AST"]
pdf_all["PA"]  = pdf_all["PTS"] + pdf_all["AST"]

pdf_all = pdf_all.sort_values("GAME_DATE", ascending=False)

pdf = pdf_all.copy()
if location == "Home":
    pdf = pdf[pdf["MATCHUP"].str.contains("vs", na=False)]
elif location == "Away":
    pdf = pdf[pdf["MATCHUP"].str.contains("@", na=False)]

if opp != "All":
    pdf = pdf[pdf["OPPONENT"] == opp]

if num_games != "All":
    pdf = pdf.head(int(num_games))

if pdf.empty:
    st.warning("No games found with these filters. Try Location = All and Opponent = All.")
    st.stop()

stat_col = STAT_MAP[stat_label]
series = pd.to_numeric(pdf[stat_col], errors="coerce").dropna()
if series.empty:
    st.warning("Selected stat has no numeric values for these filters.")
    st.stop()

# ============================
# METRICS + CHIPS
# ============================
over = int((series > line_value).sum())
under = int((series < line_value).sum())
push = int((series == line_value).sum())
total = int(series.shape[0])

last5 = series.head(5)
last5_over = int((last5 > line_value).sum())
last5_total = int(last5.shape[0])
last5_rate = (last5_over / last5_total) if last5_total else 0.0

streak_label, streak_count = compute_streak(series, line_value)
pill_cls = "mid"
if streak_label == "Over":
    pill_cls = "good"
elif streak_label == "Under":
    pill_cls = "bad"

chips = [
    pill_html(f"🔥 Streak: <strong>{streak_label} x{streak_count}</strong>", pill_cls),
    pill_html(f"Last 5 Over%: <strong>{last5_rate:.0%}</strong>", "good" if last5_rate >= 0.6 else "mid"),
    pill_html(f"Filter: <strong>{location}</strong> • Opp: <strong>{opp}</strong>", "mid"),
]
st.markdown(f'<div class="pill-row">{"".join(chips)}</div>', unsafe_allow_html=True)

m1, m2 = st.columns(2)
m1.metric("Over", f"{over}", f"{(over/total):.0%}")
m2.metric("Under", f"{under}", f"{(under/total):.0%}")

m3, m4 = st.columns(2)
m3.metric("Push", f"{push}", f"{(push/total):.0%}")
m4.metric("Games", f"{total}")

# ============================
# SHARE LINK + COPY BUTTON
# ============================
st.subheader("Share")

share_params = {
    "season": season,
    "player_name": player_name,
    "stat": stat_label,
    "games": str(num_games),
    "loc": location,
    "opp": opp,
    "line": str(line_value),
}
share_url = build_share_url(APP_BASE_URL, share_params)
st.text_input("Shareable link", share_url, key="share_url_box")
copy_to_clipboard_button(share_url, "Copy share link")

# ============================
# TABS (CHART DEFAULT)
# ============================
tab_chart, tab_summary, tab_games = st.tabs(["Chart", "Summary", "Games"])

with tab_chart:
    st.subheader(f"{player_name} • {stat_label} • Line {line_value}")

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

    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.bar(np.arange(len(values)), values, color=colors)
    ax.axhline(line_value, linestyle="--")
    ax.set_xlabel("Game (Oldest → Newest)")
    ax.set_ylabel(stat_label)
    ax.set_title("Game-by-game results")
    st.pyplot(fig, use_container_width=True)

with tab_summary:
    st.subheader("Averages (Filtered)")
    avg_cols = ["PTS", "REB", "AST", "PRA", "PR", "RA", "PA", "FG3M", "STL", "BLK", "TOV", "MIN"]
    avg_cols = [c for c in avg_cols if c in pdf.columns]
    avg = pdf[avg_cols].mean(numeric_only=True).round(2)
    st.write(avg)

with tab_games:
    st.subheader("Games")
    show_recent_only = st.toggle("Show only recent 10 games", value=True, key="recent_toggle")
    table_df = pdf.head(10) if show_recent_only else pdf.copy()

    existing_cols = [c for c in DISPLAY_COLS if c in table_df.columns]
    st.dataframe(
        table_df[existing_cols].sort_values("GAME_DATE", ascending=True),
        use_container_width=True,
        height=420
    )
