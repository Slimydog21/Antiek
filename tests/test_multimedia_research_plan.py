from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import os
import socket
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

import substrate.multimedia.research_plan as research_plan_module
from substrate.multimedia.research_intent import ResearchIntentLedger
from substrate.multimedia.research_plan import (
    InvestigationActivationAuthorization,
    InvestigationActivationQuote,
    ResearchPlanError,
    ResearchPlanLedger,
    ResearchPlanStorageError,
    ResearchPlanValidationError,
)
from tests.test_multimedia_research_intent import _create


def _intent(tmp_path, owner: str = "a" * 64):
    intent, _ = _create(ResearchIntentLedger(tmp_path), owner=owner)
    return intent


def test_plan_is_owner_scoped_private_opaque_and_exactly_idempotent(tmp_path) -> None:
    intent = _intent(tmp_path)
    ledger = ResearchPlanLedger(tmp_path)
    plan, created = ledger.handoff(
        owner_identity_digest="a" * 64,
        idempotency_key="handoff-123456789",
        intent=intent,
    )
    replay, replay_created = ledger.handoff(
        owner_identity_digest="a" * 64,
        idempotency_key="handoff-123456789",
        intent=intent,
    )
    assert created is True and replay_created is False and replay == plan
    assert plan.plan_id.startswith("mrp_") and len(plan.plan_id) == 52
    assert oct(os.stat(ledger.path).st_mode & 0o777) == "0o600"
    assert plan.tree["root"]["question"] == intent.question
    assert plan.tree["root"]["children"] == []
    assert plan.source_intent_digest == intent.plan_seed["intent_digest"]
    assert plan.source_evidence_digest == intent.evidence_digest
    with pytest.raises(ResearchPlanError, match="unavailable"):
        ledger.get(owner_identity_digest="b" * 64, plan_id=plan.plan_id)


def test_two_owners_get_distinct_plans_and_keys_cannot_drift(tmp_path) -> None:
    first_intent = _intent(tmp_path)
    second_intent = _intent(tmp_path, "b" * 64)
    ledger = ResearchPlanLedger(tmp_path)
    first, _ = ledger.handoff(
        owner_identity_digest="a" * 64, idempotency_key="handoff-123456789", intent=first_intent
    )
    second, _ = ledger.handoff(
        owner_identity_digest="b" * 64, idempotency_key="handoff-123456789", intent=second_intent
    )
    assert first.plan_id != second.plan_id
    with pytest.raises(ResearchPlanError, match="idempotency conflict"):
        ledger.handoff(
            owner_identity_digest="a" * 64,
            idempotency_key="different-key-1234",
            intent=first_intent,
        )


def test_concurrent_handoff_creates_one_plan(tmp_path) -> None:
    intent = _intent(tmp_path)
    ledger = ResearchPlanLedger(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: ledger.handoff(
            owner_identity_digest="a" * 64,
            idempotency_key="handoff-123456789",
            intent=intent,
        ), range(8)))
    assert len({plan.plan_id for plan, _ in results}) == 1
    assert sum(created for _, created in results) == 1


