# Playmaker Lab — NBA • NFL • MLB Player Analytics

A Streamlit app for researching player props with historical game logs. Pick a sport, a player,
a stat and a line, and see how often the player has gone over, under or pushed in past games,
with a game-by-game chart, a full game log and a CSV export.

It shows **historical results, not predictions**. A historical over rate is not a calibrated
probability for the next game. There are no odds, sportsbook integrations or betting recommendations.

---

## Features

**Header and layout**: every page opens with a dark header holding a **Latest results** ticker
(recent final scores: NBA from the stored game logs, NFL and MLB from the schedules saved by
`refresh.nfl` / `refresh.mlb`). Each sport's tab shows only that league; Today's Lab and Call It mix
the leagues played in the last 10 days,
the title and the tabs, with the open tab highlighted. The sidebar starts closed (open it with »
for page options); "About" is linked in the footer.

**Today's Lab (home page)**: starting points from recent NBA games, each linking straight into
the full analysis with the right player, stat and filters selected:
- *Heating up*: last 5 games (all this season) vs the 30 before them, with minutes before/after.
- *Consistency corner*: smallest spread relative to average over the last 10 games.
- *Matchup history*: biggest gap between a player's average vs one team and overall (last 3
  seasons, 6+ games vs that team).
Cards only include players who **played in their team's most recent game**, so anyone currently out
(injury, rest or suspension) drops off until they play again. For absences the game logs can't show
yet, add a row to `data/unavailable.csv` (sport, player_id, player_name, until, note); it stops
applying after its `until` date. A "Who's left out?" note on the page lists both groups.
Every card shows its sample size and date range, plus how fresh the data is. Minimum minutes and
averages keep tiny samples out. Logic lives in `sports/insights.py` (tested).

