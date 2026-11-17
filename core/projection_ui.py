"""Shared display for NBA Player Projections: tables, flags, Top 5 and the player pop-up.
Used by the Projections page and the NBA player page."""
import numpy as np
import pandas as pd
import streamlit as st

from matchup import nba_live
from matchup import projections_live as pl
from sports import nba_projections as pj

CSS = """
<style>
.pp-banner { background: linear-gradient(135deg, #0f766e 0%, #0891b2 55%, #6366f1 100%); color: #fff;
  border-radius: 16px; padding: 18px 22px; margin: 4px 0 10px; box-shadow: 0 6px 22px rgba(8, 145, 178, 0.25); }
.pp-banner .pp-title { font-size: 1.9rem !important; font-weight: 800; line-height: 1.15; color: #fff; }
.pp-banner .pp-tag { font-size: 0.95rem; opacity: 0.94; margin-top: 4px; color: #fff; }
.pp-team { display: flex; align-items: center; gap: 8px; font-weight: 800; font-size: 1.1rem !important; margin: 6px 0 2px; }
.pp-team img { width: 28px; height: 28px; }
.pp-stats { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; margin: 6px 0 4px; }
.pp-stats th { text-align: left; font-size: 0.78rem; opacity: 0.7; font-weight: 700; padding: 4px 6px;
  border-bottom: 1px solid rgba(128,128,128,0.3); }
.pp-stats td { padding: 6px; border-bottom: 1px solid rgba(128,128,128,0.15); font-size: 0.92rem; }
.pp-stats td.big { font-weight: 800; font-size: 1.05rem; }
.pp-up { color: #059669; font-weight: 800; }
.pp-down { color: #dc2626; font-weight: 800; }
.pp-note { font-size: 0.82rem !important; opacity: 0.8; }
.pp-flag { border: 1px solid rgba(128,128,128,0.25); border-radius: 14px; padding: 10px 14px; height: 100%; }
.pp-flag.up { border: 2px solid #059669; background: rgba(5, 150, 105, 0.06); }
.pp-flag.down { border: 2px solid #dc2626; background: rgba(220, 38, 38, 0.05); }
.pp-flag .who { font-weight: 800; font-size: 1rem !important; }
.pp-flag .what { font-size: 0.95rem !important; margin-top: 2px; }
.pp-flag .why { font-size: 0.82rem !important; opacity: 0.8; margin-top: 4px; }
.pp-flag .res { font-size: 0.85rem !important; font-weight: 700; margin-top: 4px; }
.pp-flagline { border-radius: 10px; padding: 10px 14px; margin: 6px 0; font-size: 0.95rem; }
.pp-flagline.up { background: rgba(5, 150, 105, 0.10); border-left: 4px solid #059669; }
.pp-flagline.down { background: rgba(220, 38, 38, 0.08); border-left: 4px solid #dc2626; }
div[class*="st-key-pp_flag_"] { position: relative; }
div[class*="st-key-pp_flag_"] [data-testid="stElementContainer"]:has(.stButton) {
  position: absolute; inset: 0; z-index: 3; margin: 0; width: 100% !important; height: 100% !important; }
div[class*="st-key-pp_flag_"] .stButton, div[class*="st-key-pp_flag_"] .stButton button {
  width: 100%; height: 100%; min-height: 0; }
div[class*="st-key-pp_flag_"] .stButton button { opacity: 0; cursor: pointer; }
div[class*="st-key-pp_flag_"] .pp-flag { transition: transform .12s ease, box-shadow .12s ease; }
div[class*="st-key-pp_flag_"]:hover .pp-flag { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0,0,0,.12); }
div[class*="st-key-pp_flag_"]:has(button:focus-visible) .pp-flag { outline: 3px solid #0891b2; outline-offset: 2px; }
.pp-warn { background: rgba(245, 158, 11, 0.12); border-left: 4px solid #d97706; border-radius: 8px;
  padding: 8px 12px; font-size: 0.9rem; margin: 6px 0; }
</style>
"""

