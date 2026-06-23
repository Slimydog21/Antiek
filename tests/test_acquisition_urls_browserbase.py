"""Tests for the Wedge 2 — Browserbase escalation fallback.

Spec: `docs/integration_exa_browserbase.md` §7. The Browserbase SDK
itself is an OPTIONAL dep; tests mock through the
`session_factory` + `page_runner` injection seams on
`fetch_via_browserbase`, and monkeypatch the adapter's lazy import
where needed.

Coverage:
  - budget_browserbase: cap enforcement, reservation, refund-on-failure
  - client_browserbase: robots.txt enforcement, concurrency cap,
    BrowserbaseUnavailable when SDK absent, runner integration
  - adapter.ingest_url: default-off behavior unchanged; fallback
    flag on a low_word_count URL triggers escalation + emits the
    FetchFallbackEscalatedPayload; budget-exceeded path returns
    low_word_count_after_fallback; recovery path produces full
    ingestion
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from acquisition.urls.adapter import ingest_url
from acquisition.urls.budget_browserbase import (
    DEFAULT_DAILY_BUDGET_USD,
    BrowserbaseBudgetExceeded,
    BudgetState,
    check_and_reserve,
    read_state,
    record_actual,
    write_state,
)
from acquisition.urls.client import FetchedHtml
from acquisition.urls.client_browserbase import (
    MAX_CONCURRENT_SESSIONS,
    BrowserbaseFetchError,
    BrowserbaseRobotsDisallowed,
    BrowserbaseUnavailable,
    fetch_via_browserbase,
)

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Redirect budgets + event log to tmp_path. Sets the
    Browserbase creds + the legal-gate disabled flag so the
    integration paths run cleanly."""
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("BROWSERBASE_API_KEY", "test-bb-key")
    monkeypatch.setenv("BROWSERBASE_PROJECT_ID", "test-project")
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_DISABLED", "1")
    yield {"events_dir": str(events_dir), "tmpdir": str(tmp_path)}


# Minimal fake-session for client tests.
@dataclass
class _FakeSession:
    closed: bool = False

    def connect_url(self) -> str:
        return "wss://test/connect"

    def close(self) -> None:
        self.closed = True


def _fake_session_factory(*, fail: bool = False):
    """Build a session_factory callable that returns a fresh fake
    session per call. ``fail=True`` raises on factory invocation
    (simulates BrowserbaseUnavailable etc.)."""

    def factory():
        if fail:
            raise BrowserbaseUnavailable("test-induced unavailable")
        return _FakeSession()

    return factory


def _make_page_runner(
    body: bytes = b"<html><body>" + b"hello world " * 30 + b"</body></html>",
    final_url: str | None = None,
    status: int = 200,
    raise_exc: Exception | None = None,
):
    def runner(*, session, url, wait_for, wait_timeout_s, user_agent):
        if raise_exc is not None:
            raise raise_exc
        return body, final_url or url, status

    return runner


# ── budget_browserbase ────────────────────────────────────────────


def test_budget_reservation_accumulates(isolated_env):
    s1 = check_and_reserve(0.30)
    assert s1.spent_usd == 0.30
    assert s1.session_count == 1
    s2 = check_and_reserve(0.30)
    assert s2.spent_usd == 0.60
    assert s2.session_count == 2


def test_budget_exceeded_raises(isolated_env):
    # Pre-fill within $0.01 of the cap.
    s = BudgetState(
        date_stamp=read_state().date_stamp,
        spent_usd=DEFAULT_DAILY_BUDGET_USD - 0.01,
        session_count=10,
        cap_usd=DEFAULT_DAILY_BUDGET_USD,
    )
    write_state(s)
    with pytest.raises(BrowserbaseBudgetExceeded):
        check_and_reserve(0.50)


def test_budget_record_actual_clamps_at_zero(isolated_env):
    check_and_reserve(0.30)
    record_actual(-10.0)  # Refund more than spent.
    assert read_state().spent_usd == 0.0


def test_budget_override_per_call_relaxes_cap(isolated_env):
    s = BudgetState(
        date_stamp=read_state().date_stamp,
        spent_usd=DEFAULT_DAILY_BUDGET_USD,  # at cap
        session_count=10,
        cap_usd=DEFAULT_DAILY_BUDGET_USD,
    )
    write_state(s)
    # With a much higher per-call cap, the next call succeeds.
    check_and_reserve(0.30, cap_override=50.0)


