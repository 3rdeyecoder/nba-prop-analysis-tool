"""📈 Player Projections (NBA): every rotation player's minutes, points, rebounds, assists, 3-pointers,
steals, blocks and turnovers for tonight, locked before tip-off and graded the next morning.
The model's opinion, for fun and research; never betting advice."""
import json

import pandas as pd
import streamlit as st

from core import projection_ui as ui
from core.ui import viewer_timezone
from matchup import nba_live
from matchup import projections_live as pl
from sports import nba_projections as pj


# ---------------------------------------------------------------- page

st.markdown(ui.CSS, unsafe_allow_html=True)
st.markdown('<div class="pp-banner"><div class="pp-title">📈 Player Projections</div>'
            '<div class="pp-tag">Every NBA rotation player, every stat, every night · Locked before tip-off, '
            'graded the next morning · For fun, never betting advice</div></div>', unsafe_allow_html=True)

model = pj.load_model()
if model is None:
    st.info("Player Projections aren't set up yet. Run `python -m refresh.train_projections` and "
            "`python -m refresh.projections`, then commit the `data/` folder.")
    st.stop()

TEAMS = ui.teams()
today = nba_live.today_et()
tz = viewer_timezone()
days = [d for d in pl.all_days() if d <= today]
if not days:
    st.info("The first projections are posted the morning of the next NBA game day (about 6:15 AM ET).")
    st.stop()

show = today if days[-1] == today else days[-1]
if show != today:
    st.info(f"Tonight's projections are posted each morning (about 6:15 AM ET). Showing "
            f"{show:%A, %B} {show.day}.")
opts = [d for d in reversed(days[-7:])]
show = st.selectbox("Day", opts, index=opts.index(show), format_func=lambda d: f"{d:%a, %b} {d.day}"
                    + (" (tonight)" if d == today else ""), key="pp_day")
d = ui.load_day(show.isoformat(), ui.mtime(pl.day_path(show)))
if d.empty:
    st.info("No projections for this day.")
    st.stop()
graded = (d["status"].fillna("") != "").any()
st.caption(("Graded: projection → actual. " if graded else "🔒 Locked in before tip-off; never changed. ")
           + f"Built from games through {pd.Timestamp(d['data_through'].iloc[0]):%b} "
           f"{pd.Timestamp(d['data_through'].iloc[0]).day}. "
           "⚠️ = missed his team's last game. Tap a player's row for the details.")

# ---------------------------------------------------------------- Top 5
top = pl.top_picks(d)
if not top.empty:
    rep5 = json.loads(pj.REPORT_PATH.read_text()).get("top5") if pj.REPORT_PATH.exists() else None
    st.subheader("Top 5 tonight" if show == today else f"Top 5 · {show:%a, %b} {show.day}")
    st.caption("The model's 5 most confident calls for a player finishing above or below his season average "
               "(points, rebounds or assists; one per player). The % is the model's honest chance, checked "
               "against past seasons."
               + (f" On {rep5['nights']} past nights these picks hit {rep5['hit_rate']*100:.0f}% of the time; "
                  f"all 5 hit on about {rep5['five_for_five']*100:.0f}% of nights and 4+ on "
                  f"{rep5['four_plus']*100:.0f}%. Nothing is a lock." if rep5 else ""))
    with st.container(horizontal=True, gap="small"):
        for k, p in enumerate(top.itertuples()):
            r = d.loc[p.i]
            why = ui.drivers(r, p.stat)[:1]
            why = f"Main reason: {why[0][0].lower()} ({why[0][1]*100:+.0f}%)." if why else ""
            res = ui.pick_result(r, p.stat, p.dir)
            with st.container(width=300, key=f"pp_flag_top_{show}_{k}_{st.session_state.get('pp_ver', 0)}"):
                st.markdown(f'<div class="pp-flag {"up" if p.dir == "over" else "down"}">'
                            f'<div class="who">#{k + 1} {r["player"]}<span style="opacity:.55;font-weight:600"> · '
                            f'{r["team"]} {"vs" if r["home"] else "@"} {r["opp"]}</span></div>'
                            f'<div class="what">{ui.pick_sentence(r, p.stat, p.dir, p.chance)}</div>'
                            f'<div class="why">{why}</div>' + (f'<div class="res">{res}</div>' if res else "")
                            + "</div>", unsafe_allow_html=True)
                if st.button(f"Details: {r['player']}", key=f"pp_topbtn_{show}_{k}"):
                    ui.player_dialog(r)

fl = ui._flags(d)
if not fl.empty:
    st.subheader("Tonight's flags" if show == today else f"Flags · {show:%a, %b} {show.day}")
    st.caption("⬆️/⬇️ = the model projects a player 25%+ above or below his season average. On past seasons, "
               "⬆️ points flags finished above average 63% of the time and ⬇️ below it 75% of the time. "
               "Tap a card for the details.")
    c1, c2 = st.columns([2, 1], vertical_alignment="center")
    which = c1.segmented_control("Stat", ["All"] + [pj.LABELS[x] for x in pl.FLAG_STATS], key="pp_flag_stat",
                                 default="All", label_visibility="collapsed") or "All"
    if which != "All":
        fl = fl[fl["stat"] == {v: k for k, v in pj.LABELS.items()}[which]]
    show_all = c2.toggle(f"Show all {len(fl)}", key="pp_flag_all") if len(fl) > 9 else True
    with st.container(horizontal=True, gap="small"):
        for k, f in enumerate((fl if show_all else fl.head(9)).itertuples()):
            r = d.loc[f.i]
            top = ui.drivers(r, f.stat)[:1]
            why = f"Main reason: {top[0][0].lower()} ({top[0][1]*100:+.0f}%)." if top else ""
            res = ui.flag_result(r, f.stat)
            with st.container(width=300, key=f"pp_flag_{show}_{k}_{st.session_state.get('pp_ver', 0)}"):
                st.markdown(f'<div class="pp-flag {f.dir}"><div class="who">{r["player"]}'
                            f'<span style="opacity:.55;font-weight:600"> · {r["team"]} {"vs" if r["home"] else "@"} '
                            f'{r["opp"]}</span>{" ⚠️" if r["returning"] else ""}</div>'
                            f'<div class="what">{ui.flag_sentence(r, f.stat)}</div><div class="why">{why}</div>'
                            + (f'<div class="res">{res}</div>' if res else "") + "</div>", unsafe_allow_html=True)
                if st.button(f"Details: {r['player']}", key=f"pp_flagbtn_{show}_{k}"):
                    ui.player_dialog(r)