DISCLAIMER = ("Projections are our model's opinion, for fun and research, never betting advice. Players who "
              "don't play are voided, not counted as misses. If you choose to bet, you must be 21+. "
              "Gambling problem? Call 1-800-GAMBLER.")
COLS = ["MIN", "PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV"]


@st.cache_data(show_spinner=False, max_entries=8)
def load_day(day_iso: str, mtime: float) -> pd.DataFrame:
    return pl.load_day(pd.Timestamp(day_iso).date())


def teams() -> dict:
    """team -> (full name, team id), from the Upset Watch snapshot (cached by file time)."""
    return _teams(mtime(nba_live.STATE_PATH))


@st.cache_data(show_spinner=False, max_entries=2)
def _teams(mtime: float) -> dict:
    snap = nba_live.load_snapshot()
    if snap is None:
        return {}
    s = snap[0]
    return {r.team: (r.team_name, int(r.team_id) if pd.notna(r.team_id) else None) for r in s.itertuples()}


def mtime(p) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


def logo(team: str) -> str:
    from core.cards import LOGO
    tid = teams().get(team, (team, None))[1]
    return f'<img src="{LOGO.format(tid)}" alt="">' if tid else ""


def _arrow(r, stat) -> str:
    f = r.get(f"flag_{stat}", "") if stat in pl.FLAG_STATS else ""
    f = "" if pd.isna(f) else f
    return {"up": ' <span class="pp-up">⬆️</span>', "down": ' <span class="pp-down">⬇️</span>'}.get(f, "")


def _fmt(x, stat) -> str:
    return f"{x:.0f}" if stat == "MIN" else f"{x:.1f}"


def team_frame(d: pd.DataFrame, graded: bool) -> pd.DataFrame:
    """Display table for one team: projection (and → actual once graded), with ⬆️/⬇️ flags."""
    out = {"Player": [r["player"] + (" ⚠️" if r["returning"] else "") for _, r in d.iterrows()]}
    for c in COLS:
        vals = []
        for _, r in d.iterrows():
            f = r.get(f"flag_{c}", "") if c in pl.FLAG_STATS else ""
            arrow = {"up": " ⬆️", "down": " ⬇️"}.get("" if pd.isna(f) else f, "")
            p = _fmt(r[f"p_{c}"], c)
            if graded and r["status"] == "graded":
                vals.append(f"{p} → {r[f'act_{c}']:.0f}{arrow}")
            elif graded and r["status"] == "dnp":
                vals.append("DNP" if c == "MIN" else "")
            else:
                vals.append(p + arrow)
        out[pj.SHORT[c]] = vals
    return pd.DataFrame(out)


def _pct(v) -> str:
    return "·" if pd.isna(v) or round(v * 100) == 0 else f"{v * 100:+.0f}%"


def _reason_facts(r) -> dict:
    opp = r["opp"]
    def rel(x):
        return f"{abs(x - 1) * 100:.0f}% {'more' if x > 1 else 'fewer'}"
    return {
        "Opponent": f"{opp} allows {rel(r['opp_def_PTS'])} points, {rel(r['opp_def_REB'])} rebounds and "
                    f"{rel(r['opp_def_AST'])} assists per possession than average.",
        "Pace": f"This game's expected pace is {abs(r['pace'] - 1) * 100:.0f}% "
                + ("faster than average (more possessions, more chances)." if r["pace"] > 1
                   else "slower than average (fewer possessions, fewer chances)."),
        "Teammates out": (f"Regulars who sat out {r['team']}'s last game usually play about "
                          f"{r['missing_share'] * 240:.0f} of the team's 240 minutes.") if r["missing_share"] > 0
        else "No regulars missed the team's last game.",
        "Home/away": "Home game." if r["home"] else "Road game.",
        "Rest": "Second night of a back-to-back." if r["rest"] <= 1 else f"{min(int(r['rest']), 7)} days since his last game.",
        "Back from absence": "He didn't play in the team's last game (could be limited, or still out)."
        if r["returning"] else "Played in the team's last game.",
        "Blowout risk": f"Team strength gap of {abs(r['mismatch']):.1f} net-rating points: lopsided games mean "
                        "fewer starter minutes." if abs(r["mismatch"]) >= 3 else "Evenly matched teams.",
    }


