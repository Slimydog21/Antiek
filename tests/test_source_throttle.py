"""SPR-03 M2/M3 — persistent cross-process throttle + ban sentinel + rotation.

The 2026-05-29 prod run's defining failure: an in-process-only throttle died on
process restart, so a re-run re-hit the just-banned endpoint and dug the hole
deeper. These tests prove the fix at the level the rigor card demands:

  - RESTART SURVIVAL: two SourceThrottle instances over the SAME state file
    (the cross-process / process-restart simulation) see the SAME banned_until,
    and the persisted min-interval is enforced.
  - 429/503 -> SENTINEL: a ban status arms banned_until; a banned source's
    before_request raises SourceBanned (it does NOT fetch).
  - BACKOFF: the exponential-with-jitter schedule is deterministic under an
    injected jitter, bounded by max attempts + max delay.
  - ROTATION: next_available_source picks the next non-banned source; when ALL
    are banned it halts cleanly recording the soonest banned_until.
  - END-TO-END ban_then_rotate: a mocked 429 IN THE CONNECTOR FETCH PATH sets
    the sentinel, and the NEXT live call rotates to another source — exercised
    THROUGH the OA fetch path, not by poking the sentinel directly.

NO live HTTP, NO real state file: ANTIEK_SOURCE_THROTTLE_PATH is redirected to a
tmp path so a test can never write a ban to ~/.antiek/source_throttle.json.
``now``/``sleep`` are injected so CI never sleeps for real.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.source_throttle import (  # noqa: E402
    DEFAULT_BAN_BACKOFF_S,
    SourceBanned,
    SourceThrottle,
    backoff_delays,
    next_available_source,
)


class _Clock:
    """An injectable fake clock; sleep advances it instead of blocking."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


# ---------------------------------------------------------------------------
# M2 — restart survival + min-interval enforcement
# ---------------------------------------------------------------------------


def test_banned_until_survives_a_fresh_instance(tmp_path):
    """A 429 on instance A persists a banned_until that instance B (a fresh
    construction over the SAME state file — the process-restart simulation)
    reads identically; B refuses to fetch the banned source."""
    path = str(tmp_path / "throttle.json")
    clock = _Clock()

    a = SourceThrottle(state_path=path, now=clock.now, sleep=clock.sleep)
    a.note_response("gutendex", 429)
    expected = clock.now() + DEFAULT_BAN_BACKOFF_S

    # Fresh instance, same file — must see the same sentinel.
    b = SourceThrottle(state_path=path, now=clock.now, sleep=clock.sleep)
    assert b.is_banned("gutendex")
    assert b.banned_until("gutendex") == pytest.approx(expected)
    with pytest.raises(SourceBanned):
        b.before_request("gutendex")


def test_min_interval_enforced_across_instances(tmp_path):
    """The persisted last-request timestamp spaces a second instance's request:
    a request on A, then before_request on a fresh B within the interval,
    sleeps the remaining gap (in-process spacing is now persisted)."""
    path = str(tmp_path / "throttle.json")
    clock = _Clock()

    a = SourceThrottle(
        state_path=path, default_min_interval_s=5.0,
        now=clock.now, sleep=clock.sleep,
    )
    a.before_request("oa_unpaywall")  # records last_request_at = 1000

    clock.t += 2.0  # only 2s have elapsed; need 5

    b = SourceThrottle(
        state_path=path, default_min_interval_s=5.0,
        now=clock.now, sleep=clock.sleep,
    )
    before = clock.now()
    b.before_request("oa_unpaywall")
    # B slept the remaining 3s to honor the 5s persisted interval.
    assert clock.now() - before == pytest.approx(3.0)


def test_per_source_isolation(tmp_path):
    """A ban on one source does not ban another — state is per source key."""
    path = str(tmp_path / "throttle.json")
    clock = _Clock()
    t = SourceThrottle(state_path=path, now=clock.now, sleep=clock.sleep)
    t.note_response("gutendex", 503)
    assert t.is_banned("gutendex")
    assert not t.is_banned("oa_unpaywall")
    # oa_unpaywall is free to request.
    t.before_request("oa_unpaywall")


