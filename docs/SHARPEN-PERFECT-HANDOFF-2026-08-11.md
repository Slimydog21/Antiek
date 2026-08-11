# SHARPEN & PERFECT — Antiek v1 Activation Handoff Spec
**Authored:** 2026-08-11 20:05 UTC · **Session:** Prime Agent goal "sharpen and perfect my Antiek website so I can begin using it"
**Status:** SPEC + verified current-state audit. Everything below that says VERIFIED was checked live this session (code on origin/main @ 17aeecdbd, tests run, prod box inspected). Items marked DO-NOW are the next agent's concrete work.

---

## 0. How to read this document

This spec exists because the operator's v1-activation ask is far larger than one
context window. It (a) records what ALREADY EXISTS (most of the vision is
implemented — do not rebuild it), (b) names the exact remaining gaps with
file-level pointers, (c) sequences the work, and (d) hands off the open
research items. Read the corpus first — in this order:
`docs/master-product-spec.md` (3064 lines; §3 what's built, §9 ad economics,
§13 account model, §14 sprint table, §15.7 RLM decisions),
`docs/operator_gate_actions.md` (the LIVE gate register — G1–G13),
`docs/rlm_integration_spec.md`, `docs/integration_turbopuffer.md` (72KB),
`docs/integration_prime_intellect.md`, `docs/integration_applovin.md`,
`docs/integration_posthog.md`, `docs/decisions/` (130+ decision records).

**Corpus honesty:** the master spec's "what's NOT built" list dates to 2026-05-18;
most items shipped since. The live register is `docs/operator_gate_actions.md`.

---

## 1. Session deliverables (this agent, verified)

| Item | State | Evidence |
|---|---|---|
| DeepSeek-OCR-2 + Firecrawl AnyDoc in ingest | **MERGED** #3002 (main `17aeecdbd`) | 21 new tests; prod `firecrawl-anydoc==0.1.8` installed + live-verified (docx→GFM on prod box); OCR verified against real llama.cpp v2 service |
| arXiv OAI-PMH sync upstream-move fix | **PR #3006** + **prod patched** (`.bak-20260811`) | prod journal now `GET https://oaipmh.arxiv.org/oai … 200 OK`; 91 arXiv tests pass; root cause: `export.arxiv.org/oai2` 301 + `follow_redirects=False` |
| BYOT usage/balance frontend panel | in progress (child agent) | backend `byot_usage_routes.py` verified live+registered; frontend had zero consumers |
| This spec | here | — |

---

## 2. Prime Agent (RLM) embedding — audit + plan

**VERIFIED on main:**
- RLM primitives shipped: `interfaces/research/rlm_repl.py` (REPL sandbox),
  `substrate/graph/rlm_tools.py` (sub-LLM tool-calling), `interfaces/research/rlm_dag.py`
  (decomposition DAG), `substrate/constants.py` §F (bounded constants),
  `skills/verification/rlm.py`. Spec: `docs/rlm_integration_spec.md` (6 design
  decisions in §6 awaiting ratification — do not relitigate; ratify per §15.7).
- Prime Agent adapter shipped dormant: `runtime/remote_exec/prime_exec.py`
  (`PrimeExecProvider`, default-off via `ANTIEK_PRIME_EXEC_ENABLED`, RPC mode
  v0.7.0, research fan-out only — per `docs/decisions/s16-research-fanout-exemption.md`).
- Execution-backend seam shipped: `runtime/exec_backend/` (LocalProcessBackend,
  DockerBackend) + `runtime/remote_exec/` (provider registry + fallback).

**GAP (DO-NOW, ranked):**
1. Ratify the six RLM decisions (`rlm_integration_spec.md` §6) — one review
   session; then RLM-1 sprint can start.
2. Wire `PrimeExecProvider` as the research-fan-out backend for RLM leaves:
   in the RLM DAG's sub-LLM tool calls, add a `remote_exec` tool that routes
   to PrimeExecProvider when `ANTIEK_PRIME_EXEC_ENABLED=1`, with the existing
   `ANTIEK_PRIME_AGENT_BIN` / `ANTIEK_PRIME_AGENT_PROVIDER` /
   `ANTIEK_PRIME_AGENT_MODEL` envs. Runbook exists:
   `infrastructure/runbooks/remote-exec-fanout.md`.
3. Verify `prime_exec.py`'s tests pass (`tests/test_remote_exec_*.py`) and add
   a smoke test that boots `prime-agent --mode rpc --version` when the binary
   exists.

**Vision mapping (agent tool-calling for knowledge workers):** the substrate
already lets research agents write DuckDB/SQL (substrate + `runtime/db_lock.py`
single-writer), run Python analysis (exec_backend), and fetch sources. Gaps:
- **Processing (p5.js/Java) visual generation** — add a `visual_backend`
  provider (HTML canvas/p5 sketches emitted as HTML assets) under exec_backend;
  see §5 wheel-of-styles hook.
