"""No Speak route may take the write lock on the event loop.

``connect_write`` blocks on an flock with ``DEFAULT_TIMEOUT_S = 300``. Taken
inline in an ``async def`` it parks the whole uvicorn event loop, and the
service runs ``--workers 1`` — so one caller stalls the entire API for up to
five minutes.

Six routes in this module are reachable with NO session at all: the operator-
auth middleware waves through ``/speak/invite/*`` and
``/speak/projects/{id}/open-contribute``. On those, the stall is an anonymous
denial of service rather than a slow request for a logged-in user.

This is source-shaped deliberately. The property is where the acquisition
sits relative to the coroutine, which is statically decidable; a behavioural
test would have to win a race against a real lock holder to observe it.

The repo's own ``no_blocking_write_in_async`` lint does not catch these,
because it looks for a direct ``connect_write`` entry and this module reaches
it one hop away through the ``_write()`` contextmanager. Until that lint
learns the one-hop rule, this test is the guard for this module.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MODULE = _ROOT / "interfaces" / "research" / "api" / "speak_routes.py"

#: Names that acquire the single-writer flock, directly or one hop away.
_WRITE_ENTRIES = {"_write", "connect_write"}


def _module() -> ast.Module:
    return ast.parse(_MODULE.read_text(encoding="utf-8"))


def _offenders() -> list[tuple[str, int, str]]:
    """(coroutine, line, callee) for every write entry ON the loop."""
    out: list[tuple[str, int, str]] = []
    for node in ast.walk(_module()):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        # Lines belonging to a nested SYNC def are off the loop: that is the
        # `def _sync(): ...; await asyncio.to_thread(_sync)` idiom.
        offloaded: set[int] = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.FunctionDef):
                offloaded.update(
                    range(inner.lineno, (inner.end_lineno or inner.lineno) + 1)
                )
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id in _WRITE_ENTRIES
                and sub.lineno not in offloaded
            ):
                out.append((node.name, sub.lineno, sub.func.id))
    return sorted(out)


def test_the_premise_still_holds() -> None:
    """Not vacuous: no coroutines, or no write entries, passes trivially."""
    tree = _module()
    coros = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
    assert len(coros) >= 10, f"expected many async routes, found {len(coros)}"
    writes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in _WRITE_ENTRIES
    ]
    assert writes, (
        "no write-lock entry found in speak_routes.py at all — if _write() was "
        "renamed, update _WRITE_ENTRIES rather than letting this pass"
    )


#: Reachable with NO session — the operator-auth middleware waves through
#: /speak/invite/* and /speak/projects/{id}/open-contribute. A stall here is
#: an anonymous denial of service. These must stay at zero.
_UNAUTHENTICATED = frozenset({
    "open_contribute",
    "invitee_consent",
    "invitee_answer",
    "invitee_voice",
    "invitee_followups",
    "invitee_decline",
})

#: Session-gated routes with the same shape. Still a real availability bug —
#: any one of them parks the loop for every other request — but it takes a
#: credential to trigger, so they are a backlog rather than a hole. Recorded
#: so the count can only SHRINK: a new coroutine with an on-loop write fails
#: the test below instead of joining a list nobody re-reads.
_KNOWN_AUTHENTICATED_BLOCKING = frozenset({
    "corroborate", "create_biography", "create_project", "draft",
    "get_project", "grade_interview", "invite", "list_invites",
    "list_projects", "map_contributor", "open_public", "order_book",
    "publish", "record_consent", "record_interview_claim", "release_payout",
    "request_takedown", "set_subject_consent",
})


def test_no_unauthenticated_route_takes_the_write_lock_on_the_loop() -> None:
    """The security boundary: an anonymous caller must not be able to stall."""
    offenders = [o for o in _offenders() if o[0] in _UNAUTHENTICATED]
    assert not offenders, (
        "these UNAUTHENTICATED coroutines acquire the single-writer flock on "
        "the event loop: "
        + "; ".join(f"{n}() line {ln}" for n, ln, _ in offenders)
        + ". connect_write blocks up to DEFAULT_TIMEOUT_S=300 and the service "
        "runs --workers 1, so one anonymous request stalls the whole API for "
        "five minutes. Move the blocking work into a nested `def _sync()` and "
        "`await asyncio.to_thread(_sync)`."
    )


def test_the_authenticated_blocking_backlog_only_shrinks() -> None:
    """A NEW on-loop write is a regression even behind a session."""
    offenders = {o[0] for o in _offenders()}
    added = sorted(offenders - _UNAUTHENTICATED - _KNOWN_AUTHENTICATED_BLOCKING)
    assert not added, (
        f"new coroutine(s) taking the write lock on the event loop: {added}. "
        "Use the `def _sync()` + `await asyncio.to_thread(_sync)` idiom. If "
        "this is deliberate, add it to _KNOWN_AUTHENTICATED_BLOCKING with a "
        "reason — but the list is meant to shrink, not grow."
    )


def test_the_known_backlog_list_is_not_stale() -> None:
    """A name that got fixed must leave the list, or the list stops meaning
    anything and quietly re-admits the shape it was recording."""
    offenders = {o[0] for o in _offenders()}
    fixed = sorted(_KNOWN_AUTHENTICATED_BLOCKING - offenders)
    assert not fixed, (
        f"these are recorded as blocking but no longer are: {fixed}. Remove "
        "them from _KNOWN_AUTHENTICATED_BLOCKING — a stale allowance is a "
        "slot a future regression can occupy for free."
    )
