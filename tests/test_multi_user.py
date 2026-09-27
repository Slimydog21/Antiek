"""Multi-user substrate tests (Sprint 22, master-spec §13.2)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.auth.magic_link import verify_session_cookie
from substrate.multi_user import (
    AuthError,
    GraphRouter,
    MockAuthProvider,
    PartitionInvariantViolation,
    PartitionKind,
    UserClaims,
    assign_to_partition,
    decode_token,
    extract_discovered_rule,
    move_to_partition,
    propagate_to_shared_substrate,
    resolve_personal_graph,
    resolve_shared_substrate,
    validate_partition,
)
from substrate.multi_user import auth as auth_subject
from substrate.multi_user.auth import (
    AuthSchemaMigrationError,
    ensure_auth_subjects_schema,
    mint_session_cookie,
    operator_claims,
    subject_owner_id,
)

# ── Auth tests ───────────────────────────────────────────────────────


def test_operator_claims_canonical():
    """The canonical operator claims match the substrate's
    owner_user_id='__operator__' default."""
    claims = operator_claims()
    assert claims.user_id == "__operator__"
    assert "operator" in claims.scopes
    assert "private_research" in claims.scopes


def test_mock_auth_provider_decodes_known_token():
    provider = MockAuthProvider(tokens={
        "tok-A": UserClaims(
            user_id="user-1", email="u1@x.com",
            scopes=frozenset({"basic"}), issued_at="2026-05-19T12:00:00Z",
        ),
    })
    claims = decode_token(provider, "tok-A")
    assert claims.user_id == "user-1"


def test_mock_auth_provider_rejects_unknown():
    provider = MockAuthProvider(tokens={})
    with pytest.raises(AuthError):
        decode_token(provider, "unknown-token")


def test_decode_token_strips_bearer_prefix():
    provider = MockAuthProvider(tokens={
        "tok-A": UserClaims(
            user_id="u", email=None, scopes=frozenset(),
            issued_at="2026-05-19T12:00:00Z",
        ),
    })
    claims = decode_token(provider, "Bearer tok-A")
    assert claims.user_id == "u"


def test_decode_token_rejects_empty():
    provider = MockAuthProvider(tokens={})
    with pytest.raises(AuthError):
        decode_token(provider, "")


def test_auth_subject_schema_is_idempotent_and_exact(tmp_path):
    db_path = str(tmp_path / "subjects.duckdb")
    con = connect_write(db_path, purpose="auth_subject_schema_test")
    try:
        ensure_auth_subjects_schema(con)
        ensure_auth_subjects_schema(con)
        assert con.execute("SELECT count(*) FROM auth_subjects").fetchone() == (0,)
    finally:
        con.close()

    raw = duckdb.connect(str(tmp_path / "drifted.duckdb"))
    raw.execute("CREATE TABLE auth_subjects(provider VARCHAR)")
    raw.close()
    drifted = connect_write(str(tmp_path / "drifted.duckdb"), purpose="auth_drift_test")
    try:
        with pytest.raises(AuthSchemaMigrationError, match="auth_schema_migration_required"):
            ensure_auth_subjects_schema(drifted)
    finally:
        drifted.close()


def test_concurrent_subject_mints_converge_to_one_owner(monkeypatch, tmp_path):
    db_path = str(tmp_path / "concurrent.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "subject-secret-" + "x" * 48)
    email = "Same.Subject@Example.Test"

    with ThreadPoolExecutor(max_workers=2) as pool:
        cookies = list(pool.map(lambda _: mint_session_cookie("magic_link", email, email), range(2)))

    owners = {verify_session_cookie(cookie).user_id for cookie in cookies}
    assert owners == {subject_owner_id("magic_link", email)}
    with duckdb.connect(db_path, read_only=True) as con:
        assert con.execute(
            "SELECT provider,subject,owner_user_id,count(*) FROM auth_subjects "
            "GROUP BY ALL"
        ).fetchall() == [
            ("magic_link", email.lower(), subject_owner_id("magic_link", email), 1)
        ]


def test_failed_cookie_mint_does_not_leave_partial_subject(monkeypatch, tmp_path):
    db_path = str(tmp_path / "mint-failure.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "subject-secret-" + "y" * 48)

    def fail_mint(**_kwargs):
        raise RuntimeError("simulated cookie mint crash")

    with monkeypatch.context() as patch:
        patch.setattr(auth_subject, "_mint_signed_session_cookie", fail_mint)
        with pytest.raises(RuntimeError, match="simulated cookie mint crash"):
            mint_session_cookie("magic_link", "owner@example.test", "owner@example.test")

    cookie = mint_session_cookie("magic_link", "owner@example.test", "owner@example.test")
    assert verify_session_cookie(cookie).user_id == subject_owner_id(
        "magic_link", "owner@example.test"
    )
    with duckdb.connect(db_path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM auth_subjects").fetchone() == (1,)


# ── Graph routing tests ──────────────────────────────────────────────


def test_graph_router_personal_path_sanitized():
    """User-id path traversal must be impossible."""
    router = GraphRouter(personal_graphs_dir="/tmp/test")
    path = router.personal_graph_path("user-123_safe")
    assert path == "/tmp/test/user-123_safe.duckdb"

    # Path-traversal attempt
    path = router.personal_graph_path("../etc/passwd")
    assert "../" not in path
    assert path.endswith(".duckdb")


def test_graph_router_rejects_empty_user_id():
    router = GraphRouter()
    with pytest.raises(ValueError):
        router.personal_graph_path("")


def test_resolve_personal_graph_returns_handle():
    router = GraphRouter(personal_graphs_dir="/tmp/test")
    handle = resolve_personal_graph(router, user_id="alice", encryption_key_ref="key-alice")
    assert handle.user_id == "alice"
    assert handle.db_path.endswith("alice.duckdb")
    assert handle.encryption_key_ref == "key-alice"


def test_resolve_shared_substrate_returns_handle():
    router = GraphRouter(shared_substrate_path="/tmp/shared.duckdb")
    handle = resolve_shared_substrate(router)
    assert handle.db_path == "/tmp/shared.duckdb"


# ── Partition tests ──────────────────────────────────────────────────


def test_default_assignment_to_private():
    assignment = assign_to_partition(
        item_id="note-1",
        item_kind="note",
        user_id="user-A",
        partition=PartitionKind.PRIVATE,
    )
    assert assignment.partition == PartitionKind.PRIVATE
    assert assignment.user_id == "user-A"
    assert assignment.assigned_by_action == "user_explicit"


def test_move_to_partition_records_provenance():
    a1 = assign_to_partition(
        item_id="note-1", item_kind="note", user_id="user-A",
        partition=PartitionKind.PRIVATE,
    )
    a2 = move_to_partition(
        assignment=a1, new_partition=PartitionKind.PUBLIC,
        triggered_by_action="operator_promote_to_public",
    )
    assert a2.partition == PartitionKind.PUBLIC
    assert a2.assigned_by_action == "operator_promote_to_public"
    # Item identity preserved.
    assert a2.item_id == a1.item_id
    assert a2.user_id == a1.user_id


def test_validate_partition_blocks_cross_user_private_read():
    """Per master-spec §13.2: private items physically inaccessible
    to other users."""
    with pytest.raises(PartitionInvariantViolation):
        validate_partition(
            item_owner_user_id="user-A",
            accessing_user_id="user-B",
            partition=PartitionKind.PRIVATE,
        )


def test_validate_partition_allows_owner_private_access():
    """Same-user access to own private items: allowed."""
    validate_partition(
        item_owner_user_id="user-A",
        accessing_user_id="user-A",
        partition=PartitionKind.PRIVATE,
    )


def test_validate_partition_allows_cross_user_public_read():
    """Public items: any user can read."""
    validate_partition(
        item_owner_user_id="user-A",
        accessing_user_id="user-B",
        partition=PartitionKind.PUBLIC,
    )


# ── Skill propagation tests ──────────────────────────────────────────


def test_extract_discovered_rule_is_content_addressed():
    """Same input produces same rule_id (idempotency)."""
    r1 = extract_discovered_rule(
        observation_text="Lukin papers are Tier 1 in neutral atom physics",
        rule_kind="source_tier_rule",
        domain="quantum",
        epsilon_budget_consumed=0.5,
    )
    r2 = extract_discovered_rule(
        observation_text="Lukin papers are Tier 1 in neutral atom physics",
        rule_kind="source_tier_rule",
        domain="quantum",
        epsilon_budget_consumed=2.0,  # different ε
    )
    assert r1.rule_id == r2.rule_id  # content-addressed; ε is metadata only


def test_extract_discovered_rule_carries_only_rule_not_private_content():
    """Per master-spec §13.2: 'the operator's specific quantum
    chunks stay walled; the discovered fact about source tiers
    propagates'. The digest's rule_text MUST NOT carry any chunk_id
    or document_id referencing the private source."""
    r = extract_discovered_rule(
        observation_text="Tier-1 sources in neutral atom physics: Lukin lab",
        rule_kind="source_tier_rule",
        domain="quantum",
        epsilon_budget_consumed=1.0,
    )
    # The structure carries the rule + metadata only — no private
    # content fields.
    assert hasattr(r, "rule_text")
    assert hasattr(r, "epsilon_budget_consumed")
    assert not hasattr(r, "source_chunk_id")
    assert not hasattr(r, "private_document_id")


def test_propagate_to_shared_substrate_is_idempotent(tmp_path):
    """Re-propagating the same digest is a no-op (ON CONFLICT DO NOTHING)."""
    db_path = str(tmp_path / "shared.duckdb")
    con = connect_write(db_path, purpose="multi_user_test")
    try:
        digest = extract_discovered_rule(
            observation_text="Test rule",
            rule_kind="source_tier_rule",
            domain="quantum",
            epsilon_budget_consumed=1.0,
        )
        rule_id_1 = propagate_to_shared_substrate(con, digest)
        rule_id_2 = propagate_to_shared_substrate(con, digest)
        assert rule_id_1 == rule_id_2

        # Verify single row.
        row = con.execute(
            "SELECT COUNT(*) FROM skill_rules WHERE rule_id = ?",
            [rule_id_1],
        ).fetchone()
        assert row[0] == 1
    finally:
        con.close()
