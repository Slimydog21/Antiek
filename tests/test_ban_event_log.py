"""SPR-05 arXiv task 5B — attributable bans via an append-only ban-event log.

Each ban-status response must append ONE JSON line naming who and where
(ts, source, status, host, pid, argv0). The sentinel is always written FIRST;
the append never raises into the caller.

NO live HTTP, NO real state files: the conftest ``_isolate_ban_event_log``
fixture points the log at ``tmp_path``; throttle state paths are explicit tmp
paths; clocks are fakes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.rate_governor import arxiv_governed_client  # noqa: E402
from acquisition.arxiv.throttle import (  # noqa: E402
    ARXIV_BAN_SOURCE_KEY,
    ArxivThrottle,
)
from substrate.ban_events import (  # noqa: E402
    BAN_EVENT_FIELDS,
    append_ban_event,
    default_ban_event_log_path,
    read_ban_events,
)
from substrate.source_throttle import SourceThrottle  # noqa: E402


class _FakeClock:
    """Monotonic fake wall-clock; sleep advances it instead of blocking."""

    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _log_lines() -> list[str]:
    p = Path(default_ban_event_log_path())
    if not p.exists():
        return []
    return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_arxiv_throttle_429_appends_one_event_with_all_six_fields(
    tmp_path: Path,
) -> None:
    clock = _FakeClock(t=1_700_000_000.0)
    t = ArxivThrottle(
        state_path=str(tmp_path / "t.json"),
        now=clock.now,
        sleep=clock.sleep,
    )
    before = len(_log_lines())
    t.note_response(
        429, {}, url="https://export.arxiv.org/api/query?search_query=x"
    )
    lines = _log_lines()
    assert len(lines) == before + 1
    events = read_ban_events()
    assert len(events) == before + 1
    event = events[-1]
    assert set(event.keys()) == set(BAN_EVENT_FIELDS)
    assert event["source"] == ARXIV_BAN_SOURCE_KEY
    assert event["status"] == 429
    assert event["host"] == "export.arxiv.org"
    assert event["pid"] == os.getpid()
    argv0 = event["argv0"]
    assert isinstance(argv0, str) and argv0
    assert event["ts"] == clock.now()
    assert t.banned_until() > 0


def test_source_throttle_429_appends_one_event_with_all_six_fields(
    tmp_path: Path,
) -> None:
    clock = _FakeClock(t=1_700_000_000.0)
    s = SourceThrottle(
        state_path=str(tmp_path / "s.json"),
        now=clock.now,
        sleep=clock.sleep,
    )
    before = len(_log_lines())
    s.note_response(
        "arxiv_export", 429, {}, url="https://export.arxiv.org/api/query"
    )
    lines = _log_lines()
    assert len(lines) == before + 1
    events = read_ban_events()
    event = events[-1]
    assert set(event.keys()) == set(BAN_EVENT_FIELDS)
    assert event["source"] == "arxiv_export"
    assert event["status"] == 429
    assert event["host"] == "export.arxiv.org"
    assert event["pid"] == os.getpid()
    argv0 = event["argv0"]
    assert isinstance(argv0, str) and argv0
    assert event["ts"] == clock.now()
    assert s.banned_until("arxiv_export") > 0


def test_non_ban_status_appends_nothing(tmp_path: Path) -> None:
    clock = _FakeClock()
    t = ArxivThrottle(
        state_path=str(tmp_path / "t.json"),
        now=clock.now,
        sleep=clock.sleep,
    )
    s = SourceThrottle(
        state_path=str(tmp_path / "s.json"),
        now=clock.now,
        sleep=clock.sleep,
    )
    t.note_response(200, {}, url="https://export.arxiv.org/api/query")
    s.note_response("arxiv_export", 200, {}, url="https://export.arxiv.org/api/query")
    s.note_response("arxiv_export", 500, {}, url="https://export.arxiv.org/api/query")
    assert _log_lines() == []
    assert read_ban_events() == []


def test_source_throttle_503_is_logged(tmp_path: Path) -> None:
    clock = _FakeClock()
    s = SourceThrottle(
        state_path=str(tmp_path / "s.json"),
        now=clock.now,
        sleep=clock.sleep,
    )
    s.note_response("gutendex", 503, {}, url="https://gutendex.com/books")
    events = read_ban_events()
    assert len(events) == 1
    assert events[0]["source"] == "gutendex"
    assert events[0]["status"] == 503
    assert events[0]["host"] == "gutendex.com"
    assert s.banned_until("gutendex") > 0


def test_mirror_note_response_at_is_not_logged(tmp_path: Path) -> None:
    clock = _FakeClock()
    s = SourceThrottle(
        state_path=str(tmp_path / "s.json"),
        now=clock.now,
        sleep=clock.sleep,
    )
    s.note_response_at("arxiv_export", clock.now() + 100.0)
    assert _log_lines() == []
    assert read_ban_events() == []
    assert s.banned_until("arxiv_export") > 0


def test_unwritable_log_never_breaks_the_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    afile = tmp_path / "afile"
    afile.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv(
        "ANTIEK_BAN_EVENT_LOG_PATH", str(afile / "ban_events.jsonl")
    )
    clock = _FakeClock()
    t = ArxivThrottle(
        state_path=str(tmp_path / "t.json"),
        now=clock.now,
        sleep=clock.sleep,
    )
    t.note_response(429, {})
    assert t.banned_until() > 0
    s = SourceThrottle(
        state_path=str(tmp_path / "s.json"),
        now=clock.now,
        sleep=clock.sleep,
    )
    s.note_response("arxiv_export", 429, {})
    assert s.banned_until("arxiv_export") > 0


def test_governed_client_429_event_names_the_arxiv_host(tmp_path: Path) -> None:
    clock = _FakeClock()
    state = str(tmp_path / "arxiv_throttle.json")
    lock = str(tmp_path / "gov.lock")
    throttle = ArxivThrottle(
        state_path=state,
        min_spacing_s=0.0,
        now=clock.now,
        sleep=clock.sleep,
    )

    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "60"})

    client = arxiv_governed_client(
        throttle=throttle,
        lock_path=lock,
        transport=httpx.MockTransport(_handler),
        timeout=5.0,
        lock_sleep=clock.sleep,
    )
    resp = client.get("https://export.arxiv.org/api/query?search_query=x")
    assert resp.status_code == 429
    events = read_ban_events()
    # The hooked path may legitimately note the same 429 twice (hook + outer
    # request); assert >= 1 and that every event names the arXiv host.
    assert len(events) >= 1
    for event in events:
        assert event["host"] == "export.arxiv.org"
        assert event["status"] == 429


def test_read_ban_events_returns_last_n_and_skips_malformed_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "ban_events.jsonl"
    monkeypatch.setenv("ANTIEK_BAN_EVENT_LOG_PATH", str(log))
    good = (
        {"ts": 1.0, "source": "a", "status": 429, "host": "h", "pid": 1, "argv0": "x"},
        {"ts": 2.0, "source": "b", "status": 503, "host": "", "pid": 2, "argv0": "y"},
        {"ts": 3.0, "source": "c", "status": 429, "host": "h2", "pid": 3, "argv0": "z"},
    )
    log.write_text(
        "\n"
        + json.dumps(good[0])
        + "\n"
        + "not json\n"
        + json.dumps([1, 2, 3])
        + "\n"
        + json.dumps(good[1])
        + "\n"
        + json.dumps(good[2])
        + "\n",
        encoding="utf-8",
    )
    all_events = read_ban_events()
    assert [e["source"] for e in all_events] == ["a", "b", "c"]
    last2 = read_ban_events(last=2)
    assert [e["source"] for e in last2] == ["b", "c"]
    assert read_ban_events(path=str(tmp_path / "missing.jsonl")) == []


def test_arxiv_verify_ban_events_prints_exactly_n_without_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for i in range(5):
        append_ban_event(
            source=f"s{i}",
            status=429,
            url="https://export.arxiv.org/api/query",
            ts=1_000.0 + i,
        )

    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("run_checks must not be called for --ban-events")

    monkeypatch.setattr("tools.arxiv_verify.run_checks", _boom)
    from tools.arxiv_verify import main

    rc = main(["--ban-events", "3"])
    assert rc == 0
    captured = capsys.readouterr()
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) == 3
    # The LAST three seeded events, in file order.
    assert "source=s2" in lines[0]
    assert "source=s3" in lines[1]
    assert "source=s4" in lines[2]


def test_arxiv_verify_help_lists_ban_events_flag() -> None:
    from tools.arxiv_verify import build_parser

    assert "--ban-events" in build_parser().format_help()
