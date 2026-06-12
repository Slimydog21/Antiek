#!/usr/bin/env python3
"""Generate ANT-DRL htmlspec artifacts. Idempotent."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
STYLE_PATH = Path("/Users/slimydog/.grok/skills/htmlspec/templates/style.css")
DATE = "2026-06-12"
CSS_BLOCK = f"<style>\n{STYLE_PATH.read_text()}\n</style>"


def wrap(title: str, body: str, wide: bool = False) -> str:
    cls = "page page--wide" if wide else "page"
    return (
        f"<!doctype html>\n<html lang=\"en\">\n<head>\n"
        f"<meta charset=\"utf-8\" />\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
        f"<title>{title}</title>\n{CSS_BLOCK}\n</head>\n<body>\n"
        f"<main class=\"{cls}\">\n{body}\n</main>\n</body>\n</html>\n"
    )


def rigor(h, f, r, d, de) -> str:
    return f"""<section class="block"><h2>Rigor — operating manual for this sprint</h2>
<div class="rigor">
<div class="rigor-card"><span class="label">1 · Intellectual honesty</span><h4>Calibrate confidence</h4><p>{h}</p></div>
<div class="rigor-card"><span class="label">2 · Fairness</span><h4>Steelman rejected alt</h4><p>{f}</p></div>
<div class="rigor-card"><span class="label">3 · Rigor</span><h4>Mechanical checks</h4><p>{r}</p></div>
<div class="rigor-card"><span class="label">4 · Diligence</span><h4>Read before write</h4><p>{d}</p></div>
<div class="rigor-card"><span class="label">5 · Defensibility</span><h4>Survives turnover</h4><p>{de}</p></div>
</div></section>"""


def milestones(items) -> str:
    out = ['<section class="block"><h2>Technical milestones</h2>']
    for i, (t, desc, crit, files) in enumerate(items, 1):
        cl = "".join(f"<li>{c}</li>" for c in crit)
        fl = "".join(f'<span class="file">{x}</span>' for x in files)
        out.append(f"""<div class="milestone"><div class="num">{i}</div><div>
<div class="title">{t}</div><p class="desc">{desc}</p>
<div class="criteria"><strong>Acceptance criteria</strong><ul>{cl}</ul></div>
<div class="files">{fl}</div></div></div>""")
    out.append("</section>")
    return "\n".join(out)


def sprint(
    sid, num, slug, title, tagline, wave, budget,
    p1, p2, pos, goal_extra, ms, rig, deps, ext, oos, gates, harness,
    status: str = "pending",
) -> str:
    du = "".join(f"<li>{x}</li>" for x in deps) or '<li class="muted">None</li>'
    de = "".join(f"<li>{x}</li>" for x in ext)
    oo = "".join(f"<li>{x}</li>" for x in oos)
    gt = "".join(
        f"<tr><td><strong>{n}</strong></td><td><code>{c}</code></td><td>{e}</td></tr>"
        for n, c, e in gates
    )
    body = f"""<header class="hero">
<p class="eyebrow"><a href="index.html">&larr; Perfect Deep Research Loop</a> · Sprint {num}</p>
<h1>{title}</h1><p class="tagline">{tagline}</p>
<div class="meta-row">
<span class="tag tag--blue"><span class="dot"></span>Wave {wave}</span>
<span class="tag tag--{'green' if status == 'done' else 'yellow'}"><span class="dot"></span>{status}</span>
<span class="tag tag--grey">Budget: {budget}</span></div></header>
<section class="block"><h2>Parent context</h2><p>{p1}</p><p>{p2}</p>
<div class="callout callout--info"><strong>Position:</strong> {pos}</div></section>
<section class="block"><h2>Goal</h2><p><strong>{tagline}</strong></p><p>{goal_extra}</p></section>
{milestones(ms)}
{rigor(*rig)}
<section class="block"><h2>Dependencies</h2><div class="two-col">
<div><h3>Upstream</h3><ul>{du}</ul></div>
<div><h3>External</h3><ul>{de}</ul></div></div></section>
<section class="block"><h2>Out of scope</h2><ul>{oo}</ul></section>
<section class="block"><h2>Verification gates</h2>
<table class="spec"><thead><tr><th>Gate</th><th>Command</th><th>Expected</th></tr></thead><tbody>{gt}</tbody></table></section>
<section class="block"><h2>Handoff packet</h2>
<p class="lede">Paste this block at the end of your final message when the sprint is done.</p>
<pre><code>## Sprint {sid} — Handoff

### Status
done | blocked | partial — one line why

### Files touched
- path:line — what changed

### Milestones
- [x] M1: …
- [ ] M2: …

### Verification gate results
- Gate name: pass | fail | skipped (why)

### Decisions made mid-flight
- what / why / what would reverse it

### Assumptions surfaced
- …

### Steelman of rejected alternative
- …

### Open questions discovered
- question — who can answer

### Next sprint can start when
- condition

