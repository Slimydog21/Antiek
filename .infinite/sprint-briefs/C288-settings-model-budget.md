# C288 — Settings: model selection + budget usage + prompt projection

**Authored:** 2026-07-09 (Grok /infinite host)  
**Status:** brief only — not yet executed  
**Repo truth:** `origin/main@c4d93c11`

## 1. Current state (verified)

| Surface | Reality |
|---|---|
| Settings UI | **Stub.** `apps/reading/src/modes/Settings/index.tsx` shows viewport tier / OS theme / reduce-motion only. Explicit "Coming later" list includes "Dispatch-tier overrides + budget caps". |
| Model picker / decision-tree tab | **Missing.** No `ModelPicker` / decision-tree component in reading app. |
| Per-key usage bar | **Missing** as a Settings surface. |
| Prompt cost projection | **Missing** as pre-submit UI. |
| Registered providers (health) | **Exists.** `/health` returns `registered_providers` + `providers_ready` (prod live: deepseek, hermes, xiaomi, zai, zai_reasoning). |
| Research budget caps | **Exists** in cascade API (`BudgetCap`, `per_research_budget_usd`, aggregate budget). UI reads defaults in ResearchWorkstation. |
| Continuous daemon budget | **Exists** substrate-side (`orchestration/continuous/budget.py`, $5/day default via misnamed `ANTIEK_DAEMON_HOURLY_BUDGET_USD`). Spawn wiring still `no_op_spawn` (midnight-oil residual). |
| BYOK store | **Exists** for X/Twitter personal pipeline credentials only (`runtime/byok/`) — **not** a general multi-provider API-key settings vault. |
| NotDiamond | Spec complete (`~/specs/antiek-notdiamond/`); Wave-1 code on stale local branch only; **not on main**. Rebuild in flight. |
| Antiek-bench | **Missing** (no hits on main). |

## 2. Reuse, do not reinvent

1. **Provider inventory** — `app.state.registered_providers` + `/health` fields (already public-ish).
2. **Research budget types** — `BudgetCap` + cascade request fields; extend patterns rather than invent a second budget ontology.
3. **Daemon budget sidecar** — `~/.antiek/budgets/daemon_<date>.json` shape for daily spend persistence (can inspire operator budget ledger).
4. **Master-spec §13.5 / §15.10** — pay-as-you-go token-budget model is the monetization north star; Settings must surface *operator* budget, not only ad campaign budgets.
5. **Dispatch config** — `substrate/dispatch/config.yaml` + router; model override must stay on the **advisory / explicit override** side of §16 (no silent re-route of the registered provider set).

## 3. Minimal SPR-01 (executable next)

**Name:** Settings Model & Budget Readout (operator-local)  
**Goal:** Replace Settings stub section with a real, honest panel:

1. **Models / providers table**  
   - Source: `/health.registered_providers` + static dispatch catalog (config.yaml) for display names.  
   - Show: provider id, ready?, default role bindings if known.  
   - Explicit "Add model" is **SPR-02** (needs secret store expansion beyond X BYOK).

2. **Budget bar (operator daily/monthly)**  
   - Read env-backed caps if present (`ANTIEK_DAEMON_HOURLY_BUDGET_USD` / future `ANTIEK_OPERATOR_BUDGET_USD`).  
   - Read spent-to-date from a **new** small ledger OR daemon budget sidecar if operator budget shares it.  
   - If no spend ledger exists yet: show cap + "spent: unknown (ledger not wired)" — **honest**, never invent $0.

3. **Prompt projection (API + UI)**  
   - `POST /ops/prompt-cost-estimate` (auth-required): body `{provider, model?, input_chars, expected_output_tokens?}` → `{estimated_usd_low, estimated_usd_high, would_exceed_budget: bool|null, notes}`.  
   - Deterministic table-driven rates (no network). Unknown model → explicit `null` + reason.  
   - Settings + Research start form show projection before dispatch.

### Files (expected)

```
interfaces/research/api/settings_budget.py   # NEW routes
interfaces/research/api/app.py               # include router
apps/reading/src/modes/Settings/index.tsx    # real panel
apps/reading/src/api/settings.ts             # NEW client
tests/test_settings_budget_api.py            # NEW
apps/reading/src/modes/Settings/Settings.test.tsx  # NEW
```

### Acceptance tests

- Health-derived provider list renders; empty providers → honest empty state (not fake models).
- Budget bar: cap present / cap absent / spent unknown cases all covered.
- Projection: known model returns finite range; unknown model returns null + reason; over-budget flag true when estimate > remaining when remaining is known.
- §16: no change to `register_default_providers` membership from Settings UI alone.
- No secret values in API responses (key fingerprints only if keys added later).

## 4. Explicitly NOT in SPR-01

| Deferred | Why |
|---|---|
| NotDiamond advisory routing | Separate measured wedge (`antiek-notdiamond` Wave 2+); rebuild Wave 1 first |
| Antiek-bench recursive weekly suite | New product surface; needs usage-pattern corpus first |
| Full multi-provider secret vault / "add model" | Needs threat model + key storage beyond X BYOK |
| Midnight oil UI (time + goals + price ceiling) | Depends on continuous `spawn_fn` wiring (still `no_op_spawn`) |
| Floating research windows / merge instances | Reader/workstation interaction model; separate htmlspec |
| Marketplace book purchase flow | Partial substrate exists; legal/publisher gates |

## 5. Sequencing after SPR-01

1. **SPR-02** — Add-model + key storage (generalize BYOK patterns carefully).  
2. **SPR-03** — Decision-tree tab for per-prompt model override (ties into ResearchWorkstation StartResearch).  
3. **Midnight oil productization** — wire `spawn_fn` → loop_one; Settings price-ceiling approve; rename continuous as "Midnight oil" in UI only if operator wants that brand.  
4. **NotDiamond Wave 2** — advisory DRW routing after Wave 1 lands + §14.4 baseline report.  
5. **Antiek-bench** — weekly task slices from real investigation outcomes.

## 6. NotDiamond usefulness verdict (investigation)

**Verdict: YES, as a measured advisory wedge — already correctly scoped in `~/specs/antiek-notdiamond/`.**

- Useful if and only if it **beats** hand-measured §14.4 dispatch on DRW role calls with evidence.  
- **Not** useful as an authoritative router (§16 REJECT of Prime-as-provider applies equally).  
- Wave 1 (adapter + event attribution) is the precondition for any usefulness measurement.  
- Stale branch `notdiamond/integration` is based on `1c4d5df9` with schema v28; main is **EVENT_SCHEMA_VERSION = 31** → rebuild required, do not merge stale stack.

## 7. Midnight oil (autonomous swarm) — residual truth

- Substrate: `orchestration/continuous/daemon.py` + budget caps **exist**.  
- Default spawn is still **`no_op_spawn`** — "Production wiring lives in a follow-up Sprint 14 PR".  
- UI: SuggestedResearch + daemon badge exist; **no** "set time of work + goals + recommended price ceiling" product flow.  
- Brand "midnight oil" does not appear in codebase; continuous mode is the technical name.

## 8. Ship bar for any Settings PR

Mechanical green (tsc/vitest/pytest focused + declared-bar) · heterogeneous review · hardenx 0 REAL · no secret leakage · honest unknown-spend states · operator merge+deploy.
