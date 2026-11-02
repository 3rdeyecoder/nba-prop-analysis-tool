"""Manual unavailable list: data/unavailable.csv

Use it for absences the game logs can't show yet (for example, an injury announced before the
team's next game). Each row applies until its `until` date, then is ignored automatically.

    sport,player_id,player_name,until,note
    nba,1630162,Anthony Edwards,2027-01-05,Injury (expected return early January)

`player_name` is just for readability; matching uses `player_id`. Leave `until` empty to keep a
row active until you delete it.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from core.config import DATA_DIR

PATH = DATA_DIR / "unavailable.csv"


def load(sport: str, today: date | None = None) -> pd.DataFrame:
    """Active rows for this sport. A missing or malformed file means nobody is listed."""
    cols = ["sport", "player_id", "player_name", "until", "note"]
    try:
        df = pd.read_csv(PATH, dtype=str).fillna("")
    except (FileNotFoundError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame(columns=cols)
    if not set(["sport", "player_id"]) <= set(df.columns):
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df:
            df[c] = ""
    today = today or date.today()
    until = pd.to_datetime(df["until"], errors="coerce").dt.date
    still_out = until.isna() | (until >= today)
    rows = df[(df["sport"].str.lower() == sport) & still_out & df["player_id"].str.strip().ne("")]
    return rows[cols].reset_index(drop=True)


def ids(sport: str, today: date | None = None) -> frozenset[str]:
    return frozenset(load(sport, today)["player_id"].str.strip())
