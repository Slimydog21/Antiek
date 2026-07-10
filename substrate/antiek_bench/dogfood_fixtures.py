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
# Residual (wd): v10 adds book_qa information theory (Shannon free PD).
# Residual (wl): v11 adds book_qa computability (Turing free PD).
# Residual (xi): v12 adds book_qa computing history (Lovelace free PD).
# Residual (adn): v13 adds wrestle write-seed has-body honesty (title-only → rewrite).
# Residual (aeu): v14 learns seamless Write path + intelligent search/evidence.
# Residual (afi): v15 learns written analysis Open Write source + unit continue path.
# Residual (afo): v16 learns Select open multi-select assembly + unit restore path.
# Residual (afv): v17 learns Select recent path + ResearchWorkstation spine.
COMPETITIVE_DOGFOOD_VERSION = "suite-competitive-dogfood-v17"


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
        # Residual (adn): write-seed body honesty → recursive suite rewrite learning.
        SuiteItem(
            item_id="dogfood-wrestle-write-seed-has-body",
            task_class="wrestle",
            prompt=(
                "Wrestle with twin_seed body honesty: when should data-write-seed-has-body "
                "be true vs title-only false across Open Write handoffs, and how should "
                "title-only (has_body=false) failed usage events feed Antiek-bench "
                "recursive suite rewrite without inventing document bodies?"
            ),
            expected_keywords=(
                "has-body",
                "title-only",
                "twin_seed",
                "rewrite",
                "honesty",
            ),
        ),
        # Residual (wd): free information-theory PD → book_qa (Shannon).
        SuiteItem(
            item_id="dogfood-book-shannon-communication",
            task_class="book_qa",
            prompt=(
                "From Shannon A Mathematical Theory of Communication (free PD HTML): "
                "what is the fundamental problem of communication, how does logarithmic "
                "information measure relate to entropy, and why does free public-domain "
                "hosting of foundational information-theory texts matter for technology "
                "research workstations?"
            ),
            expected_keywords=(
                "shannon",
                "information",
                "entropy",
                "communication",
                "html",
            ),
        ),
        # Residual (wl): free computability PD → book_qa (Turing).
        SuiteItem(
            item_id="dogfood-book-turing-computable-numbers",
            task_class="book_qa",
            prompt=(
                "From Turing On Computable Numbers (free PD HTML): what is a computable "
                "number, how does the Entscheidungsproblem relate to machine calculation, "
                "and why does free public-domain hosting of foundational computability "
                "texts matter for technology research workstations?"
            ),
            expected_keywords=(
                "turing",
                "computable",
                "machine",
                "entscheidungsproblem",
                "html",
            ),
        ),
        # Residual (xi): free computing-history PD → book_qa (Lovelace).
        SuiteItem(
            item_id="dogfood-book-lovelace-analytical-engine",
            task_class="book_qa",
            prompt=(
                "From Lovelace Sketch of the Analytical Engine (free PD HTML): how does "
                "she describe the Analytical Engine as weaving algebraical patterns, what "
                "is an operation in her most general sense, and why does free public-domain "
                "hosting of foundational computing-history texts matter for technology "
                "research workstations?"
            ),
            expected_keywords=(
                "lovelace",
                "analytical",
                "engine",
                "babbage",
                "html",
            ),
        ),
        # Residual (aeu): seamless Write path honesty across reading/research surfaces.
        SuiteItem(
            item_id="dogfood-wrestle-seamless-write-path",
            task_class="wrestle",
            prompt=(
                "Wrestle with seamless Open Write path honesty: how should "
                "data-seamless-reading-research-write (deep research parent asset), "
                "data-seamless-merge-write (draft_combined vs into_parent), "
                "data-seamless-host-write (HostedHtml), data-seamless-port "
                "(marketplace library), and data-seamless-moil-write (Midnight Oil "
                "deposit) differ as machine-readable handoffs into the recursive "
                "note-taker without inventing document ids or auto-merging?"
            ),
            expected_keywords=(
                "seamless",
                "write",
                "draft_combined",
                "into_parent",
                "html",
            ),
        ),
        # Residual (aeu): intelligent search + evidence citation-trust → Write.
        SuiteItem(
            item_id="dogfood-wrestle-intelligent-search-context-write",
            task_class="wrestle",
            prompt=(
                "Wrestle with intelligent search and evidence → Write: when context_search "
                "or evidence_pack Open Write stamps data-seamless-context-write, "
                "data-query, data-hit-count, and data-citation-trust grounded vs "
                "ungrounded, how should Antiek-bench weekly rewrite learn which models "
                "preserve citation honesty and recursive note-taker substrate quality?"
            ),
            expected_keywords=(
                "search",
                "citation",
                "context",
                "twin_seed",
                "honesty",
            ),
        ),
        # Residual (afi/afg): written analysis Open Write must not collapse to doc merge.
        SuiteItem(
            item_id="dogfood-wrestle-written-analysis-open-write-source",
            task_class="wrestle",
            prompt=(
                "Wrestle with multi-spawn written analysis Open Write provenance: after "
                "Create written analysis (collective + draft_combined), why must "
                "data-write-seed-source stay collective_written_analysis instead of "
                "collapsing to collective_doc_merge, and how does that protect Antiek-bench "
                "weekly rewrite feeds for analysis vs document merge tasks?"
            ),
            expected_keywords=(
                "collective_written_analysis",
                "collective_doc_merge",
                "twin_seed",
                "write",
                "honesty",
            ),
        ),
        # Residual (afi/afh): continue-as-unit path honesty for unit re-entry → DR.
        SuiteItem(
            item_id="dogfood-wrestle-continue-as-unit-path",
            task_class="wrestle",
            prompt=(
                "Wrestle with continue-as-unit path honesty: when Continue as cohesive unit "
                "stamps data-seamless-unit-continue · data-collective-id · "
                "data-parent-asset-id, how should the workstation keep multi-select unit "
                "re-entry into deep research machine-readable without claiming L6 live "
                "multi-agent council is online?"
            ),
            expected_keywords=(
                "continue",
                "collective",
                "seamless",
                "parent",
                "deferred",
            ),
        ),
        # Residual (afo/afn): Select open multi-select assembly path honesty.
        SuiteItem(
            item_id="dogfood-wrestle-select-open-path",
            task_class="wrestle",
            prompt=(
                "Wrestle with Select open multi-select assembly path honesty: when "
                "Select open stamps data-seamless-select-open · data-last-select-mode=open "
                "· data-open-in-available and excludes closed recent-only spawns, how "
                "should Antiek-bench weekly rewrite learn which models keep open-window "
                "cohesive unit prep machine-readable without inventing L6 live council?"
            ),
            expected_keywords=(
                "select",
                "open",
                "seamless",
                "multi-select",
                "deferred",
            ),
        ),
        # Residual (afo/afl): restore last unit membership path honesty.
        SuiteItem(
            item_id="dogfood-wrestle-unit-restore-path",
            task_class="wrestle",
            prompt=(
                "Wrestle with restore last unit path honesty: when Restore last unit "
                "stamps data-seamless-unit-restore and membership status action=restored "
                "intersects sessionStorage spawn_ids with available list, how should the "
                "workstation re-open multi-select cohesive unit membership without claiming "
                "L6 live multi-agent council is online?"
            ),
            expected_keywords=(
                "restore",
                "unit",
                "seamless",
                "membership",
                "deferred",
            ),
        ),
        # Residual (afv/afp): Select recent multi-select assembly path honesty.
        SuiteItem(
            item_id="dogfood-wrestle-select-recent-path",
            task_class="wrestle",
            prompt=(
                "Wrestle with Select recent multi-select assembly path honesty: when "
                "Select recent stamps data-seamless-select-recent · data-last-select-mode="
                "recent · data-recent-in-available for closed chase/float twin-chase batch, "
                "how should Antiek-bench weekly rewrite learn models that keep recent_ring "
                "cohesive unit prep machine-readable without inventing L6 live council?"
            ),
            expected_keywords=(
                "select",
                "recent",
                "seamless",
                "multi-select",
                "deferred",
            ),
        ),
        # Residual (afv/afr–aft): ResearchWorkstation reading≡research spine.
        SuiteItem(
            item_id="dogfood-wrestle-research-workstation-spine",
            task_class="wrestle",
            prompt=(
                "Wrestle with ResearchWorkstation /inv/:id reading≡research spine: when "
                "InvestigationCenter mounts TwinNotes (autoLoad · autoSeed · autoPromote), "
                "ResearchContext pack, and CollectiveResearchPanel for open/recent DR "
                "spawns, how should Antiek-bench learn models that keep recursive note-taker "
                "substrate and multi-select assembly honest on the research workstation?"
            ),
            expected_keywords=(
                "workstation",
                "twin",
                "context",
                "collective",
                "promote",
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
