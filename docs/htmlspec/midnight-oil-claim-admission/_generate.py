#!/usr/bin/env python3
"""Generate the ANT-MOCA executable htmlspec tree."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
STYLE_PATH = Path("/Users/slimydog/.agents/skills/htmlspec/templates/style.css")
DATE = "2026-07-13"
CSS = STYLE_PATH.read_text(encoding="utf-8")


def wrap(title: str, body: str, *, wide: bool = False) -> str:
    page = "page page--wide" if wide else "page"
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8" />\n<meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"<title>{title}</title>\n<style>\n{CSS}\n</style>\n</head>\n<body>\n"
        f'<main class="{page}">\n{body}\n</main>\n</body>\n</html>\n'
    )


def rigor(cards: tuple[str, str, str, str, str]) -> str:
    labels = (
        ("1 · Intellectual honesty", "Calibrate acceptance claims"),
        ("2 · Fairness", "Protect partial work without promoting it"),
        ("3 · Rigor", "Make refusal mechanically falsifiable"),
        ("4 · Diligence", "Trace the existing authority first"),
        ("5 · Defensibility", "Leave a reconstructable contract"),
    )
    rendered = "".join(
        f'<div class="rigor-card"><span class="label">{label}</span><h4>{title}</h4><p>{text}</p></div>'
        for (label, title), text in zip(labels, cards, strict=True)
    )
    return (
        '<section class="block"><h2>Rigor — operating manual for this sprint</h2>'
        '<p class="lede">Each card is anchored to this sprint’s files and failure modes.</p>'
        f'<div class="rigor">{rendered}</div></section>'
    )


def milestones(items: list[tuple[str, str, list[str], list[str]]]) -> str:
    rows: list[str] = []
    for index, (title, description, criteria, files) in enumerate(items, 1):
        checks = "".join(f"<li>{item}</li>" for item in criteria)
        paths = "".join(f'<span class="file">{path}</span>' for path in files)
        rows.append(
            f'<div class="milestone"><div class="num">{index}</div><div>'
            f'<div class="title">{title}</div><p class="desc">{description}</p>'
            f'<div class="criteria"><strong>Acceptance criteria</strong><ul>{checks}</ul></div>'
            f'<div class="files">{paths}</div></div></div>'
        )
    return (
        '<section class="block"><h2>Technical milestones</h2>'
        '<p class="lede">Execute in order; every milestone has a red proof and named files.</p>'
        + "".join(rows)
        + "</section>"
    )


def sprint(spec: dict[str, object]) -> str:
    sid = str(spec["sid"])
    deps = "".join(f"<li>{item}</li>" for item in spec["deps"]) or '<li class="muted">None</li>'
    external = "".join(f"<li>{item}</li>" for item in spec["external"])
    out = "".join(f"<li>{item}</li>" for item in spec["out"])
    gates = "".join(
        f"<tr><td><strong>{name}</strong></td><td><code>{command}</code></td><td>{expected}</td></tr>"
        for name, command, expected in spec["gates"]
    )
    harness = spec["harness"]
    body = f"""<header class="hero">
<p class="eyebrow"><a href="index.html">&larr; Midnight Oil claim admission</a> · {sid}</p>
<h1>{spec['title']}</h1><p class="tagline">{spec['tagline']}</p>
<div class="meta-row"><span class="tag tag--blue"><span class="dot"></span>Wave {spec['wave']}</span>
<span class="tag tag--yellow"><span class="dot"></span>Pending</span>
<span class="tag tag--grey">Budget: {len(spec['milestones'])} milestones</span>
<span class="tag tag--grey">Owner: serial sprint agent</span></div></header>
<section class="block"><h2>Parent context</h2><p>{spec['context1']}</p><p>{spec['context2']}</p>
<div class="callout callout--info"><strong>Position:</strong> {spec['position']}</div></section>
<section class="block"><h2>Goal</h2><p><strong>{spec['tagline']}</strong></p><p>{spec['goal']}</p></section>
{milestones(spec['milestones'])}
{rigor(spec['rigor'])}
<section class="block"><h2>Dependencies</h2><div class="two-col"><div><h3>Upstream sprints</h3><ul>{deps}</ul></div>
<div><h3>External systems &amp; configs</h3><ul>{external}</ul></div></div></section>
<section class="block"><h2>Out of scope</h2><ul>{out}</ul><div class="callout callout--warn"><strong>Scope stop:</strong> record tempting expansions in the handoff; do not implement them here.</div></section>
<section class="block"><h2>Verification gates</h2><table class="spec"><thead><tr><th>Gate</th><th>Command</th><th>Expected</th></tr></thead><tbody>{gates}</tbody></table></section>
<section class="block"><h2>Handoff packet</h2><pre><code>## {sid} — Handoff

### Status
done | blocked | partial — exact reason

