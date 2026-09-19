from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import SCHEMA_TABLES, init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate import policy_store as policy_store_module
from substrate.legal_gate.policy_store import (
    GlobalPolicyAdminCapability,
    LegalPolicyAuthority,
    LegalPolicyDenied,
    account_policy_authority,
    append_policy_event,
    evaluate_document,
    global_policy_authority,
    load_global_policy_admin_capability,
    policy_snapshot,
)

NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _global_capability(monkeypatch):
    monkeypatch.setenv("ANTIEK_LEGAL_POLICY_ADMIN_ENABLED", "1")
    monkeypatch.setenv("ANTIEK_LEGAL_POLICY_ISSUER_ID", "operator-policy-issuer")
    monkeypatch.setenv("ANTIEK_LEGAL_POLICY_RATIFICATION_SHA256", "9" * 64)
    return load_global_policy_admin_capability()


def _database(tmp_path):
    path = str(tmp_path / "legal.duckdb")
    init_database_at_path(path)
    return path


def _account(tmp_path, account_id):
    authority = InvestigationAuthority(
        account_id,
        "legal-admin",
        root=tmp_path / "tenancy",
    )
    initialize_composite_stream(authority)
    return account_policy_authority(authority)


def test_policy_snapshot_is_deterministic_cited_and_owner_scoped(tmp_path, monkeypatch):
    path = _database(tmp_path)
    operator = global_policy_authority(_global_capability(monkeypatch))
    alice = _account(tmp_path, "alice")
    bob = _account(tmp_path, "bob")
    with connect_write(path, purpose="legal-policy-test") as con:
        global_id = append_policy_event(
            con,
            operator,
            scope_kind="global",
            matcher_kind="domain",
            matcher_value="Example.COM.",
            decision="deny",
            citation_ref="court-order-17",
            issuer_id="operator-policy-issuer",
            reason_code="takedown",
            effective_at=NOW,
        )
        alice_id = append_policy_event(
            con,
            alice,
            scope_kind="account",
            matcher_kind="corpus",
            matcher_value="  Licensed-Corpus  ",
            decision="allow",
            citation_ref="license-42",
            issuer_id="alice-rights-import",
            reason_code="personal-license",
            effective_at=NOW,
        )
        alice_snapshot = policy_snapshot(con, alice, at=NOW + timedelta(seconds=1))
        bob_snapshot = policy_snapshot(con, bob, at=NOW + timedelta(seconds=1))

    assert [row["event_id"] for row in alice_snapshot.active_events] == [
        global_id,
        alice_id,
    ]
    assert [row["event_id"] for row in bob_snapshot.active_events] == [global_id]
    assert alice_snapshot.snapshot_sha256 != bob_snapshot.snapshot_sha256
    assert alice_snapshot.active_events[0]["matcher_value"] == "example.com"
    assert alice_snapshot.active_events[1]["matcher_value"] == "licensed-corpus"


def test_policy_events_are_idempotent_append_only_and_revocable(tmp_path):
    path = _database(tmp_path)
    alice = _account(tmp_path, "alice")
    kwargs = dict(
        scope_kind="account",
        matcher_kind="content_sha256",
        matcher_value="a" * 64,
        decision="deny",
        citation_ref="notice-1",
        issuer_id="alice-policy",
        reason_code="owner-block",
        effective_at=NOW,
    )
    with connect_write(path, purpose="legal-policy-test") as con:
        event_id = append_policy_event(con, alice, **kwargs)
        assert append_policy_event(con, alice, **kwargs) == event_id
        revoke_id = append_policy_event(
            con,
            alice,
            **{
                **kwargs,
                "decision": "revoke",
                "citation_ref": "notice-1-withdrawn",
                "effective_at": NOW + timedelta(minutes=1),
                "supersedes_event_id": event_id,
            },
        )
        snapshot = policy_snapshot(con, alice, at=NOW + timedelta(minutes=2))
        rows = con.execute(
            "SELECT event_id FROM legal_policy_events ORDER BY created_at"
        ).fetchall()
    assert revoke_id != event_id
    assert rows == [(event_id,), (revoke_id,)]
    assert snapshot.active_events == ()


