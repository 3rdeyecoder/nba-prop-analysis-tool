"""NBA page. Reads stored snapshots only (no live stats.nba.com calls from the app)."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.config import LINE_COLOR, OVER_COLOR, UNDER_COLOR
from core.metrics import OVER, PUSH, UNDER, classify
from core.ui import Selection, SportView, StatOption, data_status, render_analysis, show_chart
from sports import nba

VIEW = SportView(
    prefix="nba",
    sport="nba",
    stats=[StatOption("", label, col) for label, col in nba.STATS.items()],
    season_types=list(nba.SEASON_TYPES),
    extra_cols=[("MIN", "MIN")],
    participation_note=(
        "Every game in stats.nba.com's player game log, i.e. games the player checked into "
        "(including cameos that round to 0 minutes). DNPs and inactive games are not counted."
    ),
)


@st.cache_data(show_spinner=False, max_entries=40)
def _load_file(path: str, season: str, season_type: str, mtime: float) -> pd.DataFrame:
    # mtime is part of the cache key, so a refreshed file is re-read automatically.
    from pathlib import Path
    return nba.load_file(Path(path), season, season_type)


def load(seasons: tuple[str, ...], season_type: str) -> pd.DataFrame:
    frames, problems = [], []
    for s in seasons:
        path = nba.season_path(s, season_type)
        if not path.exists():
            continue
        try:
            frames.append(_load_file(str(path), s, season_type, path.stat().st_mtime))
        except Exception as e:  # noqa: BLE001 - one bad file shouldn't break the page
            problems.append(f"{s}: {e}")
    if problems:
        st.warning("Some stored NBA files couldn't be read: " + "; ".join(problems))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------- NBA-only pieces

def _hit_tile(label: str, values: pd.Series, line: float) -> str:
    res = classify(values.dropna(), line)
    o, u, p = int((res == OVER).sum()), int((res == UNDER).sum()), int((res == PUSH).sum())
    if o + u == 0:
        sub = "no games" if p == 0 else f"{p} push{'es' if p > 1 else ''}"
        return (f'<div class="hit-tile"><div class="hit-label">{label}</div>'
                f'<div class="hit-value">–</div><div class="hit-pct">{sub}</div></div>')
    rate = o / (o + u)
    tone = "over" if rate >= 0.6 else "under" if rate <= 0.4 else ""
    push_txt = f" · {p}P" if p else ""
    return (f'<div class="hit-tile {tone}"><div class="hit-label">{label}</div>'
            f'<div class="hit-value">{o}/{o + u}</div><div class="hit-pct">{rate*100:.0f}%{push_txt}</div></div>')


def _streak(values: pd.Series, line: float):
    res = classify(values.dropna(), line).tolist()
    if not res or res[-1] == PUSH:
        return 0, None
    last, k = res[-1], 0
    for r in reversed(res):
        if r != last:
            break
        k += 1
    return k, last


def trend_sentence(player_name: str, stat_key: str, s: pd.Series) -> str:
    """Unchanged from the original app."""
    if len(s) < 6:
        return f"{player_name} does not have enough games in this timeframe to confidently describe a trend for {stat_key}."
    first, second = s.iloc[: len(s)//2].mean(), s.iloc[len(s)//2:].mean()
    diff = second - first
    slope = np.polyfit(np.arange(len(s), dtype=float), s.astype(float).to_numpy(), 1)[0]
    direction = "upward" if diff > 0.25 else "downward" if diff < -0.25 else "flat"
    if direction == "flat":
        return f"{player_name}'s {stat_key} trend looks fairly steady in this timeframe (no strong upward or downward movement)."
    strength = "slightly" if abs(diff) < 1.0 else "clearly" if abs(diff) >= 2.0 else "moderately"
    slope_hint = "with consistent momentum" if abs(slope) > 0.10 else "but with game-to-game swings"
    return (f"{player_name} is trending **{direction}** for **{stat_key}** {strength} "
            f"({first:.1f} → {second:.1f} avg from early to late games), {slope_hint}.")


def header(sel: Selection) -> None:
    g = sel.player_games
    col = sel.stat.col
    vals = g[col].dropna()
    last = g.iloc[-1]
    season_text = sel.seasons[0] if len(sel.seasons) == 1 else f"{len(sel.seasons)} seasons"
    with st.container(border=True):
        left, right = st.columns([0.22, 1.78], vertical_alignment="center")
        left.image(last["headshot_url"], width=130)
        right.markdown(
            f'<div class="player-name">{sel.player_name}</div>'
            f'<div class="player-sub">{last["team"]}, {len(g)} games in {season_text} '
            f'({sel.season_type.lower()}). Showing {sel.stat.label}.</div>',
            unsafe_allow_html=True,
        )
        avg, l5, l10 = vals.mean(), vals.tail(5).mean(), vals.tail(10).mean()
        m_avg, m_l5 = g["MIN"].mean(), g["MIN"].tail(5).mean()
        m = st.columns(4)
        m[0].metric("Average", f"{avg:.1f}")
        m[1].metric("Last 5", f"{l5:.1f}", delta=f"{l5 - avg:+.1f} vs avg")
        m[2].metric("Last 10", f"{l10:.1f}", delta=f"{l10 - avg:+.1f} vs avg")
        m[3].metric("Minutes (L5)", f"{m_l5:.1f}", delta=f"{m_l5 - m_avg:+.1f} vs avg")

    with st.container(border=True):
        st.subheader(f"Quick hit-rate strip: {sel.stat.label} over {sel.line:g}")
        all_label = "Season" if len(sel.seasons) == 1 else "All games"
        tiles = [("Last 5", vals.tail(5)), ("Last 10", vals.tail(10)), ("Last 20", vals.tail(20)),
                 (all_label, vals),
                 ("Home", g.loc[g["venue"] == "Home", col]), ("Away", g.loc[g["venue"] == "Away", col])]
        st.markdown('<div class="hit-grid">' + "".join(_hit_tile(l, v, sel.line) for l, v in tiles) + "</div>",
                    unsafe_allow_html=True)
        k, side = _streak(vals, sel.line)
        if k >= 2:
            color = OVER_COLOR if side == OVER else UNDER_COLOR
            st.markdown(f'<div class="streak">Went <b style="color:{color}">{side}</b> in each of the '
                        f'last <b>{k}</b> games.</div>', unsafe_allow_html=True)
        st.caption("Overs out of decided games (pushes shown as P and excluded). This strip uses all of the "
                   "player's games in the selected seasons; the opponent, home/away and recent-games "
                   "filters apply to everything below.")


def extras(sel: Selection) -> None:
    d = sel.window
    col, label, line = sel.stat.col, sel.stat.label, sel.line
    t1, t2, t3 = st.tabs(["📊 Distribution", "📈 Trends", "🧩 Matchup"])
    with t1, st.container(border=True):
        st.caption("Shows volatility and where outcomes cluster.")
        if len(d) < 8:
            st.info(f"Only {len(d)} games in this view. This chart gets useful around 8 or more; try a longer window.")
        else:
            counts = d[col].round(0).astype(int).value_counts().sort_index()
            colors = [OVER_COLOR if v > line else UNDER_COLOR if v < line else LINE_COLOR for v in counts.index]
            fig = go.Figure(go.Bar(x=counts.index, y=counts.values, marker_color=colors,
                                   hovertemplate=f"{label} %{{x}}: %{{y}} game(s)<extra></extra>"))
            fig.add_vline(x=line, line_dash="dash", line_color=LINE_COLOR, line_width=2,
                          annotation_text=f"Line {line:g}", annotation_position="top")
            fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), xaxis_title=label, yaxis_title="Games",
                              bargap=0.15, showlegend=False)
            fig.update_yaxes(dtick=1, rangemode="tozero")
            show_chart(fig)
    with t2:
        with st.container(border=True):
            st.subheader("Trend summary")
            st.markdown(trend_sentence(sel.player_name, label, d[col]))
        with st.container(border=True):
            st.subheader("Rolling average (5-game)")
            roll = d[col].rolling(5, min_periods=1).mean()
            fig = go.Figure()
            fig.add_scatter(x=d["game_date"], y=d[col], mode="lines+markers", name=label)
            fig.add_scatter(x=d["game_date"], y=roll, mode="lines", name="Rolling avg (5)")
            fig.add_hline(y=line, line_dash="dash", annotation_text=f"Line: {line:g}", annotation_position="top left")
            fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), xaxis_title="Date", yaxis_title=label)
            show_chart(fig)
    with t3:
        with st.container(border=True):
            st.subheader("Opponent split (in this view)")
            st.dataframe(d.groupby("opponent")[col].agg(games="count", avg="mean", median="median")
                         .sort_values(["games", "avg"], ascending=False), width="stretch")
        with st.container(border=True):
            st.subheader("Home vs away (in this view)")
            st.dataframe(d.groupby("venue")[col].agg(games="count", avg="mean", median="median"), width="stretch")


# ---------------------------------------------------------------- page

with st.sidebar:
    st.markdown("### 🏀 NBA options")
    if st.button("Reload stored data", key="btn_nba_reload",
                 help="Re-reads the stored files. New games come from `python -m refresh.nba`."):
        st.cache_data.clear()
        st.rerun()
    show_raw = st.toggle("Show raw table", key="nba_show_raw")

files = nba.available_files()
order = sorted({s for s, _, _ in files})
try:
    sel = render_analysis(VIEW, order, load, header=header, extras=extras)
except Exception as e:  # noqa: BLE001 - keep the rest of the app alive
    st.error(f"The NBA section hit an error and couldn't render: {e}")
    sel = None

if sel is not None and show_raw:
    with st.container(border=True):
        st.subheader("Raw data (debug)")
        st.dataframe(sel.player_games.head(200), width="stretch", hide_index=True)

st.markdown("---")
data_status("nba", sel.pool if sel is not None else None,
            "stats.nba.com player game logs via nba_api (stored snapshots in data/)")