### Files touched
- path:line — change and why

### Milestones
- [ ] M1 …

### Verification gates
- gate: pass | fail | NOT RUN (why)

### Decisions and reversers
- decision / rejected alternative / what would reverse it

### Assumptions and open questions
- assumption or question — resolver

### Next sprint can start when
- mechanically checkable condition
</code></pre></section>
<section class="block" id="harness-hint" data-harness-pattern="{harness[0]}"
 data-harness-fanout-unit="{harness[1]}" data-harness-verifier-lenses="{harness[2]}"
 data-harness-rounds-floor="{harness[3]}" data-harness-rounds-cap="{harness[4]}">
<h2>Execution harness hint</h2><p>Pattern <code>{harness[0]}</code>. {harness[1]}</p>
<ul><li>{harness[2].replace('|', '</li><li>')}</li></ul></section>
<footer class="spec-footer">{sid} · <a href="index.html">Back to master spec</a> · Generated {DATE}</footer>"""
    return wrap(f"{sid} · {spec['title']} — ANT-MOCA", body)


SPECS: list[dict[str, object]] = [
    {
        "sid": "SPR-01", "slug": "acceptance-contract", "title": "Research acceptance contract",
        "tagline": "Name and canonicalize the approval-time epistemic policy.", "wave": 1,
        "context1": "Midnight Oil already signs spend authority, route configuration, source policy, duration, and model selection. Those controls prove who authorized execution; they do not define which returned claims may become durable knowledge.",
        "context2": "The preceding admission patch removed fabricated fallback insights. This sprint defines the next authority without changing dispatch, deposit, or graph writes.",
        "position": "Foundation. All later schema and enforcement work consumes this canonical contract.",
        "goal": "Add the binding closed v1 acceptance policy to JobConsentConfig: insights and deliverable prose paragraphs require exact local evidence; exploratory questions may remain explicitly unverified and operational-only. The policy must be stable across processes and part of the existing consent hash.",
        "milestones": [
            ("Define the closed policy", "Add a versioned immutable policy rather than free-form knobs.", ["V1 gates every insight and every non-empty normalized output_text paragraph", "Exploratory questions are labeled unverified and never projected as supported assertions", "Unknown versions fail closed"], ["substrate/midnight_oil/contracts.py", "substrate/midnight_oil/spend_consent.py"]),
            ("Fix deterministic identity", "Normalize paragraphs, then derive IDs from UTF-8 canonical JSON with sorted keys, compact separators, ensure_ascii=False, and explicit domain/schema fields.", ["claim_id covers domain, schema_version, job_id, step_key, claim_class, ordinal, and normalized_text", "receipt_id covers domain, schema_version, document_id, chunk_id, hash_scope, content_hash, and canonical_url", "Display title and dictionary insertion order cannot change identity", "Delimiter-shaped input cannot collide"], ["substrate/midnight_oil/contracts.py", "docs/decisions/midnight-oil-claim-admission.md"]),
            ("Canonicalize policy identity", "Include policy fields in canonical hashing and approval receipts.", ["Changing one policy field changes the config hash", "Ordering does not change the hash"], ["substrate/midnight_oil/spend_consent.py", "tests/test_midnight_oil_spend_consent.py"]),
            ("Expose the launch brief", "Carry policy identity through preflight, packet, handoff, and applied receipt.", ["Round-trip tests cover every contract", "No provider call is needed"], ["substrate/midnight_oil/contracts.py", "tests/test_midnight_oil_contract.py"]),
            ("Record the decision", "Write the version/reverser, exact segmentation, claim-ID material, and migration posture.", ["V1 admits only locally canonical document/chunk/hash receipts", "Public-web receipts without a local canonical chunk remain operational-only", "Legacy rows remain legacy-unverified and are never auto-upgraded"], ["docs/decisions/midnight-oil-claim-admission.md"]),
        ],
        "rigor": (
            "Do not call a source-count threshold ‘grounding.’ The contract must state that per-claim coverage is required and label legacy or unsupported output unverified.",
            "Steelman permissive operational retention: partial work is valuable. Preserve it in HTML while keeping graph admission fail-closed.",
            "Prove canonical hash sensitivity field by field; a policy that can drift without hash drift is not approved authority.",
            "Read JobConsentConfig, preflight packets, and consent verification end-to-end before adding a second hash or receipt.",
            "The decision record must name policy version 1, every field, default, and the exact condition that would justify version 2.",
        ),
        "deps": [], "external": ["No live provider keys", "Existing spend-consent test keyring"],
        "out": ["Claim evidence schema", "Graph writes", "Frontend controls"],
        "gates": [("Contract", ".venv/bin/python -m pytest tests/test_midnight_oil_contract.py tests/test_midnight_oil_spend_consent.py -q", "all passed"), ("Types", ".venv/bin/mypy substrate/midnight_oil/contracts.py substrate/midnight_oil/spend_consent.py --no-error-summary", "exit 0")],
        "harness": ("inline", "Shared consent contract files require serial ownership.", "hash drift|closed-version refusal", "1", "4"),
    },
    {
        "sid": "SPR-02", "slug": "durable-authority", "title": "Durable policy authority",
        "tagline": "Bind the approved acceptance policy through queue, lease, and recovery.", "wave": 2,
        "context1": "SPR-01 defines the policy and places it in the signed configuration. Production authority is the owner job row plus queued operation payload, not the frontend receipt alone.",
        "context2": "A crash or restart must not silently fall back to a newer default policy. Drift is reconciliation-required, never dispatchable.",
        "position": "Authority track. Runs after SPR-01 and before SPR-03 because both touch worker/live authority boundaries.",
        "goal": "Persist the policy/version/hash through the API composition boundary, durable owner authority, and queue payload; require exact equality with JobConsentConfig, consent receipt, lease authority, and recovery state before any transition, hold, retrieval, or dispatch.",
        "milestones": [
            ("Compose exact authority", "Carry bounded policy data through create, consent reconstruction, claim, and enqueue into owner payload and queued options.", ["Owner payload, JobConsentConfig.canonical_hash(), consent receipt, and queue payload are exactly equal", "No state transition or hold precedes the equality check"], ["interfaces/research/api/midnight_oil_routes.py", "substrate/midnight_oil/job_store.py", "substrate/midnight_oil/operation_queue.py", "tests/test_midnight_oil_routes.py", "tests/test_midnight_oil_consent_routes.py", "tests/test_midnight_oil_enqueue_once.py"]),
            ("Fence lease acquisition", "Add policy equality to immutable job/authority/queue reconciliation.", ["Drift returns reconciliation-required before lease", "No budget hold or dispatch occurs"], ["substrate/midnight_oil/worker.py", "tests/test_midnight_oil_runtime.py"]),
            ("Fence live composition", "Recheck signed policy at the injected live boundary.", ["Config drift test performs zero retrieval and dispatch"], ["substrate/midnight_oil/live.py", "tests/test_midnight_oil_live.py"]),
            ("Prove restart behavior", "Round-trip and migrate durable stores without auto-upgrading epistemic authority.", ["Legacy rows remain operational-only", "Restart tests preserve exact policy identity"], ["tests/test_midnight_oil_durable_job_store.py", "tests/test_midnight_oil_runtime.py"]),
        ],
        "rigor": (
            "Report legacy rows as legacy-unverified; do not describe a defaulted policy as operator-approved.",
            "Steelman auto-upgrading old rows for convenience, then reject it because it fabricates consent the operator never signed.",
            "Every drift red proof must assert zero lease, zero hold, zero retrieval, and zero dispatch, not merely an error response.",
            "Trace owner CAS, operation queue, legacy job mirror, and live plan together; editing only one authority creates split brain.",
            "Handoff must list the canonical fields compared at lease time and the recovery state chosen for each mismatch.",
        ),
        "deps": ["SPR-01 — canonical policy and hash"], "external": ["Temporary DuckDB/SQLite stores only"],
        "out": ["Provider output parsing", "Graph admission", "UI copy"],
        "gates": [("Composition", ".venv/bin/python -m pytest tests/test_midnight_oil_routes.py tests/test_midnight_oil_consent_routes.py tests/test_midnight_oil_enqueue_once.py -q", "create→consent→claim→enqueue passed"), ("Authority", ".venv/bin/python -m pytest tests/test_midnight_oil_durable_job_store.py tests/test_midnight_oil_runtime.py -q", "restart and lease equality passed"), ("Live fence", ".venv/bin/python -m pytest tests/test_midnight_oil_live.py -q", "all passed")],
        "harness": ("inline", "CAS and lease invariants share authority files.", "split-brain authority|zero-side-effect drift", "1", "5"),
    },
    {
        "sid": "SPR-03", "slug": "claim-evidence", "title": "Claim-to-receipt evidence model",
        "tagline": "Represent which receipts support each returned claim or paragraph.", "wave": 3,
        "context1": "Step-level source receipts prove only that retrieval happened somewhere in a step. They cannot prove that every insight or paragraph is supported by every source.",
        "context2": "This sprint changes evidence representation and worker normalization only. It must preserve raw operational output for audit while refusing to invent mappings for legacy, offline, or malformed provider results.",
        "position": "Evidence track. Runs after SPR-02 so its worker/live edits consume the settled durable authority contract without collisions.",
        "goal": "Add stable claim identifiers and exact receipt references for insight, question, and prose claims, with bounded decoding, secret redaction, and explicit unverified state.",
        "milestones": [
            ("Define claim evidence", "Add immutable claim records keyed by the ratified canonical-JSON claim and receipt IDs.", ["Duplicate IDs and unknown receipt references reject", "Delimiter-shaped fields cannot collide", "Reordered receipt keys and changed title preserve receipt ID", "Questions may be explicitly exploratory rather than supported claims"], ["substrate/midnight_oil/job.py", "tests/test_midnight_oil_job.py"]),
            ("Normalize worker output", "Extend WorkerStepResult and _step_evidence without deriving citations from string similarity.", ["Secrets remain redacted", "Unmapped claims remain unverified"], ["substrate/midnight_oil/worker.py", "tests/test_midnight_oil.py"]),
            ("Emit live mappings", "Require the live synthesizer adapter to return structured claim mappings.", ["Malformed mappings fail the step before content completion", "No provider call in tests"], ["substrate/midnight_oil/live.py", "tests/test_midnight_oil_live.py"]),
            ("Round-trip recovery", "Persist mappings across durable store restart and replay.", ["Evidence hash includes mappings", "Old rows decode without invented coverage"], ["substrate/midnight_oil/job.py", "tests/test_midnight_oil_graph_projection.py"]),
        ],
        "rigor": (
            "An unmapped claim is unverified, not ‘implicitly supported’ by the step’s first receipt. Preserve that distinction in every serializer.",
            "Steelman sentence-similarity auto-linking for ease of migration, then reject it because probabilistic matching would manufacture provenance.",
            "Red proofs cover duplicate claim IDs, missing receipt IDs, mixed supported/unverified prose, whitespace, truncation, and secret-shaped strings.",
            "Read _step_evidence, live retrieval receipts, graph canonical evidence hashing, and old-row decoding before choosing identifiers.",
            "Implement the ratified canonical-JSON claim and receipt identity material exactly; display metadata must never enter authority or replay hashes.",
        ),
        "deps": ["SPR-01 — policy says which claim classes require coverage", "SPR-02 — settled worker/live authority boundaries"], "external": ["Injected fake retrieval and dispatch only"],
        "out": ["Consent persistence", "Graph write refusal", "Frontend policy control"],
        "gates": [("Evidence", ".venv/bin/python -m pytest tests/test_midnight_oil_job.py tests/test_midnight_oil.py tests/test_midnight_oil_live.py tests/test_midnight_oil_graph_projection.py -q", "duplicate/unknown receipt, delimiter collision, key order, display-title exclusion, legacy, paragraph, and replay proofs passed"), ("Types", ".venv/bin/mypy substrate/midnight_oil/job.py substrate/midnight_oil/worker.py substrate/midnight_oil/live.py --no-error-summary", "exit 0")],
        "harness": ("inline", "Job and worker evidence schema are tightly coupled.", "invented mapping|replay hash stability", "1", "5"),
    },
    {
        "sid": "SPR-04", "slug": "graph-admission", "title": "Fail-closed graph admission",
        "tagline": "Preflight verified claim coverage before the first DuckDB write.", "wave": 4,
        "context1": "Operational HTML deposit may retain partial or unsupported work honestly. The durable depth graph is a stronger epistemic surface and must admit only claims covered under the approved policy.",
        "context2": "Graph projection currently begins inserting a deliverable before it evaluates each source receipt. This sprint adds a read-only full preflight and preserves deterministic replay semantics.",
        "position": "Convergence gate. Requires both durable authority and claim evidence.",
        "goal": "Verify non-DuckDB policy, claim structure, and artifact identity before locking; then acquire the existing exclusive writer context and revalidate every DuckDB-resident authority input plus every deterministic output row through that same connection before its first mutating SQL. The graph schema must already be initialized. Refusal creates zero protected-graph/event delta and no effect receipt.",
        "milestones": [
            ("Build a read-only verifier", "Return a typed admission result with covered, unverified, invalid, and exploratory claims.", ["No DuckDB writes", "Reason codes are closed and bounded"], ["substrate/midnight_oil/claim_admission.py", "tests/test_midnight_oil_claim_admission.py"]),
            ("Validate canonical receipts under the writer flock", "After connect_write, revalidate document/chunk association, current chunk text/hash, receipt identity, and local authority through that connection before mutation; v1 keeps external receipts operational-only.", ["Hash mismatch or a changed/deleted chunk refuses the claim", "External receipts never receive fake local foreign keys or graph admission", "No DuckDB-resident authority check is trusted from the unlocked phase"], ["substrate/midnight_oil/claim_admission.py", "substrate/midnight_oil/graph_projection.py", "tests/test_midnight_oil_graph_projection.py"]),
            ("Census deterministic conflicts under the writer flock", "Precompute expected rows, acquire connect_write once, then revalidate every DuckDB-resident authority input and compare every existing deliverable, section, node, and edge before the first mutating SQL; never call ensure_initialized inside projection.", ["Independent conflict fixtures cover every output row class", "Conflict refusal leaves pre-existing rows byte-equivalent", "Barrier tests change/delete a chunk before lock acquisition and attempt a concurrent write after acquisition; neither can create stale admission or interleave"], ["substrate/midnight_oil/claim_admission.py", "substrate/midnight_oil/graph_projection.py", "tests/test_midnight_oil_graph_projection.py"]),
            ("Preflight graph projection", "Complete non-DuckDB verification before lock acquisition, then complete all DuckDB authority and conflict SELECTs under the exclusive lock before deterministic inserts.", ["Any refusal causes zero protected graph-row delta and zero typed event-file delta", "No new effect receipt is checkpointed", "Best-effort write_log observability is not misreported as a graph effect"], ["substrate/midnight_oil/graph_projection.py", "tests/test_midnight_oil_graph_projection.py"]),
            ("Project only admitted claims", "Write exact claim-to-source edges; omit exploratory-question nodes and edges entirely in v1.", ["No null-attributed insight edge", "No exploratory-question graph row", "Receipt replay is byte-identical"], ["substrate/midnight_oil/graph_projection.py", "tests/test_midnight_oil_graph_projection.py"]),
            ("Own durable recovery state", "Extend MidnightOilJob and DurableJobStore round trips with refused plus the closed reason table while preserving operational deposit.", ["internal_local_chunk_temporarily_missing, operational_artifact_pending, and graph_lock_unavailable remain retryable pending", "policy_authority_drift, legacy_unverified, claim_coverage_missing, receipt_malformed_or_forged, external_receipt_not_admissible_v1, and deterministic_row_conflict are durable refused", "Worker CLI reports the typed reason without redispatch"], ["substrate/midnight_oil/job.py", "substrate/midnight_oil/durable_job.py", "substrate/midnight_oil/worker_cli.py", "tests/test_midnight_oil_job.py", "tests/test_midnight_oil_graph_projection.py", "tests/test_midnight_oil_runtime.py"]),
        ],
        "rigor": (
            "Do not report a successful graph projection because operational HTML exists. Admission success requires every policy-covered claim to pass before the first write.",
            "Steelman partial graph projection, then reject it because deterministic replay cannot safely distinguish an accepted subset from a crash-truncated write.",
            "Use before/after row counts, row bytes, and event-file digests for every refusal reason; absolute zero is wrong when a conflict fixture intentionally pre-exists.",
            "Read graph_projection.py, connect_write’s flock lifetime, deterministic IDs, conflict rechecks, and the effect-receipt checkpoint before moving any code across the write boundary.",
            "The handoff must map each refusal code to operator-visible recovery and state whether redispatch is forbidden, optional, or required.",
        ),
        "deps": ["SPR-02 — durable policy authority", "SPR-03 — claim-to-receipt mapping"], "external": ["Temporary DuckDB graph", "No network or provider calls"],
        "out": ["Automatic promotion of legacy rows", "Changing engagement deposit semantics", "Write citation gate"],
        "gates": [("Admission", ".venv/bin/python -m pytest tests/test_midnight_oil_claim_admission.py tests/test_midnight_oil_graph_projection.py tests/test_midnight_oil_job.py -q", "admission and DurableJobStore restart proofs passed"), ("No-write", ".venv/bin/python -m pytest tests/test_midnight_oil_graph_projection.py -k 'refus or no_write or conflict or concurrent' -q", "zero-delta, unchanged-conflict, and lock-barrier proofs passed")],
        "harness": ("adversarial-verification", "One builder; independent verifier attempts partial-write and forged-coverage attacks.", "zero-write refusal|receipt forgery|replay equivalence", "2", "6"),
    },
    {
        "sid": "SPR-05", "slug": "launch-surface", "title": "Launch brief and admission status",
        "tagline": "Make the approved research brief and graph-admission outcome visible.", "wave": 5,
        "context1": "The operator chooses goals, duration, budget, model, and source policy in the Midnight Oil surface. The new acceptance policy is meaningful only if it is visible before approval and immutable afterward.",
        "context2": "Operational deposits must remain readable even when graph admission refuses them. The UI must distinguish no-result, unverified operational output, graph-admitted knowledge, and reconciliation-required authority drift.",
        "position": "Product closure after backend authority and enforcement are stable.",
        "goal": "Add a concise research-acceptance summary to create/approve flows and display typed admission outcomes without implying that operational retention equals verified knowledge.",
        "milestones": [
            ("Extend API contracts", "Expose policy/version/hash and typed admission state.", ["TypeScript mirrors closed backend enums", "Unknown values render honest fallback"], ["apps/reading/src/api/midnightOil.ts", "interfaces/research/api/midnight_oil_routes.py"]),
            ("Render approval brief", "Show coverage rule beside source policy and price ceiling before approval.", ["Approval request includes exact policy version", "Post-approval controls are read-only"], ["apps/reading/src/modes/MidnightOil/index.tsx", "apps/reading/src/modes/MidnightOil/MidnightOil.test.tsx"]),
            ("Render terminal admission", "Separate operational artifact link from graph-admission state and reason.", ["Unverified does not use success copy", "Refusal preserves reopen/download of HTML"], ["apps/reading/src/modes/MidnightOil/index.tsx", "apps/reading/src/modes/MidnightOil/MidnightOil.test.tsx"]),
            ("Close route proofs", "Verify create, consent, run, deposit, and recovery response parity.", ["Backend/frontend contract tests pass", "No live smoke claimed"], ["tests/test_midnight_oil_routes.py", "apps/reading/src/api/midnightOil.test.ts"]),
        ],
        "rigor": (
            "Do not use ‘verified’ for a retained HTML artifact whose graph admission is pending or refused. Copy must name the exact state.",
            "Steelman hiding policy detail to simplify the launch form; reject it because the operator cannot consent to an invisible epistemic rule.",
            "Component tests must cover policy drift, legacy-unverified, receipt-only, no-result, admitted, and refused states with exact machine attributes.",
            "Reuse the existing budget/approval chokepoint and API client; do not create a parallel launch modal or browser-only policy state.",
            "Record the final operator copy and enum mapping in the decision doc so backend and frontend cannot independently rename states.",
        ),
        "deps": ["SPR-02 — policy available on API authority", "SPR-04 — typed admission outcomes"], "external": ["Vitest/jsdom", "No browser network"],
        "out": ["Live provider smoke", "Automatic retry", "Settings-wide policy presets"],
        "gates": [("Frontend", "cd apps/reading && npm test -- --run src/api/midnightOil.test.ts src/modes/MidnightOil/MidnightOil.test.tsx", "all passed"), ("Types", "cd apps/reading && npm run typecheck", "exit 0"), ("Routes", ".venv/bin/python -m pytest tests/test_midnight_oil_routes.py tests/test_midnight_oil_consent_routes.py -q", "all passed")],
        "harness": ("inline", "API and one product surface share the launch contract.", "copy truthfulness|backend-frontend enum parity", "1", "4"),
    },
]


def master() -> str:
    cards = "".join(
        f'<a class="sprint-card" href="sprint-{str(item["sid"])[4:]}-{item["slug"]}.html">'
        f'<span class="id">{item["sid"]}</span><span class="title">{item["title"]}</span>'
        f'<span class="goal">{item["tagline"]}</span><span class="footer">'
        f'<span class="tag tag--blue">Wave {item["wave"]}</span><span class="tag tag--yellow">Pending</span></span></a>'
        for item in SPECS
    )
    body = f"""<header class="hero"><p class="eyebrow">Master spec · ANT-MOCA</p>
