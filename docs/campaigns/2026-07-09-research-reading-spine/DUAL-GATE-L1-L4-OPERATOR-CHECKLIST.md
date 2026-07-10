# Dual-gate L1–L4 operator checklist (residual ky)

**Purpose:** set future agents + the operator up for **perfect live enablement**
without silent network, ToS violations, or inventing LLM note-taker content.  
**Default remains offline-honest.** Live paths are dual-gated: env **and** process injectors.

**Campaign:** PR #465 · `campaign/research-reading-spine-2026-07-09-main`  
**Bar:** HTML-first · soft budget · propose≠promote · NotDiamond advisory only (L7 forever)

---

## Preflight (always)

1. Re-read `~/Antiek/.infinite/cycle-state.json` tip residual + `git log -1` on campaign worktree.
2. Confirm Settings readiness panels (hydrate / twin seed / MO live-step status) show **offline defaults**.
3. Confirm suite-proposal plan AC green (`tests/test_settings_suite_proposal.py` → 4_passed).
4. Do **not** enable live injectors in CI or shared runners without operator network policy OK.

---

## L1 — Live arXiv body hydrate

| Item | Value |
|---|---|
| Env | `ANTIEK_HYDRATE_LIVE_ARXIV=1` |
| Wire | `substrate/engagement_spine/hydrate_live_wiring.py` · boot in `interfaces/research/api/app.py` |
| Injector | `acquisition.arxiv.client.fetch_by_id` (Atom metadata; not PDF human view) |
| Human view | Still HTML via hydrate projection — never PDF as view surface |
| Verify | Settings hydrate status: arxiv env on + injector installed; offline_honest=false only when body landed |
| Rollback | Unset env → offline identity stubs |

**Operator OK required:** outbound network to arxiv.org; no paywall scrape.

---

## L2 — Live Substack body hydrate

| Item | Value |
|---|---|
| Env | `ANTIEK_HYDRATE_LIVE_SUBSTACK=1` |
| Wire | same hydrate_live_wiring · **requires** explicit `fetch_post` factory |
| Injector | Operator-supplied `fetch_post` (ToS-compliant); env alone is insufficient |
| Honesty | Env on + no factory → status reports factory missing (do not invent body) |
| Verify | Settings hydrate status: substack env on + factory installed |
| Rollback | Unset env / remove factory |

**Operator OK required:** Substack ToS + explicit factory inject (no silent crawl).

---

## L3 — Live twin note_taker seed {#l3-twin}

| Item | Value |
|---|---|
| Env dual-gate | `ANTIEK_TWIN_SEED_LIVE=1` **and** `ANTIEK_TWIN_SEED_USE_DISPATCH=1` |
| Wire | `substrate/engagement_spine/twin_seed_live_wiring.py` · `configure_twin_seed_live` |
| Injector | `fn(title, body_text) -> Sequence[tuple[kind, text]]` (insight/question) |
| Force offline | UI panels pass `force_offline=true` for safe seeds — live only via deliberate path |
| Honesty | `live_seed`, `seed_source`, `offline_honest` on payload (TwinNotesPanel hh) |
| Verify | Settings twin seed readiness both flags on + configure succeeded |
| Rollback | Unset either env flag |

**Operator OK required:** dispatch note_taker green + budget path acceptable.

---

## L4 — Live Midnight Oil worker step {#l4-moil}

| Item | Value |
|---|---|
| Env | `ANTIEK_MIDNIGHT_OIL_LIVE_STEP=1` |
| Wire | `substrate/midnight_oil/product_path.py` · process step injector |
| Dual | Env on **and** step_fn configured; else offline step honesty |
| Budget | Soft halt when projected spend would exceed approved ceiling |
| Verify | Settings / MO live-step status; deposit still HTML-first |
| Rollback | Unset env → offline step notes |

**Operator OK required:** swarm step_fn + ceiling/budget halt verified in dogfood.

---

## Explicitly never (L7)

**NotDiamond as router:** rejected. Advisory only. Do not implement dispatch authority
even if a vendor SDK makes it easy.

