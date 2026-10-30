"""End-to-end checks with Streamlit's AppTest (runs the real scripts on the stored data)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from sports import mlb, nfl

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _app():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def _keys(at):
    return {w.key for w in list(at.selectbox) + list(at.multiselect) + list(at.number_input) if w.key}


def test_nba_is_default_and_renders():
    at = _app()
    keys = _keys(at)
    assert {"nba_seasons", "nba_player", "nba_stat", "nba_window", "nba_opp", "nba_venue"} <= keys
    assert not any(k.startswith(("nfl_", "mlb_")) for k in keys)   # other sports never ran
    labels = [m.label for m in at.metric]
    for want in ["Qualifying games", "Average", "Median", "Std. deviation", "Over / Under / Push",
                 "Historical over rate", "Minutes (L5)"]:
        assert want in labels
    assert at.selectbox(key="nba_stat").options[:4] == ["Points", "Rebounds", "Assists", "3-pointers made"]


def test_nba_stats_and_combos_still_work():
    at = _app()
    for stat in ["Pts + Reb + Ast (PRA)", "Pts + Reb (PR)", "Pts + Ast (PA)", "Reb + Ast (RA)",
                 "Steals", "Blocks", "3-pointers made", "3-pointers attempted",
                 "Field goals made", "Field goals attempted", "Free throws made",
                 "Free throws attempted"]:
        at.selectbox(key="nba_stat").set_value(stat).run()
        assert not at.exception, (stat, at.exception)


def test_sport_state_is_independent_and_survives_switching():
    at = _app()
    at.selectbox(key="nba_stat").set_value("Rebounds").run()
    at.selectbox(key="nba_window").set_value("Last 5").run()

    at.switch_page("views/nfl.py").run()
    assert not at.exception, at.exception
    keys = _keys(at)
    assert "nfl_stat" in keys and "nba_stat" not in keys
    if nfl.available_seasons():
        assert at.selectbox(key="nfl_window").value == "Last 10"      # untouched by the NBA change
        at.selectbox(key="nfl_stat").set_value("Passing · Passing TDs").run()
        assert not at.exception

    at.switch_page("views/nba.py").run()
    assert at.selectbox(key="nba_stat").value == "Rebounds"           # NBA selection kept
    assert at.selectbox(key="nba_window").value == "Last 5"


def test_nfl_page():
    at = _app()
    at.switch_page("views/nfl.py").run()
    assert not at.exception, at.exception
    if not nfl.available_seasons():
        assert any("No NFL data" in w.value for w in at.warning)
        return
    at.selectbox(key="nfl_stype").set_value("Postseason").run()
    assert not at.exception
    if "2026" in at.multiselect(key="nfl_seasons").value:      # no 2026 playoffs yet -> empty state
        assert any("No stored postseason games" in i.value for i in at.info)
    at.multiselect(key="nfl_seasons").set_value(["2024", "2025"]).run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Historical over rate" in labels
    at.selectbox(key="nfl_stat").set_value("Combos · Pass + Rush yards").run()
    assert not at.exception


def test_mlb_page_without_data_shows_setup_message():
    at = _app()
    at.switch_page("views/mlb.py").run()
    assert not at.exception, at.exception
    if not mlb.available_seasons("hitting"):
        assert any("refresh.mlb" in w.value for w in at.warning)


def test_about_page():
    at = _app()
    at.switch_page("views/about.py").run()
    assert not at.exception


def test_nfl_stat_list_follows_player_position():
    if not nfl.available_seasons():
        return
    at = _app()
    at.switch_page("views/nfl.py").run()
    from sports import nfl as nflmod
    df = nflmod.load_season(int(at.multiselect(key="nfl_seasons").value[-1]))
    wr = df[df.position == "WR"].groupby("player_id")["receiving_yards"].sum().idxmax()
    qb = df[df.position == "QB"].groupby("player_id")["passing_yards"].sum().idxmax()

    at.selectbox(key="nfl_player").set_value(wr).run()
    stat = at.selectbox(key="nfl_stat")
    assert stat.value == "Receiving · Receiving yards"
    assert stat.options[0].startswith("Receiving")

    at.selectbox(key="nfl_stat").set_value("Receiving · Receptions").run()
    at.selectbox(key="nfl_player").set_value(qb).run()
    stat = at.selectbox(key="nfl_stat")
    assert stat.value == "Passing · Passing yards"            # receptions doesn't fit a QB
    assert stat.options[0].startswith("Passing")

    at.selectbox(key="nfl_player").set_value(wr).run()       # back to the WR (who threw 1 pass)
    assert at.selectbox(key="nfl_stat").value == "Receiving · Receiving yards"

    at.toggle(key="nfl_all_stats").set_value(True).run()
    assert len(at.selectbox(key="nfl_stat").options) == len(nflmod.STATS)
