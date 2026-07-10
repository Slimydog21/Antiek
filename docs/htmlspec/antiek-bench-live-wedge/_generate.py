"""Generate the self-contained Antiek-bench live-wedge htmlspec tree."""

from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STYLE_SOURCE = Path("/Users/slimydog/.agents/skills/htmlspec/templates/style.css")
GENERATED = "2026-07-10"


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


def rigor(cards: dict[str, str]) -> str:
    return "".join(
        f'<article class="rigor-card"><span class="label">{esc(name)}</span>'
        f'<p>{esc(text)}</p></article>'
        for name, text in cards.items()
    )


def milestones(items: list[tuple[str, str, str]]) -> str:
    out = []
    for i, (title, desc, criteria) in enumerate(items, 1):
        out.append(
            f'<div class="milestone"><div class="num">{i}</div><div>'
            f'<div class="title">{esc(title)}</div><p class="desc">{esc(desc)}</p>'
            f'<div class="criteria"><strong>Acceptance:</strong> {esc(criteria)}</div>'
            "</div></div>"
        )
    return "".join(out)


SPRINTS = [
    {
        "id": "ABLW-SPR-01",
        "slug": "journal-budget",
        "title": "Append-only journal + hard budget",
        "wave": "1",
        "goal": "Make realized spend, crash recovery, and idempotency consequences of one append-only record.",
        "files": "substrate/antiek_bench/live/{journal,budget,call_runner}.py; tests/test_antiek_bench_live_journal.py",
        "deps": "Existing BenchStore conventions; no dispatch provider or Not Diamond credentials.",
        "out": "No model calls, scoring changes, DuckDB table, retry policy, or UI.",
        "milestones": [
            ("Version the record", "Define LiveCallRecord with deterministic call_id, requested and actual model identity, task class, tokens, realized/reserved cost, latency, status, hashes, and bounded failure text.", "Round-trip every status without serializing environment values or API credentials."),
            ("Append and replay", "Implement fsync-backed JSONL append, duplicate-call rejection, tolerant replay of one truncated trailing line, and deterministic lookup.", "A simulated crash preserves every complete row and replays the same call map."),
            ("Fold the cap", "Compute spent and conservative pre-call reservation from the journal; a timeout consumes its full reservation because provider billing is unknowable.", "Property tests prove no new call starts when spent + reserve exceeds the approved USD cap."),
            ("Bound abandoned work", "Expose an injected timeout runner and explicit timeout result; do not invent process cancellation for an already-issued provider request.", "Timeout is recorded once, charged conservatively, and never retried implicitly."),
        ],
        "rigor": {
            "Intellectual honesty": "A timeout is not free: charge its reservation because the provider may have billed after the client stopped waiting. Record truncated-tail recovery rather than pretending every crash is atomic.",
            "Fairness": "Steelman SQLite as the second-best journal. Reject it here only because this wedge needs one-writer append/replay and existing Antiek state already uses file stores; reopen if concurrent writers become a requirement.",
            "Rigor": "Property-test arbitrary cost sequences against the hard-cap invariant, then inject a torn final JSONL line. A happy-path append test does not prove budget or crash safety.",
            "Diligence": "Read BenchStore and Midnight Oil budget conventions before naming fields. Reuse Antiek's deterministic hash identity pattern instead of adding random run identifiers.",
            "Defensibility": "Every persisted field must support scoring replay, budget proof, attribution, or failure diagnosis. Remove fields without one of those jobs and document the cap formula beside the implementation.",
        },
        "gates": "pytest -q tests/test_antiek_bench_live_journal.py; mypy substrate/antiek_bench/live; ruff check substrate/antiek_bench/live tests/test_antiek_bench_live_journal.py",
        "pattern": "inline",
        "fanout": "journal and budget share record semantics; run inline",
        "lenses": "torn-write/idempotency; timeout spend conservatism",
    },
    {
        "id": "ABLW-SPR-02",
        "slug": "fallback-free-runner",
        "title": "Fallback-free measured runner",
        "wave": "2",
        "goal": "Measure exactly two operator-configured models across the four Antiek task classes without cross-model fallback contamination.",
        "files": "substrate/antiek_bench/live/{wedge_config,live_run,suite_live}.py; tests/test_antiek_bench_live_run.py",
        "deps": "ABLW-SPR-01; model registry entries with non-zero input/output prices; dispatch router remains the sole execution authority.",
        "out": "No normal research-routing change, concurrency, automatic driver install, or benchmark-suite promotion.",
        "milestones": [
            ("Validate the wedge", "Require exactly two distinct enabled model IDs, positive prices, one positive total cap, one per-call timeout, and suite coverage of distill, synthesize, wrestle, and book_qa with non-empty scoring expectations.", "Invalid count, duplicate, disabled, zero-price, missing-class, and empty-keyword cases all fail before dispatch."),
            ("Remove fallback contamination", "Build one DispatchConfig per candidate with a single bench tier and fallback=None; never use provider_override atop the normal fallback chain.", "A provider-A failure produces A=failed/score-zero and never calls or attributes provider B."),
            ("Adapt existing scoring", "Wrap dispatch in the existing ProviderFn seam and delegate keyword scoring and BenchStore persistence to run_suite instead of forking it.", "Two models x eight items produce sixteen joined journal rows and normal leaderboard-compatible runs."),
            ("Resume deterministically", "Derive wedge_id and call_id from week, suite, model, and item; replay completed rows and continue only at the first absent call.", "A second identical run performs zero dispatches and yields identical scores and spend."),
        ],
        "rigor": {
            "Intellectual honesty": "Assert actual provider/model equals the requested registry pair even though fallback=None should guarantee it. A future router regression must fail attribution, not quietly poison Antiek-bench.",
            "Fairness": "A provider outage scores zero rather than being excluded, because availability is part of workstation quality. The verdict must also expose failure rate so the zero is not misread as answer-quality evidence alone.",
            "Rigor": "Inject successful, failed, timed-out, and over-budget calls. Verify call counts and config.fallback, not merely the final mean score.",
            "Diligence": "Compose run_suite, DispatchResult, ModelRegistry, and TierPricing directly. If a required literal rejects role=bench, change the narrow schema with a contract test rather than using a misleading production role.",
            "Defensibility": "The handoff records why provider_override was rejected: it preserves normal fallback behavior. Reconsider only if the router gains an explicit no-fallback override with equivalent tests.",
        },
        "gates": "pytest -q tests/test_antiek_bench_live_run.py tests/test_benchmark_harness.py; mypy substrate/antiek_bench/live; verify 0 network calls in deterministic CI",
        "pattern": "adversarial-verification",
        "fanout": "one builder; independent refuter targets cross-model attribution",
        "lenses": "fallback contamination; cap/restart call-count proof",
    },
    {
        "id": "ABLW-SPR-03",
        "slug": "notdiamond-shadow",
        "title": "Privacy-hashed Not Diamond shadow",
        "wave": "3",
        "goal": "Record Not Diamond recommendations for comparison while making dispatch authority structurally impossible.",
        "files": "substrate/antiek_bench/live/nd_shadow.py; tests/test_antiek_bench_nd_shadow.py; docs/htmlspec/notdiamond-verdict/VERDICT.md",
        "deps": "ABLW-SPR-02; operator-provided NOTDIAMOND_API_KEY only for gated smoke; official /v2/modelRouter/modelSelect contract.",
        "out": "No custom-router training, preference promotion, key storage, response generation, or authoritative routing.",
        "milestones": [
            ("Define an inert protocol", "NDShadowClient returns only recommendation, session_id, latency, and failure; the module may not import Antiek dispatch or model-selection mutators.", "An AST contract fails on forbidden imports or any callable named dispatch/install/select_driver."),
            ("Double-gate calls", "Require both explicit wedge configuration and ANTIEK_NOTDIAMOND truthy; default off. Always request hash_content=true and exactly the two wedge candidates.", "Unset env or disabled config makes zero client calls and writes zero shadow rows."),
            ("Record, never obey", "Append recommendation, candidate set, tradeoff, session ID, status, and latency; do not expose as_dispatch_kwargs or feed it to scoring.", "Changing ND output cannot change dispatch calls, scores, selected driver, or budget ledger."),
            ("Bound privacy and failure", "Truncate external errors, exclude prompt/response bodies and secrets, and make ND timeout/failure non-fatal.", "Sentinel secrets are absent from journal, BenchStore, and rendered artifacts; failed ND still leaves the wedge identical."),
        ],
        "rigor": {
            "Intellectual honesty": "Call this a shadow recommendation, never a router integration. The verdict must separate ND availability from evidence that its suggestion would have won.",
            "Fairness": "Compare ND against both the operator's explicit driver and Antiek-bench, including disagreements; do not frame agreement as correctness or disagreement as failure without measured outcomes.",
            "Rigor": "Prove inertness with forbidden-import AST checks and before/after registry snapshots. A UI label saying advisory is not an authority boundary.",
            "Diligence": "Implement the current official modelSelect fields—messages, two llm_providers, hash_content, tradeoff, session_id—behind an injected client so CI never opens a socket.",
            "Defensibility": "Keep custom-router training outside this sprint and cite the existing G8 gate. Reconsider only after enough task-labeled Antiek outcomes exist and the operator explicitly unlocks training.",
        },
        "gates": "pytest -q tests/test_antiek_bench_nd_shadow.py tests/test_notdiamond_advisory_settings.py; static forbidden-import gate; secret sentinel scan",
        "pattern": "perspective-diverse-verify",
        "fanout": "privacy refuter and authority-boundary refuter are independent lenses",
        "lenses": "secret/content leakage; indirect dispatch-authority path",
    },
    {
        "id": "ABLW-SPR-04",
        "slug": "weekly-verdict-smoke",
        "title": "Weekly HTML verdict + gated smoke",
        "wave": "4",
        "goal": "Turn measured calls into an operator-readable HTML comparison and one safely gated live proof.",
        "files": "substrate/antiek_bench/live/weekly_verdict.py; scripts/antiek_bench_live_smoke.py; tests/test_antiek_bench_weekly_verdict.py; docs/decisions/antiek-bench-live-wedge.md",
        "deps": "ABLW-SPR-01..03; real credentials and spend approval only for the manual smoke.",
        "out": "No scheduler install, production traffic switch, custom router, automatic suite rewrite, or automatic model promotion.",
        "milestones": [
            ("Compare three selectors", "Render operator driver, per-task bench winner, and ND shadow modal suggestion with quality, cost, p50/p95 latency, availability, disagreement counts, and sample sizes.", "Golden fixture produces exact metrics and never labels an unmeasured or truncated class winner."),
            ("Render self-contained HTML", "Project the verdict as HTML with source week, suite version, budget spent/cap, failures, and a fixed advisory-only/no-auto-promotion footer.", "Artifact opens offline, contains no prompt body or secret, and sets auto_promotion=false in its structured payload."),
            ("Refuse unsafe smoke", "Create a one-item x two-model smoke requiring ANTIEK_BENCH_LIVE_SMOKE=1, refusing under CI, enforcing <=$0.10 and 30-second timeout, printing only IDs and aggregate spend.", "Absent gate and CI both exit 2 before provider construction; injected smoke proves cap and output redaction."),
            ("Close the decision", "Update the decision record with measured reconsider-if thresholds and preserve operator approval for suite/model changes.", "Registry and active suite snapshots are identical before and after verdict generation."),
        ],
        "rigor": {
            "Intellectual honesty": "Suppress a winner for any budget-truncated task class and display failure/timeout counts beside quality. Do not turn a tiny shadow sample into a Not Diamond adoption claim.",
            "Fairness": "Present operator choice, Antiek-bench, and ND in the same table with the same sample and metric labels. The operator's explicit preference remains valid even when a benchmark mean differs.",
            "Rigor": "Golden-test percentile math, disagreement matrix, truncation, partial outage, and HTML redaction. The manual live smoke is evidence only when its journal and approved cap are preserved.",
            "Diligence": "Reuse existing leaderboard and HTML projection conventions; read deployment scheduling patterns but do not install a scheduler in this bounded wedge.",
            "Defensibility": "Persist the verdict inputs and schema versions so a later model release can reproduce why a recommendation changed. Record the exact evidence threshold required before revisiting ND custom routing.",
        },
        "gates": "pytest -q tests/test_antiek_bench_weekly_verdict.py tests/test_settings_suite_proposal.py; smoke refusal tests; HTML parser link/structure check; hardenx on merged diff",
        "pattern": "adversarial-verification",
        "fanout": "builder plus independent metrics/privacy refuter",
        "lenses": "truncated-class false winner; HTML secret/prompt leakage",
    },
]


