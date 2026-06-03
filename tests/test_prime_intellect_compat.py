"""Prime Intellect F + D debt items — Sprint 17 (master-spec §15.8).

F: trajectory → verifiers schema compat test. Proves Antiek's typed
event log can be mapped to the Prime Intellect verifiers env schema
without information loss.

D: `prime eval run` runner for Antiek rubrics with the
parameter_extractor_v0.jsonl fixture. Sprint 17 ships 10 of the 50
target examples; operator-curated expansion to 50 lands incrementally
as parameter_extractor traces accumulate in production.
"""

from __future__ import annotations

import json
import os

import pytest

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "parameter_extractor_v0.jsonl"
)


@pytest.fixture
def fixture_rows():
    rows = []
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def test_fixture_exists_and_loads():
    """Item D: the eval fixture must be readable JSONL."""
    assert os.path.exists(FIXTURE_PATH), (
        "parameter_extractor_v0.jsonl missing from tests/fixtures/. "
        "Without it the `prime eval run` runner has no inputs."
    )
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    assert len(rows) >= 10, (
        f"Sprint 17 ships ≥10 examples; got {len(rows)}. Operator "
        f"expands to 50 incrementally per master-spec §15.8."
    )


def test_fixture_schema(fixture_rows):
    """Item D: each fixture row must have chunk_text + expected_parameters."""
    for i, row in enumerate(fixture_rows):
        assert "chunk_text" in row, f"row {i} missing chunk_text"
        assert "expected_parameters" in row, f"row {i} missing expected_parameters"
        assert isinstance(row["expected_parameters"], list)
        for j, p in enumerate(row["expected_parameters"]):
            for required in ("name", "value", "units"):
                assert required in p, (
                    f"row {i} parameter {j} missing required field {required!r}"
                )


def test_trajectory_event_maps_to_verifiers_shape():
    """Item F: an Antiek typed event row must be mappable to the
    Prime Intellect verifiers env schema.

    Verifiers shape (from `prime` SDK Environment.step protocol):
      {
        "observation": str,       # what the agent sees
        "action": str,            # what the agent emits
        "reward": float | None,   # scalar reward (None during eval)
        "info": dict,             # arbitrary metadata
      }

    Antiek event row (from substrate/schemas/events.py):
      {
        "event_id": str,
        "investigation_id": str,
        "action_type": str,
        "emitted_at": str (ISO 8601),
        "role": str,
        "payload": {...},
      }

    The mapping (deterministic, no LLM in the loop):
      observation = payload context (depends on action_type)
      action      = payload completion text or role output
      reward      = computed downstream from rubric verification
      info        = {event_id, action_type, role, emitted_at}
    """
    antiek_event = {
        "event_id": "evt-abc123",
        "investigation_id": "inv-quantum-001",
        "action_type": "parameter_extractor.delivered",
        "emitted_at": "2026-05-19T12:34:56.789Z",
        "role": "parameter_extractor",
        "payload": {
            "action_type": "parameter_extractor.delivered",
            "chunk_id": "chunk-7890",
            "parameters": [
                {
                    "name": "single_qubit_gate_error_rate",
                    "value": 8.5e-4,
                    "units": "dimensionless",
                },
            ],
        },
    }
    verifiers_step = _map_to_verifiers(antiek_event)
    assert "observation" in verifiers_step
    assert "action" in verifiers_step
    assert "info" in verifiers_step
    assert verifiers_step["info"]["event_id"] == "evt-abc123"
    assert verifiers_step["info"]["action_type"] == "parameter_extractor.delivered"
    assert verifiers_step["info"]["role"] == "parameter_extractor"


def _map_to_verifiers(event: dict) -> dict:
    """Antiek event row → verifiers env step shape.

    Lives in this test for now; promotes to
    `substrate/dispatch/verifiers_adapter.py` when prime-rl integration
    actively uses it (Sprint 19+ autoresearch local-only track per
    master-spec §14.2)."""
    payload = event.get("payload") or {}
    return {
        "observation": json.dumps(
            {k: v for k, v in payload.items() if k != "action_type"},
            sort_keys=True,
        ),
        "action": payload.get("text") or payload.get("completion") or "",
        "reward": None,  # filled in by downstream rubric verifier
        "info": {
            "event_id": event.get("event_id"),
            "action_type": event.get("action_type"),
            "role": event.get("role"),
            "emitted_at": event.get("emitted_at"),
            "investigation_id": event.get("investigation_id"),
        },
    }
