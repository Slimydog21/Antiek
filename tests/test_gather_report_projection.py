from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from interfaces.research.api import cascade_routes as cr
from interfaces.research.api.investigation_access import RequestInvestigationAuthority
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas.events import (
    ActionType,
    GatherReportRecordedPayload,
    GatherSourceReportReceipt,
)


def _payload(*, unknown: bool = False) -> GatherReportRecordedPayload:
    statuses = ("unknown", "skipped", "skipped", "skipped") if unknown else (
        "succeeded",
        "succeeded",
        "succeeded",
        "succeeded",
    )
    sources = ("exa", "parallel", "arxiv", "substack")
    return GatherReportRecordedPayload(
        launch_fingerprint="a" * 64,
        plan_fingerprint="b" * 64,
        legal_policy_snapshot_sha256="c" * 64,
        receipts=tuple(
            GatherSourceReportReceipt(
                source=source,
                status=status,
                document_ids=("doc-1",) if not unknown and index == 0 else (),
            )
            for index, (source, status) in enumerate(zip(sources, statuses, strict=True))
        ),
        document_ids=() if unknown else ("doc-1",),
        minimum_evidence_documents=1,
        evidence_complete=not unknown,
        partial=False,
        unknown_outcome=unknown,
    )


def test_gather_report_schema_rejects_noncanonical_or_false_unknown_truth() -> None:
    payload = _payload()
    raw = payload.model_dump(mode="json")
    raw["receipts"][0]["source"] = "parallel"
    with pytest.raises(ValidationError, match="canonical source order"):
        GatherReportRecordedPayload.model_validate(raw)

    raw = payload.model_dump(mode="json")
    raw["unknown_outcome"] = True
    with pytest.raises(ValidationError, match="must match source receipts"):
        GatherReportRecordedPayload.model_validate(raw)

    raw = payload.model_dump(mode="json")
    raw["document_ids"] = []
    with pytest.raises(ValidationError, match="ordered receipt union"):
        GatherReportRecordedPayload.model_validate(raw)

    raw = payload.model_dump(mode="json")
    raw["evidence_complete"] = False
    with pytest.raises(ValidationError, match="admitted document coverage"):
        GatherReportRecordedPayload.model_validate(raw)

    raw = payload.model_dump(mode="json")
    raw["partial"] = True
    with pytest.raises(ValidationError, match="terminal source coverage"):
        GatherReportRecordedPayload.model_validate(raw)


def test_recovery_projects_validated_secret_free_leaf_report(monkeypatch, tmp_path: Path) -> None:
    access = RequestInvestigationAuthority(
        InvestigationAuthority("acct", "session", tmp_path), frozenset(), "test"
    )
    payload = _payload(unknown=True)
    monkeypatch.setattr(cr, "owns_investigation", lambda _access: True)
    monkeypatch.setattr(
        "substrate.event_log.trajectory_authorized",
        lambda _authority: [
            {
                "action_type": ActionType.GATHER_REPORT_RECORDED.value,
                "payload": payload.model_dump(mode="json"),
            }
        ],
    )

    reports = cr._gather_reports_authorized(access, ["session-leaf-0"])

    assert reports[0]["investigation_id"] == "session-leaf-0"
    assert reports[0]["unknown_outcome"] is True
    assert reports[0]["receipts"][0]["status"] == "unknown"
    assert "action_type" not in reports[0]
    assert "api_key" not in str(reports).lower()


def test_recovery_isolates_invalid_typed_report_as_secret_free_error(
    monkeypatch, tmp_path: Path
) -> None:
    access = RequestInvestigationAuthority(
        InvestigationAuthority("acct", "session", tmp_path), frozenset(), "test"
    )
    malformed = _payload().model_dump(mode="json")
    malformed["evidence_complete"] = False
    monkeypatch.setattr(cr, "owns_investigation", lambda _access: True)
    monkeypatch.setattr(
        "substrate.event_log.trajectory_authorized",
        lambda _authority: [
            {
                "action_type": ActionType.GATHER_REPORT_RECORDED.value,
                "payload": malformed,
            }
        ],
    )
    errors: list[dict[str, str]] = []

    reports = cr._gather_reports_authorized(
        access, ["session-leaf-0"], errors=errors
    )

    assert reports == []
    assert errors == [
        {"investigation_id": "session-leaf-0", "code": "gather_report_invalid"}
    ]
    assert "validation" not in str(errors).lower()
