from __future__ import annotations

import json
from pathlib import Path

from runtime.research_runner.derived_companion_execution import (
    SCHEMA_VERSION,
    project_derived_companion_execution,
)


def _project(path: Path) -> dict[str, object]:
    return project_derived_companion_execution(
        derived_asset_id="ast_" + "a" * 32,
        revision_id="rev_" + "b" * 32,
        content_sha256="c" * 64,
        generation=3,
        qualification_path=path,
    )


def test_projects_checked_blockers_without_spend_authority(tmp_path: Path) -> None:
    source = Path("runtime/research_runner/provider_qualification.json")
    path = tmp_path / "qualification.json"
    path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    result = _project(path)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["available"] is False
    assert result["reservable"] is False
    assert result["dispatch_authorized"] is False
    assert result["reason"] == "no_provider_route_qualified"
    assert result["pricing_status"] == "unavailable"
    assert result["recommended_ceiling_cents"] is None
    routes = result["routes"]
    assert isinstance(routes, list)
    assert [(route["provider"], route["model"], route["operation"]) for route in routes] == sorted(
        (route["provider"], route["model"], route["operation"]) for route in routes
    )
    openai = next(route for route in routes if route["provider"] == "openai")
    assert openai["blocking_dimensions"] == [
        "durable_idempotency", "authoritative_reconciliation"
    ]
    assert "finding" not in json.dumps(result) and "source_url" not in json.dumps(result)


def test_malformed_registry_fails_closed_without_details(tmp_path: Path) -> None:
    path = tmp_path / "qualification.json"
    path.write_text('{"secret":"leak-me"}', encoding="utf-8")
    result = _project(path)
    assert result["reason"] == "qualification_registry_invalid"
    assert result["routes"] == []
    assert result["recommended_ceiling_cents"] is None
    assert "leak-me" not in json.dumps(result)


def test_passing_evidence_alone_does_not_register_execution(tmp_path: Path) -> None:
    evidence = {
        dimension: {
            "status": "pass",
            "source_url": f"https://example.com/{dimension}",
            "finding": "checked",
        }
        for dimension in (
            "pinned_pricing", "durable_idempotency", "hidden_retries_disabled",
            "authoritative_reconciliation", "stable_provider_evidence",
        )
    }
    path = tmp_path / "qualification.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "qualifications": [{
            "provider": "future", "model": "grounded", "operation": "answer",
            "checked_at": "2026-07-15", "verdict": "qualified", "evidence": evidence,
        }],
    }), encoding="utf-8")
    result = _project(path)
    assert result["reason"] == "executable_route_not_registered"
    assert result["available"] is False
    assert result["reservable"] is False
    assert result["dispatch_authorized"] is False
    assert result["routes"][0]["blocking_dimensions"] == []


def test_refused_verdict_cannot_promote_all_passing_evidence(tmp_path: Path) -> None:
    evidence = {
        dimension: {
            "status": "pass",
            "source_url": f"https://example.com/{dimension}",
            "finding": "checked",
        }
        for dimension in (
            "pinned_pricing", "durable_idempotency", "hidden_retries_disabled",
            "authoritative_reconciliation", "stable_provider_evidence",
        )
    }
    path = tmp_path / "qualification.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "qualifications": [{
            "provider": "future", "model": "grounded", "operation": "answer",
            "checked_at": "2026-07-15", "verdict": "refused", "evidence": evidence,
        }],
    }), encoding="utf-8")
    result = _project(path)
    assert result["reason"] == "no_provider_route_qualified"
    assert result["routes"][0]["verdict"] == "refused"