- **SQL/DuckDB quantitative lanes** — exists (`substrate/` tables + `tools/`);
  document the pattern in the runbook for agents.

---

## 3. BYOT — remove system keys, self-onboarding, OAuth, usage, balances

**VERIFIED on main:**
- `runtime/byok/store.py` — encrypted-at-rest key store (SecretBox), owner-scoped.
- `interfaces/research/api/settings_models_admin.py` + `byot_usage_routes.py`:
  `GET /settings/usage`, `POST /settings/usage/{id}/limit`,
  `GET /settings/balance/{id}` (balance adapters: deepseek native,
  kimi native, spend-history/quota-pct; honest `unavailable` degrade).
- `byot_usage` ledger (`substrate/byot_usage/ledger.py`) — per-key used cents.
- Frontend: `modes/Settings/` (overview + decision tabs, ModelDecisionBar,
  AddModelPanel BYOK paste-a-key, passkeys); `api/settingsModels.ts`,
  `api/composerProjection.ts`.
- Provider catalog + multi-model keys: `interfaces/research/api/boot_providers.py`
  (deepseek/zai/kimi/xiaomi/hermes; DeepSeek V4 Pro/Flash both present).
- Grok OAuth: **open PR #2997** "feat(byot): Grok (xAI) OAuth device-code
  onboarding + byok integration" (Aug 7) — review/land it.

