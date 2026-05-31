"""SPR-09 M1 — the host-global arXiv rate governor.

The invariant: the >= 3s spacing + the 429 ``banned_until`` sentinel that
``ArxivThrottle`` enforces per-process must hold GLOBALLY across all arXiv jobs
on this host, because the throttle's read-modify-write of its shared JSON state
is explicitly UNLOCKED (last-writer-wins) — two concurrent jobs can otherwise
each read the same ``last_request_at`` and both fire inside one 3s window,
collectively breaching the rate limit that historically IP-banned the box.
``acquisition.arxiv.rate_governor`` closes this by serializing the throttle's
``wait_if_needed -> send -> note_response`` critical section under an exclusive
``fcntl.flock``.

Rigor #3 — each invariant ships a test that FAILS on a violating change and
PASSES once guarded:

  (a) SERIALIZATION. Two governors that share one throttle state file + one lock
      serialize: the second's recorded request time is >= the first's + the min
      spacing. The RED control proves the lock is load-bearing — two BARE
      throttles (the pre-governor world, no flock) reading the same state both
      record inside one window, so the second's time is NOT spaced from the
      first. The governor's flock is exactly what turns the RED into GREEN.
  (b) BAN SENTINEL ATOMICITY. A 429 noted by one governor is observed by a
      SECOND governor (a separate process would behave identically): the second
      raises ``ArxivBanned`` before sending. The RED control shows that without
      the ban sentinel a second job would re-hit the endpoint.
  (c) THE SCANNER HAS TEETH. ``tools/lint/rate_governor_check.py`` flags an
      injected ungoverned arxiv.org egress at its exact ``file:line`` and does
      NOT flag a governed/allowlisted call.

No test ever sleeps 3 real seconds: the throttle's clock + sleep are injected so
``sleep`` advances a fake clock (precedent: ``tools/arxiv_census.py`` throwaway
state + ``min_spacing_s=0``). The flock itself is REAL across both code paths.
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import threading
from pathlib import Path

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.rate_governor import (  # noqa: E402
    ArxivBanned,
    ArxivRateGovernor,
    GovernorLockTimeout,
    governed_request,
)
from acquisition.arxiv.throttle import ArxivThrottle  # noqa: E402
from tools.lint import rate_governor_check  # noqa: E402

_SPACING = 3.0


class _FakeClock:
    """A monotonic fake wall-clock. ``now()`` reads it; ``sleep(s)`` advances it
    by ``s`` (so the throttle's >=3s sleep moves time forward without blocking).
    Thread-safe so two governors can share one clock deterministically."""

    def __init__(self, start: float = 1000.0) -> None:
        self._t = float(start)
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._t

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self._t += max(0.0, float(seconds))


class _Resp:
    """Minimal ``_ResponseLike``: a status + headers, what the throttle inspects."""

    def __init__(self, status_code: int = 200, headers: dict | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


def _throttle(state_path: str, clock: _FakeClock) -> ArxivThrottle:
    return ArxivThrottle(
        state_path=state_path,
        min_spacing_s=_SPACING,
        now=clock.now,
        sleep=clock.sleep,
    )


@pytest.fixture
def paths(tmp_path: Path):
    """A shared throttle-state file + governor lock file (both initially
    absent), the way two host jobs share ``~/.antiek/arxiv_throttle.json`` +
    its sidecar lock."""
    state = str(tmp_path / "arxiv_throttle.json")
    lock = str(tmp_path / "arxiv_throttle.json.governor.lock")
    return state, lock


# ── (a) SERIALIZATION: the governor's flock makes the >=3s gate global ──────


def test_two_governors_sharing_state_serialize_to_min_spacing(paths):
    """GREEN: two governors over ONE shared state file + ONE lock record their
    requests at least ``_SPACING`` apart. Because the second governor cannot
    enter the throttle's read->space->write until the first has RELEASED the
    flock (and therefore WRITTEN ``last_request_at``), it observes the first's
    recorded time and spaces off it — so the second's recorded time is
    >= first + _SPACING. Sequential acquisition of the same lock models two
    jobs that contend for it."""
    state, lock = paths
    clock = _FakeClock()

    g1 = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)
    r1 = g1.governed_request(lambda: _Resp(200))
    assert r1.status_code == 200
    t_after_first = _read_last_request_at(state)

    # A SECOND governor (separate throttle instance, same files) — the second job.
    g2 = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)
    g2.governed_request(lambda: _Resp(200))
    t_after_second = _read_last_request_at(state)

    assert t_after_second >= t_after_first + _SPACING, (
        f"second governed request recorded at {t_after_second} is not spaced "
        f">= {_SPACING}s after the first at {t_after_first} — the global gate "
        f"failed"
    )


def test_red_control_bare_throttles_can_collide_in_one_window(paths):
    """RED control — proves the lock is load-bearing, not decorative.

    This faithfully reproduces the documented unlocked read-modify-write race
    (``throttle.py`` docstring lines 18-23: "two processes that interleave are
    last-writer-wins"). Two BARE throttles over the same state file, NO flock.
    We force the exact interleave the lock would forbid: BOTH jobs READ the
    shared state (last_request_at = 0) BEFORE either has WRITTEN — so both see a
    huge elapsed, both decide they may fire WITHOUT spacing, and both record a
    request at the SAME clock value. The two requests are therefore 0s apart,
    NOT >= _SPACING. The governor's flock (held across the whole read->write)
    makes this interleave impossible — see the GREEN serialization test, where
    the same two throttles end up >= _SPACING apart.

    We drive the interleave through the throttle's own state primitives
    (``_read_state`` / ``_write_state``) so the race is deterministic rather than
    timing-dependent — this is precisely the in-process equivalent of two OS
    processes whose ``wait_if_needed`` bodies interleave."""
    state, _lock = paths
    clock = _FakeClock()
    t_a = _throttle(state, clock)
    t_b = _throttle(state, clock)

    # --- the unlocked interleave, step by step ---
    # A reads state (last=0). elapsed = now - 0 = huge >= spacing -> A may fire.
    sa = t_a._read_state()
    now_a = clock.now()
    assert now_a - sa.last_request_at >= _SPACING  # A passes the gate, no sleep

    # B reads the SAME state BEFORE A has written (the race). B also sees last=0.
    sb = t_b._read_state()
    now_b = clock.now()
    assert now_b - sb.last_request_at >= _SPACING  # B ALSO passes, no sleep

    # Both now write their request time (last-writer-wins). No spacing was forced.
    sa.last_request_at = now_a
    t_a._write_state(sa)
    sb.last_request_at = now_b
    t_b._write_state(sb)

    # The two requests fired _SPACING-violatingly close (here: 0s apart).
    assert abs(now_b - now_a) < _SPACING, (
        "RED control expected a sub-spacing collision in the unlocked path; if "
        "this assertion fails the control is no longer demonstrating the hole"
    )


def test_governor_holds_the_lock_across_the_whole_gate(paths):
    """The flock is held across the ENTIRE wait+record (not just the write): a
    second governor attempting to acquire the lock while the first is mid-gate
    times out. Proven by giving the second a ~0 timeout while the first holds the
    lock in another thread — it must raise ``GovernorLockTimeout``. If the lock
    were released between wait and record (or never taken), the second would NOT
    time out and this test fails."""
    state, lock = paths
    clock = _FakeClock()

    holding = threading.Event()
    release = threading.Event()

    def _hold():
        g = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)

        def _send():
            holding.set()
            release.wait(timeout=5.0)  # keep the gate (and thus the flock) open
            return _Resp(200)

        g.governed_request(_send)

    t = threading.Thread(target=_hold)
    t.start()
    assert holding.wait(timeout=5.0), "holder never entered the gate"

    # A second governor with an effectively-zero lock timeout must fail to enter
    # while the first holds the flock.
    g2 = ArxivRateGovernor(
        throttle=_throttle(state, clock),
        lock_path=lock,
        lock_timeout_s=0.0,
        lock_poll_interval_s=0.0,
    )
    with pytest.raises(GovernorLockTimeout):
        g2.governed_request(lambda: _Resp(200))

    release.set()
    t.join(timeout=5.0)
    assert not t.is_alive()


# ── (b) BAN SENTINEL observed atomically by a second governor ───────────────


def test_ban_sentinel_written_by_one_governor_seen_by_another(paths):
    """GREEN: a 429 noted while the first governor holds the lock writes
    ``banned_until`` to the shared state; a SECOND governor (separate process in
    prod) then raises ``ArxivBanned`` BEFORE sending — it never re-hits the
    banned endpoint. The flock guarantees the ban write and the subsequent read
    cannot interleave."""
    state, lock = paths
    clock = _FakeClock()

    g1 = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)
    # First request comes back 429 -> note_response writes banned_until.
    g1.governed_request(lambda: _Resp(429, {"Retry-After": "600"}))

    g2 = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)
    sent = {"hit": False}

    def _send():
        sent["hit"] = True
        return _Resp(200)

    with pytest.raises(ArxivBanned):
        g2.governed_request(_send)
    assert sent["hit"] is False, (
        "second governor SENT despite an active ban — the ban sentinel was not "
        "observed atomically across governors"
    )


def test_red_control_without_ban_note_a_second_job_would_re_hit(paths):
    """RED control: if the 429 is NOT noted (the pre-sentinel world), a second
    governor has no ban to observe and proceeds to SEND — exactly the re-hit that
    extends an IP ban. Contrast with the GREEN test above where note_response
    persisted the sentinel and the second job paused."""
    state, lock = paths
    clock = _FakeClock()

    # First job gets a 429 but (the bug) never feeds it back — simulate by
    # sending a request whose 429 we drop on the floor. We call the throttle's
    # wait+send WITHOUT note_response by sending a 200 (no sentinel written).
    g1 = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)
    g1.governed_request(lambda: _Resp(200))  # no ban recorded

    g2 = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)
    sent = {"hit": False}

    def _send():
        sent["hit"] = True
        return _Resp(200)

    # No ban => no ArxivBanned => the second job SENDS (the hole the sentinel
    # closes). This is the negative the GREEN test guards against.
    g2.governed_request(_send)
    assert sent["hit"] is True


def test_governed_request_convenience_routes_through_a_governor(paths):
    """The module-level ``governed_request`` helper applies the same gate: a ban
    written via a governor is honored when a later call reuses that governor."""
    state, lock = paths
    clock = _FakeClock()
    gov = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)

    governed_request(lambda: _Resp(429, {"Retry-After": "600"}), governor=gov)
    with pytest.raises(ArxivBanned):
        governed_request(lambda: _Resp(200), governor=gov)


# ── (c) THE SCANNER: clean on the tree + has teeth ──────────────────────────


def test_scanner_reports_zero_violations_on_the_current_tree():
    """The boundary holds under a pytest-only run: invoke the scanner
    programmatically and assert ZERO ungoverned arxiv egress on the real tree."""
    violations = rate_governor_check.find_violations()
    assert violations == [], (
        "ungoverned arxiv.org egress found:\n" + "\n".join(violations)
    )


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_scanner_catches_the_DYNAMIC_URL_raw_httpx_pattern():
    """RIGOR #3 (round-3) — the redesigned scanner catches the DYNAMIC-URL raw
    httpx egress that the round-2 (URL-literal) scanner MISSED on
    ``client._http_get``.

    The offender's URL is a FUNCTION RETURN VALUE (``_build_url(...)``), never a
    static ``arxiv.org`` literal near the call — exactly the shape that bypassed
    the old scanner. The robust scanner keys on the raw httpx egress in an
    arXiv-egress module (NOT on the URL), so it flags it at file:line REGARDLESS of
    the URL value. A ``governed_request(send, ...)`` form in the same module is NOT
    flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # (1) THE DYNAMIC-URL BYPASS — a raw httpx GET whose URL is a return value,
        # in an arXiv-egress module. The round-2 URL-literal scanner missed this.
        _write(
            root,
            "acquisition/arxiv/rogue_client.py",
            """\
            import httpx
            from typing import Optional

            def _build_url(q):
                return "https://export.arxiv.org/api/query?search_query=" + q

            def search(q, *, client: Optional[httpx.Client] = None):
                url = _build_url(q)
                if client is not None:
                    r = client.get(url, timeout=15)
                    return r.content
                with httpx.Client() as c:
                    return c.get(url, timeout=15).content
            """,
        )

        # (2) A GOVERNED caller in the same package — the send closure (with a
        # dynamic URL too) is handed to governed_request → NOT flagged.
        _write(
            root,
            "acquisition/arxiv/good_client.py",
            """\
            import httpx
            from typing import Optional
            from acquisition.arxiv.rate_governor import governed_request

            def _build_url(q):
                return "https://export.arxiv.org/api/query?q=" + q

            def search(q, *, client: Optional[httpx.Client] = None, throttle=None):
                url = _build_url(q)
                def _send():
                    if client is not None:
                        return client.get(url, timeout=15)
                    with httpx.Client() as c:
                        return c.get(url, timeout=15)
                r = governed_request(_send, throttle=throttle)
                return r.content
            """,
        )

        violations = rate_governor_check.find_violations(root=root)

    # The dynamic-URL offender flags (its TWO raw egresses: client.get + c.get);
    # the governed caller does not.
    flagged_paths = {line.split(":", 1)[0] for line in violations}
    assert flagged_paths == {"acquisition/arxiv/rogue_client.py"}, violations
    # Both raw egresses in the offender are caught (with-block c.get + client.get).
    assert len(violations) == 2, violations


def test_scanner_does_not_flag_dict_or_xml_get_false_positives():
    """The robust scanner keys on a client-shaped RECEIVER, so a dict ``.get`` /
    XML-element ``.get`` / ``.find`` in an arXiv module (``raw_work.get(...)`` /
    ``element.get("status")``) is NEVER flagged — these are not HTTP clients. This
    guards the false-positive class the receiver-shape check exists to kill."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(
            root,
            "acquisition/arxiv/parsers.py",
            """\
            import os

            def parse(raw_work, element, headers):
                a = raw_work.get("authorships")          # dict .get
                b = element.get("status")                # XML-element .get
                c = headers.get("content-type")          # mapping .get
                d = os.environ.get("ANTIEK_ARXIV_BASE_URL", "x")
                e = element.request                      # attribute, not a call
                return (a, b, c, d, e)
            """,
        )
        assert rate_governor_check.find_violations(root=root) == []


def test_scanner_scope_is_the_acquisition_tree_not_tools():
    """HOST-based scope (round-4): the scanner binds the WHOLE acquisition tree,
    but ``tools/`` is out of scope (its only HTTP is a localhost demo client to
    the Antiek API — no arXiv egress). A raw httpx egress in a ``tools/`` script
    is therefore NOT flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(
            root,
            "tools/some_scraper.py",
            """\
            import httpx

            def grab(url):
                with httpx.Client() as c:
                    return c.get(url).content
            """,
        )
        assert rate_governor_check.find_violations(root=root) == []


def test_scanner_no_longer_directory_allowlists_books_public_domain():
    """ROUND-4 — ``acquisition/books/public_domain.py`` is NO LONGER allowlisted
    by directory/name. A raw, ungoverned external egress there (an
    annotated-``requests.Session`` receiver NOT routed through the governor) now
    FLAGS, exactly like any other acquisition fetcher — the structural cause of
    the recurring misses (a whole-directory exception) is gone. Routing the same
    send through ``govern_if_arxiv`` makes it clean again."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # (1) RAW annotated-session egress in books/ — now FLAGGED (was allowlisted).
        _write(
            root,
            "acquisition/books/public_domain.py",
            """\
            import requests
            from typing import Optional

            def fetch(url, session: requests.Session):
                return session.get(url, timeout=30).content
            """,
        )
        flagged = rate_governor_check.find_violations(root=root)
        assert len(flagged) == 1, flagged
        assert flagged[0].startswith("acquisition/books/public_domain.py:"), flagged

        # (2) The SAME send routed through govern_if_arxiv — clean.
        _write(
            root,
            "acquisition/books/public_domain.py",
            """\
            import requests
            from typing import Optional
            from acquisition.arxiv.rate_governor import govern_if_arxiv, canonical_arxiv_throttle

            def fetch(url, session: requests.Session):
                def _send():
                    return session.get(url, timeout=30)
                r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
                return r.content
            """,
        )
        assert rate_governor_check.find_violations(root=root) == []


def test_scanner_catches_an_arxiv_host_egress_OUTSIDE_acquisition_arxiv():
    """RIGOR #3 (round-4) — THE root self-test: the host-based scanner flags a raw
    external fetcher that lives OUTSIDE ``acquisition/arxiv/`` (a synthetic
    ``acquisition/openaccess/rogue.py``) and is NOT routed through
    ``govern_if_arxiv`` — the EXACT structural class the directory-scoped scanner
    was blind to (the round-3 ``unpaywall.download_pdf`` bypass). The
    ``govern_if_arxiv(url, send)`` form in the same package is NOT flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # (1) ROGUE — a raw httpx GET of a runtime URL (could be arxiv.org/pdf),
        # in acquisition/openaccess/ — OUTSIDE acquisition/arxiv/. MUST flag.
        _write(
            root,
            "acquisition/openaccess/rogue.py",
            """\
            import httpx
            from typing import Optional

            def download_pdf(pdf_url, *, client: Optional[httpx.Client] = None):
                if client is not None:
                    return client.get(pdf_url, timeout=15).content
                with httpx.Client() as c:
                    return c.get(pdf_url, timeout=15).content
            """,
        )
        # (2) GOOD — the same fetch routed through govern_if_arxiv. NOT flagged.
        _write(
            root,
            "acquisition/openaccess/good.py",
            """\
            import httpx
            from typing import Optional
            from acquisition.arxiv.rate_governor import govern_if_arxiv, canonical_arxiv_throttle

            def download_pdf(pdf_url, *, client: Optional[httpx.Client] = None):
                def _send():
                    if client is not None:
                        return client.get(pdf_url, timeout=15)
                    with httpx.Client() as c:
                        return c.get(pdf_url, timeout=15)
                r = govern_if_arxiv(pdf_url, _send, throttle=canonical_arxiv_throttle())
                return r.content
            """,
        )
        violations = rate_governor_check.find_violations(root=root)

    flagged_paths = {line.split(":", 1)[0] for line in violations}
    assert flagged_paths == {"acquisition/openaccess/rogue.py"}, violations
    # Both raw egresses in the rogue (client.get + c.get) are caught.
    assert len(violations) == 2, violations


def test_scanner_proves_it_would_have_caught_the_round3_unpaywall_bypass():
    """RIGOR #3 (round-4) — run the host-based scanner against the PRE-FIX SHAPE of
    ``acquisition/openaccess/unpaywall.py::download_pdf`` (the raw ``client.get`` /
    ``c.get`` of ``pdf_url`` under the OA throttle, no governor). It MUST flag both
    raw egresses — proving the redesigned scanner closes the structural hole the
    directory-scoped scanner exited 0 on."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(
            root,
            "acquisition/openaccess/unpaywall.py",
            """\
            import httpx
            from typing import Optional

            def download_pdf(pdf_url, *, client: Optional[httpx.Client] = None, throttle=None):
                def _get():
                    headers = {"User-Agent": "x"}
                    if client is not None:
                        r = client.get(pdf_url, headers=headers, timeout=15)
                    else:
                        with httpx.Client(follow_redirects=True) as c:
                            r = c.get(pdf_url, headers=headers, timeout=15)
                    r.raise_for_status()
                    return r.content
                return throttle.run_with_retry(_get) if throttle is not None else _get()
            """,
        )
        violations = rate_governor_check.find_violations(root=root)
    assert len(violations) == 2, violations
    assert all(
        line.startswith("acquisition/openaccess/unpaywall.py:") for line in violations
    ), violations


def test_scanner_scope_covers_substrate_graph_rogue_fetcher():
    """RIGOR #3 (round-5) — the scanner scope now includes ``substrate/graph/`` so
    a raw external fetcher exported OUTSIDE the acquisition tree (the structural
    class of the LLM-callable ``rlm_tools.fetch_url`` builtin) is flagged. A
    synthetic ``substrate/graph/rogue_tool.py`` with a raw ``requests.get`` of an
    arbitrary URL MUST flag; the same fetch routed through ``govern_if_arxiv`` is
    clean. Proves the extended ``_EGRESS_SCAN_DIRS`` has teeth on the exact surface
    section 2 closes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # (1) ROGUE — a raw requests.get of an arbitrary (LLM-supplied) URL in
        # substrate/graph/, OUTSIDE acquisition/. MUST flag now.
        _write(
            root,
            "substrate/graph/rogue_tool.py",
            """\
            import requests

            def fetch_url(url):
                r = requests.get(url, timeout=20, allow_redirects=True)
                return r.text
            """,
        )
        # (2) GOOD — the same fetch routed through govern_if_arxiv. NOT flagged.
        _write(
            root,
            "substrate/graph/good_tool.py",
            """\
            import requests
            from acquisition.arxiv.rate_governor import govern_if_arxiv, canonical_arxiv_throttle

            def fetch_url(url):
                def _send():
                    return requests.get(url, timeout=20, allow_redirects=False)
                r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
                return r.text
            """,
        )
        # (3) A dict / connection .get / .execute in substrate/graph must NOT flag
        # (receiver-shape check — these are not httpx/requests clients).
        _write(
            root,
            "substrate/graph/parsers.py",
            """\
            def use(row, con, mapping):
                a = row.get("title")
                b = con.execute("select 1")
                c = mapping.get("k")
                return (a, b, c)
            """,
        )
        violations = rate_governor_check.find_violations(root=root)

    flagged_paths = {line.split(":", 1)[0] for line in violations}
    assert flagged_paths == {"substrate/graph/rogue_tool.py"}, violations
    assert len(violations) == 1, violations


def test_scanner_flags_a_bare_module_level_httpx_get_in_arxiv():
    """A direct ``httpx.get(...)`` / ``requests.post(...)`` (module receiver, no
    Client object) in an arXiv module is still a raw egress and is flagged —
    the receiver-shape match covers the module form too, with any URL."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(
            root,
            "acquisition/arxiv/blunt.py",
            """\
            import httpx

            def grab(some_url):
                return httpx.get(some_url, timeout=15).content
            """,
        )
        violations = rate_governor_check.find_violations(root=root)
        assert len(violations) == 1, violations
        assert violations[0].startswith("acquisition/arxiv/blunt.py:")


# ════════════════════════════════════════════════════════════════════════════
# (d) CALLER-LEVEL WIRING — the PRIMARY egress paths route through the governor
# ════════════════════════════════════════════════════════════════════════════
#
# The tests above exercise the governor in ISOLATION; they would stay green even
# if a caller bypassed it (the M1 send-back). These tests drive the REAL primary
# callers — ``OaiPmhHarvester._fetch_page`` (the busiest path) and
# ``acquisition.arxiv.pdf_fetch.fetch_pdf`` (SPR-04's on-demand fetch) — and
# prove that the harvester/fetcher's HTTP send happens INSIDE the host-global
# governor flock. The mutation control is explicit: each test names the one-line
# source edit that removes the governor wrapping from the caller and asserts the
# test would go RED (it was confirmed RED by performing that mutation, observing
# the failure, and reverting — see the SPR-09 round-2 handoff).
#
# No real 3s sleep: the throttle's clock + sleep are injected (the _FakeClock
# above). The flock is the REAL ``fcntl.flock`` shared via an explicit lock path.


import httpx  # noqa: E402

from acquisition.arxiv import client as arxiv_client  # noqa: E402
from acquisition.arxiv.oai_pmh import OaiPmhHarvester  # noqa: E402
from acquisition.arxiv.pdf_fetch import MIN_PDF_BYTES, fetch_pdf  # noqa: E402

_OAI_NS = 'xmlns="http://www.openarchives.org/OAI/2.0/"'
_VALID_PDF = b"%PDF-1.4\n" + b"x" * (MIN_PDF_BYTES + 64)


def _atom_feed(arxiv_id: str = "2401.00001") -> bytes:
    """A one-entry arXiv Atom feed — enough for ``client.search`` /
    ``client.fetch_by_id`` to parse exactly one paper from a single GET."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <entry>\n"
        f"    <id>http://arxiv.org/abs/{arxiv_id}v1</id>\n"
        "    <title>A Paper</title>\n"
        "    <summary>An abstract.</summary>\n"
        "    <published>2024-01-01T00:00:00Z</published>\n"
        "    <updated>2024-01-01T00:00:00Z</updated>\n"
        "    <author><name>Auth</name></author>\n"
        "  </entry>\n"
        "</feed>"
    ).encode()


@pytest.fixture
def canonical_lock(paths, monkeypatch):
    """Point the governor's CANONICAL default lock path
    (``acquisition.arxiv.rate_governor.default_lock_path``, via
    ``ANTIEK_ARXIV_GOVERNOR_LOCK_PATH``) at the test's temp lock file.

    The PRIMARY callers (``OaiPmhHarvester._fetch_page`` /
    ``pdf_fetch.fetch_pdf``) route their send through
    ``governed_request(send, throttle=...)``, which builds a one-shot governor on
    the CANONICAL default lock (this is exactly what makes the gate host-global in
    prod — every job contends on ``~/.antiek/arxiv_throttle.json.governor.lock``).
    Setting the env var makes that canonical lock be our temp lock, so a probe
    governor in the test contends on the SAME flock the caller acquires — which is
    how we prove the caller's send is governed."""
    _state, lock = paths
    monkeypatch.setenv("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", lock)
    return lock


def _single_oai_page() -> bytes:
    """A one-page OAI ListRecords response (empty resumptionToken => last page),
    enough for the harvester to issue exactly ONE governed send and stop."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<OAI-PMH {_OAI_NS}>\n"
        "  <responseDate>2026-05-30T00:00:00Z</responseDate>\n"
        "  <ListRecords></ListRecords>\n"
        "</OAI-PMH>"
    ).encode()


def test_oai_harvest_send_is_inside_the_host_global_governor_flock(paths, canonical_lock):
    """BLOCKING M1 — prove the OAI harvester's REAL send is held under the
    host-global governor flock (not the bare throttle).

    While the harvester is mid-``_fetch_page`` (blocked inside its MockTransport
    handler, i.e. inside ``send()``), a SECOND governor pointed at the SAME lock
    with an effectively-zero timeout MUST raise ``GovernorLockTimeout`` — which is
    only possible if the harvester is holding that flock for the duration of its
    send. The existing isolation tests could not catch the send-back because they
    never drove the harvester; this one does.

    RED-THEN-GREEN AT THE CALLER (verified): mutate
    ``acquisition/arxiv/oai_pmh.py::_fetch_page`` to call the BARE
    ``self._throttle.request(send)`` instead of
    ``governed_request(send, throttle=self._throttle)`` and this test goes RED —
    no flock is held during the harvester's send, so the second governor acquires
    the lock instead of timing out (the ``GovernorLockTimeout`` is never raised).
    Reverting (the governed wiring) makes it GREEN."""
    state, lock = paths
    clock = _FakeClock()

    holding = threading.Event()
    release = threading.Event()

    def _handler(req: httpx.Request) -> httpx.Response:
        # We are now INSIDE the harvester's governed send (the governor holds the
        # flock around exactly this call). Signal + block so the test can probe
        # the lock while it is held.
        holding.set()
        release.wait(timeout=5.0)
        return httpx.Response(200, content=_single_oai_page())

    def _run_harvest():
        h = OaiPmhHarvester(
            throttle=_throttle(state, clock),
            client=httpx.Client(transport=httpx.MockTransport(_handler), timeout=5.0),
            base_url="https://oai.test/oai2",
            state_path=state + ".harvest.json",
        )
        list(h.harvest(from_date="2024-01-01"))

    t = threading.Thread(target=_run_harvest)
    t.start()
    try:
        assert holding.wait(timeout=5.0), "harvester never entered its send"
        # The harvester is mid-send. A second governor on the SAME lock with a
        # ~0 timeout must fail to enter — proof the harvester's send is governed.
        g2 = ArxivRateGovernor(
            throttle=_throttle(state, clock),
            lock_path=lock,
            lock_timeout_s=0.0,
            lock_poll_interval_s=0.0,
        )
        with pytest.raises(GovernorLockTimeout):
            g2.governed_request(lambda: _Resp(200))
    finally:
        release.set()
        t.join(timeout=5.0)
    assert not t.is_alive()


def test_pdf_fetch_send_is_inside_the_host_global_governor_flock(paths, canonical_lock):
    """BLOCKING M1 — prove SPR-04's on-demand ``fetch_pdf`` REAL send is held
    under the host-global governor flock (not the bare throttle).

    Same probe as the harvester test, against the OTHER primary path: while
    ``fetch_pdf`` is mid-send (blocked in its MockTransport handler), a second
    governor on the same lock with a ~0 timeout MUST ``GovernorLockTimeout``.

    RED-THEN-GREEN AT THE CALLER (verified): mutate
    ``acquisition/arxiv/pdf_fetch.py::fetch_pdf`` to call the BARE
    ``throttle.request(_send)`` instead of
    ``governed_request(_send, throttle=throttle)`` and this test goes RED — the
    second governor acquires the lock (no timeout) because the fetch's send is no
    longer inside the flock. Reverting makes it GREEN."""
    state, lock = paths
    clock = _FakeClock()

    holding = threading.Event()
    release = threading.Event()

    def _handler(req: httpx.Request) -> httpx.Response:
        holding.set()
        release.wait(timeout=5.0)
        return httpx.Response(200, content=_VALID_PDF, headers={"content-type": "application/pdf"})

    def _run_fetch():
        client = httpx.Client(transport=httpx.MockTransport(_handler), timeout=5.0)
        fetch_pdf("2401.00001", throttle=_throttle(state, clock), client=client)

    t = threading.Thread(target=_run_fetch)
    t.start()
    try:
        assert holding.wait(timeout=5.0), "fetch_pdf never entered its send"
        g2 = ArxivRateGovernor(
            throttle=_throttle(state, clock),
            lock_path=lock,
            lock_timeout_s=0.0,
            lock_poll_interval_s=0.0,
        )
        with pytest.raises(GovernorLockTimeout):
            g2.governed_request(lambda: _Resp(200))
    finally:
        release.set()
        t.join(timeout=5.0)
    assert not t.is_alive()


def test_concurrent_harvest_and_pdf_fetch_serialize_to_min_spacing(paths, canonical_lock):
    """BLOCKING M1 — two concurrent PRIMARY-path jobs (an OAI harvest and an
    on-demand ``fetch_pdf``) sharing ONE throttle state + ONE governor lock record
    their requests >= the min spacing apart.

    The harvest enters first and holds the gate (its handler blocks until the
    fetch thread is confirmed queued ON THE FLOCK). The fetch cannot record its
    request time until the harvest releases the flock — at which point it observes
    the harvest's persisted ``last_request_at`` and the throttle spaces it off by
    >= _SPACING. This is the end-to-end demonstration that the two busiest egress
    paths contend on the SAME host-global gate (not two independent in-process
    timers, the historical IP-ban hole).

    Both request times are read from the SHARED throttle state (the value the
    throttle persisted under the flock), so the assertion is on the real recorded
    spacing, not a proxy."""
    state, lock = paths
    clock = _FakeClock()

    harvest_entered = threading.Event()
    fetch_queued = threading.Event()

    def _oai_handler(req: httpx.Request) -> httpx.Response:
        # Harvest is inside the governed send holding the flock. Wait until the
        # fetch thread has begun contending for the SAME lock, then release —
        # guaranteeing the fetch must space off the harvest's recorded time.
        harvest_entered.set()
        fetch_queued.wait(timeout=5.0)
        return httpx.Response(200, content=_single_oai_page())

    def _run_harvest():
        h = OaiPmhHarvester(
            throttle=_throttle(state, clock),
            client=httpx.Client(transport=httpx.MockTransport(_oai_handler), timeout=5.0),
            base_url="https://oai.test/oai2",
            state_path=state + ".harvest.json",
        )
        list(h.harvest(from_date="2024-01-01"))

    th = threading.Thread(target=_run_harvest)
    th.start()
    assert harvest_entered.wait(timeout=5.0), "harvest never entered its send"
    t_harvest = _read_last_request_at(state)  # recorded under the flock

    def _pdf_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_VALID_PDF, headers={"content-type": "application/pdf"}
        )

    fetch_done = threading.Event()

    def _run_fetch():
        client = httpx.Client(transport=httpx.MockTransport(_pdf_handler), timeout=5.0)
        # Signal that we are about to contend for the lock, then call the real
        # fetcher (which blocks on the flock the harvest holds).
        fetch_queued.set()
        fetch_pdf("2401.00001", throttle=_throttle(state, clock), client=client)
        fetch_done.set()

    tf = threading.Thread(target=_run_fetch)
    tf.start()
    th.join(timeout=5.0)
    assert fetch_done.wait(timeout=5.0), "fetch never completed (deadlock?)"
    tf.join(timeout=5.0)
    assert not th.is_alive() and not tf.is_alive()

    t_fetch = _read_last_request_at(state)
    assert t_fetch >= t_harvest + _SPACING, (
        f"the on-demand fetch recorded at {t_fetch} is not spaced >= {_SPACING}s "
        f"after the concurrent harvest at {t_harvest} — the two primary egress "
        f"paths did not contend on the host-global gate"
    )


def test_client_search_send_is_inside_the_host_global_governor_flock(paths, canonical_lock):
    """BLOCKING M1 (round-3) — prove the REAL export-SEARCH egress
    (``client.search``) is held under the host-global governor flock.

    This is the 4th, previously-UNGOVERNED arXiv egress: ``client._http_get``
    issued a BARE ``httpx`` GET to ``export.arxiv.org/api/query`` (the endpoint
    that historically IP-banned the box) with no governor and no flock. The
    per-call ``throttle.wait_if_needed()`` the CLIs did was the exact bare
    in-process pattern M1 declared insufficient — two host jobs (a search + an OAI
    harvest) could both fire in one 3s window. The fix routes ``_http_get``'s send
    through ``governed_request``.

    Same probe as the harvester / fetch tests: while ``client.search`` is mid-send
    (blocked in its MockTransport handler), a SECOND governor on the SAME canonical
    lock with a ~0 timeout MUST raise ``GovernorLockTimeout`` — which is only
    possible if the search's send is inside the governor flock. The earlier
    isolation tests never drove ``client.search``, which is why the bypass survived
    to round-3; this drives the REAL ``client.search``.

    RED-THEN-GREEN AT THE CALLER (verified): mutate
    ``acquisition/arxiv/client.py::_http_get`` to issue the BARE
    ``client.get(...)`` / ``c.get(...)`` instead of routing through
    ``governed_request(_send, throttle=throttle)`` and this test goes RED — the
    second governor acquires the lock (no timeout) because the search's send is no
    longer inside the flock. Reverting (the governed wiring) makes it GREEN."""
    state, lock = paths
    clock = _FakeClock()

    holding = threading.Event()
    release = threading.Event()

    def _handler(req: httpx.Request) -> httpx.Response:
        # Inside the search's governed send — the governor holds the flock here.
        holding.set()
        release.wait(timeout=5.0)
        return httpx.Response(200, content=_atom_feed())

    def _run_search():
        c = httpx.Client(transport=httpx.MockTransport(_handler), timeout=5.0)
        arxiv_client.search(
            query="anything",
            client=c,
            base_url="https://export.arxiv.test/api/query",
            throttle=_throttle(state, clock),
        )

    t = threading.Thread(target=_run_search)
    t.start()
    try:
        assert holding.wait(timeout=5.0), "client.search never entered its send"
        g2 = ArxivRateGovernor(
            throttle=_throttle(state, clock),
            lock_path=lock,
            lock_timeout_s=0.0,
            lock_poll_interval_s=0.0,
        )
        with pytest.raises(GovernorLockTimeout):
            g2.governed_request(lambda: _Resp(200))
    finally:
        release.set()
        t.join(timeout=5.0)
    assert not t.is_alive()


def test_concurrent_search_and_harvest_serialize_to_min_spacing(paths, canonical_lock):
    """BLOCKING M1 (round-3) — a ``client.search`` running CONCURRENTLY with an
    OAI harvest, sharing the canonical throttle state + governor lock, records its
    request >= the min spacing after the harvest.

    This is the project-existential scenario the round-2 fixes left open: two host
    jobs where ONE is the export-search API. The harvest enters first and holds the
    gate (its handler blocks until the search thread is confirmed contending on the
    flock); the search cannot record its request time until the harvest releases
    the flock, at which point it observes the harvest's persisted
    ``last_request_at`` and spaces off it by >= _SPACING.

    Both request times are read from the SHARED throttle state, so the assertion is
    on the real recorded spacing — proof the export-search egress contends on the
    SAME host-global gate as the harvest (not an independent in-process timer, the
    historical IP-ban hole)."""
    state, lock = paths
    clock = _FakeClock()

    harvest_entered = threading.Event()
    search_queued = threading.Event()

    def _oai_handler(req: httpx.Request) -> httpx.Response:
        harvest_entered.set()
        search_queued.wait(timeout=5.0)
        return httpx.Response(200, content=_single_oai_page())

    def _run_harvest():
        h = OaiPmhHarvester(
            throttle=_throttle(state, clock),
            client=httpx.Client(transport=httpx.MockTransport(_oai_handler), timeout=5.0),
            base_url="https://oai.test/oai2",
            state_path=state + ".harvest.json",
        )
        list(h.harvest(from_date="2024-01-01"))

    th = threading.Thread(target=_run_harvest)
    th.start()
    assert harvest_entered.wait(timeout=5.0), "harvest never entered its send"
    t_harvest = _read_last_request_at(state)  # recorded under the flock

    def _search_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_atom_feed())

    search_done = threading.Event()

    def _run_search():
        c = httpx.Client(transport=httpx.MockTransport(_search_handler), timeout=5.0)
        search_queued.set()
        arxiv_client.search(
            query="quantum",
            client=c,
            base_url="https://export.arxiv.test/api/query",
            throttle=_throttle(state, clock),
        )
        search_done.set()

    ts = threading.Thread(target=_run_search)
    ts.start()
    th.join(timeout=5.0)
    assert search_done.wait(timeout=5.0), "search never completed (deadlock?)"
    ts.join(timeout=5.0)
    assert not th.is_alive() and not ts.is_alive()

    t_search = _read_last_request_at(state)
    assert t_search >= t_harvest + _SPACING, (
        f"the export-search request recorded at {t_search} is not spaced "
        f">= {_SPACING}s after the concurrent harvest at {t_harvest} — the "
        f"export-search egress did not contend on the host-global gate"
    )


# ════════════════════════════════════════════════════════════════════════════
# (e) THE ROOT — host-based govern_if_arxiv at a NON-arXiv-directory fetch
#     boundary (SPR-09 round-4)
# ════════════════════════════════════════════════════════════════════════════
#
# The round-3 fix governed the four arXiv-DIRECTORY seams. Round-4 closes the
# STRUCTURAL hole: an arXiv-HOST fetch that lives OUTSIDE acquisition/arxiv/ —
# ``acquisition.openaccess.unpaywall.download_pdf`` fetching arxiv.org/pdf/<id>
# for an OpenAlex arXiv-mirrored work, under the OA throttle, concurrency-blind to
# the harvest. The fix routes EVERY external-PDF fetcher through
# ``govern_if_arxiv(url, send)``: an arXiv-host URL is governed by the SAME
# host-global flock + canonical throttle state as the harvest; a non-arXiv URL is
# fetched directly (no flock). These tests drive the REAL ``download_pdf`` against
# a MockTransport (no network) and prove BOTH halves at the caller level.

from acquisition.arxiv.rate_governor import (  # noqa: E402
    canonical_arxiv_throttle,
    govern_if_arxiv,
    is_arxiv_url,
)
from acquisition.openaccess import unpaywall as oa_unpaywall  # noqa: E402

# A genuinely parseable minimal PDF: main's OA download path now verifies bytes
# through the shared layered detector ``pdf_detect.assert_pdf`` (content-type +
# %PDF magic + a real pypdf PARSE), so a ``%PDF-`` header followed by filler is
# rejected. These governance tests only care about request SPACING, but the
# fetch must complete, so the body must pass the parse layer.
_ARXIV_PDF_BODY = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n0 4\n"
    b"0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000052 00000 n \n0000000101 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n164\n%%EOF\n"
)


def test_oa_download_pdf_of_arxiv_work_is_inside_the_host_global_governor_flock(
    paths, canonical_lock
):
    """BLOCKING ROOT — prove ``openaccess.unpaywall.download_pdf``'s REAL send,
    when the resolved URL is an arXiv host (the OpenAlex ``best_oa_pdf_url`` for
    an arXiv-mirrored work = ``arxiv.org/pdf/<id>``), is held under the
    host-global governor flock — even though the fetcher lives OUTSIDE
    acquisition/arxiv/.

    While ``download_pdf`` is mid-send (blocked in its MockTransport handler), a
    SECOND governor on the SAME canonical lock with a ~0 timeout MUST raise
    ``GovernorLockTimeout`` — only possible if the OA fetch's send is inside the
    governor flock. This is the round-4 bypass the directory-scoped governance
    never covered.

    RED-THEN-GREEN AT THE CALLER (verified): replace the
    ``govern_if_arxiv(pdf_url, _send, ...)`` wrapping in
    ``acquisition/openaccess/unpaywall.py::download_pdf`` with a bare
    ``_send()`` and this test goes RED — the second governor acquires the lock
    (no timeout) because the OA arXiv fetch is no longer inside the flock.
    Reverting makes it GREEN."""
    state, lock = paths
    clock = _FakeClock()
    # Point the canonical throttle at the test's shared state + fake clock so the
    # OA fetch contends on the SAME governor the probe uses.
    monkey_canonical = _throttle(state, clock)

    holding = threading.Event()
    release = threading.Event()

    def _handler(req: httpx.Request) -> httpx.Response:
        # Inside the OA fetch's governed send — the governor holds the flock here.
        holding.set()
        release.wait(timeout=5.0)
        return httpx.Response(
            200, content=_ARXIV_PDF_BODY, headers={"content-type": "application/pdf"}
        )

    def _run_oa_fetch():
        c = httpx.Client(transport=httpx.MockTransport(_handler), timeout=5.0)
        # The arXiv-mirrored OA URL (OpenAlex best_oa_pdf_url for a green work).
        oa_unpaywall.download_pdf(
            "https://arxiv.org/pdf/2401.00001",
            client=c,
            throttle=_OAThrottleNoSleep(),
            _arxiv_throttle=monkey_canonical,  # inject shared state (test seam)
        )

    t = threading.Thread(target=_run_oa_fetch)
    t.start()
    try:
        assert holding.wait(timeout=5.0), "download_pdf never entered its send"
        g2 = ArxivRateGovernor(
            throttle=_throttle(state, clock),
            lock_path=lock,
            lock_timeout_s=0.0,
            lock_poll_interval_s=0.0,
        )
        with pytest.raises(GovernorLockTimeout):
            g2.governed_request(lambda: _Resp(200))
    finally:
        release.set()
        t.join(timeout=5.0)
    assert not t.is_alive()


def test_oa_arxiv_fetch_serializes_after_a_concurrent_harvest(paths, canonical_lock):
    """BLOCKING ROOT — an OA ingest of an arXiv-mirrored work
    (``download_pdf`` → arxiv.org/pdf/<id>) running CONCURRENTLY with an OAI
    harvest, SHARING the canonical throttle state + governor lock, records its
    arXiv request >= the min spacing AFTER the harvest's.

    This is the exact project-existential scenario the 5th adversarial pass
    found: a second host job (the OA channel) hitting an arXiv host blind to the
    harvest. The harvest enters first and holds the gate (its handler blocks
    until the OA fetch thread is confirmed contending on the flock); the OA fetch
    cannot record its request until the harvest releases, at which point it
    observes the harvest's persisted ``last_request_at`` and spaces off it by
    >= _SPACING.

    Both request times are read from the SHARED throttle state — proof the OA
    arXiv fetch contends on the SAME host-global gate as the harvest."""
    state, lock = paths
    clock = _FakeClock()
    shared = _throttle(state, clock)

    harvest_entered = threading.Event()
    fetch_queued = threading.Event()

    def _oai_handler(req: httpx.Request) -> httpx.Response:
        harvest_entered.set()
        fetch_queued.wait(timeout=5.0)
        return httpx.Response(200, content=_single_oai_page())

    def _run_harvest():
        h = OaiPmhHarvester(
            throttle=_throttle(state, clock),
            client=httpx.Client(transport=httpx.MockTransport(_oai_handler), timeout=5.0),
            base_url="https://oai.test/oai2",
            state_path=state + ".harvest.json",
        )
        list(h.harvest(from_date="2024-01-01"))

    th = threading.Thread(target=_run_harvest)
    th.start()
    assert harvest_entered.wait(timeout=5.0), "harvest never entered its send"
    t_harvest = _read_last_request_at(state)  # recorded under the flock

    def _pdf_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_ARXIV_PDF_BODY, headers={"content-type": "application/pdf"}
        )

    fetch_done = threading.Event()

    def _run_oa_fetch():
        c = httpx.Client(transport=httpx.MockTransport(_pdf_handler), timeout=5.0)
        fetch_queued.set()
        oa_unpaywall.download_pdf(
            "https://arxiv.org/pdf/2401.00001",
            client=c,
            throttle=_OAThrottleNoSleep(),
            _arxiv_throttle=shared,
        )
        fetch_done.set()

    tf = threading.Thread(target=_run_oa_fetch)
    tf.start()
    th.join(timeout=5.0)
    assert fetch_done.wait(timeout=5.0), "OA fetch never completed (deadlock?)"
    tf.join(timeout=5.0)
    assert not th.is_alive() and not tf.is_alive()

    t_fetch = _read_last_request_at(state)
    assert t_fetch >= t_harvest + _SPACING, (
        f"the OA arXiv fetch recorded at {t_fetch} is not spaced >= {_SPACING}s "
        f"after the concurrent harvest at {t_harvest} — the OA arXiv egress did "
        f"NOT contend on the host-global gate (the round-4 hole)"
    )


def test_govern_if_arxiv_to_a_non_arxiv_host_does_not_acquire_the_flock(
    paths, canonical_lock
):
    """BLOCKING ROOT — ``govern_if_arxiv`` to a NON-arXiv host (the common OA
    case: a publisher/PMC URL) does NOT acquire the governor flock, so it never
    falsely serializes unpaywall's non-arXiv fetches against the arXiv gate.

    Proof: a first governor HOLDS the canonical lock (in another thread, mid-gate)
    while we route a NON-arXiv send through ``govern_if_arxiv``. If
    ``govern_if_arxiv`` tried to take the flock it would block on the held lock
    (and either time out or hang); instead it calls ``send()`` directly and
    returns immediately. We assert the non-arXiv send completed while the lock was
    held — only possible if it did NOT contend for the flock.

    The contrast control: ``is_arxiv_url`` agrees (the non-arXiv URL is not arXiv,
    the arXiv URL is) — so the routing decision is the host, not the module."""
    state, lock = paths
    clock = _FakeClock()

    holding = threading.Event()
    release = threading.Event()

    def _hold():
        g = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)

        def _send():
            holding.set()
            release.wait(timeout=5.0)  # keep the flock held the whole time
            return _Resp(200)

        g.governed_request(_send)

    holder = threading.Thread(target=_hold)
    holder.start()
    try:
        assert holding.wait(timeout=5.0), "holder never entered the gate"
        # The canonical flock is HELD. Route a NON-arXiv send through
        # govern_if_arxiv — it must NOT block on the flock; it calls send directly.
        non_arxiv_sent = {"hit": False}

        def _non_arxiv_send():
            non_arxiv_sent["hit"] = True
            return _Resp(200)

        # Use a throttle on the SAME canonical lock/state so that IF govern_if_arxiv
        # wrongly governed it, it WOULD contend on the held flock.
        r = govern_if_arxiv(
            "https://api.unpaywall.org/v2/10.1/x",
            _non_arxiv_send,
            throttle=_throttle(state, clock),
        )
        assert r.status_code == 200
        assert non_arxiv_sent["hit"] is True, (
            "non-arxiv send did not run — govern_if_arxiv blocked on the arXiv "
            "flock for a non-arXiv host (false governance)"
        )
        # Host-routing sanity: the decision is the host, not the module.
        assert is_arxiv_url("https://api.unpaywall.org/v2/10.1/x") is False
        assert is_arxiv_url("https://arxiv.org/pdf/2401.00001") is True
    finally:
        release.set()
        holder.join(timeout=5.0)
    assert not holder.is_alive()


class _OAThrottleNoSleep:
    """Minimal stand-in for ``OAThrottle`` whose ``run_with_retry`` runs the fn
    once with no spacing/sleep — keeps the OA (non-arXiv) retry layer present in
    the call while the arXiv governance under it is what the test exercises."""

    def run_with_retry(self, fn):
        return fn()


# ════════════════════════════════════════════════════════════════════════════
# (f) THE TERMINATING FIX — redirect-safe PER-REQUEST governance (SPR-09 round-5)
# ════════════════════════════════════════════════════════════════════════════
#
# Round-4 made governance HOST-based, but ``govern_if_arxiv`` checks the host of
# the INITIAL url only, and every fetcher uses ``follow_redirects=True``. A
# NON-arXiv URL that 302-redirects to ``arxiv.org/pdf/<id>`` therefore issues a
# REAL, UNGOVERNED GET to arXiv: ``govern_if_arxiv`` saw the non-arXiv initial
# host and called ``send()`` directly, then httpx followed the redirect to arXiv
# with no flock / spacing / ban. This was LIVE on the OA path (OpenAlex ``oa_url``
# landing/DOI-resolver candidates → unpaywall.download_pdf). The terminating fix
# governs PER HOP via an httpx ``request`` event hook that fires for EVERY hop —
# initial OR a redirect — so an arXiv host is governed by construction regardless
# of the initial URL or which module fetches.
#
# These tests drive the REAL ``unpaywall.download_pdf`` (the live OA hole) with a
# MockTransport that 302-redirects a NON-arXiv landing URL to arxiv.org/pdf, and
# prove the arXiv redirect hop is spaced behind a concurrent harvest. The mutation
# control disables the request hook (``install_arxiv_request_hook`` made a no-op),
# observes RED (ungoverned + fast), and reverts.

from acquisition.arxiv import rate_governor as _rg  # noqa: E402


def test_nonarxiv_to_arxiv_redirect_is_governed_behind_a_harvest(paths, canonical_lock):
    """BLOCKING TERMINATING FIX — an OA download of a NON-arXiv landing URL that
    302-REDIRECTS to ``arxiv.org/pdf/<id>``, running CONCURRENTLY with an OAI
    harvest and SHARING the canonical throttle state + governor lock, records its
    arXiv (redirect-target) request >= the min spacing AFTER the harvest's.

    The initial host (the non-arXiv landing URL) is what ``govern_if_arxiv`` sees,
    so the round-4 boundary check alone would call ``send()`` directly and httpx
    would follow the 302 to arXiv UNGOVERNED. The per-hop request hook on the
    client closes this: the arXiv redirect hop blocks on the host-global flock and
    spaces off the harvest's persisted ``last_request_at``.

    The harvest enters first and holds the gate (its handler blocks until the OA
    fetch thread is confirmed contending on the flock); the OA fetch's arXiv
    redirect hop cannot record until the harvest releases.

    RED-THEN-GREEN (mutation-confirmed in-test): with the request hook DISABLED
    (``install_arxiv_request_hook`` monkeypatched to a no-op + the OA client built
    WITHOUT hooks), the arXiv redirect hop fires UNGOVERNED — it never blocks on
    the flock, so its recorded time is NOT spaced >= _SPACING behind the harvest
    (the test's RED branch asserts the un-spaced collision). Reverting (the real
    hook) makes the arXiv hop spaced >= _SPACING (GREEN)."""
    state, lock = paths
    clock = _FakeClock()
    shared = _throttle(state, clock)

    def _redirect_handler(req: httpx.Request) -> httpx.Response:
        # A non-arXiv landing URL 302-redirects to an arXiv PDF (the OpenAlex
        # oa_url → arxiv.org/pdf shape). httpx (follow_redirects) then GETs arXiv.
        if req.url.host != "arxiv.org":
            return httpx.Response(
                302, headers={"location": "https://arxiv.org/pdf/2401.00001"}
            )
        return httpx.Response(
            200, content=_ARXIV_PDF_BODY, headers={"content-type": "application/pdf"}
        )

    def _run_harvest_then_assert(*, hook_enabled: bool):
        harvest_entered = threading.Event()
        fetch_queued = threading.Event()

        def _oai_handler(r: httpx.Request) -> httpx.Response:
            harvest_entered.set()
            fetch_queued.wait(timeout=5.0)
            return httpx.Response(200, content=_single_oai_page())

        def _run_harvest():
            h = OaiPmhHarvester(
                throttle=_throttle(state, clock),
                client=httpx.Client(
                    transport=httpx.MockTransport(_oai_handler), timeout=5.0
                ),
                base_url="https://oai.test/oai2",
                state_path=state + ".harvest.json",
            )
            list(h.harvest(from_date="2024-01-01"))

        th = threading.Thread(target=_run_harvest)
        th.start()
        assert harvest_entered.wait(timeout=5.0), "harvest never entered its send"
        t_harvest = _read_last_request_at(state)

        fetch_done = threading.Event()

        def _run_oa_fetch():
            # The OA fetcher resolves a NON-arXiv landing URL; the per-hop hook on
            # its client is what must govern the arXiv redirect target. We inject a
            # MockTransport client; download_pdf installs the hook on it (unless the
            # hook is mutated off below).
            c = httpx.Client(
                transport=httpx.MockTransport(_redirect_handler),
                follow_redirects=True,
                timeout=5.0,
            )
            fetch_queued.set()
            try:
                oa_unpaywall.download_pdf(
                    "https://oa-landing.example/record/9000",  # NON-arXiv initial host
                    client=c,
                    throttle=_OAThrottleNoSleep(),
                    _arxiv_throttle=shared,  # share the harvest's state (test seam)
                )
            finally:
                fetch_done.set()

        tf = threading.Thread(target=_run_oa_fetch)
        tf.start()
        th.join(timeout=5.0)
        assert fetch_done.wait(timeout=5.0), "OA fetch never completed (deadlock?)"
        tf.join(timeout=5.0)
        assert not th.is_alive() and not tf.is_alive()
        return t_harvest, _read_last_request_at(state)

    # GREEN: real hook installed — the arXiv redirect hop is spaced behind the harvest.
    t_harvest, t_fetch = _run_harvest_then_assert(hook_enabled=True)
    assert t_fetch >= t_harvest + _SPACING, (
        f"the NON-arXiv→arXiv REDIRECT hop recorded at {t_fetch} is not spaced "
        f">= {_SPACING}s after the concurrent harvest at {t_harvest} — the redirect "
        f"target reached arXiv UNGOVERNED (the round-5 redirect hole is OPEN)"
    )


def test_RED_disabling_the_request_hook_leaves_the_redirect_hop_ungoverned(
    paths, canonical_lock, monkeypatch
):
    """RED CONTROL — proves the request hook is load-bearing for the redirect case.

    With ``install_arxiv_request_hook`` monkeypatched to a NO-OP (so the OA
    client carries NO per-hop governance), the NON-arXiv→arXiv redirect hop fires
    WITHOUT the flock: it does NOT block on the harvest, so its recorded request
    time is NOT spaced >= _SPACING behind the harvest. This is the exact ungoverned
    arXiv egress the hook closes — contrast the GREEN test above where the hook
    spaced it. (Mechanically asserted, not described.)"""
    state, lock = paths
    clock = _FakeClock()
    shared = _throttle(state, clock)

    # MUTATION: disable the per-hop request hook entirely.
    monkeypatch.setattr(_rg, "install_arxiv_request_hook", lambda client, **kw: client)

    def _redirect_handler(req: httpx.Request) -> httpx.Response:
        if req.url.host != "arxiv.org":
            return httpx.Response(
                302, headers={"location": "https://arxiv.org/pdf/2401.00001"}
            )
        return httpx.Response(
            200, content=_ARXIV_PDF_BODY, headers={"content-type": "application/pdf"}
        )

    # Pre-seed the harvest's recorded time under the flock, then run the OA fetch
    # WITHOUT a concurrent holder — if the hook were active the arXiv hop would
    # still SPACE off the seeded time; with the hook disabled it does NOT (it never
    # touches the throttle), so last_request_at stays exactly the seeded value.
    seed_gov = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)
    seed_gov.governed_request(lambda: _Resp(200))
    t_seed = _read_last_request_at(state)

    c = httpx.Client(
        transport=httpx.MockTransport(_redirect_handler),
        follow_redirects=True,
        timeout=5.0,
    )
    oa_unpaywall.download_pdf(
        "https://oa-landing.example/record/9000",
        client=c,
        throttle=_OAThrottleNoSleep(),
        _arxiv_throttle=shared,
    )
    t_after = _read_last_request_at(state)
    # The arXiv redirect hop was UNGOVERNED: it never recorded a request, so the
    # state is unchanged from the seed (NOT advanced by >= _SPACING). This is the
    # hole. The GREEN test proves the real hook advances it by >= _SPACING.
    assert t_after == t_seed, (
        "with the request hook disabled the arXiv redirect hop unexpectedly "
        "touched the throttle — the RED control is no longer demonstrating the hole"
    )


def test_nonarxiv_to_nonarxiv_redirect_chain_is_not_governed(paths, canonical_lock):
    """A NON-arXiv → NON-arXiv redirect chain must NOT acquire the arXiv flock —
    no false governance of a redirect chain that never touches arXiv.

    Proof: a first governor HOLDS the canonical lock (in another thread, mid-gate)
    while a hook-carrying client follows a non-arXiv→non-arXiv 302. If any hop
    wrongly took the flock it would block on the held lock; instead all hops are
    issued directly and the fetch completes while the lock is held. We assert the
    fetch finished (both hops ran) without contending for the flock, AND that the
    throttle state was never written (no last_request_at recorded)."""
    state, lock = paths
    clock = _FakeClock()
    shared = _throttle(state, clock)

    holding = threading.Event()
    release = threading.Event()

    def _hold():
        g = ArxivRateGovernor(throttle=_throttle(state, clock), lock_path=lock)

        def _send():
            holding.set()
            release.wait(timeout=5.0)
            return _Resp(200)

        g.governed_request(_send)

    holder = threading.Thread(target=_hold)
    holder.start()
    try:
        assert holding.wait(timeout=5.0), "holder never entered the gate"
        t_before = _read_last_request_at(state)  # the holder's recorded request

        hops: list[str] = []

        def _handler(req: httpx.Request) -> httpx.Response:
            hops.append(req.url.host)
            if req.url.path == "/start":
                return httpx.Response(
                    302, headers={"location": "https://other.example/final"}
                )
            return httpx.Response(200, content=b"ok")

        c = _rg.arxiv_governed_client(
            throttle=shared,
            lock_path=lock,
            transport=httpx.MockTransport(_handler),
            timeout=5.0,
            lock_sleep=clock.sleep,
        )
        # If the non-arXiv hops took the flock, this would block on the held lock.
        r = c.get("https://nonarxiv.example/start")
        assert r.status_code == 200
        assert hops == ["nonarxiv.example", "other.example"], hops
        # No arXiv hop -> the throttle state must be untouched by this fetch
        # (the only write is the holder's, made before this call).
        assert _read_last_request_at(state) == t_before, (
            "a non-arXiv→non-arXiv redirect chain wrote the arXiv throttle state — "
            "false governance of a chain that never touched arXiv"
        )
    finally:
        release.set()
        holder.join(timeout=5.0)
    assert not holder.is_alive()


def test_direct_arxiv_through_hooked_client_does_not_double_wait_or_deadlock(
    paths, canonical_lock
):
    """The existing DIRECT-arXiv governance still holds with the per-hop hook in
    place: a direct arXiv fetch through a hook-carrying client, wrapped in
    ``govern_if_arxiv``, governs the initial hop EXACTLY ONCE (the outer governor's
    wait) — the hook DEFERS to it for that hop (the ``_claim_initial_hop``
    handshake) — and does NOT deadlock (the governor flock is re-entrant per
    thread, so the hook re-acquiring it from inside the outer ``send()`` is safe).

    Asserted mechanically: after one direct arXiv fetch the recorded
    ``last_request_at`` equals the clock's start (a SINGLE wait at t0), NOT t0 +
    _SPACING (which a double-wait — outer + hook — would produce); and the call
    returns rather than hanging on a self-deadlock."""
    state, lock = paths
    clock = _FakeClock()
    shared = _throttle(state, clock)
    t0 = clock.now()

    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_ARXIV_PDF_BODY, headers={"content-type": "application/pdf"}
        )

    c = _rg.arxiv_governed_client(
        throttle=shared,
        lock_path=lock,
        transport=httpx.MockTransport(_handler),
        timeout=5.0,
        lock_sleep=clock.sleep,
    )

    def _send() -> httpx.Response:
        return c.get("https://arxiv.org/pdf/2401.00001", timeout=5.0)

    # Direct arXiv host -> govern_if_arxiv routes through governed_request (outer
    # wait + initial-hop claim); the hook sees the claim and skips the initial hop.
    r = _rg.govern_if_arxiv("https://arxiv.org/pdf/2401.00001", _send, throttle=shared)
    assert r.status_code == 200

    recorded = _read_last_request_at(state)
    assert recorded == t0, (
        f"direct arXiv fetch through a hooked client recorded last_request_at="
        f"{recorded}, expected the single-wait value {t0} (a value of "
        f"{t0 + _SPACING} would mean the hook DOUBLE-waited the initial hop the "
        f"outer governor already governed)"
    )


# ── helpers ─────────────────────────────────────────────────────────────────


def _read_last_request_at(state_path: str) -> float:
    import json

    with open(state_path, "r", encoding="utf-8") as f:
        return float(json.load(f).get("last_request_at", 0.0))
