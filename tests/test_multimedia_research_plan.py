from __future__ import annotations

import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from substrate.multimedia.research_intent import ResearchIntentLedger
from substrate.multimedia.research_plan import (
    ResearchPlanError,
    ResearchPlanLedger,
    ResearchPlanStorageError,
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
