"""Pure tests for source attach + settings decision MO pack."""

from __future__ import annotations

import pytest

from substrate.source_attach_settings_decision_mo_compose import (
    SourceAttachSettingsDecisionMoComposeError,
    compose_source_attach_settings_decision_mo,
    format_source_attach_settings_decision_mo_summary,
)
from tests.test_settings_decision_mo_unattended_fullscreen_compose import (
    DECISION,
    MO_PACK,
)

SOURCES = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "requested_families": ["arxiv", "substack"],
    "sources": [
        {
            "source_id": "arx-1",
            "family": "arxiv",
            "title": "Scaling Laws under Noise",
            "external_id": "arxiv:2301.00001",
            "html_fragment": "<article>abstract…</article>",
        },
        {
            "source_id": "sub-1",
            "family": "substack",
            "title": "Research notes on evals",
            "external_id": "substack:evals",
            "url": "https://example.substack.com/p/evals",
            "html_fragment": "<article>essay…</article>",
        },
    ],
}

SETTINGS_MO = {
    "decision": DECISION,
    "mo_pack": MO_PACK,
}


def test_source_attach_settings_mo_ready():
    c = compose_source_attach_settings_decision_mo(
        sources=SOURCES,
        settings_mo=SETTINGS_MO,
        operator_ack=True,
    )
    assert c.sources.attach_ready is True
    assert c.sources.html_ready_count == 2
    assert c.settings_mo.pack_ready is True
    assert c.pack_ready is True
    assert c.remote_fetched is False
    assert c.pdf_primary is False
    assert c.live_router_authorized is False
    assert c.live_execution_authorized is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority == "source_attach_settings_decision_mo_compose_advisory"
    )
    assert "remote_fetched=false" in (
        format_source_attach_settings_decision_mo_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_source_attach_settings_decision_mo(
        sources=SOURCES,
        settings_mo=SETTINGS_MO,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_source_attach_settings_decision_mo(
        sources={**SOURCES, "session_id": "sess-other"},
        settings_mo=SETTINGS_MO,
        operator_ack=True,
    )
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.pdf_primary is False


def test_would_exceed_blocks_overall():
    c = compose_source_attach_settings_decision_mo(
        sources=SOURCES,
        settings_mo={
            **SETTINGS_MO,
            "decision": {
                **DECISION,
                "spent_usd": 49,
                "projected_cost_usd_high": 5,
                "projected_cost_usd_low": 3,
            },
        },
        operator_ack=True,
    )
    assert c.settings_mo.pack_ready is False
    assert c.pack_ready is False
    assert c.remote_fetched is False
    assert c.live_router_authorized is False


def test_require_operator_ack_type():
    with pytest.raises(SourceAttachSettingsDecisionMoComposeError):
        compose_source_attach_settings_decision_mo(
            sources=SOURCES,
            settings_mo=SETTINGS_MO,
            operator_ack="yes",  # type: ignore[arg-type]
        )
