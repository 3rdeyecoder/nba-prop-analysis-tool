"""🎯 Call It: a daily over/under puzzle from real past NBA games (2019-20 to today)."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import cards as card_ui
from core import links
from core.analytics import track_event
from core.config import APP_URL, LINE_COLOR, OVER_COLOR, UNDER_COLOR
from core.ui import show_chart
from sports import callit, nba

HEADSHOT = "https://cdn.nba.com/headshots/nba/latest/260x190/{}.png"
CSS = """
<style>
.ci-head { display: flex; gap: 14px; align-items: center; }
.ci-head img { height: 74px; border-radius: 12px; background: rgba(107,138,253,0.15); }
.ci-name { font-size: 1.35rem !important; font-weight: 800; line-height: 1.2; }
.ci-sub { opacity: 0.75; font-size: 0.92rem; }
.ci-season { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.82rem; font-weight: 800;
  color: #fff; background: linear-gradient(135deg, #7c3aed 0%, #db2777 100%); letter-spacing: 0.02em;
  box-shadow: 0 1px 6px rgba(219, 39, 119, 0.3); margin-right: 6px; white-space: nowrap; }
.ci-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 0; margin-top: 4px; }
.ci-q { font-size: 1.15rem !important; font-weight: 700; margin: 4px 0 2px; }
.ci-dots { font-size: 1.4rem; letter-spacing: 4px; }
.ci-big { font-size: 1.6rem !important; font-weight: 800; }
.ci-banner { background: linear-gradient(135deg, #7c3aed 0%, #db2777 100%); color: #fff; border-radius: 16px;
  padding: 18px 22px; margin: 4px 0 10px; box-shadow: 0 6px 22px rgba(124, 58, 237, 0.25); }
.ci-banner .ci-title { font-size: 1.9rem !important; font-weight: 800; line-height: 1.15; color: #fff; }
.ci-banner .ci-tag { font-size: 0.95rem; opacity: 0.92; margin-top: 4px; color: #fff; }
.ci-score { text-align: center; padding: 22px 18px 18px; }
.ci-score .ci-num { font-size: 3.4rem !important; font-weight: 900; line-height: 1; color: #fff; }
.ci-score .ci-num span { font-size: 1.4rem !important; opacity: 0.8; }
.ci-score .ci-rank { font-size: 1.3rem !important; font-weight: 800; margin-top: 6px; color: #fff; }
.ci-score .ci-grid { font-size: 2rem; letter-spacing: 6px; margin-top: 8px; }
</style>
"""


@st.cache_data(show_spinner=False, max_entries=4)
def _data(paths: tuple) -> tuple[pd.DataFrame, pd.DataFrame]:
    from pathlib import Path
    df = pd.concat([nba.load_file(Path(p), s, "Regular Season") for s, p, _ in paths], ignore_index=True)
    return df, callit.build_pool(df)


def _when(r: dict) -> str:
    d = r["game_date"]
    where = "vs" if r["venue"] == "Home" else "@"
    return f"{r['team']} {where} {r['opponent']} · {d:%B} {d.day}, {d:%Y}"


def _season(r: dict) -> str:
    """The season as a highlighted badge, e.g. [2019-20 season]."""
    return f'<span class="ci-season">{r["season"]} season</span>'


def _meta(r: dict) -> str:
    return f'<div class="ci-meta">{_season(r)}<span class="ci-sub">{_when(r)}</span></div>'



def _chart(prior: pd.DataFrame, r: dict) -> None:
    vals = prior[r["stat"]]
    colors = [OVER_COLOR if v > r["line"] else UNDER_COLOR for v in vals]
    labels = [f"{d:%b} {d.day}<br>{'vs' if v == 'Home' else '@'} {o}"
              for d, v, o in zip(prior["game_date"], prior["venue"], prior["opponent"])]
    fig = go.Figure(go.Bar(x=labels, y=vals, marker_color=colors, text=[f"{v:g}" for v in vals],
                           textposition="outside", cliponaxis=False,
                           hovertemplate="%{x}: %{y}<extra></extra>"))
    fig.add_hline(y=r["line"], line_dash="dash", line_color=LINE_COLOR, line_width=2,
                  annotation_text=f"Line {r['line']:g}", annotation_position="top left")
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10), showlegend=False,
                      xaxis=dict(type="category"), yaxis=dict(title=callit.LABEL[r["stat"]].capitalize(),
                                                              rangemode="tozero"))
    show_chart(fig)


def _analysis_link(r: dict) -> None:
    st.page_link("views/nba.py", label=f"See {r['player_name']}'s {r['season']} games →",
                 query_params=_link_params(r))


SCORE_TITLES = {5: "🔥 Perfect read!", 4: "🎯 Sharp eye", 3: "👍 Solid night", 2: "📉 Tough slate",
                1: "🥶 Cold night", 0: "🫣 Rough one"}


def _link_params(r: dict) -> dict:
    return links.build(sport="nba", player_id=r["player_id"], stat_col=r["stat"], seasons=[r["season"]],
                       season_type="Regular Season", window_label="All games", line=r["line"])


def recap_card(i: int, r: dict, pick: str) -> None:
    ok = pick == r["answer"]
    d = r["game_date"]
    where = "vs" if r["venue"] == "Home" else "@"
    team_line = (f'<div class="pc-vs">{r["team"]} {where} '
                 f'{card_ui.logo_img(r.get("opp_team_id"), cls="")}<b>{r["opponent"]}</b></div>')
    card_ui.player_card(
        f"ci_{i}", player_id=r["player_id"], name=r["player_name"], team=r["team"], team_id=r.get("team_id"),
        badge=f"{'✅' if ok else '❌'} Round {i + 1}", season=r["season"], tone="good" if ok else "bad",
        big=f"{r['actual']:g}", unit_label=callit.LABEL[r["stat"]],
        pill=f"You: {pick} {r['line']:g}", pill_kind="good" if ok else "bad",
        sub=f"Line {r['line']:g} → it went <b>{r['answer']}</b>",
        meta=f"{d:%b} {d.day}, {d:%Y}<br>{_box(r)}",
        link=_link_params(r), link_label=f"See {r['season']} games →", team_line=team_line)


def _box(r: dict) -> str:
    b = r["box"]
    return f"{b['PTS']:g} pts · {b['REB']:g} reb · {b['AST']:g} ast · {b['MIN']:g} min"


# ---------------------------------------------------------------- page

files = [(s, p) for s, t, p in nba.available_files() if t == "Regular Season"]
if not files:
    st.warning("No NBA data is stored yet. Run `python -m refresh.nba` to get started.")
    st.stop()

st.markdown(CSS, unsafe_allow_html=True)
today = datetime.now(ZoneInfo("America/New_York")).date()     # same puzzle for everyone
number = callit.puzzle_number(today)
with st.spinner("Setting up today's puzzle..."):
    df, pool = _data(tuple((s, str(p), p.stat().st_mtime) for s, p in files))
    rounds = callit.daily_rounds(pool, today)

state = st.session_state.setdefault("callit_state", {"puzzle": number, "picks": {}})
if state["puzzle"] != number:                                   # new day, new puzzle
    state.update(puzzle=number, picks={})
picks: dict[int, str] = state["picks"]
results = [picks[i] == rounds[i]["answer"] for i in range(len(rounds)) if i in picks]

st.markdown(f'<div class="ci-banner"><div class="ci-title">🎯 Call It #{number}</div>'
            f'<div class="ci-tag">The daily stats puzzle · 5 real games · Over or under?</div></div>',
            unsafe_allow_html=True)
st.caption(f"{today:%A, %B} {today.day}, {today:%Y} · 5 real NBA games from {files[0][0]} to today. "
           "You see each player's 10 games before that night. Call over or under the line, then see "
           "what happened. New puzzle every day at midnight Eastern.")
finished = bool(rounds) and len(picks) == len(rounds)
if not finished:                                                # the score banner shows the grid at the end
    dots = "".join("🟩" if ok else "🟥" for ok in results) + "⬜" * (len(rounds) - len(results))
    st.markdown(f'<div class="ci-dots">{dots}</div>', unsafe_allow_html=True)

for i, r in enumerate([] if finished else rounds):
    stat_label = callit.LABEL[r["stat"]]
    if i in picks:                                              # answered: show the result
        ok = picks[i] == r["answer"]
        latest = i == max(picks)
        with st.container(border=True):
            st.markdown(f"**Round {i + 1}: {r['player_name']}**{_meta(r)}", unsafe_allow_html=True)
            msg = (f"{'✅ Nice call!' if ok else '❌ Not this time.'} You said **{picks[i]} {r['line']:g}**. "
                   f"Actual: **{r['actual']:g} {stat_label}** → **{r['answer']}**")
            if latest:
                st.markdown(f'<div class="ci-big">{r["actual"]:g} {stat_label}</div>', unsafe_allow_html=True)
                (st.success if ok else st.error)(msg)
                st.caption(f"Full game: {_box(r)}")
                _analysis_link(r)
            else:
                st.markdown(msg)
        continue

    # the current round
    prior = callit.prior_games(df, r)
    with st.container(border=True):
        st.markdown(
            f'<div class="ci-head"><img src="{HEADSHOT.format(r["player_id"])}" alt="">'
            f'<div><div class="ci-name">Round {i + 1} of {len(rounds)} · {r["player_name"]}</div>'
            f'{_meta(r)}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="ci-q">Over or under {r["line"]:g} {stat_label}?</div>', unsafe_allow_html=True)
        vals = prior[r["stat"]]
        st.caption(f"The 10 games before this one: average {vals.mean():.1f}, median {vals.median():g}. "
                   f"{int((vals > r['line']).sum())} were over the line, {int((vals < r['line']).sum())} under.")
        _chart(prior, r)
        c1, c2 = st.columns(2)
        if c1.button(f"⬆️ Over {r['line']:g}", key=f"ci_{number}_{i}_over", width="stretch"):
            picks[i] = "Over"
            st.rerun()
        if c2.button(f"⬇️ Under {r['line']:g}", key=f"ci_{number}_{i}_under", width="stretch"):
            picks[i] = "Under"
            st.rerun()
    break

if picks and not finished:
    track_event("callit_start", {"puzzle_number": number}, once_key=f"callit_start_{number}")

if finished:
    score = sum(results)
    track_event("callit_complete", {"puzzle_number": number, "score": score, "perfect": score == len(rounds)},
                once_key=f"callit_complete_{number}")
    grid = "".join("🟩" if ok else "🟥" for ok in results)
    st.markdown(f'<div class="ci-banner ci-score"><div class="ci-num">{score}<span>/{len(rounds)}</span></div>'
                f'<div class="ci-rank">{SCORE_TITLES.get(score, "")}</div><div class="ci-grid">{grid}</div></div>',
                unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("**Share your score**")
        st.caption("Copy this and send it to friends. The squares don't give away the answers, so they can still play.")
        url = f"{APP_URL.rstrip('/')}/callit" if APP_URL else ""
        st.code(callit.share_text(number, results, url), language=None)
    st.subheader("Your recap")
    st.caption("Team, logo and season are from the night of each game. Photos are the player's current headshot.")
    card_ui.apply_css()
    with st.container(horizontal=True, gap="small"):
        for i, r in enumerate(rounds):
            recap_card(i, r, picks[i])
    st.caption(f"Come back tomorrow for Call It #{number + 1}.")

st.caption("Every game already happened: this is a stats-reading game, not a prediction or betting advice. "
           "The line is the median of the 10 games shown (about half above, half below).")