def drivers(r, stat: str) -> list[tuple[str, float, str]]:
    """(reason, % effect, plain-English why) for one stat, biggest first; includes recent form."""
    facts = _reason_facts(r)
    out = []
    ctx = 1.0
    for name in pj.CONTEXT:
        v = r.get(f"eff_{stat}_{name}", np.nan)
        if pd.notna(v):
            ctx *= 1 + v
            out.append((name, float(v), facts[name]))
    avg = r[f"avg_{stat}"]
    if avg > 0:
        out.append(("Recent form and role", float(r[f"p_{stat}"] / (avg * ctx) - 1),
                    f"His recent games compared with his season average (last 3 games: {r['min_l3']:.0f} minutes)."))
    return sorted([x for x in out if round(x[1] * 100) != 0], key=lambda x: -abs(x[1]))


def flag_sentence(r, stat: str) -> str:
    """'⬆️ Points: projected 11.1 vs his 6.8 season average (+63%), usually 6–16.'"""
    p, avg = r[f"p_{stat}"], r[f"avg_{stat}"]
    pct = (p / avg - 1) * 100 if avg else 0
    arrow = "⬆️" if pct > 0 else "⬇️"
    return (f"{arrow} <b>{pj.LABELS[stat]}</b>: projected <b>{p:.1f}</b> vs his {avg:.1f} season average "
            f"(<b>{pct:+.0f}%</b>), usually {np.floor(r[f'lo_{stat}']):.0f}–{np.ceil(r[f'hi_{stat}']):.0f}.")


def flag_result(r, stat: str) -> str:
    if r.get("status") == "dnp":
        return "Didn't play: voided."
    if r.get("status") != "graded":
        return ""
    act, avg, up = r[f"act_{stat}"], r[f"avg_{stat}"], r[f"flag_{stat}"] == "up"
    hit = act > avg if up else act < avg
    return f"{'✅' if hit else '❌'} Finished with {act:.0f} ({'above' if act > avg else 'below' if act < avg else 'at'} his average)."


def _flags(d: pd.DataFrame) -> pd.DataFrame:
    """One row per (player, stat) flag, biggest % difference first."""
    out = []
    for i, r in d.iterrows():
        for s in pl.FLAG_STATS:
            f = r.get(f"flag_{s}", "")
            if isinstance(f, str) and f in ("up", "down"):
                out.append({"i": i, "stat": s, "dir": f, "pct": r[f"p_{s}"] / r[f"avg_{s}"] - 1})
    return pd.DataFrame(out).sort_values("pct", key=lambda x: -x.abs()) if out else pd.DataFrame()


def chance_lines(r) -> list[str]:
    """'Points: 71% above his 22.4 average (projected 26.1)' for points, rebounds and assists."""
    out = []
    for s in pj.CHANCE_STATS:
        o, u = r.get(f"over_{s}", np.nan), r.get(f"under_{s}", np.nan)
        if pd.isna(o) or pd.isna(u):
            continue
        side, c = ("above", o) if o >= u else ("below", u)
        out.append(f"{pj.LABELS[s]}: **{c*100:.0f}%** chance {side} his {r[f'avg_{s}']:.1f} average "
                   f"(projected {r[f'p_{s}']:.1f})")
    return out


def pick_sentence(r, stat: str, direction: str, chance: float) -> str:
    return (f"{'⬆️' if direction == 'over' else '⬇️'} <b>{chance*100:.0f}%</b> chance of "
            f"{'more' if direction == 'over' else 'fewer'} than his <b>{r[f'avg_{stat}']:.1f}</b> "
            f"{pj.LABELS[stat].lower()} average · projected <b>{r[f'p_{stat}']:.1f}</b>")