---

## Agent execution contract when enabling

1. Inventory residual letter + one surface at a time.
2. Tests prove: default offline; env-on-without-injector honest failure; env+inject green.
3. No invent $0 budget; no invent live body when offline_honest.
4. Ship on campaign branch only; **main merge operator-gated**.

## Related inventories / notes

- `TWIN-SEED-LIVE.md`, hydrate live wiring residual hr, competitive notes jf–kx
- Settings panels: hydrate readiness, twin seed readiness, MO live-step status

---

## UI prep deep-links (residual nl–nn · 2026-07-10)

Checklist is linked from engagement surfaces for operator prep only.
**None of these enable injectors** — they route humans to this document.

| Surface | data-testid | Prep focus |
|---|---|---|
| PublicationAttach | `publication-attach-dual-gate-checklist-link` | L1/L2 hydrate |
| Midnight Oil | `moil-dual-gate-checklist-link` | L4 live step |
| Marketplace | `marketplace-dual-gate-checklist-link` | host/hydrate path |
| TwinNotes | `twin-notes-dual-gate-checklist-link` | L3 twin seed |
| ResearchContext | `research-context-dual-gate-checklist-link` | L1/L2 hydrate |
| ResearchProgress | `research-progress-dual-gate-checklist-link` | multi-minute job |
| Collective | `collective-dual-gate-checklist-link` | L6 multi-agent prep |
| SpawnMerge | `spawn-merge-dual-gate-checklist-link` | merge path prep |
| SessionFlywheel | `session-flywheel-dual-gate-checklist-link` | land → bench feed |
| Settings Antiek-bench | `antiek-bench-dual-gate-checklist-link` | suite rewrite + L7 ND |
| ResearchLaunchBudget | `research-launch-budget-dual-gate-checklist-link` | shared launch budget |
| DecisionTreeDriverBadge | `decision-tree-dual-gate-checklist-link` | shared driver+budget |

---

## L5 — Marketplace payment rails (deferred · residual vt/uy) {#l5-payment}

| Item | Value |
|---|---|
| Status | **Deferred** · `manual_receipt_only` · `live_payment=false` |
| Product truth | Free PD + host HTML path ships offline; paid checkout does not |
| Honesty surfaces | MarketplaceHost L5 stamp · Settings dual-gate L5 payment deferred |
| Unlock when | Product/legal payment design + operator OK |
| Never | Silent live payment or invent free when rails paid |

**Operator OK required:** payment design + receipt policy. Not dual-gate env.

---

## L6 — Live multi-agent collective council (deferred · residual vx/vz) {#l6-collective}

| Item | Value |
|---|---|
| Status | **Deferred** · offline merge unit only |
| Product truth | Multi-select merge → unit prompt / draft / written analysis ships offline |
| Honesty surfaces | CollectiveResearchPanel `data-l6-live-multiagent=deferred` · Settings dual-gate L6 |
| Spec | `spec-dn-collective-live-multiagent.md` |
| Unlock when | Spec + injectors + budget halt verified |
| Never | Silent live multi-agent council from multi-select alone |

**Operator OK required:** council injectors + soft budget · offline default remains correct.

---

## L7 — NotDiamond as router (**never** · residual rl / §16) {#l7-notdiamond}

| Item | Value |
|---|---|
| Status | **Rejected forever as dispatch authority** |
| Product truth | NotDiamond advisory-only · weekly refresh · never auto-installs driver |
| Honesty surfaces | Settings `#notdiamond-advisory` · dual-gate L7 ND advisory link |
| Unlock when | **Never** as router |
| Correct use | Advisory delta vs installed decision-tree driver only |

**Never:** NotDiamond select model for research dispatch. Advisory ≠ authority.

---

## Residual (wg) honesty note · 2026-07-10

L5–L7 documented here so Settings dual-gate prep and engagement deep-links
point at a complete operator map — not L1–L4-only silence after L5/L6 stamps
landed in product UI.
