"""Player cards shared by Today's Lab and Call It.

A card: headshot banner (with optional team logo, rank/badge and a season tag), name, team line,
a big headline number, a colored pill, supporting lines, and a link into the analysis.

Headshots come from NBA's image server, which only has each player's CURRENT photo. The team
logo, team abbreviation and season tag come from the game itself, so they're correct for that year.
"""
from __future__ import annotations

import streamlit as st

HEADSHOT = "https://cdn.nba.com/headshots/nba/latest/260x190/{}.png"
LOGO = "https://cdn.nba.com/logos/nba/{}/global/L/logo.svg"

CARD_CSS = """
<style>
[class*="st-key-pc_"] { padding: 0 !important; overflow: hidden; }
[class*="st-key-pc_"] [data-testid="stPageLink"] { padding: 0 12px 10px; }
.pc-top { position: relative; height: 112px; display: flex; align-items: flex-end; justify-content: center;
  background: linear-gradient(160deg, rgba(107,138,253,0.22), rgba(47,191,113,0.12)); }
.pc-top.good { background: linear-gradient(160deg, rgba(47,191,113,0.45), rgba(47,191,113,0.12)); }
.pc-top.bad  { background: linear-gradient(160deg, rgba(229,72,77,0.42), rgba(229,72,77,0.10)); }
.pc-shot { height: 104px; width: auto; display: block; }
.pc-logo { position: absolute; top: 8px; right: 8px; width: 30px; height: 30px; }
.pc-rank { position: absolute; top: 8px; left: 10px; font-weight: 800; font-size: 0.85rem; opacity: 0.8; }
.pc-season { position: absolute; bottom: 6px; right: 8px; font-size: 0.68rem; font-weight: 800;
  padding: 1px 7px; border-radius: 999px; background: rgba(0,0,0,0.55); color: #fff; letter-spacing: 0.03em; }
.pc-body { padding: 10px 12px 4px; }
.pc-team { font-size: 0.8rem; opacity: 0.7; margin-bottom: 6px; }
.pc-body .pc-name { font-weight: 800; font-size: 1.05rem !important; line-height: 1.2; }
.pc-body .pc-big { font-size: 2.1rem !important; font-weight: 800; line-height: 1.05 !important;
  letter-spacing: -0.02em; margin: 2px 0; }
.pc-body .pc-big span { font-size: 0.85rem !important; font-weight: 600; opacity: 0.7; margin-left: 4px;
  letter-spacing: 0; }
.pc-pill { display: inline-block; margin: 6px 0 4px; padding: 2px 9px; border-radius: 999px;
  font-size: 0.8rem; font-weight: 700; }
.pc-pill.up, .pc-pill.good { color: #1f9d5c; background: rgba(47,191,113,0.15); }
.pc-pill.steady { color: #4f6fe0; background: rgba(107,138,253,0.15); }
.pc-pill.bad { color: #d23c41; background: rgba(229,72,77,0.14); }
.pc-sub { font-size: 0.83rem; opacity: 0.85; }
.pc-meta { font-size: 0.72rem; opacity: 0.6; margin-top: 6px; line-height: 1.35; }
.pc-vs { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; opacity: 0.8; margin-bottom: 6px; }
.pc-vs img { width: 20px; height: 20px; }
@media (max-width: 640px) {   /* phones: one full-width card per row */
  div:has(> [class*="st-key-pc_"]), [class*="st-key-pc_"] {
    width: 100% !important; max-width: 100% !important; flex: 1 1 100% !important; }
  .pc-top { height: 128px; }
  .pc-shot { height: 120px; }
}
</style>
"""


def apply_css() -> None:
    st.markdown(CARD_CSS, unsafe_allow_html=True)


def logo_img(team_id, cls: str = "pc-logo") -> str:
    try:
        return f'<img class="{cls}" src="{LOGO.format(int(team_id))}" alt="">' if team_id is not None else ""
    except (TypeError, ValueError):   # NaN or missing
        return ""


def player_card(key: str, *, player_id: str, name: str, team: str, team_id=None, badge: str = "",
                big: str, unit_label: str, pill: str, pill_kind: str, sub: str, meta: str,
                link: dict | None = None, link_label: str = "Open analysis →", team_line: str | None = None,
                season: str | None = None, tone: str = "") -> None:
    """Render one card. `tone` = '', 'good' or 'bad' tints the headshot banner."""
    team_line = team_line or f'<div class="pc-team">{team}</div>'
    season_tag = f'<span class="pc-season">{season}</span>' if season else ""
    badge_html = f'<span class="pc-rank">{badge}</span>' if badge else ""
    with st.container(border=True, width=232, key=f"pc_{key}"):
        st.markdown(
            f'<div class="pc-top {tone}">{badge_html}'
            f'<img class="pc-shot" src="{HEADSHOT.format(player_id)}" alt="">{logo_img(team_id)}{season_tag}</div>'
            f'<div class="pc-body"><div class="pc-name">{name}</div>{team_line}'
            f'<div class="pc-big">{big}<span>{unit_label}</span></div>'
            f'<div class="pc-pill {pill_kind}">{pill}</div>'
            f'<div class="pc-sub">{sub}</div><div class="pc-meta">{meta}</div></div>',
            unsafe_allow_html=True)
        if link is not None:
            st.page_link("views/nba.py", label=link_label, query_params=link)
