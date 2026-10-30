"""Pure calculation helpers shared by every sport. No Streamlit imports here."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

OVER, UNDER, PUSH = "Over", "Under", "Push"

# Chronological ordering keys every normalized game log carries.
ORDER_COLS = ["game_date", "game_seq", "game_id"]


def classify(values: pd.Series, line: float) -> pd.Series:
    """Over: stat > line. Under: stat < line. Push: stat == line. Missing stays missing."""
    v = pd.to_numeric(values, errors="coerce").astype(float)
    arr = v.to_numpy()
    present = ~np.isnan(arr)
    push = present & np.isclose(arr, line, rtol=0.0, atol=1e-9)
    out = np.full(len(arr), None, dtype=object)
    out[present & (arr > line) & ~push] = OVER
    out[present & (arr < line) & ~push] = UNDER
    out[push] = PUSH
    return pd.Series(out, index=v.index, dtype="object")


@dataclass
class Summary:
    games: int
    mean: float | None
    median: float | None
    std: float | None
    overs: int
    unders: int
    pushes: int

    @property
    def decided(self) -> int:
        return self.overs + self.unders

    @property
    def over_rate(self) -> float | None:
        """Overs / (overs + unders). Pushes excluded; unavailable when nothing was decided."""
        return self.overs / self.decided if self.decided else None


def summarize(values: pd.Series, line: float) -> Summary:
    """Summary of the selected window, computed from unrounded values."""
    v = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    res = classify(v, line)
    n = len(v)
    return Summary(
        games=n,
        mean=float(v.mean()) if n else None,
        median=float(v.median()) if n else None,
        std=float(v.std(ddof=1)) if n >= 2 else None,  # sample standard deviation
        overs=int((res == OVER).sum()),
        unders=int((res == UNDER).sum()),
        pushes=int((res == PUSH).sum()),
    )


def fmt(x: float | None, digits: int = 1) -> str:
    """Round for display only. None/NaN -> 'Unavailable', never 0."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "Unavailable"
    return f"{x:.{digits}f}"


def sort_games(df: pd.DataFrame) -> pd.DataFrame:
    """Chronological order with deterministic tie-breaks (doubleheaders, same-day games)."""
    cols = [c for c in ORDER_COLS if c in df.columns]
    return df.sort_values(cols, kind="mergesort").reset_index(drop=True)


def most_recent(df: pd.DataFrame, n: int | None) -> pd.DataFrame:
    """Most recent N qualifying games. Apply all other filters BEFORE calling this."""
    ordered = sort_games(df)
    return ordered if n is None else ordered.tail(n).reset_index(drop=True)


def dedupe(df: pd.DataFrame, keys: list[str]) -> tuple[pd.DataFrame, int]:
    """Drop duplicate player/game records, keeping the last (newest) copy."""
    before = len(df)
    out = df.drop_duplicates(subset=keys, keep="last").reset_index(drop=True)
    return out, before - len(out)


def default_line(values: pd.Series) -> float:
    """Starting line: last-10 average snapped to the .5 below it (kept from the original app)."""
    v = pd.to_numeric(values, errors="coerce").dropna().tail(10)
    if v.empty:
        return 0.5
    return float(np.floor(v.mean())) + 0.5


# ---------- baseball helpers ----------

def total_bases(singles, doubles, triples, home_runs):
    """TB = 1B + 2*2B + 3*3B + 4*HR."""
    return singles + 2 * doubles + 3 * triples + 4 * home_runs


def outs_to_ip(outs) -> str | None:
    """17 outs -> '5.2' (five innings and two outs)."""
    if outs is None or pd.isna(outs):
        return None
    outs = int(outs)
    if outs < 0:
        raise ValueError("outs cannot be negative")
    return f"{outs // 3}.{outs % 3}"


def ip_to_outs(ip) -> int | None:
    """'5.2' or 5.2 -> 17 outs. Rejects values like 5.5 that are not valid innings notation."""
    if ip is None or (isinstance(ip, float) and math.isnan(ip)):
        return None
    s = str(ip).strip()
    if not s:
        return None
    whole, _, frac = s.partition(".")
    frac = frac or "0"
    if not whole.isdigit() or frac not in {"0", "1", "2"}:
        raise ValueError(f"invalid innings notation: {ip!r}")
    return int(whole) * 3 + int(frac)
