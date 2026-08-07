"""antiek-yegge-execute SPR-01 — the ``worker.identity`` typed event.

Asserts the SUBSTRATE side: the payload is a member of the typed union,
validates ``spawn_kind`` against its closed set, rejects missing required
fields, and round-trips through the single-writer funnel (emit → persist →
query). The worker registry that EMITS these (SPR-04) is not yet built; this
test pins the event-log contract the registry will write against.

Companion: ``test_dispatch_call_token_burn_fields.py`` covers the token-burn
half (five optional fields added to ``DispatchCallPayload`` instead of a
forking second event).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from substrate.event_log import (
    emit_worker_identity,
    query_worker_identity,
    trajectory,
)
from substrate.schemas.events import (
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
    ActionType,
    WorkerIdentityPayload,
)


@pytest.fixture(autouse=True)
def _events_dir(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-worker-identity-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "events"))


# ── schema ──────────────────────────────────────────────────────────────────


def test_worker_identity_is_in_the_typed_union():
    """Read-side reconstruction treats worker.identity as typed (not dict)."""
    assert ActionType.WORKER_IDENTITY.value in TYPED_PAYLOAD_ACTION_TYPES


def test_worker_identity_records_the_spr_tag():
    """Rigor #5: the payload's origin is reconstructable from the code alone."""
    assert "SPR-01" in WorkerIdentityPayload.__doc__
    assert "yegge" in (WorkerIdentityPayload.__doc__ or "").lower()


def test_event_schema_version_bumped():
    """Adding a typed event to the union bumps EVENT_SCHEMA_VERSION.

    Pinned strict so a union change without a conscious bump reds here.
    Tracks the current value: 28 (worker.identity, yegge SPR-01) -> 29
    (DiscoveryProvider Literal += "parallel", restore #134) -> 30/31
    (SkillPatchGateDecided + SkillPatchGateReviewed, GF-3c/d Phase-8
    gate calibration audit events) -> 32 (multimedia authority events) -> 33
    (NotDiamond DispatchCallPayload attribution fields) -> 34 (owner-scoped
    account-memory graph events)."""
    assert EVENT_SCHEMA_VERSION == 34


# ── validation (rigor #3: rejects bad input at emit time) ───────────────────


@pytest.mark.parametrize(
    "spawn_kind",
    ["subprocess", "asyncio_task", "thread", "role_invocation", "variant"],
)
def test_worker_identity_accepts_each_spawn_kind(spawn_kind):
    p = WorkerIdentityPayload(
        worker_id="w1", role="extractor", session_id="s1", spawn_kind=spawn_kind
    )
    assert p.spawn_kind == spawn_kind


def test_worker_identity_rejects_unknown_spawn_kind():
    """A typo (e.g. "async") must not land as an un-queryable string."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WorkerIdentityPayload(
            worker_id="w1", role="extractor", session_id="s1", spawn_kind="async"
        )


def test_worker_identity_rejects_missing_required_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WorkerIdentityPayload(role="extractor", session_id="s1", spawn_kind="thread")  # missing worker_id
    with pytest.raises(ValidationError):
        WorkerIdentityPayload(worker_id="w1", session_id="s1", spawn_kind="thread")  # missing role


def test_worker_identity_rejects_negative_expected_lifetime():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WorkerIdentityPayload(
            worker_id="w1", role="extractor", session_id="s1",
            spawn_kind="thread", expected_lifetime_s=-1,
        )


def test_worker_identity_does_not_validate_worker_id_shape():
    """event_log stores the worker_id string verbatim — UUID-v7 validity is
    SPR-04's job, not event_log's. A non-UUID string is accepted here."""
    p = WorkerIdentityPayload(
        worker_id="not-a-uuid", role="extractor", session_id="s1", spawn_kind="thread"
    )
    assert p.worker_id == "not-a-uuid"


# ── persistence: emit → trajectory → query round-trips ──────────────────────


def test_emit_worker_identity_round_trips_and_queries():
    """The emitted event persists to the trajectory and is queryable by filter."""
    eid = emit_worker_identity(
        "inv-worker-1",
        worker_id="w-root",
        role="extractor",
        session_id="sess-1",
        spawn_kind="asyncio_task",
        parent_worker_id=None,
        context_hash="abc123",
    )
    assert eid is not None

    # The event is in the raw trajectory.
    rows = trajectory("inv-worker-1")
    worker_rows = [r for r in rows if r["action_type"] == "worker.identity"]
    assert len(worker_rows) == 1
    assert worker_rows[0]["payload"]["worker_id"] == "w-root"
    assert worker_rows[0]["payload"]["spawn_kind"] == "asyncio_task"
    assert worker_rows[0]["payload"]["context_hash"] == "abc123"

    # The query helper filters by role.
    queried = query_worker_identity("inv-worker-1", role="extractor")
    assert len(queried) == 1
    assert queried[0]["worker_id"] == "w-root"
    assert queried[0]["role"] == "extractor"

    # The query helper filters out non-matching roles.
    assert query_worker_identity("inv-worker-1", role="synthesizer") == []


def test_query_worker_identity_filters_by_worker_and_parent():
    """A child worker (parent_worker_id set) is queryable both directly and via
    its parent."""
    emit_worker_identity(
        "inv-worker-2", worker_id="w-parent", role="orchestrator",
        session_id="sess-1", spawn_kind="asyncio_task",
    )
    emit_worker_identity(
        "inv-worker-2", worker_id="w-child", role="extractor",
        session_id="sess-1", spawn_kind="role_invocation",
        parent_worker_id="w-parent",
    )
    children = query_worker_identity("inv-worker-2", parent_worker_id="w-parent")
    assert [r["worker_id"] for r in children] == ["w-child"]
    direct = query_worker_identity("inv-worker-2", worker_id="w-parent")
    assert len(direct) == 1 and direct[0]["role"] == "orchestrator"


def test_emit_worker_identity_rejects_bad_spawn_kind_at_emit_time():
    """The emit wrapper must raise (not silently drop) on a bad spawn_kind — a
    malformed event is a substrate bug, per the emit_typed contract."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        emit_worker_identity(
            "inv-worker-3", worker_id="w1", role="extractor",
            session_id="s1", spawn_kind="async",
        )
    # Nothing was written.
    assert trajectory("inv-worker-3") == []


def test_query_worker_identity_empty_when_none_emitted():
    """An honest absent — empty list, never a fabricated row."""
    assert query_worker_identity("inv-worker-none") == []
