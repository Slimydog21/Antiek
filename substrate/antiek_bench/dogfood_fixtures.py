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
# Residual (afz): v18 learns highlight → floating DR path honesty (afw–afx).
# Residual (agh): v19 learns Gödel foundations free PD book_qa.
# Residual (agp): v20 learns TalkToBook + MetaReading twin note-taker paths.
# Residual (ags): v21 learns Fourier heat free PD book_qa + ResearchThis twins.
# Residual (agw): v22 learns seamless spawn merge + multi-spawn collective merge paths.
# Residual (ahd): v23 learns knowledge-dense publication quick-call matrix (agx–ahc).
# Residual (ahn): v24 learns budget foresight with pubs + purchase seamless port.
# Residual (ahs): v25 learns domain-aware twin intelligent search (ahr).
# Residual (aib): v26 learns collective unit twin seed + MO deposit twin honesty.
# Residual (aig): v27 learns pub-ref foresight chrome matrix (aic–aif).
# Residual (ail): v28 learns citation chain + competitive DR scorecard honesty.
# Residual (ais): v29 learns multi-hop citation chain hop navigation (air).
# Residual (ajb): v30 learns expanded domain-aware twin search (aiy biology/method/physics/math).
# Residual (ajk): v31 learns evidence pack Write seed multi-hop hop honesty (aji).
# Residual (ajq): v32 learns twin promote depth-graph unit≡node honesty (ajn/ajo).
# Residual (ajw): v33 learns twin promote Write seed depth-graph honesty (ajv).
# Residual (anj): v34 learns reading conversation + marketplace host collective multi-select (ang–ani).
# Residual (ano): v35 learns free PD Nicomachean Ethics philosophy book_qa (anm).
COMPETITIVE_DOGFOOD_VERSION = "suite-competitive-dogfood-v35"


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
        # Residual (agh): free foundations PD → book_qa (Gödel incompleteness).
        SuiteItem(
            item_id="dogfood-book-godel-incompleteness",
            task_class="book_qa",
            prompt=(
                "From Gödel On Formally Undecidable Propositions (free PD HTML): what "
                "conjecture about formal systems does he refute, how do undecidable "
                "propositions in arithmetic limit machine reasoning, and why does free "
                "public-domain hosting of foundations texts matter for technology "
                "research workstations and knowledge graphs?"
            ),
            expected_keywords=(
                "godel",
                "undecidable",
                "formal",
                "axioms",
                "html",
            ),
        ),
        # Residual (ags): free heat/signal processing PD → book_qa (Fourier).
        SuiteItem(
            item_id="dogfood-book-fourier-heat",
            task_class="book_qa",
            prompt=(
                "From Fourier The Analytical Theory of Heat (free PD HTML): how does he "
                "frame heat as penetrating every substance, what is the object of the "
                "work regarding mathematical laws, and why does free public-domain "
                "hosting of foundational heat and signal-processing texts matter for "
                "technology research workstations?"
            ),
            expected_keywords=(
                "fourier",
                "heat",
                "mathematical",
                "laws",
                "html",
            ),
        ),
        # Residual (ags/agq): ResearchThis twin note-taker on book DR launch.
        SuiteItem(
            item_id="dogfood-wrestle-research-this-twins",
            task_class="wrestle",
            prompt=(
                "Wrestle with ResearchThis recursive note-taker path: when Research this "
                "passage mounts TwinNotesPanel with data-seamless-research-this-twins · "
                "autoLoad · autoSeedIfEmpty for documentId and selection body, how should "
                "Antiek-bench learn models that keep book DR launch twin substrate honest "
                "alongside collective multi-select without claiming live L3 seed is online?"
            ),
            expected_keywords=(
                "research",
                "twin",
                "seamless",
                "selection",
                "book",
            ),
        ),
        # Residual (agw/agu): highlight → float DR → single-spawn merge path honesty.
        SuiteItem(
            item_id="dogfood-wrestle-spawn-merge-path",
            task_class="wrestle",
            prompt=(
                "Wrestle with seamless highlight→DR→merge path: when SpawnMergePanel stamps "
                "data-seamless-spawn-merge · data-seamless-highlight-dr-merge with spawn_id "
                "and parent_asset_id bound, and draft_combined vs into_parent actions stamp "
                "data-seamless-merge-draft / data-seamless-merge-parent, how should "
                "Antiek-bench learn models that preserve draft-leaves-parent honesty and "
                "recursive note-taker twin seed after merge without inventing live council?"
            ),
            expected_keywords=(
                "seamless",
                "merge",
                "draft_combined",
                "into_parent",
                "spawn",
            ),
        ),
        # Residual (agw/agv): multi-select subagent collective merge path honesty.
        SuiteItem(
            item_id="dogfood-wrestle-collective-multi-spawn-merge",
            task_class="wrestle",
            prompt=(
                "Wrestle with seamless multi-spawn collective merge: when CollectiveResearchPanel "
                "stamps data-seamless-collective-merge · data-seamless-multi-spawn-merge and "
                "data-seamless-collective-merge-ready when parent is bound and ≥1 spawn selected, "
                "and draft / into_parent / written analysis actions stamp seamless merge attrs, "
                "how should Antiek-bench learn models that keep multi-select subagent merge into "
                "reading assets and written analysis offline-honest without claiming L6 live council?"
            ),
            expected_keywords=(
                "collective",
                "multi",
                "spawn",
                "merge",
                "seamless",
            ),
        ),
        # Residual (ahd/agx–ahc): knowledge-dense publication quick-call matrix.
        SuiteItem(
            item_id="dogfood-wrestle-pub-quick-call-matrix",
            task_class="wrestle",
            prompt=(
                "Wrestle with knowledge-dense publication quick-call matrix: when "
                "KNOWLEDGE_DENSE_PUBLICATION_PRESETS insert arxiv/URL handles on StartResearch, "
                "ChatInputArea, PublicationAttachPanel, HostedHtml, MarketplaceHost, and "
                "ResearchThis with data-seamless-pub-quick-call · data-auto-hydrate=false "
                "(insert-only · never invent live body), how should Antiek-bench learn models "
                "that ground deep research with competitive source connectors while staying "
                "offline-honest until Attach/Ask/DR and dual-gate L1/L2 live injectors?"
            ),
            expected_keywords=(
                "publication",
                "arxiv",
                "quick",
                "hydrate",
                "offline",
            ),
        ),
        # Residual (ahn/ahg–ahm): budget foresight when multi-source pubs ground a prompt.
        SuiteItem(
            item_id="dogfood-wrestle-budget-foresight-pub-refs",
            task_class="wrestle",
            prompt=(
                "Wrestle with budget foresight when knowledge-dense pubs ground a prompt: when "
                "StartResearch, ChatInputArea, ResearchThis, HostedHtml, and MarketplaceHost stamp "
                "data-pub-ref-count · data-has-pub-refs · data-prompt-chars and budget panels use "
                "composeDriverPromptText(body, pubRefs) so multi-ref quick-call increases projected "
                "spend before Ask/DR fire, how should Antiek-bench learn models that keep soft "
                "budget honesty without inventing $0 or silent over-budget launches?"
            ),
            expected_keywords=(
                "budget",
                "foresight",
                "publication",
                "projection",
                "soft",
            ),
        ),
        # Residual (ahn/ahe): paid digital book seamless port honesty (L5 deferred).
        SuiteItem(
            item_id="dogfood-wrestle-purchase-seamless-port",
            task_class="wrestle",
            prompt=(
                "Wrestle with paid digital book seamless port: when MarketplaceHost purchase+host "
                "stamps data-seamless-purchase-port · data-l5-payment-rails=deferred · "
                "data-live-payment=false · manual_receipt_only and host land stamps purchased-path "
                "for non-PD books as HTML, how should Antiek-bench learn models that never invent "
                "live checkout rails while preserving HTML-first account port and recursive "
                "note-taker twin seed after purchase?"
            ),
            expected_keywords=(
                "purchase",
                "seamless",
                "receipt",
                "html",
                "payment",
            ),
        ),
        # Residual (ahs/ahr): domain-aware twin intelligent search default.
        SuiteItem(
            item_id="dogfood-wrestle-domain-aware-twin-search",
            task_class="wrestle",
            prompt=(
                "Wrestle with domain-aware twin intelligent search: when ResearchContextPanel "
                "prefills query via domainAwareSearchDefault from asset subjects (heat / "
                "signal_processing for Fourier free STEM, foundations for Gödel, electricity, "
                "information_theory, computing) and marketplace host openWindow passes catalog "
                "subjects into HostedHtml domainSubjects, how should Antiek-bench learn models "
                "that ground recursive note-taker search without inventing domains or live L3 seed?"
            ),
            expected_keywords=(
                "domain",
                "twin",
                "search",
                "subjects",
                "heat",
            ),
        ),
        # Residual (aib/aht): collective unit HTML twin seed offline honesty.
        SuiteItem(
            item_id="dogfood-wrestle-collective-unit-twin-seed",
            task_class="wrestle",
            prompt=(
                "Wrestle with collective unit HTML twin seed: when opening multi-spawn cohesive "
                "unit prompt as float|full HTML seeds twin notes with force_offline and body "
                "port honesty multi-spawn cohesive unit prompt (never invent live L6 council), "
                "how should Antiek-bench learn models that keep recursive note-taker substrate "
                "honest for multi-select unit windows without claiming live multi-agent council?"
            ),
            expected_keywords=(
                "collective",
                "unit",
                "twin",
                "offline",
                "seed",
            ),
        ),
        # Residual (aib/ahu): Midnight Oil deposit twin port honesty.
        SuiteItem(
            item_id="dogfood-wrestle-moil-deposit-twin-honesty",
            task_class="wrestle",
            prompt=(
                "Wrestle with Midnight Oil deposit twin honesty: when reseedDepositTwins prefixes "
                "body with Port path Midnight Oil deposit HTML offline-honest and L4 live worker "
                "dual-gate deferred, how should Antiek-bench learn models that record MO provenance "
                "in recursive note-taker substrate without inventing live multi-provider worker steps?"
            ),
            expected_keywords=(
                "midnight",
                "oil",
                "deposit",
                "twin",
                "offline",
            ),
        ),
        # Residual (aig/aic–aif): operator-visible pub-ref foresight chrome matrix.
        SuiteItem(
            item_id="dogfood-wrestle-pub-ref-foresight-chrome",
            task_class="wrestle",
            prompt=(
                "Wrestle with pub-ref foresight chrome: when StartResearch, ChatInputArea, "
                "ResearchThis, HostedHtml, and MarketplaceHost show operator-visible chrome "
                "Knowledge-dense pubs in projection: N refs · chars=… · soft budget below after "
                "knowledge-dense quick-call inserts, how should Antiek-bench learn models that "
                "keep competitive budget-before-fire honesty for multi-source grounding without "
                "inventing $0 or hiding over-budget risk?"
            ),
            expected_keywords=(
                "foresight",
                "chrome",
                "budget",
                "refs",
                "soft",
            ),
        ),
        # Residual (ail/aij): evidence pack citation chain honesty.
        SuiteItem(
            item_id="dogfood-wrestle-citation-chain",
            task_class="wrestle",
            prompt=(
                "Wrestle with evidence pack citation chain: when ResearchContextPanel stamps "
                "data-testid=evidence-citation-chain with insights→questions→source refs, "
                "data-chain-complete when insights and refs both present, and incomplete chain "
                "copy never invents sources, how should Antiek-bench learn models that preserve "
                "competitive citation-required synthesis honesty?"
            ),
            expected_keywords=(
                "citation",
                "chain",
                "insights",
                "refs",
                "grounded",
            ),
        ),
        # Residual (ais/air): multi-hop claim→source hop navigation (anchors · no invented edges).
        SuiteItem(
            item_id="dogfood-wrestle-citation-chain-hops",
            task_class="wrestle",
            prompt=(
                "Wrestle with multi-hop citation chain navigation: when evidence_pack emits "
                "citation_chain stages (insights → questions → sources) with stable anchors "
                "(evidence-insight-N / evidence-question-N / evidence-source-N), chain_complete "
                "only when claims and sources both present, and ResearchContextPanel renders "
                "data-testid=evidence-citation-chain-hops with #anchor hop links without inventing "
                "supported_by edges, how should Antiek-bench learn models that preserve competitive "
                "claim→source grounding UX honesty?"
            ),
            expected_keywords=(
                "multi-hop",
                "anchor",
                "citation_chain",
                "hops",
                "sources",
            ),
        ),
        # Residual (ajb/aiy): expanded domain-aware twin intelligent search free STEM.
        SuiteItem(
            item_id="dogfood-wrestle-domain-aware-stem-expanded",
            task_class="wrestle",
            prompt=(
                "Wrestle with expanded domain-aware twin intelligent search: when "
                "domainAwareSearchDefault maps biology→micrographia natural history, "
                "method→novum organum, physics→principia motion forces, and pure mathematics→"
                "geometry elements axioms (while electricity still precedes bare physics), "
                "how should Antiek-bench learn models that ground twin search queries in free "
                "STEM catalog subjects without inventing subjects?"
            ),
            expected_keywords=(
                "domain-aware",
                "biology",
                "method",
                "physics",
                "mathematics",
            ),
        ),
        # Residual (ajk/aji): evidence pack Write twin_seed multi-hop hop honesty.
        SuiteItem(
            item_id="dogfood-wrestle-evidence-write-multi-hop",
            task_class="wrestle",
            prompt=(
                "Wrestle with evidence pack → Write twin_seed multi-hop honesty: when "
                "buildEvidencePackWriteHref stamps data-chain-complete, data-citation-chain-hops, "
                "and plain_text anchors (evidence-insight-N / evidence-source-N) without inventing "
                "supported_by edges or empty packs, how should Antiek-bench learn models that "
                "preserve claim→source multi-hop grounding into the recursive note-taker?"
            ),
            expected_keywords=(
                "multi-hop",
                "twin_seed",
                "chain_complete",
                "evidence_pack",
                "write",
            ),
        ),
        # Residual (ajq/ajn/ajo): twin promote depth-graph content-addressed honesty.
        SuiteItem(
            item_id="dogfood-wrestle-twin-promote-depth-graph",
            task_class="wrestle",
            prompt=(
                "Wrestle with twin promote → depth-graph honesty: when twin_promote_context_payload "
                "emits graph_node_ids, unique_graph_node_count, content_addressed_alignment "
                "(unit_id ≡ graph_node_id), and TwinNotesPanel twin-promote-metrics stamps "
                "data-content-addressed-alignment with FUTURE twin matrix deep-links without "
                "inventing graph edges, how should Antiek-bench learn models that preserve "
                "recursive note-taker promote→context content-addressed identity?"
            ),
            expected_keywords=(
                "depth-graph",
                "content-addressed",
                "graph_node",
                "promote",
                "twin",
            ),
        ),
        # Residual (ajw/ajv): twin promote Write twin_seed depth-graph honesty.
        SuiteItem(
            item_id="dogfood-wrestle-twin-promote-write-depth-graph",
            task_class="wrestle",
            prompt=(
                "Wrestle with twin promote → Write twin_seed depth-graph honesty: when "
                "buildTwinPromoteWriteHref stamps [depth_graph] unique_nodes, "
                "content_addressed_alignment, data-unique-graph-node-count, and unit_id "
                "anchors in plain/HTML without inventing graph edges, how should Antiek-bench "
                "learn models that preserve recursive note-taker promote→Write depth-graph "
                "identity into writing?"
            ),
            expected_keywords=(
                "depth-graph",
                "twin_seed",
                "write",
                "content_addressed",
                "promote",
            ),
        ),
        # Residual (ail/aii): Settings competitive DR quality scorecard honesty.
        SuiteItem(
            item_id="dogfood-wrestle-competitive-dr-scorecard",
            task_class="wrestle",
            prompt=(
                "Wrestle with Settings competitive DR quality scorecard: when the scorecard lists "
                "shipped offline multi-agent merge, citation chain, budget foresight, HTML-first, "
                "source quick-call, twins, and deferred L1–L6 live injectors with ND never router, "
                "how should Antiek-bench learn models that never claim live injectors as shipped "
                "and never promote NotDiamond to dispatch authority?"
            ),
            expected_keywords=(
                "scorecard",
                "shipped",
                "deferred",
                "notdiamond",
                "competitive",
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
        # Residual (afz/afw–afx): highlight → floating deep research path honesty.
        SuiteItem(
            item_id="dogfood-wrestle-highlight-deep-research-path",
            task_class="wrestle",
            prompt=(
                "Wrestle with highlight → deep research path honesty: when FloatMenu "
                "Deep-research stamps data-seamless-highlight-dr · view-mode float|full "
                "and openDeepResearchFromHighlight stamps payload.seamless_highlight_dr "
                "with host data-seamless-highlight-dr, how should Antiek-bench weekly "
                "rewrite learn models that keep highlight→session→window path continuous "
                "without inventing live multi-agent council?"
            ),
            expected_keywords=(
                "highlight",
                "seamless",
                "floating",
                "deep",
                "research",
            ),
        ),
        # Residual (agp/agm): TalkToBook twin note-taker on book asset.
        SuiteItem(
            item_id="dogfood-wrestle-talk-to-book-twins",
            task_class="wrestle",
            prompt=(
                "Wrestle with TalkToBook recursive note-taker path: when open Talk to this "
                "book mounts TwinNotesPanel with data-seamless-talk-twins · autoLoad · "
                "autoSeedIfEmpty for documentId, how should Antiek-bench learn models that "
                "keep book conversation twin insights/questions substrate honest without "
                "claiming live L3 note_taker seed is online?"
            ),
            expected_keywords=(
                "talk",
                "twin",
                "book",
                "seamless",
                "note",
            ),
        ),
        # Residual (agp/agn): MetaReading twin note-taker on synthesis asset.
        SuiteItem(
            item_id="dogfood-wrestle-meta-reading-twins",
            task_class="wrestle",
            prompt=(
                "Wrestle with MetaReading recursive note-taker path: when a corpus "
                "meta-reading deliverable mounts TwinNotesPanel with "
                "data-seamless-meta-twins · autoLoad · autoSeedIfEmpty for asset_id, "
                "how should Antiek-bench weekly rewrite learn models that keep synthesis "
                "asset twin substrate continuous with reading ≡ research?"
            ),
            expected_keywords=(
                "meta",
                "twin",
                "reading",
                "seamless",
                "asset",
            ),
        ),
        # Residual (anj/ang): TalkToBook collective multi-select merge into book.
        SuiteItem(
            item_id="dogfood-wrestle-talk-to-book-collective",
            task_class="wrestle",
            prompt=(
                "Wrestle with TalkToBook collective multi-select path (ang): when open "
                "Talk to this book mounts CollectiveResearchPanel with "
                "data-seamless-talk-collective · open/recent DR spawn ids · "
                "parentAssetId=documentId, how should Antiek-bench weekly rewrite learn "
                "models that multi-select merge/analysis targets the book under "
                "conversation without inventing live multi-agent council (L6 dual-gate)?"
            ),
            expected_keywords=(
                "talk",
                "collective",
                "book",
                "merge",
                "spawn",
            ),
        ),
        # Residual (anj/anh): MetaReading collective multi-select into deliverable.
        SuiteItem(
            item_id="dogfood-wrestle-meta-reading-collective",
            task_class="wrestle",
            prompt=(
                "Wrestle with MetaReading collective multi-select path (anh): when a "
                "meta-reading deliverable mounts CollectiveResearchPanel with "
                "data-seamless-meta-collective · open/recent DR spawns · "
                "parentAssetId=asset_id, how should Antiek-bench learn models that "
                "keep multi-select merge into the HTML synthesis continuous with "
                "reading ≡ research twin+context remount?"
            ),
            expected_keywords=(
                "meta",
                "collective",
                "reading",
                "merge",
                "spawn",
            ),
        ),
        # Residual (anj/ani): Marketplace host-land collective multi-select.
        SuiteItem(
            item_id="dogfood-wrestle-marketplace-host-collective",
            task_class="wrestle",
            prompt=(
                "Wrestle with MarketplaceHost host-land collective multi-select (ani): "
                "when hosted free/purchased HTML book mounts CollectiveResearchPanel with "
                "data-seamless-marketplace-collective · open/recent DR spawns · "
                "parentAssetId=document_id, how should Antiek-bench weekly rewrite learn "
                "models that multi-select merge targets the hosted library book while "
                "L5 payment rails stay offline-honest?"
            ),
            expected_keywords=(
                "marketplace",
                "collective",
                "host",
                "merge",
                "html",
            ),
        ),
        # Residual (ano/anm): free PD Nicomachean Ethics philosophy book_qa.
        SuiteItem(
            item_id="dogfood-book-nicomachean-ethics",
            task_class="book_qa",
            prompt=(
                "Book QA over free public-domain HTML Nicomachean Ethics (Aristotle): "
                "what is the chief good at which all arts and inquiries aim, and how "
                "should Antiek HTML-first reading + twin note-taker capture eudaimonia "
                "insights without inventing live payment rails or PDF view?"
            ),
            expected_keywords=(
                "ethics",
                "good",
                "html",
                "philosophy",
                "aristotle",
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
