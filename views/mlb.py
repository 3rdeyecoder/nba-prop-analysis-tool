"""MLB page with separate Hitters and Pitchers sections. Reads stored Parquet files only."""
import pandas as pd
import streamlit as st

from core.metrics import outs_to_ip
from core.ui import SportView, StatOption, data_status, render_analysis
from sports import mlb

COMMON_RULES = ("Doubleheader games are separate games, ordered game 1 then game 2. A suspended game "
                "is stored once, after it is completed, and dated by the day it began (how MLB credits "
                "the stats). Regular season and postseason are kept separate.")


def _ip_display(values: pd.Series, col: str) -> pd.Series:
    if col != "outs":
        return values.map(lambda v: f"{v:g}")
    return values.map(lambda v: f"{int(v)} ({outs_to_ip(v)} IP)")


HITTERS = SportView(
    prefix="mlb_hit", sport="mlb",
    stats=[StatOption(g, label, col) for g, label, col in mlb.HITTER_STATS],
    season_types=["Regular Season", "Postseason"],
    extra_cols=[("round", "Round"), ("batting_order", "Bat. order"), ("pa", "PA")],
    participation_note=("A hitter game counts when the player had at least one plate appearance; "
                        "defensive-only and pinch-running appearances are excluded. "
                        "Strikeouts here are the batter's own strikeouts. " + COMMON_RULES),
)
PITCHERS = SportView(
    prefix="mlb_pit", sport="mlb",
    stats=[StatOption(g, label, col) for g, label, col in mlb.PITCHER_STATS],
    season_types=["Regular Season", "Postseason"],
    extra_cols=[("round", "Round"), ("ip", "IP"), ("started", "Start"), ("pitches", "Pitches")],
    value_display=_ip_display,
    participation_note=("A pitcher game counts when the pitcher faced at least one batter or recorded "
                        "an out. Workload is stored as outs: 5.2 IP means 5 innings + 2 outs = 17 outs, "
                        "not 5.2 decimal innings. Strikeouts here are strikeouts the pitcher recorded. "
                        + COMMON_RULES),
)


@st.cache_data(show_spinner=False, max_entries=20)
def _load(kind: str, season: int, mtime: float) -> pd.DataFrame:
    return mlb.load_season(kind, season)


def _read(kind: str, seasons: tuple[str, ...], season_type: str) -> pd.DataFrame:
    frames = []
    for s in seasons:
        path = mlb.path_for(kind, int(s))
        if path.exists():
            frames.append(_load(kind, int(s), path.stat().st_mtime))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return df[df["season_type"] == season_type]


def load_hitters(seasons, season_type):
    df = _read("hitting", seasons, season_type)
    if df.empty:
        return df
    if st.session_state.get("mlb_hit_starters"):
        df = df[df["started"]]
    return df[df["pa"] >= st.session_state.get("mlb_hit_min_pa", 1)]


def load_pitchers(seasons, season_type):
    df = _read("pitching", seasons, season_type)
    if df.empty:
        return df
    if st.session_state.get("mlb_pit_scope", "Starts only") == "Starts only":
        df = df[df["started"]]
    return df


st.session_state.setdefault("mlb_role", "Hitters")
role = st.segmented_control("Section", ["Hitters", "Pitchers"], key="mlb_role", label_visibility="collapsed")
role = role or "Hitters"

kind = "hitting" if role == "Hitters" else "pitching"
seasons = [str(s) for s in mlb.available_seasons(kind)]
sel = None
if not seasons:
    st.warning("No MLB data is stored yet. Initialize it with:\n\n"
               "```\npython -m refresh.mlb --seasons 2025 2026\n```\n\n"
               "This needs network access to statsapi.mlb.com.")
elif role == "Hitters":
    c1, c2 = st.columns(2)
    st.session_state.setdefault("mlb_hit_starters", False)
    st.session_state.setdefault("mlb_hit_min_pa", 1)
    c1.toggle("Starting lineup only", key="mlb_hit_starters",
              help="Only games where the hitter was in the starting lineup.")
    c2.number_input("Minimum plate appearances", min_value=1, max_value=8, step=1, key="mlb_hit_min_pa",
                    help="Games with fewer PAs are excluded before the recent-games window.")
    try:
        sel = render_analysis(HITTERS, seasons, load_hitters)
    except Exception as e:  # noqa: BLE001
        st.error(f"The MLB hitters section hit an error and couldn't render: {e}")
else:
    st.session_state.setdefault("mlb_pit_scope", "Starts only")
    st.radio("Appearances", ["Starts only", "Starts + relief"], key="mlb_pit_scope", horizontal=True,
             help="Starts only is the default for pitcher props.")
    try:
        sel = render_analysis(PITCHERS, seasons, load_pitchers)
    except Exception as e:  # noqa: BLE001
        st.error(f"The MLB pitchers section hit an error and couldn't render: {e}")

st.markdown("---")
data_status("mlb", sel.pool if sel is not None else None,
            "MLB Stats API boxscores (© MLB Advanced Media; individual, non-commercial use)")
