"""Pure tests for workstation session insight record compose."""

from __future__ import annotations

import pytest

from substrate.workstation_session_insight_record_compose import (
    WorkstationSessionInsightRecordComposeError,
    compose_workstation_session_insight_record,
)


def test_pack_without_persist():
    c = compose_workstation_session_insight_record(
        session_id="ws-1",
        parent_asset_id="asset-1",
        operator_ack=True,
        mark_for_prompt_context=True,
        records=[
            {
                "record_id": "r1",
                "kind": "insight",
                "body": "claim holds under noise",
                "source_ref": "fdr_1",
            },
            {
                "record_id": "r2",
                "kind": "question",
                "body": "what is the sample size?",
            },
            {"record_id": "r3", "kind": "data", "body": "n=1200"},
        ],
    )
    assert c.record_ready is True
    assert c.record_count == 3
    assert c.insight_count == 1
    assert c.question_count == 1
    assert c.data_count == 1
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.to_dict()["record_persisted"] is False


def test_not_ready_and_duplicate():
    no_ack = compose_workstation_session_insight_record(
        session_id="ws",
        parent_asset_id="a",
        operator_ack=False,
        records=[{"record_id": "r1", "kind": "insight", "body": "x"}],
    )
    assert no_ack.record_ready is False
    with pytest.raises(
        WorkstationSessionInsightRecordComposeError, match="duplicate"
    ):
        compose_workstation_session_insight_record(
            session_id="ws",
            parent_asset_id="a",
            operator_ack=True,
            records=[
                {"record_id": "r1", "kind": "insight", "body": "x"},
                {"record_id": "r1", "kind": "question", "body": "y"},
            ],
        )