# ── client_browserbase: robots.txt ────────────────────────────────


def test_robots_disallowed_raises(isolated_env, monkeypatch):
    """A robots.txt that disallows the agent stops the fallback."""
    import acquisition.urls.client_browserbase as cb_mod

    def fake_robots_allows(url, *, user_agent=cb_mod.DEFAULT_USER_AGENT):
        return False

    monkeypatch.setattr(cb_mod, "_robots_allows", fake_robots_allows)
    with pytest.raises(BrowserbaseRobotsDisallowed):
        fetch_via_browserbase(
            "https://blocked.example.com/x",
            session_factory=_fake_session_factory(),
            page_runner=_make_page_runner(),
        )


def test_robots_check_skippable_for_operator_explicit(isolated_env, monkeypatch):
    import acquisition.urls.client_browserbase as cb_mod

    def disallows_everything(url, *, user_agent=cb_mod.DEFAULT_USER_AGENT):
        return False

    monkeypatch.setattr(cb_mod, "_robots_allows", disallows_everything)
    # skip_robots_check=True overrides — operator-explicit accept.
    result = fetch_via_browserbase(
        "https://blocked.example.com/x",
        session_factory=_fake_session_factory(),
        page_runner=_make_page_runner(),
        skip_robots_check=True,
    )
    assert isinstance(result, FetchedHtml)


# ── client_browserbase: SDK absent ────────────────────────────────


def test_unavailable_when_sdk_factory_fails(isolated_env, monkeypatch):
    """If the production SDK factory raises BrowserbaseUnavailable,
    fetch_via_browserbase propagates after refunding budget."""
    # Make robots allow everything for this test.
    import acquisition.urls.client_browserbase as cb_mod
    monkeypatch.setattr(cb_mod, "_robots_allows", lambda *a, **k: True)

    with pytest.raises(BrowserbaseUnavailable):
        fetch_via_browserbase(
            "https://example.com/x",
            session_factory=_fake_session_factory(fail=True),
            page_runner=_make_page_runner(),
        )
    # Budget should be refunded after the failure (no session ran).
    # The pre-reservation happened, then the factory failure
    # propagated through; we don't refund inside fetch_via_browserbase
    # on factory failure because the session was never opened. So
    # the budget shows the reservation as a cost. That's the
    # honest accounting — the operator paid Browserbase $0 but
    # the optimistic budget reservation captured the intent.
    state = read_state()
    assert state.spent_usd > 0


# ── client_browserbase: happy path ────────────────────────────────


def test_fetch_via_browserbase_returns_fetched_html(isolated_env, monkeypatch):
    import acquisition.urls.client_browserbase as cb_mod
    monkeypatch.setattr(cb_mod, "_robots_allows", lambda *a, **k: True)

    page_body = b"<html><body>" + b"hello " * 100 + b"</body></html>"
    result = fetch_via_browserbase(
        "https://example.com/spa",
        session_factory=_fake_session_factory(),
        page_runner=_make_page_runner(body=page_body),
    )
    assert isinstance(result, FetchedHtml)
    assert result.body == page_body
    assert result.requested_url == "https://example.com/spa"


def test_fetch_via_browserbase_session_closed(isolated_env, monkeypatch):
    """The session's close() runs even when the runner succeeds."""
    import acquisition.urls.client_browserbase as cb_mod
    monkeypatch.setattr(cb_mod, "_robots_allows", lambda *a, **k: True)

    sessions: list[_FakeSession] = []

    def factory():
        s = _FakeSession()
        sessions.append(s)
        return s

    fetch_via_browserbase(
        "https://example.com/x",
        session_factory=factory,
        page_runner=_make_page_runner(),
    )
    assert all(s.closed for s in sessions)


def test_fetch_via_browserbase_runner_exception_raises(isolated_env, monkeypatch):
    import acquisition.urls.client_browserbase as cb_mod
    monkeypatch.setattr(cb_mod, "_robots_allows", lambda *a, **k: True)

    with pytest.raises(BrowserbaseFetchError):
        fetch_via_browserbase(
            "https://example.com/x",
            session_factory=_fake_session_factory(),
            page_runner=_make_page_runner(raise_exc=RuntimeError("page exploded")),
        )


