"""Generate the self-contained floating-session workstation htmlspec."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STYLE = Path("/Users/slimydog/.agents/skills/htmlspec/templates/style.css")
DATE = "2026-07-12"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def shell(title: str, body: str, *, wide: bool = False) -> str:
    css = STYLE.read_text(encoding="utf-8")
    cls = "page page--wide" if wide else "page"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width,initial-scale=1" />'
        f"<title>{esc(title)}</title><style>{css}</style></head>"
        f'<body><main class="{cls}">{body}</main></body></html>\n'
    )


def rigor(cards: dict[str, str]) -> str:
    return '<section class="block"><h2>Rigor — operating manual</h2><div class="rigor">' + "".join(
        f'<article class="rigor-card"><span class="label">{esc(name)}</span>'
        f"<p>{esc(text)}</p></article>"
        for name, text in cards.items()
    ) + "</div></section>"


SPRINTS: list[dict[str, Any]] = [
    {
        "id": "FSW-SPR-01",
        "slug": "closed-session-lifecycle-api",
        "title": "Closed floating-session lifecycle API",
        "status": "done",
        "wave": 1,
        "goal": "Expose reopen, asset-scoped list, float/full CAS, recursive context, collective units, and confirmed merge through the existing engagement single writers.",
        "files": "interfaces/research/api/engagement_routes.py; substrate/floating_session/store.py; tests/test_engagement_routes.py",
        "milestones": [
            ("Close every request", "Use strict extra-forbid models, bounded canonical session IDs, unique lists, explicit cross-asset approval, atomic store view CAS, and revision-bound confirmed parent writes.", "Malformed, duplicate, traversal-shaped, stale-view, accidental cross-asset, incomplete-merge, unconfirmed-parent, and stale-parent requests fail before mutation."),
            ("Verify session provenance", "For every route, refresh the session from its spawn and require matching parent asset and investigation identity.", "Missing session is 404; missing or conflicting spawn linkage is a sanitized 409, never silently projected."),
            ("Compose existing context and merge writers", "Call session_research_context, sessions_collective_research, merge_sessions, and the canonical HTML projectors; do not fork twin, reference, or merge logic.", "Twin context is explicitly labeled non-mutating preview, cross-asset collective requires opt-in, draft merge leaves parent bytes unchanged, and into-parent uses the canonical store's exact revision CAS."),
            ("Prove the workstation lifecycle", "Drive open→list/get→view CAS→complete twins→context→cross-asset collective→draft→confirmed parent merge through TestClient.", "HTML is escaped and every response identifies view_format=html with exact source session provenance."),
        ],
        "out": "No frontend window chrome, new merge writer, global session enumeration, commercial book work, or claim of multi-user ownership isolation.",
        "gates": "uv run pytest -q tests/test_engagement_routes.py tests/test_floating_session.py tests/test_floating_session_context_bridge.py tests/test_session_context_flywheel.py; uv run mypy substrate/floating_session/store.py interfaces/research/api/engagement_routes.py; uv run ruff check substrate/floating_session/store.py interfaces/research/api/engagement_routes.py tests/test_engagement_routes.py",
        "rigor": {
            "1 · Intellectual honesty": "The current engagement rows contain no owner_user_id. Call this a single-operator/local workstation surface that may sit behind the app's auth mount, not authenticated ownership isolation, and return 409 when session↔spawn provenance drifts.",
            "2 · Fairness": "Cross-asset collective research is useful and intentionally allowed only after allow_cross_asset=true; destructive cross-parent merge remains forbidden so one asset cannot absorb another by UI selection error.",
            "3 · Rigor": "Test atomic stale view CAS, escaped selection HTML, incomplete sessions, parent-byte preservation in draft mode, metadata preservation, and stale parent-hash refusal for into_parent—not only successful JSON shapes.",
            "4 · Diligence": "Reuse get_session, set_view_mode, session_research_context, sessions_collective_research, merge_sessions, and canonical HTML projectors. A second session or merge store is a defect.",
            "5 · Defensibility": "Keep prompt blocks opt-in and label twin context as preview_non_mutating because it enlarges the response without writing the graph. Bind parent merge to the draft-returned hash at the canonical store write; the result hash describes the exact bytes written even if a later writer advances the parent.",
        },
        "pattern": "adversarial-verification",
        "lenses": "session↔spawn integrity and cross-asset leakage; parent mutation and HTML injection",
    },
    {
        "id": "FSW-SPR-02",
        "slug": "owned-durable-window-client",
        "title": "Owned durable window client + merge receipts",
        "status": "partial",
        "wave": 2,
        "goal": "Promote the single-operator API into an owner-scoped, multi-worker-safe browser workstation with durable merge idempotency and real floating/full window controls.",
        "files": "substrate/floating_session/{store,session,merge_receipt}.py; substrate/engagement_spine/{store,spawn,twin,merge}.py; interfaces/research/api/engagement_routes.py; apps/reading/src/{api,workspace,components/windows}/**; tests/test_{engagement_routes,floating_session,floating_session_merge_receipt}.py",
        "milestones": [
            ("Bind ownership", "Bind session-created spawns, sessions, twin context, and merged documents to request.state.user_id; preserve ownerless legacy rows only in the explicit __operator__ account.", "Foreign sessions are indistinguishable from missing; list is owner+asset scoped; same logical asset/region produces disjoint identities and twin/document namespaces across owners."),
            ("Make mutations multi-worker safe", "Replace write_text updates with atomic temp+fsync+replace under a cross-process coordinator or transactional database CAS.", "Two processes cannot lose view, completion, twin, or merge updates; injected crash leaves either the prior or complete next record."),
            ("Persist merge receipts", "Claim a bounded idempotency key against owner+parent+ordered sessions+mode+parent revision before mutation; settle the exact result afterward.", "Same key/material replays, conflicting material returns 409, and crash after write-before-response recovers without duplicate or stale parent mutation."),
            ("Wire window chrome", "Consume list/get/view/merge routes from the browser window store, persist float/full CAS before local chrome, and reopen server-owned sessions for an asset; finish context/collective/draft-confirm UI composition.", "Unit proof covers reload rehydration and server-before-local mode authority; a browser E2E must still preview draft, confirm final merge, and reject accidental cross-asset collective."),
        ],
        "out": "No provider dispatch, no automatic merge, no global public collaboration, and no weakening of the HTML-only asset contract.",
        "gates": "uv run pytest -q tests/test_session_workstation_owned.py; pnpm --dir interfaces/research/frontend test -- session-workstation; two-process crash/CAS harness; hardenx --strict --no-color .",
        "rigor": {
            "1 · Intellectual honesty": "Do not infer owner identity from asset_id, session_id, or filesystem location. This deployment's historical rows are explicitly the __operator__ account; any future import from a genuinely multi-user source requires supplied mapping or quarantine.",
            "2 · Fairness": "Steelman retaining the single-operator file stores: they are simpler and adequate locally. Replace them only at the multi-user boundary, where foreign-row ambiguity and lost updates impose the cost on users rather than maintainers.",
            "3 · Rigor": "Use two-process races and crash injection around receipt claim, parent write, and receipt settlement; one happy-path browser test cannot prove exactly-once merge behavior.",
            "4 · Diligence": "Read the app auth middleware, owner-bound Midnight Oil store, frontend windowsStore, and engagement file writers before choosing the coordinator/database. Reuse an existing owner/CAS convention where compatible.",
            "5 · Defensibility": "Record the owner migration, idempotency material hash, parent revision rule, and lock order in code and the handoff. A later agent must reconstruct why a merge replay was accepted or quarantined.",
        },
        "pattern": "fan-out-and-synthesize",
        "lenses": "owner isolation/migration; two-process receipt and parent-write crash safety; browser reload/confirmation behavior",
    },
    {
        "id": "FSW-SPR-03",
        "slug": "owner-native-capability-parity",
        "title": "Owner-native engagement capability parity",
        "status": "done",
        "wave": 3,
        "goal": "Move reference attachment, progress, evidence, context search, twin notes, hydration, and collective context behind owner-verified session authority without duplicating canonical writers.",
        "files": "substrate/engagement_spine/{store,source_refs,progress,evidence,context_search,research_context,collective,twin,twin_promote,hydrate}.py; interfaces/research/api/engagement_routes.py; apps/reading/src/{api/engagement.ts,components/engagement,components/windows/DeepResearchSessionHost*}; tests/test_engagement_routes.py",
        "milestones": [
            ("Close store authority", "Add owner-verifying spawn/document reads and atomic mutation callbacks to memory and file stores; quarantine ownerless rows from normal accounts.", "Same logical identifiers remain disjoint by owner, foreign rows read as missing, and compound append/update operations execute under the store lock."),
            ("Expose session capability routes", "Compose references, progress, evidence, twins, hydration, promotion preview, context search, research context, and collective context only after resolving the authenticated session owner.", "Strict request models reject extras; every endpoint returns 404 for a foreign session and never accepts caller-supplied owner identity."),
            ("Migrate the research window", "When session_id exists, route every primary panel through session APIs and remove global spawn merge/collective authority from that browser path.", "Attach/progress/evidence/context/twins survive authenticated reload; collective uses same-parent session IDs; legacy operator panels remain available only on explicitly sessionless surfaces."),
            ("Keep promotion honest", "Offer twin promotion as a non-mutating preview until graph ownership and an owner-scoped promotion transaction exist.", "The response labels preview_non_mutating; no graph edge is written, and the next sprint starts at owner-scoped graph persistence rather than mistaking a preview for promotion."),
        ],
        "out": "No claim of owner-scoped graph promotion, shared workspace ACLs, arbitrary cross-asset twin merging, provider dispatch, or automatic parent mutation.",
        "gates": "uv run pytest -q tests/test_engagement_routes.py tests/test_floating_session.py tests/test_floating_session_context_bridge.py tests/test_session_context_flywheel.py; uv run mypy --strict substrate/engagement_spine/*.py interfaces/research/api/engagement_routes.py; npm --prefix apps/reading run typecheck; npm --prefix apps/reading run build; npx --prefix apps/reading vitest run <targeted engagement suites>; hardenx --strict --no-color .",
        "rigor": {
            "1 · Intellectual honesty": "Session-scoped twin promotion is preview-only because the graph substrate is not owner-namespaced. The UI and API must not imply that preview results were persisted.",
            "2 · Fairness": "Legacy operator routes remain for local workflows, but authenticated session windows do not inherit their global identifier authority. Existing local users keep a path while multi-user users gain isolation.",
            "3 · Rigor": "Test Alice and Bob with identical logical asset IDs through attach, hydrate, progress, twin, evidence, context search, and foreign-session 404 behavior; test atomic mutations rather than only endpoint shapes.",
            "4 · Diligence": "Thread owner_id through the canonical functions and use store mutation callbacks. Do not clone engagement behavior inside route handlers or React panels.",
            "5 · Defensibility": "Collective authority is a list of owner-resolved session IDs sharing a parent. Recent global spawn rings and arbitrary client-supplied spawn IDs are not authorization evidence.",
        },
        "pattern": "adversarial-verification",
        "lenses": "owner confusion and foreign logical-ID collision; lost updates in compound file mutations; frontend fallback to legacy global routes",
    },
    {
        "id": "FSW-SPR-04",
        "slug": "confirmed-owner-graph-promotion",
        "title": "Confirmed owner-graph twin promotion",
        "status": "done",
        "wave": 4,
        "goal": "Turn a reviewed session-twin preview into an explicitly confirmed, owner-isolated, crash-recoverable graph promotion without forking Antiek's canonical insight/question writer.",
        "files": "substrate/graph_per_user/runtime.py; substrate/engagement_spine/{twin_promote,twin_promotion_receipt}.py; interfaces/research/api/engagement_routes.py; apps/reading/src/{api/engagement.ts,components/engagement/TwinNotesPanel*}; tests/test_{engagement_routes,twin_promotion_receipt}.py",
        "milestones": [
            ("Pin the reviewed preview", "Hash the normalized selected twin identities, kinds, canonical text, owner, session, asset, and investigation into a domain-separated preview revision returned by the non-mutating endpoint.", "Confirm requires that exact 64-hex preview revision and refuses note drift, selection drift, or reuse of an idempotency key with different material before any graph write."),
            ("Route to the owner's physical graph", "Keep __operator__ on the canonical graph for compatibility; route every authenticated non-operator to a domain-hashed per-owner DuckDB path and initialize it through the canonical graph schema.", "Alice and Bob promoting identical text produce the same semantic node identity inside different files; neither file contains the other's note, and no non-operator falls back to the global graph."),
            ("Claim, transact, and recover", "Claim an owner-scoped durable receipt, promote every selected note on one write-locked DuckDB transaction through promote_insight/promote_question, then settle the exact result; replay an applied receipt byte-for-byte.", "A conflict returns 409; a crash after graph commit but before receipt settlement can safely repeat the content-addressed transaction and settle; partial multi-note promotion is impossible."),
            ("Require visible confirmation", "The browser's first action remains preview-only and renders the exact reviewed node count/revision; a distinct confirm control sends a fresh bounded idempotency key and changes the UI to confirmed only after the server returns an applied receipt.", "Opening/reloading never promotes; preview chrome says non-mutating; confirm success shows receipt and owner-graph state; 409 preview drift clears stale confirmation and requires review again."),
        ],
        "out": "No global graph sharing, no automatic promotion, no owner identity in node labels or filenames, no arbitrary cross-asset twin lookup, and no claim that per-user DuckDB encryption/KMS is production-wired by this sprint.",
        "gates": "uv run pytest -q tests/test_twin_promotion_receipt.py tests/test_engagement_routes.py tests/test_graph_insight_question.py; uv run mypy --strict substrate/graph_per_user/runtime.py substrate/engagement_spine/twin_promotion_receipt.py substrate/engagement_spine/twin_promote.py interfaces/research/api/engagement_routes.py; uv run ruff check <changed-python>; npx --prefix apps/reading vitest run src/api/engagement.test.ts src/components/engagement/TwinNotesPanel.test.tsx; npm --prefix apps/reading run typecheck; npm --prefix apps/reading run build; hardenx . --strict --no-color",
        "rigor": {
            "1 · Intellectual honesty": "API-level owner checks do not make a global DuckDB owner-scoped. Prove physical path separation for non-operators and label KMS/encryption as a remaining deployment concern rather than implying that a hashed path encrypts data.",
            "2 · Fairness": "The operator keeps the existing canonical graph so local installations do not lose accumulated memory. Authenticated users receive separate graphs; future opt-in federation must be explicit rather than extracting network effects from private notes by default.",
            "3 · Rigor": "Test identical Alice/Bob text, foreign session 404, preview drift before mutation, idempotency material conflict, concurrent confirmation, multi-note rollback, and crash-after-commit replay. A stable node id alone is not proof of a stable transaction result.",
            "4 · Diligence": "Reuse twin_promote_context_payload and insight_question.promote_* on one caller-owned LockedConnection. Reuse the engagement store's owner-aware atomic document mutation for receipts or justify a separate store; never write graph SQL in the route.",
            "5 · Defensibility": "The receipt records owner, session, preview revision, graph path digest, ordered selected note identities, result revision, and terminal state. These fields must explain exactly why a replay was accepted without exposing owner IDs in public artifacts.",
        },
        "pattern": "perspective-diverse-verify",
        "lenses": "physical owner-graph isolation and global fallback; receipt crash/replay and batch atomicity; browser preview-versus-confirm mutation honesty",
    },
]


def sprint_page(row: dict[str, Any]) -> str:
    milestones = "".join(
        f'<div class="milestone"><div class="num">{index}</div><div><div class="title">{esc(title)}</div>'
        f'<p class="desc">{esc(desc)}</p><div class="criteria"><strong>Acceptance:</strong> {esc(criteria)}</div></div></div>'
        for index, (title, desc, criteria) in enumerate(row["milestones"], 1)
    )
    body = f"""<header class="hero"><p class="eyebrow"><a href="index.html">&larr; Floating-session workstation</a> · {esc(row['id'])}</p><h1>{esc(row['title'])}</h1><p class="tagline">{esc(row['goal'])}</p><div class="meta-row"><span class="tag tag--blue">Wave {esc(row['wave'])}</span><span class="tag tag--{'green' if row['status']=='done' else 'yellow'}">{esc(row['status'])}</span><span class="tag tag--grey">4 milestones</span></div></header>
