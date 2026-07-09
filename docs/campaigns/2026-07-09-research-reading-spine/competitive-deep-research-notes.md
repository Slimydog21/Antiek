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
- Closed (em, 2026-07-09): collective draft merge + written analysis auto-open via same openMergedResearchWindow chokepoint.
- Closed (en, 2026-07-09): hosted HTML highlight → float deep research selection + budget (reading≡research on marketplace books).
- Closed (eo, 2026-07-09): collective document merge seeds twin notes (recursive note-taker parity with spawn merge).
- Closed (ep, 2026-07-09): collective onDocMerged remounts research context (flywheel parity with spawn merge eh).
- Closed (eq, 2026-07-09): DecisionTreeDriverBadge compact daily budget usage bar (spent/cap/remaining) on all badge mounts.
- Closed (er, 2026-07-09): hosted book optional arxiv/substack/URL pub refs on float DR (ResearchThis parity).
- Closed (es, 2026-07-09): hosted book deep research full window mode (floating | full).
- Closed (et, 2026-07-09): ResearchThis full working-region deep research window (distinct from legacy /inv handoff).
- Closed (eu, 2026-07-09): hosted book mounts CollectiveResearchPanel over open DR spawns (multi-select merge into the book).
- Closed (ev, 2026-07-09): merge/analysis re-open as full working-region hosted HTML (windowMode full on openMergedResearchWindow).
- Closed (ew, 2026-07-09): Midnight Oil deposit open full working-region HTML window (parity with merge full).
- Closed (ex, 2026-07-09): Midnight Oil auto-opens deposit HTML floating after deposit/auto-deposit (opt-out checkbox).
- Closed (ey, 2026-07-09): collective continue-as-unit full working-region window (parity with reading/hosted full DR).
- Closed (ez, 2026-07-09): hosted TwinNotesPanel remounts with context refresh key after collective merge/promote.
- Closed (fa, 2026-07-09): DR host TwinNotesPanel remounts with context refresh key (parity with hosted ez).
- Closed (fb, 2026-07-09): NEXT-WAVE-after-fa.md honest gap map for future agents (live injectors/env gates + product residual candidates).
- Closed (fc, 2026-07-09): main Reading ResearchThis mounts CollectiveResearchPanel over open DR spawns (parity with hosted eu).
- Closed (fd, 2026-07-09): DecisionTreeDriverBadge Refresh re-fetches driver + budget usage bar.
- Closed (fe, 2026-07-09): FloatMenu Deep-research full + HighlightToolbar/Reading viewMode full (highlight hosts parity).
- Closed (ff, 2026-07-09): ResearchContextPanel recursive note-taker twin metrics (insight/question/other).
- Closed (fg, 2026-07-09): Settings lists proposed Antiek-bench sub-benchmark tasks + propose≠promote honesty banner.
- Closed (fh, 2026-07-09): BlockDetail deep research opens floating|full window (chase /inv fallback only).
- Closed (fi, 2026-07-09): ResearchContextPanel intelligent search metrics (hit_count/query) over twin substrate.
- Closed (fj, 2026-07-09): DecisionTreeDriverBadge Settings deep-link for model install + budget.
- Closed (fk, 2026-07-09): TwinNotesPanel twin-notes-metrics data attributes (note/insight/question counts).
- Closed (fl, 2026-07-09): HTML draft handoff from hosted document → Write (?html_draft=) with honest import-deferred banner.
- Closed (fm, 2026-07-09): Write loads hosted HTML draft (HTML-only), prefills title, seeds brainstorm plain text; outline import still deferred.
- Closed (fn, 2026-07-09): spawn + collective merge expose Open Write HTML draft handoff link.
- Closed (fo, 2026-07-09): Midnight Oil deposit Open Write HTML draft handoff.
- Closed (fp, 2026-07-09): Write stamps project-type freeform provenance html_draft:document_id when draft loads.
- Closed (fq, 2026-07-09): Write shows disabled Import HTML into outline control (honest deferral; propose≠invent).
- Closed (fr, 2026-07-09): ResearchLaunchBudgetPanel Settings deep-link for daily cap + decision-tree.
- Closed (fs, 2026-07-09): NEXT-WAVE-after-fr.md honest gap map for post-fr residuals.
- Closed (ft, 2026-07-09): Write create piece imports HTML draft plain text into outline section 0 (createSection + updateSectionProse).
- Closed (fu, 2026-07-09): multi-section HTML outline import via h1–h3 split (MAX 20 sections).
- Closed (fv, 2026-07-09): nest h2/h3 under parent_section_id by heading level on Write import.
- Closed (fw, 2026-07-09): Write HTML draft shows outline section preview before create piece.
- Closed (fx, 2026-07-09): Write import prefers HTML fragments for section prose (HTML-first land).
- Closed (fy, 2026-07-09): import badge data-html-prose + NEXT-WAVE-after-fx.md.
- Closed (fz, 2026-07-09): offline twin seed on deliverable after Write HTML draft import (recursive note-taker).
- Closed (ga, 2026-07-09): TwinNotesPanel mounted on open Write piece (reading≡write note-taker).
- Closed (gb, 2026-07-09): ResearchContextPanel on open Write piece; remount after twin promote.
- Closed (gc, 2026-07-09): DecisionTreeDriverBadge on open Write piece (model + budget).
- Left (env/operator): floating multi-agent *live* collective chat (merge+continue unit ships); live midnight oil multi-provider; paid marketplace rails; live hydrate/seed injectors; operator install of weekly LaunchAgent; PR #465 main merge.

