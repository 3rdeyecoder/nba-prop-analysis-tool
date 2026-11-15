"""🚨 Upset Watch: model vs. the standings, tonight's games, any matchup, and the public record.
The model's opinion, for fun; never betting advice."""
import json

import pandas as pd
import streamlit as st

from core.cards import LOGO
from core.ui import viewer_timezone
from matchup import nba_live, registry, track, upset
from sports import nba_matchup as m
from sports import nba_model as nm

CSS = """
<style>
.uw-banner { background: linear-gradient(135deg, #b91c1c 0%, #ea580c 55%, #f59e0b 100%); color: #fff;
  border-radius: 16px; padding: 18px 22px; margin: 4px 0 10px; box-shadow: 0 6px 22px rgba(234, 88, 12, 0.25); }
.uw-banner .uw-title { font-size: 1.9rem !important; font-weight: 800; line-height: 1.15; color: #fff; }
.uw-banner .uw-tag { font-size: 0.95rem; opacity: 0.94; margin-top: 4px; color: #fff; }
.uw-game { border: 1px solid rgba(128,128,128,0.25); border-radius: 14px; padding: 12px 14px; margin-bottom: 6px; }
.uw-game.flag { border: 2px solid #ea580c; background: rgba(234, 88, 12, 0.06); }
.uw-head { display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem !important;
  opacity: 0.75; margin-bottom: 6px; }
.uw-badge { background: #ea580c; color: #fff; border-radius: 999px; padding: 1px 9px; font-weight: 800;
  font-size: 0.72rem !important; opacity: 1; }
.uw-teams { display: flex; align-items: center; gap: 8px; font-weight: 800; font-size: 1.05rem !important; }
.uw-teams img { width: 26px; height: 26px; }
.uw-pcts { display: flex; justify-content: space-between; margin-top: 8px; font-weight: 800;
  font-size: 0.95rem !important; font-variant-numeric: tabular-nums; }
.uw-pcts .a { color: #6d28d9; }
.uw-pcts .b { color: #64748b; }
.uw-bar { display: flex; height: 12px; border-radius: 999px; overflow: hidden; margin: 4px 0 6px; }
.uw-bar .a { background: #6d28d9; }
.uw-bar .b { background: #94a3b8; }
.uw-paper { font-size: 0.82rem !important; opacity: 0.8; }
.uw-call { border-radius: 12px; padding: 12px 16px; margin: 8px 0; font-size: 1rem !important; }
.uw-call.flag { background: rgba(234, 88, 12, 0.12); border-left: 5px solid #ea580c; }
.uw-call.calm { background: rgba(128, 128, 128, 0.08); border-left: 5px solid rgba(128,128,128,0.5); }
.uw-table { width: 100%; border-collapse: collapse; font-size: 0.92rem !important; }
.uw-table td, .uw-table th { padding: 5px 8px; border-bottom: 1px solid rgba(128,128,128,0.18); }
.uw-table th { text-align: left; font-size: 0.8rem !important; opacity: 0.7; text-transform: uppercase; }
.uw-table td.v { text-align: right; font-variant-numeric: tabular-nums; width: 22%; }
.uw-table td.best { font-weight: 800; color: #6d28d9; }
.uw-table tr.sec td { font-weight: 800; padding-top: 12px; opacity: 0.85; border-bottom: none; }
.uw-note { font-size: 0.78rem !important; opacity: 0.65; }
@media (prefers-color-scheme: dark) {
  .uw-pcts .a, .uw-table td.best { color: #a78bfa; }
  .uw-pcts .b { color: #cbd5e1; }
}
</style>
"""

DISCLAIMER = ("Upset Watch is our model's opinion, for fun. Win chances describe uncertainty, not "
              "guarantees, and nothing here is betting advice.")


@st.cache_data(show_spinner=False, max_entries=4)
def _model(mtime: float) -> dict | None:
    return nm.load_model()


@st.cache_data(show_spinner=False, max_entries=4)
def _snapshot(mtime_state: float, mtime_games: float):
    return nba_live.load_snapshot()


