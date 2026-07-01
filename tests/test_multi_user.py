"""Multi-user substrate tests (Sprint 22, master-spec §13.2)."""

from __future__ import annotations

import pytest

from runtime.db_lock import connect_write
from substrate.ducklake import DuckLakeCatalog, HashPrefixSharding, InMemoryCatalogBackend
from substrate.ducklake.catalog import SqliteCatalogBackend
from substrate.multi_user import (
    CATALOG_DB_ENV,
    GRAPH_USER_ID_ENV,
    SHARD_HEX_CHARS_ENV,
    AuthError,
    AuthVendor,
    GraphRouter,
    MockAuthProvider,
    PartitionInvariantViolation,
    PartitionKind,
    UserClaims,
    assign_to_partition,
    build_graph_router_from_env,
    configured_ducklake_catalog,
    decode_token,
    default_personal_graph_handle,
    extract_discovered_rule,
    move_to_partition,
    normalize_verified_claims,
    propagate_to_shared_substrate,
    resolve_personal_graph,
    resolve_shared_substrate,
    validate_partition,
)
from substrate.multi_user.auth import operator_claims

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


def test_normalize_clerk_verified_claims_namespaces_identity_and_scopes():
    claims = normalize_verified_claims(
        vendor=AuthVendor.CLERK,
        claims={
            "sub": "user_2abc",
            "email": "USER@example.COM",
            "iat": 1_765_000_000,
            "public_metadata": {
                "antiek_scopes": ["private_research", "shared_substrate_write"],
            },
        },
    )

    assert claims.user_id == "clerk:user_2abc"
    assert claims.email == "user@example.com"
    assert claims.issued_at == "2025-12-06T05:46:40Z"
    assert claims.scopes == frozenset({
        "authenticated",
        "private_research",
        "shared_substrate_write",
    })


def test_normalize_supabase_verified_claims_reads_scope_and_app_metadata():
    claims = normalize_verified_claims(
        vendor="supabase",
        claims={
            "sub": "9e7d03ec-0f16-4e52-b615-6f94807d5133",
            "email": "reader@example.com",
            "scope": "private_research graph:read",
            "app_metadata": {"antiek_scopes": "shared_substrate_write"},
        },
    )

    assert claims.user_id == "supabase:9e7d03ec-0f16-4e52-b615-6f94807d5133"
    assert claims.email == "reader@example.com"
    assert claims.scopes == frozenset({
        "authenticated",
        "graph:read",
        "private_research",
        "shared_substrate_write",
    })


def test_normalize_verified_claims_rejects_missing_subject():
    with pytest.raises(AuthError, match="missing non-empty 'sub'"):
        normalize_verified_claims(vendor="clerk", claims={"email": "u@example.com"})


def test_normalize_verified_claims_rejects_unsupported_vendor():
    with pytest.raises(AuthError, match="unsupported auth vendor"):
        normalize_verified_claims(
            vendor="homegrown",
            claims={"sub": "u1", "email": "u@example.com"},
        )


def test_normalize_verified_claims_does_not_grant_operator_implicitly():
    claims = normalize_verified_claims(
        vendor="supabase",
        claims={"sub": "u1", "role": "service_role"},
    )

    assert claims.user_id == "supabase:u1"
    assert claims.scopes == frozenset({"authenticated"})


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


def test_graph_router_consults_ducklake_catalog_first():
    catalog = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    catalog.register(
        user_id="alice",
        db_path="/catalog/shard-7/alice.duckdb",
        encryption_key_ref="catalog-key-alice",
        shard_id="7",
    )
    router = GraphRouter(personal_graphs_dir="/tmp/test", catalog=catalog)

    assert router.personal_graph_path("alice") == "/catalog/shard-7/alice.duckdb"
    handle = resolve_personal_graph(router, user_id="alice")
    assert handle.db_path == "/catalog/shard-7/alice.duckdb"
    assert handle.encryption_key_ref == "catalog-key-alice"


def test_graph_router_falls_back_when_catalog_has_no_entry():
    catalog = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    router = GraphRouter(personal_graphs_dir="/tmp/test", catalog=catalog)

    assert router.personal_graph_path("missing-user") == "/tmp/test/missing-user.duckdb"