<section class="block"><h2>Parent context</h2><p>Antiek already has floating-session, engagement-spine, twin-note, collective-context, and merge substrate. This sprint owns the exact product seam named below and must compose those single writers.</p><p>The hard boundary is HTML-native research continuity: sessions remain traceable to their parent asset and spawn, context is explicit, and destructive parent mutation is never implicit.</p></section>
<section class="block"><h2>Goal</h2><p>{esc(row['goal'])}</p><p><strong>Owning files:</strong> <code>{esc(row['files'])}</code></p></section>
<section class="block"><h2>Technical milestones</h2>{milestones}</section>
{rigor(row['rigor'])}
<section class="block"><h2>Dependencies</h2><ul><li>Existing engagement_spine and floating_session canonical writers.</li><li>Authenticated operator middleware for production exposure.</li><li>Wave 2 waits for FSW-SPR-01 contract stability.</li></ul></section>
<section class="block"><h2>Out of scope</h2><p>{esc(row['out'])}</p></section>
<section class="block"><h2>Verification gates</h2><pre><code>{esc(row['gates'])}</code></pre><p>Every command must exit 0. Skipped gates are recorded as NOT RUN.</p></section>
<section class="block"><h2>Handoff packet</h2><pre><code>## {esc(row['id'])} handoff\nStatus: done | partial | blocked\nFiles touched: path:line + reason\nMilestones: exact result per item\nGates: command + exit + count\nAssumptions and rejected alternative\nOpen questions and next-start condition</code></pre></section>
<section class="block" id="harness-hint" data-harness-pattern="{esc(row['pattern'])}" data-harness-fanout-unit="file-disjoint owner/store/frontend seams" data-harness-verifier-lenses="{esc(row['lenses'])}" data-harness-rounds-floor="1" data-harness-rounds-cap="6"><h2>Execution harness hint</h2><p>{esc(row['lenses'])}</p></section>
<footer class="spec-footer">{esc(row['id'])} · generated {DATE} · source: active Antiek /goal Cycle 9</footer>"""
    return shell(f"{row['id']} · {row['title']}", body)


def index_page() -> str:
    cards = "".join(
        f'<a class="sprint-card" href="sprint-{index:02d}-{row["slug"]}.html"><span class="id">{esc(row["id"])}</span><span class="title">{esc(row["title"])}</span><span class="goal">{esc(row["goal"])}</span><span class="footer"><span class="tag tag--blue">Wave {row["wave"]}</span><span class="tag tag--{"green" if row["status"]=="done" else "yellow"}">{row["status"]}</span></span></a>'
        for index, row in enumerate(SPRINTS, 1)
    )
    body = f"""<header class="hero"><p class="eyebrow">Master spec · ANT-FSW</p><h1>Floating-session research workstation</h1><p class="tagline">Make every highlight research window reopenable, context-bearing, collectively promptable, and safely mergeable.</p><div class="meta-row"><span class="tag tag--blue">Status: owner graph promotion in execution</span><span class="tag tag--yellow">Owner: Antiek /infinite</span><span class="tag tag--grey">4 sprints · 4 waves</span></div></header>
