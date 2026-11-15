"""Sports available on the Upset Watch page. Adding a sport = adding its module here."""
from __future__ import annotations


def available() -> dict[str, type]:
    from matchup.nba_live import NbaModule
    from matchup.nfl_live import NflModule
    return {"NBA": NbaModule, "NFL": NflModule}


COMING_SOON = ["MLB"]
