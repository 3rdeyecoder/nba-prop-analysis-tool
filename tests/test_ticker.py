import pandas as pd

from core import ticker


def _g(league, day, a="AAA", h="HHH"):
    return {"league": league, "date": pd.Timestamp(day), "sort": day, "away": a, "away_pts": 1,
            "away_logo": None, "home": h, "home_pts": 2, "home_logo": None}


def test_each_tab_gets_its_own_league_and_home_mixes_in_season_leagues(monkeypatch):
    fake = {"NBA": [_g("NBA", "2026-11-03")] * 20,
            "NFL": [_g("NFL", "2026-11-02")] * 3,
            "MLB": [_g("MLB", "2026-10-31")] * 4}                          # World Series just ended
    monkeypatch.setattr(ticker, "by_league", lambda: fake)
    assert {g["league"] for g in ticker.latest_games("NFL")} == {"NFL"}
    assert len(ticker.latest_games("NBA")) == ticker.PER_LEAGUE            # capped
    assert {g["league"] for g in ticker.latest_games("MLB")} == {"MLB"}
    mixed = ticker.latest_games(None, today="2026-11-04")
    assert {g["league"] for g in mixed} == {"NBA", "NFL", "MLB"}           # all within 10 days
    stale = ticker.latest_games(None, today="2026-12-20")
    assert {g["league"] for g in stale} == {"NBA", "NFL", "MLB"}           # nothing recent: show what exists
    fake["NBA"] = [_g("NBA", "2026-11-19")] * 3
    assert {g["league"] for g in ticker.latest_games(None, today="2026-11-20")} == {"NBA"}  # MLB, NFL stale


def test_everything_off_season_falls_back_to_what_exists(monkeypatch):
    fake = {"NBA": [], "NFL": [_g("NFL", "2026-02-09")], "MLB": []}
    monkeypatch.setattr(ticker, "by_league", lambda: fake)
    assert [g["league"] for g in ticker.latest_games(None, today="2026-07-01")] == ["NFL"]


def test_logo_sources_for_each_league():
    from sports import mlb, nfl
    assert nfl.logo_url("LA").endswith("/lar.png") and nfl.logo_url("WAS").endswith("/wsh.png")
    assert nfl.logo_url("KC").endswith("/kc.png")
    assert nfl.logo_url("KC", {"KC": "https://x/kc.png"}) == "https://x/kc.png"       # saved nflverse logo wins
    row = pd.Series({"home_abbr": "MIL", "away_abbr": "TB", "home_id": None, "away_id": 139.0})
    assert ticker._mlb_logo(row, "home") == mlb.LOGO.format(158)                       # fallback by abbreviation
    assert ticker._mlb_logo(row, "away") == mlb.LOGO.format(139)                       # stored id
    assert len({v for v in mlb.TEAM_IDS.values()}) == 30                               # all 30 clubs covered