def pick_result(r, stat: str, direction: str) -> str:
    hit = pl.pick_hit(r, stat, direction)
    if r.get("status") == "dnp":
        return "Didn't play: voided."
    if hit is None:
        return ""
    return f"{'✅' if hit else '❌'} Finished with {r[f'act_{stat}']:.0f}."


def _closed():
    """After the pop-up closes, redraw the tables fresh so the next tap (even on the same player) opens it."""
    st.session_state["pp_ver"] = st.session_state.get("pp_ver", 0) + 1


@st.dialog("Player projection", width="large", on_dismiss=_closed)
def player_dialog(r: pd.Series):
    player_detail(r)


def player_detail(r: pd.Series):
    """Everything about one player's projection (used in the pop-up and on the NBA player page)."""
    team_name = teams().get(r["team"], (r["team"], None))[0]
    st.markdown(f'<div class="pp-team">{logo(r["team"])}{r["player"]}'
                f'<span style="opacity:.55;font-weight:600">· {team_name} {"vs" if r["home"] else "@"} '
                f'{r["opp"]}</span></div>', unsafe_allow_html=True)
    if r["returning"]:
        st.markdown('<div class="pp-warn">⚠️ He didn\'t play in his team\'s last game. Check the injury report: '
                    "if he sits, this projection is voided.</div>", unsafe_allow_html=True)
    for s in pl.FLAG_STATS:
        f = r.get(f"flag_{s}", "")
        if isinstance(f, str) and f in ("up", "down"):
            top = drivers(r, s)[:2]
            why = "; ".join(f"{n.lower()} {v*100:+.0f}%" for n, v, _ in top)
            res = flag_result(r, s)
            st.markdown(f'<div class="pp-flagline {f}">{flag_sentence(r, s)}'
                        + (f"<br><span style='opacity:.8'>Biggest reasons: {why}.</span>" if why else "")
                        + (f"<br><b>{res}</b>" if res else "") + "</div>", unsafe_allow_html=True)
    chances = chance_lines(r)
    if chances:
        st.markdown("**Chance to finish above / below his season average**  \n" + "  \n".join(chances))
    rows = []
    for c in COLS:
        lo, hi = r[f"lo_{c}"], r[f"hi_{c}"]
        row = {"Stat": pj.LABELS[c], "Projection": _fmt(r[f"p_{c}"], c) + _arrow(r, c).replace(
                   '<span class="pp-up">', "").replace('<span class="pp-down">', "").replace("</span>", ""),
               "Typical range": f"{np.floor(lo):.0f}–{np.ceil(hi):.0f}",
               "Season avg": _fmt(r[f"avg_{c}"], c)}
        if r.get("status") == "graded":
            row["Actual"] = f"{r[f'act_{c}']:.0f}"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Typical range = the middle of his likely outcomes; it held about 6 or more nights in 10 on past "
               "seasons. ⬆️/⬇️ = projected 25%+ above/below his season average.")

    st.markdown("**What's moving his numbers tonight**")
    facts = _reason_facts(r)
    table = []
    for name in pj.CONTEXT:
        effs = {pj.SHORT[s]: r.get(f"eff_{s}_{name}", np.nan) for s in pl.REASON_STATS}
        if all(pd.isna(v) or abs(v) < 0.01 for v in effs.values()):
            continue
        table.append({"Reason": name, **{k: _pct(v) for k, v in effs.items()}, "Why": facts[name]})
    form = {}
    for s in pl.REASON_STATS:
        ctx = np.prod([1 + r.get(f"eff_{s}_{n}", 0) for n in pj.CONTEXT if pd.notna(r.get(f"eff_{s}_{n}", np.nan))])
        avg = r[f"avg_{s}"]
        form[pj.SHORT[s]] = (r[f"p_{s}"] / (avg * ctx) - 1) if avg > 0 else np.nan
    table.insert(0, {"Reason": "Recent form and role", **{k: _pct(v) for k, v in form.items()},
                     "Why": f"His recent games compared with his season average (last 3 games: "
                            f"{r['min_l3']:.0f} minutes a game)."})
    st.dataframe(pd.DataFrame(table).drop(columns="Why"), hide_index=True, width="stretch")
    st.markdown("\n".join(f"- **{t['Reason']}:** {t['Why']}" for t in table))
    st.caption("Each % is how much that reason moves the projection compared with a neutral setting "
               "(an average opponent and pace, nobody missing, normal rest).")


