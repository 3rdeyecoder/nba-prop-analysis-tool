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


# ---------------------------------------------------------------- upcoming games

def test_nba_schedule_normalization_reads_nba_api_fields():
    from sports import nba
    raw = pd.DataFrame({
        "gameId": ["0022600123", "22600124", "0042600401"],
        "gameDateTimeUTC": ["2026-11-08T00:00:00Z", "2026-11-08T03:00:00Z", "2027-06-04T00:30:00Z"],
        "awayTeam_teamTricode": ["PHI", "LAL", ""],                       # 3rd = Finals placeholder (no teams yet)
        "homeTeam_teamTricode": ["DET", "SAC", ""],
        "awayTeam_teamId": [1610612755, 1610612747, 0], "homeTeam_teamId": [1610612765, 1610612758, 0],
        "awayTeam_wins": [7, 6, 0], "awayTeam_losses": [1, 2, 0],
        "homeTeam_wins": [6, 1, 0], "homeTeam_losses": [1, 6, 0],
        "arenaName": ["Little Caesars Arena", "Golden 1 Center", ""], "gameStatus": [1, 1, 1],
        "nationalBroadcasters_0_broadcasterDisplay": ["ESPN", "", ""],
        "nationalBroadcasters_1_broadcasterDisplay": ["ESPN", "Prime Video", ""],
    })
    s = nba.normalize_schedule(raw)
    assert s["game_id"].tolist() == ["0022600123", "0022600124"]                # zero-padded ids, placeholder dropped
    assert s.loc[0, "away_record"] == "7-1" and s.loc[1, "home_record"] == "1-6"
    assert s.loc[0, "tv"] == "ESPN" and s.loc[1, "tv"] == "Prime Video"         # duplicates merged, blanks skipped
    assert str(s.loc[0, "start_utc"].tz) == "UTC"


def _up(league, start, away="AAA", home="HHH"):
    return {"league": league, "start": pd.Timestamp(start, tz="UTC"), "away": away, "home": home,
            "away_logo": None, "home_logo": None, "away_record": None, "home_record": None, "tv": None}


def test_upcoming_shows_today_or_the_next_game_day(monkeypatch):
    from zoneinfo import ZoneInfo
    nba_games = [_up("NBA", "2026-11-08T00:00"), _up("NBA", "2026-11-08T03:00"),     # Sat 7 PM / 10 PM ET
                 _up("NBA", "2026-11-09T00:00")]                                    # Sunday
    nfl_games = [_up("NFL", "2026-11-08T14:30"), _up("NFL", "2026-11-08T18:00"),     # Sunday 9:30 AM / 1 PM ET
                 _up("NFL", "2026-11-15T18:00")]
    monkeypatch.setattr(ticker, "_nba_upcoming_rows", lambda: nba_games)
    monkeypatch.setattr(ticker, "_nfl_upcoming_rows", lambda: nfl_games)
    et = ZoneInfo("America/New_York")
    now = "2026-11-07T20:00"                                                       # Saturday 3 PM ET
    assert len(ticker.upcoming("NBA", now=now, tz=et)) == 2                        # tonight's two games
    nfl = ticker.upcoming("NFL", now=now, tz=et)
    assert len(nfl) == 2 and all(g["start"].tz_convert(et).day == 8 for g in nfl)  # next game day: Sunday
    assert {g["league"] for g in ticker.upcoming(None, now=now, tz=et)} == {"NBA", "NFL"}
    # a game that tipped off an hour ago still shows (no live scores yet)
    assert len(ticker.upcoming("NBA", now="2026-11-08T01:00", tz=et)) == 2
    # Pacific viewers see the 10 PM ET game as 7 PM their time, same day
    la = ZoneInfo("America/Los_Angeles")
    assert ticker._time_label(nba_games[1]["start"], la, pd.Timestamp("2026-11-07").date()) == "7:00 PM"
    assert ticker._time_label(nfl_games[0]["start"], et, pd.Timestamp("2026-11-07").date()) == "Sun 9:30 AM"


