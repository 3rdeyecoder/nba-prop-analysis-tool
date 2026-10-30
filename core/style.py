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
</style>
"""


def apply_nav() -> None:
    st.markdown(NAV_CSS, unsafe_allow_html=True)
