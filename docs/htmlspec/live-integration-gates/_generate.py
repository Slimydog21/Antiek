"""Generate the canonical live-integration gate htmlspec."""

from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STYLE_SOURCE = Path("/Users/slimydog/.agents/skills/htmlspec/templates/style.css")
GENERATED = "2026-07-13"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def shell(title: str, body: str, *, wide: bool = False) -> str:
    css = STYLE_SOURCE.read_text(encoding="utf-8")
    page = "page page--wide" if wide else "page"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(title)}</title><style>{css}</style></head>
<body><main class="{page}">{body}</main></body></html>\n"""


def milestones(items: list[tuple[str, str, str, str]]) -> str:
    return "".join(
        '<div class="milestone"><div class="num">'
        f"{index}</div><div><div class=\"title\">{esc(title)}</div>"
        f'<p class="desc">{esc(description)}</p>'
        f'<div class="criteria"><strong>Acceptance criteria</strong><ul>'
        f"<li>{esc(criteria)}</li></ul></div>"
        f'<div class="files"><span class="file">{esc(files)}</span></div>'
        "</div></div>"
        for index, (title, description, criteria, files) in enumerate(items, 1)
    )


def rigor(cards: dict[str, str]) -> str:
    return "".join(
        f'<article class="rigor-card"><span class="label">{esc(name)}</span>'
        f"<p>{esc(text)}</p></article>"
        for name, text in cards.items()
    )


SPRINTS = [
    {
        "id": "LIG-SPR-01",
        "slug": "arxiv-hydration",
        "title": "L1 · governed arXiv HTML hydration",
        "wave": "1",
        "goal": "Prove that an operator-enabled arXiv reference becomes a canonical HTML asset with governed network behavior and exact source receipts.",
        "deps": "Operator approval for outbound arxiv.org access; existing acquisition.arxiv client, hydrate-ref route, and canonical HTML ingest.",
        "out": "No PDF reading surface, broad crawler, silent CI network, or claim that Atom metadata alone is a full paper body.",
        "milestones": [
            ("Pin the body contract", "Separate metadata, abstract, source text, and unavailable states so the adapter cannot relabel metadata as a hydrated paper.", "A fixture for each state produces a distinct typed receipt and only a real body can set hydrated=true.", "substrate/engagement_spine/hydrate_adapters.py; acquisition/arxiv/"),
            ("Govern network execution", "Keep ANTIEK_HYDRATE_LIVE_ARXIV plus an installed injector as dual authority and apply the existing host-scoped rate governor.", "Env-off and env-on-without-injector perform zero requests; redirects and rate limits retain host policy.", "substrate/engagement_spine/hydrate_live_wiring.py; interfaces/research/api/app.py"),
            ("Land and reopen HTML", "Route acquired bytes through canonical hosted-document extraction, preserving arXiv ID, URL, content digest, conversion receipt, and owner binding.", "The browser reopens one canonical HTML document; no PDF viewer is introduced and every claim-to-source hop remains resolvable.", "interfaces/research/api/engagement_routes.py; acquisition/documents/; apps/reading/src/"),
        ],
        "rigor": {
            "1 · Intellectual honesty": "Do not call an Atom title and abstract a hydrated paper body. Record metadata-only, body-complete, and body-unavailable as different L1 outcomes.",
            "2 · Fairness": "Steelman direct PDF rendering for fidelity, then reject it only because Antiek requires canonical agent-editable HTML; preserve the original PDF/source URL for audit and accessibility alternatives.",
            "3 · Rigor": "Red-prove zero network for every missing gate, then test redirects, 429/backoff, oversized bodies, malformed XML, and a successful HTML reopen with exact provenance.",
            "4 · Diligence": "Read the existing arXiv rate governor, T1 storage decisions, hydrate adapter, and canonical ingest path before adding any fetch or conversion code.",
            "5 · Defensibility": "Persist the exact network policy, source URL, body classification, digest, and conversion receipt so an operator can reconstruct why L1 was marked live.",
        },
        "gates": "pytest -q tests/test_hydrate_arxiv_adapter.py tests/test_hydrate_live_wiring.py tests/test_engagement_hydrate_boot_wiring.py tests/test_acquisition_arxiv.py; operator smoke is NOT RUN until approved",
        "pattern": "adversarial-verification",
        "lenses": "metadata-as-body false green; network gate and provenance bypass",
    },
    {
        "id": "LIG-SPR-02",
        "slug": "substack-acquisition",
        "title": "L2 · policy-injected Substack acquisition",
        "wave": "1",
        "goal": "Acquire an explicitly supplied Substack post through an operator-owned, ToS-reviewed factory and land it as canonical HTML without creating a crawler.",
        "deps": "Operator-approved fetch factory and policy; existing publication reference and hydrate-ref contracts.",
        "out": "No discovery crawl, login/paywall bypass, cookie capture, newsletter mirroring, or generic web scraper hidden behind a Substack name.",
        "milestones": [
            ("Freeze the injected boundary", "Define the fetch factory response, redirect allowlist, body limit, canonical URL, and typed refusal states.", "The default contains no concrete network client and env-only enablement remains incapable of I/O.", "substrate/engagement_spine/hydrate_live_wiring.py; hydrate_adapters.py"),
            ("Enforce publication policy", "Require a user-supplied post URL, reject non-Substack hosts and paywall/auth challenges, and retain the final canonical URL.", "Host confusion, redirect escape, paywall, oversized, and malformed responses fail closed with zero asset write.", "interfaces/research/api/engagement_routes.py; tests/test_hydrate_substack_adapter.py"),
            ("Project canonical HTML", "Sanitize the permitted article body, preserve title/author/date/source receipts, and host it through the shared document service.", "A successful fixture reopens as script-free HTML and carries source plus conversion provenance into twins and research context.", "acquisition/documents/; interfaces/research/api/hosted_document_routes.py; apps/reading/src/components/engagement/"),
        ],
        "rigor": {
            "1 · Intellectual honesty": "An environment flag is not a ToS decision and must never make L2 ready by itself. Readiness requires the operator-supplied factory and a successful governed receipt.",
            "2 · Fairness": "Name the publication owner and subscriber as affected stakeholders; a convenient scrape is rejected when it defeats access controls or republishes a paid body.",
            "3 · Rigor": "Test redirect escape, HTML script removal, paywall/auth responses, body caps, factory exceptions, and exact zero-write behavior before the happy path.",
            "4 · Diligence": "Reuse the source firewall, URL gate, sanitizer, and canonical host service. Do not add a second URL policy or document store for newsletters.",
            "5 · Defensibility": "The handoff must identify who approved the fetch policy, which factory was injected, its rollback switch, and which response evidence proved a body was legitimately acquired.",
        },
        "gates": "pytest -q tests/test_hydrate_substack_adapter.py tests/test_engagement_hydrate.py tests/test_engagement_hydrate_live_status.py; operator policy smoke is NOT RUN until approved",
        "pattern": "adversarial-verification",
        "lenses": "ToS/paywall boundary escape; sanitization and canonical-URL provenance",
    },
    {
        "id": "LIG-SPR-03",
        "slug": "twin-seed",
        "title": "L3 · live recursive twin-note seed",
        "wave": "1",
        "goal": "Generate evidence-bound insight and question twins through the real dispatch boundary while retaining an offline-honest fallback and selective promotion.",
        "deps": "ANTIEK_TWIN_SEED_LIVE and ANTIEK_TWIN_SEED_USE_DISPATCH; registered note-taker role; operator budget acceptance.",
        "out": "No automatic graph promotion, raw private corpus leakage, invented source body, or replacement of user-authored twin notes.",
        "milestones": [
            ("Bind canonical input", "Resolve the owner-readable canonical HTML asset and provenance before dispatch; caller-supplied labels cannot become source truth.", "Missing, gated, or metadata-only bodies skip honestly and perform zero model calls.", "substrate/engagement_spine/twin_seed_live_wiring.py; canonical_context.py"),
            ("Dispatch and validate", "Call the note-taker role with a bounded source envelope, explicit prompt budget, model receipt, and a closed insight/question output schema.", "Malformed kinds, empty text, over-limit output, provider mismatch, and dispatch failure produce no promoted units.", "substrate/engagement_spine/twin.py; substrate/dispatch/"),
            ("Persist without auto-promote", "Store seed units with source/model/prompt-version provenance and expose offline/live truth across every twin mount.", "Reading and research surfaces show the same seed state; promotion remains a separate explicit user action.", "interfaces/research/api/engagement_routes.py; apps/reading/src/components/engagement/TwinNotesPanel.tsx"),
        ],
        "rigor": {
            "1 · Intellectual honesty": "Set live_seed only after a validated model response is durably stored; an enabled flag, installed function, or attempted call is not a live twin result.",
            "2 · Fairness": "Preserve user notes and offline deterministic seeds as first-class alternatives. Live LLM output may propose insights, but it cannot silently overwrite or outrank the operator's thinking.",
            "3 · Rigor": "Mutation-test removal of source text, model receipt, and promotion separation. Each mutation must turn the live-complete assertion red.",
            "4 · Diligence": "Inventory every TwinNotesPanel mount and the canonical recursive prompt-context implementation before changing the seed payload; parity is a product invariant.",
            "5 · Defensibility": "Persist source asset ID, content digest, prompt version, provider/model identity, cost receipt, and each accepted/rejected unit reason for later benchmark learning.",
        },
        "gates": "pytest -q tests/test_twin_seed_live.py tests/test_twin_seed_live_wiring.py tests/test_engagement_twin_seed_live_status.py tests/test_seed_twins_hydrate.py; focused TwinNotesPanel vitest",
        "pattern": "perspective-diverse-verify",
        "lenses": "private/source provenance leakage; automatic-promotion authority creep",
    },
    {
        "id": "LIG-SPR-04",
        "slug": "midnight-oil-live-step",
        "title": "L4 · production Midnight Oil paid step",
        "wave": "2",
        "goal": "Enable one provider-backed Midnight Oil step only through owner consent, a durable fenced lease, reserve-before-spend, and provider idempotency evidence.",
        "deps": "Existing production runtime and worker launcher; verified provider idempotency contract; operator-approved plan resolver and ceiling.",
        "out": "No conversion of the synthetic execute endpoint, provider without idempotency guarantees, external retrieval without canonical receipts, or unattended production enablement.",
        "milestones": [
            ("Verify provider capability", "Prove the selected provider honors the stable Idempotency-Key and returns observed cost; unsupported providers fail before network I/O.", "A duplicate operation/step key produces one billable effect in an injected provider contract test.", "substrate/midnight_oil/live.py; substrate/dispatch/providers/"),
            ("Compose the server plan", "Resolve and sign route, pricing, byte/output caps, source policy, ceiling, and config hash before issuing owner-bound consent.", "Any drift or unsupported source policy prevents lease creation and performs zero provider/retrieval calls.", "substrate/midnight_oil/runtime.py; interfaces/research/api/midnight_oil_runtime.py"),
            ("Run and reconcile", "Exercise the deployed worker path through return checkpoint, settlement, terminalization, deposit, restart, and unknown-outcome quarantine.", "Crash matrices never replay a possibly billed step; exact evidence rehydrates the HTML/twin deposit after restart.", "substrate/midnight_oil/worker_cli.py; runtime/deployment/systemd/"),
        ],
        "rigor": {
            "1 · Intellectual honesty": "A generic OpenAI-compatible header is not proof of provider idempotency. Keep L4 unavailable until the exact endpoint contract and duplicate-key behavior are verified.",
            "2 · Fairness": "Steelman post-call debit for simplicity, then reject it because it transfers overshoot and ambiguous-billing risk to the operator. Reserve-before-spend remains the sole budget authority.",
            "3 · Rigor": "Run stale lease, config drift, cap refusal, timeout, lost response, return-then-crash, settlement-then-crash, and deposit-then-crash matrices with exact provider call counts.",
            "4 · Diligence": "Use the production worker CLI and systemd composition already present; never validate L4 only through the permanent synthetic oracle.",
            "5 · Defensibility": "Retain consent, lease generation, idempotency key, projected hold, observed settlement, checkpoint, and deposit effect receipts so every paid transition is reconstructable.",
        },
        "gates": "pytest -q tests/test_midnight_oil_authorized_e2e.py tests/test_midnight_oil_runtime.py tests/test_midnight_oil_live_step.py; provider capability smoke is operator-only and NOT RUN by default",
        "pattern": "perspective-diverse-verify",
        "lenses": "double-bill/unknown-outcome replay; consent/config/source-policy bypass",
    },
    {
        "id": "LIG-SPR-05",
        "slug": "digital-book-payment",
        "title": "L5 · entitled digital-book payment and port",
        "wave": "2",
        "goal": "Turn an operator-approved checkout into a confirmed entitlement, bounded acquired file, canonical HTML document, and owner library membership without weakening the manual-receipt fallback.",
        "deps": "Operator product/legal selection of payment and delivery partners; durable HostStore; existing deferred payment adapter and file-port path.",
        "out": "No card storage, invented zero-price entitlement, DRM circumvention, retailer credential automation, redistribution right, or PDF human view.",
        "milestones": [
            ("Ratify entitlement authority", "Specify signed webhook/session verification, amount/currency/title binding, replay identity, refund/revocation semantics, and the opaque manual-receipt fallback.", "Unconfirmed, mismatched, replayed, refunded, or foreign-owner receipts host nothing and create no library membership.", "substrate/marketplace_host/payment_adapter.py; docs/decisions/"),
            ("Acquire the purchased asset", "Accept only the approved delivery mechanism, validate content type/size/digest, and preserve rights plus receipt evidence before extraction.", "A payment confirmation without bytes remains pending; corrupt, oversized, or unsupported files never become served books.", "interfaces/research/api/marketplace_host_routes.py; acquisition/documents/"),
            ("Port and recover", "Convert the acquired file to canonical HTML, persist document/receipt/membership atomically, and prove backup/restore plus owner isolation.", "Restart and disaster recovery retain purchased=false/free=false truth, entitlement, projection receipt, and the same hosted identity.", "substrate/marketplace_host/; runtime/deployment/backup/"),
        ],
        "rigor": {
            "1 · Intellectual honesty": "A successful checkout is not a downloaded book, and a downloaded book is not automatically redistributable. Surface payment, acquisition, extraction, and servability as distinct states.",
            "2 · Fairness": "Protect the buyer from double charge and lost access while preserving publisher rights and refund/revocation semantics; neither stakeholder's evidence may be silently discarded.",
            "3 · Rigor": "Red-prove replay, owner swap, amount/title mismatch, refund, missing bytes, malicious archive, failed extraction, commit crash, and restore from an older generation.",
            "4 · Diligence": "Compose the durable HostStore and canonical ingest already shipped. A payment adapter must not create a second library, receipt store, or HTML projection pipeline.",
            "5 · Defensibility": "Record the operator-ratified provider/legal decision and reversal conditions beside the adapter; retain opaque upstream IDs without storing card data or provider secrets.",
        },
        "gates": "pytest -q tests/test_marketplace_payment_adapter_akr.py tests/test_marketplace_purchase_payment_path_aku.py tests/test_marketplace_host.py tests/test_marketplace_host_store.py; live checkout is NOT RUN until operator ratification",
        "pattern": "perspective-diverse-verify",
        "lenses": "entitlement/replay/refund correctness; acquired-file and recovery data loss",
    },
    {
        "id": "LIG-SPR-06",
        "slug": "collective-council",
        "title": "L6 · budgeted live collective council",
        "wave": "2",
        "goal": "Run selected research sessions as one explicitly prompted, budget-reserved council whose evidence returns to the existing offline merge, draft, twin, and graph substrate.",
        "deps": "Operator-approved council models and ceiling; completed spawn identities; existing collective merge and model-control authority.",
        "out": "No silent fan-out from selection alone, NotDiamond dispatch authority, auto-merge into a source asset, auto-promotion, or loss of the offline cohesive-unit fallback.",
        "milestones": [
            ("Freeze council input", "Resolve selected spawn IDs, owner, evidence packs, shared prompt, model choices, and an immutable preflight cost envelope.", "Foreign, incomplete, missing-evidence, duplicate, or over-budget selections perform zero model calls.", "substrate/floating_session/; substrate/engagement_spine/"),
            ("Execute bounded roles", "Reserve the council ceiling before fan-out, run explicit member roles with per-call receipts, and halt new work when remaining reserve cannot cover the next call.", "Concurrency cannot exceed the approved envelope; failures remain attributed and do not disappear behind a successful synthesizer.", "substrate/engagement_spine/collective.py; substrate/model_registration/"),
            ("Converge through one merge path", "Synthesize claims against member evidence, then reuse collective_unit_prompt, draft_combined/into_parent, twin seed, and explicit promotion choices.", "The result is canonical HTML with claim/source/member receipts; offline merge remains selectable and no output auto-commits.", "interfaces/research/api/engagement_routes.py; apps/reading/src/components/engagement/CollectiveResearchPanel.tsx"),
        ],
        "rigor": {
            "1 · Intellectual honesty": "Do not label an offline concatenation a live council or hide failed members behind the final synthesis. Member status, cost, and evidence contribution remain visible.",
            "2 · Fairness": "Give the operator a cheap offline cohesive-unit path and an explicit live price before fire; a richer council may not silently consume the budget because multiple sessions were selected.",
            "3 · Rigor": "Test foreign members, duplicate selection, partial member failure, concurrent halt, synthesizer failure, citation mismatch, and draft-versus-parent merge choice with exact call and reserve counts.",
            "4 · Diligence": "Reuse collective merge, research artifacts, decision-tree model selection, and Midnight Oil budget primitives where their authority matches; document any boundary that cannot be shared.",
            "5 · Defensibility": "Persist council membership, role/model plan, approved ceiling, member receipts, merge mode, citations, and user promotion decisions so the written analysis can be replayed and audited.",
        },
        "gates": "pytest -q tests/test_collective_research.py tests/test_collective_merge_usage_oi.py; focused CollectiveResearchPanel and SpawnMergePanel vitest; live council smoke is operator-only",
        "pattern": "perspective-diverse-verify",
        "lenses": "fan-out budget overshoot; evidence loss and unauthorized auto-merge",
    },
    {
        "id": "LIG-SPR-07",
        "slug": "notdiamond-advisory",
        "title": "L7 · NotDiamond advisory boundary",
        "wave": "1",
        "goal": "Keep NotDiamond useful as privacy-bounded comparative evidence while making authoritative or silent dispatch structurally impossible.",
        "deps": "Existing Antiek-bench shadow and operator decision-tree; no live credentials required for the authority proof.",
        "out": "No automatic routing, driver install, hidden cost projection, required external dependency, or custom-router promotion without a new operator decision.",
        "milestones": [
            ("Prove structural inertness", "Maintain a closed recommendation shape and forbidden-import boundary against dispatch, driver installation, and model-selection mutators.", "AST/import tests show no path from NotDiamond output to a provider call or active driver mutation.", "substrate/antiek_bench/live/nd_shadow.py; tests/test_antiek_bench_nd_shadow.py"),
            ("Present measured advice", "Compare shadow recommendation with operator choice and task-class benchmark evidence, including cost, availability, sample size, and disagreement.", "Missing or weak evidence renders NOT MEASURED; agreement is never labeled correctness.", "apps/reading/src/modes/Settings/; substrate/antiek_bench/"),
            ("Require explicit use", "If assisted selection is later approved, specify a per-prompt Use suggestion action that re-runs normal budget projection and retains manual override.", "No recommendation changes routing without a user action and the existing dispatch authority path.", "docs/htmlspec/notdiamond-verdict/VERDICT.md; substrate/model_registration/"),
        ],
        "rigor": {
            "1 · Intellectual honesty": "Call NotDiamond a shadow advisor, not a router integration. Distinguish recommendation availability from evidence that the recommended model would have produced an acceptable answer.",
            "2 · Fairness": "Show operator choice, Antiek-bench, and NotDiamond with the same task and evidence labels; do not privilege the vendor merely because its suggestion is external.",
            "3 · Rigor": "Use forbidden-import and registry-snapshot tests to prove inertness. UI copy saying advisory is insufficient if an indirect mutation path exists.",
            "4 · Diligence": "Read the measured-wedge and judged-scoring decisions before changing thresholds; do not resurrect the deleted campaign brief or parallel model router.",
            "5 · Defensibility": "Any reconsideration must cite complete judged weeks, sample sizes, availability, disagreement, cost improvement, and an explicit operator policy change; thresholds only permit review.",
        },
        "gates": "pytest -q tests/test_antiek_bench_nd_shadow.py tests/test_notdiamond_advisory_settings.py tests/test_antiek_bench_weekly_verdict.py; static forbidden-import gate",
        "pattern": "adversarial-verification",
        "lenses": "indirect routing authority; unmeasured recommendation presented as quality",
    },
]


def sprint_page(sprint: dict[str, object]) -> str:
    body = f"""