- Closed (hh–ho, 2026-07-10): TwinNotes offline-seed honesty; twin-promote/session-flywheel/research-progress/collective/spawn-merge metrics; marketplace twin-seed honesty; Midnight Oil recommended-ceiling metrics + formula note.
- Closed (hp, 2026-07-10): ResearchLaunchBudgetPanel projection-metrics (usd band, would_exceed, chars, tier) for competitive budget-before-fire audit.

- Closed (hq–hv, 2026-07-10): hydrate/twin live status Settings + boot wire; suite rewrite metrics; evidence pack metrics; decision-tree driver budget metrics.

- Closed (io–is, 2026-07-10): knowledge-dense PD catalog expansion; host research substrate; catalog honesty API + server honesty UI; free public-domain research filter.

- Closed (iu–iw, 2026-07-10): marketplace host + library deep research float|full (reading≡research on HTML books).

- Closed (iy, 2026-07-10): marketplace host DR budget soft-gate before fire.

- Closed (jf–jo, 2026-07-10) **Depth-tier product spine (reading ≡ research ≡ write ≡ midnight oil):**
  - (jf) Collective continue-as-unit Settings depth prefill
  - (jg) ResearchThis Settings depth prefill
  - (jh) WriteHome piece DR Settings depth prefill
  - (ji) research_tier persists on spawn + floating session open + launchFloatingDeepResearch
  - (jj) useSettingsResearchTier shared hook; Reading FloatMenu / HighlightToolbar / BlockDetail
  - (jk) session host chrome surfaces research_tier (payload wins over Settings)
  - (jl) Midnight Oil recommended ceiling × tier (fast 0.5 / deep 1.0 / wrestle 2.0)
  - (jm) spinResearch full workstation path + InvestigationStart research_tier
  - (jn) TalkToBook Settings research_tier on askBook
  - (jo) progress poll cadence by tier (fast 2s / deep 4s / wrestle 8s)
  Competitive match: budget-capped depth honesty + multi-minute wrestle posture without second runtime.


- Closed (jt–jw, 2026-07-10) **Depth → bench + intensity honesty:**
  - (jt) session flywheel research_tier → Antiek-bench task_class on complete
  - (ju) shared progress poll map (TS)
  - (jv) shared MO ceiling multiplier map (TS ↔ Python contract)
  - (jw) budget panel intensity chrome on every launch surface
  - (jx) substrate TIER_MULTIPLIER closed-set contract test for fleet parity


- Closed (jy–ka, 2026-07-10) **Meta-reading + progress identity:**
  - (jy) MetaReading Settings research_tier on generate
  - (jz) progress_payload includes spawn research_tier
  - (ka) ResearchProgressPanel API research_tier fallback (prop wins)


- Closed (kd–ke, 2026-07-10) **Evidence + collective depth identity:**
  - (kd) Evidence pack UI research_tier chrome (citation-trust depth posture)
  - (ke) Collective multi-spawn recommended_research_tier depth-max for continue-as-unit


- Closed (kf–kl, 2026-07-10) **HTML + research-context pack depth identity (reading ≡ research):**
  - (kf) competitive notes + suite-proposal plan AC recheck (propose≠promote)
  - (kg) intelligent context search payload research_tier when spawn-scoped
  - (kh) context_search HTML projects tier=…
  - (ki) evidence + progress HTML projects tier=… (parity kh)
  - (kj) collective HTML recommended_tier + member tiers
  - (kk) ResearchContextPack.research_tier + research_context_html + prompt_block
  - (kl) ResearchContextPanel pack chrome (parity evidence kd)
  Competitive bar: every human-viewable engagement surface that can name a spawn
  also names closed depth (fast|deep|wrestle) in API + HTML + UI when identity exists.
  NotDiamond remains advisory only (L7). Live hydrate/seed/MO-step injectors dual-gate (L1–L4).


- Closed (kn–ko, 2026-07-10) **Merge + publication-attach depth identity:**
  - (kn) merge_product_payload research_tiers + recommended_research_tier + HTML + SpawnMergePanel
  - (ko) attach-refs research_tier + PublicationAttachPanel chrome (citation path depth)
  Completes depth identity on merge-into-asset and mid-session arxiv/substack attach.


- Closed (kq–ks, 2026-07-10) **Flywheel pack + recursive note-taker depth identity:**
  - (kq) SessionFlywheelPanel session||context.research_tier fallback + pack chrome
  - (kr) TwinNotesPanel researchTier chrome; DeepResearchSessionHost wire
  - (ks) HostedHtml + Write TwinNotes researchTier wire (reading ≡ write ≡ DR)
  Recursive note-taker substrate now inherits closed depth on every major host.


- Closed (ku–kv, 2026-07-10) **Decision-tree driver + depth co-display:**
  - (ku) DecisionTreeDriverBadge researchTier chrome; DR/Hosted/Write hosts
  - (kv) Midnight Oil create path wires researchTier into driver badge
  Model driver + daily budget + closed depth share one advisory surface.
  NotDiamond remains advisory only (L7).


- Closed (kx–ky, 2026-07-10) **Marketplace driver depth + dual-gate enablement prep:**
  - (kx) MarketplaceHost DecisionTreeDriverBadge hostDrTier wire
  - (ky) DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md for live hydrate/seed/MO-step
  Completes driver+depth co-display on marketplace and documents honest live enablement.

