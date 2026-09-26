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
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_MODULE = _ROOT / "interfaces" / "research" / "api" / "speak_routes.py"

#: Names that acquire the single-writer flock, directly or one hop away.
_WRITE_ENTRIES = {"_write", "connect_write"}

#: Plain substrate functions that open ``connect_write`` THEMSELVES — two
#: hops from the route. The repo's one-hop lint keys on a direct
#: ``connect_write`` entry or a ``@contextmanager`` wrapper, so a plain
#: function call is invisible to it; this list is how the guard sees the
#: two-hop shape. Each name is premise-checked by
#: ``test_two_hop_entries_really_take_the_write_lock`` below.
_TWO_HOP_WRITE_ENTRIES = frozenset({
    "submit_answer",
    "next_followups",
    "decline",
    "list_private_repings_at",
    "prepare_reping",
})

#: Calls that run their callable argument off the event loop. A nested sync
#: def only counts as offloaded when the coroutine hands it to one of these.
_DISPATCHERS = frozenset({"_off_loop", "to_thread", "run_in_executor"})


def _module() -> ast.Module:
    return ast.parse(_MODULE.read_text(encoding="utf-8"))


def _write_entry_name(call: ast.Call) -> str | None:
    """The write-lock entry a call reaches, or None if it reaches none.

    One-hop entries are bare names (``_write``, ``connect_write``). The
    two-hop substrate helpers appear either as a bare name
    (``submit_answer(...)``) or through the ``speak_pushes`` module alias
    (``speak_pushes.prepare_reping(...)``), so attribute calls match on
    their attribute.
    """
    func = call.func
    if (
        isinstance(func, ast.Name)
        and func.id in _WRITE_ENTRIES | _TWO_HOP_WRITE_ENTRIES
    ):
        return func.id
    if isinstance(func, ast.Attribute) and func.attr in _TWO_HOP_WRITE_ENTRIES:
        return func.attr
    return None


def _call_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _offloaded_lines(coro: ast.AsyncFunctionDef) -> set[int]:
    """Lines of the nested sync defs this coroutine really runs off the loop.

    That is the `def _sync(): ...; await _off_loop(_sync)` idiom. Being a
    nested def is not enough: the def must be passed to a dispatcher
    (``_DISPATCHERS``), and the coroutine body must not also call it
    directly, which would run the same writes on the loop.
    """
    nested = [n for n in ast.walk(coro) if isinstance(n, ast.FunctionDef)]
    nested_lines: set[int] = set()
    for d in nested:
        nested_lines.update(range(d.lineno, (d.end_lineno or d.lineno) + 1))
    dispatched: set[str] = set()
    called_on_loop: set[str] = set()
    for sub in ast.walk(coro):
        if not isinstance(sub, ast.Call):
            continue
        if _call_name(sub) in _DISPATCHERS:
            dispatched.update(a.id for a in sub.args if isinstance(a, ast.Name))
        elif isinstance(sub.func, ast.Name) and sub.lineno not in nested_lines:
            called_on_loop.add(sub.func.id)
    offloaded: set[int] = set()
    for d in nested:
        if d.name in dispatched and d.name not in called_on_loop:
            offloaded.update(range(d.lineno, (d.end_lineno or d.lineno) + 1))
    return offloaded


def _offenders(tree: ast.Module | None = None) -> list[tuple[str, int, str]]:
    """(coroutine, line, callee) for every write entry ON the loop."""
    out: list[tuple[str, int, str]] = []
    for node in ast.walk(tree if tree is not None else _module()):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        offloaded = _offloaded_lines(node)
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            entry = _write_entry_name(sub)
            if entry is not None and sub.lineno not in offloaded:
                out.append((node.name, sub.lineno, entry))
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


def test_offload_requires_dispatch_not_just_a_nested_def() -> None:
    """A nested def only counts as off the loop when it is dispatched.

    The earlier version of ``_offenders`` treated every line inside a
    nested sync def as offloaded, so `rows = _sync()` (the dispatch
    dropped) passed this file. These shapes pin the rule.
    """
    src = """
async def direct():
    def _sync():
        with _write("x") as con:
            return con
    return _sync()

async def dispatched():
    def _sync():
        with _write("x") as con:
            return con
    return await _off_loop(_sync)

async def to_thread_dispatched():
    def _sync():
        return submit_answer("db")
    return await asyncio.to_thread(_sync)

async def dispatched_and_called():
    def _sync():
        return speak_pushes.prepare_reping("db")
    _sync()
    return await _off_loop(_sync)
"""
    offenders = {name for name, _line, _entry in _offenders(ast.parse(src))}
    assert offenders == {"direct", "dispatched_and_called"}, offenders


def test_the_real_module_dispatches_its_nested_defs() -> None:
    """Premise for the rule above: the migrated routes are recognised as
    dispatched, so the guard's zero comes from dispatch, not from an empty
    walk."""
    coros = [n for n in ast.walk(_module()) if isinstance(n, ast.AsyncFunctionDef)]
    with_dispatch = [c.name for c in coros if _offloaded_lines(c)]
    assert len(with_dispatch) >= 24, (
        f"only {len(with_dispatch)} coroutines dispatch a nested def; 28 did "
        "when this was written (18 migrated authenticated routes, the 6 "
        "unauthenticated ones, the 4 two-hop handlers)"
    )


def test_two_hop_entries_really_take_the_write_lock() -> None:
    """Premise: every _TWO_HOP_WRITE_ENTRIES name really reaches connect_write.

    The list exists because these are PLAIN functions that open
    ``connect_write`` themselves — one hop beyond what the repo lint sees.
    If a name stops writing (refactor, rename), matching it stops guarding
    anything; fail so the list gets pruned instead of rotting.
    """
    from substrate.speak import async_interview, pushes

    owners: dict[str, Callable[..., Any]] = {
        "submit_answer": async_interview.submit_answer,
        "next_followups": async_interview.next_followups,
        "decline": async_interview.decline,
        "list_private_repings_at": pushes.list_private_repings_at,
        "prepare_reping": pushes.prepare_reping,
    }
    assert set(owners) == set(_TWO_HOP_WRITE_ENTRIES), (
        "_TWO_HOP_WRITE_ENTRIES and the owners map drifted apart — every "
        "entry needs an owner here so the premise check covers it"
    )
    for name, fn in sorted(owners.items()):
        assert "connect_write" in inspect.getsource(fn), (
            f"{name} no longer calls connect_write — remove it from "
            "_TWO_HOP_WRITE_ENTRIES; a matched name that does not write "
            "is a guard over nothing"
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
#:
#: EMPTY since the 2026-09 Speak write migration (the `_off_loop` idiom):
#: all 18 authenticated on-loop writes moved into `def _sync()` +
#: `await _off_loop(_sync)`. Keep the name and the shrink-only tests — a new
#: on-loop write must still fail rather than re-open the backlog.
_KNOWN_AUTHENTICATED_BLOCKING = frozenset({
    # Empty on purpose. A name added back here is a regression being
    # grandfathered, not a fix.
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