def sprint_page(s: dict[str, object]) -> str:
    body = f"""
<header class="hero"><p class="eyebrow">Sprint · {esc(s['id'])}</p><h1>{esc(s['title'])}</h1>
<p class="tagline">{esc(s['goal'])}</p><div class="meta-row"><span class="tag tag--blue">Wave {esc(s['wave'])}</span><span class="tag tag--yellow">Status: ready</span><span class="tag tag--grey">Owner: isolated builder</span></div></header>
<section class="block"><h2>Parent context</h2><p>Antiek-bench currently differentiates deterministic stubs. This campaign makes one measured production wedge without replacing the existing scoring truth or Antiek's dispatch authority.</p><p>Not Diamond remains shadow-only. The complete north star is an operator-controlled model decision tree informed by measured task quality, realized cost, latency, and failures.</p><p><a href="index.html">Back to master spec</a></p></section>
<section class="block"><h2>Goal</h2><p>{esc(s['goal'])}</p><h3>Owning files</h3><p><code>{esc(s['files'])}</code></p></section>
<section class="block"><h2>Technical milestones</h2>{milestones(s['milestones'])}</section>
<section class="block"><h2>Rigor: five values</h2><div class="rigor">{rigor(s['rigor'])}</div></section>
<section class="block"><h2>Dependencies</h2><p>{esc(s['deps'])}</p></section>
<section class="block"><h2>Out of scope</h2><p>{esc(s['out'])}</p></section>
<section class="block"><h2>Verification gates</h2><pre><code>{esc(s['gates'])}</code></pre><p>Every command must exit 0; report exact counts. A gate not run is NOT RUN.</p></section>
<section class="block"><h2>Handoff packet</h2><ul><li>Commit SHA and exact files changed.</li><li>Test commands, counts, and any flakes or skipped live proof.</li><li>Budget/authority/privacy invariants proved and any deviation from this sprint.</li><li>Next sprint readiness and operator-only gates.</li></ul></section>
<section class="block" id="harness-hint" data-harness-pattern="{esc(s['pattern'])}" data-harness-fanout-unit="{esc(s['fanout'])}" data-harness-verifier-lenses="{esc(s['lenses'])}" data-harness-rounds-floor="1" data-harness-rounds-cap="4"><h2>Execution harness hint</h2><p><code>{esc(s['pattern'])}</code> · {esc(s['fanout'])}</p><p>Verifier lenses: {esc(s['lenses'])}</p></section>
<footer class="spec-footer">{esc(s['id'])} · generated {GENERATED} · source: Antiek /infinite cycle rt2 + Fable architecture pass</footer>"""
    return shell(f"{s['id']} — {s['title']}", body)


