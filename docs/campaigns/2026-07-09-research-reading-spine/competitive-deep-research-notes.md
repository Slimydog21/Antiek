# Competitive deep-research notes (evidence, non-gating)

Campaign 2026-07-09. Quality bar for Antiek deep research — study of technical decisions; not a ship gate alone.

## Patterns to match or beat

| Competitor pattern | Technical decision | Antiek implication |
|---|---|---|
| Multi-agent fan-out with shared memory | Parallel sub-questions + merge | Cascade session + `merge_spawn_outputs` / research_artifact compose |
| Citation-required synthesis | Claims tied to source chunks | insight_question `supported_by` edges + grounding |
| Budget-capped autonomous runs | Hard USD halt | research_runner BudgetManager + midnight oil ceiling |
| HTML/notebook deliverable | Portable, agent-editable | html_projection + research_artifact HTML (PDF ingest only) |
| Source connectors (arxiv, web, newsletters) | First-class acquisition | Keep arxiv/substack modules; call from runner tools |
| Model routing | Auto or manual | model_control manual now; NotDiamond advisory only |

## Antiek differentiators to preserve

1. **Twin notes** on every asset (recursive note-taker) — not just chat transcripts.
2. **Reading ≡ research** — same engagement spine for books and investigations.
3. **Script-free HTML** as canonical human view (craftsmanship + agent control).
4. **Honest failure classification** on dispatch (no fake green).
5. **Budget projection before send** — operator sees over-budget before fire.

## Gaps this campaign closed vs left

- Closed: substrate spine spawn/twin/merge; model registry + projection; HTML path proof; deferred specs for midnight oil / marketplace / bench; ND verdict.
- Closed (cx–dg, 2026-07-09): reading float budget + driver chokepoint; moil driver prefill + deposit window; hosted book DR launch; collective continue-as-unit; twin autoSeedIfEmpty; budget soft-gate family across launch surfaces.
- Closed (dh–dt, 2026-07-09): next-wave live gates inventory; collective budget gate; marketplace catalog filter + auto-open + library list/filter + rehydrate open + HTML metadata; citation trust honesty; deferred live multi-agent council spec; Antiek-bench weekly LaunchAgent + dogfood→usage events recursive rewrite flywheel + Settings UI.
- Closed (du–ea, 2026-07-09): Settings flywheel refresh (proposal/usage/ND after dogfood); marketplace driver badge; twin auto-promote to research context after load/seed on DR + hosted hosts.
- Closed (ec–ef, 2026-07-09): remount research context after twin promote / publication attach / flywheel complete; citation trust on attach results.
- Closed (eg–ej, 2026-07-09): notes refresh; remount after spawn merge; shared onContextNeedsRefresh chokepoint on DR + hosted hosts.
- Closed (ek–el, 2026-07-09): competitive notes through ej; draft_combined merge auto-opens hosted HTML window (parent merge stays manual; autoOpenDraft opt-out).
- Left (env/operator): floating multi-agent *live* collective chat (merge+continue unit ships); live midnight oil multi-provider; paid marketplace rails; live hydrate/seed injectors; operator install of weekly LaunchAgent; PR #465 main merge.
