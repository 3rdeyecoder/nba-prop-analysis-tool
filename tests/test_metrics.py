import math

import pandas as pd
import pytest

from core.metrics import (OVER, PUSH, UNDER, classify, dedupe, default_line, fmt, ip_to_outs,
                          most_recent, outs_to_ip, summarize, total_bases)


def test_over_under_push_classification():
    res = classify(pd.Series([10, 9, 8, None]), 9)
    assert res.tolist()[:3] == [OVER, PUSH, UNDER]
    assert res.iloc[3] is None  # missing stays missing, not an under


def test_over_rate_excludes_pushes():
    s = summarize(pd.Series([10, 9, 9, 8, 12]), 9)
    assert (s.overs, s.unders, s.pushes) == (2, 1, 2)
    assert s.decided == 3
    assert s.over_rate == pytest.approx(2 / 3)


def test_all_pushes_rate_unavailable():
    s = summarize(pd.Series([7, 7, 7]), 7)
    assert s.pushes == 3 and s.over_rate is None
    assert fmt(s.over_rate) == "Unavailable"


def test_empty_and_missing_values():
    s = summarize(pd.Series([], dtype=float), 5)
    assert s.games == 0 and s.mean is None and s.median is None and s.std is None and s.over_rate is None
    s = summarize(pd.Series([None, 4.0]), 5)
    assert s.games == 1 and s.std is None  # std needs 2+ games
    assert fmt(None) == "Unavailable" and fmt(float("nan")) == "Unavailable"


def test_calculations_use_unrounded_values():
    s = summarize(pd.Series([1, 2, 2]), 0.5)
    assert s.mean == pytest.approx(5 / 3)          # not 1.7
    assert fmt(s.mean) == "1.7"
    assert s.std == pytest.approx(0.5773502691896257)


def _games():
    return pd.DataFrame({
        "game_date": pd.to_datetime(["2025-05-03", "2025-05-01", "2025-05-03", "2025-05-02", "2025-04-30"]),
        "game_seq": [2, 1, 1, 1, 1],
        "game_id": ["e", "b", "d", "c", "a"],
        "opponent": ["NYY", "BOS", "NYY", "TOR", "BOS"],
        "val": [5, 2, 4, 3, 1],
    })


def test_most_recent_ordering_and_doubleheaders():
    recent = most_recent(_games(), 3)
    # Doubleheader on 05-03: game 1 (d) before game 2 (e); game 2 is the most recent
    assert recent["game_id"].tolist() == ["c", "d", "e"]
    assert most_recent(_games(), None)["game_id"].tolist() == ["a", "b", "c", "d", "e"]


def test_filters_apply_before_window():
    g = _games()
    bos = g[g["opponent"] == "BOS"]
    assert most_recent(bos, 5)["game_id"].tolist() == ["a", "b"]  # only 2 qualifying, not 5 rows


def test_dedupe_player_game():
    df = pd.DataFrame({"player_id": ["1", "1", "2"], "game_id": ["g", "g", "g"], "pts": [10, 12, 8]})
    out, dropped = dedupe(df, ["player_id", "game_id"])
    assert dropped == 1 and len(out) == 2
    assert out.loc[out.player_id == "1", "pts"].item() == 12  # newest copy kept


def test_total_bases():
    # 2 singles, 1 double, 0 triples, 1 HR -> 2 + 2 + 0 + 4
    assert total_bases(2, 1, 0, 1) == 8
    assert total_bases(0, 0, 1, 0) == 3


@pytest.mark.parametrize("outs,ip", [(0, "0.0"), (1, "0.1"), (2, "0.2"), (3, "1.0"), (17, "5.2"), (27, "9.0")])
def test_outs_innings_roundtrip(outs, ip):
    assert outs_to_ip(outs) == ip
    assert ip_to_outs(ip) == outs


def test_innings_notation_is_not_decimal():
    assert ip_to_outs(5.2) == 17      # not 5.2 * 3 = 15.6
    assert ip_to_outs("6") == 18
    with pytest.raises(ValueError):
        ip_to_outs("5.5")
    assert outs_to_ip(None) is None and ip_to_outs(None) is None


def test_default_line_snaps_below_average():
    assert default_line(pd.Series([20, 25])) == 22.5
    assert default_line(pd.Series([], dtype=float)) == 0.5
    assert not math.isnan(default_line(pd.Series([None, 3.0])))