<section id="spec-lineage" class="block" data-spec-depth="0" data-parent-spec=""><h2>Spec lineage</h2><p>Root spec. No parent and no child specs yet; ownership and browser implementation remain Sprint 2 rather than a decorative subtree.</p><ul class="child-specs"></ul></section>
<section class="block"><h2>Goal</h2><p>Close the missing API lifecycle over Antiek's existing floating-session substrate, then define the exact ownership, durability, idempotency, and browser work required for a multi-user workstation.</p><h3>Success criteria</h3><ul><li>Session identity maps to one matching spawn/asset/investigation or fails reconciliation.</li><li>Context and collective operations are explicit, bounded, HTML-native, and cross-asset conscious.</li><li>Draft merge leaves parent content unchanged; parent merge requires confirmation plus the exact previewed parent hash and preserves unrelated metadata.</li><li>Future ownership and multi-worker work has executable crash and browser gates.</li></ul></section>
<section class="block"><h2>Architecture overview</h2><div class="dep-graph">Highlight → FloatingSession → verified Spawn provenance\n             ├→ context pack → HTML / optional prompt\n             ├→ collective unit (cross-asset opt-in)\n             └→ draft preview → confirmed parent merge\nFuture: authenticated owner + CAS/receipt store + browser windowsStore</div><h3>Key invariants</h3><ul><li>No second twin, context, collective, merge, or HTML writer.</li><li>No global session enumeration and no claim of owner isolation until owner columns exist.</li><li>No implicit graph promotion, prompt-body exposure, cross-asset collective, or parent mutation.</li></ul></section>
<section class="block"><h2>Sprint roster</h2><div class="sprint-grid">{cards}</div></section>
<section class="block"><h2>Rejected alternatives</h2><table class="spec"><thead><tr><th>Alternative</th><th>Why rejected</th><th>Reconsider if</th></tr></thead><tbody><tr><td>New session/merge service</td><td>Duplicates shipped engagement_spine writers and breaks recursive twin provenance.</td><td>The canonical spine is deliberately retired through a migration.</td></tr><tr><td>Silent cross-asset collective</td><td>A multi-selection mistake can mix unrelated or future foreign-owner context.</td><td>Ownership policy explicitly defines shared workspaces and UI communicates scope.</td></tr><tr><td>Automatic into-parent merge</td><td>Destroys the draft-review boundary the product vision explicitly asks for.</td><td>Never; confirmation may become a richer review transaction, not disappear.</td></tr><tr><td>API-only graph ownership</td><td>An owner-verified route still deposits private note labels into the shared graph, where global readers or identical-text dedup can cross account boundaries.</td><td>The graph schema and every read surface gain a proven row-level owner policy; physical per-owner graphs remain the safer current contract.</td></tr><tr><td>Content hash as the whole receipt</td><td>Stable node ids prevent duplicate rows but do not pin the reviewed selection, prevent idempotency-key reuse, make a multi-note batch atomic, or replay the exact response after a crash.</td><td>Never for explicit user confirmation; content addressing remains one layer inside the receipt transaction.</td></tr></tbody></table></section>
<section class="block"><h2>Open questions</h2><table class="spec"><tbody><tr><td>Which authenticated workspace owns pre-owner rows?</td><td>Do not guess; operator-supplied migration mapping or quarantine.</td><td>Operator + Sprint 2 executor</td></tr><tr><td>Which browser surface owns window state?</td><td>Extend the shipped windowsStore rather than create another chrome store.</td><td>Frontend implementation archaeology</td></tr></tbody></table></section>
<section class="block" id="harness-hint-run" data-harness-default-pattern="adversarial-verification" data-harness-inline-only-sprints="FSW-SPR-01"><h2>Execution harness hint</h2><p>SPR-01 is a tight existing-writer composition. SPR-02 may fan out owner/store and frontend work only in isolated file scopes, then synthesize behind crash and browser gates.</p></section>
<footer class="spec-footer">Generated by htmlspec · source: active Antiek /goal Cycle 9 · {DATE}</footer>"""
    return shell("Floating-session workstation — Master Spec", body, wide=True)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "index.html").write_text(index_page(), encoding="utf-8")
    for index, row in enumerate(SPRINTS, 1):
        (ROOT / f"sprint-{index:02d}-{row['slug']}.html").write_text(
            sprint_page(row), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
