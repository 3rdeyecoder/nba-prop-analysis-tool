"""Entry point: `streamlit run app.py`

Navigation uses st.navigation(position="hidden") plus a row of st.page_link buttons
under the title. Unlike st.tabs (which executes every tab on
every rerun), only the selected sport's page script runs, so opening NBA never loads NFL or
MLB data.
"""
import streamlit as st

from core import style, ticker
from core.analytics import add_google_analytics
from core.config import APP_ICON, APP_NAME, APP_SUBTITLE

st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide", initial_sidebar_state="collapsed")
style.apply()
style.apply_nav()
style.apply_header()
add_google_analytics()

# Streamlit deletes a widget's state when the widget isn't drawn on a rerun, which would
# wipe NBA selections while NFL is open. Re-assigning the sport-prefixed keys here (before
# any page runs) keeps each sport's selections alive and separate.
for _k in list(st.session_state.keys()):
    if isinstance(_k, str) and _k.startswith(("nba_", "nfl_", "mlb_", "today_")):
        st.session_state[_k] = st.session_state[_k]

# Today's Lab is the home page ("/"); sports live at /nba, /nfl and /mlb.
home = st.Page("views/today.py", title="Today's Lab", icon="🧪", url_path="today", default=True)
call_it = st.Page("views/callit.py", title="Call It", icon="🎯", url_path="callit")
sport_pages = [
    st.Page("views/nba.py", title="NBA", icon="🏀", url_path="nba"),
    st.Page("views/nfl.py", title="NFL", icon="🏈", url_path="nfl"),
    st.Page("views/mlb.py", title="MLB", icon="⚾", url_path="mlb"),
]
about = st.Page("views/about.py", title="About / How it works", icon="ℹ️", url_path="about")
nav = st.navigation([home] + sport_pages + [call_it, about], position="hidden")

with st.container(key="pl_header"):
    ticker.render({"nba": "NBA", "nfl": "NFL", "mlb": "MLB"}.get(nav.url_path))
    st.title(f"{APP_ICON} {APP_NAME}")
    st.caption(APP_SUBTITLE + " · Historical research, not picks.")
    with st.container(horizontal=True, gap="small", key="sport_nav"):
        for page in [home] + sport_pages + [call_it]:
            st.page_link(page)  # Streamlit adds the page icon
style.highlight_tab(nav.url_path)
st.sidebar.page_link(about)

nav.run()

st.markdown("---")
st.page_link(about, label="About Playmaker Lab / How it works")
st.caption("Playmaker Lab is a sports research tool: it shows past results, not predictions or picks. "
           "If you choose to bet, you must be 21+ (age limits vary by state). "
           "Gambling problem? Call or text **1-800-GAMBLER**.")