def test_retry_after_extends_but_never_undercuts_floor(tmp_path):
    """A Retry-After is honored when LONGER than the default floor, and a tiny
    advertised window can never undercut the conservative floor."""
    path = str(tmp_path / "throttle.json")
    clock = _Clock()
    t = SourceThrottle(state_path=path, now=clock.now, sleep=clock.sleep)

    # Tiny Retry-After must not shorten the protective floor.
    t.note_response("gutendex", 429, {"Retry-After": "5"})
    assert t.banned_until("gutendex") == pytest.approx(clock.now() + DEFAULT_BAN_BACKOFF_S)

    # A longer Retry-After extends the ban.
    clock.t += 10_000
    long = DEFAULT_BAN_BACKOFF_S + 3600
    t.note_response("oa_pmc", 429, {"Retry-After": str(int(long))})
    assert t.banned_until("oa_pmc") == pytest.approx(clock.now() + long)


def test_non_ban_status_is_noop(tmp_path):
    """A 200 / 404 / 500 does not arm the sentinel — only 429/503 do."""
    path = str(tmp_path / "throttle.json")
    clock = _Clock()
    t = SourceThrottle(state_path=path, now=clock.now, sleep=clock.sleep)
    for status in (200, 404, 500, 502):
        t.note_response("gutendex", status)
    assert not t.is_banned("gutendex")


def test_corrupt_state_file_does_not_disable_throttle(tmp_path):
    """An unreadable/garbled state file must not silently disable throttling —
    it reads as empty (space from now), not as 'never banned, go fast'."""
    path = tmp_path / "throttle.json"
    path.write_text("}{ not json", encoding="utf-8")
    clock = _Clock()
    t = SourceThrottle(state_path=str(path), now=clock.now, sleep=clock.sleep)
    # Does not raise; treats source as not-yet-seen.
    assert not t.is_banned("gutendex")
    t.before_request("gutendex")


# ---------------------------------------------------------------------------
# M3 — exponential backoff with jitter (deterministic under injected jitter)
# ---------------------------------------------------------------------------


def test_backoff_schedule_deterministic_with_fixed_jitter():
    """With jitter pinned to its max (1.0 -> factor 1.0) the schedule is the
    pure capped exponential: base, 2*base, 4*base, ... up to max_attempts-1."""
    delays = backoff_delays(
        base_s=0.5, max_s=30.0, max_attempts=4, jitter=lambda: 1.0
    )
    assert delays == (0.5, 1.0, 2.0)  # 3 delays for 4 attempts


def test_backoff_is_bounded_by_max_delay():
    """The capped exponential never exceeds max_s even before jitter."""
    delays = backoff_delays(
        base_s=10.0, max_s=15.0, max_attempts=5, jitter=lambda: 1.0
    )
    # 10, capped 15, capped 15, capped 15
    assert delays == (10.0, 15.0, 15.0, 15.0)
    assert all(d <= 15.0 for d in delays)


def test_backoff_jitter_only_reduces_within_cap():
    """Jitter maps [0,1) -> [0.5,1.0], so a delay is in [0.5*cap, cap] — it
    never extends past the deterministic ceiling."""
    delays_min = backoff_delays(
        base_s=1.0, max_s=30.0, max_attempts=3, jitter=lambda: 0.0
    )
    delays_max = backoff_delays(
        base_s=1.0, max_s=30.0, max_attempts=3, jitter=lambda: 1.0
    )
    for lo, hi in zip(delays_min, delays_max):
        assert lo == pytest.approx(hi * 0.5)
        assert lo <= hi


# ---------------------------------------------------------------------------
# M3 — source rotation on hard ban
# ---------------------------------------------------------------------------


