"""Entry point: `streamlit run app.py`

Navigation uses st.navigation(position="hidden") plus a row of st.page_link buttons
under the title. Unlike st.tabs (which executes every tab on
every rerun), only the selected sport's page script runs, so opening NBA never loads NFL or
MLB data.
"""
import streamlit as st

from core import style
from core.config import APP_ICON, APP_NAME, APP_SUBTITLE

st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide", initial_sidebar_state="auto")
style.apply()
style.apply_nav()

# Streamlit deletes a widget's state when the widget isn't drawn on a rerun, which would
# wipe NBA selections while NFL is open. Re-assigning the sport-prefixed keys here (before
# any page runs) keeps each sport's selections alive and separate.
for _k in list(st.session_state.keys()):
    if isinstance(_k, str) and _k.startswith(("nba_", "nfl_", "mlb_")):
        st.session_state[_k] = st.session_state[_k]

# The default page (NBA) is served at "/"; NFL and MLB at /nfl and /mlb.
sport_pages = [
    st.Page("views/nba.py", title="NBA", icon="🏀", url_path="nba", default=True),
    st.Page("views/nfl.py", title="NFL", icon="🏈", url_path="nfl"),
    st.Page("views/mlb.py", title="MLB", icon="⚾", url_path="mlb"),
]
about = st.Page("views/about.py", title="About / How it works", icon="ℹ️", url_path="about")
nav = st.navigation(sport_pages + [about], position="hidden")

st.title(f"{APP_ICON} {APP_NAME}")
st.caption(APP_SUBTITLE + " · Historical research, not picks.")
with st.container(horizontal=True, gap="small", key="sport_nav"):
    for page in sport_pages:
        st.page_link(page)  # Streamlit adds the page icon
st.sidebar.page_link(about)

nav.run()