def test_global_policy_cannot_be_forged_or_allow(tmp_path, monkeypatch):
    path = _database(tmp_path)
    alice = _account(tmp_path, "__operator__")
    with pytest.raises(LegalPolicyDenied):
        LegalPolicyAuthority(
            account_digest=None,
            global_capability_fingerprint="forged",
            global_issuer_id="forged",
            _token=object(),
        )
    with pytest.raises(LegalPolicyDenied):
        GlobalPolicyAdminCapability(
            issuer_id="forged",
            ratification_fingerprint="forged",
            _token=object(),
        )
    monkeypatch.delenv("ANTIEK_LEGAL_POLICY_ADMIN_ENABLED", raising=False)
    with pytest.raises(LegalPolicyDenied):
        load_global_policy_admin_capability()
    with connect_write(path, purpose="legal-policy-test") as con:
        with pytest.raises(LegalPolicyDenied):
            append_policy_event(
                con,
                alice,
                scope_kind="global",
                matcher_kind="domain",
                matcher_value="example.com",
                decision="deny",
                citation_ref="order",
                issuer_id="forged",
                reason_code="forged",
                effective_at=NOW,
            )
        with pytest.raises(ValueError):
            append_policy_event(
                con,
                global_policy_authority(_global_capability(monkeypatch)),
                scope_kind="global",
                matcher_kind="domain",
                matcher_value="example.com",
                decision="allow",
                citation_ref="order",
                issuer_id="operator-policy-issuer",
                reason_code="allow",
                effective_at=NOW,
            )
        capability = _global_capability(monkeypatch)
        with pytest.raises(LegalPolicyDenied):
            append_policy_event(
                con,
                global_policy_authority(capability),
                scope_kind="global",
                matcher_kind="domain",
                matcher_value="example.com",
                decision="deny",
                citation_ref="order",
                issuer_id="different-issuer",
                reason_code="deny",
                effective_at=NOW,
            )


def test_revocation_cannot_expire_and_resurrect_policy(tmp_path):
    path = _database(tmp_path)
    alice = _account(tmp_path, "alice")
    with connect_write(path, purpose="legal-policy-test") as con:
        event_id = append_policy_event(
            con,
            alice,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="deny",
            citation_ref="notice-1",
            issuer_id="alice-policy",
            reason_code="owner-block",
            effective_at=NOW,
        )
        with pytest.raises(ValueError):
            append_policy_event(
                con,
                alice,
                scope_kind="account",
                matcher_kind="domain",
                matcher_value="example.com",
                decision="revoke",
                citation_ref="notice-withdrawn",
                issuer_id="alice-policy",
                reason_code="withdrawn",
                effective_at=NOW + timedelta(minutes=1),
                expires_at=NOW + timedelta(minutes=2),
                supersedes_event_id=event_id,
            )


def test_global_deny_precedes_account_allow(tmp_path, monkeypatch):
    path = _database(tmp_path)
    operator = global_policy_authority(_global_capability(monkeypatch))
    alice = _account(tmp_path, "alice")
    with connect_write(path, purpose="legal-policy-test") as con:
        global_deny = append_policy_event(
            con,
            operator,
            scope_kind="global",
            matcher_kind="domain",
            matcher_value="restricted.example",
            decision="deny",
            citation_ref="order-9",
            issuer_id="operator-policy-issuer",
            reason_code="global-restriction",
            effective_at=NOW,
        )
        append_policy_event(
            con,
            alice,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="restricted.example",
            decision="allow",
            citation_ref="personal-license-9",
            issuer_id="alice-rights-import",
            reason_code="personal-license",
            effective_at=NOW,
        )
        snapshot = policy_snapshot(con, alice, at=NOW + timedelta(seconds=1))
    verdict = evaluate_document(snapshot, url="https://sub.restricted.example/paper")
    assert verdict.decision == "deny"
    assert verdict.matched_event_ids == (global_deny,)
    assert verdict.reason_code == "global-restriction"