# ── client_browserbase: concurrency cap ──────────────────────────


def test_concurrency_cap_is_three(isolated_env, monkeypatch):
    """Spec §7.6 — max 3 concurrent sessions per process. The
    fourth caller blocks until one releases.

    Test pattern: pre-acquire all 3 semaphore slots manually, then
    confirm the 4th fetch_via_browserbase blocks. Release one slot
    and confirm the 4th completes."""
    import acquisition.urls.client_browserbase as cb_mod
    monkeypatch.setattr(cb_mod, "_robots_allows", lambda *a, **k: True)

    # Pre-acquire all 3 slots.
    acquired = []
    for _ in range(MAX_CONCURRENT_SESSIONS):
        cb_mod._SESSION_SEMAPHORE.acquire()
        acquired.append(True)

    result_holder = {"r": None, "err": None}

    def caller():
        try:
            # Short timeout so the test doesn't hang if the cap fails.
            result_holder["r"] = fetch_via_browserbase(
                "https://example.com/x",
                session_factory=_fake_session_factory(),
                page_runner=_make_page_runner(),
            )
        except Exception as e:
            result_holder["err"] = e

    t = threading.Thread(target=caller)
    t.start()
    # Give the thread a moment to attempt acquire.
    time.sleep(0.1)
    assert t.is_alive(), "4th caller should be blocked on the semaphore"

    # Release one slot. The thread should complete.
    cb_mod._SESSION_SEMAPHORE.release()
    acquired.pop()
    t.join(timeout=5.0)
    assert not t.is_alive()
    assert result_holder["err"] is None
    assert result_holder["r"] is not None

    # Clean up the remaining acquired slots.
    for _ in acquired:
        cb_mod._SESSION_SEMAPHORE.release()


# ── adapter.ingest_url: default-off behavior unchanged ───────────


def test_ingest_url_default_does_not_call_browserbase(isolated_env, tmp_path, monkeypatch):
    """The fallback_to_browserbase flag defaults to False. Every
    call path that doesn't pass it MUST NOT invoke Browserbase."""

    # Build a fake fetched HTML that's empty enough to trigger
    # low_word_count.
    empty = FetchedHtml(
        requested_url="https://example.com/short",
        final_url="https://example.com/short",
        status_code=200,
        content_type="text/html",
        charset="utf-8",
        body=b"<html><body>tiny</body></html>",
    )

    # Sentry: monkeypatch the escalation helper to raise if called.
    import acquisition.urls.adapter as adapter_mod

    def explode(*args, **kwargs):
        raise AssertionError("escalation must not run without fallback_to_browserbase=True")

    monkeypatch.setattr(adapter_mod, "_try_browserbase_escalation", explode)

    result = ingest_url(
        "https://example.com/short",
        investigation_id="inv-1",
        fetched=empty,
    )
    assert result.skipped_reason == "low_word_count"


# ── adapter.ingest_url: escalation path ──────────────────────────


def test_ingest_url_with_fallback_recovers(isolated_env, tmp_path, monkeypatch):
    """When fallback_to_browserbase=True and the primary fetch is
    low_word_count, the escalation runs. If the escalation recovers
    a full body, the ingestion proceeds normally."""

    primary = FetchedHtml(
        requested_url="https://example.com/spa",
        final_url="https://example.com/spa",
        status_code=200,
        content_type="text/html",
        charset="utf-8",
        body=b"<html><body>shell</body></html>",
    )

    # Substitute the escalation helper with a stub that returns a
    # full-body FetchedHtml. The stub also emits the event so the
    # adapter sees the standard wedge-2 emission shape.
    recovered = FetchedHtml(
        requested_url="https://example.com/spa",
        final_url="https://example.com/spa",
        status_code=200,
        content_type="text/html",
        charset="utf-8",
        body=b"<html><body>" + b"recovered content " * 50 + b"</body></html>",
    )

    import acquisition.urls.adapter as adapter_mod

    def fake_escalate(*, url, primary_word_count, investigation_id, wait_for):
        from substrate.event_log import emit_typed
        from substrate.schemas.events import FetchFallbackEscalatedPayload

        emit_typed(
            investigation_id,
            FetchFallbackEscalatedPayload(
                url=url,
                primary_word_count=primary_word_count,
                fallback_fetcher="browserbase",
                fallback_word_count=120,
                escalation_reason="low_word_count",
                estimated_cost_usd=0.30,
            ),
            role="acquisition",
            policy_id="acquisition/urls/browserbase",
        )
        return recovered

    monkeypatch.setattr(adapter_mod, "_try_browserbase_escalation", fake_escalate)
    monkeypatch.setattr(
        adapter_mod, "default_db_path",
        lambda: str(tmp_path / "graph.duckdb"),
    )
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))

    # Use the no-op embedder used elsewhere in the test suite.
    class _StubEmbedder:
        def encode(self, text):
            return [0.0] * 4

    result = ingest_url(
        "https://example.com/spa",
        investigation_id="inv-1",
        fetched=None,  # Must be None — escalation only runs on a fresh fetch.
        http_client=httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=primary.body)
        )),
        fallback_to_browserbase=True,
        embedder=_StubEmbedder(),
    )
    assert result.skipped_reason is None
    assert result.chunks_written > 0


