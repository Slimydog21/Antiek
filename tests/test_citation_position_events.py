from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from substrate.event_log import (
    IdempotencyConflict,
    append_idempotent_typed_event_authorized,
    seal_investigation_authorized,
    trajectory_authorized_append_order,
)
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas import DocumentCitationPositionSetPayload


def _append(authority: InvestigationAuthority, *, key: str, request: str, index: int = 1):
    payload = DocumentCitationPositionSetPayload(
        receipt_sha256="a" * 64,
        index=index,
        anchor_count=3,
        mutation_key_sha256=key,
        request_sha256=request,
    )
    return append_idempotent_typed_event_authorized(
        authority,
        payload,
        document_id="doc-1",
        mutation_key_sha256=key,
        request_sha256=request,
    )


def test_replay_conflict_and_concurrency_share_one_authorized_stream_lock(tmp_path):
    authority = InvestigationAuthority("alice", "investigation", root=tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        events = list(pool.map(lambda _: _append(authority, key="b" * 64, request="c" * 64), range(16)))
    assert len({event.event_id for event in events}) == 1
    assert len(trajectory_authorized_append_order(authority)) == 1
    with pytest.raises(IdempotencyConflict):
        _append(authority, key="b" * 64, request="d" * 64, index=2)

    payload = DocumentCitationPositionSetPayload(
        receipt_sha256="a" * 64,
        index=1,
        anchor_count=3,
        mutation_key_sha256="e" * 64,
        request_sha256="f" * 64,
    )
    with pytest.raises(ValueError, match="digests do not match"):
        append_idempotent_typed_event_authorized(
            authority,
            payload,
            document_id="doc-1",
            mutation_key_sha256="0" * 64,
            request_sha256="f" * 64,
        )


def test_account_isolation_and_sealed_prefix_live_tail_append_order(tmp_path):
    alice = InvestigationAuthority("alice", "same-display-id", root=tmp_path)
    bob = InvestigationAuthority("bob", "same-display-id", root=tmp_path)
    first = _append(alice, key="1" * 64, request="2" * 64, index=0)
    assert seal_investigation_authorized(alice)
    second = _append(alice, key="3" * 64, request="4" * 64, index=2)
    _append(bob, key="5" * 64, request="6" * 64, index=1)
    assert [row["event_id"] for row in trajectory_authorized_append_order(alice)] == [first.event_id, second.event_id]
    assert [row["payload"]["index"] for row in trajectory_authorized_append_order(bob)] == [1]
    payload = trajectory_authorized_append_order(alice)[-1]["payload"]
    assert set(payload) == {
        "action_type", "receipt_sha256", "index", "anchor_count", "mutation_key_sha256", "request_sha256"
    }
    assert "doc-1" not in str(payload)
