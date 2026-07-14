#!/usr/bin/env python3
"""CLI entry for research-workstation pure-logic residual.

Exercises the real shipped functions end-to-end (no mocks):
  note twin → research merge → midnight oil ceiling → budget projection.

Usage:
  PYTHONPATH=. python tools/research_workstation_cli.py
  PYTHONPATH=. python tools/research_workstation_cli.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root or tools/
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from substrate.research_workstation import (  # noqa: E402
    BudgetLimit,
    ModelRateCard,
    ResearchInstance,
    apply_merge_plan,
    build_midnight_oil_plan,
    build_note_twin,
    plan_merge,
    project_prompt_cost,
    twin_to_html,
    usage_bar,
)


def run_demo() -> dict[str, object]:
    source_text = (
        "Antiek is an HTML-first research and reading workstation. "
        "Deep research spins from highlights into floating windows. "
        "Every asset should carry a note twin of insights and open questions."
    )
    twin = build_note_twin(
        "asset-demo-1",
        insights=[
            "HTML is the primary human-viewable projection",
            {
                "summary": "Floating deep-research windows are first-class workspace objects",
                "quote": "spin from highlights into floating windows",
                "llm_confidence": 0.88,
            },
        ],
        open_questions=[
            "How should collective multi-agent merges preserve provenance?",
        ],
        source_text=source_text,
    )

    instances = [
        ResearchInstance(
            instance_id="dr-1",
            status="completed",
            findings=(
                "Competitive deep-research products ground claims in live retrieval; "
                "Antiek should keep gather non-stub on the dogfood path."
            ),
            highlight="Deep research spins from highlights",
            twin=twin,
            parent_asset_id="asset-demo-1",
            confidence=0.9,
        ),
        ResearchInstance(
            instance_id="dr-2",
            status="completed",
            findings=(
                "Price ceilings for autonomous swarms must be operator-approved "
                "before any live spend."
            ),
            highlight="autonomous research swarm",
            parent_asset_id="asset-demo-1",
            confidence=0.75,
        ),
        ResearchInstance(
            instance_id="dr-3",
            status="running",
            findings="still working",
        ),
    ]

    draft_plan = plan_merge(instances, "draft_merge")
    draft_doc = apply_merge_plan(instances, draft_plan)

    collective_plan = plan_merge(
        instances,
        "collective",
        selected_ids=["dr-1", "dr-2"],
    )
    collective_doc = apply_merge_plan(instances, collective_plan)

    oil = build_midnight_oil_plan(
        goals=[
            "Survey arxiv + substack connectors in deep research",
            "Draft Antiek-bench task taxonomy from usage patterns",
        ],
        work_minutes=90,
        agent_count=3,
        rate_card=ModelRateCard(
            model_id="research-default",
            usd_per_1k_input=0.50,
            usd_per_1k_output=1.50,
            tokens_per_minute=4000,
        ),
    )

    prompt = (
        "Using the merged research twin, write a precise analysis of "
        "HTML-first reading vs PDF-primary workflows for professional researchers."
    )
    limit = BudgetLimit(limit_usd=25.0, used_usd=3.40, label="demo-key")
    projection = project_prompt_cost(prompt, expected_output_tokens=1500)
    bar = usage_bar(limit, projection)

    return {
        "note_twin": {
            "twin_id": twin.twin_id,
            "asset_id": twin.asset_id,
            "insight_count": len(twin.insights),
            "open_question_count": len(twin.open_questions),
            "html_has_article": 'class="antiek-note-twin"' in twin_to_html(twin),
        },
        "draft_merge": {
            "executable": draft_plan.is_executable,
            "mutates_source": draft_plan.mutates_source,
            "instance_ids": list(draft_doc.source_instance_ids),
            "is_draft": draft_doc.is_draft,
            "html_has_merge": 'class="antiek-research-merge"' in draft_doc.body_html,
            "markdown_chars": len(draft_doc.body_markdown),
        },
        "collective_merge": {
            "executable": collective_plan.is_executable,
            "instance_ids": list(collective_doc.source_instance_ids),
            "title": collective_doc.title,
        },
        "midnight_oil": {
            "goals": list(oil.goals),
            "work_minutes": oil.work_minutes,
            "agent_count": oil.agent_count,
            "recommended_ceiling_usd": oil.ceiling.recommended_ceiling_usd,
            "expected_spend_usd": oil.ceiling.expected_spend_usd,
            "estimated_tokens": oil.ceiling.estimated_tokens,
            "requires_operator_approval": oil.requires_operator_approval,
        },
        "model_budget": {
            "label": bar.label,
            "percent_used": bar.percent_used,
            "projected_cost_usd": bar.projected_cost_usd,
            "would_exceed": bar.would_exceed,
            "remaining_usd": bar.remaining_usd,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON only",
    )
    args = parser.parse_args(argv)
    result = run_demo()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("Antiek research-workstation residual — live pure-logic path")
        print("=" * 60)
        print(json.dumps(result, indent=2, sort_keys=True))
        # Primary observables for harness verification
        assert result["note_twin"]["insight_count"] == 2
        assert result["draft_merge"]["executable"] is True
        assert result["draft_merge"]["mutates_source"] is False
        assert result["collective_merge"]["executable"] is True
        assert result["midnight_oil"]["recommended_ceiling_usd"] > 0
        assert result["midnight_oil"]["requires_operator_approval"] is True
        assert result["model_budget"]["would_exceed"] is False
        print("=" * 60)
        print("PRIMARY OBSERVABLES: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
