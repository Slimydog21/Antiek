"""Pure tests for competition gap residual execute compose."""

from __future__ import annotations

import pytest

from substrate.competition_gap_residual_execute_compose import (
    CompetitionGapResidualExecuteComposeError,
    compose_competition_gap_residual_execute,
)

RESIDUAL = {
    "residual_id": "res-citation-1",
    "area": "citation_grounding",
    "competitor": "perplexity",
    "residual_text": "Span-level citations in DR output",
    "antiek_status": "behind",
    "priority": "P0",
    "execution_hint": "Wire citation spans into DR quality floor pure modules",
}


def test_package_without_execution():
    c = compose_competition_gap_residual_execute(
        residual=RESIDUAL,
        operator_ack=True,
        proposed_owned_files=[
            "apps/reading/src/api/deepResearchCitationSpans.ts",
        ],
    )
    assert c.package_ready is True
    assert c.execution_authorized is False
    assert c.backlog_mutated is False
    assert c.store_mutated is False
    assert "pure_module" in c.acceptance_gates
    assert c.to_dict()["execution_authorized"] is False


def test_not_ready_without_ack():
    c = compose_competition_gap_residual_execute(
        residual=RESIDUAL, operator_ack=False
    )
    assert c.package_ready is False
    assert c.execution_authorized is False


def test_rejects_app_py():
    with pytest.raises(CompetitionGapResidualExecuteComposeError, match="app.py"):
        compose_competition_gap_residual_execute(
            residual=RESIDUAL,
            operator_ack=True,
            proposed_owned_files=["interfaces/research/api/app.py"],
        )