<h1>Midnight Oil claim admission</h1><p class="tagline">Bind an approved research brief to per-claim evidence and fail closed before durable graph writes.</p>
<div class="meta-row"><span class="tag tag--blue"><span class="dot"></span>Status: executable</span>
<span class="tag tag--yellow"><span class="dot"></span>Owner: primary orchestrator</span>
<span class="tag tag--grey">5 sprints · 5 serial waves</span><span class="tag tag--grey">Generated {DATE}</span></div></header>
<section id="spec-lineage" class="block" data-spec-depth="0" data-parent-spec="">
<h2>Spec lineage</h2><p class="lede">Root htmlspec derived from the active Antiek goal and the output-admission decision.</p>
<p><strong>Parent:</strong> <a href="../../decisions/midnight-oil-output-admission.md">Midnight Oil output admission</a></p>
<h3>Child specs</h3><ul class="child-specs"><li>None yet. Hatch a child only if a sprint discovers a separately load-bearing program.</li></ul></section>
<section class="block"><h2>Goal</h2><p>Prevent unsupported Midnight Oil claims from becoming trusted graph knowledge while preserving partial work as clearly labeled operational HTML. Success is a signed policy, durable drift fencing, per-claim evidence mapping, a zero-write graph preflight, and truthful operator-visible states.</p>
<h3>Success criteria</h3><ul><li>Changing the acceptance policy invalidates approval authority before lease or spend.</li><li>Every admitted insight maps to approved, canonical receipt identifiers; unmapped claims remain operational-only.</li><li>Every graph refusal is proven to create zero protected-graph row delta, zero typed-event delta, and no new effect receipt while preserving any pre-existing rows byte-for-byte.</li><li>Legacy jobs never acquire invented coverage or retroactive operator consent.</li></ul>
<h3>Failure mode to avoid</h3><p>Do not confuse execution receipts, one step-level citation, fluent prose, or retained HTML with per-claim epistemic support.</p></section>
<section class="block"><h2>Context &amp; motivation</h2><p>Antiek’s completed Midnight Oil runtime already secures consent, budget, leases, terminal settlement, replay, deposit ordering, and graph effect receipts. Commit <code>16b0734e4</code> removed fabricated fallback claims and made no-result recovery honest.</p><p>The remaining gap is narrower and deeper: <code>MidnightOilStepEvidence</code> attaches receipts to a whole step, while graph projection creates every insight/question edge from that shared set. A count cannot prove coverage. This program versions the acceptance rule at approval and carries exact claim-to-receipt identity through recovery.</p></section>
<section class="block"><h2>Architecture overview</h2><div class="dep-graph">approved ResearchAcceptancePolicy
        │ included in JobConsentConfig canonical hash
        ▼