@st.cache_data(show_spinner=False, max_entries=4)
def _log(mtime: float) -> pd.DataFrame:
    return track.load(track.log_path("NBA"))


def _mtime(p) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


def _logo(team_id) -> str:
    return f'<img src="{LOGO.format(int(team_id))}" alt="">' if team_id is not None and pd.notna(team_id) else ""


def win_bar(a: str, b: str, p_a: float) -> str:
    """Percentages on a row above a slim bar, so a small side's label is never cut off."""
    return (f'<div class="uw-pcts"><span class="a">{a} {p_a*100:.0f}%</span>'
            f'<span class="b">{(1-p_a)*100:.0f}% {b}</span></div>'
            f'<div class="uw-bar"><div class="a" style="width:{p_a*100:.1f}%"></div>'
            f'<div class="b" style="width:{(1-p_a)*100:.1f}%"></div></div>')


def call_box(chk: upset.UpsetCheck | None, threshold: float) -> str:
    if chk is None:
        return '<div class="uw-call calm">Even on paper, so there is no underdog here.</div>'
    msg = (f"On paper, <b>{chk.underdog}</b> has a <b>{chk.paper_prob*100:.0f}%</b> chance. "
           f"Our model gives them <b>{chk.model_prob*100:.0f}%</b>")
    if chk.edge >= threshold - 1e-12:
        return f'<div class="uw-call flag">🚨 <b>Upset Watch:</b> {msg} ({chk.edge*100:+.0f} points).</div>'
    if chk.edge <= -threshold:
        return f'<div class="uw-call calm">{msg}. The model likes the favorite, <b>{chk.favorite}</b>, even more.</div>'
    return f'<div class="uw-call calm">{msg}. Close to what the standings say.</div>'


def stats_table(rows, a: str, b: str) -> str:
    html, sec = [f'<table class="uw-table"><tr><th>Stat</th><th style="text-align:right">{a}</th>'
                 f'<th style="text-align:right">{b}</th></tr>'], None
    for r in rows:
        if r.section != sec:
            sec = r.section
            html.append(f'<tr class="sec"><td colspan="3">{sec}</td></tr>')

        def cell(v, side):
            txt = "—" if v is None or (not isinstance(v, str) and pd.isna(v)) else r.fmt.format(v)
            return f'<td class="v{" best" if r.better == side else ""}">{txt}</td>'
        note = f'<div class="uw-note">{r.note}</div>' if r.note else ""
        html.append(f"<tr><td>{r.label}{note}</td>{cell(r.a, 'a')}{cell(r.b, 'b')}</tr>")
    return "".join(html) + "</table>"


# ---------------------------------------------------------------- page

st.markdown(CSS, unsafe_allow_html=True)
st.markdown('<div class="uw-banner"><div class="uw-title">🚨 Upset Watch</div>'
            '<div class="uw-tag">Our model vs. the standings · Any matchup, side by side · For fun, never '
            'betting advice</div></div>', unsafe_allow_html=True)

sports = registry.available()
c1, c2 = st.columns([1, 2], vertical_alignment="center")
st.session_state.setdefault("uw_sport", "NBA")
sport = c1.segmented_control("Sport", list(sports), key="uw_sport", label_visibility="collapsed") or "NBA"
c2.caption(f"{' and '.join(registry.COMING_SOON)} coming soon.")

model = _model(_mtime(nm.MODEL_PATH))
snap = _snapshot(_mtime(nba_live.STATE_PATH), _mtime(nba_live.GAMES_PATH))
if model is None or snap is None:
    st.info("Upset Watch isn't set up yet. Run `python -m refresh.train_nba` and then "
            "`python -m refresh.upsets`, and commit the `data/` folder.")
    st.stop()
state, tg = snap
as_of = pd.Timestamp(state["as_of"].iloc[0]).date()
through = pd.Timestamp(state["data_through"].iloc[0]).date()
today = nba_live.today_et()
tz = viewer_timezone()

