from __future__ import annotations

import ast
import asyncio
import json
import os
import socket
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from substrate.multimedia.research_intent import ResearchIntentLedger
from substrate.multimedia.research_plan import (
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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3


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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
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
