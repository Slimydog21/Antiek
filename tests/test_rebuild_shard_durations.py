from __future__ import annotations

import json
from pathlib import Path

from tools.rebuild_shard_durations import durations_from_logs, parse_log

_ROOT = Path(__file__).resolve().parents[1]
_MAP = _ROOT / "tools" / "pytest_shard_durations.json"


def _log(tmp_path: Path, lines: list[str]) -> Path:
    p = tmp_path / "shard.log"
    p.write_text("\n".join(f"job\tstep\t{line}" for line in lines), encoding="utf-8")
    return p


def test_parses_the_seven_digit_timestamps_github_writes(tmp_path) -> None:
    """GitHub logs carry seven fractional digits; strptime accepts six."""
    log = _log(tmp_path, ["2026-10-01T09:08:43.7670359Z tests/test_a.py::test_one"])
    parsed = parse_log(log)

    assert len(parsed) == 1
    assert parsed[0][1] == "tests/test_a.py"


def test_duration_is_the_gap_between_consecutive_starts(tmp_path) -> None:
    """`-v` prints each node id as it STARTS, so the gap is the earlier test's time."""
    log = _log(tmp_path, [
        "2026-10-01T09:00:00.0000000Z tests/test_a.py::test_one",
        "2026-10-01T09:00:12.0000000Z tests/test_b.py::test_two",
        "2026-10-01T09:00:20.0000000Z tests/test_b.py::test_three",
    ])
    got = durations_from_logs([log])

    assert got["tests/test_a.py"] == 12.0
    assert got["tests/test_b.py"] == 8.0
    # the last test has no successor, so it is left unmeasured rather than guessed
    assert sum(got.values()) == 20.0


def test_out_of_order_or_absurd_gaps_are_dropped_not_summed(tmp_path) -> None:
    log = _log(tmp_path, [
        "2026-10-01T09:00:20.0000000Z tests/test_a.py::test_one",   # going backwards
        "2026-10-01T09:00:00.0000000Z tests/test_a.py::test_two",
        "2026-10-01T09:00:01.0000000Z tests/test_a.py::test_three",
    ])
    got = durations_from_logs([log])

    assert got["tests/test_a.py"] == 1.0, "a negative gap must not be accumulated"


def test_the_committed_map_covers_the_suite_and_is_plausible() -> None:
    """Guards the file the packer trusts: it must be a real measurement.

    The map it replaced held 854 files and 38.7 minutes against a real suite of
    about 80, with individual entries wrong by up to 7x in one direction and 2.3x
    in the other. This test fails if the map is ever regenerated into something
    that small or that empty again.
    """
    data = json.loads(_MAP.read_text(encoding="utf-8"))

    assert len(data) > 900, f"only {len(data)} files mapped"
    assert all(isinstance(v, (int, float)) and v >= 0 for v in data.values())
    total_minutes = sum(data.values()) / 60
    assert 60 < total_minutes < 110, f"{total_minutes:.1f} minutes of test time is not plausible"