### Out-of-scope temptations encountered
- wanted X; did Y instead
</code></pre></section>
<section class="block" id="harness-hint" data-harness-pattern="{harness[0]}"
 data-harness-fanout-unit="{harness[1]}" data-harness-verifier-lenses="{harness[2]}"
 data-harness-rounds-floor="{harness[3]}" data-harness-rounds-cap="{harness[4]}">
<h2>Harness hint</h2><p>Pattern <code>{harness[0]}</code> · {harness[1]}</p></section>
<footer class="spec-footer">{sid} · <a href="index.html">Master spec</a> · {DATE}</footer>"""
    return wrap(f"{sid} · {title}", body)


def main() -> None:
    # --- sprint pages ---
    specs = [
        ("01", "terminal-contract", "DeepResearchComplete terminal contract",
         "Define the single falsifiable terminal state for deep research.", 1, "4 milestones",
         "Loop 1 (orchestration/loop_one) ends at synthesize.delivered and investigation.completed; DRW (cascade_routes._research_loop_factory) still uses make_demo_loop(steps=3) and can reach done without synthesis.",
         "Path A (converge) is ratified. This sprint is fork-independent: name the terminal contract before harness or convergence work.",
         "Wave 1 foundation.",
         "ANT-DRL · fork A · Exa out of scope.",
         [
             ("Invariant module", "Add orchestration/invariants/deep_research_complete.py using Phase 6–9 postconditions semantics.",
              ["pytest tests/test_deep_research_complete.py -q passes", "DRW-only trajectory fails invariant"],
              ["orchestration/invariants/deep_research_complete.py", "tests/test_deep_research_complete.py"]),
             ("Wire callers", "loop_one and cascade_session consult invariant before terminal complete.",
              ["grep shows both modules import invariant", "negative test for premature DRW done"],
              ["orchestration/loop_one/orchestrator.py", "orchestration/cascade_session.py"]),
             ("Decision doc", "docs/decisions/deep-research-terminal-contract.md",
              ["file exists with event-type citations"], ["docs/decisions/deep-research-terminal-contract.md"]),
             ("Regression fixture", "tests/regression/agent_failures/drw_done_without_synthesis.yaml",
              ["fixture collected by pytest"], ["tests/regression/agent_failures/drw_done_without_synthesis.yaml"]),
         ],
         ("Report make_demo_loop in prod factory from grep, not memory.", "Steelman fork B; rejected — split-brain is named failure mode.",
          "pytest negatives required.", "Read postconditions.py Phase 6–9 before defining terminal.",
          "Handoff quotes SYNTHESIZE_DELIVERED and constraint_loop_status values."),
         [], ["orchestration/phase_runner/postconditions.py", ".venv pytest"],
         ["Exa adapter", "SPR-DRL-06 convergence", "apps/reading UI"],
         [("Invariant tests", "./.venv/bin/python -m pytest tests/test_deep_research_complete.py -q", "all passed")],
         ("inline", "single module", "falsifiability|correspondence", "1", "3")),
        ("02", "harness-p11-p15", "PLATFORM_EXEC P-11..P-15",
         "Mechanical harness for Loop 1 E2E, reconstruct, flywheel.", 2, "5 milestones",
         "PLATFORM_EXEC_MATRIX ends at P-10. Loop 1 and cascade_session have tests but no binding rows or canonical_verify profile.",
         "Reviewer: canonical_verify. Split-brain must fail CI, not review.",
         "Wave 2 after SPR-DRL-01.",
         "Adds deep-research subcommand to canonical_verify.sh.",
         [
             ("Matrix rows", "P-11 Loop 1 E2E, P-12 invariant negative, P-13 session reconstruct, P-14 PromotionFunnel serialize, P-15 knowledge.reused.",
              ["five rows with commands"], ["docs/agent-execution/PLATFORM_EXEC_MATRIX.md"]),
             ("canonical_verify deep-research", "New subcommand orchestrating hermetic checks.",
              ["prints CANONICAL_VERIFY_OK: deep-research"], ["scripts/canonical_verify.sh", "tests/test_canonical_verify.py"]),
             ("P-11 test", "Loop 1 path asserts DeepResearchComplete before completed.",
              ["isolated pytest passes"], ["tests/test_loop_one_orchestrator.py"]),
             ("P-13 test", "cascade_session reconstruct from JSONL.",
              ["tests/test_cascade_session.py passes"], ["tests/test_cascade_session.py"]),
             ("CI wiring", "agent_execution_gates.yml runs deep-research on orchestration/ changes.",
              ["workflow diff shows step"], [".github/workflows/agent_execution_gates.yml"]),
         ],
         ("Mark GAP if gate cannot be hermetic.", "Steelman operator-only verify; rejected for split-brain risk.",
          "Each row fails on injected regression.", "Mirror P-01..P-10 row format exactly.",
          "Handoff lists row IDs with introducing SHA."),
         ["SPR-DRL-01"], ["PLATFORM_EXEC_MATRIX.md", "canonical_verify.sh"],
         ["Live LLM in CI", "Exa", "Playwright P-07"],
         [("Profile", "./scripts/canonical_verify.sh deep-research", "CANONICAL_VERIFY_OK: deep-research")],
         ("inline", "matrix+script", "harness-completeness|F3-guard", "1", "4")),
        ("03", "loop-one-engine", "Loop 1 engine hardening",
         "Bounded parallel Phase 2 and subgraph connector seeds.", 3, "4 milestones",
         "Loop 1 is synthesis spine under Path A; must be hard-to-vary before external evidence packs arrive.",
         "Parallel with SPR-DRL-04 — disjoint files.",
         "Wave 3 engine track.",
         "Respect DuckDB single-writer and rubric latency baseline.",
         [
             ("Bounded parallel Phase 2", "Capped concurrency with deterministic event ordering.",
              ["concurrency bound test", "monotonic seq"], ["orchestration/loop_one/orchestrator.py"]),
             ("Connector seeds", "Phase 1 orientation cites graph when provenance intact.",
              ["hermetic seeded graph test"], ["orchestration/loop_one/", "substrate/graph/"]),
             ("Postcondition alignment", "verify_phase boundaries match DeepResearchComplete.",
              ["grep alignment"], ["orchestration/phase_runner/postconditions.py"]),
             ("Rubric guard", "benchmarks.rubric_latency --check-regression passes.",
              ["exit 0"], ["benchmarks/rubric_latency.py"]),
         ],
         ("Stop if parallel Phase 2 breaks db_lock.", "Steelman serial Phase 2; rejected for post-convergence latency.",
          "No sleep-based concurrency tests.", "Read orchestrator.py end-to-end first.",
          "Log concurrency cap rationale if non-obvious."),
         ["SPR-DRL-01"], ["craft_signature.md", "runtime/db_lock.py"],
         ["DRW convergence", "New dispatch providers"],
         [("Loop one", "./.venv/bin/python -m pytest tests/test_loop_one_orchestrator.py -q", "pass"),
          ("Rubric", "./.venv/bin/python -m benchmarks.rubric_latency --check-regression", "exit 0")],
         ("inline", "orchestrator.py shared", "single-writer|craft-signature", "1", "3")),
        ("04", "evict-demo-loop", "Evict make_demo_loop from prod",
         "Contract-faithful gather stub in _research_loop_factory.", 3, "4 milestones",
         "Prod factory returns make_demo_loop — reuse-blind MOCK per compounding/benchmark.",
         "Parallel with SPR-DRL-03.",
         "Wave 3 gather track.",
         "Stub is not real research; honest placeholder until Exa.",
         [
             ("Contract stub loop", "Real StepEvents + PromotionFunnel under db_lock.",
              ["deterministic cost", "funnel append"], ["runtime/research_runner/host_local.py"]),
             ("Swap factory", "cascade_routes uses stub not make_demo_loop(steps=3).",
              ["grep confirms"], ["interfaces/research/api/cascade_routes.py"]),
             ("Benchmark README", "Distinguish MOCK demo vs contract stub vs future Exa.",
              ["README updated"], ["compounding/benchmark/README.md"]),
             ("Boundary doc", "spr-08-meta-reading-boundary.md note.",
              ["doc mentions stub"], ["docs/decisions/spr-08-meta-reading-boundary.md"]),
         ],
         ("Do not claim stub is real research.", "Steelman keep demo loop for UX; rejected — prod lying blocks Path A.",
          "cascade + remote_exec tests stay green.", "Read host_local make_demo_loop first.",
          "Handoff states behavioral delta demo vs stub."),
         ["SPR-DRL-01"], ["promotion_funnel.py", "compounding/benchmark/"],
         ["Exa", "Removing MOCK from benchmark null path"],
         [("Cascade", "./scripts/canonical_verify.sh cascade", "CANONICAL_VERIFY_OK: cascade")],
         ("inline", "factory+host_local", "prod-honesty|promotion-path", "1", "3")),
        ("05", "evidence-pack", "SessionEvidencePack contract",
         "Typed bridge from DRW merge to Loop 1 Phase 6+.", 4, "4 milestones",
         "Path A needs stable handoff artifact; Exa fills gather later, pack shape stays.",
         "Blocks SPR-DRL-06.",
         "Wave 4 contract sprint.",
         "Provenance chain required on every chunk.",
         [
             ("Schema", "Typed pack with chunk_ids, documents, ip_holder_id, session_id, hash.",
              ["invalid pack rejected"], ["tests/test_session_evidence_pack.py"]),
             ("Pack builder", "cascade_session merge builds pack from funnel + JSONL.",
              ["hermetic JSONL test"], ["orchestration/cascade_session.py"]),
             ("Immutability hash", "Same inputs → same content_hash.",
              ["hash stability test"], ["orchestration/cascade_session.py"]),
             ("Decision doc", "session-evidence-pack.md rejects raw StepEvent pipe.",
              ["file exists"], ["docs/decisions/session-evidence-pack.md"]),
         ],
         ("Empty pack valid but cannot satisfy DeepResearchComplete.", "Steelman pipe JSONL directly; rejected — synthesizer expects artifacts.",
          "On-disk JSONL fixtures.", "Read merge + promotion_funnel first.",
          "Schema version field for forward Exa compat."),
         ["SPR-DRL-02", "SPR-DRL-04"], ["substrate/schemas/", "cascade_session.py"],
         ["Synthesizer tuning", "Exa", "DRW UI redesign"],
         [("Pack tests", "./.venv/bin/python -m pytest tests/test_session_evidence_pack.py -q", "pass")],
         ("inline", "schema+builder", "provenance-chain|insufficient-evidence", "1", "4")),
        ("06", "convergence", "DRW → Loop 1 convergence",
         "One terminal path via DeepResearchComplete on Ask spine.", 4, "5 milestones",
         "Load-bearing Path A sprint: DRW gather-only, Loop 1 owns synthesis tail.",
         "Depends SPR-DRL-03 and SPR-DRL-05.",
         "Wave 4 capstone.",
         "Automatic synthesis tail — no split-brain UX.",
         [
             ("Pack entry", "loop_one Phase 6+ accepts SessionEvidencePack.",
              ["pack-only hermetic test"], ["orchestration/loop_one/orchestrator.py"]),
             ("Cascade tail", "All leaves done → pack → phases 6–9 on parent investigation.",
              ["parent investigation.completed", "DeepResearchComplete True"],
              ["orchestration/cascade_session.py", "orchestration/loop_one/orchestrator.py"]),
             ("Close regression", "drw_done_without_synthesis.yaml mitigation ships.",
              ["fixture no longer GAP"], ["tests/regression/agent_failures/"]),
             ("API honesty", "cascade_routes docstring/OpenAPI mentions synthesis tail.",
              ["doc updated"], ["interfaces/research/api/cascade_routes.py"]),
             ("Path A decision", "deep-research-convergence-a.md",
              ["file exists"], ["docs/decisions/deep-research-convergence-a.md"]),
         ],
         ("Report insufficient_evidence honestly.", "Steelman two-step UX gather then synthesize; rejected — split-brain failure mode.",
          "canonical_verify deep-research passes E2E.", "Trace parent investigation_id in spawn events.",
          "Handoff includes event sequence diagram."),
         ["SPR-DRL-03", "SPR-DRL-05"], ["cascade_routes.py", "loop_one/orchestrator.py"],
         ["Exa", "G7 multi-user", "Sprint 18 payouts"],
         [("E2E profile", "./scripts/canonical_verify.sh deep-research", "CANONICAL_VERIFY_OK: deep-research")],
         ("adversarial-verification", "convergence vs negative inject", "terminal-uniqueness|event-order", "2", "6")),
        ("07", "flywheel-e2e", "Flywheel E2E gates",
         "P-11..P-15 green; knowledge.reused on second run.", 5, "4 milestones",
         "Perfect loop requires harness proof of reuse observability, not just execution.",
         "Final integration after SPR-DRL-06.",
         "Wave 5 closure.",
         "MOCK compounding null stays documented.",
         [
             ("P-15 reuse", "Two-run hermetic test emits knowledge.reused.",
              ["P-15 row passes"], ["tests/test_flywheel_reuse.py"]),
             ("P-14 funnel", "Concurrent promotions serialize via db_lock.",
              ["P-14 row passes"], ["tests/test_promotion_funnel.py"]),
             ("CI job", "deep-research in agent_execution_gates on main.",
              ["workflow contains step"], [".github/workflows/agent_execution_gates.yml"]),
             ("Operator handoff", "SPR-DRL-handoff.md passes canonical_verify handoff.",
              ["handoff subcommand OK"], ["docs/htmlspec/deep-research-loop/SPR-DRL-handoff.md"]),
         ],
         ("Do not claim compounding delta from MOCK economics.", "Steelman skip P-15; rejected — flywheel is moat.",
          "Reuse test uses contract stub.", "Read app.py flywheel checks first.",
          "List hermetic vs operator-live rows like P-01."),
         ["SPR-DRL-06"], ["compounding/benchmark/", "interfaces/research/api/app.py"],
         ["Prod deploy", "Exa", "Claiming benchmark delta > 0 on MOCK"],
         [("Deep-research", "./scripts/canonical_verify.sh deep-research", "OK"),
          ("Agent-gates", "./scripts/canonical_verify.sh agent-gates", "OK")],
         ("inline", "CI sequential", "compounding-honesty|matrix-closure", "1", "4")),
        ("08", "parallel-gather", "Parallel Search gather loop",
         "Wire Parallel Search API into DRW browse loop; real chunks in pack.", 6, "5 milestones",
         "Operator ratified Parallel-first (not Exa-first). Path A convergence (SPR-DRL-06) is green; cascade_routes still defaults to make_contract_gather_stub.",
         "Mirror acquisition/search/exa/ shape for parallel/. Reuse promote_discovery pattern via ingest_url. Depends SPR-DRL-06 + SPR-DRL-07.",
         "Wave 6 gather adapter — Parallel Search only.",
         "No Parallel Task API one-call research; no Exa in this sprint; no Browserbase.",
         [
             ("acquisition/search/parallel/", "client.py: POST https://api.parallel.ai/v1/search (x-api-key, objective + search_queries). adapter.py: discover() → DiscoveryProposed with provider=parallel.",
              ["MockTransport hermetic test", "DiscoveryProvider includes parallel", "disc-parallel- id prefix"],
              ["acquisition/search/parallel/client.py", "acquisition/search/parallel/adapter.py", "substrate/schemas/events.py"]),
             ("make_parallel_gather_loop", "Browse loop: discover(sub_question) → promote_discovery top-k → StepEvents with discovery_id + document_id.",
              ["gather_mode=parallel on steps", "budget sidecar or cost estimate on proposal"],
              ["runtime/research_runner/host_local.py", "acquisition/search/parallel/adapter.py"]),
             ("Factory seam", "ANTIEK_DRW_GATHER=parallel|stub (default stub); PARALLEL_API_KEY from env only.",
              ["grep shows env gate", "test_cascade_api asserts stub default"],
              ["interfaces/research/api/cascade_routes.py", ".env"]),
             ("Pack chunks from ingest", "Ingested docs → doc-url-* in SessionEvidencePack (not doc-gather-* placeholders).",
              ["pack test with mocked parallel discover + ingest", "content_hash stable"],
              ["orchestration/session_evidence_pack.py", "runtime/research_runner/promotion_funnel.py"]),
             ("P-16 harness + decision", "Matrix row + tests/test_parallel_gather_loop.py; deep-research-exa-gather.md → parallel-first decision doc.",
              ["P-16 row with command", "docs/decisions/deep-research-parallel-gather.md exists"],
              ["docs/agent-execution/PLATFORM_EXEC_MATRIX.md", "scripts/canonical_verify.sh", "tests/test_parallel_gather_loop.py", "docs/decisions/deep-research-parallel-gather.md"]),
         ],
         ("Report Parallel index/cache blind spots in Not proved.", "Steelman Exa-first — rejected; operator chose Parallel. Steelman Parallel Task API as gather — rejected; collapses attribution like /answer.",
          "Zero live PARALLEL_API_KEY in CI; httpx.MockTransport only.", "Read exa/adapter.py as template; Parallel API needs objective + 2-3 search_queries per call.",
          "Handoff diagrams parallel search → ingest_url → funnel → pack chunk chain."),
         ["SPR-DRL-06", "SPR-DRL-07"], ["acquisition/urls/adapter.py", "substrate/legal_gate/", "https://docs.parallel.ai/api-reference/search/search"],
         ["Exa gather (SPR-DRL-10)", "Parallel Task/FindAll APIs", "Browserbase", "SerpAPI", "Live Parallel in CI"],
         [("Parallel gather", "./.venv/bin/python -m pytest tests/test_parallel_gather_loop.py -q", "all passed"),
          ("Deep-research profile", "./scripts/canonical_verify.sh deep-research", "CANONICAL_VERIFY_OK: deep-research")],
         ("adversarial-verification", "parallel-loop+pack", "attribution-chain|legal-gate|stub-default", "2", "5")),
        ("09", "dogfood-readiness", "Pack fidelity + parent terminal observability",
         "Gate prod dogfood: real doc-url-* in pack; session parent terminal visible.", 7, "5 milestones",
         "Cycle-2 tribunal: naive dogfood-first breaks on base-rate and incentives. SPR-DRL-08 Parallel mock E2E (P-16) does not prove pack bridge fidelity or parent DeepResearchComplete observability. _run_to_completion swallows synthesis-tail exceptions.",
         "Depends SPR-DRL-08. Cycle-2 htmlspec-2 sharpen — not a re-litigation of Path A.",
         "Wave 7 — dogfood readiness (engineering before trusted operator smoke).",
         "Pack E2E + parent-terminal instrumentation only; full HTTP cascade profile deferred.",
         [
             ("Pack fidelity E2E", "CascadeSession + make_parallel_gather_loop (mocked ingest) → build_evidence_pack yields ≥1 chunk with doc-url-* document_id (not doc-gather-* placeholder).",
              ["Hermetic test green", "content_hash stable on rebuild", "fails if only placeholder docs"],
              ["tests/test_drw_pack_fidelity.py", "orchestration/session_evidence_pack.py", "tests/test_session_evidence_pack.py"]),
             ("Insight metadata bridge", "When parallel loop promotes via ingest, funnel metadata carries source_document_id onto insight nodes so pack builder resolves doc-url-*.",
              ["Pack test passes without stub-only placeholders", "StepEvent document_id propagates to graph metadata"],
              ["runtime/research_runner/promotion_funnel.py", "substrate/graph/insight_question.py"]),
             ("Parent terminal observability", "Synthesis-tail failure must not silently pass: emit typed event or log; session status exposes deep_research_complete + synthesis_tail_error when recoverable.",
              ["Injected synthesis failure surfaces in trajectory or status", "_run_to_completion no bare except pass without audit trail"],
              ["interfaces/research/api/cascade_routes.py", "orchestration/cascade_session.py", "orchestration/invariants/deep_research_complete.py"]),
             ("P-17 harness + regression", "PLATFORM_EXEC_MATRIX P-17 row; canonical_verify deep-research includes pack fidelity test.",
              ["P-17 command documented", "scripts/canonical_verify.sh runs test"],
              ["docs/agent-execution/PLATFORM_EXEC_MATRIX.md", "scripts/canonical_verify.sh", "tests/test_drw_pack_fidelity.py"]),
             ("Operator smoke checklist", "docs/decisions/deep-research-smoke-checklist.md — tribunal checklist for DRW #1 before sessions 2–10.",
              ["Checklist cites parent investigation.completed", "Lists pack doc-url-* audit", "G2 counsel parallel track noted"],
              ["docs/decisions/deep-research-smoke-checklist.md"]),
         ],
         ("Report thin-pack and silent synthesis as Not proved until smoke DRW #1.", "Steelman full HTTP cascade E2E in CI — rejected this sprint; pack+parent observability is the binding falsifier.",
          "Zero live PARALLEL_API_KEY; mock ingest via sys.modules or fake ingest_url.", "Read build_session_evidence_pack doc-gather fallback before writing fidelity test.",
          "Handoff lists operator-live rows P-17 hermetic vs smoke DRW."),
         ["SPR-DRL-08"], ["orchestration/cascade_session.py", "tests/test_cascade_convergence.py", "docs/htmlspec/deep-research-loop/.caffenagent/egghead/tribunal-cycle-2-synthesis.md"],
         ["Full HTTP POST→SSE→synthesis TestClient profile", "Live Parallel in CI", "Exa SPR-DRL-10", "Browserbase", "10-session dogfood automation"],
         [("Pack fidelity", "./.venv/bin/python -m pytest tests/test_drw_pack_fidelity.py -q", "all passed"),
          ("Deep-research profile", "./scripts/canonical_verify.sh deep-research", "CANONICAL_VERIFY_OK: deep-research")],
         ("adversarial-verification", "pack-fidelity+parent-terminal", "split-brain|thin-pack|silent-synthesis", "2", "5")),
    ]

    statuses = {f"{n:02d}": "done" for n in range(1, 9)}
    statuses["09"] = "pending"

    for spec in specs:
        num, slug, title, tag, wave, budget, p1, p2, pos, extra, ms, rig, deps, ext, oos, gates, harness = spec
        sid = f"SPR-DRL-{num}"
        html = sprint(
            sid, num, slug, title, tag, wave, budget, p1, p2, pos, extra, ms, rig,
            deps, ext, oos, gates, harness, status=statuses.get(num, "pending"),
        )
        (ROOT / f"sprint-{num}-{slug}.html").write_text(html)

    cards = {1: "", 2: "", 3: "", 4: "", 5: "", 6: "", 7: ""}
    meta = [
        ("01", "terminal-contract", "DeepResearchComplete terminal contract", "Define falsifiable terminal state.", 1, "4 milestones", "done"),
        ("02", "harness-p11-p15", "PLATFORM_EXEC P-11..P-15", "Harness proves E2E + reconstruct + reuse.", 2, "5 milestones", "done"),
        ("03", "loop-one-engine", "Loop 1 engine hardening", "Bounded parallel Phase 2 + connectors.", 3, "4 milestones", "done"),
        ("04", "evict-demo-loop", "Evict make_demo_loop", "Contract-faithful prod factory.", 3, "4 milestones", "done"),
        ("05", "evidence-pack", "SessionEvidencePack", "Typed DRW→Loop1 bridge.", 4, "4 milestones", "done"),
        ("06", "convergence", "Path A convergence", "DRW gather → Loop 1 synthesis tail.", 4, "5 milestones", "done"),
        ("07", "flywheel-e2e", "Flywheel E2E", "P-11..P-15 green in CI.", 5, "4 milestones", "done"),
        ("08", "parallel-gather", "Parallel Search gather loop", "Parallel discovery → pack chunks.", 6, "5 milestones", "done"),
        ("09", "dogfood-readiness", "Pack fidelity + parent terminal", "Gate operator smoke DRW #1.", 7, "5 milestones", "pending"),
    ]
    for num, slug, title, goal, wave, budget, st in meta:
        sid = f"SPR-DRL-{num}"
        chip = "green" if st == "done" else "yellow"
        cards[wave] += f"""<a class="sprint-card" href="sprint-{num}-{slug}.html">
