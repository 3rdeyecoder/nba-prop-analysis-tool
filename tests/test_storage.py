import pandas as pd
import pytest
import requests

from core import storage


def test_atomic_write_keeps_old_file_on_failure(tmp_path):
    path = tmp_path / "x.parquet"
    storage.atomic_write_parquet(pd.DataFrame({"a": [1, 2]}), path)

    class Boom(pd.DataFrame):
        def to_parquet(self, *a, **k):
            raise OSError("disk full")

    with pytest.raises(OSError):
        storage.atomic_write_parquet(Boom({"a": [9]}), path)
    assert pd.read_parquet(path)["a"].tolist() == [1, 2]       # last valid dataset retained
    assert not list(tmp_path.glob(".*.tmp"))                   # no temp file left behind


def test_rewrite_is_idempotent(tmp_path):
    path = tmp_path / "x.parquet"
    df = pd.DataFrame({"player_id": ["1"], "game_id": ["g"]})
    storage.atomic_write_parquet(df, path)
    storage.atomic_write_parquet(df, path)
    assert len(pd.read_parquet(path)) == 1


def test_retries_are_bounded_for_transient_errors(monkeypatch):
    monkeypatch.setattr(storage.time, "sleep", lambda s: None)
    calls = []

    def flaky():
        calls.append(1)
        raise requests.Timeout("slow")

    with pytest.raises(storage.SourceUnavailable):
        storage.with_retries(flaky, attempts=3)
    assert len(calls) == 3


def test_blocked_endpoint_is_not_retried(monkeypatch):
    monkeypatch.setattr(storage.time, "sleep", lambda s: None)
    calls = []
    resp = requests.Response()
    resp.status_code = 403

    def blocked():
        calls.append(1)
        raise requests.HTTPError("forbidden", response=resp)

    with pytest.raises(requests.HTTPError):
        storage.with_retries(blocked, attempts=3)
    assert len(calls) == 1


def test_schema_guard():
    with pytest.raises(ValueError, match="no rows"):
        storage.require_columns(pd.DataFrame(), ["a"], "x")
    with pytest.raises(ValueError, match="missing"):
        storage.require_columns(pd.DataFrame({"b": [1]}), ["a"], "x")


def test_meta_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "META_DIR", tmp_path)
    storage.update_meta("nfl", seasons={"2024": {"rows": 1}})
    storage.update_meta("nfl", seasons={"2025": {"rows": 2}}, last_error=None)
    meta = storage.read_meta("nfl")
    assert set(meta["seasons"]) == {"2024", "2025"}