def test_approval_is_owner_derived_version_pinned_and_replay_stable(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    plan, _ = ledger.handoff(
        owner_identity_digest="a" * 64,
        idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    approved = ledger.approve(
        owner_identity_digest="a" * 64, plan_id=plan.plan_id, expected_plan_version=1
    )
    replay = ledger.approve(
        owner_identity_digest="a" * 64, plan_id=plan.plan_id, expected_plan_version=1
    )
    assert approved == replay
    assert approved.state == "approved"
    assert approved.approved_by_owner_digest == "a" * 64
    assert approved.research_launched is False
    with pytest.raises(ResearchPlanError, match="version conflict"):
        ledger.approve(
            owner_identity_digest="a" * 64, plan_id=plan.plan_id, expected_plan_version=2
        )
    with pytest.raises(ResearchPlanError, match="unavailable"):
        ledger.approve(
            owner_identity_digest="b" * 64, plan_id=plan.plan_id, expected_plan_version=1
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_intent_digest", "tampered"),
        ("source_evidence_digest", "tampered"),
        ("state", "tampered"),
        ("plan_id", "mrp_" + "f" * 48),
        ("created_at", "2020-01-01T00:00:00Z"),
        ("updated_at", "2020-01-01T00:00:00Z"),
        ("plan_id", None),
        ("tree", {"root": {"kind": "research_question", "question": "Substituted", "children": []}}),
    ],
)
def test_tampered_plan_fails_closed(tmp_path, field: str, value: object) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    plan, _ = ledger.handoff(
        owner_identity_digest="a" * 64,
        idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    with sqlite3.connect(ledger.path) as connection:
        raw = connection.execute(
            "SELECT plan_json FROM multimedia_research_plans WHERE plan_id=?", (plan.plan_id,)
        ).fetchone()[0]
        record = json.loads(raw)
        record["plan"][field] = value
        connection.execute(
            "UPDATE multimedia_research_plans SET plan_json=? WHERE plan_id=?",
            (json.dumps(record), plan.plan_id),
        )
    with pytest.raises(ResearchPlanError, match="stored research plan"):
        ledger.get(owner_identity_digest="a" * 64, plan_id=plan.plan_id)


def test_schema_and_unsafe_path_fail_closed(tmp_path) -> None:
    path = tmp_path / "research-plans.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE multimedia_research_plans (plan_id TEXT)")
    os.chmod(path, 0o600)
    with pytest.raises(ResearchPlanError, match="schema conflicts"):
        ResearchPlanLedger(tmp_path).handoff(
            owner_identity_digest="a" * 64,
            idempotency_key="handoff-123456789",
            intent=_intent(tmp_path),
        )


def test_matching_malformed_row_and_envelope_types_fail_closed(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    plan, _ = ledger.handoff(
        owner_identity_digest="a" * 64,
        idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    with sqlite3.connect(ledger.path) as connection:
        raw = connection.execute(
            "SELECT plan_json FROM multimedia_research_plans WHERE plan_id=?", (plan.plan_id,)
        ).fetchone()[0]
        record = json.loads(raw)
        record["plan"]["created_at"] = 1
        connection.execute(
            "UPDATE multimedia_research_plans SET created_at=?, plan_json=? WHERE plan_id=?",
            (1, json.dumps(record), plan.plan_id),
        )
    with pytest.raises(ResearchPlanError, match="stored research plan"):
        ledger.get(owner_identity_digest="a" * 64, plan_id=plan.plan_id)


def test_operational_file_open_failure_is_storage_unavailable(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    intent = _intent(tmp_path)
    with (
        patch("substrate.multimedia.research_plan.os.open", side_effect=OSError("I/O")),
        pytest.raises(ResearchPlanStorageError, match="ledger is unavailable"),
    ):
        ledger.handoff(
            owner_identity_digest="a" * 64,
            idempotency_key="handoff-123456789",
            intent=intent,
        )


def test_ordered_edit_batch_preserves_ids_reopens_approval_and_replays_history(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    root_id = plan.tree["root"]["node_id"]
    approved = ledger.approve(
        owner_identity_digest=owner, plan_id=plan.plan_id, expected_plan_version=1
    )
    edited = ledger.edit(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="mutation-12345678", expected_plan_version=1,
        operations=[{"type": "add_child", "parent_node_id": root_id,
                     "position": 0, "question": "  First child?  "}],
    )
    child_id = edited.tree["root"]["children"][0]["node_id"]
    assert edited.plan_version == 2 and edited.state == "draft"
    assert edited.approved_at is None and edited.approved_by_owner_digest is None
    assert edited.tree["root"]["node_id"] == root_id
    assert child_id.startswith("mrpn_") and edited.tree["root"]["children"][0]["question"] == "First child?"
    later = ledger.edit(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="mutation-23456789", expected_plan_version=2,
        operations=[{"type": "update_question", "node_id": child_id,
                     "question": "Updated child?"}],
    )
    replay = ledger.edit(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="mutation-12345678", expected_plan_version=1,
        operations=[{"type": "add_child", "parent_node_id": root_id,
                     "position": 0, "question": "First child?"}],
    )
    assert approved.state == "approved" and later.plan_version == 3
    assert replay == edited
    assert ledger.get(owner_identity_digest=owner, plan_id=plan.plan_id) == later


def test_edit_batch_failure_and_idempotency_drift_have_no_side_effects(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    root_id = plan.tree["root"]["node_id"]
    with pytest.raises(ResearchPlanValidationError):
        ledger.edit(
            owner_identity_digest=owner, plan_id=plan.plan_id,
            idempotency_key="mutation-12345678", expected_plan_version=1,
            operations=[
                {"type": "add_child", "parent_node_id": root_id,
                 "position": 0, "question": "Valid child?"},
                {"type": "remove_subtree", "node_id": root_id},
            ],
        )
    assert ledger.get(owner_identity_digest=owner, plan_id=plan.plan_id) == plan
    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute("SELECT count(*) FROM multimedia_research_plan_mutations").fetchone()[0] == 0
    committed = ledger.edit(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="mutation-12345678", expected_plan_version=1,
        operations=[{"type": "add_child", "parent_node_id": root_id,
                     "position": 0, "question": "Valid child?"}],
    )
    with pytest.raises(ResearchPlanError, match="idempotency conflict"):
        ledger.edit(
            owner_identity_digest=owner, plan_id=plan.plan_id,
            idempotency_key="mutation-12345678", expected_plan_version=2,
            operations=[{"type": "remove_subtree",
                         "node_id": committed.tree["root"]["children"][0]["node_id"]}],
        )
    assert ledger.get(owner_identity_digest=owner, plan_id=plan.plan_id) == committed


def test_concurrent_same_version_edits_commit_once(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    root_id = plan.tree["root"]["node_id"]

    def mutate(index: int):
        try:
            return ledger.edit(
                owner_identity_digest=owner, plan_id=plan.plan_id,
                idempotency_key=f"mutation-concurrent-{index}", expected_plan_version=1,
                operations=[{"type": "add_child", "parent_node_id": root_id,
                             "position": 0, "question": f"Concurrent child {index}?"}],
            )
        except ResearchPlanError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(mutate, range(2)))
    assert sum(not isinstance(value, Exception) for value in outcomes) == 1
    assert ledger.get(owner_identity_digest=owner, plan_id=plan.plan_id).plan_version == 2


def test_move_reorder_and_remove_subtree_are_ordered_and_keep_unaffected_ids(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    root_id = plan.tree["root"]["node_id"]
    seeded = ledger.edit(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="mutation-12345678", expected_plan_version=1,
        operations=[
            {"type": "add_child", "parent_node_id": root_id, "position": 0,
             "question": "First branch?"},
            {"type": "add_child", "parent_node_id": root_id, "position": 1,
             "question": "Second branch?"},
        ],
    )
    first, second = seeded.tree["root"]["children"]
    moved = ledger.edit(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="mutation-23456789", expected_plan_version=2,
        operations=[
            {"type": "move_subtree", "node_id": second["node_id"],
             "new_parent_node_id": first["node_id"], "position": 0},
            {"type": "remove_subtree", "node_id": first["node_id"]},
        ],
    )
    assert moved.tree["root"]["node_id"] == root_id
    assert moved.tree["root"]["children"] == []
    assert moved.plan_version == 3


def test_exact_v1_store_migrates_transactionally_with_stable_root_id(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    with sqlite3.connect(ledger.path) as connection:
        row = connection.execute(
            "SELECT plan_id,owner_identity_digest,source_intent_id,source_intent_digest,"
            "source_evidence_digest,idempotency_key,request_digest,plan_version,plan_json,"
            "created_at,updated_at FROM multimedia_research_plans"
        ).fetchone()
        envelope = json.loads(row[8])
        envelope["plan"]["tree"]["root"].pop("node_id")
        connection.execute("DROP TABLE multimedia_prepared_investigations")
        connection.execute("DROP TABLE multimedia_research_plan_mutations")
        connection.execute("DROP TABLE multimedia_research_plans")
        connection.execute(
            "CREATE TABLE multimedia_research_plans (plan_id TEXT PRIMARY KEY, "
            "owner_identity_digest TEXT NOT NULL, source_intent_id TEXT NOT NULL, "
            "source_intent_digest TEXT NOT NULL, source_evidence_digest TEXT NOT NULL, "
            "idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL, "
            "plan_version INTEGER NOT NULL, plan_json TEXT NOT NULL, created_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, UNIQUE(owner_identity_digest, idempotency_key), "
            "UNIQUE(owner_identity_digest, source_intent_id))"
        )
        connection.execute(
            "INSERT INTO multimedia_research_plans VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            row[:8] + (json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")),) + row[9:],
        )
        connection.execute("PRAGMA user_version=1")
    migrated = ledger.get(owner_identity_digest=owner, plan_id=plan.plan_id)
    replay = ledger.get(owner_identity_digest=owner, plan_id=plan.plan_id)
    assert migrated.tree["root"]["node_id"].startswith("mrpn_")
    assert replay.tree["root"]["node_id"] == migrated.tree["root"]["node_id"]
    assert migrated.plan_version == plan.plan_version
    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5


def test_tampered_receipt_tree_is_a_stored_integrity_error(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    body = [{"type": "add_child", "parent_node_id": plan.tree["root"]["node_id"],
             "position": 0, "question": "A child question?"}]
    ledger.edit(owner_identity_digest=owner, plan_id=plan.plan_id,
                idempotency_key="mutation-12345678", expected_plan_version=1,
                operations=body)
    with sqlite3.connect(ledger.path) as connection:
        raw = connection.execute(
            "SELECT response_json FROM multimedia_research_plan_mutations"
        ).fetchone()[0]
        response = json.loads(raw)
        response["tree"]["root"]["children"][0]["node_id"] = response["tree"]["root"]["node_id"]
        connection.execute(
            "UPDATE multimedia_research_plan_mutations SET response_json=?",
            (json.dumps(response, sort_keys=True, separators=(",", ":")),),
        )
    with pytest.raises(ResearchPlanError, match="stored research plan mutation integrity") as error:
        ledger.edit(owner_identity_digest=owner, plan_id=plan.plan_id,
                    idempotency_key="mutation-12345678", expected_plan_version=1,
                    operations=body)
    assert not isinstance(error.value, ResearchPlanValidationError)


def test_prepare_is_immutable_owner_scoped_and_replays_historical_snapshot(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    ledger.approve(owner_identity_digest=owner, plan_id=plan.plan_id, expected_plan_version=1)
    prepared, created = ledger.prepare_investigation(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="prepare-123456789", expected_plan_version=1,
    )
    edited = ledger.edit(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="mutation-12345678", expected_plan_version=1,
        operations=[{"type": "add_child", "parent_node_id": plan.tree["root"]["node_id"],
                     "position": 0, "question": "A later child?"}],
    )
    replay, replay_created = ledger.prepare_investigation(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="prepare-123456789", expected_plan_version=1,
    )
    assert created is True and replay_created is False and replay == prepared
    assert prepared.investigation_id.startswith("mpi_")
    assert prepared.tree == plan.tree and prepared.tree is not edited.tree
    assert prepared.total_node_count == prepared.leaf_question_count == 1
    assert prepared.state == "prepared" and prepared.execution_started is False
    with pytest.raises(ResearchPlanError, match="unavailable"):
        ledger.get_prepared_investigation(
            owner_identity_digest="b" * 64, investigation_id=prepared.investigation_id
        )


def test_prepare_rejects_draft_stale_drift_and_second_key(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    with pytest.raises(ResearchPlanError, match="not approved"):
        ledger.prepare_investigation(
            owner_identity_digest=owner, plan_id=plan.plan_id,
            idempotency_key="prepare-123456789", expected_plan_version=1,
        )
    ledger.approve(owner_identity_digest=owner, plan_id=plan.plan_id, expected_plan_version=1)
    with pytest.raises(ResearchPlanError, match="version conflict"):
        ledger.prepare_investigation(
            owner_identity_digest=owner, plan_id=plan.plan_id,
            idempotency_key="prepare-123456789", expected_plan_version=2,
        )
    ledger.prepare_investigation(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="prepare-123456789", expected_plan_version=1,
    )
    with pytest.raises(ResearchPlanError, match="idempotency conflict"):
        ledger.prepare_investigation(
            owner_identity_digest=owner, plan_id=plan.plan_id,
            idempotency_key="prepare-123456789", expected_plan_version=2,
        )
    with pytest.raises(ResearchPlanError, match="already prepared"):
        ledger.prepare_investigation(
            owner_identity_digest=owner, plan_id=plan.plan_id,
            idempotency_key="prepare-other-12345", expected_plan_version=1,
        )


def test_concurrent_prepare_creates_exactly_one_v3_row(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    ledger.approve(owner_identity_digest=owner, plan_id=plan.plan_id, expected_plan_version=1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ledger.prepare_investigation(
            owner_identity_digest=owner, plan_id=plan.plan_id,
            idempotency_key="prepare-123456789", expected_plan_version=1,
        ), range(4)))
    assert sum(created for _, created in results) == 1
    assert len({prepared.investigation_id for prepared, _ in results}) == 1
    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert connection.execute(
            "SELECT count(*) FROM multimedia_prepared_investigations"
        ).fetchone()[0] == 1


def test_exact_v2_store_migrates_atomically_to_v3(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    with sqlite3.connect(ledger.path) as connection:
        connection.execute("DROP TABLE multimedia_prepared_investigations")
        connection.execute("PRAGMA user_version=2")
    assert ledger.get(owner_identity_digest=owner, plan_id=plan.plan_id) == plan
    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        assert connection.execute(
            "SELECT count(*) FROM multimedia_prepared_investigations"
        ).fetchone()[0] == 0


def test_v2_migration_failure_rolls_back_without_partial_v3(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    with sqlite3.connect(ledger.path) as connection:
        connection.execute("DROP TABLE multimedia_prepared_investigations")
        connection.execute("PRAGMA user_version=2")
    with (
        patch("substrate.multimedia.research_plan._V3_PREPARED_SCHEMA", "CREATE TABLE broken ("),
        pytest.raises(ResearchPlanStorageError),
    ):
        ledger.get(owner_identity_digest=owner, plan_id=plan.plan_id)
    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' "
            "AND name='multimedia_prepared_investigations'"
        ).fetchone()[0] == 0


def test_prepared_tamper_and_forbidden_imports_fail_closed(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    ledger.approve(owner_identity_digest=owner, plan_id=plan.plan_id, expected_plan_version=1)
    prepared, _ = ledger.prepare_investigation(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="prepare-123456789", expected_plan_version=1,
    )
    with sqlite3.connect(ledger.path) as connection:
        raw = connection.execute(
            "SELECT prepared_json FROM multimedia_prepared_investigations"
        ).fetchone()[0]
        envelope = json.loads(raw)
        envelope["prepared_investigation"]["total_node_count"] = True
        changed = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        connection.execute(
            "UPDATE multimedia_prepared_investigations SET prepared_json=? WHERE investigation_id=?",
            (changed, prepared.investigation_id),
        )
    with pytest.raises(ResearchPlanError, match="stored prepared investigation"):
        ledger.get_prepared_investigation(
            owner_identity_digest=owner, investigation_id=prepared.investigation_id
        )

    tree = ast.parse((Path(__file__).parents[1] / "substrate/multimedia/research_plan.py").read_text())
    imports = {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    forbidden = ("event", "graph", "orchestration", "provider", "dispatch", "budget", "spend")
    assert not any(token in name for name in imports for token in forbidden)


def test_prepare_replay_read_and_failure_schedule_no_work_or_network(tmp_path) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    ledger.approve(owner_identity_digest=owner, plan_id=plan.plan_id, expected_plan_version=1)
    with (
        patch.object(asyncio, "create_task") as create_task,
        patch.object(socket, "create_connection") as create_connection,
    ):
        prepared, _ = ledger.prepare_investigation(
            owner_identity_digest=owner, plan_id=plan.plan_id,
            idempotency_key="prepare-123456789", expected_plan_version=1,
        )
        ledger.prepare_investigation(
            owner_identity_digest=owner, plan_id=plan.plan_id,
            idempotency_key="prepare-123456789", expected_plan_version=1,
        )
        ledger.get_prepared_investigation(
            owner_identity_digest=owner, investigation_id=prepared.investigation_id
        )
        with pytest.raises(ResearchPlanError):
            ledger.prepare_investigation(
                owner_identity_digest=owner, plan_id=plan.plan_id,
                idempotency_key="prepare-other-12345", expected_plan_version=1,
            )
    create_task.assert_not_called()
    create_connection.assert_not_called()


@pytest.mark.parametrize("column,value", [
    ("owner_identity_digest", "b" * 64),
    ("source_plan_version", 2),
    ("source_plan_integrity_digest", "b" * 64),
    ("source_intent_digest", "b" * 64),
    ("source_evidence_digest", "b" * 64),
    ("idempotency_key", "short"),
    ("request_digest", "b" * 64),
    ("prepared_integrity_digest", "b" * 64),
    ("created_at", "2020-01-01T00:00:00Z"),
])
def test_prepared_relational_binding_tamper_fails_closed(tmp_path, column, value) -> None:
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789",
        intent=_intent(tmp_path),
    )
    ledger.approve(owner_identity_digest=owner, plan_id=plan.plan_id, expected_plan_version=1)
    prepared, _ = ledger.prepare_investigation(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="prepare-123456789", expected_plan_version=1,
    )
    with sqlite3.connect(ledger.path) as connection:
        connection.execute(
            f"UPDATE multimedia_prepared_investigations SET {column}=? WHERE investigation_id=?",
            (value, prepared.investigation_id),
        )
    with pytest.raises(ResearchPlanError, match="prepared investigation"):
        ledger.get_prepared_investigation(
            owner_identity_digest=owner, investigation_id=prepared.investigation_id
        )


def _activation_fixture(tmp_path):
    ledger = ResearchPlanLedger(tmp_path)
    owner = "a" * 64
    plan, _ = ledger.handoff(
        owner_identity_digest=owner, idempotency_key="handoff-123456789", intent=_intent(tmp_path),
    )
    ledger.approve(owner_identity_digest=owner, plan_id=plan.plan_id, expected_plan_version=1)
    prepared, _ = ledger.prepare_investigation(
        owner_identity_digest=owner, plan_id=plan.plan_id,
        idempotency_key="prepare-123456789", expected_plan_version=1,
    )
    prepared_raw = json.dumps(
        asdict(prepared), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    prepared_digest = hashlib.sha256(prepared_raw).hexdigest()
    workload = {
        "investigation_id": prepared.investigation_id,
        "prepared_integrity_digest": prepared_digest,
        "total_node_count": prepared.total_node_count,
        "leaf_question_count": prepared.leaf_question_count,
    }
    workload_digest = hashlib.sha256(json.dumps(
        workload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    now = datetime.now(UTC)
    quote = InvestigationActivationQuote(
        schema_version=1, route_policy="balanced", resolved_tier="standard",
        provider="server-provider", model="server-model", dispatch_config_digest="d" * 64,
        pricing_source="server-pricebook", pricing_digest="e" * 64,
        workload_digest=workload_digest, quoted_ceiling_cents=250, quote_id="quote-123",
        issued_at=now.isoformat().replace("+00:00", "Z"),
        expires_at=(now + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
    )
    return ledger, owner, prepared, quote


def test_activation_authorization_is_exact_private_and_non_executing(tmp_path) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    kwargs = dict(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-12345678", route_policy="balanced",
        approved_ceiling_cents=300, ttl_seconds=3600, quote_resolver=lambda *_: quote,
    )
    created, was_created = ledger.authorize_investigation_activation(**kwargs)
    replay, replay_created = ledger.authorize_investigation_activation(**kwargs)
    read = ledger.get_investigation_activation_authorization(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id
    )
    assert was_created is True and replay_created is False
    assert created == replay == read and created.authorization_id.startswith("mia_")
    assert created.execution_started is created.background_work_authorized is False
    assert created.event_authority_digest is created.graph_authority_digest is None
    assert created.provider_authority_digest is created.spend_reservation_digest is None
    assert created.consumed_at is None and created.is_expired is False
    with pytest.raises(ResearchPlanError, match="unavailable"):
        ledger.get_investigation_activation_authorization(
            owner_identity_digest="b" * 64, investigation_id=prepared.investigation_id
        )
    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert not any(token in name for name in tables for token in ("event", "graph", "budget", "task"))


def test_activation_exact_replay_does_not_resolve_quote(tmp_path) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    kwargs = dict(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-12345678", route_policy="balanced",
        approved_ceiling_cents=300, ttl_seconds=3600,
    )
    created, _ = ledger.authorize_investigation_activation(
        **kwargs, quote_resolver=lambda *_: quote,
    )

    def unavailable(*_args):
        raise AssertionError("quote resolver must not run for exact replay")

    replay, was_created = ledger.authorize_investigation_activation(
        **kwargs, quote_resolver=unavailable,
    )
    assert replay == created
    assert was_created is False


def test_activation_max_ttl_is_persisted_and_expiry_is_capped_by_quote(tmp_path) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    kwargs = dict(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-86400-ttl", route_policy="balanced",
        approved_ceiling_cents=300, ttl_seconds=86400,
    )
    created, was_created = ledger.authorize_investigation_activation(
        **kwargs, quote_resolver=lambda *_: quote,
    )
    replay, replay_created = ledger.authorize_investigation_activation(
        **kwargs, quote_resolver=lambda *_: pytest.fail("replay resolved a quote"),
    )
    read = ledger.get_investigation_activation_authorization(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
    )

    assert was_created is True and replay_created is False
    assert created == replay == read
    assert created.ttl_seconds == 86400
    assert created.expires_at == created.quote_expires_at
    with sqlite3.connect(ledger.path) as connection:
        ttl, raw = connection.execute(
            "SELECT ttl_seconds, authorization_json FROM "
            "multimedia_investigation_activation_authorizations WHERE authorization_id=?",
            (created.authorization_id,),
        ).fetchone()
    assert ttl == 86400
    assert json.loads(raw)["ttl_seconds"] == 86400


@pytest.mark.parametrize("tamper", [59, 86399, 86401])
def test_activation_persisted_ttl_tamper_fails_closed(tmp_path, tamper) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    authorization, _ = ledger.authorize_investigation_activation(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-86400-ttl", route_policy="balanced",
        approved_ceiling_cents=300, ttl_seconds=86400, quote_resolver=lambda *_: quote,
    )
    with sqlite3.connect(ledger.path) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE multimedia_investigation_activation_authorizations SET ttl_seconds=? "
            "WHERE authorization_id=?", (tamper, authorization.authorization_id),
        )
    with pytest.raises(ResearchPlanError, match="integrity"):
        ledger.get_investigation_activation_authorization(
            owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        )


def test_activation_quote_resolver_runs_without_write_lock(tmp_path) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)

    def resolver(*_args):
        with sqlite3.connect(ledger.path, timeout=0) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.commit()
        return quote

    authorization, created = ledger.authorize_investigation_activation(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-12345678", route_policy="balanced",
        approved_ceiling_cents=300, ttl_seconds=3600, quote_resolver=resolver,
    )
    assert created is True
    assert authorization.investigation_id == prepared.investigation_id


def test_concurrent_exact_activation_safely_replays_after_both_resolve(tmp_path) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    barrier = threading.Barrier(2)

    def resolver(*_args):
        barrier.wait(timeout=5)
        return quote

    def authorize():
        return ledger.authorize_investigation_activation(
            owner_identity_digest=owner, investigation_id=prepared.investigation_id,
            idempotency_key="activate-12345678", route_policy="balanced",
            approved_ceiling_cents=300, ttl_seconds=3600, quote_resolver=resolver,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: authorize(), range(2)))
    assert sum(created for _, created in results) == 1
    assert results[0][0] == results[1][0]


def test_activation_rejects_non_quote_resolver_result(tmp_path) -> None:
    ledger, owner, prepared, _quote = _activation_fixture(tmp_path)
    with pytest.raises(ResearchPlanError, match="quote is malformed"):
        ledger.authorize_investigation_activation(
            owner_identity_digest=owner, investigation_id=prepared.investigation_id,
            idempotency_key="activate-12345678", route_policy="balanced",
            approved_ceiling_cents=300, ttl_seconds=3600,
            quote_resolver=lambda *_: {"quoted_ceiling_cents": 250},
        )


def test_activation_authorization_fails_closed_on_terms_quote_and_drift(tmp_path) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    base = dict(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-12345678", route_policy="balanced",
        approved_ceiling_cents=300, ttl_seconds=3600, quote_resolver=lambda *_: quote,
    )
    with pytest.raises(ResearchPlanError, match="does not cover"):
        ledger.authorize_investigation_activation(**{**base, "approved_ceiling_cents": 249})
    stale = InvestigationActivationQuote(**{
        **asdict(quote), "issued_at": "2020-01-01T00:00:00Z", "expires_at": "2020-01-01T01:00:00Z"
    })
    with pytest.raises(ResearchPlanError, match="stale"):
        ledger.authorize_investigation_activation(
            **{**base, "quote_resolver": lambda *_: stale}
        )
    created, _ = ledger.authorize_investigation_activation(**base)
    with pytest.raises(ResearchPlanError, match="idempotency conflict"):
        ledger.authorize_investigation_activation(**{**base, "approved_ceiling_cents": 301})
    with pytest.raises(ResearchPlanError, match="idempotency conflict"):
        ledger.authorize_investigation_activation(**{**base, "ttl_seconds": 3599})
    with pytest.raises(ResearchPlanError, match="already has"):
        ledger.authorize_investigation_activation(**{**base, "idempotency_key": "activate-other-123"})
    with sqlite3.connect(ledger.path) as connection:
        connection.execute(
            "UPDATE multimedia_prepared_investigations SET prepared_integrity_digest=? "
            "WHERE investigation_id=?", ("f" * 64, prepared.investigation_id),
        )
    with pytest.raises(ResearchPlanError, match="integrity"):
        ledger.get_investigation_activation_authorization(
            owner_identity_digest=owner, investigation_id=created.investigation_id
        )


@pytest.mark.parametrize("value", [True, 9_223_372_036_854_775_808])
def test_activation_monetary_values_reject_bool_and_bigint_overflow(tmp_path, value) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    kwargs = dict(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-12345678", route_policy="balanced",
        approved_ceiling_cents=300, ttl_seconds=3600,
    )
    with pytest.raises(ResearchPlanValidationError, match="positive integer"):
        ledger.authorize_investigation_activation(
            **{**kwargs, "approved_ceiling_cents": value},
            quote_resolver=lambda *_: quote,
        )
    invalid_quote = InvestigationActivationQuote(**{
        **asdict(quote), "quoted_ceiling_cents": value,
    })
    with pytest.raises(ResearchPlanError, match="quote integrity"):
        ledger.authorize_investigation_activation(
            **kwargs, quote_resolver=lambda *_: invalid_quote,
        )


def test_activation_canonical_record_tamper_fails_closed(tmp_path) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    authorization, _ = ledger.authorize_investigation_activation(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-12345678", route_policy="balanced",
        approved_ceiling_cents=300, ttl_seconds=3600,
        quote_resolver=lambda *_: quote,
    )
    with sqlite3.connect(ledger.path) as connection:
        raw = json.loads(connection.execute(
            "SELECT authorization_json FROM "
            "multimedia_investigation_activation_authorizations WHERE authorization_id=?",
            (authorization.authorization_id,),
        ).fetchone()[0])
        raw["provider"] = "tampered-provider"
        connection.execute(
            "UPDATE multimedia_investigation_activation_authorizations "
            "SET authorization_json=? WHERE authorization_id=?",
            (json.dumps(raw, sort_keys=True, separators=(",", ":")), authorization.authorization_id),
        )
    with pytest.raises(ResearchPlanError, match="integrity"):
        ledger.get_investigation_activation_authorization(
            owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        )


def test_activation_expiry_boundary_is_inclusive() -> None:
    now = datetime.now(UTC)

    def timestamp(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    base = dict(
        authorization_id="mia_" + "a" * 48, investigation_id="mpi_" + "b" * 48,
        prepared_integrity_digest="c" * 64, source_plan_id="mrp_" + "d" * 48,
        source_plan_version=1, source_plan_integrity_digest="e" * 64,
        source_intent_id="mmri_" + "f" * 48, source_intent_digest="1" * 64,
        source_evidence_digest="2" * 64, total_node_count=1, leaf_question_count=1,
        route_policy="balanced", resolved_tier="standard", provider="provider", model="model",
        dispatch_config_digest="3" * 64, pricing_source="pricebook",
        pricing_digest="4" * 64, workload_digest="5" * 64, quoted_ceiling_cents=1,
        quote_id="quote", quote_issued_at=timestamp(now - timedelta(hours=1)),
        quote_expires_at=timestamp(now + timedelta(hours=1)), quote_digest="6" * 64,
        approved_ceiling_cents=1, ttl_seconds=60, request_digest="7" * 64,
        issued_at=timestamp(now - timedelta(minutes=1)),
    )
    assert InvestigationActivationAuthorization(
        **base, expires_at=timestamp(now),
    ).is_expired is True
    assert InvestigationActivationAuthorization(
        **base, expires_at=timestamp(now + timedelta(minutes=1)),
    ).is_expired is False


def test_activation_consumption_reserves_complete_band_and_replays_exactly(tmp_path) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    authorization, _ = ledger.authorize_investigation_activation(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-12345678", route_policy="balanced",
        approved_ceiling_cents=300, ttl_seconds=3600, quote_resolver=lambda *_: quote,
    )
    kwargs = dict(owner_identity_digest=owner, investigation_id=prepared.investigation_id,
                  authorization_id=authorization.authorization_id,
                  idempotency_key="consume-12345678", quote_resolver=lambda *_: quote,
                  supported_maximum_cents=(1 << 62) - 1)
    reservation, created = ledger.consume_investigation_activation(**kwargs)
    replay, replay_created = ledger.consume_investigation_activation(**kwargs)
    assert created is True and replay_created is False and replay == reservation
    assert reservation.reserved_cents == authorization.approved_ceiling_cents == 300
    assert reservation.launch_reservation_id.startswith("mlr_")
    assert reservation.spend_run_id.startswith("mlsr_")
    assert reservation.session_id.startswith("mls_")
    assert reservation.execution_started is reservation.background_work_authorized is False
    with pytest.raises(ResearchPlanError, match="consumption conflicts"):
        ledger.consume_investigation_activation(
            **{**kwargs, "idempotency_key": "consume-other-123"}
        )


def test_activation_consumption_rejects_semantic_quote_drift_without_row(tmp_path) -> None:
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    authorization, _ = ledger.authorize_investigation_activation(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-12345678", route_policy="balanced",
        approved_ceiling_cents=300, ttl_seconds=3600, quote_resolver=lambda *_: quote,
    )
    with pytest.raises(ResearchPlanError, match="drifted"):
        ledger.consume_investigation_activation(
            owner_identity_digest=owner, investigation_id=prepared.investigation_id,
            authorization_id=authorization.authorization_id,
            idempotency_key="consume-12345678",
            quote_resolver=lambda *_: replace(quote, model="changed-model"),
            supported_maximum_cents=(1 << 62) - 1,
        )
    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM multimedia_investigation_launch_reservations"
        ).fetchone()[0] == 0


def _authorized_consumption(tmp_path, approved_cents: int = 300):
    ledger, owner, prepared, quote = _activation_fixture(tmp_path)
    authorization, _ = ledger.authorize_investigation_activation(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        idempotency_key="activate-consume-123", route_policy="balanced",
        approved_ceiling_cents=approved_cents, ttl_seconds=3600,
        quote_resolver=lambda *_: quote,
    )
    kwargs = dict(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        authorization_id=authorization.authorization_id,
        idempotency_key="consume-rigorous-123", supported_maximum_cents=(1 << 62) - 1,
    )
    return ledger, owner, prepared, quote, authorization, kwargs


def test_launch_replay_after_expiry_is_exact_and_does_not_resolve(tmp_path, monkeypatch) -> None:
    ledger, _owner, _prepared, quote, authorization, kwargs = _authorized_consumption(tmp_path)
    created, _ = ledger.consume_investigation_activation(
        **kwargs, quote_resolver=lambda *_: quote,
    )
    future = datetime.fromisoformat(authorization.expires_at.replace("Z", "+00:00"))

    class ExpiredDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return future

    monkeypatch.setattr(research_plan_module, "datetime", ExpiredDateTime)
    replay, was_created = ledger.consume_investigation_activation(
        **kwargs, quote_resolver=lambda *_: pytest.fail("exact replay resolved a quote"),
    )
    assert was_created is False and replay == created


def test_launch_first_use_rejects_inclusive_authorization_expiry(tmp_path, monkeypatch) -> None:
    ledger, _owner, _prepared, quote, authorization, kwargs = _authorized_consumption(tmp_path)
    boundary = datetime.fromisoformat(authorization.expires_at.replace("Z", "+00:00"))

    class BoundaryDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return boundary

    monkeypatch.setattr(research_plan_module, "datetime", BoundaryDateTime)
    with pytest.raises(ResearchPlanError, match="expired"):
        ledger.consume_investigation_activation(**kwargs, quote_resolver=lambda *_: quote)
    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM multimedia_investigation_launch_reservations"
        ).fetchone()[0] == 0


def test_launch_accepts_refreshed_quote_identity_and_timestamps(tmp_path) -> None:
    ledger, _owner, _prepared, quote, _authorization, kwargs = _authorized_consumption(tmp_path)
    now = datetime.now(UTC)
    refreshed = replace(
        quote, quote_id="refreshed-quote-identity",
        issued_at=(now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        expires_at=(now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
    )
    reservation, created = ledger.consume_investigation_activation(
        **kwargs, quote_resolver=lambda *_: refreshed,
    )
    assert created is True and reservation.reserved_cents == 300


def test_concurrent_launch_consumption_has_one_winner(tmp_path) -> None:
    ledger, _owner, _prepared, quote, _authorization, kwargs = _authorized_consumption(tmp_path)
    barrier = threading.Barrier(2)

    def resolve(*_args):
        barrier.wait(timeout=5)
        return quote

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda _: ledger.consume_investigation_activation(**kwargs, quote_resolver=resolve),
            range(2),
        ))
    assert sum(created for _, created in results) == 1
    assert results[0][0] == results[1][0]


def test_launch_consumption_starts_no_network_task_thread_or_background_path(tmp_path) -> None:
    ledger, _owner, _prepared, quote, _authorization, kwargs = _authorized_consumption(tmp_path)
    with (
        patch.object(asyncio, "create_task") as create_task,
        patch.object(socket, "create_connection") as create_connection,
        patch.object(threading.Thread, "start") as thread_start,
    ):
        reservation, created = ledger.consume_investigation_activation(
            **kwargs, quote_resolver=lambda *_: quote,
        )
    assert created is True
    assert reservation.execution_started is False
    assert reservation.background_work_authorized is False
    create_task.assert_not_called()
    create_connection.assert_not_called()
    thread_start.assert_not_called()


@pytest.mark.parametrize("delta, commits", [(0, True), (1, False)])
def test_launch_supported_authority_boundary_is_enforced_before_commit(
    tmp_path, delta: int, commits: bool,
) -> None:
    maximum = (1 << 62) - 1
    ledger, _owner, _prepared, quote, _authorization, kwargs = _authorized_consumption(
        tmp_path, maximum + delta,
    )
    if commits:
        reservation, created = ledger.consume_investigation_activation(
            **kwargs, quote_resolver=lambda *_: quote,
        )
        assert created is True and reservation.reserved_cents == maximum
    else:
        with pytest.raises(ResearchPlanError, match="exceeds supported"):
            ledger.consume_investigation_activation(**kwargs, quote_resolver=lambda *_: quote)
        with sqlite3.connect(ledger.path) as connection:
            assert connection.execute(
                "SELECT count(*) FROM multimedia_investigation_launch_reservations"
            ).fetchone()[0] == 0


@pytest.mark.parametrize("column", ["provider", "launch_manifest_digest", "reserved_cents"])
def test_launch_explicit_scalar_tamper_fails_closed(tmp_path, column: str) -> None:
    ledger, owner, prepared, quote, _authorization, kwargs = _authorized_consumption(tmp_path)
    ledger.consume_investigation_activation(**kwargs, quote_resolver=lambda *_: quote)
    value = 301 if column == "reserved_cents" else "f" * 64
    with sqlite3.connect(ledger.path) as connection:
        connection.execute(
            f"UPDATE multimedia_investigation_launch_reservations SET {column}=?",
            (value,),
        )
    with pytest.raises(ResearchPlanError, match="integrity"):
        ledger.get_investigation_launch_reservation(
            owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        )


def test_launch_noncanonical_json_tamper_fails_closed(tmp_path) -> None:
    ledger, owner, prepared, quote, _authorization, kwargs = _authorized_consumption(tmp_path)
    ledger.consume_investigation_activation(**kwargs, quote_resolver=lambda *_: quote)
    with sqlite3.connect(ledger.path) as connection:
        raw = connection.execute(
            "SELECT reservation_json FROM multimedia_investigation_launch_reservations"
        ).fetchone()[0]
        connection.execute(
            "UPDATE multimedia_investigation_launch_reservations SET reservation_json=?",
            (json.dumps(json.loads(raw), indent=2),),
        )
    with pytest.raises(ResearchPlanError, match="integrity"):
        ledger.get_investigation_launch_reservation(
            owner_identity_digest=owner, investigation_id=prepared.investigation_id,
        )


def test_v4_to_v5_migration_preserves_activation_authorization(tmp_path) -> None:
    ledger, owner, prepared, _quote, authorization, _kwargs = _authorized_consumption(tmp_path)
    with sqlite3.connect(ledger.path) as connection:
        connection.execute("DROP TABLE multimedia_investigation_launch_reservations")
        connection.execute("PRAGMA user_version=4")
    reopened = ledger.get_investigation_activation_authorization(
        owner_identity_digest=owner, investigation_id=prepared.investigation_id,
    )
    assert reopened == authorization
    with sqlite3.connect(ledger.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(multimedia_investigation_launch_reservations)"
            )
        }
    assert "launch_manifest_digest" in columns
    assert "authorization_integrity_digest" in columns