<header class="hero"><p class="eyebrow"><a href="index.html">&larr; Live integration gates</a> · {esc(sprint['id'])}</p>
<h1>{esc(sprint['title'])}</h1><p class="tagline">{esc(sprint['goal'])}</p><div class="meta-row">
<span class="tag tag--blue">Wave {esc(sprint['wave'])}</span><span class="tag tag--yellow">Status: operator-gated</span>
<span class="tag tag--grey">3 milestones</span><span class="tag tag--grey">Owner: future executing agent</span></div></header>
<section class="block"><h2>Parent context</h2><p>Antiek already ships the offline product loop for this capability. This sprint is the cold-executable contract for crossing one live boundary without duplicating that substrate or rounding an enable flag up to a working product.</p><p>All live work remains operator-controlled. Default and CI behavior stays offline, every network or paid effect needs two independent authorities, and human-viewable output remains canonical HTML.</p><div class="callout callout--info"><strong>Position:</strong> {esc(sprint['id'])} is one independent gate in the L1-L7 map; it does not authorize another gate.</div></section>
<section class="block"><h2>Goal</h2><p><strong>{esc(sprint['goal'])}</strong></p></section>
<section class="block"><h2>Technical milestones</h2>{milestones(sprint['milestones'])}</section>
<section class="block"><h2>Rigor — operating manual for this sprint</h2><div class="rigor">{rigor(sprint['rigor'])}</div></section>
<section class="block"><h2>Dependencies</h2><p>{esc(sprint['deps'])}</p></section>
<section class="block"><h2>Out of scope</h2><p>{esc(sprint['out'])}</p></section>
<section class="block"><h2>Verification gates</h2><pre><code>{esc(sprint['gates'])}</code></pre><p>Record exact exits and counts. Operator-only or paid smoke stays <strong>NOT RUN</strong> until explicitly authorized.</p></section>
<section class="block"><h2>Handoff packet</h2><ul><li>Commit SHA and exact files/authority boundaries changed.</li><li>Every gate command with count and NOT RUN reason.</li><li>Offline, missing-authority, live-success, rollback, and adverse-path receipts.</li><li>Operator decision or external contract still required.</li><li>Any divergence from this sprint and what would reverse it.</li></ul></section>
<section class="block" id="harness-hint" data-harness-pattern="{esc(sprint['pattern'])}" data-harness-fanout-unit="one builder in an isolated worktree" data-harness-verifier-lenses="{esc(sprint['lenses'])}" data-harness-rounds-floor="2" data-harness-rounds-cap="6"><h2>Execution harness hint</h2><p><code>{esc(sprint['pattern'])}</code> · verifier lenses: {esc(sprint['lenses'])}</p><p>Irreversible enablement, spend, deployment, merge, and operator decisions remain in the primary orchestrator.</p></section>
<footer class="spec-footer">{esc(sprint['id'])} · generated {GENERATED} · source: research-reading-spine handoff, canonical decisions, and deleted campaign archaeology</footer>"""
    return shell(f"{sprint['id']} · {sprint['title']}", body)


def master_page() -> str:
    cards = "".join(
        f'<a class="sprint-card" href="sprint-{index:02d}-{sprint["slug"]}.html"><span class="id">{esc(sprint["id"])}</span><span class="title">{esc(sprint["title"])}</span><span class="goal">{esc(sprint["goal"])}</span><span class="footer"><span class="tag tag--blue">Wave {esc(sprint["wave"])}</span><span class="tag tag--yellow">operator-gated</span></span></a>'
        for index, sprint in enumerate(SPRINTS, 1)
    )
    body = f"""
