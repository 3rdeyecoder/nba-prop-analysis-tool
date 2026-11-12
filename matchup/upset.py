"""Upset Watch: games where our model gives the 'on paper' underdog a clearly better chance than
the teams' records suggest. For fun: the model's opinion, never betting advice.

'On paper' = what a casual fan would expect from the standings alone: each team's win percentage
(blended with a .500 start early in the season), combined head-to-head with the log5 formula, then
adjusted for home court. The model adds what records miss (form, ratings, rest, missing players).
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_THRESHOLD = 0.05      # 5 percentage points above the on-paper chance (adjustable)
PRIOR_GAMES = 10              # early-season blend: every team starts as if 5-5
NBA_HOME_WIN_RATE = 0.553     # home teams won 55.3% of 6,140 NBA games, 2021-22 to 2025-26


def win_pct(wins: int, losses: int, prior_games: int = PRIOR_GAMES) -> float:
    """Win percentage blended with a .500 start, so 2-0 isn't treated as unbeatable."""
    return (wins + prior_games / 2) / (wins + losses + prior_games)


def log5(p_a: float, p_b: float) -> float:
    """Chance A beats B given each team's strength vs. an average team (Bill James' log5)."""
    num = p_a * (1 - p_b)
    return num / (num + p_b * (1 - p_a))


def on_paper(record_a: tuple[int, int], record_b: tuple[int, int], home: str | None,
             home_win_rate: float = NBA_HOME_WIN_RATE) -> float:
    """On-paper chance team A wins. `home` is 'a', 'b' or None (neutral site)."""
    p = log5(win_pct(*record_a), win_pct(*record_b))
    if home is None:
        return p
    boost = home_win_rate / (1 - home_win_rate)                 # home court as a win/loss ratio multiplier
    ratio = p / (1 - p) * (boost if home == "a" else 1 / boost)
    return ratio / (1 + ratio)


@dataclass
class UpsetCheck:
    underdog: str
    favorite: str
    paper_prob: float          # underdog's on-paper chance
    model_prob: float          # underdog's chance by the model
    threshold: float

    @property
    def edge(self) -> float:
        return self.model_prob - self.paper_prob

    @property
    def flagged(self) -> bool:
        return self.paper_prob < 0.5 and self.edge >= self.threshold - 1e-12


def check(team_a: str, team_b: str, paper_a: float, model_a: float,
          threshold: float = DEFAULT_THRESHOLD) -> UpsetCheck:
    """The underdog is whoever is less likely to win on paper. Even on paper: no underdog."""
    if abs(paper_a - 0.5) < 1e-9:
        raise ValueError("even on paper: no underdog")
    if paper_a < 0.5:
        return UpsetCheck(team_a, team_b, paper_a, model_a, threshold)
    return UpsetCheck(team_b, team_a, 1 - paper_a, 1 - model_a, threshold)
