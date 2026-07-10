"""Competitive dogfood fixtures for Antiek-bench (residual av).

Fixed offline prompts that mirror competitive deep-research task postures
(distill / synthesize / wrestle / book_qa). Used to seed weekly runs and as
a stable base for usage-driven suite rewrites — never live multi-provider.

Does not auto-promote; register via ``register_competitive_dogfood_suite``.
"""

from __future__ import annotations

from typing import Any

from .suite import SuiteDefinition, SuiteItem, SuiteRegistry, register_suite

# Residual (st): v2 adds write-seed / float HTML / budget foresight postures.
# Residual (tf): v3 adds book_qa electricity STEM (Faraday/Maxwell free PD).
# Residual (tv): v4 adds multi-spawn collective unit → Write twin_seed posture.
# Residual (tz): v5 adds book_qa computing/logic (Boole free PD).
# Residual (ud): v6 adds book_qa electricity engineering (Heaviside free PD).
# Residual (us): v7 adds wrestle citation-trust ungrounded hydrate prep.
# Residual (ve): v8 adds wrestle twin_cross_asset_merge Write seed posture.
# Residual (vl): v9 adds wrestle collective_written_analysis Write seed posture.
COMPETITIVE_DOGFOOD_VERSION = "suite-competitive-dogfood-v9"


def competitive_dogfood_items() -> tuple[SuiteItem, ...]:
    return (
        SuiteItem(
            item_id="dogfood-distill-attention",
            task_class="distill",
            prompt=(
                "Distill the key claim from: Attention is content-addressable "
                "memory for sequence modeling (Transformer)."
            ),
            expected_keywords=("attention", "memory", "transformer", "claim"),
        ),
        SuiteItem(
            item_id="dogfood-synth-perplexity-vs-openai",
            task_class="synthesize",
            prompt=(
                "Synthesize how Perplexity-class speed and OpenAI-class depth "
                "differ for multi-step deep research product design."
            ),
            expected_keywords=("perplexity", "openai", "speed", "depth", "research"),
        ),
        SuiteItem(
            item_id="dogfood-wrestle-twin-notes",
            task_class="wrestle",
            prompt=(
                "Wrestle with the tension between ephemeral chat research and "
                "recursive twin notes that permanently capture insights/questions."
            ),
            expected_keywords=("twin", "notes", "insights", "questions", "recursive"),
        ),
        SuiteItem(
            item_id="dogfood-book-html-first",
            task_class="book_qa",
            prompt=(
                "Answer from a reading asset: why is HTML-first projection "
                "preferred over PDF for agent-controllable research workstations?"
            ),
            expected_keywords=("html", "pdf", "agent", "reading", "workstation"),
        ),
        SuiteItem(
            item_id="dogfood-wrestle-citations",
            task_class="wrestle",
            prompt=(
                "Wrestle with citation trust: how should arxiv/substack source "
                "refs land in an evidence pack without inventing sources?"
            ),
            expected_keywords=("arxiv", "substack", "citation", "evidence", "source"),
        ),
        # Residual (st): recursive note-taker → Write twin_seed posture.
        SuiteItem(
            item_id="dogfood-wrestle-write-seed",
            task_class="wrestle",
            prompt=(
                "Wrestle with the recursive note-taker Write path: why should "
                "deep research sessions seed twin_seed HTML writing assets "
                "that feed Antiek-bench by_source without auto-promoting suites?"
            ),
            expected_keywords=(
                "twin_seed",
                "write",
                "recursive",
                "bench",
                "promote",
            ),
        ),
        # Residual (st): float HTML evidence / reading flywheel posture.
        SuiteItem(
            item_id="dogfood-synth-float-evidence",
            task_class="synthesize",
            prompt=(
                "Synthesize how floating HTML evidence packs and context search "
                "windows beat chat-export PDFs for a personal research workstation."
            ),
            expected_keywords=(
                "html",
                "evidence",
                "float",
                "pdf",
                "workstation",
            ),
        ),
        # Residual (st): soft budget foresight at model driver choice.
        SuiteItem(
            item_id="dogfood-distill-budget-foresight",
            task_class="distill",
            prompt=(
                "Distill why decision-tree model install should show budget "
                "usage and sample cost projection without inventing $0 pricing."
            ),
            expected_keywords=(
                "budget",
                "projection",
                "decision-tree",
                "pricing",
                "soft",
            ),
        ),
        # Residual (tf): free STEM electricity PD → book_qa for tech researchers.
        SuiteItem(
            item_id="dogfood-book-faraday-induction",
            task_class="book_qa",
            prompt=(
                "From Faraday Experimental Researches in Electricity (free PD HTML): "
                "what is electromagnetic induction, and why does free public-domain "
                "hosting of knowledge-dense STEM books matter for research workstations?"
            ),
            expected_keywords=(
                "faraday",
                "induction",
                "electricity",
                "public",
                "html",
            ),
        ),
        # Residual (tv): multi-spawn cohesive unit prompt → Write twin_seed.
        SuiteItem(
            item_id="dogfood-wrestle-collective-unit-write-seed",
            task_class="wrestle",
            prompt=(
                "Wrestle with multi-select deep-research spawns: after merging into a "
                "cohesive unit prompt (source=collective_unit_prompt HTML float), why "
                "must Open Write preserve twin_seed source for Antiek-bench weekly rewrite "
                "instead of collapsing to twin_draft_selected, and never invent a server "
                "document_id for the prompt body alone?"
            ),
            expected_keywords=(
                "collective",
                "twin_seed",
                "write",
                "unit",
                "html",
            ),
        ),
        # Residual (tz): free computing/logic PD → book_qa for tech researchers.
        SuiteItem(
            item_id="dogfood-book-boole-laws-of-thought",
            task_class="book_qa",
            prompt=(
                "From Boole An Investigation of the Laws of Thought (free PD HTML): "
                "what is the relationship between logic and the symbolical calculus, "
                "and why does free public-domain hosting of foundational computing texts "
                "matter for technology research workstations?"
            ),
            expected_keywords=(
                "boole",
                "logic",
                "calculus",
                "computing",
                "html",
            ),
        ),
        # Residual (ud): free electricity engineering PD → book_qa (Heaviside).
        SuiteItem(
            item_id="dogfood-book-heaviside-em",
            task_class="book_qa",
            prompt=(
                "From Heaviside Electromagnetic Theory (free PD HTML): how did "
                "Heaviside reformulate Maxwell's equations for electrical engineering, "
                "and why does free public-domain hosting of engineering STEM texts "
                "matter for technology research workstations?"
            ),
            expected_keywords=(
                "heaviside",
                "maxwell",
                "electromagnetic",
                "engineering",
                "html",
            ),
        ),
        # Residual (us): citation-trust ungrounded → dual-gate hydrate prep.
        SuiteItem(
            item_id="dogfood-wrestle-citation-trust-ungrounded",
            task_class="wrestle",
            prompt=(
                "Wrestle with competitive deep research honesty: when an evidence pack "
                "or publication attach is ungrounded (ref_count=0 or hydrate failed), "
                "why must the workstation surface Settings hydrate readiness and dual-gate "
                "L1–L2 checklist instead of inventing arxiv/substack bodies or silent-live "
                "hydrate — and how does offline-default identity preserve citation trust?"
            ),
            expected_keywords=(
                "ungrounded",
                "hydrate",
                "citation",
                "offline",
                "dual",
            ),
        ),
        # Residual (ve): recursive note-taker cross-asset merge → Write twin_seed.
        SuiteItem(
            item_id="dogfood-wrestle-twin-cross-asset-merge-write-seed",
            task_class="wrestle",
            prompt=(
                "Wrestle with the recursive note-taker cross-asset merge path: after "
                "loading twins from multiple asset_ids and opening a combined HTML draft, "
                "why must Open Write preserve source=twin_cross_asset_merge for Antiek-bench "
                "weekly rewrite instead of collapsing to twin_draft_selected, and how does "
                "that feed honest multi-asset note provenance?"
            ),
            expected_keywords=(
                "twin",
                "cross",
                "merge",
                "twin_seed",
                "write",
            ),
        ),
        # Residual (vl): multi-spawn written analysis → Write twin_seed.
        SuiteItem(
            item_id="dogfood-wrestle-collective-written-analysis-write-seed",
            task_class="wrestle",
            prompt=(
                "Wrestle with multi-select deep-research written analysis: after merging "
                "spawn outputs into a written analysis HTML float "
                "(source=collective_written_analysis), why must Open Write preserve that "
                "source for Antiek-bench weekly rewrite instead of collapsing to "
                "hosted_html_document, and how does that differ from cohesive unit prompts?"
            ),
            expected_keywords=(
                "collective",
                "analysis",
                "twin_seed",
                "write",
                "html",
            ),
        ),
    )