<span class="id">{sid}</span><span class="title">{title}</span><span class="goal">{goal}</span>
<span class="footer"><span class="tag tag--blue">Wave {wave}</span>
<span class="tag tag--grey">{budget}</span><span class="tag tag--{chip}"><span class="dot"></span>{st}</span></span></a>"""

    index_body = f"""<header class="hero"><p class="eyebrow">Master spec · ANT-DRL</p>
<h1>Perfect Deep Research Loop</h1>
<p class="tagline">One terminal contract, Path A convergence, real gather via Parallel Search (operator: Parallel-first).</p>
<div class="meta-row"><span class="tag tag--blue"><span class="dot"></span>draft</span>
<span class="tag tag--green"><span class="dot"></span>Waves 1–6 done</span>
<span class="tag tag--grey">9 sprints · 7 waves · {DATE}</span></div></header>
<section class="block"><h2>Goal</h2>
<p>Converge DRW gather with Loop 1 synthesis under <code>DeepResearchComplete</code>, wire <strong>Parallel Search</strong> (SPR-DRL-08), then gate <strong>operator dogfood</strong> with pack fidelity + parent-terminal observability (SPR-DRL-09). Exa deferred to SPR-DRL-10.</p>
<h3>Success criteria</h3><ul>
<li>DRW done without synthesis fails invariant in CI (P-12) — <strong>shipped SPR-DRL-01</strong></li>
<li><code>canonical_verify.sh deep-research</code> green — <strong>shipped SPR-DRL-07</strong></li>
<li>Prod factory uses <code>make_contract_gather_stub</code>, not <code>make_demo_loop</code> — <strong>shipped SPR-DRL-04</strong></li>
<li>P-15 <code>knowledge.reused</code> on second hermetic run — <strong>shipped SPR-DRL-07</strong></li>
<li>P-16 Parallel gather mock E2E — <strong>shipped SPR-DRL-08</strong></li>
<li>P-17 pack <code>doc-url-*</code> fidelity + parent terminal observability — <strong>SPR-DRL-09</strong></li></ul>
<h3>Failure mode</h3><p><strong>Split-brain</strong> — two terminals, one product name. <strong>Attribution collapse</strong> — Parallel Task API or Exa <code>/answer</code> substituting for Loop 1 synthesis.</p></section>
<section class="block"><h2>Context</h2>
<p>Loop 1: <code>orchestration/loop_one</code> → synthesis tail on session parent → <code>investigation.completed</code>.
DRW: <code>cascade_routes._research_loop_factory</code> → <code>make_contract_gather_stub</code> (honest placeholder).
Discovery: <code>acquisition/search/parallel/</code> (new) mirrors exa adapter shape; <code>PARALLEL_API_KEY</code> in operator <code>.env</code>.
Harness: P-11..P-16 shipped; P-17 in SPR-DRL-09. Cycle-2 tribunal ratified engineering-before-trusted-dogfood.</p>
<p>Interview ratified <strong>Path A</strong>, reviewer <strong>canonical_verify</strong>. Waves 1–6 executed; Wave 7 gates operator smoke.</p></section>
<section class="block"><h2>Architecture</h2>
<div class="dep-graph">W1: SPR-DRL-01 contract ✓
W2: SPR-DRL-02 harness ✓
W3: SPR-DRL-03 engine ✓ || SPR-DRL-04 evict demo ✓
W4: SPR-DRL-05 pack ✓ → SPR-DRL-06 converge ✓
W5: SPR-DRL-07 flywheel E2E ✓
W6: SPR-DRL-08 Parallel gather ✓
W7: SPR-DRL-09 dogfood readiness (pack fidelity + parent terminal)</div></section>
<section class="block"><h2>Sprint roster</h2>
<div class="wave-band">Wave 1</div><div class="sprint-grid">{cards[1]}</div>
<div class="wave-band">Wave 2</div><div class="sprint-grid">{cards[2]}</div>
<div class="wave-band">Wave 3 parallel</div><div class="sprint-grid">{cards[3]}</div>
<div class="wave-band">Wave 4 convergence</div><div class="sprint-grid">{cards[4]}</div>
<div class="wave-band">Wave 5</div><div class="sprint-grid">{cards[5]}</div>
<div class="wave-band">Wave 6 — real gather</div><div class="sprint-grid">{cards[6]}</div>
<div class="wave-band">Wave 7 — dogfood readiness</div><div class="sprint-grid">{cards[7]}</div></section>
<section class="block" id="harness-hint-run" data-harness-default-pattern="fan-out-and-synthesize"
 data-harness-inline-only-sprints="SPR-DRL-01,SPR-DRL-02,SPR-DRL-03,SPR-DRL-04,SPR-DRL-07,SPR-DRL-08"
 data-harness-sharpen-sprints="SPR-DRL-09">
