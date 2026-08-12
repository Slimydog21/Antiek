# AI Role Lineup — forensic findings, taxonomy, and selector design

**Date:** 2026-08-12 · **Author:** Prime Agent (forensic + implementation session)
**Status:** implemented on branch `feat/ai-role-lineup` (backend + frontend + tests + docs)

---

## 1. What this is

The operator wants the BYOT model-selection experience organized around AI
**roles**, with two selector layers:

1. **General selector** — one model per role, presented as a football lineup
   (FIFA Ultimate Team style) where substitutions are made by tapping a
   position and a bench card.
2. **Advanced selector** — a per-action/behavior model override surface,
   bucketed under the role that owns the action.

Before building, this document records the forensic investigation that
answers: *which AI roles/actions actually exist in the product, and is the
operator's four-role taxonomy (writer / data miner / data refinement /
data verification) complete?*

## 2. Forensic method (read-only)

| Surface | What was examined | Source |
|---|---|---|
| Backend role catalog | `substrate/dispatch/config.yaml` role_tiers + `substrate/constants.py` ROLES/DEFAULT_ROLE_TIER | origin/main |
| Every dispatch call site | `grep role=` across substrate/ + apps/ → 22 distinct roles | origin/main |
| Non-dispatch AI surfaces | multimedia router (Krea), embeddings (graph), vision providers, transcription (whisper), TTS (gpt-4o-mini-tts), RLM bridge tools | origin/main |
| Behavior catalog | `substrate/schemas/events.py` ActionTypes (132 typed events) | origin/main |
| Frontend task buckets | `apps/reading/src/api/composerProjection.ts` ComposerDecisionTask (7) | origin/main |
| BYOT vertical | ModelPicker.tsx, settings_models_admin.py, owner_byot_dispatch.py, byot_provider_catalog.py, AddModelPanel/UsagePanel | origin/main + prod |
| Deployed prod | api.antiek.ai /health + 401-gated /settings/* routes; SPA bundle strings ("Model driver", "Add model", "Settings") | prod 167.235.202.98 |

## 3. The complete inventory — every AI role/action found

### 3.1 Dispatch roles (LLM, routed via config.yaml tiers)

| Role | Tier | What it does |
|---|---|---|
| decomposer | pro | split research questions |
| evidence_retriever | flash | fetch evidence |
| parameter_extractor | flash | extract search params |
| connector | pro | cross-domain connection |
| synthesizer | synthesis | human-facing synthesis |
| user_agent | pro | talk-to-book conversational agent |
| note_taker | flash | emergent notes |
| challenger | pro | adversarial questioning |
| grounder | flash | grounding checks |
| tier_assigner | flash | rule-based routing (LLM only downward) |
| constraint_checker | flash | constraint preflight |
| verifier | verify | cross-family verification |
| knowledge_extractor | pro | phase-8 knowledge extraction |
| thought_partner | pro | advisory companion |
| creative_writer | pro | write draft generation |
| autocomplete | flash | inline completions |
| write_repository | (config gap) | repository write actions |
| write_composition | (config gap) | composition actions |
| write_editor | (config gap) | editor assist |
| interviewer | (config gap) | speak-mode interviewer |
| attribution | (config gap) | page attribution |
| extractor | (config gap) | distillation/visual claims |

*(config gap = referenced at call sites; no explicit role_tiers entry — they
resolve through DEFAULT_ROLE_TIER or the router's fallback path. Flagged,
not fixed, by this vertical.)*

### 3.2 Non-dispatch AI surfaces

| Surface | Kind | Evidence |
|---|---|---|
| transcription | voice | whisper-1 tier, voice capture |
| text-to-speech | voice | gpt-4o-mini-tts tier, interview voice mode |
| media generation | media | Krea via `substrate/multimedia/provider_router.py` |
| graph embeddings | embedding | `graph/embedding_meta.py`, EMBED_MODEL_REGISTER event |
| retrieval indexing | embedding | turbopuffer adapter |
| vision (frames/claims) | llm+vision | VISUAL_FRAME_IDENTIFIED / VISUAL_CLAIMS_EXTRACTED |
| RLM agent bridge | llm agent | `graph/rlm_tools.py` (web_search, fetch_url, search_graph, SubLLMWithTools) |
| AI sidecar UI actions | llm | `ai_actions/actions.py` apply/undo |

### 3.3 Frontend behavior buckets (composer projection)

`deep_research, research_synthesis, reading, twin_note, writing, multimedia, general`
— the 7 advisory task buckets the ModelPicker already projects candidates for.

## 4. The taxonomy decision

The operator's four roles map onto the inventory as follows (evidence in §3):

### General roles (the formation)

| Role | Position | Covers (actions) |
|---|---|---|
| **writer** | ATT | research_synthesis, creative_draft, write_repository, write_composition, write_editor, autocomplete, thought_partner |
| **data_refinement** | MID | decomposition, connector, talk_to_book, interviewing, meta_reading, visual_claims |
| **data_miner** | DEF | evidence_retrieval, parameter_extraction, note_taking, knowledge_extraction, distillation, attribution, tier_assignment, constraint_checking, transcription |
| **data_verification** | GK | verification, challenge, grounding, quality_gates, groundedness_scoring |

### Missing roles — the forensic answer

**Yes, roles are missing.** Five gaps are real and evidence-backed:

1. **orchestrator** — *planning/dispatch*. Nothing covers cascade-plan
   construction, chase-tree planning, or RLM bridge route decisions. Evidence:
   deep-research PlanEditor/launchPlan surface, `decompose.requested` +
   `rlm.bridge.decided` events, tier_assigner is rule-based (not a planner).
2. **critic** — *adversarial review of human-facing deliverables*. The
   operator's taxonomy has verification for DATA; nothing reviews the
   writer's OUTPUT (audit findings, deliverable critique). Evidence:
   `audit.finding_emitted`, the own-your-mind program's adversarial-review
   deliverable (docs/own-your-mind/06-adversarial-review.md), quality gates
   run verifier roles on data, not prose.
3. **media_creator** — *image/video generation* (Krea). A separate model
   class (not token-based LLM). Evidence: multimedia provider_router,
   /krea routes, multimedia task bucket.
4. **voice** — *speech synthesis*. TTS is a distinct model class from
   transcription (which is mining). Evidence: tts tier, Speak voice mode.
5. **indexer** — *graph embeddings + retrieval indexing*. Embedding model
   choice (BGE-family) is a distinct model class. Evidence: graph embedding
   modules, EMBED_MODEL_REGISTER, turbopuffer adapter.

Deliberate non-additions: *tier_assigner* is rule-based (not a model
choice), *ai_actions* are UI-mutation plumbing (not a model-driven role),
*RLM bridge* folds into orchestrator + user_agent.

### Advanced actions (the tactics board)

27 actions, each bucketed under exactly one general role, each carrying its
real dispatch_role + default tier (or `none` for non-dispatch surfaces) —
this makes a future binding vertical mechanical (the mapping is data).

## 5. Selector design (as built)

### 5.1 General selector — the pitch (FIFA Ultimate Team style)

- A football pitch (green gradient, white markings, penalty areas) with
  positions placed by formation: ATT top (writer, media_creator), MID
  (data_refinement, orchestrator, critic, voice), DEF (data_miner,
  indexer), GK (data_verification).
- Each position is a player-style card: position tag (GK/DEF/MID/ATT),
  role name, assigned model (`Auto — platform default` when unassigned),
  STR badge, and a `NEW SIGNING` chip on the five discovered roles.
- **STR is tier strength from the dispatch tier NAME** (synthesis/verify=9,
  pro=8, flash=6, presets/user models=7 unmeasured) — explicitly never a
  model-quality measurement; tooltip says so.
- **Substitution**: tap a position → it lifts and a sub bar appears →
  tap **Substitute** → the bench (your BYOK models + BYOT presets + server
  dispatch tiers) slides up → tap a bench card → the assignment PUTs and
  the card shows the new model. **Auto** resets a position to the platform
  default. Keyboard-accessible (buttons, listbox, Escape).
- **Honest states**: loading, error with retry, empty bench ("add your own
  keys in Add model"), saved receipt with timestamp, save-failure surfaced.

### 5.2 Advanced selector — the tactics board

- Per-role tab switcher; each role expands to its actions with label,
  blurb, dispatch_role and default_tier in mono.
- Per action: **Auto** (follow the formation pick) or a direct model pick
  from the bench. Direct picks override only that action.

### 5.3 Registry + API (backend)

- `GET/PUT /settings/lineup` — owner-scoped, JSON sidecar
  `~/.antiek/settings/lineup.json` (mirrors user_models.json precedent:
  lenient reads, fsynced writes, single-writer API process).
- Every choice is validated against the **live bench** (user models +
  presets + dispatch tiers incl. fallback chains); unknown models are
  rejected value-free. `null` (Auto) always valid.
- **Scope discipline (house precedent)**: the lineup stores operator
  intent; it does NOT silently mutate dispatch routing. Binding
  assignments to dispatch (provider_override per role/action) is the
  explicit next vertical — same shape as AddModelPanel → route authority.

## 6. Verification (all run, all green)

- Backend: `tests/test_settings_lineup.py` 6/6; `test_settings_models_admin.py` +
  `test_settings_budget_api.py` 98/98 (no regression from the mount); ruff clean;
  mypy: **zero new errors** vs the 241-file baselined state (2 of my own
  errors found and fixed — including a real comprehension bug).
- Frontend: `LineupPitch.test.tsx` 6/6, `LineupPanel.test.tsx` 5/5,
  Settings.test.tsx updated for the 3-tab reality; **full suite 2,014/2,014**;
  `tsc -b --noEmit` clean.
- The one full-suite failure on the first run was the known pre-existing
  Reading.test.tsx flake (documented in #3048); the rerun passed everything.

## 7. Open items (honest)

- **Binding vertical**: wiring lineup assignments into dispatch
  (`provider_override` per role/action) + prod-parity coverage for the
  registry — deliberately next, per house scope discipline.
- **Config-gap roles** (write_repository/write_composition/write_editor/
  interviewer/attribution/extractor have no explicit role_tiers entry):
  flagged in §3.1, not fixed here.
- **Deploy**: not deployed. Prod runs `8a26f499` + an uncommitted hotfix;
  main is `2f14a983b6` with a RED declared-bar (3 NEW mypy violations in
  acquisition/arxiv/bulk.py). This branch is based on current main; merge +
  deploy when the bar is green.
