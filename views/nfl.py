"""NFL page. Reads stored nflverse Parquet files only."""
import pandas as pd
import streamlit as st

from core.ui import SportView, StatOption, data_status, render_analysis
from sports import nfl

VIEW = SportView(
    prefix="nfl",
    sport="nfl",
    stats=[StatOption(g, label, col) for g, label, col in nfl.STATS],
    season_types=["Regular Season", "Postseason"],
    season_label=lambda s: f"{s} season",
    extra_cols=[("week", "Week"), ("round", "Round"), ("position", "Pos")],
    participation_note=(
        "A game counts when the player has a row in nflverse's weekly player stats, which means they "
        "were credited with at least one play (pass, carry, target, kick, tackle...). Bye weeks and missed "
        "games have no row and never count. A 0 is a real zero in a game the player appeared in. "
        "Limitation: a player on the field who never touched the ball or drew a target has no row. "
        "Seasons use the official NFL season year (January playoff games belong to the prior season)."
    ),
)


@st.cache_data(show_spinner=False, max_entries=20)
def _load_season(season: int, mtime: float) -> pd.DataFrame:
    return nfl.load_season(season)


def load(seasons: tuple[str, ...], season_type: str) -> pd.DataFrame:
    frames = []
    for s in seasons:
        path = nfl.season_path(int(s))
        if path.exists():
            frames.append(_load_season(int(s), path.stat().st_mtime))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df[df["season_type"] == season_type]
    pos = st.session_state.get("nfl_positions") or nfl.POSITIONS
    return df[df["position"].isin(pos)]


with st.sidebar:
    st.markdown("### 🏈 NFL options")
    st.session_state.setdefault("nfl_positions", nfl.POSITIONS)
    st.multiselect("Positions", ["QB", "RB", "FB", "WR", "TE"], key="nfl_positions",
                   help="Limits the player list. Stats come from each player's listed nflverse position.")

seasons = [str(s) for s in nfl.available_seasons()]
if not seasons:
    st.warning("No NFL data is stored yet. Initialize it with:\n\n"
               "```\npython -m refresh.nfl --seasons 2023 2024 2025 2026\n```")
    sel = None
else:
    try:
        sel = render_analysis(VIEW, seasons, load)
    except Exception as e:  # noqa: BLE001
        st.error(f"The NFL section hit an error and couldn't render: {e}")
        sel = None

st.markdown("---")
st.caption("Weekly nflverse stats are typically published within a day of each game and can be "
           "corrected afterwards; recent weeks may change on the next refresh.")
data_status("nfl", sel.pool if sel is not None else None,
            "nflverse weekly player stats via nflreadpy (CC-BY 4.0, data by nflverse)")