**🎯 Call It (daily puzzle)**: 5 real past NBA games from every stored season (2019-20 to
today). For each, you see the player's 10 games before that night and call over or under the line,
then the result is revealed with a link into that player's analysis. Everyone gets the same puzzle
each day (US Eastern date). The results screen shows the score with a title, a spoiler-free share
grid (🟩🟥), and a recap of player cards. Each card shows the team, opponent logo and season from the
night of that game; photos are the player's current headshot (NBA's image server only has current ones).
- The line is the **median** of the 10 games shown (moved to the .5 below if it's a whole number),
  so no ties are possible. Across all ~66k playable games this line goes over 48% of the time
  (47.8–50.1% per stat); an average-based line went over only 44.5%, because big nights pull
  averages up.
- Rounds need 10+ earlier games that season, 25+ minutes a night, and a stat minimum. Games are
  picked without looking at results, only games 3+ days old are used (so a refresh can't change
  today's puzzle), and every round is a different player. Logic: `sports/callit.py` (tested).

**Shareable links**: every view's settings live in the URL (sport, player, stat, seasons,
window, opponent, home/away, line), and the address bar updates as you change filters. Each
page has a "Share this view" box. Set `APP_URL` in `core/config.py` if the app's address changes.

**Every sport**
- Searchable player picker (keyed by stable player IDs, so traded players stay one player)
- Season and season-type (regular season / postseason) selectors
- Recent-games window: last 5, 10, 15, 20 or all qualifying games
- Opponent and home/away filters (NFL also shows neutral-site games)
- Summary cards: qualifying games, average, median, standard deviation, overs / unders / pushes,
  and historical over rate with its numerator and denominator
- Game-by-game chart with the line, 5-game rolling average, dates and hover details
- Game-log table and CSV download of exactly the games shown

**NBA**: points, rebounds, assists, 3-pointers made and attempted, field goals made and
attempted, free throws made and attempted, steals, blocks, PRA, PR, PA, RA, blocks + steals;
headshot card, quick hit-rate strip, streaks, distribution, trend summary, rolling average,
opponent and home/away splits.

**NFL**: passing (yards, TDs, attempts, completions, INTs), rushing (yards, attempts, TDs),
receiving (yards, receptions, targets, TDs) and combos (rush + rec yards, pass + rush yards,
rush + rec TDs). QB, RB, WR and TE by default (FB optional). The stat list follows the
player's position (passing first for QBs, rushing for RBs, receiving for WRs/TEs), plus any
other stat type they actually recorded; a sidebar toggle shows every stat instead.

**MLB**: separate **Hitters** (hits, HR, total bases, runs, RBIs, walks, batter strikeouts,
stolen bases, H+R+RBI) and **Pitchers** (strikeouts, outs recorded, hits allowed, earned runs,
walks allowed, HR allowed; innings shown for display). Pitchers default to starts only.

## How the numbers are calculated

| Term | Definition |
|---|---|
| Over / Under / Push | stat > line / stat < line / stat = line |
| Historical over rate | overs ÷ (overs + unders). Pushes are excluded and shown separately. If every game pushed, the rate is unavailable. |
| Window | Season → season type → opponent → home/away filters are applied **first**, then the most recent N remaining games are used. |
| Std. deviation | Sample standard deviation of the window (needs 2+ games). |

Calculations use exact values; rounding happens only for display. Missing values show as
"Unavailable", never 0. Small samples (under 10 games) get a note but are never blocked.

### Which games count

- **NBA**: every row in stats.nba.com's player game log, i.e. games the player checked into
  (including cameos that round to 0 minutes). DNPs and inactive games have no row.
- **NFL**: a row in nflverse's weekly player stats, which exists when the player was credited with
  at least one play. Bye weeks and missed games never count. A 0 is a real zero in a game the
  player appeared in. Seasons use the official NFL season year (January/February playoff games
  belong to the previous season).
- **MLB hitters**: at least one plate appearance (defensive-only subs excluded). Optional
  filters: starting lineup only, minimum plate appearances.
- **MLB pitchers**: faced at least one batter or recorded an out. "Starts only" by default;
  switch to "Starts + relief" to include relief appearances.
- **MLB scheduling**: doubleheader games are separate games, ordered game 1 then game 2.
  Suspended games are stored once, after completion, dated by the day they began (how MLB
  credits the stats). Postponed games are skipped until played.
- **Innings**: workload is stored as integer outs. `5.2` IP means 5 innings + 2 outs = 17 outs,
  not 5.2 decimal innings. Charts and lines use outs.

---

## Setup

```bash
git clone https://github.com/3rdeyecoder/nba-prop-analysis-tool.git
cd nba-prop-analysis-tool
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app only **reads** stored files in `data/`. It never calls a data API while you browse,
which avoids the timeouts stats.nba.com causes on Streamlit Cloud.

## Initializing and refreshing data

Refreshes are separate scripts. Run them on your own machine, then commit `data/` so Streamlit
Cloud picks up the new files. Each sport refreshes independently; a failure leaves the previous
files untouched and is recorded in `data/meta/<sport>.json`.

### NBA (stats.nba.com via `nba_api`)

```bash
python -m refresh.nba                                   # current season: regular season + playoffs
python -m refresh.nba --seasons 2023-24 2024-25 2025-26
python -m refresh.nba --types regular                   # skip playoffs
```

Writes `data/league_logs_<season>.csv.gz` (and `..._playoffs.csv.gz`), the same files the
original app used. Each season is re-pulled in full, which picks up stat corrections.
`python fetch_data.py [seasons...]` still works and calls the same code.
Optional: `export NBA_PROXY=...` to route through a proxy (never printed in logs).

### NFL (nflverse via `nflreadpy`)

```bash
python -m refresh.nfl                                   # current season
python -m refresh.nfl --seasons 2020 2021 2022 2023 2024 2025 2026   # full initialization
```

Writes `data/nfl/player_week_<season>.parquet` (≈130 KB per season). nflverse publishes one
file per season, so each refresh re-downloads it and picks up corrections. Weekly stats usually
appear within a day of a game and may be revised later.

### MLB (MLB Stats API)

```bash
python -m refresh.mlb --seasons 2025 2026               # first run: ~25-40 min per season
python -m refresh.mlb                                   # later runs: new games only
python -m refresh.mlb --recent-days 5                   # re-pull the last 5 days for corrections
python -m refresh.mlb --max-games 20                    # quick smoke test
```

Writes `data/mlb/hitting_<season>.parquet` and `data/mlb/pitching_<season>.parquet`. One
schedule request per season, then one boxscore per completed game not already stored, spaced
0.5 s apart (`--delay`). Rows are keyed by player + gamePk, so reruns don't duplicate. After 5
consecutive failures the run stops and saves what it has. Pitch-level Statcast data is not used.

### Automatic daily refresh (GitHub Actions)

`.github/workflows/refresh-data.yml` runs every morning (~6–7 AM Eastern). It refreshes NFL,
NBA and MLB independently, commits any new data (which redeploys the Streamlit app), and posts a
per-sport success/failure summary on the run's page. A sport that fails leaves its stored files
exactly as they were. Run it by hand from GitHub: **Actions → Refresh data → Run workflow**.

stats.nba.com often blocks cloud servers like GitHub's. If the NBA step keeps failing there,
keep running `python -m refresh.nba --types regular` on your own machine. Run `git pull` first
so you have the bot's latest commits, then push as usual.

### Scheduling

Run the commands above on a schedule you control (cron, Task Scheduler, or a GitHub Actions
workflow that commits `data/`). Verify that the scheduler can actually reach each source before
relying on it; stats.nba.com in particular often blocks cloud IP ranges.

---

## Project layout

```
app.py                 entry point: title, Today's Lab | Call It | NBA | NFL | MLB navigation, state
core/
  config.py            app name/subtitle (rebrand here), colors, window options
  metrics.py           over/under/push, summaries, ordering, dedupe, outs <-> innings, total bases
  storage.py           atomic writes, refresh metadata, bounded retries, schema checks
  ui.py                shared controls, summary cards, chart, table, CSV, data status
  links.py             shareable links (settings <-> URL)
  analytics.py         Google Analytics tag
  style.py             design CSS from the original app
sports/
  nba.py nfl.py mlb.py data normalization and stored-file readers (no network)
  insights.py          Today's Lab calculations
  callit.py            Call It puzzle generation
views/
  today.py             Today's Lab (home page)
  callit.py            Call It daily puzzle
  nba.py nfl.py mlb.py about.py   one Streamlit page per sport
refresh/
  nba.py nfl.py mlb.py ingestion scripts (network lives here only)
data/                  stored datasets + data/meta/<sport>.json (last refresh, coverage)
tests/                 pytest suite
fetch_data.py          backward-compatible wrapper for refresh.nba
.github/workflows/     daily automatic data refresh
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Covers over/under/push and over-rate rules, empty and missing data, most-recent ordering,
doubleheaders, duplicate records, NFL season and postseason handling, MLB total bases,
outs ↔ innings, strikeout separation, two-way players, atomic writes and retry limits, plus
Streamlit `AppTest` runs of every page, including independent state between sports.

## Analytics

Google Analytics 4 is added in `core/analytics.py` with the measurement ID in `core/config.py`
(`GA_MEASUREMENT_ID`; set it to `""` to turn tracking off). It loads once per visit, is skipped
when running on localhost, and counts NBA/NFL/MLB switches as page views through GA4's
"page changes based on browser history events" setting. Ad blockers will hide some visits.

Call It also sends two custom events: `callit_start` (first pick) and `callit_complete`
(with `puzzle_number`, `score` and `perfect`). Each is sent once per browser tab, so reloads
don't double count. To see score breakdowns in reports, register `score` and `puzzle_number` as
custom dimensions in GA4 (Admin → Custom definitions).

## Responsible use

Every page ends with a note that the app shows past results, not picks, with the 21+ reminder and
1-800-GAMBLER. The About page has a short "Play responsibly" section.

## Data sources and terms

- **NBA**: stats.nba.com via [`nba_api`](https://github.com/swar/nba_api). Unofficial endpoints;
  can be rate-limited or blocked.
- **NFL**: [nflverse](https://github.com/nflverse/nflverse-data) via
  [`nflreadpy`](https://github.com/nflverse/nflreadpy). Licensed CC-BY 4.0. Data by nflverse.
- **MLB**: MLB Stats API (statsapi.mlb.com). © MLB Advanced Media. Its notice permits
  individual, non-commercial, non-bulk use only. Keep refreshes incremental and polite.

## Known limitations

- NFL: a player who was on the field but never touched the ball or drew a target has no
  nflverse row, so that game doesn't count. Snap-count data would be needed to include it.
- NBA: Play-In games are not loaded. Playoff files exist only after running the NBA refresh.
- MLB: the parser follows the Stats API boxscore format but has only been tested against
  sample responses; check the first refresh's output.
- Historical hit rates ignore role changes, injuries and matchup context.

## Tech stack

Python · Streamlit · pandas · NumPy · Plotly · PyArrow/Parquet · nba_api · nflreadpy · pytest
