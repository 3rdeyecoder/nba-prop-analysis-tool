"""Design-system CSS carried over unchanged from the original app.py."""
import streamlit as st

CSS = """
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
.stTabs [data-baseweb="tab"] p { font-size: 1.0rem !important; }


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
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)

NAV_CSS = """
<style>
.st-key-sport_nav { flex-wrap: nowrap !important; border-bottom: 1px solid rgba(128,128,128,0.25); padding-bottom: 6px; margin-bottom: 8px; }
.st-key-sport_nav a[data-testid="stPageLink-NavLink"] {
  border: 1px solid rgba(128,128,128,0.30); border-radius: 12px; padding: 6px 16px; justify-content: center; white-space: nowrap;
}
.st-key-sport_nav a[data-testid="stPageLink-NavLink"] p { font-weight: 700; font-size: 1.08rem !important; }
/* Call It: game-style tab that stands out from the research tabs */
.st-key-sport_nav a[data-testid="stPageLink-NavLink"][href$="callit"] {
  background: linear-gradient(135deg, #7c3aed 0%, #db2777 100%) !important;
  border-color: transparent !important;
  box-shadow: 0 2px 10px rgba(219, 39, 119, 0.35);
  transition: transform 0.15s ease, filter 0.15s ease;
}
.st-key-sport_nav a[data-testid="stPageLink-NavLink"][href$="callit"] p,
.st-key-sport_nav a[data-testid="stPageLink-NavLink"][href$="callit"] span { color: #fff !important; }
.st-key-sport_nav a[data-testid="stPageLink-NavLink"][href$="callit"]:hover {
  filter: brightness(1.08); transform: translateY(-1px);
}
.st-key-sport_nav a[data-testid="stPageLink-NavLink"][href$="callit"]::after {
  content: "PLAY"; margin-left: 6px; padding: 1px 7px; border-radius: 999px;
  background: rgba(255, 255, 255, 0.25); color: #fff; font-size: 0.62rem; font-weight: 800;
  letter-spacing: 0.06em;
}
@media (max-width: 640px) {   /* phones: tighter tabs that wrap onto a second row if needed */
  .st-key-sport_nav { flex-wrap: wrap !important; gap: 6px !important; }
  .st-key-sport_nav a[data-testid="stPageLink-NavLink"] { padding: 5px 10px; }
  .st-key-sport_nav a[data-testid="stPageLink-NavLink"] p { font-size: 0.95rem !important; }
}
</style>
"""


def apply_nav() -> None:
    st.markdown(NAV_CSS, unsafe_allow_html=True)


HEADER_CSS = """
<style>
/* Dark header bar: ticker, title, subtitle and tabs */
.st-key-pl_header {
  background: linear-gradient(120deg, #0b1020 0%, #1e1b4b 55%, #4c1d95 100%);
  border-radius: 18px; padding: 14px 22px 12px !important; margin-bottom: 14px;
  box-shadow: 0 8px 28px rgba(30, 27, 75, 0.25);
}
.st-key-pl_header h1, .st-key-pl_header h1 * { color: #fff !important; }
.st-key-pl_header [data-testid="stCaptionContainer"], .st-key-pl_header [data-testid="stCaptionContainer"] * {
  color: rgba(255, 255, 255, 0.72) !important; }
.st-key-pl_header .st-key-sport_nav { border-bottom: none; margin-bottom: 0; padding-bottom: 2px; }
.st-key-pl_header .st-key-sport_nav a[data-testid="stPageLink-NavLink"] {
  background: rgba(255, 255, 255, 0.08); border-color: rgba(255, 255, 255, 0.18) !important; }
.st-key-pl_header .st-key-sport_nav a[data-testid="stPageLink-NavLink"]:hover { background: rgba(255, 255, 255, 0.16); }
.st-key-pl_header .st-key-sport_nav a[data-testid="stPageLink-NavLink"] p,
.st-key-pl_header .st-key-sport_nav a[data-testid="stPageLink-NavLink"] span { color: #fff !important; }

/* Results ticker */
.pl-ticker { display: flex; gap: 8px; overflow-x: auto; padding: 2px 0 10px; margin-bottom: 4px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12); scrollbar-width: thin; }
.pl-ticker .tk-label { flex: 0 0 auto; color: #c4b5fd; font-size: 0.66rem !important; font-weight: 800;
  letter-spacing: 0.08em; line-height: 1.3 !important; align-self: center; padding-right: 4px; }
.pl-ticker .tk-game { flex: 0 0 auto; min-width: 118px; padding: 6px 10px; border-radius: 10px;
  background: rgba(255, 255, 255, 0.07); border: 1px solid rgba(255, 255, 255, 0.10); }
.pl-ticker .tk-head { color: rgba(255, 255, 255, 0.55); font-size: 0.62rem !important; font-weight: 700;
  letter-spacing: 0.03em; margin-bottom: 3px; white-space: nowrap; line-height: 1.3 !important; }
.pl-ticker .tk-row { display: flex; align-items: center; gap: 6px; color: rgba(255, 255, 255, 0.7);
  font-size: 0.82rem !important; line-height: 1.45 !important; }
.pl-ticker .tk-row img { width: 18px; height: 18px; padding: 2px; border-radius: 50%; object-fit: contain;
  background: rgba(255, 255, 255, 0.92); box-sizing: border-box; }   /* light circle keeps dark logos visible */
.pl-ticker .tk-dot { width: 8px; height: 8px; border-radius: 50%; background: rgba(255, 255, 255, 0.35);
  margin: 0 4px; display: inline-block; }
.pl-ticker .tk-abbr { font-weight: 700; }
.pl-ticker .tk-pts { margin-left: auto; font-variant-numeric: tabular-nums; }
.pl-ticker .tk-win { color: #fff; font-weight: 800; }
/* upcoming games: purple accent so they read differently from finals */
.pl-ticker .tk-label-up { color: #f0abfc; }
.pl-ticker .tk-label + .tk-game { margin-left: 0; }
.pl-ticker .tk-up { background: rgba(167, 139, 250, 0.16); border-color: rgba(196, 181, 253, 0.35); }
.pl-ticker .tk-up .tk-head { color: #e9d5ff; }
.pl-ticker .tk-up .tk-row { color: #fff; }
.pl-ticker .tk-rec { margin-left: auto; color: rgba(255, 255, 255, 0.55); font-size: 0.72rem !important;
  font-variant-numeric: tabular-nums; }
.pl-ticker .tk-tv { margin-top: 2px; color: rgba(255, 255, 255, 0.6); font-size: 0.62rem !important; font-weight: 700;
  letter-spacing: 0.03em; white-space: nowrap; }
.pl-ticker .tk-label:not(:first-child) { margin-left: 8px; padding-left: 12px; border-left: 1px solid rgba(255, 255, 255, 0.18); }
@media (max-width: 640px) { .st-key-pl_header { padding: 12px 14px 10px !important; } }
</style>
"""


def apply_header() -> None:
    st.markdown(HEADER_CSS, unsafe_allow_html=True)


def highlight_tab(url_path: str) -> None:
    """Mark the open page's tab (Streamlit doesn't expose an 'active' marker for page links).
    Links are matched by how their address ENDS, since Streamlit Cloud writes them with a prefix;
    the home tab (Today's Lab) is always first, so it's matched by position."""
    link = 'a[data-testid="stPageLink-NavLink"]'
    if url_path in ("", "today"):
        sel = f'.st-key-sport_nav [data-testid="stElementContainer"]:first-child {link}'
    else:
        sel = f'.st-key-sport_nav {link}[href$="{url_path}"]'
    if url_path == "callit":
        css = f"{sel} {{ outline: 2px solid #fff; outline-offset: 2px; }}"
    else:
        css = (f"{sel} {{ background: #fff !important; border-color: #fff !important; }} "
               f"{sel} p, {sel} span {{ color: #1e1b4b !important; }}")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
