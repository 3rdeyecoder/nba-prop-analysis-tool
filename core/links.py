"""Shareable links: a view's settings live in the URL query string.

    /nba?sport=nba&player=1629029&stat=PTS&seasons=2026-27&type=regular&window=10&opp=BOS&venue=home&line=27.5
    /mlb?sport=mlb&role=pitchers&player=669373&stat=k&seasons=2026&type=regular&window=5

Opening a link selects those settings. As the visitor changes filters, the URL is updated in
place, so the browser address bar (and the "Share this view" box) always matches the screen.
Unknown or out-of-range values are ignored and fall back to the normal defaults.
"""
from __future__ import annotations

from urllib.parse import urlencode

import streamlit as st

from core.config import APP_URL, WINDOW_OPTIONS

WINDOW_TO_SLUG = {label: ("all" if n is None else str(n)) for label, n in WINDOW_OPTIONS.items()}
SLUG_TO_WINDOW = {v: k for k, v in WINDOW_TO_SLUG.items()}


def type_slug(season_type: str) -> str:
    """'Regular Season' -> 'regular', 'Postseason' -> 'postseason', 'Playoffs' -> 'playoffs'."""
    return season_type.split()[0].lower()


def build(*, sport: str, player_id: str, stat_col: str, seasons: list[str], season_type: str,
          window_label: str, opponent: str = "All", venue: str = "All",
          line: float | None = None, extra: dict | None = None) -> dict[str, str]:
    params = {"sport": sport, **(extra or {}), "player": str(player_id), "stat": stat_col,
              "seasons": ",".join(seasons), "type": type_slug(season_type),
              "window": WINDOW_TO_SLUG.get(window_label, "10")}
    if opponent and opponent != "All":
        params["opp"] = opponent
    if venue and venue != "All":
        params["venue"] = venue.lower()
    if line is not None:
        params["line"] = f"{line:g}"
    return params


def incoming(prefix: str, sport: str) -> dict[str, str] | None:
    """URL settings meant for this sport, or None if there are none or this page wrote them."""
    qp = st.query_params.to_dict()
    if "player" not in qp or qp.get("sport", sport) != sport:
        return None
    if qp == st.session_state.get(f"{prefix}_url_written"):
        return None
    return qp


def write(prefix: str, params: dict[str, str]) -> None:
    if st.query_params.to_dict() != params:
        st.query_params.from_dict(params)
    st.session_state[f"{prefix}_url_written"] = params


def full_url(url_path: str, params: dict[str, str]) -> str:
    base = APP_URL.rstrip("/") if APP_URL else _current_base()
    return f"{base}/{url_path}?{urlencode(params)}"


def _current_base() -> str:
    try:
        url = st.context.url or ""
    except Exception:  # noqa: BLE001
        url = ""
    # strip the page path and query: https://host/nba?x=1 -> https://host
    if "://" in url:
        scheme, rest = url.split("://", 1)
        return f"{scheme}://{rest.split('/', 1)[0]}"
    return ""