def test_graph_router_uses_sharding_strategy_for_uncatalogued_users():
    catalog = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    router = GraphRouter(
        personal_graphs_dir="/tmp/test",
        catalog=catalog,
        sharding_strategy=HashPrefixSharding(hex_chars=2),
    )

    path = router.personal_graph_path("alice")
    assert path.startswith("/tmp/test/")
    assert path.endswith("/alice.duckdb")
    assert len(path.removeprefix("/tmp/test/").split("/", 1)[0]) == 2


def test_env_graph_router_uses_sqlite_catalog(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.sqlite"
    catalog = DuckLakeCatalog(backend=SqliteCatalogBackend(db_path=str(catalog_path)))
    catalog.register(
        user_id="alice",
        db_path=str(tmp_path / "catalog" / "alice.duckdb"),
        encryption_key_ref="key-alice",
        shard_id="7",
    )

    monkeypatch.setenv(CATALOG_DB_ENV, str(catalog_path))
    monkeypatch.setenv(GRAPH_USER_ID_ENV, "alice")
    monkeypatch.setenv("ANTIEK_PERSONAL_GRAPHS_DIR", str(tmp_path / "fallback"))

    router = build_graph_router_from_env()
    handle = default_personal_graph_handle()

    assert router.personal_graph_path("alice") == str(
        tmp_path / "catalog" / "alice.duckdb"
    )
    assert handle.user_id == "alice"
    assert handle.db_path == str(tmp_path / "catalog" / "alice.duckdb")
    assert handle.encryption_key_ref == "key-alice"


def test_configured_ducklake_catalog_is_cached(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.sqlite"
    monkeypatch.setenv(CATALOG_DB_ENV, str(catalog_path))

    assert configured_ducklake_catalog() is configured_ducklake_catalog()


def test_env_graph_router_falls_back_to_sharded_path(tmp_path, monkeypatch):
    monkeypatch.delenv(CATALOG_DB_ENV, raising=False)
    monkeypatch.setenv("ANTIEK_PERSONAL_GRAPHS_DIR", str(tmp_path))
    monkeypatch.setenv(SHARD_HEX_CHARS_ENV, "2")

    router = build_graph_router_from_env()
    path = router.personal_graph_path("alice")

    assert path.startswith(str(tmp_path))
    assert path.endswith("/alice.duckdb")
    assert len(path.removeprefix(str(tmp_path) + "/").split("/", 1)[0]) == 2


def test_default_db_path_routes_through_catalog_when_configured(tmp_path, monkeypatch):
    from substrate.graph import default_db_path

    catalog_path = tmp_path / "catalog.sqlite"
    routed_path = tmp_path / "stage2" / "operator.duckdb"
    catalog = DuckLakeCatalog(backend=SqliteCatalogBackend(db_path=str(catalog_path)))
    catalog.register(
        user_id="__operator__",
        db_path=str(routed_path),
        encryption_key_ref="key-operator",
    )

    monkeypatch.delenv("ANTIEK_DUCKDB_PATH", raising=False)
    monkeypatch.setenv(CATALOG_DB_ENV, str(catalog_path))

    assert default_db_path() == str(routed_path)


def test_default_db_path_ignores_partial_router_env_without_catalog(tmp_path, monkeypatch):
    import os

    from substrate.constants import DUCKDB_PATH
    from substrate.graph import default_db_path

    monkeypatch.delenv("ANTIEK_DUCKDB_PATH", raising=False)
    monkeypatch.delenv(CATALOG_DB_ENV, raising=False)
    monkeypatch.setenv(GRAPH_USER_ID_ENV, "alice")
    monkeypatch.setenv("ANTIEK_PERSONAL_GRAPHS_DIR", str(tmp_path / "graphs"))
    monkeypatch.setenv(SHARD_HEX_CHARS_ENV, "2")

    assert default_db_path() == os.path.expanduser(DUCKDB_PATH)


def test_default_db_path_keeps_explicit_duckdb_override(tmp_path, monkeypatch):
    from substrate.graph import default_db_path

    explicit_path = tmp_path / "explicit.duckdb"
    catalog_path = tmp_path / "catalog.sqlite"
    catalog = DuckLakeCatalog(backend=SqliteCatalogBackend(db_path=str(catalog_path)))
    catalog.register(
        user_id="__operator__",
        db_path=str(tmp_path / "catalog.duckdb"),
        encryption_key_ref="key-operator",
    )

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(explicit_path))
    monkeypatch.setenv(CATALOG_DB_ENV, str(catalog_path))

    assert default_db_path() == str(explicit_path)


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