def test_mixed_ticker_skips_leagues_with_nothing_this_week(monkeypatch):
    from zoneinfo import ZoneInfo
    monkeypatch.setattr(ticker, "_nba_upcoming_rows", lambda: [_up("NBA", "2026-11-08T00:00")])
    monkeypatch.setattr(ticker, "_nfl_upcoming_rows", lambda: [_up("NFL", "2027-01-10T18:00")])
    got = ticker.upcoming(None, now="2026-11-07T20:00", tz=ZoneInfo("America/New_York"))
    assert {g["league"] for g in got} == {"NBA"}


def test_nfl_upcoming_reads_saved_schedule_in_eastern_time():
    from sports import nfl
    seasons = sorted(nfl.NFL_DIR.glob("schedule_*.parquet"))
    if not seasons or "gametime" not in pd.read_parquet(seasons[-1]).columns:
        return
    rows = ticker._nfl_upcoming_rows()
    if rows:
        g = rows[0]
        sched = pd.read_parquet(seasons[-1])
        r = sched[(sched.away_team == g["away"]) & (sched.home_team == g["home"]) & sched.away_score.isna()].iloc[0]
        et = g["start"].tz_convert("America/New_York")
        assert f"{et:%Y-%m-%d}" == r["gameday"] and f"{et:%H:%M}" == r["gametime"]


def _render_html(monkeypatch, coming, games, now_et="2026-11-07 15:00"):
    from zoneinfo import ZoneInfo
    import core.ui as ui
    et = ZoneInfo("America/New_York")
    out = []
    monkeypatch.setattr(ticker, "latest_games", lambda league=None: games)
    monkeypatch.setattr(ticker, "upcoming", lambda league=None, tz=None: coming)
    monkeypatch.setattr(ui, "viewer_timezone", lambda: et)
    monkeypatch.setattr(ticker.pd.Timestamp, "now", classmethod(lambda cls, tz=None: pd.Timestamp(now_et, tz=et)))
    monkeypatch.setattr(ticker.st, "markdown", lambda html, **k: out.append(html))
    ticker.render("NFL")
    return out[0]


def test_results_lead_unless_there_are_games_today(monkeypatch):
    final = [{**_g("NFL", "2026-11-02"), "label": "Week 8"}]
    sunday = [_up("NFL", "2026-11-08T18:00")]                                 # tomorrow
    html = _render_html(monkeypatch, sunday, final)
    assert html.index("NFL<br>RESULTS") < html.index("NFL<br>UP NEXT")        # Saturday: results first
    tonight = [_up("NFL", "2026-11-08T01:15")]                                # 8:15 PM ET today
    html = _render_html(monkeypatch, tonight, final)
    assert html.index("NFL<br>TODAY") < html.index("NFL<br>RESULTS")          # game day: today's games first


def test_home_team_from_matchup_text():
    assert ticker._home_team(["BOS vs. NYK", "NYK @ BOS"]) == "BOS"
    assert ticker._home_team(["NYK @ BOS", "NYK @ BOS"]) == "BOS"            # only away-style rows
    assert ticker._home_team(["MEM vs. ORL", "ORL vs. MEM"]) is None         # neutral site listed both ways
    assert ticker._home_team(["???", "!!!"]) is None


def test_one_bad_game_or_league_never_blanks_the_ticker(tmp_path, monkeypatch):
    rows = pd.DataFrame({
        "GAME_ID": [1, 1, 2, 2], "GAME_DATE": ["2026-11-06"] * 4, "TEAM_ID": [1, 2, 3, 4],
        "TEAM_ABBREVIATION": ["BOS", "NYK", "MEM", "ORL"],
        "MATCHUP": ["BOS vs. NYK", "NYK @ BOS", "MEM vs. ORL", "ORL vs. MEM"],          # game 2: ambiguous
        "PTS": [110, 101, 99, 98]})
    f = tmp_path / "logs.csv.gz"
    rows.to_csv(f, index=False, compression="gzip")
    games = ticker._nba_games.__wrapped__(((str(f), 0.0),))
    assert [(g["away"], g["home"], g["home_pts"]) for g in games] == [("NYK", "BOS", 110)]   # bad game skipped
    monkeypatch.setattr(ticker, "_nba_results", lambda: 1 / 0)                              # NBA loading breaks
    out = ticker.by_league()
    assert out["NBA"] == [] and set(out) == {"NBA", "NFL", "MLB"}                            # others still load