COMBOS = {"PRA": ["PTS", "REB", "AST"], "PR": ["PTS", "REB"], "PA": ["PTS", "AST"], "RA": ["REB", "AST"],
          "BLK_STL": ["BLK", "STL"]}


def expected(r, col: str, label: str) -> dict | None:
    """Expected value for the stat chosen on the player page: a projected stat, or a sum of them.
    None if we don't project it (shot attempts, free throws...)."""
    parts = COMBOS.get(col, [col])
    if any(f"p_{x}" not in r for x in parts):
        return None
    mu = float(sum(r[f"p_{x}"] for x in parts))
    avg = float(sum(r[f"avg_{x}"] for x in parts))
    if len(parts) == 1:
        lo, hi = float(r[f"lo_{col}"]), float(r[f"hi_{col}"])
    else:                                  # spread of a sum: add each stat's spread (squared)
        sd = float(np.sqrt(sum(((r[f"hi_{x}"] - r[f"p_{x}"]) / pj.RANGE_Z) ** 2 for x in parts)))
        lo, hi = max(mu - pj.RANGE_Z * sd, 0.0), mu + pj.RANGE_Z * sd
    act = float(sum(r[f"act_{x}"] for x in parts)) if r.get("status") == "graded" else None
    label = " + ".join(pj.LABELS[x].lower() for x in parts) if len(parts) > 1 else label.lower()
    out = {"label": label, "mu": mu, "avg": avg, "lo": lo, "hi": hi, "act": act, "chance": None}
    if col in pj.CHANCE_STATS:
        o, u = r.get(f"over_{col}", np.nan), r.get(f"under_{col}", np.nan)
        if pd.notna(o) and pd.notna(u):
            out["chance"] = ("above", float(o)) if o >= u else ("below", float(u))
    return out


def next_game(team: str, today) -> tuple | None:
    """(date, opponent, home?) of the team's next regular-season game from today on (US Eastern)."""
    from sports import nba
    files = sorted(nba.DATA_DIR.glob("nba_schedule_*.parquet"))
    if not files or not team:
        return None
    sch = pd.read_parquet(files[-1])
    sch = sch[sch["game_id"].astype(str).str.startswith("002") & ((sch["home"] == team) | (sch["away"] == team))].copy()
    sch["d"] = pd.to_datetime(sch["start_utc"], utc=True).dt.tz_convert(nba_live.ET).dt.date
    sch = sch[sch["d"] >= today].sort_values("d")
    if sch.empty:
        return None
    g = sch.iloc[0]
    return g["d"], (g["away"] if g["home"] == team else g["home"]), g["home"] == team


def _no_projection(team: str | None, today) -> None:
    """Explain why there's no projection, instead of showing nothing."""
    posted = pl.day_path(today).exists()
    ng = next_game(team, today) if team else None
    with st.container(border=True):
        st.markdown("**📈 Tonight's projection**")
        if ng and ng[0] == today and not posted:
            st.caption(f"{team} plays {'vs' if ng[2] else '@'} {ng[1]} tonight. Tonight's projections are posted "
                       "each morning (about 6:15 AM ET) and will show here.")
        elif ng and ng[0] == today:
            st.caption(f"{team} plays tonight, but he isn't projected: he hasn't played enough recent minutes, "
                       "or he hasn't played in his team's last 10 games.")
        elif ng:
            when = "tomorrow" if (ng[0] - today).days == 1 else f"{ng[0]:%A, %b} {ng[0].day}"
            st.caption(f"No game tonight. {team}'s next game is {when} {'vs' if ng[2] else '@'} {ng[1]}; "
                       "his projection is posted that morning (about 6:15 AM ET).")
        else:
            st.caption("No upcoming game on the schedule, so there's no projection right now.")


