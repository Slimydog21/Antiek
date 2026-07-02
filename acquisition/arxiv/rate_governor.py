"""Host-global arXiv rate governor — serialize the throttle's critical section
across ALL arXiv jobs on this box (SPR-09 M1).

The problem this closes (project_researchmaxx_arxiv.md; ``throttle.py`` docstring
lines 18-23, 137). ``ArxivThrottle`` already enforces >= 3s spacing and a
``banned_until`` 429 sentinel via a shared JSON state file, so the spacing/ban
state *survives* across separate process invocations. BUT its read-modify-write
of that state file is explicitly UNLOCKED / last-writer-wins: two concurrent
jobs (a harvest + an on-demand PDF fetch, or two shells) can each read the same
``last_request_at``, both compute ``elapsed >= 3s``, and BOTH fire inside one 3s
window — collectively exceeding the 1-request-per-3s ceiling that historically
IP-banned the box. There is also no single-connection cap.

This module makes the gate GLOBAL by serializing the throttle's
``wait_if_needed() -> send() -> note_response()`` critical section under an
exclusive cross-process ``fcntl.flock`` (the canonical Antiek cross-process
serialization mechanism — the very same pattern as ``runtime/db_lock.py``'s
``connect_write`` / ``_stale_pid_check`` / ``LockedConnection``: ``LOCK_EX``,
poll-to-deadline, stale-PID cleanup, release-on-close). Because only one job can
hold the lock at a time, only one job is ever inside the gate — which also gives
the "<= 1 arXiv request in-flight across all jobs" single-connection property
for free.

What this module does NOT do — re-implement throttling. Re-implementing
rate-limiting is the documented historical cause of the IP ban (the prior
in-process timer ignored another shell's history). We REUSE ``ArxivThrottle``
verbatim as the per-request timing + ban-sentinel engine and only wrap its
critical section in the flock. ``ArxivBanned`` propagates unchanged.

Scope of the guarantee (honesty bar 1 — see
``docs/decisions/arxiv-rate-governor-host-scoped.md``):

  * MECHANICAL: the >= 3s spacing + 429 ban sentinel are now enforced GLOBALLY
    across every arXiv job ON THIS HOST (any process that routes its send through
    ``governed_request`` blocks on the same flock + shares the same JSON state),
    and a CI lint (``tools/lint/rate_governor_check.py``) reds a NEW direct
    arxiv.org egress that bypasses this seam.
  * OPERATIONAL, NOT MECHANICAL: "no multi-IP circumvention" cannot be enforced
    from one box — a second physical machine / IP running its own scraper is
    invisible to this flock and this JSON file. That is an operational policy
    (do not run a second un-governed scraper / second IP), not a code guarantee.

Time + sleep + the lock path are injectable so CI tests serialize against the
*real* flock deterministically without ever sleeping 3 real seconds (precedent:
``tools/arxiv_census.py`` throwaway state + ``min_spacing_s=0``).
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from acquisition.arxiv.throttle import (
    ArxivBanned,
    ArxivThrottle,
    _ResponseLike,
    default_state_path,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import httpx

# The arXiv hosts the IP ban applies to. The ban is HOST-scoped (every endpoint
# under arxiv.org / export.arxiv.org shares the one IP-rate budget), so the
# governor must catch a fetch to ANY of these — the public site (arxiv.org/pdf,
# arxiv.org/abs), the OAI/export API (export.arxiv.org), OR any subdomain of
# either. We match the registrable host AND any ``*.arxiv.org`` subdomain.
_ARXIV_HOSTS: frozenset[str] = frozenset({"arxiv.org", "export.arxiv.org"})
_ARXIV_HOST_SUFFIX = ".arxiv.org"


def is_arxiv_url(url: str) -> bool:
    """Whether ``url`` resolves to an arXiv host the IP ban governs.

    True iff the URL's host is ``arxiv.org`` / ``export.arxiv.org`` or any
    subdomain of ``arxiv.org`` (e.g. ``export.arxiv.org``, a future
    ``www.arxiv.org``). The host is lower-cased and any ``:port`` /
    ``user@`` is ignored. A non-URL / hostless string (a bare path, a
    ``data:`` URI) is NOT arXiv. This is the runtime FETCH-boundary check
    that makes governance host-based, not module-location-based: whatever
    module holds the URL, an arXiv host is caught here."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except (ValueError, TypeError):
        return False
    if not host:
        return False
    return host in _ARXIV_HOSTS or host.endswith(_ARXIV_HOST_SUFFIX)