def competitive_dogfood_suite() -> SuiteDefinition:
    return SuiteDefinition(
        suite_version=COMPETITIVE_DOGFOOD_VERSION,
        label="antiek-bench-competitive-dogfood",
        items=competitive_dogfood_items(),
    )


def register_competitive_dogfood_suite(
    *,
    registry: SuiteRegistry | None = None,
    make_active: bool = False,
) -> SuiteDefinition:
    """Register dogfood suite. Does not auto-activate unless make_active=True."""
    suite = competitive_dogfood_suite()
    return register_suite(suite, registry=registry, make_active=make_active)


def dogfood_fixture_payload(*, include_html: bool = False) -> dict[str, Any]:
    """Settings/product-facing listing of dogfood fixtures (not a live run)."""
    suite = competitive_dogfood_suite()
    by_class: dict[str, int] = {}
    for it in suite.items:
        by_class[it.task_class] = by_class.get(it.task_class, 0) + 1
    payload: dict[str, Any] = {
        "suite_version": suite.suite_version,
        "label": suite.label,
        "item_count": len(suite.items),
        "by_task_class": by_class,
        "items": [
            {
                "item_id": i.item_id,
                "task_class": i.task_class,
                "prompt": i.prompt,
            }
            for i in suite.items
        ],
        "auto_promoted": False,
        "view_format": "html",
        "settings_panel": "antiek_bench_dogfood_fixtures",
        "source": "antiek_bench.dogfood_fixtures",
        "notes": [
            "Competitive dogfood fixtures are offline prompts only.",
            "Register with register_competitive_dogfood_suite; promote only via approve_and_promote.",
        ],
    }
    if include_html:
        payload["html"] = project_dogfood_html(payload)
    return payload


def project_dogfood_html(payload: dict[str, Any]) -> str:
    from substrate.engagement_spine.project import project_to_html

    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Antiek-bench competitive dogfood"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Suite {payload.get('suite_version')} · "
                        f"items={payload.get('item_count')} · view: HTML · not auto-promoted"
                    ),
                }
            ],
        },
    ]
    for it in payload.get("items") or []:
        if not isinstance(it, dict):
            continue
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"[{it.get('task_class')}] {it.get('item_id')}: {it.get('prompt')}",
                    }
                ],
            }
        )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id="antiek-bench-dogfood",
        creator="antiek_bench.dogfood_fixtures",
    )
