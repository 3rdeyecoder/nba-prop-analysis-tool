"""🚨 Upset Watch: model vs. the standings for each sport: upcoming games, any matchup, and the public record.
The model's opinion, for fun; never betting advice."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from core.ui import viewer_timezone
from matchup import nba_live, registry, track, upset

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
.uw-game.live { border: 2px solid #d97706; background: rgba(245, 158, 11, 0.07); }
.uw-badge { background: #ea580c; color: #fff; border-radius: 999px; padding: 1px 9px; font-weight: 800;
  font-size: 0.72rem !important; opacity: 1; }
.uw-badge.live { background: #fde68a; color: #78350f; }
.uw-why { font-size: 0.82rem !important; font-weight: 600; margin-top: 4px; }
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
.uw-call.flag.live { background: rgba(245, 158, 11, 0.12); border-left-color: #d97706; }
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


@st.cache_resource(show_spinner=False, max_entries=8)
def _module(sport: str, mtimes: tuple):
    """The sport's live module (model + snapshot); reloaded whenever one of its files changes."""
    return registry.available()[sport]()


@st.cache_data(show_spinner=False, max_entries=8)
def _log(path_str: str, mtime: float) -> pd.DataFrame:
    return track.load(Path(path_str))


def _mtime(p) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


def _img(url) -> str:
    return f'<img src="{url}" alt="">' if url else ""


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
    if chk.kind == upset.ALERT:
        return (f'<div class="uw-call flag">🚨 <b>Upset alert:</b> {msg} ({chk.edge*100:+.0f} points), '
                f'so the model picks <b>{chk.underdog}</b> to win.</div>')
    if chk.kind == upset.LIVE:
        return (f'<div class="uw-call flag live">👀 <b>Live underdog:</b> {msg} ({chk.edge*100:+.0f} points). '
                f'The model still favors <b>{chk.favorite}</b>, but this one is closer than the standings say.</div>')
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
if registry.COMING_SOON:
    c2.caption(f"{' and '.join(registry.COMING_SOON)} coming soon.")

cls = sports[sport]
paths = (cls.model_path(),) + tuple(cls.state_paths()) + (track.log_path(sport),)
mod = _module(sport, tuple(_mtime(p) for p in paths))
if not mod.ready:
    st.info(f"{sport} Upset Watch isn't set up yet. Train the model (`python -m refresh.train_{sport.lower()}`), "
            "run `python -m refresh.upsets`, and commit the `data/` folder.")
    st.stop()
state = mod.state
as_of = pd.Timestamp(state["as_of"].iloc[0]).date()
through = pd.Timestamp(state["data_through"].iloc[0]).date()
today = nba_live.today_et()
tz = viewer_timezone()
weekly = mod.unit == "week"

st.session_state.setdefault("uw_threshold", int(upset.DEFAULT_THRESHOLD * 100))
threshold = st.slider("Upset Watch threshold (points above the on-paper chance)", 3, 15, key="uw_threshold",
                      help="Highlights games where the model gives the on-paper underdog at least this many "
                           "points more. The public record always uses the official +5.") / 100

# ---------------------------------------------------------------- upcoming games
log = _log(str(mod.log_path), _mtime(mod.log_path))
slate = mod.slate(today)
title = f"{mod.slate_title} · {today:%A, %B} {today.day}" if not weekly else \
    f"{mod.slate_title} · {today:%b} {today.day} to {(today + pd.Timedelta(days=6)):%b} {(today + pd.Timedelta(days=6)).day}"
st.subheader(title)
locked = log.set_index("game_id") if not log.empty else log
calls = []                                    # (home, away, p_home, paper_home, start, locked?)
for g in slate.itertuples():
    if g.game_id in locked.index:
        r = locked.loc[g.game_id]
        calls.append((g.home, g.away, float(r["home_model_prob"]), float(r["home_paper_prob"]), g.start_utc, True))
    elif as_of == today and pd.Timestamp(g.start_utc) > pd.Timestamp.now(tz="UTC"):
        c = mod.predict(g.home, g.away, None if g.neutral else g.home, pd.Timestamp(g.start_utc).tz_convert(nba_live.ET).date(),
                        threshold)
        calls.append((g.home, g.away, c.p_a, c.paper_a, g.start_utc, False))
if calls:
    lock_word = "kickoff" if weekly else "tip-off"
    st.caption(f"🔒 Locked in on game day before {lock_word}, from games through {through:%b} {through.day}; "
               "saved once and never changed." + (" Games later this week are a preview until their game day."
                                                   if weekly else ""))
else:
    st.info(f"No {sport} games {'this week' if weekly else 'tonight'}, or today's predictions haven't been made yet. "
            "They're locked in each morning.")


def _open(home, away):
    st.session_state[f"uw_a_{sport}"], st.session_state[f"uw_b_{sport}"] = away, home
    st.session_state[f"uw_home_{sport}"] = "B"