def test_rotation_picks_first_non_banned_source(tmp_path):
    """When arxiv is banned, rotation skips it and tries the next configured
    source — the skip is observable in the decision."""
    path = str(tmp_path / "throttle.json")
    clock = _Clock()
    t = SourceThrottle(state_path=path, now=clock.now, sleep=clock.sleep)
    t.note_response("arxiv_pdf", 429)

    decision = next_available_source(t, ["arxiv_pdf", "gutendex", "oa_unpaywall"])
    assert decision.next_source == "gutendex"
    assert [s for s, _ in decision.skipped] == ["arxiv_pdf"]
    assert not decision.all_banned
    assert "skip arxiv_pdf" in decision.render()


def test_rotation_all_banned_halts_with_soonest_resume(tmp_path):
    """When EVERY configured source is banned, rotation returns no next source
    and records the SOONEST banned_until so a resume is informed (clean halt,
    not a spin)."""
    path = str(tmp_path / "throttle.json")
    clock = _Clock()
    t = SourceThrottle(state_path=path, now=clock.now, sleep=clock.sleep)

    t.note_response("arxiv_pdf", 429, {"Retry-After": str(int(DEFAULT_BAN_BACKOFF_S + 100))})
    t.note_response("gutendex", 503)  # default floor — sooner

    decision = next_available_source(t, ["arxiv_pdf", "gutendex"])
    assert decision.all_banned
    assert decision.next_source is None
    # gutendex's default-floor ban is sooner than arxiv's extended one.
    assert decision.soonest_banned_until == pytest.approx(
        clock.now() + DEFAULT_BAN_BACKOFF_S
    )


# ---------------------------------------------------------------------------
# M3 — END-TO-END: mocked 429 in the fetch path -> sentinel -> next call rotates
# ---------------------------------------------------------------------------


def test_ban_then_rotate_e2e_through_orchestrator(tmp_path, monkeypatch):
    """END-TO-END through the LIVE orchestrator (not a sentinel poke, not a
    direct ``next_available_source`` call): a 429 raised inside the REAL OA
    ``download_pdf`` path arms the persistent sentinel; the orchestrator's
    ``discover_all`` — the production caller of source rotation — then SKIPS the
    banned OA source and pulls the non-banned arXiv-bulk source instead.

    This proves rotation as a SYSTEM behavior: the same ``SourceThrottle`` file
    the OA fetch armed is the one ``discover_all`` reads (redirected via
    ``ANTIEK_SOURCE_THROTTLE_PATH``), and the rotation decision is observable in
    the returned ``rotation_log`` — not validated by reaching into the rotation
    helper directly.

    Step 1: ``unpaywall.download_pdf`` hits a mocked 429 through
            ``OAThrottle.run_with_retry`` (max_retries=0 -> the 429 propagates
            after one attempt) — but ``note_response`` armed the sentinel for
            ``oa_unpaywall`` in the shared file.
    Step 2: ``discover_all`` with --source open_access + arxiv (bulk) reads that
            shared file, finds ``oa_unpaywall`` banned, logs the skip, and runs
            ONLY the non-banned arXiv-bulk source — the banned OA source's
            discovery adapter is never even entered.
    """
    from acquisition.openaccess import OAThrottle, unpaywall
    from tools.run_corpus_ingest import build_parser, discover_all

    path = str(tmp_path / "throttle.json")
    monkeypatch.setenv("ANTIEK_SOURCE_THROTTLE_PATH", path)

    # Step 1: arm the sentinel for oa_unpaywall through the REAL OA fetch path.
    # SourceThrottle() inside the OA path reads ANTIEK_SOURCE_THROTTLE_PATH, so
    # we let it default-construct (the env redirect is the shared-file contract).
    persistent = SourceThrottle(state_path=path)

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request)

    client = httpx.Client(transport=httpx.MockTransport(_handler))
    throttle = OAThrottle(
        min_spacing_s=0.0, max_retries=0, sleep=lambda _s: None,
        persistent=persistent, source="oa_unpaywall",
    )
    with pytest.raises(httpx.HTTPStatusError):
        unpaywall.download_pdf(
            "https://oa.example/paper.pdf", client=client, throttle=throttle
        )
    client.close()

    # The ban is on disk (process-restart-survivable): a fresh throttle sees it.
    assert SourceThrottle(state_path=path).is_banned("oa_unpaywall")

    # Step 2: drive the LIVE orchestrator. It selects open_access (banned) +
    # arxiv-bulk (not banned); rotation must skip OA and pull arxiv-bulk.
    snapshot = os.path.join(_REPO, "tests/fixtures/arxiv/bulk_snapshot_sample.jsonl")
    args = build_parser().parse_args([
        "--source", "open_access", "--source", "arxiv",
        "--oa-source", "unpaywall",
        "--arxiv-source", "bulk", "--arxiv-bulk-snapshot", snapshot,
        "--limit", "3", "--dry-run",
    ])
    outcome = discover_all(args)

    # The banned OA source was SKIPPED (observable in the rotation log) and the
    # non-banned arXiv-bulk source was pulled — rotation as a system behavior.
    assert any("skip oa_unpaywall" in line for line in outcome.rotation_log)
    assert not outcome.all_banned
    assert outcome.candidates  # arXiv-bulk candidates came through
    assert {c.source for c in outcome.candidates} == {"arxiv"}