owner authority + operation queue + lease reconciliation
        │
        ▼
MidnightOilStepEvidence.claims[] ──► receipt-id validation
        │                                  │
        ├──► operational HTML (may retain unverified work)
        │
        └──► non-DuckDB preflight ──► exclusive writer flock
                                          │ authority + census SELECTs before mutation
                         refusal ────────► zero protected-graph/event delta + typed state</div>
<h3>Key invariants</h3><ul><li>Approval-time policy identity is one authority, carried by the existing canonical config hash.</li><li>Claim support is explicit; no string matching, first-receipt fallback, or legacy auto-upgrade.</li><li>Operational retention and graph admission are separate states.</li><li>Only non-DuckDB policy, claim-shape, and artifact checks finish before <code>connect_write</code>. Document/chunk association, current chunk text/hash, receipt identity, deterministic conflict census, and mutation share one exclusive connection; every authority/census SELECT precedes the first mutating SQL.</li><li>Projection never initializes schema; graph initialization is an explicit prerequisite.</li></ul></section>
<section class="block"><h2>Sprint roster</h2><p class="lede">All waves are serial because authority and evidence both cross the worker/live boundary. Each sprint must hand off green before the next begins.</p><div class="sprint-grid">{cards}</div></section>
<section class="block"><h2>Decision log</h2><table class="spec"><thead><tr><th>Decision</th><th>Why</th><th>Reverser</th><th>Date</th></tr></thead><tbody>
<tr><td>Per-claim mapping, not citation count</td><td>A step receipt cannot prove every claim.</td><td>A formally verified provider contract that supplies equivalent claim coverage.</td><td>{DATE}</td></tr>
<tr><td>Operational HTML may retain unverified work</td><td>Partial research is useful and recovery must not lose it.</td><td>Operator explicitly chooses destructive discard in a later policy version.</td><td>{DATE}</td></tr>
<tr><td>Preflight before first write</td><td>DuckDB writes and event logs must not partially admit claims.</td><td>A proven atomic cross-store transaction replaces replay.</td><td>{DATE}</td></tr></tbody></table></section>
<section class="block"><h2>Binding v1 policy</h2><ul>
<li><strong>Covered classes:</strong> every insight and every non-empty normalized <code>output_text</code> paragraph requires one or more exact locally canonical document/chunk/hash receipts.</li>
<li><strong>Exploratory questions:</strong> may remain explicitly unverified and operational-only; they are never projected as supported assertions.</li>
<li><strong>Paragraphs:</strong> normalize CRLF to LF, trim outer whitespace, split on one or more blank lines, preserve order, and retain normalized text.</li>
<li><strong>Canonical encoding:</strong> UTF-8 JSON with keys sorted, compact <code>(",", ":")</code> separators, <code>ensure_ascii=False</code>, and no display-only fields.</li>
<li><strong>Claim identity:</strong> SHA-256 of canonical JSON containing <code>domain="antiek.midnight_oil.claim"</code>, <code>schema_version=1</code>, <code>job_id</code>, <code>step_key</code>, <code>claim_class</code>, zero-based <code>ordinal</code>, and <code>normalized_text</code>.</li>
<li><strong>Receipt identity:</strong> SHA-256 of canonical JSON containing <code>domain="antiek.midnight_oil.source_receipt"</code>, <code>schema_version=1</code>, <code>document_id</code>, <code>chunk_id</code>, <code>hash_scope</code>, <code>content_hash</code>, and <code>canonical_url</code>. Title and other display metadata are excluded.</li>
<li><strong>External receipts:</strong> public-web receipts without a locally canonical chunk are retained operationally but refused graph admission in v1.</li>
<li><strong>Legacy:</strong> old rows are <code>legacy-unverified</code>; no default, migration, or similarity matcher may invent consent or coverage.</li>
</ul></section>
<section class="block"><h2>Admission outcomes</h2><table class="spec"><thead><tr><th>Reason code</th><th>State</th><th>Retry / operator action</th></tr></thead><tbody>
<tr><td><code>internal_local_chunk_temporarily_missing</code></td><td>pending</td><td>Retry only after local ingestion/reconciliation restores the already-authorized chunk.</td></tr>
<tr><td><code>operational_artifact_pending</code></td><td>pending</td><td>Resume deposit recovery; never redispatch research.</td></tr>
<tr><td><code>graph_lock_unavailable</code></td><td>pending</td><td>Retry projection after contention clears; never redispatch research.</td></tr>
<tr><td><code>policy_authority_drift</code></td><td>refused</td><td>New explicit approval/rerun; do not mutate the signed run.</td></tr>
<tr><td><code>legacy_unverified</code></td><td>refused</td><td>Explicit operator review or rerun; never auto-upgrade.</td></tr>
<tr><td><code>claim_coverage_missing</code></td><td>refused</td><td>Retain operational HTML; a new run may supply coverage.</td></tr>
<tr><td><code>receipt_malformed_or_forged</code></td><td>refused</td><td>Quarantine evidence; no automatic retry.</td></tr>
<tr><td><code>external_receipt_not_admissible_v1</code></td><td>refused</td><td>Ingest canonically under a future/new approved run or leave operational-only.</td></tr>
<tr><td><code>deterministic_row_conflict</code></td><td>refused</td><td>Operator reconciliation; pre-existing graph rows remain unchanged.</td></tr>
</tbody></table></section>
<section class="block"><h2>Rejected alternatives</h2><table class="spec"><thead><tr><th>Alternative</th><th>Why rejected</th><th>Reconsider if…</th></tr></thead><tbody>
<tr><td><strong>One citation per step</strong></td><td>Creates false coverage for unrelated claims in the same step.</td><td>Never without claim-scoped semantics.</td></tr>
<tr><td><strong>Reject all unsupported deposits</strong></td><td>Loses partial operational work and contradicts Midnight Oil recovery.</td><td>The operator selects destructive retention policy explicitly.</td></tr>
<tr><td><strong>Auto-link by embedding similarity</strong></td><td>Manufactures provenance probabilistically.</td><td>Only as advisory UI, never admission authority.</td></tr>
<tr><td><strong>Retroactively default legacy rows</strong></td><td>Fabricates approval and evidence mappings that never existed.</td><td>Never; rerun or explicit operator review is required.</td></tr></tbody></table></section>
<section class="block"><h2>Open questions</h2><table class="spec"><thead><tr><th>Question</th><th>Non-blocking v1 rule</th><th>Resolver</th></tr></thead><tbody>
<tr><td>Should a future policy admit cryptographically signed external receipts without local ingestion?</td><td>No. V1 requires a locally canonical document/chunk/hash chain.</td><td>Future policy-version RFC with operator approval</td></tr>
<tr><td>Should verified quotations become a distinct claim class?</td><td>No. V1 treats them as prose paragraphs and requires the same exact local coverage.</td><td>Usage evidence after SPR-05</td></tr></tbody></table></section>
<section class="block"><h2>Glossary</h2><table class="spec"><tbody><tr><td><strong>Operational output</strong></td><td>Retained HTML/audit material that is not yet admitted as trusted graph knowledge.</td></tr><tr><td><strong>Claim coverage</strong></td><td>An explicit mapping from one stable claim ID to one or more approved receipt IDs.</td></tr><tr><td><strong>Admission preflight</strong></td><td>A two-phase zero-mutation check: non-DuckDB validation before lock acquisition, followed by all DuckDB-resident authority and deterministic-row SELECTs under the exclusive writer connection before its first mutating SQL.</td></tr></tbody></table></section>
<section class="block" id="harness-hint-run" data-harness-default-pattern="serial" data-harness-serial-sprints="SPR-01,SPR-02,SPR-03,SPR-04,SPR-05"><h2>Execution harness hint</h2><p>Run all five waves serially. Use adversarial verification for SPR-04, but do not overlap file ownership across waves.</p></section>
<footer class="spec-footer">Generated by htmlspec · Source: active Antiek goal + <code>16b0734e4</code> · {DATE}</footer>"""
    return wrap("ANT-MOCA — Midnight Oil claim admission", body, wide=True)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "index.html").write_text(master(), encoding="utf-8")
    for item in SPECS:
        number = str(item["sid"])[4:]
        (ROOT / f"sprint-{number}-{item['slug']}.html").write_text(
            sprint(item), encoding="utf-8"
        )
    (ROOT / "README.md").write_text(
        "# ANT-MOCA\n\nExecutable HTML spec for approval-bound Midnight Oil research acceptance, per-claim evidence mapping, fail-closed graph admission, and truthful launch/admission UI. Open `index.html`; execute sprints by wave and consume each page’s harness hint.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