**GAPS (DO-NOW, ranked):**
1. **Operator key removal (prod)**: `/etc/antiek/secrets.env` still holds
   DEEPSEEK_API_KEY, XIAOMI_API_KEY, Z_AI_API_KEY, EXA_API_KEY, SERPAPI_API_KEY,
   BROWSERBASE_API_KEY, STRIPE_SECRET_KEY, AGENTMAIL_API_KEY, etc. (verified
   key-names list 2026-08-11). Operator action: onboard the same keys through
   the Settings UI (BYOK), verify dispatch works with `ANTIEK_BYOT_ONLY=1`
   (env exists; PR #3000), then strip the provider keys from secrets.env.
   STRIPE/AGENTMAIL/CF_ACCESS/AUTH remain system-level (not model tokens).
   Precisely: keep `ANTIEK_OPERATOR_TOKEN`, `ANTIEK_AUTH_SECRET`,
   `CF_ACCESS_*`, `STRIPE_SECRET_KEY`, `AGENTMAIL_*`, `ANTIEK_*` config vars;
   remove provider/API keys only.
2. **Usage dashboard UI** — the frontend panel (in progress this session) is
   the first cut; extend into a dedicated `OperatorDashboard` usage tab
   (per-key: used, cap, remaining, balance kind + resets_at).
3. **Balance in the model dropdown** — after the panel lands, add a balance
   chip to the provider/model picker used by dispatch (ModelDecisionBar +
   `composerProjection`), consuming `GET /settings/balance/{id}` per key.
4. **Multi-model toggle per key** — the provider catalog exposes models; the
   dropdown must group by key and list its models (DeepSeek V4 Pro vs Flash)
   with the selected one persisted per function (task-level model override
   exists in dispatch; surface it in the picker).
5. **OpenAI + Anthropic OAuth (T3Code-style)** — NOT implemented. Research
   brief (child agent) lands at `/tmp/antiek-research-brief.md`; expected
   shape: OAuth app per provider (OpenAI: OAuth for API usage via
   provider account connect; Anthropic: console OAuth), PKCE, token refresh,
   BYOK store integration. This is a NEW backend + settings UI surface.
6. **Grok OAuth** — land #2997; verify device-code flow against x.ai.
7. **BYOTools (bring your own tools)** — connectors exist for SEC EDGAR
   (`interfaces/research/api/connector.py`, paste-a-key chassis from #2975).
   Add: X API (note G11: X content is `personal_reading`/`social_thread` and
   NEVER trainable), YouTube Data API (acquisition/youtube exists — key it),
   and vendor connectors (sell-side research, expert interviews, survey data)
   per the research brief. Decide the catalog with the operator; start with
   X + YouTube since acquisition code already exists.

---

## 4. arXiv — VERIFIED CLEAN (this session)

- 91 tests pass (acquisition, ingest, html-ingest, OAI sync, systemd).
- Rate governor matches the operator's claude arxiv skill contract: >=3s
  spacing persisted cross-process, 429 backoff (60/120/240s jittered), ban
  sentinel, cross-process flock (`acquisition/arxiv/rate_governor.py`).
- Fixed: OAI endpoint 301 (PR #3006, prod patched + live-verified).
- Remaining niceties (optional): port the skill's metadata cache
  (`~/.cache/claude-arxiv/metadata/`) idea into `acquisition/arxiv` to avoid
  re-fetching paper metadata on repeated ingests.

---

## 5. HTML document framework + wheel of styles + frontend-craft

**VERIFIED on main:**
- Document→HTML pipeline: `substrate/reader_html/store.py` (sanitized reader
  HTML with SANITIZER_VERSION, provenance sidecar), `reader_html_routes.py`
  (serve gate), `upload_routes.py` (doc→HTML S4: PDF/HTML/MD/TXT upload,
  magic-byte sniffing, EPUB→409 ceremony), `acquisition/snapshot/reader_html.py`
  (URL snapshot), `substrate/books/html_sanitizer.py` (allowlist sanitizer).
- Universal ingest: `substrate/research_bridge/extractors.py` (+ OCR/AnyDoc
  from #3002) → `ingest_file.py` → graph + notes.
- Wheel of styles: **backend only** — `feat(html-projection)` forkable style
  system merged (#2973); the *frontend wheel UI* does NOT exist yet
  (verified: no refs in apps/reading).
- frontend-craft skill: operator's `~/.claude/skills/frontend-craft/SKILL.md`
  + `~/.prime/agent/skills/frontend-craft/SKILL.md` — the design bar.

**GAPS (DO-NOW):**
1. **Wheel-of-styles UI**: a `StyleWheel` component in the reading/artifact
   view: (a) buttons to pick a style for generating/re-generating an artifact,
   (b) fork + edit a style, (c) save new styles into the wheel. Backend style
   registry exists — surface it (check `substrate/html_projection/` merge).
2. **Universal asset→HTML**: extend the doc→HTML lane to *every* ingestable
   asset (URL, PDF, Office docs via AnyDoc, EPUB via acquisition ceremony,
   arxiv papers) so the reader can open ANYTHING as sanitized HTML with
   provenance. The pieces exist; the integration gap is routing every ingest
   path through `store_reader_html` (books lane does; URL lane does; universal
   ingest does not yet).
3. **Prompt-editing in the HTML view**: "interact and edit with prompts armed
   with personal context" — the Reading/Write modes exist; add a
   "rewrite artifact" action that sends the artifact HTML + personal context
   (memory recall, §8) through the composer and renders a forked style.
4. **frontend-craft embedding**: adopt the skill's honesty/no-slop rules as a
   lint + review gate for artifact HTML (extend `tools/lints/` patterns).

---

## 6. Book products, copyright, marketplace, TollBit

**VERIFIED:** Bartz compliance is ENGINEERED: `acquisition/books/` with
`content_class` legal gating (G1 closed, SQL-WHERE enforced), EPUB only via
authorized acquisition ceremony (409 redirect), uploads require
`acquisition_attestation`, `ip_holders` pre-onboarding (Kalshi pattern,
G2/G3/G10 gates open — operator+counsel). Stripe Press titles are
personal-read only until G10. The master spec §9 + `operator_gate_actions.md`
G2/G3/G10 are the live register.

**GAPS (DO-NOW = design + spec only, gated on G2/G3):**
1. **Marketplace product spec**: direct digital book purchase + the
   research-ingestion API product (notes-only, no reading). Design doc needed:
   license model (per-book, per-research-ingest), DRM-free reading surface,
   forkable-book features (merge two books, condense, expand, page-by-page
   investigation) — these map to existing substrate primitives (chunking,
   synthesis, versioning) but need a product spec before build.
2. **TollBit bridge**: research brief (child) → decide short-term bridge vs
   direct publisher deals; operator preference: publisher API payment gates
   should eventually come down in favor of ad revenue (§6 of research brief).
3. **Hosting question**: Amazon/Spotify early-days analysis → the operator
   should NOT host publishers' books long-term; v1: user-uploaded +
   PD (public-domain) corpus + publisher-brokered access. Whitelabel
   marketplace options researched in the brief (Gumroad/Lemon Squeezy are
   payment rails, not hosting; PD books from Project Gutenberg/Internet
   Archive are the v1 catalog).
4. **Per-second ad attribution thesis** (§9 of master spec) is already the
   architecture: `ad_impressions`, `ad_routes`, `advertisers`, `campaigns`,
   `creator_payouts` routes exist on main. DO-NOW: verify the impression
   recording pipeline works end-to-end (an impression event → ledger row →
   attribution split to ip_holders), then build the advertiser console UI
   (mode exists: `AdvertiserConsole`). AppLovin integration = research brief
   §6 (mobile-first; web alternatives for v1).

---

## 7. Turbopuffer + infra scaling + sandboxes

**VERIFIED:** `docs/integration_turbopuffer.md` (72KB) — the design is done:
turbopuffer as SECONDARY hybrid index (Wedge 1 spike gated, §6.4), 12 explicit
REJECTs, cost discipline (§11.2 daily budget cap). NOT implemented in code
(no turbopuffer client on main).

**GAPS (DO-NOW):**
1. Run the Wedge-1 spike (§6.4): turbopuffer namespace + hybrid search over
   a chunk sample; evaluate against DuckDB cosine. The new sharding feature
   (research brief §5) should be validated in the spike — tenant/shard
   layout matters for the multi-user pivot.
2. **Sandbox/compute**: today agents run as local subprocesses (exec_backend)
   and on the Hetzner box. Daytona (or E2B/Modal/Fly) evaluation → research
   brief §4. Recommended shape: keep LocalProcessBackend for personal v1;
   add a `remote` backend behind `RemoteExecProvider` when onboarding friends
   (the seam already exists — `runtime/remote_exec/` + `prime_exec.py`).
3. **Hetzner scaling plan**: current box = 4 vCPU/15GB/150GB (CX42-class),
   10% disk used, UFW 22-only, tunnel-only egress. Scaling path: (a) friends
   → same box with per-user namespaces + auth (multi-user gate G7, ~Nov
   2026); (b) >50 users → Hetzner App/Node pools or fly.io; sandbox agents
   move to Daytona/E2B. Write `infrastructure/runbooks/scaling.md`.

---

## 8. Agent-facing memory + account-level memory + anydoc

**VERIFIED on main:**
- `substrate/memory/` — account-level memory substrate (store, recall,
  router, models; #2989 "agent-memory S2a" merged Aug 7). API surface:
  check `interfaces/research/api/` memory routes (search "memory" in app.py).
- Note-taking: `roles/note_taker/`, `substrate/note_taker*`, NotesPanel UI.
- AnyDoc (Firecrawl) now in the ingest pipeline (#3002) — doc→markdown for
  agent memory ingestion is live.

**GAPS (DO-NOW):** persist long-term cross-document memory: memory substrate
exists but needs (a) document-level memory hooks (every ingested doc updates
account memory), (b) recall prompt injection in the composer (personal
context for §5.3), (c) a memory dashboard UI (search + browse account
memory). Map Firecrawl anydoc as the memory *format* layer (doc → markdown →
memory events).

---

## 9. v1 focus + product roadmap

- **v1 (NOW)**: web app activation = this spec's DO-NOW list + operator gates
  (G2 counsel, G7 six-month demo, operator usage).
- v2 iPad → v3 iPhone → v4 Google Play: the reading app is already a
  responsive SPA (viewport tiers, PWA-friendly); native shells come later.
- v5 RL, v6 model building: RLM trajectory harvesting (§15.7, rlm_integration
  §5.5) + Prime Intellect verifiers (integration_prime_intellect.md) are the
  on-ramps. Do not build now.

## 10. Sub-agent orchestration for the next agent

The operator asked for swarms across Claude Opus 5/4.8, codex-cc, glm-cc,
kimi-cc, deepseek-cc, mimo-cc. On THIS machine the verified RLM selectors are:
`kimi-sub/k3` (frontend/design, 1M ctx), `openai-codex/gpt-5.3-codex-spark`
(code), `grok-sub/grok-4.5` (adversarial review), `deepseek/deepseek-v4-pro`
(deep reasoning), `deepseek/deepseek-v4-flash` (bulk), `zai/glm-5.2` (1M ctx),
`xiaomi-token-plan-sgp/mimo-v2.5-pro` (vision). Map: UI→k3, backend→codex,
review→grok, corpus analysis→glm/k3, bulk extraction→flash, vision→mimo.
Use the file-handoff pattern (children write files; parent reviews; run the
artifact's own gate before accepting). Never fan out >6 in flight.
NOTE 2026-08-11: kimi-sub/k3 + grok-sub + openai-codex extension spawns were
flaky this session (empty sessions / auth preflight failures); deepseek
spawns were reliable. Re-check selector health before fan-out.

## 11. Immediate next actions (first agent to pick this up)

1. Land PR #3006 (arXiv) — CI green.
2. Review/land #2997 (Grok OAuth) + #3000/#3001/#2999/#2998/#2996/#2995
   (the Aug-7 BYOK stack) — they are the BYOT foundation.
3. Finish the usage-panel PR (child in flight this session) — then build the
   balance chip into the model dropdown (§3.3).
4. Operator: onboard keys via Settings UI → set `ANTIEK_BYOT_ONLY=1` → strip
   provider keys from `/etc/antiek/secrets.env` (§3.1).
5. Ratify RLM decisions + wire PrimeExecProvider into RLM leaves (§2).
6. Wheel-of-styles UI + universal asset→HTML routing (§5).
7. Turbopuffer Wedge-1 spike incl. sharding (§7.1).
8. Write marketplace + TollBit decision docs (§6) — gated on G2/G3.
9. Per-second attribution: verify impression→ledger→attribution e2e; build
   AdvertiserConsole UI (§6.4).
10. Memory hooks + dashboard (§8).