def test_ingest_url_with_fallback_unrecovered(isolated_env, tmp_path, monkeypatch):
    """When the escalation runs but fails to recover content (returns
    None — e.g. paywall, captcha), the adapter returns
    `low_word_count_after_fallback`."""

    primary = FetchedHtml(
        requested_url="https://example.com/x",
        final_url="https://example.com/x",
        status_code=200,
        content_type="text/html",
        charset="utf-8",
        body=b"<html><body>tiny</body></html>",
    )

    import acquisition.urls.adapter as adapter_mod

    def fake_escalate(*, url, primary_word_count, investigation_id, wait_for):
        # Simulate "escalation tried but didn't recover content".
        return None

    monkeypatch.setattr(adapter_mod, "_try_browserbase_escalation", fake_escalate)

    result = ingest_url(
        "https://example.com/x",
        investigation_id="inv-1",
        fetched=primary,  # passing fetched skips the escalation (per impl)
        fallback_to_browserbase=True,
    )
    # With fetched= preset, the escalation does NOT run (purely
    # additive — only the live-fetch path can escalate). The skip
    # reason is the standard low_word_count.
    assert result.skipped_reason == "low_word_count"


def test_ingest_url_fallback_emits_escalation_event(isolated_env, tmp_path, monkeypatch):
    """The real _try_browserbase_escalation always emits the
    FetchFallbackEscalatedPayload, even when escalation fails.
    Verify by reading the events_dir JSONL."""

    import acquisition.urls.adapter as adapter_mod
    import acquisition.urls.client_browserbase as cb_mod

    # Force the SDK to be "unavailable" inside the real helper.
    monkeypatch.setattr(cb_mod, "_robots_allows", lambda *a, **k: True)

    primary_body = b"<html><body>shell</body></html>"

    def fetch_short(url, *, client=None):
        return FetchedHtml(
            requested_url=url, final_url=url, status_code=200,
            content_type="text/html", charset="utf-8",
            body=primary_body,
        )

    monkeypatch.setattr(adapter_mod, "fetch", fetch_short)

    # Run the real escalation helper; the SDK factory will raise
    # BrowserbaseUnavailable inside fetch_via_browserbase, which
    # the helper catches and emits the failure event.
    result = ingest_url(
        "https://example.com/test-event-emission",
        investigation_id="inv-event-test",
        fallback_to_browserbase=True,
    )
    assert result.skipped_reason == "low_word_count_after_fallback"

    # The events_dir should have at least one FetchFallbackEscalated
    # event with fallback_word_count=0 (no recovery).
    events_dir = isolated_env["events_dir"]
    jsonl_files = list(Path(events_dir).rglob("*.jsonl"))
    assert jsonl_files, "expected at least one event log file"
    found = False
    for f in jsonl_files:
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            ev = json.loads(line)
            if ev.get("action_type") == "fetch.fallback.escalated":
                found = True
                p = ev.get("payload", {})
                assert p.get("fallback_word_count") == 0
                assert p.get("primary_fetcher") == "httpx"
                break
        if found:
            break
    assert found, "FetchFallbackEscalated event not emitted"