def player_panel(player_id, stat_col: str | None = None, stat_label: str | None = None,
                 team: str | None = None) -> None:
    """Tonight's projection box for one player (NBA player page). Shows last night's graded
    projection when tonight's aren't posted yet, otherwise says why there's none."""
    today = nba_live.today_et()
    days = [x for x in pl.all_days() if x <= today][-2:]
    for day in reversed(days):
        d = load_day(day.isoformat(), mtime(pl.day_path(day)))
        if d.empty:
            continue
        m = d[d["player_id"].astype(str) == str(player_id)]
        if m.empty:
            continue
        r = m.iloc[0]
        graded = r.get("status") == "graded"
        st.markdown(CSS, unsafe_allow_html=True)
        when = "Tonight" if day == today else f"{day:%a, %b} {day.day}"
        with st.container(border=True):
            st.markdown(f"**📈 {when}: projection {'vs' if r['home'] else '@'} {r['opp']}**"
                        + (" · graded" if graded else " · didn't play (voided)" if r.get("status") == "dnp"
                           else " · 🔒 locked before tip-off"))
            if r["returning"]:
                st.markdown('<div class="pp-warn">⚠️ He missed his team\'s last game. If he sits, this is voided.'
                            "</div>", unsafe_allow_html=True)
            if stat_col:
                e = expected(r, stat_col, stat_label or stat_col)
                if e is None:
                    st.markdown(f'<div class="pp-flagline">We don\'t project <b>{stat_label}</b> yet. '
                                "Pick points, rebounds, assists, 3-pointers made, steals, blocks or a combo "
                                "(like PRA) to see what we expect tonight.</div>", unsafe_allow_html=True)
                else:
                    diff = e["mu"] - e["avg"]
                    line = (f'{"We expected" if e["act"] is not None else "Tonight we expect"} '
                            f'<b style="font-size:1.25rem">{e["mu"]:.1f} {e["label"]}</b> '
                            f'(usually {np.floor(e["lo"]):.0f}–{np.ceil(e["hi"]):.0f}) · his average is '
                            f'{e["avg"]:.1f} ({diff:+.1f})')
                    if e["chance"]:
                        line += f' · <b>{e["chance"][1]*100:.0f}%</b> chance {e["chance"][0]} his average'
                    if e["act"] is not None:
                        line += f' · <b>actual: {e["act"]:.0f}</b>'
                    kind = "up" if diff > 0 else "down"
                    st.markdown(f'<div class="pp-flagline {kind}">{line}</div>', unsafe_allow_html=True)
            cols = st.columns(5)
            for c, stat in zip(cols, ["MIN", "PTS", "REB", "AST", "FG3M"]):
                f = r.get(f"flag_{stat}", "") if stat in pl.FLAG_STATS else ""
                arrow = {"up": " ⬆️", "down": " ⬇️"}.get(f if isinstance(f, str) else "", "")
                delta = (f"actual {r[f'act_{stat}']:.0f}" if graded
                         else f"{r[f'p_{stat}'] - r[f'avg_{stat}']:+.1f} vs avg")
                c.metric(pj.LABELS[stat], f"{_fmt(r[f'p_{stat}'], stat)}{arrow}", delta,
                         delta_color="off" if graded else "normal")
            lines = chance_lines(r)
            if lines:
                st.markdown("  \n".join(lines))
            if st.button("Why? See every stat and the reasons", key=f"pp_panel_{player_id}_{day}"):
                player_dialog(r)
        return
    _no_projection(team, today)