# ── canonical host-global throttle (shared state across ALL arXiv egress) ──
#
# A single module-level ``ArxivThrottle`` so any fetcher anywhere in the
# codebase (the OAI harvest, the on-demand PDF fetch, the export search, AND a
# non-arXiv fetcher like ``openaccess.unpaywall.download_pdf`` that happens to
# land an arxiv.org/pdf URL) routes its arXiv send through the SAME >=3s spacing
# + 429 ban-sentinel state file (``~/.antiek/arxiv_throttle.json``) under the
# SAME ``.governor.lock`` flock. Without one shared throttle, a second module
# constructing its own ``ArxivThrottle()`` would still share the JSON state file
# (same default path) AND the flock (same default lock path) — so concurrency is
# already safe — but exposing the canonical one lets a caller pass it explicitly
# and makes the shared-state intent obvious. Lazily constructed; tests that
# inject a fake clock build their own throttle and pass it through.
_CANONICAL_THROTTLE: ArxivThrottle | None = None


def canonical_arxiv_throttle() -> ArxivThrottle:
    """The one process-wide ``ArxivThrottle`` over the canonical
    ``~/.antiek/arxiv_throttle.json`` state. Every arXiv egress — from any
    module — should route through THIS (or any throttle pointing at the same
    default state path; they share the JSON file + flock regardless). Exposed so
    a non-arXiv fetcher (e.g. ``openaccess.unpaywall``) that can resolve to an
    arXiv host has a handle to the shared governor state."""
    global _CANONICAL_THROTTLE
    if _CANONICAL_THROTTLE is None:
        _CANONICAL_THROTTLE = ArxivThrottle()
    return _CANONICAL_THROTTLE

# How long to wait for the governor flock before giving up. The critical
# section is a >= 3s sleep + one HTTP round-trip, so a handful of queued jobs
# can legitimately take a while; 300s mirrors db_lock's DEFAULT_TIMEOUT_S.
DEFAULT_LOCK_TIMEOUT_S = 300.0
DEFAULT_LOCK_POLL_INTERVAL_S = 0.1
DEFAULT_HTTP_TIMEOUT_S = 20.0


def default_lock_path() -> str:
    """The governor's sidecar lock file — co-located with the throttle JSON
    state so the lock and the state it serializes live together. Honors
    ``ANTIEK_ARXIV_GOVERNOR_LOCK_PATH`` for tests / alternate homes.

    All host arXiv jobs that share the same throttle state file
    (``~/.antiek/arxiv_throttle.json`` by default) also share this one lock,
    which is what makes the gate host-global.
    """
    env = os.environ.get("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH")
    if env:
        return env
    return default_state_path() + ".governor.lock"


class GovernorLockTimeout(RuntimeError):
    """Raised when the governor flock could not be acquired within the timeout.

    Mirrors ``runtime.db_lock.WriteLockTimeout``: a stuck holder is diagnosable
    via the PID + purpose stamped in the lock file.
    """


def _stale_pid_check(lock_path: str) -> None:
    """Remove the lock file if its stamped PID is no longer alive.

    The OS releases the flock on process death, but the lock file + its PID
    stamp persist. Best-effort hygiene called before ``os.open()`` — the real
    serialization still happens via flock; if a live writer re-creates the file
    between our stat and open, the flock on open correctly serializes. Lifted
    verbatim in spirit from ``runtime.db_lock._stale_pid_check``.
    """
    try:
        with open(lock_path) as f:
            content = f.read(64)
    except (FileNotFoundError, OSError):
        return
    pid_str = content.split()[0] if content.strip() else ""
    if not pid_str or not pid_str.isdigit():
        return
    pid = int(pid_str)
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        with contextlib.suppress(OSError):
            os.unlink(lock_path)


