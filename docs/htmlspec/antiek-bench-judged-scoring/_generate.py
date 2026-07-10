"""Generate the self-contained judged-scoring htmlspec."""

from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STYLE = Path("/Users/slimydog/.agents/skills/htmlspec/templates/style.css")
DATE = "2026-07-10"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def shell(title: str, body: str, *, wide: bool = False) -> str:
    page = "page page--wide" if wide else "page"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        f"<title>{esc(title)}</title><style>{STYLE.read_text()}</style></head>"
        f'<body><main class="{page}">{body}</main></body></html>\n'
    )


def milestones(rows: list[tuple[str, str, str, str]]) -> str:
    return "".join(
        f'<div class="milestone"><div class="num">{index}</div><div>'
        f'<div class="title">{esc(title)}</div><p class="desc">{esc(description)}</p>'
        f'<div class="criteria"><strong>Acceptance:</strong> {esc(acceptance)}</div>'
        f'<div class="files"><span class="file">{esc(files)}</span></div></div></div>'
        for index, (title, description, acceptance, files) in enumerate(rows, 1)
    )


def rigor(cards: dict[str, str]) -> str:
    return "".join(
        f'<article class="rigor-card"><span class="label">{esc(name)}</span>'
        f"<p>{esc(text)}</p></article>"
        for name, text in cards.items()
    )