st.session_state.setdefault("uw_threshold", int(upset.DEFAULT_THRESHOLD * 100))
threshold = st.slider("Upset Watch threshold (points above the on-paper chance)", 3, 15, key="uw_threshold",
                      help="Highlights games where the model gives the on-paper underdog at least this many "
                           "points more. The public record always uses the official +5.") / 100

# ---------------------------------------------------------------- tonight
log = _log(_mtime(track.log_path("NBA")))
locked = log[log["game_date"] == today.isoformat()]
st.subheader(f"Tonight · {today:%A, %B} {today.day}")
if not locked.empty:
    st.caption(f"Locked in before tip-off from games through {through:%b} {through.day}. "
               "Predictions are saved once and never changed.")
    games = locked.sort_values("start_utc")
    calls = [(g.home, g.away, float(g.home_model_prob), float(g.home_paper_prob), g.start_utc) for g in games.itertuples()]
elif as_of == today:
    sched = nba_live.todays_games(today)
    calls = []
    for g in sched.itertuples():
        if g.home in state.index and g.away in state.index:
            c = nba_live.predict(model, state, tg, g.home, g.away, g.home, today, threshold)
            calls.append((g.home, g.away, c.p_a, c.paper_a, pd.Timestamp(g.start_utc).isoformat()))
    if calls:
        st.caption("Preview: today's predictions get locked in by the morning job.")
else:
    calls = []
if not calls:
    st.info("No NBA games tonight, or today's predictions haven't been made yet. They're locked in each morning.")


def _open(home, away):
    st.session_state["uw_a"], st.session_state["uw_b"], st.session_state["uw_home"] = away, home, "B"


with st.container(horizontal=True, gap="small"):
    for i, (home, away, p_home, paper_home, start) in enumerate(calls):
        try:
            chk = upset.check(home, away, paper_home, p_home, threshold)
        except ValueError:
            chk = None
        flagged = bool(chk and chk.flagged)
        t = pd.Timestamp(start).tz_convert(tz)
        with st.container(width=300, key=f"uw_game_{i}"):
            st.markdown(
                f'<div class="uw-game{" flag" if flagged else ""}"><div class="uw-head">'
                f'<span>{t.strftime("%I:%M %p").lstrip("0")}</span>'
                f'{"<span class=uw-badge>🚨 UPSET WATCH</span>" if flagged else ""}</div>'
                f'<div class="uw-teams">{_logo(state.loc[away, "team_id"])}{away}'
                f'<span style="opacity:.5">@</span>{_logo(state.loc[home, "team_id"])}{home}</div>'
                f'{win_bar(away, home, 1 - p_home)}'
                f'<div class="uw-paper">On paper: {away} {(1-paper_home)*100:.0f}% · {home} {paper_home*100:.0f}%</div>'
                "</div>", unsafe_allow_html=True)
            st.button("Open matchup ↓", key=f"uw_open_{i}", on_click=_open, args=(home, away), width="stretch")

# ---------------------------------------------------------------- compare any two teams
st.subheader("Compare any two teams")
teams = list(state.sort_values("team_name")["team"])
names = dict(zip(state["team"], state["team_name"]))
if calls and "uw_a" not in st.session_state:
    _open(calls[0][0], calls[0][1])
st.session_state.setdefault("uw_a", teams[0])
st.session_state.setdefault("uw_b", teams[1])
st.session_state.setdefault("uw_home", "B")
c1, c2, c3 = st.columns([1.2, 1.2, 1])
a = c1.selectbox("Team A", teams, key="uw_a", format_func=lambda t: names.get(t, t))
b = c2.selectbox("Team B", teams, key="uw_b", format_func=lambda t: names.get(t, t))
venue = c3.radio("Home court", ["A", "B", "Neutral"], key="uw_home", horizontal=True,
                 format_func=lambda v: {"A": a, "B": b, "Neutral": "Neutral"}[v])
if a == b:
    st.warning("Pick two different teams.")
    st.stop()
home = {"A": a, "B": b, "Neutral": None}[venue]
call = nba_live.predict(model, state, tg, a, b, home, today, threshold)

