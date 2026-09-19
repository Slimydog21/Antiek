from __future__ import annotations

import hashlib
import shutil

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.graph.tenancy import (
    GraphAuthorityConflict,
    GraphTenancyState,
    add_node_membership,
    assert_graph_authority,
    graph_key,
    graph_tenancy_state,
    has_node_membership,
    initialize_graph_authority,
    transition_graph_tenancy_state,
)
from substrate.investigation_tenancy import InvestigationAuthority


def _database(path):
    con = connect_write(str(path), purpose="test-graph-tenancy")
    init_database(con)
    return con


def test_schema_is_additive_and_manifest_starts_unbound(tmp_path):
    with _database(tmp_path / "graph.duckdb") as con:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        assert {
            "graph_tenancy_manifest",
            "graph_investigation_allocations",
            "investigation_node_memberships",
        } <= tables
        assert con.execute("SELECT * FROM graph_tenancy_manifest").fetchall() == []
        for table in (
            "edges",
            "syntheses",
            "notebooks",
            "discovery_cache",
            "outline_block_commands",
            "monitors",
            "supersession_candidates",
        ):
            columns = {
                row[0]
                for row in con.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = ?",
                    [table],
                ).fetchall()
            }
            assert {"account_digest", "investigation_digest"} <= columns


def test_same_display_id_allocates_distinct_graph_authorities(tmp_path):
    tenancy_root = tmp_path / "events"
    tenancy_root.mkdir()
    alice = InvestigationAuthority("alice", "shared", root=tenancy_root)
    bob = InvestigationAuthority("bob", "shared", root=tenancy_root)
    with _database(tmp_path / "graph.duckdb") as con:
        assert initialize_graph_authority(con, alice) == graph_key(alice)
        assert initialize_graph_authority(con, bob) == graph_key(bob)
        assert graph_key(alice) != graph_key(bob)
        assert assert_graph_authority(con, alice) == graph_key(alice)
        assert assert_graph_authority(con, bob) == graph_key(bob)
        assert graph_tenancy_state(con) is GraphTenancyState.UNSCOPED


def test_private_node_identity_can_deduplicate_without_visibility_leak(tmp_path):
    tenancy_root = tmp_path / "events"
    tenancy_root.mkdir()
    alice = InvestigationAuthority("alice", "shared", root=tenancy_root)
    bob = InvestigationAuthority("bob", "shared", root=tenancy_root)
    node_id = "insight-shared-content-hash"
    with _database(tmp_path / "graph.duckdb") as con:
        initialize_graph_authority(con, alice)
        initialize_graph_authority(con, bob)
        add_node_membership(
            con,
            alice,
            node_id=node_id,
            role="insight",
            source_row_digest=hashlib.sha256(b"alice-source").hexdigest(),
        )
        assert has_node_membership(con, alice, node_id=node_id)
        assert not has_node_membership(con, bob, node_id=node_id)
        add_node_membership(
            con,
            bob,
            node_id=node_id,
            role="insight",
            source_row_digest=hashlib.sha256(b"bob-source").hexdigest(),
        )
        assert has_node_membership(con, bob, node_id=node_id)


def test_membership_replay_requires_exact_source_digest(tmp_path):
    tenancy_root = tmp_path / "events"
    tenancy_root.mkdir()
    authority = InvestigationAuthority("alice", "private", root=tenancy_root)
    first = hashlib.sha256(b"first").hexdigest()
    with _database(tmp_path / "graph.duckdb") as con:
        initialize_graph_authority(con, authority)
        add_node_membership(
            con, authority, node_id="node-1", role="note", source_row_digest=first
        )
        add_node_membership(
            con, authority, node_id="node-1", role="note", source_row_digest=first
        )
        with pytest.raises(GraphAuthorityConflict, match="conflicts"):
            add_node_membership(
                con,
                authority,
                node_id="node-1",
                role="note",
                source_row_digest=hashlib.sha256(b"second").hexdigest(),
            )


def test_state_transition_is_compare_and_swap(tmp_path):
    tenancy_root = tmp_path / "events"
    tenancy_root.mkdir()
    authority = InvestigationAuthority("alice", "private", root=tenancy_root)
    with _database(tmp_path / "graph.duckdb") as con:
        initialize_graph_authority(con, authority)
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.UNSCOPED,
            desired=GraphTenancyState.COPYING,
        )
        assert graph_tenancy_state(con) is GraphTenancyState.COPYING
        with pytest.raises(GraphAuthorityConflict, match="state changed"):
            transition_graph_tenancy_state(
                con,
                expected=GraphTenancyState.UNSCOPED,
                desired=GraphTenancyState.COPYING,
            )


def test_quarantined_graph_rejects_authority_allocation_and_membership(tmp_path):
    tenancy_root = tmp_path / "events"
    tenancy_root.mkdir()
    authority = InvestigationAuthority("alice", "private", root=tenancy_root)
    with _database(tmp_path / "graph.duckdb") as con:
        initialize_graph_authority(con, authority)
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.UNSCOPED,
            desired=GraphTenancyState.COPYING,
        )
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.COPYING,
            desired=GraphTenancyState.QUARANTINED,
        )
        with pytest.raises(GraphAuthorityConflict, match="quarantined"):
            initialize_graph_authority(con, authority)
        with pytest.raises(GraphAuthorityConflict, match="quarantined"):
            add_node_membership(
                con,
                authority,
                node_id="node-1",
                role="note",
                source_row_digest=hashlib.sha256(b"source").hexdigest(),
            )


def test_fresh_root_restore_preserves_key_binding_and_allocations(tmp_path):
    source_root = tmp_path / "events-source"
    source_root.mkdir()
    authority = InvestigationAuthority("alice", "private", root=source_root)
    source_db = tmp_path / "source.duckdb"
    with _database(source_db) as con:
        initialize_graph_authority(con, authority)

    restored_root = tmp_path / "events-restored"
    shutil.copytree(source_root, restored_root)
    restored_db = tmp_path / "restored.duckdb"
    shutil.copy2(source_db, restored_db)
    restored = InvestigationAuthority("alice", "private", root=restored_root)
    with connect_write(str(restored_db), purpose="test-restored-graph") as con:
        assert assert_graph_authority(con, restored) == graph_key(restored)

    foreign_root = tmp_path / "events-foreign"
    foreign_root.mkdir()
    foreign = InvestigationAuthority("alice", "private", root=foreign_root)
    with connect_write(str(restored_db), purpose="test-foreign-graph") as con:
        with pytest.raises(GraphAuthorityConflict, match="manifest"):
            assert_graph_authority(con, foreign)
