# Anti-Ek vision map — 2026-09-17 (repurpose, do not rewrite)

**Date:** 2026-09-17 (Asia/Riyadh)  
**Status:** Consolidation / remap — **no product code**.  
**Mandate:** Forensic inventory of Antiek-related specs/plans Faisal has made on the Mac Mini, remapped onto the **locked 2026-09-17 Anti-Ek vision**. Do not start from scratch — cite KEEP / MERGE / DEFER / ARCHIVE for each pillar.  
**Repo companion:** this file lands in-repo so next PRs can cite it. Mini-only companions stay linked by path.  
**Ads coordination:** AppLovin website MVP + attribution ledger is already recorded in [`docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md`](./decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md) (merged #3103). **This doc does not duplicate that PR** — it cross-links and absorbs ads only as pillar 5/7.

---

## Locked vision (target of remap)

| # | Pillar |
|---|---|
| **1** | HTML-native documents/research/writing; dual structure **DuckDB/graph SoT + HTML/Lemon projections**; datasets not HTML-only |
| **2** | Daily-usable loop: **read → highlight → research → notebook → write** |
| **3** | **BYOT** AI keys + model toggles; **BYO connectors** (user liability); agent CPU = Antiek-managed slider + monthly bill predictability; power-user **BYO CPU** optional |
| **4** | **TurboPuffer = SERVABLE retrieval index only**; private/gated stays DuckDB + `owner_read` |
| **5** | Ads: AppLovin (web/phone/iPad), Apple ads phone; **~70/30** Spotify-like payback; non-disruptive desktop |
| **6** | Client chain: **website → iPad → iPhone Duo → Android** |
| **7** | Ads monetization; Antiek as **orchestration not datacenter** |

---

## How to read status labels

| Status | Meaning |
|---|---|
| **shipped** | Landed on `main` (code and/or ratified decision) and still load-bearing |
| **partial** | Real substrate/UI exists; gaps remain vs locked vision |
| **stale** | Useful history; dates/tense drift; do not treat as current execution state |
| **superseded** | Explicitly replaced by a later canon (cite successor) |
| **conflict** | Says something incompatible with locked vision or with a later canon — resolve before reuse |
| **archive-candidate** | Out of active product path (philosophy drills, personal-* authority sprawl, one-off audits) |

Disposition for next work: **KEEP** (drive PRs as-is) · **MERGE** (fold into a living companion) · **DEFER** (right idea, wrong time) · **ARCHIVE** (pointer only).

---

## 1. Inventory table (vision-relevant corpus)

Paths are relative to the Antiek git root unless prefixed `~/…` (Mac Mini companions outside the tracked tree). Dates are file mtimes or document headers when known.

### 1.1 Canon / governance (repo `docs/`)

| path | title/topic | date | status | vision # |
|---|---|---|---|---|
| `docs/master-product-spec.md` | Master product contract (arch / §5 / §9 / §16) | 2026-05-17→19 | **partial** — UI/surfaces **superseded** by ROADMAP; money/attribution **KEEP** | 1–7 |
| `docs/roadmap/ROADMAP.html` | Living Roadmap — STABLE vs FLUID surfaces | 2026-05-27 | **shipped** canon for UI/surface org | 2, 6 |
| `docs/roadmap/GOVERNANCE.md` | Roadmap governance | 2026-05-27 | **shipped** | 2 |
| `docs/architecture_notes.md` | Substrate commitments (event log, single-writer) | 2026-05-16 | **shipped** bedrock | 1, 4, 7 |
| `docs/html-first-design-thesis.md` | HTML-native artifact thesis | ~2026-06 | **shipped** — aligns with pillar 1 | 1 |
| `docs/design-system.md` | Lemon / Werner presentation of HTML artifacts | — | **shipped** | 1, 6 |
| `docs/html/ant-aht-vision-map.html` | Thariq HTML thesis → shipped ledger map | 2026-06-24 | **partial** / slightly **stale** vs 2026-09 dogfood | 1, 2 |
| `docs/htmlspec/antiek-html-transport/` | ANT-AHT HTML transport master | 2026-09-17 tree | **KEEP** | 1 |
| `docs/quack_spec.md` | Quack write coordinator for DuckDB | 2026-05-17 | **DEFER** (Flock still default) | 1, 7 |
| `docs/philosophy/physics-of-reading.md` | Physics of reading canon | from malleable-reading | **KEEP** | 2 |
| `docs/anti-ek-mac-mini-dogfood.md` | Shared DuckDB + Loop One dogfood | 2026-09-17 | **shipped** ops companion for pillar 2 | 2 |
| `docs/anti-ek-cli-swarm.md` | Multi-CLI swarm playbook | 2026-09-17 | ops — not product vision | — |
| `docs/engineering_deferrals.md` | D1–D11 deferral ledger | living | **KEEP** gate list | 3, 7 |
| `docs/operator_gate_actions.md` | G1–G8 operator gates | living | **KEEP** | 5, 7 |
| `docs/ui_redesign_posthog/` (+ `ARCHIVE.md`) | Panel shell + TipTap notebook programme | 2026-05–06 | **shipped**; archive pointer | 2, 6 |
| `docs/ui_redesign_posthog/sprint_07_notebook.html` | Notebook surface sprint | — | **partial** vs daily loop | 2 |

### 1.2 Dual structure / DuckDB / HTML projection

| path | title/topic | date | status | vision # |
|---|---|---|---|---|
| `docs/decisions/owner-privileged-read-path.md` | Owner read for gated/private | — | **shipped** — pillar 4 private path | 4 |
| `docs/decisions/read-spr-01-servable-corpus-gate.md` | Servable corpus gate | — | **shipped** | 4, 5 |
| `docs/decisions/speak-private-public-spine.md` | Private/public spine | — | **KEEP** | 1, 4 |
| `~/Antiek/specs/antiek-html-projection/` | HTML projection sprints | 2026-06-12 | **KEEP** / **MERGE** with html-transport | 1 |
| `~/Antiek/specs/antiek-duckdb-plane/` | DuckDB discipline plane | 2026-06-23 | **KEEP** | 1, 4 |
| `docs/specs/canonical-twin-*` / htmlspec twins | Twin document / knowledge HTML | various | **partial** | 1, 2 |
| `docs/decisions/form-factor-demand-gate-PREREGISTERED.md` | `.antiek` format demand gate | 2026-06-12 | **DEFER** evidence gate | 1 |
| `docs/decisions/g4-lemon-ui-verdict.md` | Reject wholesale `@posthog/lemon-ui` | 2026-05-23 | **shipped** — custom Lemon | 1, 6 |

### 1.3 Daily loop (read → highlight → research → notebook → write)

| path | title/topic | date | status | vision # |
|---|---|---|---|---|
| `docs/htmlspec/deep-research-loop/` | Perfect deep research loop | on tree | **KEEP** | 2 |
| `~/Antiek/specs/antiek-deep-research-doctrine/` | Competitive doctrine → verdicts | 2026-07-11 | **KEEP** (closed PR #716 still useful) | 2 |
| `~/Antiek/specs/antiek-deep-research-hardening/` | Hardening sprints | 2026-06 | **partial** | 2, 3 |
| `~/Antiek/specs/antiek-malleable-reading/` | Facet physics for Read | 2026-05-27 | **KEEP** | 2 |
| `~/Antiek/specs/antiek-reading-convergence/` | Reader collective / fullscreen | — | **MERGE** into ROADMAP FLUID | 2, 6 |
| `~/Antiek/specs/antiek-dogfood-real-loop/` | Real loop dogfood | 2026-07 | **stale** vs Mini dogfood doc | 2 |
| `~/Antiek/specs/antiek-voicenote-2026-08-28-anchored-comments/` | Anchored comments on HTML | 2026-08-28 | **KEEP** (highlight/marginalia) | 2 |
| `~/Antiek/specs/antiek-writing-vertical/` + `antiek-write-edit-delivery/` | Write vertical | — | **partial** | 2 |
| `docs/campaigns/…` / `ANTIEK-712-RESEARCH-READING-SLICE-AUDIT` | Research↔reading spine audit | 2026-07-10 | **stale** campaign residue | 2 |
| `docs/own-your-mind/*` (also `~/Antiek/docs/own-your-mind/`) | Own Your Mind programme | 2026-08-12–13 | **partial** (P0 PR lineage); transparency layer on loop | 2, 7 |

### 1.4 BYOT / BYOK / BYO connectors / BYO CPU

| path | title/topic | date | status | vision # |
|---|---|---|---|---|
| `docs/specs/byot-oauth-2026-08-12.md` | Grok/OpenAI/Anthropic OAuth BYOT | 2026-08-12 | **shipped** modules; not go-live | 3 |
| `docs/specs/byot-tools-vendors-2026-08-12.md` | BYOTools expansion (Drive/Notion/…) | 2026-08-12 | **KEEP** — liability posture matches vision | 3 |
| `docs/specs/byok-model-route-authority.md` | Per-prompt model route authority | — | **KEEP** next PR driver | 3 |
| `docs/htmlspec/byot-request-scoped-authority/` | Request-scoped DispatchAuthority | 2026-08-11 | **KEEP** | 3 |
| `docs/htmlspec/byok-model-route-authority-foundation.html` | BYOK foundation | — | **MERGE** with byok-model-route | 3 |
| `docs/specs/ai-role-lineup-2026-08-12.md` | FUT-style AI role lineup (#3061) | 2026-08-12 | **shipped** UI for toggles | 3 |
| `~/Antiek/specs/antiek-voicenote-2026-08-28-byoc-compute/` | BYO compute (sandboxes) | 2026-08-29 | **KEEP** optional power-user CPU | 3, 7 |
| `~/Antiek/specs/antiek-voicenote-2026-08-28-byoc-persistent-machine/` | Persistent BYO machine | 2026-08-29 | **DEFER** / optional | 3, 7 |
| `~/Antiek/specs/antiek-voicenote-2026-08-28-never-sleeping-agent/` | Never-sleeping agent | 2026-08-29 | **DEFER** — conflicts with bill predictability if always-on house CPU | 3, 7 |
| `docs/specs/scalability-roadmap-2026-08-12.md` | Hetzner scale + Daytona seams | 2026-08-12 | **KEEP** for managed CPU slider story | 3, 7 |
| `docs/daytona_integration_spec.md` | Remote exec / sandbox | — | **MERGE** with BYOC + scalability | 3, 7 |

### 1.5 TurboPuffer / retrieval

| path | title/topic | date | status | vision # |
|---|---|---|---|---|
| `docs/integration_turbopuffer.md` | Hybrid search; TP secondary index only | 2026-05-23 | **KEEP** — already rejects private-graph TP | 4 |
| `docs/specs/turbopuffer-sharding-2026-08-12.md` | Sharding plan | 2026-08-12 | **DEFER** until servable corpus proves need | 4 |
| `~/Antiek/turbopuffer-shadow-benchmark/` | Shadow benchmark worktree | 2026-08 | **partial** evidence lane | 4 |
| `~/Antiek/specs/antiek-turbopuffer-incident-remediation-2026-08-11/` | Incident remediation | 2026-08-11 | **ARCHIVE** after lessons merged | 4 |
| `~/Antiek/specs/antiek-retrieval-gate-closure/` | Retrieval gate | — | **KEEP** | 4 |
| `docs/decisions/retrieval-substrate-spike-2026-05-31.md` | Spike decision | 2026-05-31 | **stale** companion | 4 |

### 1.6 Ads / attribution / payback

| path | title/topic | date | status | vision # |
|---|---|---|---|---|
| **`docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md`** | **Locked ads decision (website MVP)** | **2026-09-17** | **shipped** (#3103) — **authoritative for pillar 5 website** | **5, 6, 7** |
| `docs/integration_applovin.md` | AppLovin / Axon posture; REJECT web MAX | 2026-07-02 | **KEEP** doctrine (#118) | 5 |
| `docs/specs/ad-v1-scalable-2026-08-12.md` | Gap-ranked ad v1 plan | 2026-08-12 | **KEEP** execution order | 5 |
| `docs/specs/publisher-ecosystem-2026-08-12.md` | 70/30 publisher ecosystem | 2026-08-12 | **KEEP** | 5, 7 |
| `~/Antiek/specs/antiek-frame-attribution/` | S1–S6 frame attribution | 2026-07-02 | **partial** (S1 lineage shipped) | 5 |
| `~/Antiek/specs/antiek-axon-loop/` | In-house Axon-style loop | 2026-07-03 | **KEEP** (copy loop, not network) | 5 |
| `~/Antiek/specs/antiek-disbursement-readiness/` | Disbursement readiness | 2026-07-03 | **DEFER** behind G2/G3 | 5 |
| `docs/decisions/afa-synthesis-attribution-canonical.md` | Synthesis attribution | — | **KEEP** | 5 |

> **Conflict callout (ads):** colloquial “ads via AppLovin for website” ≠ drop MAX/pixel on web. #3103 + `integration_applovin.md` already resolve: **Antiek-served creatives + Axon-style in-house ranking**; MAX/Apple ads = **native later**. Do not open a second competing ads PR.

### 1.7 Clients / form factors / orchestration-not-datacenter

| path | title/topic | date | status | vision # |
|---|---|---|---|---|
| `docs/decisions/form-factor-demand-gate-PREREGISTERED.md` | New format demand | 2026-06 | **DEFER** | 6 |
| `docs/decisions/read-frontend-sprints-on-existing-surface.md` | Stay on existing Read surface | — | **KEEP** — website-first | 6 |
| `~/specs/xiaomi-tablet-decision/` | Tablet hardware decision | 2026-08-21 | **ARCHIVE** / hardware note only | 6 |
| `docs/specs/scalability-roadmap-2026-08-12.md` | Orchestration seams, not re-arch | 2026-08-12 | **KEEP** pillar 7 | 7 |
| `docs/integration_prime_intellect.md` / `loop_3_unlock_criteria.md` | Training/RL unlocks | — | **DEFER** | 7 |
| `~/Antiek/docs/own-your-mind/05-own-your-mind-design-spec.md` | User-owned graph (not auctioned mind) | 2026-08-12 | **KEEP** philosophy of pillar 7 | 7 |

### 1.8 Large Mini-only / home companions (pointer inventory)

| path | note | status | vision # |
|---|---|---|---|
| `~/Antiek/specs/` (~311 dirs; **193** `antiek-personal-*`) | Personal-domain authority pack — not Anti-Ek daily product | **ARCHIVE**-batch for vision work | — |
| `~/Antiek/specs/` (~118 non-personal) | Sprint HTML specs; many executed or superseded | mixed — see pillars | 1–7 |
| `~/specs/` (~127 project dirs; many symlinks into `~/Antiek/specs/`) | Historical caffenagent homes | prefer Antiek tree copies | — |
| `~/Antiek/FORENSIC-REPORT-2026-08-*.md` | August forensic passes | **ARCHIVE** incident history | — |
| `~/Desktop/Antiek-Operator-Handbook.md` | Operator handbook draft | **MERGE** selectively into dogfood/runbooks | 2 |
| `~/specs/ANTIEK-*-2026-07-*.md` | Stack readiness / merge order | **stale** | — |

**Prior worktrees:** scanned; unique vision-bearing specs already mirrored under `~/Antiek/specs/` or `docs/`. No separate worktree-only vision canon found beyond dated forks of ROADMAP / integration_* (prefer git `main`).

---

## 2. Conflicts and supersessions (honest)

| Tension | Older claim | Locked / later canon | Disposition |
|---|---|---|---|
| Four products vs surfaces | Master §16.2 REJECT “four products” | `ROADMAP.html`: four **surfaces** over one graph is STABLE/FLUID truth | **UI:** ROADMAP wins. **Architecture/§9/§16:** master still wins. |
| PostHog Lemon package | Early integrate `@posthog/lemon-ui` | `g4-lemon-ui-verdict.md` REJECT package; custom Lemon | **ARCHIVE** package path; **KEEP** custom Lemon + notebook |
| UI redesign vs ROADMAP | `ui_redesign_posthog` sprint novel | ROADMAP + ARCHIVE.md | Treat redesign as **shipped shell**; new surface org edits go to ROADMAP FLUID |
| AppLovin on web | Operator admiration / “use AppLovin” | #3103 + `integration_applovin.md`: no web publisher SDK; copy Axon loop | **KEEP** #3103; no competing ads remap |
| TurboPuffer as store / private graph | Temptation in early chats / sharding doc | `integration_turbopuffer.md` §2 REJECT primary store + private TP | **KEEP** REJECT; sharding **DEFER** |
| Datacenter scale now | Hetzner curiosity / always-on agents | Vision 7 + scalability roadmap: seams now, scale later; managed CPU slider | **DEFER** never-sleeping house CPU; **KEEP** BYOC optional |
| Own Your Mind vs ads | Transparency / anti-auction mind | Ads are opt-in payback on **servable** corpus, not profiling auction | Compatible if escrow + `ad_eligible` + user-owned objective card stay |
| HTML-only datasets | Form-factor enthusiasm | Vision 1: datasets remain DuckDB/graph; HTML is projection | Form-factor gate **DEFER**; never make DuckDB optional |
| Dogfood docs drift | `antiek-dogfood-real-loop` (July) | `anti-ek-mac-mini-dogfood.md` (2026-09-17) | Prefer September Mini dogfood |

---

## 3. Remap by vision pillar — KEEP / MERGE / DEFER / ARCHIVE

### Pillar 1 — HTML-native + DuckDB/graph SoT + Lemon projections

| Disposition | Specs |
|---|---|
| **KEEP** | `html-first-design-thesis.md`, `htmlspec/antiek-html-transport/`, `architecture_notes.md`, `~/Antiek/specs/antiek-html-projection/`, `~/Antiek/specs/antiek-duckdb-plane/`, `design-system.md` |
| **MERGE** | `html/ant-aht-vision-map.html` → refresh citations against this map; twin/htmlspec multimedia HTML assets into transport vocabulary |
| **DEFER** | `form-factor-demand-gate`, Quack cutover, DuckLake multi-user |
| **ARCHIVE** | PapaHTML / hermes-lemon experiments under `~/specs/` that are not wired to Antiek ingest |

### Pillar 2 — Daily loop read → highlight → research → notebook → write

| Disposition | Specs |
|---|---|
| **KEEP** | `ROADMAP.html`, `anti-ek-mac-mini-dogfood.md`, `htmlspec/deep-research-loop/`, `antiek-deep-research-doctrine`, `antiek-malleable-reading`, `physics-of-reading.md`, anchored-comments voicenote, notebook sprint_07 + TipTap shipped code |
| **MERGE** | reading-convergence + living-roadmap Read sprints into ROADMAP FLUID checklist; OYM explain/objective into loop “why am I seeing this” |
| **DEFER** | Full Write canvas Lego / tab-complete outline (vision map deferred rows); Speak-as-daily-driver |
| **ARCHIVE** | July campaign audits once Mini dogfood is the ops SoT |

### Pillar 3 — BYOT / BYO connectors / managed CPU + optional BYO CPU

| Disposition | Specs |
|---|---|
| **KEEP** | `byot-oauth`, `byot-tools-vendors`, `byok-model-route-authority`, `byot-request-scoped-authority`, `ai-role-lineup`, `byoc-compute` (optional), `scalability-roadmap` (managed capacity) |
| **MERGE** | Daytona + BYOC persistent-machine into one “compute authority” companion later |
| **DEFER** | Enterprise data vendors; never-sleeping agent as **default**; multi-tenant billing |
| **ARCHIVE** | Duplicate BYOK sprint HTML that only restates byok-model-route |

### Pillar 4 — TurboPuffer servable-only; private = DuckDB + owner_read

| Disposition | Specs |
|---|---|
| **KEEP** | `integration_turbopuffer.md`, `owner-privileged-read-path`, `read-spr-01-servable-corpus-gate`, retrieval-gate-closure |
| **MERGE** | Shadow-benchmark results into turbopuffer unlock criteria appendix when measured |
| **DEFER** | `turbopuffer-sharding-2026-08-12.md` |
| **ARCHIVE** | Incident remediation specs after runbook bullets land |

### Pillar 5 — Ads / 70/30 / non-disruptive desktop

| Disposition | Specs |
|---|---|
| **KEEP** | **`applovin-website-mvp-attribution-ledger-2026-09-17.md` (primary)**, `integration_applovin.md`, `ad-v1-scalable`, `publisher-ecosystem`, frame-attribution Mini spec, axon-loop |
| **MERGE** | Nothing new in this PR — follow #3103 next-agent one-liner |
| **DEFER** | Live AppLovin demand, MAX, Apple ads, disbursement-readiness |
| **ARCHIVE** | None of the ads doctrine (too load-bearing) |

### Pillar 6 — website → iPad → Duo → Android

| Disposition | Specs |
|---|---|
| **KEEP** | #3103 client-chain note; `read-frontend-sprints-on-existing-surface`; responsive / a11y sprints already in ui_redesign |
| **MERGE** | Tablet notes only as FLUID roadmap bullets |
| **DEFER** | Native MAX, Duo-specific chrome, Android app |
| **ARCHIVE** | Hardware shopping specs (`xiaomi-tablet-decision`) |

### Pillar 7 — Monetization via ads; orchestration not datacenter

| Disposition | Specs |
|---|---|
| **KEEP** | master §9 + publisher-ecosystem + scalability-roadmap + OYM design (user-owned graph) + BYOC optional |
| **MERGE** | Operator handbook scale sections into scalability companion |
| **DEFER** | Postgres shard stages; Loop 3 / PI training; house always-on agent fleet |
| **ARCHIVE** | Forensic pass reports as product guidance |

---

## 4. Prioritized reuse list — top 10 specs to drive next PRs (not rewrite)

1. **`docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md`** — website ads/ledger next steps (cross-link only; do not fork).  
2. **`docs/specs/byok-model-route-authority.md` + `docs/htmlspec/byot-request-scoped-authority/`** — make model toggles authority-safe on highlight→research and write.  
3. **`docs/anti-ek-mac-mini-dogfood.md` + Loop One broadcast fixes** — prove daily loop on Mini before new surfaces.  
4. **`docs/html-first-design-thesis.md` + `docs/htmlspec/antiek-html-transport/`** — keep artifacts HTML-native with DuckDB SoT.  
5. **`docs/htmlspec/deep-research-loop/` + `~/Antiek/specs/antiek-deep-research-doctrine/`** — research quality bar for the middle of the loop.  
6. **`~/Antiek/specs/antiek-malleable-reading/` + `docs/philosophy/physics-of-reading.md`** — highlight/marginalia composability.  
7. **`docs/specs/ad-v1-scalable-2026-08-12.md` + `~/Antiek/specs/antiek-frame-attribution/`** — close S2–S6 escrow gaps without live network ads.  
8. **`docs/integration_turbopuffer.md`** — enforce servable-only index; private stays DuckDB.  
9. **`docs/specs/byot-tools-vendors-2026-08-12.md`** — next BYO connectors under user liability.  
10. **`docs/specs/scalability-roadmap-2026-08-12.md` + `~/Antiek/specs/antiek-voicenote-2026-08-28-byoc-compute/`** — managed CPU slider now; BYO CPU optional.

Honorable mentions (11–15): `publisher-ecosystem-2026-08-12.md`, `ai-role-lineup`, `owner-privileged-read-path`, OYM `05`+`12`, `ROADMAP.html` FLUID updates.

---

## 5. Grades

| Score | /100 | Rationale |
|---|---|---|
| **Spec archaeology completeness** | **86** | Repo `docs/` (~474 md/html), Mini `~/Antiek/specs/` (311 dirs), `~/specs/` symlinks, OYM tree, voicenote/BYOC pack, and #3103 ads forensic were covered. Deducted for: (a) 193 personal-* authority specs inventoried only as a batch, not row-by-row; (b) nested `.caffenagent` copies inside specs not re-diffed; (c) Google Drive empty for ads (per #3103) — other Drive Antiek notes not re-crawled this pass. |
| **Alignment of corpus to locked 2026-09-17 vision** | **78** | Strong alignment on HTML+DuckDB dual structure, BYOT, turbopuffer-as-index, 70/30 attribution design, website-first clients, orchestration posture. Drag from: UI canon split (master vs ROADMAP — already reconciled but easy to mis-read); AppLovin colloquial vs web-SDK reality (resolved in #3103 but still a verbal hazard); BYOC/never-sleeping vs bill predictability; multimedia htmlspec sprawl vs daily reading loop priority; Quack/DuckLake/form-factor still tempting HTML-only or infra-first detours. |

---

## 6. Coordination notes

- **Ads agent / #3103:** authoritative for pillar 5 website MVP. This map **cross-links only**.  
- **Standing rule:** next product PRs should **open the KEEP row and implement**, not author a parallel master spec.  
- **Secrets:** none; Mini paths and public gate names only.

---

## 7. One-liner for the next agent

Implement from the top-10 KEEP list in order: authority-safe BYOK on the highlight→research path, Mini dogfood loop green, then ad-v1 ranks that #3103 already sequenced — do not rewrite doctrine.