def test_account_allow_and_no_decision_remain_distinct(tmp_path):
    path = _database(tmp_path)
    alice = _account(tmp_path, "alice")
    with connect_write(path, purpose="legal-policy-test") as con:
        append_policy_event(
            con,
            alice,
            scope_kind="account",
            matcher_kind="author",
            matcher_value="Ada Lovelace",
            decision="allow",
            citation_ref="public-domain-review-1",
            issuer_id="alice-rights-import",
            reason_code="public-domain",
            effective_at=NOW,
        )
        snapshot = policy_snapshot(con, alice, at=NOW + timedelta(seconds=1))
    assert evaluate_document(snapshot, author="Countess  Ada\tLovelace").decision == "allow"
    assert evaluate_document(snapshot, author="Grace Hopper").decision == "no_decision"


def test_snapshot_rejects_forged_authority_and_corrupt_event(tmp_path):
    path = _database(tmp_path)
    alice = _account(tmp_path, "alice")
    with connect_write(path, purpose="legal-policy-test") as con:
        append_policy_event(
            con,
            alice,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="example.com",
            decision="deny",
            citation_ref="notice",
            issuer_id="alice-policy",
            reason_code="owner-block",
            effective_at=NOW,
        )
        con.execute("UPDATE legal_policy_events SET citation_ref = 'tampered'")
        with pytest.raises(LegalPolicyDenied, match="integrity"):
            policy_snapshot(con, alice, at=NOW + timedelta(seconds=1))

    class Forged:
        account_digest = alice.account_digest

    with (
        duckdb.connect(path, read_only=True) as con,
        pytest.raises(LegalPolicyDenied, match="authority"),
    ):
        policy_snapshot(con, Forged(), at=NOW + timedelta(seconds=1))  # type: ignore[arg-type]


def test_database_constraints_reject_structurally_invalid_events(tmp_path):
    path = _database(tmp_path)
    with (
        connect_write(path, purpose="legal-policy-test") as con,
        pytest.raises(duckdb.ConstraintException),
    ):
        con.execute(
            "INSERT INTO legal_policy_events "
            "(event_id, scope_kind, account_digest, matcher_kind, matcher_value, "
            "decision, citation_ref, issuer_id, reason_code, effective_at, expires_at, "
            "supersedes_event_id, capability_fingerprint, event_fingerprint) "
            "VALUES (?, 'account', 'acct', 'domain', 'example.com', 'revoke', "
            "'citation', 'issuer', 'reason', ?, ?, NULL, '', ?)",
            ["lpe-" + "a" * 32, NOW, NOW + timedelta(minutes=1), "a" * 64],
        )


def test_snapshot_survives_restart_and_is_independent_of_insert_order(tmp_path):
    def build(path, values):
        init_database_at_path(path)
        alice = _account(tmp_path, "alice")
        with connect_write(path, purpose="legal-policy-test") as con:
            for value in values:
                append_policy_event(
                    con,
                    alice,
                    scope_kind="account",
                    matcher_kind="domain",
                    matcher_value=value,
                    decision="deny",
                    citation_ref=f"notice-{value}",
                    issuer_id="alice-policy",
                    reason_code="owner-block",
                    effective_at=NOW,
                )
        with duckdb.connect(path, read_only=True) as con:
            return policy_snapshot(con, alice, at=NOW + timedelta(seconds=1))

    forward = build(str(tmp_path / "forward.duckdb"), ["a.example", "b.example"])
    reverse = build(str(tmp_path / "reverse.duckdb"), ["b.example", "a.example"])
    assert forward == reverse


def test_expiry_and_transaction_rollback_are_fail_closed(tmp_path):
    path = _database(tmp_path)
    alice = _account(tmp_path, "alice")
    with connect_write(path, purpose="legal-policy-test") as con:
        append_policy_event(
            con,
            alice,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="expired.example",
            decision="allow",
            citation_ref="temporary-license",
            issuer_id="alice-policy",
            reason_code="temporary-license",
            effective_at=NOW,
            expires_at=NOW + timedelta(minutes=1),
        )
        con.execute("BEGIN TRANSACTION")
        append_policy_event(
            con,
            alice,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="rolled-back.example",
            decision="deny",
            citation_ref="draft-notice",
            issuer_id="alice-policy",
            reason_code="draft",
            effective_at=NOW,
        )
        con.execute("ROLLBACK")
        snapshot = policy_snapshot(con, alice, at=NOW + timedelta(minutes=2))
    assert snapshot.active_events == ()