<header class="hero"><p class="eyebrow">Master spec · ANT-LIG</p><h1>Live integration gates</h1>
<p class="tagline">Cold-executable contracts for the remaining L1-L6 live boundaries, plus the L7 authority rejection.</p><div class="meta-row"><span class="tag tag--blue">Status: executable when gate authority exists</span><span class="tag tag--yellow">Owner: Antiek operator</span><span class="tag tag--grey">7 sprints · 2 waves</span><span class="tag tag--grey">{GENERATED}</span></div></header>
<section id="spec-lineage" class="block" data-spec-depth="0" data-parent-spec=""><h2>Spec lineage</h2><p>Root durable replacement for generated campaign briefs intentionally removed by <code>bc71bf4753</code>. It refines <a href="../../decisions/research-reading-spine-handoff.md">the research-reading spine handoff</a>, <a href="../competitive-deep-research/index.html">competitive deep research</a>, <a href="../midnight-oil/index.html">Midnight Oil</a>, <a href="../marketplace-host/index.html">marketplace hosting</a>, and <a href="../notdiamond-verdict/VERDICT.md">the NotDiamond verdict</a>.</p><ul class="child-specs"></ul></section>
<section class="block" id="competitive-quality"><h2>Goal</h2><p>Give every live/deferred link in the product a durable destination whose acceptance criteria are precise enough for a future agent to execute without the deleted campaign ledger. Success means each live capability has one authority boundary, an offline default, zero-effect missing-gate proofs, exact provenance, rollback, and an operator-visible NOT RUN state.</p><h3>Failure mode to avoid</h3><p>Adding more readiness chrome, adapters, or generated notes while no real product entry crosses the boundary—or enabling a paid/network effect because an environment flag exists.</p></section>
<section class="block"><h2>Architecture overview</h2><div class="dep-graph">operator decision + environment gate + process injector\n                         │\n                         ▼\n              preflight / zero-effect refusal\n                         │\n        reserve or policy authorization\n                         │\n                         ▼\n                one canonical live effect\n                         │\n                         ▼\n       receipt → canonical HTML → twin/context\n                         │\n                         ▼\n             explicit user merge/promotion</div><h3>Shared invariants</h3><ul><li>Environment state alone never authorizes network, spend, entitlement, model dispatch, merge, or promotion.</li><li>Every human-viewable artifact is canonical HTML; source PDFs/files remain provenance-bearing ingest inputs.</li><li>NotDiamond and Antiek-bench remain advisory; operator model choice and visible budget projection retain authority.</li><li>Paid/live/prod proof is RUN or NOT RUN, never inferred from fixtures.</li></ul></section>
<section class="block"><h2>Sprint roster</h2><p class="lede">Wave 1 contracts can execute independently. Wave 2 requires production/provider/product authority in addition to the shipped offline substrate.</p><div class="sprint-grid">{cards}</div></section>
<section class="block"><h2>Decision log</h2><table class="spec"><thead><tr><th>Decision</th><th>Why</th><th>Reconsider if</th></tr></thead><tbody><tr><td>One durable htmlspec replaces campaign links</td><td><code>docs/campaigns</code> is intentionally forbidden orchestration scratch, while product links need stable execution contracts.</td><td>The repository adopts a versioned documentation router with equivalent reachability gates.</td></tr><tr><td>Seven authority gates, not one global LIVE flag</td><td>Network policy, model spend, payment entitlement, and routing authority are different risks and need different proofs.</td><td>Never; shared UI may aggregate status but cannot collapse authority.</td></tr><tr><td>L7 is a rejection sprint</td><td>NotDiamond may advise but cannot silently own dispatch or hide budget choice.</td><td>Only an explicit operator policy change after complete judged evidence.</td></tr></tbody></table></section>
<section class="block"><h2>Rejected alternatives</h2><table class="spec"><thead><tr><th>Alternative</th><th>Why rejected</th><th>Reconsider if</th></tr></thead><tbody><tr><td>Restore deleted campaign briefs</td><td>They mix durable conclusions with residual letters and generated run state; the repository has an explicit gate forbidding that tree.</td><td>Never while <code>campaign_artifact_check</code> is policy.</td></tr><tr><td>Point every link at the handoff</td><td>The handoff names gates but is not a cold-executable operating manual for each integration.</td><td>Each gate gains equivalent milestones, tests, rollback, and five-values rigor there.</td></tr><tr><td>Implement the easiest live adapter now</td><td>An adapter without operator policy/provider/legal authority would be fixture-green fake progress.</td><td>The relevant sprint dependency and operator authority are both present.</td></tr><tr><td>One global enable switch</td><td>It creates transitive authority across unrelated live effects and makes rollback unsafe.</td><td>Never; aggregate status may remain read-only.</td></tr></tbody></table></section>
<section class="block"><h2>Open questions</h2><table class="spec"><thead><tr><th>Question</th><th>Current assumption</th><th>Resolver</th></tr></thead><tbody><tr><td>Which Substack acquisition policy/factory is approved?</td><td>None; L2 remains zero-network.</td><td>Operator + legal/product review</td></tr><tr><td>Which payment and book-delivery partners are approved?</td><td>None; manual receipt remains canonical.</td><td>Operator + legal/product review</td></tr><tr><td>Which provider guarantees Midnight Oil idempotency?</td><td>No checked-in default is proven.</td><td>Operator + provider contract evidence</td></tr><tr><td>What live council composition earns its extra spend?</td><td>Offline cohesive merge remains default.</td><td>Operator + Antiek-bench judged evidence</td></tr></tbody></table></section>
<section class="block" id="harness-hint-run" data-harness-default-pattern="perspective-diverse-verify" data-harness-inline-only-sprints=""><h2>Execution harness hint</h2><p>Run only gates whose external dependencies are satisfied. Use one isolated builder plus gate-specific independent refuters; do not fan out multiple live gates under one authority decision. Require at least two sharpen rounds.</p></section>
<footer class="spec-footer">Generated by htmlspec · durable replacement for deleted campaign links · {GENERATED}</footer>"""
    return shell("Live integration gates — Master Spec", body, wide=True)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "index.html").write_text(master_page(), encoding="utf-8")
    for index, sprint in enumerate(SPRINTS, 1):
        (ROOT / f"sprint-{index:02d}-{sprint['slug']}.html").write_text(
            sprint_page(sprint), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