<h2>Harness hint (run)</h2><p>Waves 1–6 complete. Execute <strong>SPR-DRL-09</strong> with adversarial-verification on pack-fidelity + parent-terminal (Cycle-2 tribunal). Operator smoke DRW #1 follows green P-17.</p></section>
<section class="block"><h2>Decision log</h2>
<table class="spec"><thead><tr><th>Decision</th><th>Why</th><th>Reconsider if</th></tr></thead><tbody>
<tr><td>Path A converge</td><td>Interview: split-brain = waste</td><td>Loop 1 deprecated</td></tr>
<tr><td>canonical_verify reviewer</td><td>Mechanical gates per HARD_TO_VARY</td><td>Operator waives row (GAP)</td></tr>
<tr><td>Stub default, Parallel env-gated</td><td>Hermetic CI + honest prod until operator sets <code>ANTIEK_DRW_GATHER=parallel</code></td><td>P-16 mock E2E green</td></tr>
<tr><td>Parallel Search only in SPR-DRL-08</td><td>Operator ratified Parallel-first; Exa → SPR-DRL-10</td><td>Parallel index blind spots measured</td></tr>
<tr><td>ingest_url single write seam</td><td>substrate-as-source-of-truth invariant</td><td>Second doc-id shape appears</td></tr>
<tr><td>SPR-DRL-09 before trusted dogfood</td><td>Cycle-2 tribunal: pack fidelity + parent terminal</td><td>Smoke DRW #1 green without P-17</td></tr>
<tr><td>Full HTTP cascade E2E deferred</td><td>Pack+parent falsifiers sufficient this cycle</td><td>Smoke shows HTTP-only gap</td></tr>
</tbody></table></section>
<section class="block"><h2>Rejected alternatives</h2>
<table class="spec"><tbody>
<tr><td><strong>B — Honest fork</strong></td><td>Operator chose A</td><td>Convergence fails twice</td></tr>
<tr><td><strong>Exa-first (pre-contract)</strong></td><td>Terminal undefined without contract</td><td>SPR-DRL-01..04 done ✓</td></tr>
<tr><td><strong>Exa /answer gather</strong></td><td>Collapses attribution chain (integration spec §12.5)</td><td>Typed replay of /answer exists</td></tr>
<tr><td><strong>DRW-only synthesizer</strong></td><td>Duplicates Loop 1 rubric</td><td>Loop 1 cannot take packs</td></tr>
<tr><td><strong>Polish both spines</strong></td><td>Two terminals, one product name</td><td>DeepResearchComplete shipped ✓</td></tr>
</tbody></table></section>
<section class="block"><h2>Open questions</h2>
<table class="spec"><tbody>
<tr><td>Phase 2 concurrency cap?</td><td>Default 4 (SPR-DRL-03)</td><td>Closed</td></tr>
<tr><td>Parent investigation for cascade tail?</td><td>Session root (SPR-DRL-06)</td><td>Closed</td></tr>
<tr><td>Exa gather (Wedge 1)?</td><td>Deferred — operator chose Parallel-first</td><td>SPR-DRL-10</td></tr>
<tr><td>SerpAPI / Tavily?</td><td>Provider enum extensible; no sprint yet</td><td>Operator gate</td></tr>
<tr><td>Auto-promote vs operator review for DRW?</td><td>SPR-DRL-08 defaults auto-promote top-k in loop; review UI deferred</td><td>Legal gate rejection rate measured</td></tr>
<tr><td>PARALLEL_API_KEY in prod?</td><td>Operator <code>.env</code> only; never CI</td><td>Key rotated after chat exposure</td></tr>
</tbody></table></section>
<section class="block"><h2>Glossary</h2>
<table class="spec"><tbody>
<tr><td><strong>DeepResearchComplete</strong></td><td>Phase 6–9 postconditions + synthesize.delivered + investigation.completed on session parent.</td></tr>
<tr><td><strong>SessionEvidencePack</strong></td><td>Typed DRW merge artifact feeding Loop 1 Phase 6+; chunks carry document + ip_holder provenance.</td></tr>
<tr><td><strong>make_parallel_gather_loop</strong></td><td>Browse loop factory: Parallel <code>discover</code> → <code>promote_discovery</code> → funnel; replaces stub when env-gated.</td></tr>
<tr><td><strong>DiscoveryProposed</strong></td><td>Typed event: URL considered, not ingested. Promotion via <code>DiscoverySelected</code>.</td></tr>
<tr><td><strong>doc-gather-* placeholder</strong></td><td>Pack fallback when insight nodes lack <code>source_document_id</code> — thin-pack signal, not success.</td></tr>
<tr><td><strong>Smoke DRW #1</strong></td><td>Operator checklist in <code>deep-research-smoke-checklist.md</code> (SPR-DRL-09).</td></tr>
</tbody></table></section>
<footer class="spec-footer">htmlspec ANT-DRL · {DATE}</footer>"""
    (ROOT / "index.html").write_text(wrap("ANT-DRL — Perfect Deep Research Loop", index_body, wide=True))
    print("Generated index +", len(specs), "sprints in", ROOT)


if __name__ == "__main__":
    main()