with st.container(horizontal=True, gap="small"):
    for i, (home, away, p_home, paper_home, start, is_locked) in enumerate(calls):
        try:
            chk = upset.check(home, away, paper_home, p_home, threshold)
        except ValueError:
            chk = None
        kind = chk.kind if chk else None
        t = pd.Timestamp(start).tz_convert(tz)
        when = t.strftime("%a %I:%M %p").replace(" 0", " ") if weekly else t.strftime("%I:%M %p").lstrip("0")
        when += "" if is_locked else " · preview"
        card = {upset.ALERT: " flag", upset.LIVE: " live"}.get(kind, "")
        badge = (f'<span class="uw-badge{" live" if kind == upset.LIVE else ""}">'
                 f'{upset.KIND_LABELS[kind].upper()}</span>') if kind else ""
        why = f'<div class="uw-why">{chk.explain()}</div>' if kind else ""
        with st.container(width=300, key=f"uw_game_{sport}_{i}"):
            st.markdown(
                f'<div class="uw-game{card}"><div class="uw-head">'
                f'<span>{when}</span>{badge}</div>'
                f'<div class="uw-teams">{_img(mod.logo(away))}{away}'
                f'<span style="opacity:.5">@</span>{_img(mod.logo(home))}{home}</div>'
                f'{win_bar(away, home, 1 - p_home)}'
                f'<div class="uw-paper">On paper: {away} {(1-paper_home)*100:.0f}% · {home} {paper_home*100:.0f}%</div>'
                f"{why}</div>", unsafe_allow_html=True)
            st.button("Open matchup ↓", key=f"uw_open_{sport}_{i}", on_click=_open, args=(home, away), width="stretch")

# ---------------------------------------------------------------- compare any two teams
st.subheader("Compare any two teams")
teams = list(state.sort_values("team_name")["team"])
names = dict(zip(state["team"], state["team_name"]))
ka, kb, kh = f"uw_a_{sport}", f"uw_b_{sport}", f"uw_home_{sport}"
if calls and ka not in st.session_state:
    _open(calls[0][0], calls[0][1])
st.session_state.setdefault(ka, teams[0])
st.session_state.setdefault(kb, teams[1])
st.session_state.setdefault(kh, "B")
c1, c2, c3 = st.columns([1.2, 1.2, 1])
a = c1.selectbox("Team A", teams, key=ka, format_func=lambda t: names.get(t, t))
b = c2.selectbox("Team B", teams, key=kb, format_func=lambda t: names.get(t, t))
venue = c3.radio(mod.home_word.capitalize(), ["A", "B", "Neutral"], key=kh, horizontal=True,
                 format_func=lambda v: {"A": a, "B": b, "Neutral": "Neutral"}[v])
if a == b:
    st.warning("Pick two different teams.")
    st.stop()
home = {"A": a, "B": b, "Neutral": None}[venue]
call = mod.predict(a, b, home, today, threshold)

with st.container(border=True):
    st.markdown(f'<div class="uw-teams" style="font-size:1.3rem">{_img(mod.logo(a))}{names[a]}'
                f'<span style="opacity:.5;margin:0 6px">vs</span>{_img(mod.logo(b))}{names[b]}</div>'
                f'{win_bar(a, b, call.p_a)}'
                f'<div class="uw-paper">On paper (records + {mod.home_word}): {a} {mod.record(a)}, '
                f'{call.paper_a*100:.0f}% · {b} {mod.record(b)}, {(1-call.paper_a)*100:.0f}%</div>',
                unsafe_allow_html=True)
    st.markdown(call_box(call.check, threshold), unsafe_allow_html=True)
    why = mod.reasons(call, today)
    if why:
        st.markdown("**Why the model leans this way**")
        for r in why:
            st.markdown(f"- **{r['factor']}** favors **{r['favors']}** (about {r['points']:.0f} points): {r['fact']}")
    st.caption(f"Team numbers as of {as_of:%b} {as_of.day}, using games through {through:%b} {through.day}. "
               "Rest is counted from today." + (" Quarterbacks are the listed starters for each team's next game."
                                               if weekly else ""))

with st.expander("Full side-by-side comparison", expanded=False):
    st.markdown(stats_table(mod.get_matchup_stats(a, b, today), a, b), unsafe_allow_html=True)
    h = mod.head_to_head(a, b, today)
    if h["games"]:
        recent = " · ".join(f"{d} {a} {pf}-{pa} ({w})" for d, pf, pa, w in h["recent"])
        st.markdown(f"**Head-to-head, {mod.h2h_label}:** {a} {h['a_wins']}-{h['b_wins']}, "
                    f"average margin {h['avg_margin_a']:+.1f} for {a}.  \nRecent: {recent}")
    else:
        st.markdown(f"**Head-to-head:** no meetings in the {mod.h2h_label}.")
    if sport == "NFL":
        st.caption("NFL data: nflverse (CC-BY 4.0).")

# ---------------------------------------------------------------- the record
st.subheader("The record")
s = track.summary(log)
row = s[s["sport"] == sport]
if row.empty or int(row["settled"].iloc[0]) == 0:
    st.info(f"The live {sport} record starts with the first locked-in flags. Results appear the morning "
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
        "Type": [upset.KIND_LABELS[upset.kind_of(p, True)] for p in recent["model_prob"]],
        "Underdog": recent["underdog"] + " (" + recent["underdog_record"].fillna("") + ")",
        "On paper": (recent["paper_prob"] * 100).round(0).astype(int).astype(str) + "%",
        "Model": (recent["model_prob"] * 100).round(0).astype(int).astype(str) + "%",
        "Result": recent["result"].fillna("pending"),
    }), hide_index=True, width="stretch")

if mod.report_path.exists():
    rep = json.loads(mod.report_path.read_text())
    five = next((x for x in rep.get("upset_watch", []) if abs(x["threshold"] - 0.05) < 1e-9), None)
    if five:
        st.caption(f"Backtest (not live): on {len(rep['held_out_seasons'])} past seasons the model never saw, "
                   f"+5 flags came about {five['per_night']:.1f} per {mod.unit}, and those underdogs won "
                   f"{five['upset_rate']*100:.1f}% vs {five['expected_on_paper']*100:.1f}% expected on paper. "
                   "'On paper' is an easy benchmark; the live record above is the real test.")
st.caption(DISCLAIMER)
