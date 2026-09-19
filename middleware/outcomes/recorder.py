"""Outcome construction + persistence.

Pure construction (``build_outcome_record``): converts a JSON payload
into a validated ``OutcomeRecord`` dataclass.

Persistence (``record_outcome_via_db``, Sprint 10 day 4-5): writes to
the ``outcomes`` table on a ``LockedConnection``. The four sub-list/
object inputs are serialized as TEXT-JSON columns; the
typed ``OutcomeRecordedPayload`` remains canonical (callers can fire
``emit_outcome_recorded`` after the write).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from .types import (
    DecisionAlignmentInput,
    ExecutionRiskOutcomeInput,
    FalsificationOutcomeInput,
    OutcomeRecord,
    ThesisOutcomeInput,
)


def build_outcome_record(
    *,
    synthesis_id: str,
    payload: Mapping[str, Any],
    observer: str | None = None,
    notes: str | None = None,
    outcome_id: str | None = None,
) -> OutcomeRecord:
    """Validate + project a raw payload into an ``OutcomeRecord``.

    ``payload`` is the legacy INPUT_SCHEMA dict shape (four optional
    list/object keys plus optional ``observer`` / ``notes`` envelope
    fields). Per-element validation happens in the dataclass
    ``__post_init__`` hooks — bad enums fail loudly here, not at
    Pydantic serialization later.

    ``observer`` and ``notes`` override the payload-embedded values
    when supplied (matches the Researchmaxx CLI semantics).
    """
    obs = observer or payload.get("observer")
    if not obs:
        raise ValueError("observer is required (kwarg or payload.observer)")

    nts = notes if notes is not None else payload.get("notes")

    thesis_raw = payload.get("thesis_outcomes") or []
    thesis = tuple(
        ThesisOutcomeInput(
            thesis_claim=str(t.get("thesis_claim", "")),
            outcome=str(t.get("outcome", "unresolved")),
            evidence=str(t.get("evidence", "")),
            evidence_chunk_ids=tuple(t.get("evidence_chunk_ids") or ()),
        )
        for t in thesis_raw
    )

    fals_raw = payload.get("falsification_outcomes") or []
    falsifications = tuple(
        FalsificationOutcomeInput(
            condition=str(f.get("condition", "")),
            occurred=bool(f.get("occurred", False)),
            evidence=str(f.get("evidence", "")),
        )
        for f in fals_raw
    )

    risks_raw = payload.get("execution_risk_outcomes") or []
    risks = tuple(
        ExecutionRiskOutcomeInput(
            risk=str(r.get("risk", "")),
            manifested=bool(r.get("manifested", False)),
            severity_actual=str(r.get("severity_actual", "none")),
            evidence=str(r.get("evidence", "")),
        )
        for r in risks_raw
    )

    da_raw = payload.get("decision_alignment")
    decision = None
    if da_raw is not None:
        decision = DecisionAlignmentInput(
            agent_implicit_recommendation=str(
                da_raw.get("agent_implicit_recommendation", "conditional")
            ),
            actual_decision=str(da_raw.get("actual_decision", "not_observed")),
            decision_outcome_at_observation=str(
                da_raw.get("decision_outcome_at_observation", "")
            ),
            thesis_outcome_when_proceeded=str(
                da_raw.get("thesis_outcome_when_proceeded", "not_observed")
            ),
        )

    return OutcomeRecord(
        outcome_id=outcome_id or str(uuid.uuid4()),
        synthesis_id=synthesis_id,
        observer=obs,
        thesis_outcomes=thesis,
        falsification_outcomes=falsifications,
        execution_risk_outcomes=risks,
        decision_alignment=decision,
        notes=nts,
    )


def record_outcome_via_db(con: Any, record: OutcomeRecord) -> str:
    """Persist an ``OutcomeRecord`` to the ``outcomes`` table. Returns
    the outcome_id. Requires a ``LockedConnection``."""
    try:
        from ...runtime.db_lock import LockedConnection  # type: ignore[import-not-found]
    except ImportError:
        from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "record_outcome_via_db requires a LockedConnection."
        )
    con.execute(
        "INSERT INTO outcomes ("
        " outcome_id, synthesis_id, observer, "
        " thesis_outcomes, falsification_outcomes, "
        " execution_risk_outcomes, decision_alignment, notes"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            record.outcome_id, record.synthesis_id, record.observer,
            json.dumps([asdict(t) for t in record.thesis_outcomes]),
            json.dumps([asdict(f) for f in record.falsification_outcomes]),
            json.dumps([asdict(r) for r in record.execution_risk_outcomes]),
            (
                json.dumps(asdict(record.decision_alignment))
                if record.decision_alignment is not None else None
            ),
            record.notes,
        ],
    )
    return record.outcome_id


def record_outcome_authorized(
    con: Any, authority: Any, record: OutcomeRecord
) -> str:
    """Persist an outcome only when its synthesis parent matches authority."""
    from substrate.graph.tenancy import assert_graph_authority
    from substrate.investigation_tenancy import InvestigationAuthority

    if not isinstance(authority, InvestigationAuthority):
        raise TypeError("outcome recording requires InvestigationAuthority")
    assert_graph_authority(con, authority)
    parent = con.execute(
        "SELECT synthesis_id, investigation_id, account_digest, "
        "investigation_digest FROM syntheses WHERE synthesis_id = ? "
        "AND account_digest = ? AND investigation_digest = ?",
        [
            record.synthesis_id,
            authority.account_digest,
            authority.investigation_digest,
        ],
    ).fetchone()
    if parent is None:
        raise KeyError(f"synthesis_id not found: {record.synthesis_id!r}")
    return record_outcome_via_db(con, record)


def record_outcome_payload_authorized(
    con: Any,
    authority: Any,
    *,
    outcome_id: str,
    synthesis_id: str,
    observer: str,
    thesis_outcomes: list[dict[str, Any]],
    falsification_outcomes: list[dict[str, Any]],
    execution_risk_outcomes: list[dict[str, Any]],
    decision_alignment: dict[str, Any] | None,
    notes: str | None,
) -> str:
    """Authority-safe compatibility writer for the API's historical payload."""
    from substrate.graph.tenancy import assert_graph_authority
    from substrate.investigation_tenancy import InvestigationAuthority

    if not isinstance(authority, InvestigationAuthority):
        raise TypeError("outcome recording requires InvestigationAuthority")
    assert_graph_authority(con, authority)
    parent = con.execute(
        "SELECT synthesis_id, investigation_id, account_digest, "
        "investigation_digest FROM syntheses WHERE synthesis_id = ? "
        "AND account_digest = ? AND investigation_digest = ?",
        [synthesis_id, authority.account_digest, authority.investigation_digest],
    ).fetchone()
    if parent is None:
        raise KeyError(f"synthesis_id not found: {synthesis_id!r}")
    con.execute(
        "INSERT INTO outcomes (outcome_id, synthesis_id, observer, "
        "thesis_outcomes, falsification_outcomes, execution_risk_outcomes, "
        "decision_alignment, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            outcome_id,
            synthesis_id,
            observer,
            json.dumps(thesis_outcomes),
            json.dumps(falsification_outcomes),
            json.dumps(execution_risk_outcomes),
            json.dumps(decision_alignment) if decision_alignment is not None else None,
            notes,
        ],
    )
    return outcome_id