with st.container(border=True):
    st.markdown(f'<div class="uw-teams" style="font-size:1.3rem">{_logo(state.loc[a, "team_id"])}{names[a]}'
                f'<span style="opacity:.5;margin:0 6px">vs</span>{_logo(state.loc[b, "team_id"])}{names[b]}</div>'
                f'{win_bar(a, b, call.p_a)}'
                f'<div class="uw-paper">On paper (records + home court): {a} {call.paper_a*100:.0f}% · '
                f'{b} {(1-call.paper_a)*100:.0f}%</div>', unsafe_allow_html=True)
    st.markdown(call_box(call.check, threshold), unsafe_allow_html=True)
    why = nba_live.reasons(call, state, tg, today)
    if why:
        st.markdown("**Why the model leans this way**")
        for r in why:
            st.markdown(f"- **{r['factor']}** favors **{r['favors']}** (about {r['points']:.0f} points): {r['fact']}")
    st.caption(f"Team numbers as of {as_of:%b} {as_of.day}, using games through {through:%b} {through.day}. "
               "Rest is counted from today.")

with st.expander("Full side-by-side comparison", expanded=False):
    mod = sports[sport](model=model, snapshot=snap)
    st.markdown(stats_table(mod.get_matchup_stats(a, b, today), a, b), unsafe_allow_html=True)
    h = m.head_to_head(tg, a, b, pd.Timestamp(today))
    if h["games"]:
        recent = " · ".join(f"{d} {a} {pf}-{pa} ({w})" for d, pf, pa, w in h["recent"])
        st.markdown(f"**Head-to-head, last {nba_live.H2H_SEASONS} seasons:** {a} {h['a_wins']}-{h['b_wins']}, "
                    f"average margin {h['avg_margin_a']:+.1f} for {a}.  \nRecent: {recent}")
    else:
        st.markdown(f"**Head-to-head:** no meetings in the last {nba_live.H2H_SEASONS} seasons.")

# ---------------------------------------------------------------- the record
st.subheader("The record")
s = track.summary(log)
row = s[s["sport"] == "NBA"]
if row.empty or int(row["settled"].iloc[0]) == 0:
    st.info("The live record starts with this season's first locked-in flags. Results appear the morning "
            "after each game, wins and misses alike.")
else:
    r = row.iloc[0]
    c = st.columns(3)
    c[0].metric("Upset Watch flags settled", f"{int(r['upsets'])} upsets in {int(r['settled'])}",
                f"{r['upset_rate']*100:.0f}% won", delta_color="off")
    c[1].metric("Expected on paper", f"{r['expected_on_paper']*100:.0f}%")
    c[2].metric("Model expected", f"{r['expected_by_model']*100:.0f}%")
    st.caption(f"Every game graded so far: the model picked {int(r['model_correct'])} of {int(r['games_graded'])} "
               f"winners; 'on paper' picked {int(r['paper_correct'])}.")
    recent = log[log["flagged"]].sort_values("start_utc", ascending=False).head(15)
    st.dataframe(pd.DataFrame({
        "Date": recent["game_date"], "Game": recent["away"] + " @ " + recent["home"],
        "Underdog": recent["underdog"] + " (" + recent["underdog_record"].fillna("") + ")",
        "On paper": (recent["paper_prob"] * 100).round(0).astype(int).astype(str) + "%",
        "Model": (recent["model_prob"] * 100).round(0).astype(int).astype(str) + "%",
        "Result": recent["result"].fillna("pending"),
    }), hide_index=True, width="stretch")

report_path = nm.MODEL_PATH.with_name("nba_report.json")
if report_path.exists():
    rep = json.loads(report_path.read_text())
    five = next((x for x in rep.get("upset_watch", []) if abs(x["threshold"] - 0.05) < 1e-9), None)
    if five:
        st.caption(f"Backtest (not live): on {len(rep['held_out_seasons'])} past seasons the model never saw, "
                   f"+5 flags came about {five['per_night']:.1f} per game night, and those underdogs won "
                   f"{five['upset_rate']*100:.1f}% vs {five['expected_on_paper']*100:.1f}% expected on paper. "
                   "'On paper' is an easy benchmark; the live record above is the real test.")
st.caption(DISCLAIMER)