SPRINTS = [
    {
        "id": "ABJS-SPR-01",
        "slug": "blinded-judge-evidence",
        "title": "Versioned blinded judge evidence",
        "wave": "1",
        "goal": "Add qualitative scoring without exposing candidate identity or replacing deterministic checks.",
        "context": "The live wedge currently persists keyword-proxy quality. That proxy is useful for exact expected concepts but cannot judge synthesis quality, source handling, nuance, or whether an answer genuinely wrestles with a tension. This sprint adds a separate evidence journal; it does not change dispatch, model choice, or the existing keyword score.",
        "deps": "The hardened live call journal and exact eight-item suite at campaign tip 70eacc2c4. Judge calls remain injected/off by default; no credential is required in CI.",
        "out": "No pairwise winner, no weekly recommendation, no router mutation, no judging deterministic schema/provenance checks, and no raw prompt/response persistence.",
        "milestones": [
            ("Freeze the rubric", "Define a versioned qualitative rubric per task class with closed axes, integer bounds, evidence requirements, and deterministic validation.", "Unknown axes, out-of-range values, missing rationales, and rubric-version drift fail before journal append.", "substrate/antiek_bench/judged/rubric.py"),
            ("Blind candidate artifacts", "Create judge inputs with opaque candidate A/B labels, salted content hashes, task context, and rubric only. Provider/model IDs stay in a private join map outside the judge request.", "A sentinel candidate name, API key, prompt body, and route receipt never appear in the judge request or evidence journal.", "substrate/antiek_bench/judged/blinding.py"),
            ("Journal claims and settlements", "Use an fsync append-only claim/settle protocol with full SHA-256 identity over week, suite, item, rubric version, judge model, and blinded candidates.", "Concurrent duplicate claims make one external call; a stale claim becomes reconciliation-required and is never silently retried.", "substrate/antiek_bench/judged/journal.py"),
            ("Inject the judge boundary", "Accept a typed JudgeClient returning schema-validated axis scores and bounded rationale; persist only scores, evidence references, hashes, timing, and fixed failure codes.", "CI fixtures produce reproducible evidence with zero sockets, and external exceptions cannot leak into storage.", "substrate/antiek_bench/judged/runner.py; tests/test_antiek_bench_judged_evidence.py"),
        ],
        "rigor": {
            "Intellectual honesty": "Call this qualitative judge evidence, not ground truth. If a judge response omits an axis or violates the schema, record failed evidence; never coerce it into a plausible score.",
            "Fairness": "Candidate order is deterministically swapped across judge passes and identities remain hidden. A model may not judge its own output; reject that configuration rather than claiming neutrality.",
            "Rigor": "Property-test rubric bounds and journal identity, then race two claimers and inject a crash before settlement. A single valid fixture does not prove blinding or replay safety.",
            "Diligence": "Reuse the live journal's lock/fsync/corruption conventions and the suite task literals. Keep deterministic keyword, receipt, budget, and provenance checks outside the LLM rubric.",
            "Defensibility": "Persist rubric version, judge identity, blinded order, and input hashes so every score can be reproduced or invalidated when a rubric or judge model changes.",
        },
        "gates": "pytest -q tests/test_antiek_bench_judged_evidence.py; mypy substrate/antiek_bench/judged; ruff check substrate/antiek_bench/judged tests/test_antiek_bench_judged_evidence.py",
        "pattern": "adversarial-verification",
        "fanout": "one builder; independent privacy/blinding refuter",
        "lenses": "identity leakage and self-judging; crash-safe claim/settle replay",
    },
    {
        "id": "ABJS-SPR-02",
        "slug": "disagreement-calibration",
        "title": "Disagreement + calibration",
        "wave": "2",
        "goal": "Measure judge instability and agreement before interpreting qualitative scores.",
        "context": "A single LLM score is not a reliable evaluation. This sprint consumes the immutable evidence from Sprint 1 and adds position-swap, independent-judge, and human-anchor calibration views. No score can become a winner unless its evidence coverage and disagreement state are visible.",
        "deps": "ABJS-SPR-01; at least two judge configurations that are not candidate models. Human anchors are optional but their absence must be explicit.",
        "out": "No automatic benchmark rewrite, no model promotion, no hidden averaging across rubric versions, and no claim that judge agreement proves correctness.",
        "milestones": [
            ("Run position swaps", "Evaluate A/B and B/A under the same rubric and judge identity, storing order as part of evidence identity.", "A winner that flips under order is labeled position-sensitive and cannot produce a qualitative winner.", "substrate/antiek_bench/judged/calibration.py"),
            ("Compute independent disagreement", "Compare per-axis scores and winners across judge identities with explicit sample coverage and missing-evidence states.", "The report exposes axis deltas, winner disagreement, failure count, and effective sample size without averaging missing rows as zero.", "substrate/antiek_bench/judged/disagreement.py"),
            ("Calibrate against anchors", "Support versioned operator-reviewed anchor items and calculate signed error per axis; never include anchors in measured candidate means.", "Absent anchors display uncalibrated; changed anchors invalidate only their calibration version, not raw evidence.", "substrate/antiek_bench/judged/anchors.py"),
            ("Gate interpretation", "Define an advisory QualitativeVerdict that suppresses winners for position flips, judge disagreement above threshold, missing coverage, self-judging, or mixed rubric versions.", "Adversarial fixtures cannot produce a winner under any suppression condition, and no API returns dispatch-shaped output.", "substrate/antiek_bench/judged/verdict.py; tests/test_antiek_bench_judge_calibration.py"),
        ],
        "rigor": {
            "Intellectual honesty": "Report disagreement as evidence about evaluator uncertainty, not as noise to average away. An uncalibrated panel must say uncalibrated in its typed verdict.",
            "Fairness": "A position-flip harms both candidates symmetrically and suppresses the comparison. Human anchors are versioned and visible so one operator preference cannot masquerade as universal truth.",
            "Rigor": "Test Condorcet cycles, equal scores, missing judges, one failed swap, mixed rubric versions, and adversarial self-judging. Every suppression reason is a closed literal with a golden fixture.",
            "Diligence": "Read the weekly verdict completeness logic and reuse its fail-closed pattern. Keep raw evidence immutable; calibration is a derived view, never an in-place rewrite.",
            "Defensibility": "Thresholds live in a versioned policy record with their source and reverser. The handoff must distinguish observed disagreement from the policy decision that suppresses a winner.",
        },
        "gates": "pytest -q tests/test_antiek_bench_judge_calibration.py; mutation fixtures for every suppression reason; static no-dispatch-import gate",
        "pattern": "perspective-diverse-verify",
        "fanout": "calibration mathematician and authority-boundary refuter",
        "lenses": "position/order bias; missing-evidence false certainty; mutator-shaped output",
    },
    {
        "id": "ABJS-SPR-03",
        "slug": "weekly-verdict-integration",
        "title": "Weekly verdict integration",
        "wave": "3",
        "goal": "Show deterministic, qualitative, and disagreement evidence together without automatic promotion.",
        "context": "The weekly HTML verdict already compares keyword quality, cost, latency, availability, operator driver, and NotDiamond shadow. This sprint adds judged axes and uncertainty beside those facts, preserving the existing deterministic evidence and the structural auto_promotion=false boundary.",
        "deps": "ABJS-SPR-01 and ABJS-SPR-02; the existing weekly verdict and self-contained HTML projector.",
        "out": "No weighted composite ranking hidden from the operator, no production routing change, no scheduled paid judge calls, and no suite proposal or model installation.",
        "milestones": [
            ("Join exact evidence", "Join judged evidence only on exact week, suite, item, candidate hashes, rubric version, and allowed judge panel; reject near matches.", "Forged task, prompt, model, order, rubric, and judge variants do not change the verdict.", "substrate/antiek_bench/live/weekly_verdict.py"),
            ("Render three evidence layers", "Add deterministic keyword/availability facts, qualitative axes, and judge disagreement/calibration as separate labeled columns and structured payloads.", "The HTML never collapses the layers into an unexplained scalar and contains no prompts, responses, secrets, or free-form judge rationale.", "substrate/antiek_bench/live/weekly_verdict.py"),
            ("Preserve authority", "Keep auto_promotion=false, show every suppression reason, and require operator acknowledgment before any future recommendation export.", "AST and API-surface tests prove no install/select/dispatch callable was added and registry/suite snapshots remain unchanged.", "tests/test_antiek_bench_judged_weekly_verdict.py"),
            ("Close the decision record", "Document calibration coverage, judge cost, disagreement, and the explicit evidence threshold for considering a future advisory recommendation.", "The decision record identifies what remains unproved and never calls this a router benchmark until live judged samples exist.", "docs/decisions/antiek-bench-judged-scoring.md"),
        ],
        "rigor": {
            "Intellectual honesty": "Keep keyword proxy, judged quality, and evaluator agreement visually distinct. If no live judged samples exist, render NOT MEASURED rather than a fixture-derived recommendation.",
            "Fairness": "Show per-model cost and availability beside qualitative scores so an expensive brittle answer cannot win by prose quality alone. Do not invent a composite weight on the operator's behalf.",
            "Rigor": "Golden-test exact joins, redaction, incomplete panels, mixed versions, over-budget evidence, and auto_promotion=false in both HTML and JSON payloads.",
            "Diligence": "Extend the current verdict schema instead of creating a second dashboard. Preserve existing consumers and explicitly version the added judged-evidence section.",
            "Defensibility": "The HTML embeds input digests, rubric/policy versions, sample counts, and suppression reasons so a changed weekly result can be reconstructed without trusting narrative prose.",
        },
        "gates": "pytest -q tests/test_antiek_bench_judged_weekly_verdict.py tests/test_antiek_bench_weekly_verdict.py; HTML parser redaction gate; hardenx on merged diff",
        "pattern": "adversarial-verification",
        "fanout": "builder plus independent exact-join/privacy refuter",
        "lenses": "forged evidence join; hidden composite/promotion authority; HTML leakage",
    },
]