# ── per-thread re-entrancy for the governor flock ──────────────────────────
#
# A single logical fetch can need the governor lock TWICE on one thread: the
# outer ``governed_request`` holds it across the whole ``send()`` (so the
# caller-level "flock held during send" property holds), and the per-request
# event hook (see ``arxiv_governed_client``) wants it again for each REDIRECT
# hop fired from inside that same ``send()``. A plain ``fcntl.flock`` taken on a
# SECOND fd for the same file from the same process BLOCKS (flock is per open
# file description, not per process), so the inner acquisition would
# self-deadlock. We make the lock RE-ENTRANT per thread: the first acquisition
# on a thread does the real ``flock``; a nested acquisition (same thread, same
# lock path) just bumps a depth counter and reuses the held fd. Only the
# outermost release actually unlocks. Cross-thread / cross-process contention
# still serializes on the real ``flock`` — re-entrancy is strictly intra-thread.
_REENTRANT = threading.local()


def _held_depth(lock_path: str) -> int:
    held = getattr(_REENTRANT, "held", None)
    if not held:
        return 0
    entry = held.get(lock_path)
    return entry[1] if entry else 0


class _GovernorLock:
    """An acquired exclusive flock on the governor sidecar, released on
    ``__exit__``. Same acquire shape as ``runtime.db_lock.connect_write``:
    ``LOCK_EX | LOCK_NB`` polled to a deadline (so we can enforce a timeout),
    stale-PID cleanup before open, release + close on exit.

    RE-ENTRANT per thread (see ``_REENTRANT`` above): if this thread already
    holds the flock for ``lock_path`` (an outer ``governed_request`` plus an
    inner redirect-hop hook), the nested acquisition reuses the held fd and only
    bumps a depth counter, so it cannot self-deadlock; only the outermost exit
    releases.
    """

    def __init__(
        self,
        lock_path: str,
        *,
        timeout_s: float,
        poll_interval_s: float,
        purpose: str,
        sleep: Callable[[float], None],
    ) -> None:
        self._lock_path = lock_path
        self._timeout_s = float(timeout_s)
        self._poll_interval_s = float(poll_interval_s)
        self._purpose = purpose or "-"
        # The poll sleep uses real monotonic time, NOT the injected throttle
        # clock: the lock wait is wall-clock contention, independent of the
        # throttle's fake test clock. Tests that exercise contention drive
        # acquisition order directly rather than through this poll.
        self._sleep = sleep
        self._fd: int | None = None
        self._reentered = False

    def __enter__(self) -> _GovernorLock:
        held = getattr(_REENTRANT, "held", None)
        if held is None:
            held = {}
            _REENTRANT.held = held
        entry = held.get(self._lock_path)
        if entry is not None:
            # Already held by THIS thread — re-enter: bump depth, reuse the fd.
            fd, depth = entry
            held[self._lock_path] = (fd, depth + 1)
            self._fd = fd
            self._reentered = True
            return self

        parent = os.path.dirname(self._lock_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        _stale_pid_check(self._lock_path)
        fd = os.open(self._lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
        deadline = time.monotonic() + self._timeout_s
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as e:
                    if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                        raise
                    if time.monotonic() >= deadline:
                        os.close(fd)
                        raise GovernorLockTimeout(
                            f"Could not acquire arXiv governor lock on "
                            f"{self._lock_path} within {self._timeout_s}s. "
                            f"Another arXiv job is holding it; inspect with "
                            f"`cat {self._lock_path}` (PID + purpose)."
                        ) from e
                    self._sleep(self._poll_interval_s)
        except GovernorLockTimeout:
            raise
        except Exception:
            with contextlib.suppress(OSError):
                os.close(fd)
            raise
        # Stamp pid + purpose + timestamp for ops debugging (best-effort).
        try:
            os.ftruncate(fd, 0)
            stamp = (
                f"{os.getpid()} {self._purpose} "
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            )
            os.write(fd, stamp.encode())
        except OSError:
            pass
        self._fd = fd
        held[self._lock_path] = (fd, 1)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        held = getattr(_REENTRANT, "held", None) or {}
        entry = held.get(self._lock_path)
        if entry is not None:
            fd, depth = entry
            if depth > 1:
                # Inner (re-entered) scope — keep the flock; just drop depth.
                held[self._lock_path] = (fd, depth - 1)
                self._fd = None
                return False
            # Outermost scope — actually release.
            held.pop(self._lock_path, None)
        if self._fd is not None and not self._reentered:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                with contextlib.suppress(OSError):
                    os.close(self._fd)
        self._fd = None
        return False


class ArxivRateGovernor:
    """The single seam every host arXiv egress routes through.

    Wraps one ``ArxivThrottle`` (the reused >= 3s + ban-sentinel engine) and
    serializes its ``wait_if_needed -> send -> note_response`` critical section
    under an exclusive ``fcntl.flock`` so the rate gate holds GLOBALLY across
    all arXiv jobs on this host, not merely per-process.

    Construct ONE per job and call :meth:`governed_request` for each HTTP send.
    All governors that point at the same throttle state file + lock path (the
    production default) serialize against each other across processes.
    """

    def __init__(
        self,
        *,
        throttle: ArxivThrottle | None = None,
        lock_path: str | None = None,
        lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
        lock_poll_interval_s: float = DEFAULT_LOCK_POLL_INTERVAL_S,
        purpose: str = "arxiv",
        lock_sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        # REUSE the throttle as-is; never re-implement spacing/ban here.
        self._throttle = throttle if throttle is not None else ArxivThrottle()
        self._lock_path = lock_path or default_lock_path()
        self._lock_timeout_s = float(lock_timeout_s)
        self._lock_poll_interval_s = float(lock_poll_interval_s)
        self._purpose = purpose
        self._lock_sleep = lock_sleep

    @property
    def throttle(self) -> ArxivThrottle:
        return self._throttle

    @property
    def lock_path(self) -> str:
        return self._lock_path

    def governed_request(
        self, send: Callable[[], _ResponseLike]
    ) -> _ResponseLike:
        """Issue ONE arXiv request with the host-global rate gate held.

        Equivalent to ``ArxivThrottle.request`` but with the ENTIRE
        ``wait_if_needed -> send -> note_response`` sequence executed inside an
        exclusive cross-process flock. Because the wait+record AND the
        ban-sentinel write all happen while this job holds the lock, no second
        job can observe a stale ``last_request_at`` (so two jobs can never both
        fire in one 3s window) and the ``banned_until`` sentinel a 429 writes is
        observed atomically by the next job to acquire the lock.

        ``send`` performs the actual HTTP GET and returns a response exposing
        ``.status_code`` + ``.headers`` (an ``httpx.Response`` does). Raises
        ``ArxivBanned`` (before sending, inside the lock) if a ban sentinel is
        active — the caller must PAUSE, not retry. Raises ``GovernorLockTimeout``
        if the lock cannot be acquired in time.
        """
        with _GovernorLock(
            self._lock_path,
            timeout_s=self._lock_timeout_s,
            poll_interval_s=self._lock_poll_interval_s,
            purpose=self._purpose,
            sleep=self._lock_sleep,
        ):
            # The throttle's own request() pairs wait_if_needed() BEFORE and
            # note_response() AFTER, so a 429 records the ban and an active ban
            # raises ArxivBanned before the send. Running it INSIDE the flock is
            # the whole point: the read->space->write->note is now one atomic,
            # globally-serialized critical section.
            #
            # REDIRECT-SAFE RECONCILIATION (SPR-09 round-5): if ``send`` issues
            # the request through a client carrying the per-hop request/response
            # hooks (see ``arxiv_governed_client``), the hook would ALSO govern
            # the very first hop this ``request()`` is about to govern — a double
            # wait. We claim the INITIAL hop here so the hook skips exactly one
            # arXiv hop (the one already governed by this outer wait) and governs
            # only the SUBSEQUENT redirect hops. The flock is re-entrant, so a
            # redirect hop's hook re-acquiring it from inside ``send()`` does not
            # deadlock. For a non-hook client this marker is simply never read.
            token = _claim_initial_hop(self._throttle)
            try:
                return self._throttle.request(send)
            finally:
                _release_initial_hop(token)


def governed_request(
    send: Callable[[], _ResponseLike],
    *,
    governor: ArxivRateGovernor | None = None,
    throttle: ArxivThrottle | None = None,
) -> _ResponseLike:
    """Convenience seam: route one arXiv send through a host-global governor.

    Pass an existing ``governor`` to reuse its throttle + lock, or pass a
    ``throttle`` (or neither, for the production defaults) to build a one-shot
    governor. Re-raises ``ArxivBanned`` / ``GovernorLockTimeout`` from the
    governed call.
    """
    gov = governor if governor is not None else ArxivRateGovernor(throttle=throttle)
    return gov.governed_request(send)


def govern_if_arxiv(
    url: str,
    send: Callable[[], _ResponseLike],
    *,
    throttle: ArxivThrottle | None = None,
    governor: ArxivRateGovernor | None = None,
) -> _ResponseLike:
    """THE ROOT host-based runtime gate (SPR-09 round-4).

    The FETCH-boundary helper every external-PDF/HTTP fetcher that can resolve
    to a variable URL routes its send through. The host is only known at runtime
    (an OpenAlex ``best_oa_pdf_url`` for an arXiv-mirrored work is
    ``https://arxiv.org/pdf/<id>``; a non-arXiv OA work is a publisher host), so
    the governance decision is made HERE, at the boundary, on the actual URL —
    NOT by which module the call lives in. This is what makes the guarantee
    bypass-proof: regardless of which module fetches, an arXiv host is governed.

      * ``url`` is an arXiv host (:func:`is_arxiv_url`) → route ``send`` through
        :func:`governed_request` (the host-global ``fcntl.flock`` + >=3s spacing
        + 429 ban sentinel on the canonical ``~/.antiek/arxiv_throttle.json`` +
        ``.governor.lock``). When no ``throttle``/``governor`` is supplied the
        :func:`canonical_arxiv_throttle` is used so the fetch shares state with
        the OAI harvest / pdf_fetch / export search. Re-raises ``ArxivBanned`` /
        ``GovernorLockTimeout``.
      * ``url`` is NOT an arXiv host → call ``send()`` DIRECTLY. A non-arXiv
        fetch (the common OA case: a publisher / PMC / repository host) keeps its
        OWN throttling untouched and never touches the arXiv flock — so there is
        no false governance (no spurious lock contention) of non-arXiv egress.

    Because the host check is at the boundary on the resolved URL, a fetcher
    cannot bypass the arXiv governor by living outside ``acquisition/arxiv/``.
    """
    if is_arxiv_url(url):
        eff_throttle = throttle if throttle is not None else canonical_arxiv_throttle()
        return governed_request(send, governor=governor, throttle=eff_throttle)
    return send()


# ── PER-REQUEST, REDIRECT-SAFE governance (SPR-09 round-5, the terminating fix) ─
#
# ``govern_if_arxiv`` checks the host of the INITIAL url only; every fetcher uses
# ``follow_redirects=True``. A non-arXiv URL that 302-redirects to
# ``arxiv.org/pdf/<id>`` therefore issues a REAL, UNGOVERNED GET to arXiv — the
# boundary check saw the non-arXiv initial host and called ``send()`` directly,
# then httpx followed the redirect to arXiv with no flock / spacing / ban check.
# The terminating fix governs at the PER-REQUEST level via an httpx ``request``
# event hook that fires for EVERY hop (initial OR a redirect), so an arXiv host
# is governed by CONSTRUCTION regardless of the initial URL or which module
# fetches. The paired ``response`` hook records the 429 ban sentinel per hop.
#
# Reconciliation with the existing outer ``governed_request`` (so each hop is
# governed EXACTLY once, with no double-wait and no deadlock):
#   * The outer ``governed_request`` governs the INITIAL hop (its
#     ``throttle.request`` does wait_if_needed + note_response) and claims that
#     one hop via ``_claim_initial_hop`` so the request/response hooks SKIP it.
#   * The hooks then govern every SUBSEQUENT (redirect) hop. The governor flock
#     is re-entrant per thread, so a redirect hop's hook re-acquiring the flock
#     from inside the outer ``send()`` does not self-deadlock.
#   * When the initial host is NON-arXiv, ``govern_if_arxiv`` calls ``send()``
#     directly (no outer wait, no claim) — so a redirect to an arXiv host is
#     governed solely by the hook. THIS is the hole that was live on the OA path.

# Per-thread state for the initial-hop claim. ``count`` is the number of arXiv
# initial hops the outer governor has claimed and the hooks have not yet
# consumed; ``throttle`` identifies which throttle owns the claim (so a stray
# hook bound to a DIFFERENT throttle does not consume someone else's claim).
_HOOK_STATE = threading.local()


def _claim_initial_hop(throttle: ArxivThrottle) -> int:
    """Mark that the outer governor is about to govern ONE arXiv hop itself, so
    the per-hop request/response hooks for ``throttle`` skip exactly that hop.
    Returns the prior claim count (an opaque token for ``_release_initial_hop``).
    Nestable: a re-entrant outer governance bumps the count."""
    prev = getattr(_HOOK_STATE, "claim", 0)
    _HOOK_STATE.claim = prev + 1
    _HOOK_STATE.claim_throttle = throttle
    return prev


def _release_initial_hop(token: int) -> None:
    """Drop one initial-hop claim, restoring the count to ``token``. Called in a
    ``finally`` so a claim never leaks past its outer governed section even if
    the send raised (e.g. ``ArxivBanned``)."""
    _HOOK_STATE.claim = token
    if token == 0:
        _HOOK_STATE.claim_throttle = None


def _consume_initial_hop_claim(throttle: ArxivThrottle) -> bool:
    """Whether THIS arXiv hop was already governed by an outer ``governed_request``
    (and so the hook must NOT govern it again). Consumes one claim if present —
    the claim covers exactly one hop (the initial request); subsequent redirect
    hops find no claim and are governed by the hook. The throttle identity is
    matched so a hook with an unrelated throttle never consumes a foreign claim."""
    claim = getattr(_HOOK_STATE, "claim", 0)
    if claim <= 0:
        return False
    claim_throttle = getattr(_HOOK_STATE, "claim_throttle", None)
    if claim_throttle is not throttle:
        return False
    _HOOK_STATE.claim = claim - 1
    if claim - 1 == 0:
        _HOOK_STATE.claim_throttle = None
    return True


def _govern_request_hop(
    throttle: ArxivThrottle,
    lock_path: str,
    *,
    lock_timeout_s: float,
    lock_poll_interval_s: float,
    lock_sleep: Callable[[float], None],
) -> None:
    """Apply the host-global wait (flock + >=3s spacing + ``banned_until`` check)
    for ONE outbound arXiv request hop. Mirrors the wait half of
    ``ArxivThrottle.request`` but for a single hop, held under the re-entrant
    governor flock. Raises ``ArxivBanned`` (before the hop goes out) if a ban
    sentinel is active, and ``GovernorLockTimeout`` if the flock can't be taken."""
    with _GovernorLock(
        lock_path,
        timeout_s=lock_timeout_s,
        poll_interval_s=lock_poll_interval_s,
        purpose="arxiv-hook",
        sleep=lock_sleep,
    ):
        throttle.wait_if_needed()


def _note_response_hop(
    throttle: ArxivThrottle,
    lock_path: str,
    status_code: int,
    headers,
    *,
    lock_timeout_s: float,
    lock_poll_interval_s: float,
    lock_sleep: Callable[[float], None],
) -> None:
    """Record one arXiv response hop's outcome (the 429 ``banned_until`` sentinel)
    under the re-entrant governor flock — the note half of the per-hop gate."""
    with _GovernorLock(
        lock_path,
        timeout_s=lock_timeout_s,
        poll_interval_s=lock_poll_interval_s,
        purpose="arxiv-hook",
        sleep=lock_sleep,
    ):
        throttle.note_response(status_code, headers)


def install_arxiv_request_hook(
    client: httpx.Client,
    *,
    throttle: ArxivThrottle | None = None,
    lock_path: str | None = None,
    lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
    lock_poll_interval_s: float = DEFAULT_LOCK_POLL_INTERVAL_S,
    lock_sleep: Callable[[float], None] = time.sleep,
) -> httpx.Client:
    """Attach the redirect-safe per-hop arXiv governance hooks to ``client``.

    Adds a ``request`` event hook that, for EVERY request the client issues whose
    host is an arXiv host — including each redirect hop httpx follows — applies
    the host-global governor wait (re-entrant flock + >=3s spacing + ``banned_until``
    check on the shared throttle state) BEFORE the hop goes out, and a paired
    ``response`` hook that records the 429 ban sentinel. Because the hook fires on
    each hop, a non-arXiv → arXiv 302 is governed by construction: the arXiv
    redirect target's GET cannot leave un-spaced.

    The hooks DEFER to an outer ``governed_request``/``govern_if_arxiv`` for the
    one initial hop that outer wait already governs (via the ``_claim_initial_hop``
    handshake), so a request is governed exactly once per hop with no double-wait
    and — thanks to the re-entrant flock — no deadlock when the initial host is
    itself arXiv. Non-arXiv hops are never touched. Returns ``client`` for
    chaining. Idempotent: re-installing on an already-hooked client is a no-op."""
    if getattr(client, "_antiek_arxiv_hooked", False):
        return client
    eff_throttle = throttle if throttle is not None else canonical_arxiv_throttle()
    eff_lock = lock_path or default_lock_path()

    def _request_hook(request: httpx.Request) -> None:
        if not is_arxiv_url(str(request.url)):
            return
        if _consume_initial_hop_claim(eff_throttle):
            return  # the outer governed_request already waited for this hop
        _govern_request_hop(
            eff_throttle,
            eff_lock,
            lock_timeout_s=lock_timeout_s,
            lock_poll_interval_s=lock_poll_interval_s,
            lock_sleep=lock_sleep,
        )

    def _response_hook(response: httpx.Response) -> None:
        if not is_arxiv_url(str(response.request.url)):
            return
        # note_response acts ONLY on a 429 (and is conservative/idempotent: it
        # sets banned_until forward), so noting every arXiv response hop is both
        # safe and exactly what we want — a 429 from ANY hop (initial or a
        # redirect target) records the ban sentinel. The outer
        # ``throttle.request`` also notes the FINAL response when it governed the
        # initial hop; that overlap is a harmless no-op on a non-429 and a
        # conservative re-set on a 429.
        _note_response_hop(
            eff_throttle,
            eff_lock,
            response.status_code,
            response.headers,
            lock_timeout_s=lock_timeout_s,
            lock_poll_interval_s=lock_poll_interval_s,
            lock_sleep=lock_sleep,
        )

    hooks = client.event_hooks
    hooks.setdefault("request", []).append(_request_hook)
    hooks.setdefault("response", []).append(_response_hook)
    client.event_hooks = hooks
    client._antiek_arxiv_hooked = True  # type: ignore[attr-defined]
    return client


def arxiv_governed_client(
    *,
    throttle: ArxivThrottle | None = None,
    lock_path: str | None = None,
    follow_redirects: bool = True,
    lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
    lock_poll_interval_s: float = DEFAULT_LOCK_POLL_INTERVAL_S,
    lock_sleep: Callable[[float], None] = time.sleep,
    **client_kwargs,
) -> httpx.Client:
    """Build an ``httpx.Client`` whose every request hop is governed by the
    redirect-safe per-hop arXiv gate (see :func:`install_arxiv_request_hook`).

    This is the factory a variable-/redirect-prone-URL fetcher uses so a raw
    ``client.get(url)`` through it is governed on EVERY hop — the initial request
    AND any arXiv redirect target — with no per-call ``govern_if_arxiv`` host
    pre-check needed for the redirect case (the host check happens in the hook,
    per hop). ``follow_redirects`` defaults True (the whole point: the redirect
    hop is what the hook catches). Extra ``client_kwargs`` (transport, timeout,
    headers) pass through to ``httpx.Client``."""
    import httpx as _httpx

    timeout = client_kwargs.pop("timeout", DEFAULT_HTTP_TIMEOUT_S)
    client = _httpx.Client(
        follow_redirects=follow_redirects,
        timeout=timeout,  # default matches acquisition/papers/core.py DEFAULT_TIMEOUT_S (20s)
        **client_kwargs,
    )
    return install_arxiv_request_hook(
        client,
        throttle=throttle,
        lock_path=lock_path,
        lock_timeout_s=lock_timeout_s,
        lock_poll_interval_s=lock_poll_interval_s,
        lock_sleep=lock_sleep,
    )


__all__ = [
    "ArxivRateGovernor",
    "ArxivBanned",
    "GovernorLockTimeout",
    "governed_request",
    "govern_if_arxiv",
    "is_arxiv_url",
    "canonical_arxiv_throttle",
    "default_lock_path",
    "install_arxiv_request_hook",
    "arxiv_governed_client",
]
