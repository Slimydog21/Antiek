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
    {
        "id": "FSW-SPR-05",
        "slug": "owner-native-graph-recall",
        "title": "Owner-native graph recall and thought-partner grounding",
        "status": "done",
        "wave": 5,
        "goal": "Close the personal-memory write-to-use loop by combining public canonical corpus retrieval with the authenticated owner's physically isolated insight/question graph in thought-partner and explicit context-picker reads.",
        "files": "substrate/graph_per_user/runtime.py; substrate/graph/personal_recall.py; interfaces/research/api/app.py; interfaces/research/api/engagement_routes.py; tests/test_{owner_graph_recall,thought_partner,compose_context,engagement_routes}.py",
        "milestones": [
            ("Resolve reads without side effects", "Add a read resolver that returns the operator canonical graph or an existing hashed owner graph, but never creates directories, initializes a DB, or falls back to the canonical graph for an absent non-operator partition.", "An unmaterialized Alice read is honestly empty while a canonical leak-canary remains invisible; resolving readiness does not create Alice's shard directory or graph file."),
            ("Recall private graph nodes semantically", "Search insight/question node embeddings with the same pinned provider identity used at promotion, retain a lexical fallback for legacy nodes without identity metadata, and return bounded provenance-bearing context units.", "A promoted twin whose meaning matches the prompt reaches selected_notes even without chunks; incompatible embeddings are excluded rather than compared, and duplicate lexical/semantic hits collapse by node id."),
            ("Fuse declared public and private scopes", "Keep canonical chunks and gated public nodes as the explicit shared corpus; for non-operators add only their personal graph results, rank and cap the union, and label source scope. Keep __operator__ on its one canonical graph without double-reading.", "Alice receives public corpus plus Alice nodes, Bob receives public corpus plus Bob nodes, neither receives the other's node, and operator grounding remains byte-compatible for existing chunk hits."),
            ("Close prompt and picker seams", "Derive owner identity only from request.state, thread it into /thought-partner, and resolve @insight from the personal graph before a policy-gated canonical lookup; expose owner graph readiness without returning filesystem paths or accepting caller-supplied owners.", "Dispatched prompts contain the promoted private twin only for its owner; foreign explicit node ids are missing; readiness reports operator_canonical, physically_isolated, or unmaterialized with a non-reversible path digest."),
        ],
        "out": "No implicit federation, no owner-supplied graph id, no migration of books/documents into personal graph files, no claim that global public corpus and private memory are one physical database, and no background-worker routing beyond the prompt/context surfaces proven here.",
        "gates": "uv run pytest -q tests/test_owner_graph_recall.py tests/test_thought_partner.py tests/test_thought_partner_chunk_text_key.py tests/test_compose_context.py tests/test_engagement_routes.py; uv run mypy --strict substrate/graph_per_user/runtime.py substrate/graph/personal_recall.py interfaces/research/api/app.py interfaces/research/api/engagement_routes.py; uv run ruff check <changed-python>; hardenx . --strict --no-color",
        "rigor": {
            "1 · Intellectual honesty": "A physically isolated personal graph currently holds promoted insight/question nodes, not the user's whole document corpus. Report grounding as a declared fusion of canonical gated corpus plus private owner memory; do not call either side the complete knowledge base.",
            "2 · Fairness": "Non-operators should not lose shared public research merely because private notes moved to separate files, while operators must not pay a duplicate-read penalty against their canonical graph. Preserve both constituencies through an explicit two-scope fusion only for non-operators.",
            "3 · Rigor": "Seed distinct Alice, Bob, and canonical leak-canary nodes, then prove the exact dispatched prompt and @insight response for all three identities. Also test absent files, incompatible embedding fingerprints, duplicate fusion, bounded ranking, and a resolver that performs no filesystem mutation.",
            "4 · Diligence": "Reuse search(), the canonical retrieval gate, request.state.user_id, owner_graph_db_path, and the existing thought-partner selected_notes contract. Do not add an ambient current-owner global, a second auth parser, or an unreviewed vector store.",
            "5 · Defensibility": "Every recall item carries a declared canonical_corpus or personal_owner scope and stable node/chunk identity. Readiness exposes state and path digest—not raw path or owner input—so an operator can distinguish empty, absent, and routed graphs without creating a new disclosure surface.",
        },
        "pattern": "perspective-diverse-verify",
        "lenses": "canonical/public versus private scope fusion; cross-owner prompt exfiltration and absent-file fallback; embedding compatibility and explicit @insight authority",
    },
    {
        "id": "FSW-SPR-06",
        "slug": "production-multi-user-identity",
        "title": "Production multi-user identity and revocable sessions",
        "status": "done",
        "wave": 6,
        "goal": "Turn Antiek's owned magic-link login into a real multi-user credential path with stable opaque account identity, server-derived roles, revocable sessions, and a strictly separate operator compatibility lane.",
        "files": "substrate/auth/{account_store,magic_link}.py; substrate/multi_user/auth.py; interfaces/research/api/{auth,app,books}.py; apps/reading/src/lib/auth.tsx; tests/test_{auth_account_store,magic_link_auth,api_auth_state,multi_user_owner_path}.py",
        "milestones": [
            ("Persist stable account identity", "Add a transactional SQLite auth registry keyed by opaque user_id with unique normalized email, closed user/operator roles, active/disabled status, and atomic first-login creation under an explicit operator_only, allowlist, or open registration policy.", "Two concurrent callbacks for one email resolve one user_id; two emails never collide; changing display email never becomes the storage key; disabled accounts fail before owner data access."),
            ("Issue and revoke bound sessions", "Add one-time magic-link nonces and server-side session rows; bind the signed cookie to user_id, email, and opaque session_id while deriving scopes from the current account row on every request.", "Magic links cannot be replayed; logout revokes the exact session before clearing the cookie; expiry, revoked session, user/email drift, wrong signature, and missing multi-user session authority all return 401 without legacy fallback."),
            ("Separate users, operators, and services", "Attach request.state from one closed UserClaims shape. User magic-link credentials receive basic/private_research only; operator allowlist, operator bearer, Cloudflare, service token, and local-dev compatibility retain __operator__ but never accept caller-supplied owner identity.", "A user cookie cannot reach operator-only legacy routes or `operator_only` rights policy; operator paths remain compatible; service credentials never impersonate a personal user; `/auth/me` reports role/scopes derived server-side."),
            ("Prove the owner-native product chain", "Use two real magic-link requests/callbacks and cookies—not injected middleware—to run Alice and Bob through session open, twin record, preview, confirmed promotion, graph recall, and captured thought-partner dispatch.", "Each prompt contains shared public evidence plus only its credential owner's promoted canary; logout immediately blocks replay; disabled Alice remains blocked while Bob and operator remain available; no raw email appears in graph paths or owner document IDs."),
        ],
        "out": "No social login/JWKS dependency, password database, organization/team ACL, email-change UI, billing entitlement, public federation, or conversion of Cloudflare/service credentials into personal account identities.",
        "gates": "uv run pytest -q tests/test_auth_account_store.py tests/test_magic_link_auth.py tests/test_api_auth_state.py tests/test_multi_user_owner_path.py tests/test_owner_read_path.py tests/test_engagement_routes.py tests/test_thought_partner.py; uv run mypy --strict substrate/auth/account_store.py substrate/auth/magic_link.py substrate/multi_user/auth.py interfaces/research/api/auth.py; uv run ruff check <changed-python>; npm --prefix apps/reading test -- src/lib/auth.test.ts; npm --prefix apps/reading run typecheck; npm --prefix apps/reading run build; hardenx . --strict --no-color",
        "rigor": {
            "1 · Intellectual honesty": "The owned HMAC cookie is not an external JWT and needs no invented issuer/JWKS story; its audience is the domain-separated Antiek session signature. Call multi-user production-capable only when the server-side account and session rows—not cookie email—are the current authority.",
            "2 · Fairness": "Existing operator and local installations keep their explicit compatibility paths, while normal users receive no operator inheritance. Open registration is opt-in; closed deployments can allowlist users without turning every allowlisted email into an operator.",
            "3 · Rigor": "Race first-account creation and nonce consumption, replay cookies after logout, disable an account mid-session, mutate cookie user/email/session fields, and prove a normal user cannot cross the legacy-route or owner-read policy boundaries. Happy-path `/auth/me` is insufficient.",
            "4 · Diligence": "Reuse the shipped magic-link signer, HttpOnly cookie attributes, operator allowlist, UserClaims, and frontend auth refresh. Do not introduce JWT dependencies, trust email as owner_id, or add a second browser identity store.",
            "5 · Defensibility": "Persist account role/status and session revocation as server truth; signed cookies carry only identity references. Registration mode and user allowlist are explicit config, and every fallback is named so a missing auth database cannot silently become operator access.",
        },
        "pattern": "perspective-diverse-verify",
        "lenses": "credential-to-owner binding and replay; operator privilege confusion and rights-policy escalation; concurrent account/session durability and browser logout",
    },
    {
        "id": "FSW-SPR-07",
        "slug": "owned-collective-discovery-selection",
        "title": "Owner-wide session discovery and explicit collective selection",
        "status": "done",
        "wave": 7,
        "goal": "Make the HTML workstation discover every durable session owned by the authenticated account and compose an exact user-selected set into a non-mutating collective preview, with explicit cross-asset consent and merge authority derived from that reviewed set.",
        "files": "substrate/floating_session/{store,session}.py; interfaces/research/api/engagement_routes.py; apps/reading/src/api/engagement.ts; apps/reading/src/components/windows/DeepResearchSessionHost.tsx; tests/test_{floating_session_store,engagement_routes,multi_user_owner_path}.py; apps/reading/src/components/windows/DeepResearchSessionHost.test.tsx",
        "milestones": [
            ("Index every owned session", "Extend memory and durable stores with an owner-wide index that never scans or returns another owner's rows. Keep the existing owner+asset index for fast asset reopen, and fail reconciliation if either durable index points at a missing or owner-drifted row.", "Sessions across multiple assets and process restarts are discoverable by opaque owner identity; corrupt/missing/foreign index entries fail closed; no email or caller-supplied graph path enters storage identity."),
            ("Expose bounded owner discovery", "Add a GET owner-session route before the dynamic session-id route, with server-derived owner, stable ordering, store-level limit/cursor paging, sanitized session descriptors, and full session↔spawn provenance verification only for the returned page plus lookahead.", "Alice sees all and only Alice's sessions across assets; Bob and operator remain disjoint; malformed cursor/limit and durable reconciliation faults return stable errors without existence disclosure; one request never reads every session row."),
            ("Require exact browser selection", "Replace the implicit all-open-sessions collective with an incrementally paged discovery-backed checkbox list. Seed only the current session, require at least two explicit selections to compose, show asset/status/goal provenance, and require an explicit cross-asset checkbox before sending allow_cross_asset=true.", "Closed-tab/device sessions appear page by page; unselected sessions never enter request payloads; a failed later-page retry preserves already loaded selections while the server revalidates the retried page; busy/error/retry/empty states are visible; collective HTML remains sandboxed and non-mutating."),
            ("Bind merge to the reviewed subset", "Derive draft-merge eligibility from selected completed sessions on the current parent only. Clear collective and merge previews whenever selection changes; preserve the existing exact parent hash, receipt, and confirm boundary for into-parent mutation.", "Incomplete or cross-parent selections may contribute only to collective context, never parent merge; confirm is impossible after selection drift; draft preview leaves the parent unchanged and an exact reviewed selection is carried into the receipt-backed write."),
        ],
        "out": "No persisted team/shared collective, automatic selection based on semantic similarity, implicit cross-asset approval, background agent dispatch, deletion/archive UI, or weakening of the existing parent-hash and idempotency confirmation boundary.",
        "gates": "uv run pytest -q tests/test_floating_session_store.py tests/test_engagement_routes.py tests/test_multi_user_owner_path.py tests/test_session_workstation_owned.py; uv run mypy --strict substrate/floating_session/store.py substrate/floating_session/session.py interfaces/research/api/engagement_routes.py; uv run ruff check <changed-python>; npm --prefix apps/reading test -- src/components/windows/DeepResearchSessionHost.test.tsx src/api/engagement.test.ts; npm --prefix apps/reading run typecheck; npm --prefix apps/reading run build; hardenx . --strict --no-color",
        "rigor": {
            "1 · Intellectual honesty": "The owner-wide index discovers durable session descriptors, not every research artifact in Antiek and not a persisted collaborative workspace. Label collective HTML as a preview and keep incomplete sessions context-eligible while stating plainly that only completed, same-parent selections are mergeable.",
            "2 · Fairness": "A user returning from another tab/device should not lose sessions merely because the local windowsStore forgot them, while a user with many sessions should not have all of them silently injected. Server discovery plus explicit checkbox selection serves both without making convenience state into authority.",
            "3 · Rigor": "Race and restart the durable owner index; inject missing, wrong-owner, and wrong-parent rows; then drive real Alice/Bob credentials across two assets. In the browser, prove exact request payloads after select/deselect, explicit cross-asset consent, preview invalidation on selection drift, and merge exclusion for incomplete or foreign-parent rows.",
            "4 · Diligence": "Extend SessionStore and reuse _verified_session, sessions_collective_research, mergeEngagementSessions, the existing sandboxed HTML preview, and windowsStore descriptors. Do not create a second collective writer, trust client owner_id, or replace receipt-backed parent mutation.",
            "5 · Defensibility": "Stable ordering and cursor semantics belong in the route contract and tests; the file index is domain-hashed by opaque owner and validates every referenced row. The UI displays exactly why a selected row can contribute context but cannot merge, so future agents can reconstruct every authorization and product boundary from code and response provenance.",
        },
        "pattern": "perspective-diverse-verify",
        "lenses": "durable owner-index reconciliation and enumeration; exact checkbox/cross-asset request authority; preview invalidation and receipt-bound parent mutation",
    },
    {
        "id": "FSW-SPR-08",
        "slug": "durable-collective-research-units",
        "title": "Durable collective research units and follow-on work",
        "status": "done",
        "wave": 8,
        "goal": "Turn an authenticated user's exact reviewed multi-session preview into an immutable owner-native research unit that can seed cohesive follow-on research or an HTML-first written analysis without losing source provenance or mutating source assets.",
        "files": "substrate/engagement_spine/collective.py; substrate/floating_session/{collective_unit,context_bridge,session}.py; interfaces/research/api/engagement_routes.py; apps/reading/src/{api/engagement.ts,components/windows/DeepResearchSessionHost*}; tests/test_{collective_unit,engagement_routes,multi_user_owner_path}.py",
        "milestones": [
            ("Pin and confirm the reviewed unit", "Return a domain-separated SHA-256 revision over owner, ordered source sessions, request controls, merged context, research outputs, and prompt. Confirmation recomputes under current session authority, requires the exact revision and a bounded idempotency key, then persists one immutable owner-owned unit.", "Selection, output, twin, reference, owner, query, consent, or preview-option drift returns 409 before persistence; replay returns the same unit; conflicting key material fails closed; no caller-supplied owner is accepted."),
            ("Preserve complete provenance", "Carry source session, spawn, asset, investigation, status, output text, twin, reference, tier, model, and preview identities into the durable unit and its HTML projection. Keep full output in storage while bounding prompt projection.", "A unit can explain every source byte and distinguish incomplete/no-output sessions; cross-owner reads are 404; source rows and parent documents remain byte-identical after confirmation."),
            ("Launch cohesive follow-on research", "From an owned confirmed unit, reserve an idempotent floating or full research session using its bounded prompt, explicit member-asset anchor, current model choice, and reviewed/reselected research tier; record source_collective_id on the session.", "Retry returns the same session; anchor outside the unit is rejected; another owner cannot launch it; UI retains cost projection and model/tier controls and does not claim dispatch, spend, or budget enforcement before those systems execute."),
            ("Create an HTML-first written analysis", "Create a deterministic owner-owned draft document from the unit's complete outputs, twins, and references. Return sandboxable HTML plus source provenance and never route cross-asset work through the same-parent parent-merge writer.", "Retry returns the same draft; a reused key with conflicting intent fails; all source assets remain unchanged; browser actions are unavailable until the exact preview is confirmed and are invalidated on selection/query/consent drift."),
        ],
        "out": "No autonomous provider dispatch, team/shared collective ACLs, silent budget consumption, automatic source merge, marketplace work, arbitrary non-member anchor, or claim that a reserved research session is completed research.",
        "gates": "uv run pytest -q tests/test_collective_unit.py tests/test_engagement_routes.py tests/test_multi_user_owner_path.py; uv run mypy --strict <changed-python>; uv run ruff check <changed-python>; npm --prefix apps/reading test -- src/components/windows/DeepResearchSessionHost.test.tsx src/api/engagement.test.ts; npm --prefix apps/reading run typecheck; npm --prefix apps/reading run build; hardenx . --strict --no-color",
        "rigor": {
            "1 · Intellectual honesty": "A follow-on launch currently reserves an engagement session; it is not proof of provider dispatch, completed research, charged spend, or budget enforcement. Preserve model/tier and the existing projection UI while naming that remaining execution seam.",
            "2 · Fairness": "Cross-asset synthesis is a first-class user need, but it must not silently choose one parent as authoritative. Require explicit consent and a member anchor for research; produce a new draft for analysis so every source remains equal and unchanged.",
            "3 · Rigor": "Test real Alice/Bob credentials, stale preview after every mutable source surface, idempotency replay/conflict, crash recovery, hostile HTML, oversized output projection, non-member anchors, and exact source-document immutability.",
            "4 · Diligence": "Reuse owner-aware engagement documents, session/spawn verification, canonical floating-session reservation, source-reference parsing, decision-tree model selection, tier normalization, and sandboxed HTML hosting. Do not add another identity, session, or parent-merge writer.",
            "5 · Defensibility": "The persisted unit and every descendant record the preview revision, ordered source identities, owner scope, launch/draft identity, and immutable creation material so a future agent can reconstruct why each byte was authorized.",
        },
        "pattern": "adversarial-verification",
        "lenses": "preview drift and receipt recovery; owner/provenance isolation and prompt bounding; browser confirmation invalidation and source immutability",
    },
    {
        "id": "FSW-SPR-09",
        "slug": "collective-discovery-lineage",
        "title": "Collective discovery, reopen, and descendant lineage",
        "status": "done",
        "wave": 9,
        "goal": "Make every confirmed owner-native collective unit discoverable and reopenable after reload or on another device, with explicit, recoverable lineage to its research-session and written-analysis descendants and live execution truth.",
        "files": "substrate/engagement_spine/store.py; substrate/floating_session/collective_unit.py; interfaces/research/api/engagement_routes.py; apps/reading/src/{api/engagement.ts,components/windows/DeepResearchSessionHost*}; tests/test_{engagement_owned_store,engagement_routes,multi_user_owner_path}.py",
        "milestones": [
            ("Discover canonical unit rows", "Extend the owner-aware engagement store with bounded logical-prefix/keyset listing. The canonical immutable cunit row remains discovery authority; file storage selects only the owner-hashed prefix and deserializes at most limit+1 matching rows under a 32 MB aggregate read cap, while memory storage applies identical ordering/cursor/byte rules.", "GET owner collectives returns stable cunit identity order with limit 1..20 (default 5), a 32 MB storage-page ceiling, and N+1 next-cursor semantics; a foreign cursor, malformed row, physical/embedded identity mismatch, wrong owner/type, or oversized page fails closed; a row written before process death is discoverable without a second index repair transaction."),
            ("Record repairable descendant lineage", "Store one separate owner-owned lineage document per immutable unit, capped at 1 MB and 1,000 descendants. Append one bounded content-addressed edge after research receipt settlement or written-draft persistence, and repeat the append on every applied replay so a crash between child creation and lineage write self-repairs.", "Edges contain closed child kind/id, parent unit/revision, bounded creation provenance, and no mutable source copy; duplicate replay is byte-idempotent; a different edge reusing a child id conflicts; unit bytes never change; injected failure after child persistence is repaired on retry; the cap fails explicitly rather than silently dropping history."),
            ("Project live execution truth", "Keyset-page lineage independently from unit discovery. Resolve research-session status from the canonical owner-verified session/spawn on every projected page; project written drafts from their owned durable row. Missing or owner-drifted descendants are labeled reconciliation-required without exposing foreign existence, never silently reported complete.", "Reserved/running/complete/failed reflects the current spawn-backed session; written analysis remains draft unless its canonical row says otherwise; descendants from another owner are absent/404; list summaries include at most five edges plus a cursor, detail pages at most 100, and all summary fields reject malformed durable types rather than coercing them."),
            ("Reopen saved work in the workstation", "Add incremental collective history to the owner-native research host. Load only the first page on mount, retry/load more without losing rows, show assets/sources/tier/descendant states, and reopen a selected unit as sandboxed HTML or restore it as the active confirmed authority for explicit continue/write actions.", "A fresh mount with empty windowsStore rediscovers confirmed units; Reopen opens one stable hosted HTML window; Use unit enables descendants from that unit rather than current checkbox selection; auth/selection races discard late responses; empty/error/retry/loading states and exact source-assets-unchanged language are visible."),
        ],
        "out": "No paid provider dispatch, no claim that reserved means running, no team/shared-unit ACL, no deletion/archive, no geometry persistence, no mutation of immutable unit rows, and no generic enumeration of arbitrary owner documents in the browser.",
        "gates": "uv run pytest -q tests/test_engagement_owned_store.py tests/test_engagement_routes.py tests/test_multi_user_owner_path.py; uv run mypy --strict <changed-python>; uv run ruff check <changed-python>; npm --prefix apps/reading test -- src/components/windows/DeepResearchSessionHost.test.tsx src/api/engagement.test.ts; npm --prefix apps/reading run typecheck; npm --prefix apps/reading run build; hardenx . --strict --no-color",
        "rigor": {
            "1 · Intellectual honesty": "A lineage edge proves that Antiek created or reserved a descendant, not that an agent ran or spend occurred. Resolve research status live through the spawn-backed session and label broken lineage reconciliation-required; never infer completion from an applied launch receipt.",
            "2 · Fairness": "Steelman a dedicated SQLite collective registry: it offers atomic row+index+edge transactions and will win when shared ACLs or high-volume queries arrive. Today the immutable owner document is already canonical; prefix paging plus replay-repaired derived lineage avoids migrating two truths and preserves local file installations.",
            "3 · Rigor": "Test Alice/Bob identical unit ids, cross-owner cursor replay, limit+1 boundaries, concurrent insert after cursor, malformed owner/type rows, row-before-list crash, child-before-lineage crash, duplicate repair, live status drift, and deferred browser pages. A first-page happy path cannot prove continuity.",
            "4 · Diligence": "Reuse owned_document_id, mutate/get_owned_document, FileSessionStore's row-first recovery reasoning, _verified_session, settled action receipts, deterministic drafts, openWindow, and existing incremental session discovery states. Do not add a second unit body, session status field, or localStorage authority.",
            "5 · Defensibility": "Document logical-prefix ordering, cursor membership, maximum page size, lineage edge identity, repair order, and why immutable units are not updated with children. A future migration to SQLite must be able to replay canonical unit rows and derived edges without guessing which copy won.",
        },
        "pattern": "adversarial-verification",
        "lenses": "owner-prefix paging and cursor isolation; child-before-lineage crash/replay; reload UI and live status honesty",
    },
    {
        "id": "FSW-SPR-10",
        "slug": "consented-cohesive-research-execution",
        "title": "Consented cohesive-research execution",
        "status": "done",
        "wave": 10,
        "goal": "Execute a confirmed collective unit through Midnight Oil's signed model route, exact integer-cent ceiling, durable stage plan, recoverable worker, and owner-native terminal flywheel without turning a reservation or queue receipt into invented research progress.",
        "files": "substrate/{floating_session,midnight_oil,engagement_spine}/**; interfaces/research/api/{engagement_routes,midnight_oil_routes,midnight_oil_runtime}.py; apps/reading/src/{api,components/windows,modes/MidnightOil}/**; tests/test_{engagement_routes,midnight_oil_authorized_e2e,midnight_oil_worker_cli,multi_user_owner_path}.py",
        "milestones": [
            ("Close terminal owner authority", "Require the server-derived owner on every deposit/recovery call and thread it through spawn materialization, twins, progress, merge, and owned HTML documents. Reject a caller-chosen spawn already owned by another account before mutation.", "Alice's job writes only Alice-owned spawns/twins/documents/progress; Bob and operator cannot read them; crash-after-provider retry deposits without another provider call; no resume API can silently default to __operator__."),
            ("Prepare one immutable execution binding", "Bind owner + target session/spawn + confirmed collective id/revision + exact normalized execution configuration + bounded idempotency key to one durable job identity before consent. Replay returns that job; conflicting material fails; stale/missing/foreign session, spawn, or collective fails before job creation.", "A crash between job and binding writes is repaired by the same request, never by minting a second billable job; one session cannot acquire two active jobs; neither request nor durable payload contains a consent token or API credential."),
            ("Reuse signed spend and worker truth", "Present the existing server recommendation and signed stage/model topology, issue a short-lived consent only after explicit integer-cent approval, send it directly in the run header, and poll canonical lifecycle states. Prepared, consent-required, queued, leased/running, deposit-pending, terminal, and reconciliation-required remain distinct.", "No provider is reachable before consent claim and queue lease; double click/replay cannot enqueue or dispatch twice; projected spend and actual settled cents are both visible and never floats used as authority; browser storage/logs contain no consent token."),
            ("Complete the target flywheel recoverably", "After terminal deposit, replay an owner-bound composition step that completes the bound target spawn with durable synthesized output, insights, questions, references, progress, context/twin effects, and lineage evidence. Failed, timed-out, and budget-halted jobs preserve partial evidence and honest terminal state rather than being rounded up to complete.", "Worker/process restart repairs deposit, flywheel, graph projection, and lineage independently without provider replay; repeated composition is byte-idempotent; the session status derives from its canonical spawn and the artifact remains sandboxable HTML."),
        ],
        "out": "No second billing ledger, provider dispatcher, session store, merge writer, browser-stored consent credential, automatic parent merge, shared/team ACL, unreviewed collective drift, or claim that queued/deposit-pending work is running/complete.",
        "gates": "uv run pytest -q tests/test_midnight_oil.py tests/test_midnight_oil_live.py tests/test_midnight_oil_authorized_e2e.py tests/test_midnight_oil_worker_cli.py tests/test_engagement_routes.py tests/test_multi_user_owner_path.py; uv run mypy --strict <changed-python>; uv run ruff check <changed-python>; npm --prefix apps/reading test -- src/api/midnightOil.test.ts src/api/engagement.test.ts src/components/windows/DeepResearchSessionHost.test.tsx; npm --prefix apps/reading run typecheck; npm --prefix apps/reading run build; hardenx . --strict --no-color",
        "rigor": {
            "1 · Intellectual honesty": "A prepared job proves configuration persistence, consent-issued proves a signed ceiling, queued proves only durable enqueue, and running begins only after a fenced worker lease. Preserve those distinctions in API, UI, tests, and handoff; a terminal failure with partial evidence is not a completed cohesive analysis.",
            "2 · Fairness": "Steelman a new session-native executor: it would simplify the endpoint shape, but it would fork Midnight Oil's mature consent, budget, stage-plan, routing, lease, and recovery authorities. Compose the existing runtime so users receive one spend truth and maintainers do not inherit two subtly different billing systems.",
            "3 · Rigor": "Race prepare, consent, enqueue, lease expiry, deposit, and flywheel settlement across two processes; inject a crash after every durable boundary. Test identical Alice/Bob logical ids, stale collective revisions, conflicting idempotency material, hostile output HTML, budget halt, unknown provider outcome, and prove provider-call count remains one.",
            "4 · Diligence": "Reuse OwnerJob CAS, SpendConsentStore, ConsentStagePlanCoordinator, OperationQueue fencing, BudgetLedger, session/spawn provenance verification, collective immutable revisions, canonical twin/progress/merge writers, and worker recovery phases. Do not smuggle mutable execution state into React localStorage or add ambient owner defaults to live recovery.",
            "5 · Defensibility": "Persist closed identifiers and domain-separated hashes for the execution binding, signed configuration, stage plan, route receipts, actual spend, deposit artifact, target flywheel effect, and lineage edge. A future auditor must reconstruct what the user approved, what providers actually returned, and which recovery phase remains without any secret material.",
        },
        "pattern": "adversarial-verification",
        "lenses": "cross-owner terminal deposit and target-spawn collision; prepare/consent/enqueue/provider replay under crashes; queued-versus-running status and partial terminal flywheel honesty",
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
<footer class="spec-footer">{esc(row['id'])} · generated {DATE} · source: active Antiek /goal Cycle 15</footer>"""
    return shell(f"{row['id']} · {row['title']}", body)


def index_page() -> str:
    cards = "".join(
        f'<a class="sprint-card" href="sprint-{index:02d}-{row["slug"]}.html"><span class="id">{esc(row["id"])}</span><span class="title">{esc(row["title"])}</span><span class="goal">{esc(row["goal"])}</span><span class="footer"><span class="tag tag--blue">Wave {row["wave"]}</span><span class="tag tag--{"green" if row["status"]=="done" else "yellow"}">{row["status"]}</span></span></a>'
        for index, row in enumerate(SPRINTS, 1)
    )
    body = f"""<header class="hero"><p class="eyebrow">Master spec · ANT-FSW</p><h1>Floating-session research workstation</h1><p class="tagline">Make every highlight research window reopenable, context-bearing, collectively promptable, safely mergeable, and explicitly executable.</p><div class="meta-row"><span class="tag tag--blue">Status: consented cohesive execution complete</span><span class="tag tag--yellow">Owner: Antiek /infinite</span><span class="tag tag--grey">10 sprints · 10 waves</span></div></header>
<section id="spec-lineage" class="block" data-spec-depth="0" data-parent-spec=""><h2>Spec lineage</h2><p>Root spec. No parent and no child specs yet; ownership and browser implementation remain Sprint 2 rather than a decorative subtree.</p><ul class="child-specs"></ul></section>
<section class="block"><h2>Goal</h2><p>Close the missing API lifecycle over Antiek's existing floating-session substrate, then define the exact ownership, durability, idempotency, and browser work required for a multi-user workstation.</p><h3>Success criteria</h3><ul><li>Session identity maps to one matching spawn/asset/investigation or fails reconciliation.</li><li>Context and collective operations are explicit, bounded, HTML-native, and cross-asset conscious.</li><li>Draft merge leaves parent content unchanged; parent merge requires confirmation plus the exact previewed parent hash and preserves unrelated metadata.</li><li>Future ownership and multi-worker work has executable crash and browser gates.</li></ul></section>
<section class="block"><h2>Architecture overview</h2><div class="dep-graph">Highlight → FloatingSession → verified Spawn provenance\n             ├→ context pack → HTML / optional prompt\n             ├→ collective unit (cross-asset opt-in)\n             └→ draft preview → confirmed parent merge\nFuture: authenticated owner + CAS/receipt store + browser windowsStore</div><h3>Key invariants</h3><ul><li>No second twin, context, collective, merge, or HTML writer.</li><li>No global session enumeration and no claim of owner isolation until owner columns exist.</li><li>No implicit graph promotion, prompt-body exposure, cross-asset collective, or parent mutation.</li></ul></section>
<section class="block"><h2>Sprint roster</h2><div class="sprint-grid">{cards}</div></section>
<section class="block"><h2>Rejected alternatives</h2><table class="spec"><thead><tr><th>Alternative</th><th>Why rejected</th><th>Reconsider if</th></tr></thead><tbody><tr><td>New session/merge service</td><td>Duplicates shipped engagement_spine writers and breaks recursive twin provenance.</td><td>The canonical spine is deliberately retired through a migration.</td></tr><tr><td>Silent cross-asset collective</td><td>A multi-selection mistake can mix unrelated or future foreign-owner context.</td><td>Ownership policy explicitly defines shared workspaces and UI communicates scope.</td></tr><tr><td>Automatic into-parent merge</td><td>Destroys the draft-review boundary the product vision explicitly asks for.</td><td>Never; confirmation may become a richer review transaction, not disappear.</td></tr><tr><td>API-only graph ownership</td><td>An owner-verified route still deposits private note labels into the shared graph, where global readers or identical-text dedup can cross account boundaries.</td><td>The graph schema and every read surface gain a proven row-level owner policy; physical per-owner graphs remain the safer current contract.</td></tr><tr><td>Content hash as the whole receipt</td><td>Stable node ids prevent duplicate rows but do not pin the reviewed selection, prevent idempotency-key reuse, make a multi-note batch atomic, or replay the exact response after a crash.</td><td>Never for explicit user confirmation; content addressing remains one layer inside the receipt transaction.</td></tr><tr><td>Replace canonical retrieval with the private graph</td><td>Personal partitions currently contain promoted notes, not the shared documents/chunks needed for professional research; replacing rather than fusing would make authenticated users less informed.</td><td>Documents and rights-aware corpus retrieval migrate to a fully owner-native store with an explicit public federation layer.</td></tr><tr><td>Fall back to canonical when an owner graph is absent</td><td>Absence would silently change the meaning and confidentiality scope of a personal-memory request; it also makes routing bugs look like valid empty-user behavior.</td><td>Never implicitly. Canonical public retrieval remains a separately declared input to the fusion.</td></tr><tr><td>Email hash as permanent user_id</td><td>Email is mutable PII; hashing does not make it stable or non-enumerable, and changing it would orphan every owner-scoped asset.</td><td>Never as canonical identity. A verified email remains a credential binding to an opaque account id.</td></tr><tr><td>Trust scopes embedded in a 30-day cookie</td><td>Role removal, account disablement, and logout would not take effect until expiry. Server-side session/account checks keep current authorization authoritative.</td><td>Only for short-lived stateless tokens with a separately proven revocation SLA.</td></tr><tr><td>Add Clerk/Supabase/JWT before using owned auth</td><td>Antiek already signs audience-separated magic-link and session tokens; adding an identity vendor creates a second account authority without solving current role/session durability.</td><td>External federation or enterprise SSO becomes a product requirement and maps into the same stable account registry.</td></tr><tr><td>Use only open-window discovery</td><td>Local chrome forgets closed tabs, other devices, and server-restored sessions; it is presentation state, not an inventory authority.</td><td>Never as the durable source. It remains a useful optimistic supplement while discovery loads.</td></tr><tr><td>Automatically select every discovered session</td><td>Large or unrelated sessions silently inflate prompts and cross asset boundaries without the user's considered intent.</td><td>A future saved collective explicitly records membership and the user chooses that saved unit.</td></tr></tbody></table></section>
<section class="block"><h2>Open questions</h2><table class="spec"><tbody><tr><td>Which authenticated workspace owns pre-owner rows?</td><td>Do not guess; operator-supplied migration mapping or quarantine.</td><td>Operator + Sprint 2 executor</td></tr><tr><td>Which browser surface owns window state?</td><td>Extend the shipped windowsStore rather than create another chrome store.</td><td>Frontend implementation archaeology</td></tr></tbody></table></section>
<section class="block" id="harness-hint-run" data-harness-default-pattern="adversarial-verification" data-harness-inline-only-sprints="FSW-SPR-01"><h2>Execution harness hint</h2><p>SPR-01 is a tight existing-writer composition. SPR-02 may fan out owner/store and frontend work only in isolated file scopes, then synthesize behind crash and browser gates.</p></section>
<footer class="spec-footer">Generated by htmlspec · source: active Antiek /goal Cycle 15 · {DATE}</footer>"""
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