def sprint_page(sprint: dict[str, object]) -> str:
    body = f"""
<header class="hero"><p class="eyebrow"><a href="index.html">&larr; judged scoring</a> · {esc(sprint['id'])}</p><h1>{esc(sprint['title'])}</h1><p class="tagline">{esc(sprint['goal'])}</p><div class="meta-row"><span class="tag tag--blue">Wave {esc(sprint['wave'])}</span><span class="tag tag--yellow">ready</span><span class="tag tag--grey">Owner: isolated builder</span><span class="tag tag--grey">4 milestones</span></div></header>
<section class="block"><h2>Parent context</h2><p>{esc(sprint['context'])}</p><p>The north star is defensible task-specific model evidence for the research workstation, not a leaderboard that hides uncertainty. Every external call remains operator-gated and every output remains advisory.</p></section>
<section class="block"><h2>Goal</h2><p><strong>{esc(sprint['goal'])}</strong></p></section>
<section class="block"><h2>Technical milestones</h2>{milestones(sprint['milestones'])}</section>
<section class="block"><h2>Rigor — operating manual</h2><div class="rigor">{rigor(sprint['rigor'])}</div></section>
<section class="block"><h2>Dependencies</h2><p>{esc(sprint['deps'])}</p></section>
<section class="block"><h2>Out of scope</h2><p>{esc(sprint['out'])}</p></section>
<section class="block"><h2>Verification gates</h2><pre><code>{esc(sprint['gates'])}</code></pre><p>Every gate must exit 0. Paid/live evidence not executed is recorded as NOT RUN.</p></section>
<section class="block"><h2>Handoff packet</h2><ul><li>Commit SHA and exact files touched.</li><li>Rubric, judge, policy, and evidence schema versions.</li><li>Test commands/counts plus any live gate marked NOT RUN.</li><li>Privacy, disagreement, and authority invariants proved.</li><li>Open calibration questions and next-sprint readiness.</li></ul></section>
<section class="block" id="harness-hint" data-harness-pattern="{esc(sprint['pattern'])}" data-harness-fanout-unit="{esc(sprint['fanout'])}" data-harness-verifier-lenses="{esc(sprint['lenses'])}" data-harness-rounds-floor="1" data-harness-rounds-cap="4"><h2>Execution harness hint</h2><p><code>{esc(sprint['pattern'])}</code> · {esc(sprint['fanout'])}</p><p>{esc(sprint['lenses'])}</p></section>
<footer class="spec-footer">{esc(sprint['id'])} · generated {DATE} · source: Antiek /goal cycle sc</footer>"""
    return shell(f"{sprint['id']} — {sprint['title']}", body)


