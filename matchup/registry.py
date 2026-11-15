"""Sports available on the Matchup page. Adding a sport = adding its module here."""
from __future__ import annotations


def available() -> dict[str, type]:
    from matchup.nba_live import NbaModule
    return {"NBA": NbaModule}


COMING_SOON = ["NFL", "MLB"]
