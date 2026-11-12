"""The interface every sport's matchup module implements. The Matchup page, flagging and the
track record only talk to this interface, so adding a sport means adding one module."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class Team:
    abbr: str
    name: str
    logo: str | None = None


@dataclass(frozen=True)
class Game:
    sport: str
    game_id: str
    start_utc: str               # ISO time
    home: str
    away: str
    neutral: bool = False


@dataclass
class GameContext:
    """What the model needs beyond the two teams. `home` is None for a neutral site."""
    home: str | None
    game_date: date
    extra: dict = field(default_factory=dict)       # sport-specific (rest days, QB status, weather...)


@dataclass
class StatRow:
    """One line of the side-by-side table."""
    section: str                 # e.g. "Ratings", "Form", "Rest"
    label: str
    a: float | str | None
    b: float | str | None
    better: str | None = None    # "a", "b" or None (which side the stat favours)
    fmt: str = "{:.1f}"
    note: str = ""


@dataclass
class Prediction:
    team_a: str
    team_b: str
    p_a: float
    drivers: dict = field(default_factory=dict)     # feature -> contribution, for "why"

    @property
    def p_b(self) -> float:
        return 1.0 - self.p_a


@dataclass
class Result:
    winner: str | None           # None = tie / no result
    home_score: int | None = None
    away_score: int | None = None


class SportModule(Protocol):
    sport: str

    def get_teams(self) -> list[Team]: ...
    def get_games(self, day: date) -> list[Game]: ...
    def get_matchup_stats(self, a: str, b: str, as_of: date) -> list[StatRow]: ...
    def predict_win_prob(self, a: str, b: str, ctx: GameContext) -> Prediction: ...
    def game_result(self, game: Game) -> Result | None: ...