def master_page() -> str:
    cards = "".join(
        f'<a class="sprint-card" href="sprint-{index:02d}-{sprint["slug"]}.html"><span class="id">{esc(sprint["id"])}</span><span class="title">{esc(sprint["title"])}</span><span class="goal">{esc(sprint["goal"])}</span><span class="footer"><span class="tag tag--blue">Wave {esc(sprint["wave"])}</span><span class="tag tag--yellow">ready</span></span></a>'
        for index, sprint in enumerate(SPRINTS, 1)
    )
    body = f"""
<header class="hero"><p class="eyebrow">Master spec · ABJS</p><h1>Antiek-bench judged scoring</h1><p class="tagline">Versioned, blinded qualitative evidence with disagreement visible and routing authority absent.</p><div class="meta-row"><span class="tag tag--blue">executable</span><span class="tag tag--yellow">3 sprints · 3 waves</span><span class="tag tag--grey">{DATE}</span></div></header>
<section id="spec-lineage" class="block" data-spec-depth="1" data-parent-spec="../antiek-bench-live-wedge/index.html"><h2>Spec lineage</h2><p>Child of <a href="../antiek-bench-live-wedge/index.html">Antiek-bench live measured wedge</a>. This spec replaces keyword-only interpretation, not the deterministic evidence itself.</p><ul class="child-specs"></ul></section>
<section class="block"><h2>Goal</h2><p>Add reproducible qualitative evaluation for synthesis, source use, nuance, and intellectual engagement while exposing evaluator uncertainty and keeping every outcome advisory.</p><h3>Success criteria</h3><ul><li>Candidate identities and order are blinded; self-judging is rejected.</li><li>Raw qualitative evidence is immutable, versioned, crash-safe, and contains no prompt/response bodies or secrets.</li><li>Position and judge disagreement suppress winners rather than disappearing into an average.</li><li>Weekly HTML shows deterministic facts, qualitative axes, and evaluator uncertainty separately with <code>auto_promotion=false</code>.</li></ul><h3>Failure mode to avoid</h3><p>A fluent evaluator produces one confident number that silently becomes model-selection truth. This design treats a judge as a fallible measurement instrument whose version, bias, failures, and disagreement are first-class evidence.</p></section>
<section class="block"><h2>Architecture overview</h2><div class="dep-graph">live candidate outputs (memory only)\n        │\n        ▼\nblind + hash + rubric version ──► injected judge panel\n        │                              │\n        ▼                              ▼\nclaim/settle evidence journal ──► disagreement + anchors\n                                       │\nkeyword / receipts / budget ───────────┤\n                                       ▼\n                         weekly HTML, advisory only</div><h3>Key invariants</h3><ul><li>Deterministic constraints remain code; judges score only qualitative axes.</li><li>No candidate model judges itself and candidate identities never enter judge inputs.</li><li>Raw evidence is never rewritten by calibration or verdict generation.</li><li>No judged API has dispatch/install/select-driver shape.</li></ul></section>
<section class="block"><h2>Sprint roster</h2><div class="sprint-grid">{cards}</div></section>
<section class="block"><h2>Decision log</h2><table class="spec"><thead><tr><th>Decision</th><th>Why</th><th>Reconsider if</th></tr></thead><tbody><tr><td>Separate qualitative journal</td><td>Judge evidence has different privacy, versioning, and reconciliation semantics from provider billing evidence.</td><td>A single journal can preserve both schemas without coupling budget authority to evaluator failures.</td></tr><tr><td>Two-pass order swaps</td><td>Position bias is measurable and must suppress unstable winners.</td><td>A judge API proves order invariance on Antiek anchors over time.</td></tr><tr><td>No composite score</td><td>Weights would encode an unapproved product policy and hide disagreement.</td><td>The operator approves versioned task-specific weights after enough calibrated evidence.</td></tr></tbody></table></section>
<section class="block"><h2>Rejected alternatives</h2><table class="spec"><thead><tr><th>Alternative</th><th>Why rejected</th><th>Reconsider if</th></tr></thead><tbody><tr><td>One judge, one scalar</td><td>Hides order bias, judge instability, and axis tradeoffs.</td><td>Never for authoritative use; only a visibly labeled exploratory fixture.</td></tr><tr><td>Judge deterministic checks</td><td>Slower and less reliable than existing receipt/schema/provenance code.</td><td>A qualitative axis cannot be represented deterministically.</td></tr><tr><td>Persist raw answers for replay</td><td>Expands privacy and secret exposure.</td><td>Encrypted, access-scoped artifact storage with explicit retention policy exists.</td></tr><tr><td>Automatic model promotion</td><td>Evaluation uncertainty and operator preferences are not resolved.</td><td>Outside this spec; requires explicit authority policy and calibrated evidence.</td></tr></tbody></table></section>
<section class="block"><h2>Open questions</h2><table class="spec"><thead><tr><th>Question</th><th>Operating assumption</th><th>Resolver</th></tr></thead><tbody><tr><td>Which judge models receive paid live calibration?</td><td>Injected fixtures only until operator supplies distinct non-candidate judges and a cap.</td><td>Operator</td></tr><tr><td>How many human anchors are sufficient?</td><td>Expose uncalibrated until at least one versioned anchor per task class; do not invent statistical confidence.</td><td>Operator + research methodology review</td></tr><tr><td>What disagreement threshold permits an advisory winner?</td><td>Any winner flip suppresses; numeric axis thresholds stay versioned and conservative.</td><td>Calibration evidence</td></tr></tbody></table></section>
<section class="block" id="harness-hint-run" data-harness-default-pattern="adversarial-verification" data-harness-inline-only-sprints=""><h2>Execution harness hint</h2><p>Run serial waves. Every sprint needs an independent refuter because evaluator bias, evidence joins, and authority boundaries are load-bearing.</p></section>
<footer class="spec-footer">Generated by htmlspec · source: Antiek /goal cycle sc · {DATE}</footer>"""
    return shell("Antiek-bench judged scoring — Master Spec", body, wide=True)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "index.html").write_text(master_page(), encoding="utf-8")
    for index, sprint in enumerate(SPRINTS, 1):
        (ROOT / f'sprint-{index:02d}-{sprint["slug"]}.html').write_text(
            sprint_page(sprint), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
