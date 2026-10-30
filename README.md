# NBA Props Lab — NBA • NFL • MLB Player Analytics

A Streamlit app for researching player props with historical game logs. Pick a sport, a player,
a stat and a line, and see how often the player has gone over, under or pushed in past games,
with a game-by-game chart, a full game log and a CSV export.

It shows **historical results, not predictions**. A historical over rate is not a calibrated
probability for the next game. There are no odds, sportsbook integrations or betting recommendations.

---

## Features

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
attempted, steals, blocks, PRA, PR, PA, RA, blocks + steals;
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

### Scheduling

Run the commands above on a schedule you control (cron, Task Scheduler, or a GitHub Actions
workflow that commits `data/`). Verify that the scheduler can actually reach each source before
relying on it; stats.nba.com in particular often blocks cloud IP ranges.

---

## Project layout

```
app.py                 entry point: title, NBA | NFL | MLB navigation, per-sport state
core/
  config.py            app name/subtitle (rebrand here), colors, window options
  metrics.py           over/under/push, summaries, ordering, dedupe, outs <-> innings, total bases
  storage.py           atomic writes, refresh metadata, bounded retries, schema checks
  ui.py                shared controls, summary cards, chart, table, CSV, data status
  style.py             design CSS from the original app
sports/
  nba.py nfl.py mlb.py data normalization and stored-file readers (no network)
views/
  nba.py nfl.py mlb.py about.py   one Streamlit page per sport
refresh/
  nba.py nfl.py mlb.py ingestion scripts (network lives here only)
data/                  stored datasets + data/meta/<sport>.json (last refresh, coverage)
tests/                 pytest suite
fetch_data.py          backward-compatible wrapper for refresh.nba
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
