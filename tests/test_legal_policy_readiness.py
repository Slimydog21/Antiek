from __future__ import annotations

from datetime import UTC, datetime

import pytest

from runtime.db_lock import connect_write
from substrate.graph import ensure_initialized
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.policy_store import (
    LegalPolicyDenied,
    account_policy_authority,
    append_policy_event,
)
from substrate.legal_gate.readiness import (
    claim_policy_dispatch_lease,
    legal_policy_readiness,
    release_policy_dispatch_lease,
    require_policy_snapshot,
    snapshot_legal_gate,
)


def test_readiness_is_closed_but_snapshot_bound_without_issuer(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("ANTIEK_LEGAL_POLICY_ADMIN_ENABLED", raising=False)
    path = str(tmp_path / "graph.duckdb")
    ensure_initialized(path)
    investigation = InvestigationAuthority("alice", "root")
    initialize_composite_stream(investigation)
    authority = account_policy_authority(investigation)
    con = connect_write(path, purpose="test_legal_readiness")
    try:
        readiness = legal_policy_readiness(con, authority)
        assert readiness.migration_state == "current"
        assert len(readiness.policy_snapshot_sha256 or "") == 64
        assert readiness.issuer_state == "not_configured"
        assert readiness.production_defensible is False
    finally:
        con.close()


def test_exact_snapshot_claim_rejects_policy_drift(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "graph.duckdb")
    ensure_initialized(path)
    investigation = InvestigationAuthority("alice", "root")
    initialize_composite_stream(investigation)
    authority = account_policy_authority(investigation)
    con = connect_write(path, purpose="test_legal_snapshot_drift")
    try:
        reviewed = legal_policy_readiness(con, authority).policy_snapshot_sha256
        assert reviewed is not None
        append_policy_event(
            con,
            authority,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="deny",
            citation_ref="case:1",
            issuer_id="alice",
            reason_code="operator_deny",
            effective_at=datetime.now(UTC),
        )
        with pytest.raises(LegalPolicyDenied, match="changed after launch review"):
            require_policy_snapshot(con, authority, expected_sha256=reviewed)
    finally:
        con.close()


def test_snapshot_gate_requires_explicit_external_allow(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "graph.duckdb")
    ensure_initialized(path)
    investigation = InvestigationAuthority("alice", "root")
    initialize_composite_stream(investigation)
    authority = account_policy_authority(investigation)
    con = connect_write(path, purpose="test_snapshot_gate")
    try:
        empty = legal_policy_readiness(con, authority).policy_snapshot_sha256
        assert empty is not None
        denied = snapshot_legal_gate(con, authority, expected_sha256=empty).check_url(
            "https://example.com/paper"
        )
        assert denied.allowed is False
        assert denied.gate_kind == "durable_sql_policy"
        append_policy_event(
            con,
            authority,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="license:1",
            issuer_id="alice",
            reason_code="licensed_source",
            effective_at=datetime.now(UTC),
        )
        current = legal_policy_readiness(con, authority).policy_snapshot_sha256
        assert current is not None
        allowed = snapshot_legal_gate(con, authority, expected_sha256=current).check_url(
            "https://example.com/paper"
        )
        assert allowed.allowed is True
    finally:
        con.close()


def test_account_policy_snapshot_crosses_own_streams_but_not_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "graph.duckdb")
    ensure_initialized(path)
    alice_root = InvestigationAuthority("alice", "root")
    alice_leaf = InvestigationAuthority("alice", "leaf")
    bob_leaf = InvestigationAuthority("bob", "leaf")
    for investigation in (alice_root, alice_leaf, bob_leaf):
        initialize_composite_stream(investigation)
    alice_authority = account_policy_authority(alice_root)
    con = connect_write(path, purpose="test_account_policy_scope")
    try:
        append_policy_event(
            con,
            alice_authority,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="allow",
            citation_ref="license:alice",
            issuer_id="alice",
            reason_code="licensed_source",
            effective_at=datetime.now(UTC),
        )
        root_snapshot = legal_policy_readiness(con, alice_authority).policy_snapshot_sha256
        leaf_snapshot = legal_policy_readiness(
            con, account_policy_authority(alice_leaf)
        ).policy_snapshot_sha256
        bob_snapshot = legal_policy_readiness(
            con, account_policy_authority(bob_leaf)
        ).policy_snapshot_sha256
        assert root_snapshot == leaf_snapshot
        assert bob_snapshot != root_snapshot
    finally:
        con.close()


def test_dispatch_lease_blocks_policy_change_until_owner_release(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "graph.duckdb")
    ensure_initialized(path)
    investigation = InvestigationAuthority("alice", "leaf")
    initialize_composite_stream(investigation)
    authority = account_policy_authority(investigation)
    con = connect_write(path, purpose="test_policy_dispatch_lease")
    try:
        reviewed = legal_policy_readiness(con, authority).policy_snapshot_sha256
        assert reviewed is not None
        lease_id, _gate = claim_policy_dispatch_lease(
            con,
            authority,
            holder_investigation_digest=investigation.investigation_digest,
            expected_sha256=reviewed,
        )
        event_kwargs = {
            "scope_kind": "account",
            "matcher_kind": "domain",
            "matcher_value": "example.com",
            "decision": "deny",
            "citation_ref": "case:lease",
            "issuer_id": "alice",
            "reason_code": "operator_deny",
            "effective_at": datetime.now(UTC),
        }
        with pytest.raises(LegalPolicyDenied, match="active provider dispatch"):
            append_policy_event(con, authority, **event_kwargs)
        release_policy_dispatch_lease(
            con,
            authority,
            lease_id=lease_id,
            holder_investigation_digest=investigation.investigation_digest,
        )
        assert append_policy_event(con, authority, **event_kwargs).startswith("lpe-")
    finally:
        con.close()


def test_dispatch_lease_deadline_never_auto_unlocks_policy(tmp_path, monkeypatch):
    """A stale deadline is diagnostic; only an explicit owner release unlocks."""
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    path = str(tmp_path / "graph.duckdb")
    ensure_initialized(path)
    investigation = InvestigationAuthority("alice", "leaf")
    initialize_composite_stream(investigation)
    authority = account_policy_authority(investigation)
    con = connect_write(path, purpose="test_stale_policy_dispatch_lease")
    try:
        reviewed = legal_policy_readiness(con, authority).policy_snapshot_sha256
        assert reviewed is not None
        lease_id, _gate = claim_policy_dispatch_lease(
            con,
            authority,
            holder_investigation_digest=investigation.investigation_digest,
            expected_sha256=reviewed,
            ttl_seconds=1,
        )
        con.execute(
            "UPDATE legal_policy_dispatch_leases "
            "SET acquired_at = TIMESTAMP '2000-01-01 00:00:00', "
            "expires_at = TIMESTAMP '2000-01-01 00:00:01' WHERE lease_id = ?",
            [lease_id],
        )
        with pytest.raises(LegalPolicyDenied, match="active provider dispatch"):
            append_policy_event(
                con,
                authority,
                scope_kind="account",
                matcher_kind="domain",
                matcher_value="example.com",
                decision="deny",
                citation_ref="case:stale-lease",
                issuer_id="alice",
                reason_code="operator_deny",
                effective_at=datetime.now(UTC),
            )
        release_policy_dispatch_lease(
            con,
            authority,
            lease_id=lease_id,
            holder_investigation_digest=investigation.investigation_digest,
        )
    finally:
        con.close()