def test_concurrent_policy_writers_serialize_without_loss(tmp_path):
    path = _database(tmp_path)
    alice = _account(tmp_path, "alice")

    def write(value):
        with connect_write(path, purpose="concurrent-legal-policy") as con:
            return append_policy_event(
                con,
                alice,
                scope_kind="account",
                matcher_kind="domain",
                matcher_value=value,
                decision="deny",
                citation_ref=f"notice-{value}",
                issuer_id="alice-policy",
                reason_code="owner-block",
                effective_at=NOW,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        event_ids = list(pool.map(write, ["one.example", "two.example"]))
    with duckdb.connect(path, read_only=True) as con:
        snapshot = policy_snapshot(con, alice, at=NOW + timedelta(seconds=1))
    assert len(set(event_ids)) == 2
    assert {row["event_id"] for row in snapshot.active_events} == set(event_ids)


def test_event_id_collision_fails_closed(tmp_path, monkeypatch):
    path = _database(tmp_path)
    alice = _account(tmp_path, "alice")
    prefix = "b" * 32
    with connect_write(path, purpose="legal-policy-test") as con:
        con.execute(
            "INSERT INTO legal_policy_events "
            "(event_id, scope_kind, account_digest, matcher_kind, matcher_value, "
            "decision, citation_ref, issuer_id, reason_code, effective_at, "
            "capability_fingerprint, event_fingerprint) "
            "VALUES (?, 'account', ?, 'domain', 'seed.example', 'deny', "
            "'seed', 'seed', 'seed', ?, ?, ?)",
            [
                f"lpe-{prefix}",
                alice.account_digest,
                NOW,
                alice.global_capability_fingerprint,
                "b" * 64,
            ],
        )

        class ForcedDigest:
            def hexdigest(self):
                return prefix + "c" * 32

        monkeypatch.setattr(policy_store_module.hashlib, "sha256", lambda _value: ForcedDigest())
        with pytest.raises(LegalPolicyDenied, match="collision"):
            append_policy_event(
                con,
                alice,
                scope_kind="account",
                matcher_kind="domain",
                matcher_value="new.example",
                decision="deny",
                citation_ref="notice",
                issuer_id="alice-policy",
                reason_code="owner-block",
                effective_at=NOW,
            )


def test_account_policy_authority_requires_durable_stream_binding(tmp_path):
    root = tmp_path / "unbound-tenancy"
    root.mkdir()
    authority = InvestigationAuthority("alice", "legal-admin", root=root)

    with pytest.raises(RuntimeError, match="no account ownership binding"):
        account_policy_authority(authority)


def test_snapshot_rejects_rehashed_cross_scope_revocation(tmp_path, monkeypatch):
    path = _database(tmp_path)
    operator = global_policy_authority(_global_capability(monkeypatch))
    alice = _account(tmp_path, "alice")
    with connect_write(path, purpose="legal-policy-test") as con:
        global_id = append_policy_event(
            con,
            operator,
            scope_kind="global",
            matcher_kind="domain",
            matcher_value="restricted.example",
            decision="deny",
            citation_ref="court-order-1",
            issuer_id="operator-policy-issuer",
            reason_code="global-restriction",
            effective_at=NOW,
        )
        forged = {
            "scope_kind": "account",
            "account_digest": alice.account_digest,
            "matcher_kind": "domain",
            "matcher_value": "restricted.example",
            "decision": "revoke",
            "citation_ref": "forged-withdrawal",
            "issuer_id": "alice-policy",
            "reason_code": "forged",
            "effective_at": (NOW + timedelta(minutes=1)).isoformat(),
            "expires_at": None,
            "supersedes_event_id": global_id,
            "capability_fingerprint": alice.global_capability_fingerprint,
        }
        encoded = json.dumps(forged, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        con.execute(
            "INSERT INTO legal_policy_events "
            "(event_id, scope_kind, account_digest, matcher_kind, matcher_value, "
            "decision, citation_ref, issuer_id, reason_code, effective_at, expires_at, "
            "supersedes_event_id, capability_fingerprint, event_fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [f"lpe-{fingerprint[:32]}", *forged.values(), fingerprint],
        )

        with pytest.raises(LegalPolicyDenied, match="revocation authority"):
            policy_snapshot(con, alice, at=NOW + timedelta(minutes=2))


def test_snapshot_rejects_rehashed_global_event_without_installed_authority(tmp_path, monkeypatch):
    path = _database(tmp_path)
    _global_capability(monkeypatch)
    alice = _account(tmp_path, "alice")
    forged = {
        "scope_kind": "global",
        "account_digest": "",
        "matcher_kind": "domain",
        "matcher_value": "forged.example",
        "decision": "deny",
        "citation_ref": "forged-order",
        "issuer_id": "forged-issuer",
        "reason_code": "forged",
        "effective_at": NOW.isoformat(),
        "expires_at": None,
        "supersedes_event_id": None,
        "capability_fingerprint": "0" * 64,
    }
    encoded = json.dumps(forged, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    with connect_write(path, purpose="legal-policy-test") as con:
        con.execute(
            "INSERT INTO legal_policy_events "
            "(event_id, scope_kind, account_digest, matcher_kind, matcher_value, "
            "decision, citation_ref, issuer_id, reason_code, effective_at, expires_at, "
            "supersedes_event_id, capability_fingerprint, event_fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [f"lpe-{fingerprint[:32]}", *forged.values(), fingerprint],
        )
        with pytest.raises(LegalPolicyDenied, match="authority validation"):
            policy_snapshot(con, alice, at=NOW + timedelta(seconds=1))


def test_snapshot_validates_temporally_hidden_global_rows(tmp_path, monkeypatch):
    path = _database(tmp_path)
    operator = global_policy_authority(_global_capability(monkeypatch))
    alice = _account(tmp_path, "alice")
    with connect_write(path, purpose="legal-policy-test") as con:
        event_id = append_policy_event(
            con,
            operator,
            scope_kind="global",
            matcher_kind="domain",
            matcher_value="restricted.example",
            decision="deny",
            citation_ref="court-order-2",
            issuer_id="operator-policy-issuer",
            reason_code="global-restriction",
            effective_at=NOW,
        )
        con.execute(
            "UPDATE legal_policy_events SET effective_at = ? WHERE event_id = ?",
            [NOW + timedelta(days=1), event_id],
        )

        with pytest.raises(LegalPolicyDenied, match="integrity"):
            policy_snapshot(con, alice, at=NOW + timedelta(seconds=1))


def test_snapshot_rejects_rehashed_account_event_without_bound_authority(tmp_path):
    path = _database(tmp_path)
    alice = _account(tmp_path, "alice")
    forged = {
        "scope_kind": "account",
        "account_digest": alice.account_digest,
        "matcher_kind": "domain",
        "matcher_value": "forged.example",
        "decision": "allow",
        "citation_ref": "forged-license",
        "issuer_id": "forged-issuer",
        "reason_code": "forged",
        "effective_at": NOW.isoformat(),
        "expires_at": None,
        "supersedes_event_id": None,
        "capability_fingerprint": "0" * 64,
    }
    encoded = json.dumps(forged, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    with connect_write(path, purpose="legal-policy-test") as con:
        con.execute(
            "INSERT INTO legal_policy_events "
            "(event_id, scope_kind, account_digest, matcher_kind, matcher_value, "
            "decision, citation_ref, issuer_id, reason_code, effective_at, expires_at, "
            "supersedes_event_id, capability_fingerprint, event_fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [f"lpe-{fingerprint[:32]}", *forged.values(), fingerprint],
        )
        with pytest.raises(LegalPolicyDenied, match="account.*authority validation"):
            policy_snapshot(con, alice, at=NOW + timedelta(seconds=1))


def test_legal_policy_ledger_is_in_authoritative_schema_inventory():
    assert "legal_policy_events" in SCHEMA_TABLES
