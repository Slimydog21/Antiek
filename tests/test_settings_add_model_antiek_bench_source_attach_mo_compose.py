"""Pure tests for settings add-model over Antiek-bench source-attach MO pack."""

from __future__ import annotations

from substrate.settings_add_model_antiek_bench_source_attach_mo_compose import (
    compose_settings_add_model_antiek_bench_source_attach_mo,
    format_settings_add_model_antiek_bench_source_attach_mo_summary,
)
from tests.test_antiek_bench_source_attach_settings_mo_compose import (
    BENCH,
    SOURCE_PACK,
)

SETTINGS = {
    "models": [
        {"model_id": "gpt-5.5", "provider": "openai"},
        {"model_id": "grok-4.5", "provider": "xai"},
    ],
    "pending_add_model_ids": ["mimo-v2", "composer-2.5"],
    "action": "propose_add",
    "daily_cap_usd": 50,
    "spent_usd": 10,
    "selected_model_id": "gpt-5.5",
    "projected_cost_usd_high": 2,
    "projected_cost_usd_low": 1,
}

BENCH_PACK = {
    "bench": BENCH,
    "source_pack": SOURCE_PACK,
}


def test_settings_add_model_bench_source_ready():
    c = compose_settings_add_model_antiek_bench_source_attach_mo(
        settings=SETTINGS,
        bench_pack=BENCH_PACK,
        operator_ack=True,
    )
    assert c.settings.pack_ready is True
    assert c.settings.action == "propose_add"
    assert c.settings.proposed_new_count >= 1
    assert c.settings.inventory_mutated is False
    assert c.settings.secrets_stored is False
    assert c.bench_pack.pack_ready is True
    assert c.bench_pack.bench.recommendation is not None
    assert c.bench_pack.bench.recommendation.recommended_model_id == "gpt-5.5"
    assert c.inventory_vs_bench == "agree"
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.backlog_mutated is False
    assert c.remote_fetched is False
    assert c.live_execution_authorized is False
    assert c.purchase_executed is False
    assert c.inventory_mutated is False
    assert c.secrets_stored is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "settings_add_model_antiek_bench_source_attach_mo_compose_advisory"
    )
    assert "inventory_mutated=false" in (
        format_settings_add_model_antiek_bench_source_attach_mo_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_settings_add_model_antiek_bench_source_attach_mo(
        settings=SETTINGS,
        bench_pack=BENCH_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.inventory_mutated is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"


def test_preview_no_new_ids_still_pure():
    c = compose_settings_add_model_antiek_bench_source_attach_mo(
        settings={
            **SETTINGS,
            "action": "preview",
            "pending_add_model_ids": [],
        },
        bench_pack=BENCH_PACK,
        operator_ack=True,
    )
    assert c.settings.pack_ready is True
    assert c.settings.proposed_new_count == 0
    assert c.bench_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.inventory_mutated is False
    assert c.secrets_stored is False
    assert c.production_router_verdict == "REJECT"


def test_high_min_events_yields_bench_none():
    c = compose_settings_add_model_antiek_bench_source_attach_mo(
        settings=SETTINGS,
        bench_pack={
            "bench": {**BENCH, "min_events_for_recommendation": 100},
            "source_pack": SOURCE_PACK,
        },
        operator_ack=True,
    )
    assert c.bench_pack.bench.recommendation is None
    assert c.inventory_vs_bench == "bench_none"
    assert c.inventory_mutated is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"
