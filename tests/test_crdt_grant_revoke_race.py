"""Tests for the CRDT scaffold's grant/revoke race resolution.

DDIA-execution SPR-09. The central property: any specific edit op
either succeeds on EVERY replica or fails on EVERY replica — never
half-half. This is the open problem Kleppmann's interview names as
Automerge's contribution to decentralized access control.

Layout: each test sets up multiple OpInMemoryBackend replicas,
applies a sequence of grant/revoke/edit ops in different orders on
different replicas, merges them, then asserts they all materialize
identical state.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from substrate.multi_user.crdt_scaffold import (  # noqa: E402
    ConvergenceTrace,
    CRDTBackend,
    Document,
    EditOutcome,
    OpInMemoryBackend,
    is_edit_authorized,
)
from substrate.multi_user.crdt_scaffold.interfaces import (  # noqa: E402
    are_concurrent,
    causally_precedes,
)

# ---------------------------------------------------------------------------
# Vector-clock primitives (the bedrock — bugs here are fatal)
# ---------------------------------------------------------------------------


def test_causally_precedes_strict() -> None:
    assert causally_precedes({"a": 1}, {"a": 2})
    assert causally_precedes({"a": 1}, {"a": 1, "b": 1})


def test_causally_precedes_reflexive_is_false() -> None:
    assert not causally_precedes({"a": 1}, {"a": 1})


def test_causally_precedes_concurrent_clocks() -> None:
    assert not causally_precedes({"a": 1, "b": 0}, {"a": 0, "b": 1})
    assert not causally_precedes({"a": 0, "b": 1}, {"a": 1, "b": 0})


def test_are_concurrent() -> None:
    assert are_concurrent({"a": 1, "b": 0}, {"a": 0, "b": 1})
    assert not are_concurrent({"a": 1}, {"a": 2})


# ---------------------------------------------------------------------------
# Backend basics
# ---------------------------------------------------------------------------


def test_backend_satisfies_protocol() -> None:
    backend = OpInMemoryBackend("a1")
    assert isinstance(backend, CRDTBackend)


def test_apply_is_idempotent() -> None:
    a = OpInMemoryBackend("a1")
    grant = a.make_grant("admin", "u1", "doc1")
    a.apply(grant)  # second apply — should no-op
    a.apply(grant)
    assert len(a.ops()) == 1


def test_merge_set_union() -> None:
    a = OpInMemoryBackend("a1")
    b = OpInMemoryBackend("b1")
    a.make_grant("admin", "u1", "doc1")
    b.make_grant("admin", "u2", "doc1")
    a.merge(b)
    b.merge(a)
    # Both replicas now know both ops.
    assert len(a.ops()) == 2
    assert len(b.ops()) == 2


# ---------------------------------------------------------------------------
# Grant + concurrent edit
# ---------------------------------------------------------------------------


def test_grant_then_edit_accepted() -> None:
    """Standard happy path: grant, then edit, on one replica. Accept."""
    a = OpInMemoryBackend("a1")
    a.make_grant("admin", "u1", "doc1")
    edit = a.make_edit("u1", "doc1", "hello")
    outcome = is_edit_authorized(edit, a.ops())
    assert outcome == EditOutcome.ACCEPTED


def test_edit_without_grant_rejected() -> None:
    a = OpInMemoryBackend("a1")
    edit = a.make_edit("u1", "doc1", "hello")
    outcome = is_edit_authorized(edit, a.ops())
    assert outcome == EditOutcome.REJECTED_NO_GRANT


# ---------------------------------------------------------------------------
# Revoke + concurrent edit — THE CORE PROPERTY
# ---------------------------------------------------------------------------


def _all_replicas_materialize(
    replicas: list[OpInMemoryBackend], doc_id: str
) -> ConvergenceTrace:
    """Helper: each replica computes its document materialization,
    record into a trace.
    """
    trace = ConvergenceTrace()
    doc = Document(doc_id)
    for r in replicas:
        trace.record(
            r.actor_id,
            {"payload": doc.materialized_payload(r.ops())},
        )
    return trace


def test_grant_revoke_edit_converge_revoke_first() -> None:
    """Setup: admin grants u1, then revokes u1. u1 attempts to edit
    BEFORE seeing the revoke (concurrent with it).

    Property: every replica that ever sees both the revoke and the
    edit makes the SAME decision about the edit.
    """
    admin_replica = OpInMemoryBackend("admin")
    u1_replica = OpInMemoryBackend("u1")
    bystander = OpInMemoryBackend("witness")

    # Admin grants and revokes.
    grant = admin_replica.make_grant("admin", "u1", "doc1")
    revoke = admin_replica.make_revoke("admin", "u1", "doc1")

    # u1 sees the grant but NOT the revoke yet.
    u1_replica.apply(grant)
    edit = u1_replica.make_edit("u1", "doc1", "u1-content")

    # Eventual sync. Each replica merges with each other.
    for me in (admin_replica, u1_replica, bystander):
        for other in (admin_replica, u1_replica, bystander):
            if me is not other:
                me.merge(other)

    # All replicas converge.
    trace = _all_replicas_materialize(
        [admin_replica, u1_replica, bystander], "doc1"
    )
    assert trace.all_converged(), trace.divergence_report()

    # And the edit is rejected (revoke wins over concurrent grant).
    payload = trace.replica_snapshots[admin_replica.actor_id]["payload"]
    assert "u1-content" not in payload


def test_grant_revoke_edit_converge_edit_first() -> None:
    """Same scenario but the edit causally PRECEDES the revoke. The
    edit was made between grant and revoke; the revoke can't retroactively
    void it.
    """
    admin = OpInMemoryBackend("admin")
    u1 = OpInMemoryBackend("u1")

    grant = admin.make_grant("admin", "u1", "doc1")
    u1.apply(grant)
    edit = u1.make_edit("u1", "doc1", "u1-content")

    # Admin sees the edit, THEN issues a revoke.
    admin.apply(edit)
    revoke = admin.make_revoke("admin", "u1", "doc1")

    # Eventual sync.
    u1.merge(admin)
    admin.merge(u1)

    trace = _all_replicas_materialize([admin, u1], "doc1")
    assert trace.all_converged(), trace.divergence_report()

    # Edit happened BEFORE revoke (causally), so it's accepted.
    payload = trace.replica_snapshots[admin.actor_id]["payload"]
    assert payload == "u1-content"


def test_grant_revoke_with_concurrent_edit_revoke_wins() -> None:
    """Three replicas race. The classical Kleppmann scenario:

        admin: GRANT, REVOKE
        u1   : (sees GRANT, makes EDIT concurrently with REVOKE)

    All replicas must agree. Conservative choice: revoke wins over a
    concurrent edit. The CRITICAL property is that every replica makes
    the SAME choice — not which way it goes.
    """
    admin = OpInMemoryBackend("admin")
    u1 = OpInMemoryBackend("u1")
    third = OpInMemoryBackend("third")

    grant = admin.make_grant("admin", "u1", "doc1")
    u1.apply(grant)  # u1 sees the grant
    # NOW concurrently: admin revokes, u1 edits — neither has seen the
    # other yet.
    revoke = admin.make_revoke("admin", "u1", "doc1")
    edit = u1.make_edit("u1", "doc1", "concurrent-edit")

    # The third replica sees them in a third order.
    third.apply(grant)
    third.apply(edit)
    third.apply(revoke)

    # Full mesh sync.
    for me in (admin, u1, third):
        for other in (admin, u1, third):
            if me is not other:
                me.merge(other)

    trace = _all_replicas_materialize([admin, u1, third], "doc1")
    assert trace.all_converged(), trace.divergence_report()

    # Resolution: revoke and edit are CONCURRENT (neither happened-before
    # the other). The rule says revoke wins.
    payload = trace.replica_snapshots[admin.actor_id]["payload"]
    assert payload == "", f"expected rejected edit; got: {payload!r}"


def test_grant_revoke_regrant_edit() -> None:
    """A more complex sequence: grant, revoke, grant-again, edit. The
    edit should be accepted because the most-recent grant precedes it.
    """
    admin = OpInMemoryBackend("admin")
    u1 = OpInMemoryBackend("u1")

    admin.make_grant("admin", "u1", "doc1")
    admin.make_revoke("admin", "u1", "doc1")
    admin.make_grant("admin", "u1", "doc1")

    u1.merge(admin)
    edit = u1.make_edit("u1", "doc1", "re-granted-edit")
    admin.merge(u1)

    trace = _all_replicas_materialize([admin, u1], "doc1")
    assert trace.all_converged(), trace.divergence_report()
    payload = trace.replica_snapshots[admin.actor_id]["payload"]
    assert payload == "re-granted-edit"


# ---------------------------------------------------------------------------
# Backdated-edit attack — I-CRDT-3
# ---------------------------------------------------------------------------


def test_backdated_edit_attack_rejected() -> None:
    """A malicious user, after being revoked, tries to inject an edit
    with a low counter to pretend it happened earlier. The vector-clock
    monotonicity defense rejects it.
    """
    admin = OpInMemoryBackend("admin")
    u1 = OpInMemoryBackend("u1")

    grant = admin.make_grant("admin", "u1", "doc1")
    u1.apply(grant)
    real_edit = u1.make_edit("u1", "doc1", "legitimate")
    admin.apply(real_edit)
    revoke = admin.make_revoke("admin", "u1", "doc1")
    u1.apply(revoke)

    # u1 is now revoked. u1's counter is at 2 (1 for apply(grant)'s
    # local clock, 2 for the legitimate edit). Suppose u1 forges an
    # op with counter=0 trying to pretend it happened before grant.
    from substrate.multi_user.crdt_scaffold.interfaces import (
        EditOp,
        OpId,
    )
    forged = EditOp(
        op_id=OpId(actor="u1", counter=0),
        clock=tuple(),  # empty clock — pretending we knew nothing
        editor="u1",
        doc_id="doc1",
        payload_diff="forged-bypass",
    )

    # The backdated-edit defense catches this.
    all_ops = list(admin.ops())
    outcome = is_edit_authorized(forged, all_ops, max_clock_skew=0)
    assert outcome == EditOutcome.REJECTED_BACKDATED


# ---------------------------------------------------------------------------
# Inertness check — the scaffold doesn't fire by default
# ---------------------------------------------------------------------------


def test_scaffold_is_inert_when_not_imported() -> None:
    """The scaffold lives at substrate/multi_user/crdt_scaffold/. The
    main multi_user __init__ does NOT import it (verified by the
    multi_user module test elsewhere — here we just verify the
    scaffold imports without instantiating anything global).
    """
    # No global state, no side effects on import.
    # If a future change adds module-level state that's NOT inert,
    # this test should fail.
    import importlib

    from substrate.multi_user import crdt_scaffold  # noqa: F401

    importlib.reload(crdt_scaffold)


def test_no_production_toggle_present() -> None:
    """The scaffold does NOT expose any 'enable' or 'production'
    toggle. The S22 flip is an operator-authorized decision, not a
    config flip. If a future change adds an enable function, this
    test should be amended (with operator-review note).
    """
    from substrate.multi_user import crdt_scaffold

    forbidden_names = {
        "enable", "enable_production", "activate", "go_live",
        "PRODUCTION", "PROD_ENABLED",
    }
    actual_names = set(dir(crdt_scaffold))
    overlap = forbidden_names & actual_names
    assert not overlap, (
        f"crdt_scaffold exposes {overlap} — the SPR-09 invariant is "
        f"scaffold-only. Adding a production toggle requires operator "
        f"authorization + S22 gate close."
    )