def test_all_sources_banned_halts_with_soonest_resume_e2e(tmp_path, monkeypatch):
    """When EVERY selected source is banned, the LIVE ``discover_all`` returns a
    clean all-banned halt carrying the soonest resume time — not a spin, not a
    generic 'no candidates'. Proven through the orchestrator (the production
    caller), reading the shared sentinel both sources' bans were written to."""
    from tools.run_corpus_ingest import build_parser, discover_all

    path = str(tmp_path / "throttle.json")
    monkeypatch.setenv("ANTIEK_SOURCE_THROTTLE_PATH", path)

    t = SourceThrottle(state_path=path)
    # gutendex banned at the default floor (sooner); arxiv_pdf banned longer.
    base = t.banned_until  # noqa: F841  (read for clarity below)
    t.note_response("gutendex", 503)
    soonest = t.banned_until("gutendex")
    t.note_response(
        "arxiv_pdf", 429,
        {"Retry-After": str(int(DEFAULT_BAN_BACKOFF_S + 7200))},
    )

    args = build_parser().parse_args([
        "--source", "public_domain", "--pd-curated",
        "--source", "arxiv", "--arxiv-source", "bulk",
        "--arxiv-bulk-snapshot",
        os.path.join(_REPO, "tests/fixtures/arxiv/bulk_snapshot_sample.jsonl"),
        "--limit", "3", "--dry-run",
    ])
    outcome = discover_all(args)

    assert outcome.all_banned
    assert not outcome.candidates
    # The soonest resume is gutendex's default-floor ban, not arxiv's longer one.
    assert outcome.soonest_resume == pytest.approx(soonest)
    assert any("ALL sources banned" in line for line in outcome.rotation_log)


def test_banned_source_before_request_never_fetches(tmp_path):
    """A source whose sentinel is active makes before_request RAISE before any
    request — proving the live path consults the sentinel rather than fetching
    and re-extending the ban."""
    from acquisition.openaccess import OAThrottle

    path = str(tmp_path / "throttle.json")
    clock = _Clock()
    persistent = SourceThrottle(state_path=path, now=clock.now, sleep=clock.sleep)
    persistent.note_response("oa_unpaywall", 429)  # ban up front

    throttle = OAThrottle(
        min_spacing_s=0.0, sleep=lambda _s: None,
        persistent=persistent, source="oa_unpaywall",
    )
    fetched = {"called": False}

    def _fn():
        fetched["called"] = True
        return "should-not-happen"

    with pytest.raises(SourceBanned):
        throttle.run_with_retry(_fn)
    assert fetched["called"] is False