st.subheader("Every player" if show == today else f"Every player · {show:%a, %b} {show.day}")
q = st.text_input("Find a player", key="pp_find", placeholder="Type a name…").strip().lower()
games = d.drop_duplicates("game_id")
labels = {}
for g in games.itertuples():
    home = g.team if g.home else g.opp
    away = g.opp if g.home else g.team
    t = pd.Timestamp(g.start_utc).tz_convert(tz) if isinstance(g.start_utc, str) and g.start_utc else None
    labels[g.game_id] = f"{away} @ {home}" + (f" · {t:%I:%M %p}".replace(" 0", " ") if t is not None else "")
if q:
    picked = list(labels)
else:
    st.session_state.setdefault("pp_game", list(labels)[0])
    if st.session_state["pp_game"] not in labels:
        st.session_state["pp_game"] = list(labels)[0]
    picked = [st.pills("Game", list(labels), key="pp_game", format_func=labels.get, label_visibility="collapsed")
              or list(labels)[0]]

for gid in picked:
    gd = d[d["game_id"] == gid]
    if q:
        gd = gd[gd["player"].str.lower().str.contains(q, regex=False)]
        if gd.empty:
            continue
    for team in [gd.loc[gd["home"] == 0, "team"].head(1), gd.loc[gd["home"] == 1, "team"].head(1)]:
        if team.empty:
            continue
        t = team.iloc[0]
        td = gd[gd["team"] == t].sort_values("p_MIN", ascending=False).reset_index(drop=True)
        st.markdown(f'<div class="pp-team">{ui.logo(t)}{TEAMS.get(t, (t, None))[0]}</div>', unsafe_allow_html=True)
        key = f"pp_tbl_{show}_{gid}_{t}_{st.session_state.get('pp_ver', 0)}"
        ev = st.dataframe(ui.team_frame(td, graded), hide_index=True, width="stretch", key=key,
                          on_select="rerun", selection_mode="single-cell", height=35 * (len(td) + 1) + 3,
                          column_config={"Player": st.column_config.TextColumn(pinned=True)})
        cells = ev.selection.get("cells", []) if ev is not None else []        # tap any cell in a row
        pick = int(cells[0][0]) if cells else None
        if pick is not None and st.session_state.get(f"{key}_open") != pick:
            st.session_state[f"{key}_open"] = pick
            ui.player_dialog(td.iloc[pick])
        elif pick is None:
            st.session_state[f"{key}_open"] = None

# ---------------------------------------------------------------- the record
st.subheader("The record")
rec = pl.load_record()
if not rec or not rec.get("graded"):
    st.info("The live record starts the morning after the first projections are graded.")
else:
    st.caption(f"{rec['graded']:,} graded player-games over {rec['days']} nights "
               f"({rec['dnp']:,} did-not-play voided). Typical miss = average distance from the actual stat.")
    rows = []
    for s in pj.TARGETS:
        x = rec["stats"][s]
        row = {"Stat": pj.LABELS[s], "Model's typical miss": round(x["mae_model"], 2),
               "Season average's typical miss": round(x["mae_season_avg"], 2),
               "Inside typical range": f"{x['in_range']*100:.0f}%"}
        if "up" in x:
            row["⬆️ hit"] = f"{x['up_hit']}/{x['up']}" if x["up"] else "–"
            row["⬇️ hit"] = f"{x['down_hit']}/{x['down']}" if x["down"] else "–"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    t5 = rec.get("top5") or {}
    if t5.get("picks"):
        st.markdown(f"**Top 5 so far:** {t5['hits']} of {t5['picks']} hit ({t5['hits']/t5['picks']*100:.0f}%; "
                    f"the model expected {t5['said']*100:.0f}%) over {t5['nights']} nights"
                    + (f", {t5['voided']} voided (didn't play)." if t5["voided"] else "."))
if pj.REPORT_PATH.exists():
    rep = json.loads(pj.REPORT_PATH.read_text())
    p = next(x for x in rep["stats"] if x["stat"] == "PTS")
    st.caption(f"Backtest (not live), {', '.join(rep['held_out_seasons'])}: points typical miss {p['mae_model']:.2f} "
               f"vs {p['mae_season_avg']:.2f} for season averages; ⬆️ flags finished above average "
               f"{p['up_hit']*100:.0f}% of the time and ⬇️ flags below {p['down_hit']*100:.0f}% "
               f"(normally {p['above_avg_normally']*100:.0f}% finish above).")
st.caption(ui.DISCLAIMER)
