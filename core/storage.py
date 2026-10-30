"""File I/O for stored datasets: atomic writes, refresh metadata, bounded retries."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd

from core.config import META_DIR

log = logging.getLogger("refresh")
T = TypeVar("T")

TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class SourceUnavailable(RuntimeError):
    """A source kept failing after bounded retries (or is blocked)."""


def _tmp(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp")


def _atomic(path: Path, writer: Callable[[Path], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(path)
    try:
        writer(tmp)
        os.replace(tmp, path)  # atomic on the same filesystem
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    _atomic(path, lambda p: df.to_parquet(p, index=False))


def atomic_write_csv_gz(df: pd.DataFrame, path: Path) -> None:
    _atomic(path, lambda p: df.to_csv(p, index=False, compression="gzip"))


def atomic_write_json(obj: dict, path: Path) -> None:
    _atomic(path, lambda p: p.write_text(json.dumps(obj, indent=2, default=str)))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def meta_path(sport: str) -> Path:
    return META_DIR / f"{sport}.json"


def read_meta(sport: str) -> dict:
    p = meta_path(sport)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def update_meta(sport: str, **fields) -> dict:
    """Merge fields into data/meta/<sport>.json (nested dicts are merged one level deep)."""
    meta = read_meta(sport)
    for k, v in fields.items():
        if isinstance(v, dict) and isinstance(meta.get(k), dict):
            meta[k] = {**meta[k], **v}
        else:
            meta[k] = v
    atomic_write_json(meta, meta_path(sport))
    return meta


def is_transient(exc: BaseException) -> bool:
    """Timeouts, dropped connections and 429/5xx are worth retrying. 403/404 are not."""
    try:
        import requests

        if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
            return True
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            return exc.response.status_code in TRANSIENT_STATUS
    except ImportError:
        pass
    return isinstance(exc, (TimeoutError, ConnectionError))


def with_retries(fn: Callable[[], T], *, attempts: int = 3, base_delay: float = 2.0, label: str = "") -> T:
    """Call fn with bounded exponential backoff, retrying transient errors only."""
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if not is_transient(exc):
                raise
            if i == attempts:
                raise SourceUnavailable(f"{label or 'request'} failed after {attempts} attempts: {exc}") from exc
            delay = base_delay * 2 ** (i - 1)
            log.warning("%s: transient %s; retry %d/%d in %.0fs", label, type(exc).__name__, i, attempts - 1, delay)
            time.sleep(delay)
    raise AssertionError("unreachable")


def require_columns(df: pd.DataFrame | None, cols: list[str], label: str) -> None:
    """Schema guard: refuse to replace good data with an empty or changed schema."""
    if df is None or df.empty:
        raise ValueError(f"{label}: source returned no rows")
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{label}: source schema changed; missing columns {missing}")


def coverage(df: pd.DataFrame) -> dict:
    if df.empty or "game_date" not in df:
        return {"rows": 0}
    d = pd.to_datetime(df["game_date"], errors="coerce")
    return {"rows": int(len(df)), "first_game": str(d.min().date()), "last_game": str(d.max().date())}