def master_page() -> str:
    cards = "".join(
        f'<a class="sprint-card" href="sprint-{i:02d}-{s["slug"]}.html"><span class="id">{esc(s["id"])}</span><span class="title">{esc(s["title"])}</span><span class="goal">{esc(s["goal"])}</span><span class="footer"><span class="tag tag--blue">Wave {esc(s["wave"])}</span><span class="tag tag--yellow">ready</span></span></a>'
        for i, s in enumerate(SPRINTS, 1)
    )
    body = f"""
<header class="hero"><p class="eyebrow">Master spec · ABLW</p><h1>Antiek-bench live measured wedge</h1><p class="tagline">Two real models, four task classes, one hard cap, and a Not Diamond shadow that cannot dispatch.</p><div class="meta-row"><span class="tag tag--blue">Status: executable</span><span class="tag tag--yellow">Owner: Antiek /infinite</span><span class="tag tag--grey">4 sprints · 4 waves</span><span class="tag tag--grey">{GENERATED}</span></div></header>
<section id="spec-lineage" class="block" data-spec-depth="0" data-parent-spec=""><h2>Spec lineage</h2><p>Root spec. It sharpens <a href="../antiek-bench-recursive/index.html">Antiek-bench recursive</a> and <a href="../notdiamond-verdict/VERDICT.md">the Not Diamond verdict</a>. No child specs are required for this bounded wedge.</p><ul class="child-specs"></ul></section>
<section class="block"><h2>Goal</h2><p>Produce one restart-safe measured benchmark through Antiek's existing dispatch authority, persist enough telemetry to compare task quality, realized cost, latency, and availability, and record Not Diamond recommendations as inert shadow evidence.</p><h3>Success criteria</h3><ul><li>Exactly two registered models × four task classes; every call attributable and restart-idempotent.</li><li>No dispatch starts beyond the operator-approved cap; timeouts charge conservatively.</li><li>Weekly HTML verdict compares operator, bench, and ND shadow without auto-promoting anything.</li></ul><h3>Failure mode to avoid</h3><p>Normal router fallback silently substitutes one candidate for another and contaminates model scores. Every candidate config therefore has <code>fallback=None</code>.</p></section>
<section class="block"><h2>Architecture overview</h2><div class="dep-graph">ModelRegistry + live suite\n        │\n        ▼\nfallback-free DispatchConfig ──► dispatch() ──► LiveCallJournal\n                                      │                 │\n                                      ▼                 ▼\n                               existing run_suite   budget + replay\n                                      │                 │\n                                      └────────┬────────┘\n                                               ▼\nND modelSelect (shadow only) ─────────► weekly HTML verdict\n                                               │\n                                      operator decides</div><h3>Key invariants</h3><ul><li>Dispatch remains Hermes/Antiek-owned; ND has no dispatch imports or mutator-shaped output.</li><li>Journal identity is deterministic; completed calls replay and never double-spend.</li><li>Failures and timeouts score zero and remain separately visible as availability evidence.</li><li>No prompt bodies, responses, or secrets enter ND shadow or the HTML verdict.</li></ul></section>
<section class="block"><h2>Sprint roster</h2><p class="lede">Serial waves are deliberate: every later surface consumes the prior invariant.</p><div class="sprint-grid">{cards}</div></section>
<section class="block"><h2>Decision log</h2><table class="spec"><thead><tr><th>Decision</th><th>Why</th><th>Reconsider if</th></tr></thead><tbody><tr><td>Fallback-free per-model config</td><td>Normal fallback makes attribution untrustworthy.</td><td>Router exposes a proved no-fallback override.</td></tr><tr><td>Append-only JSONL</td><td>One primitive supplies spend, replay, and telemetry without a second DB writer.</td><td>Concurrent writers or cross-host transactions become required.</td></tr><tr><td>ND shadow only</td><td>Antiek retains BYOK budget and dispatch authority while gathering comparative evidence.</td><td>Operator unlocks G8 after enough labeled outcomes exist.</td></tr></tbody></table></section>
<section class="block"><h2>Rejected alternatives</h2><table class="spec"><thead><tr><th>Alternative</th><th>Why rejected</th><th>Reconsider if</th></tr></thead><tbody><tr><td>provider_override on normal config</td><td>Preserves fallback chain and can score the wrong model.</td><td>Fallback is explicitly disabled and mechanically tested.</td></tr><tr><td>Rewrite run_suite</td><td>Forks scoring and leaderboard semantics.</td><td>Live scoring needs a different rubric that cannot be adapted.</td></tr><tr><td>ND authoritative routing</td><td>Conflicts with explicit operator selection, BYOK budget, and §16 authority.</td><td>Not in this goal without explicit operator policy change.</td></tr><tr><td>Custom-router training now</td><td>Insufficient task-labeled outcomes; G8 remains locked.</td><td>Measured sample threshold and operator unlock are both satisfied.</td></tr></tbody></table></section>
<section class="block"><h2>Official Not Diamond grounding</h2><ul><li><a href="https://docs.notdiamond.ai/reference/token_model_select_v2_modelrouter_modelselect_post">modelSelect</a> returns a recommended model and session ID from supplied candidates.</li><li><a href="https://docs.notdiamond.ai/docs/key-concepts">Tradeoffs</a> cover quality, cost, and latency; shadow records the requested policy.</li><li><a href="https://docs.notdiamond.ai/docs/routing-between-custom-models">Custom models/router</a> require evaluation data and remain out of scope.</li></ul></section>
<section class="block" id="harness-hint-run" data-harness-default-pattern="adversarial-verification" data-harness-inline-only-sprints="ABLW-SPR-01"><h2>Execution harness hint</h2><p>Run serial waves. SPR-01 is inline; later sprints require an independent attribution, authority, or metrics refuter. Worktree isolation is mandatory.</p></section>
<footer class="spec-footer">Generated by htmlspec · source: Antiek /infinite cycle rt2, Fable architecture pass, official Not Diamond docs · {GENERATED}</footer>"""
    return shell("Antiek-bench live measured wedge — Master Spec", body, wide=True)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "index.html").write_text(master_page(), encoding="utf-8")
    for i, sprint in enumerate(SPRINTS, 1):
        path = ROOT / f"sprint-{i:02d}-{sprint['slug']}.html"
        path.write_text(sprint_page(sprint), encoding="utf-8")


if __name__ == "__main__":
    main()
