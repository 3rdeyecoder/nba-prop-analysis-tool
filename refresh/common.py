"""Small helpers shared by the refresh scripts."""
from __future__ import annotations

import logging
import sys

from core.storage import update_meta, utc_now_iso

USER_AGENT = "nba-prop-analysis-tool/2.0 (personal research; github.com/3rdeyecoder/nba-prop-analysis-tool)"


def setup_logging() -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    return logging.getLogger("refresh")


def record_result(sport: str, ok: list[str], failed: dict[str, str], coverage: dict) -> int:
    """Write refresh metadata. Successful parts update coverage even if other parts failed."""
    fields = {"last_attempt_utc": utc_now_iso(), "seasons": coverage}
    if ok:
        fields["last_success_utc"] = utc_now_iso()
    fields["last_error"] = "; ".join(f"{k}: {v}" for k, v in failed.items()) or None
    update_meta(sport, **fields)
    log = logging.getLogger("refresh")
    if failed:
        for k, v in failed.items():
            log.error("FAILED %s: %s (existing stored data left unchanged)", k, v)
        return 1
    log.info("Done: %s", ", ".join(ok) or "nothing to do")
    return 0
