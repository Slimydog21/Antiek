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


- Closed (la–lb, 2026-07-10) **Recursive note-taker seed depth identity:**
  - (la) seed_twins_for_asset research_tier from source_spawn + HTML tier=
  - (lb) TwinNotesPanel prop||API research_tier fallback chrome
  Twin seed + UI now inherit closed depth when spawn-scoped.


- Closed (ld–le, 2026-07-10) **Fleet handoff + twins list spawn-scoped tier:**
  - (ld) SESSION-ARC-kk-lc-depth-identity.md zero-context fleet handoff
  - (le) GET /engagement/twins?spawn_id= research_tier + TwinNotesPanel list wire


- Closed (lg–lh, 2026-07-10) **Driver+depth co-display on collective + pure reading:**
  - (lg) CollectiveResearchPanel DecisionTreeDriverBadge researchTier
  - (lh) TalkToBook + MetaReading DecisionTreeDriverBadge researchTier
  Completes model+budget+depth on multi-spawn continue and book-native talk/meta-read.


- Closed (lj, 2026-07-10) **Spawn merge driver+depth:**
  - (lj) SpawnMergePanel DecisionTreeDriverBadge; post-merge recommended_research_tier wins
  Single-spawn merge path now co-displays model driver, budget, and depth.


- Closed (ll, 2026-07-10) **Launch-path driver+depth complete:**
  - (ll) ResearchThis + StartResearch DecisionTreeDriverBadge researchTier
  Major launch hosts now all co-display model driver, daily budget, and closed depth.


- Closed (ln, 2026-07-10) **Workstation chat Ask driver+depth:**
  - (ln) ChatInputArea DecisionTreeDriverBadge with launchTier
  In-investigation follow-on prompts now match StartResearch co-display.


- Closed (lp, 2026-07-10) **Graph block DR entry driver+depth:**
  - (lp) BlockDetail DecisionTreeDriverBadge researchTier
  Second FloatMenu host (graph node detail) co-displays model+budget+depth.


- Closed (lr, 2026-07-10) **Multi-minute progress driver+depth:**
  - (lr) ResearchProgressPanel DecisionTreeDriverBadge when tier known
  Long-horizon plan→cite jobs keep model driver, budget, and depth visible mid-run.


- Closed (lt–lu, 2026-07-10) **Flywheel complete driver+depth:**
  - (lt) SessionFlywheelPanel DecisionTreeDriverBadge (prop → post-complete effective)
  - (lu) DeepResearchSessionHost wires session researchTier into flywheel panel

- Closed (lw, 2026-07-10) **Marketplace catalog research domains + STEM PD:**
  - CatalogEntry.subjects + filter_by_subject + search haystack
  - STEM PD spine: pd-elements, pd-principia, pd-novum (HTML-first)
  - by_subject honesty on GET /marketplace/catalog
  - UI domain chips + by_subject metrics (server honesty preferred)
  Live external catalog connectors remain deferred (L1/L2 arxiv/substack dual-gate).

- Closed (lx, 2026-07-10) **Marketplace catalog knowledge-source chips:**
  - Catalog.filter_by_source substrate (case-insensitive exact)
  - UI source chips compose free-PD × subject × text filters
  Offline demo catalog filter matrix product-complete; live connectors still deferred.


- Closed (ly, 2026-07-10) **Catalog HTML projection open:**
  - project_catalog_html substrate (chip filters free_only/subject/source)
  - GET /marketplace/catalog returns html (include_html opt-out)
  - MarketplaceHost Open catalog as HTML window

- Closed (lz, 2026-07-10) **PublicationAttach driver+depth:**
  - DecisionTreeDriverBadge on PublicationAttachPanel
  - researchTier prop (session preferred) + attach-response fallback
  - DeepResearchSessionHost wires session researchTier into attach panel

- Closed (ma, 2026-07-10) **Marketplace host → Antiek-bench book_qa usage:**
  - POST /host and /purchase-and-host record UsageEvent(task_class=book_qa, source=marketplace_host)
  - Shared bench usage store feeds Settings suite-proposal rewrite (propose≠promote)

- Closed (mb, 2026-07-10) **Marketplace host usage_event UI:**
  - HostResultResponse.usage_event types
  - Host land metrics + marketplace-host-usage-event chrome (propose≠promote)

- Closed (mc, 2026-07-10) **SESSION-ARC marketplace catalog lw–mb:**
  - SESSION-ARC-lw-mb-marketplace-catalog.md zero-context fleet handoff
  - Offline marketplace filter matrix + bench usage feed product-complete for demo

- Closed (md, 2026-07-10) **Midnight Oil ceiling budget fit:**
  - moil-ceiling-budget-fit chrome (fits|may_exceed|unknown)
  - remaining from budget projection; never invent $0

- Closed (me, 2026-07-10) **Midnight Oil approve soft-gate:**
  - Force override when ceiling may_exceed remaining daily budget
  - Unknown remaining never blocks approve

- Closed (mf, 2026-07-10) **Catalog HTML honesty lines:**
  - project_catalog_html By source / By subject for filtered set

- Closed (mg, 2026-07-10) **SESSION-ARC md–mf MO budget + catalog HTML:**
  - SESSION-ARC-md-mf-moil-catalog.md fleet handoff

- Closed (mh, 2026-07-10) **Host-land catalog subjects:**
  - marketplace-host-metrics data-subjects + chrome from catalog entry

- Closed (mi, 2026-07-10) **Chip-aware catalog HTML window ids:**
  - document_id encodes freePD/subject/source filters

- Closed (mj, 2026-07-10) **PublicationAttach dual-gate checklist link:**
  - Deep-link to DUAL-GATE-L1-L4-OPERATOR-CHECKLIST (prep only; never enables)

- Closed (mk, 2026-07-10) **SESSION-ARC lw–mj full wave:**
  - SESSION-ARC-lw-mj-catalog-moil-dualgate.md zero-context handoff

- Closed (ml, 2026-07-10) **Midnight Oil dual-gate checklist link:**
  - Parity mj attach surface; prep only for L4 live step

- Closed (mm, 2026-07-10) **Marketplace dual-gate checklist link:**
  - Completes dual-gate prep surface on attach + MO + marketplace

- Closed (mn, 2026-07-10) **Dual-gate prep triad close-out:**
  - Checklist links on PublicationAttach + Midnight Oil + Marketplace
  - Prep only; never enables L1–L4 injectors

- Closed (mo, 2026-07-10) **Twin seed domain subjects:**
  - Marketplace host twin seed body prefixes Research domains from catalog subjects

- Closed (mp, 2026-07-10) **Marketplace DR domain-aware launch:**
  - selection_text + goal_hint include catalog subjects
  - budget mount data-domains; DR status domains=

- Closed (mq, 2026-07-10) **Selective twin promote by kind:**
  - kinds filter on promote-context API + TwinNotesPanel UI
  - insights only | questions only | all for recursive note-taker merge

- Closed (mr, 2026-07-10) **Twin list filter by kind:**
  - Show all|insights|questions before selective promote (mq)

- Closed (ms, 2026-07-10) **Promote visible twins:**
  - One-click promote using current list filter (browse→merge)

- Closed (mt, 2026-07-10) **TwinNotes dual-gate checklist link:**
  - Completes dual-gate prep on attach + MO + marketplace + twins

- Closed (mu, 2026-07-10) **ResearchContext dual-gate checklist link:**
  - Completes dual-gate prep on research context hydrate path

- Closed (mv, 2026-07-10) **SESSION-ARC mp–mu twins dual-gate:**
  - SESSION-ARC-mp-mu-twins-dualgate.md fleet handoff

- Closed (mw, 2026-07-10) **Competitive duration band on progress:**
  - research-progress-competitive-band by tier + poll cadence honesty
  - dual-gate checklist on progress panel

- Closed (mx, 2026-07-10) **Multi-select twin note_id promote:**
  - `note_ids` filter on promote-context substrate/API (∩ kinds when both)
  - TwinNotesPanel checkboxes + Select visible / Clear / Promote selected
  - Per-note recursive note-taker merge into research context

- Closed (my, 2026-07-10) **Clear multi-select after promote + note_ids metrics:**
  - Selection clears after successful note_ids promote (browse→select→merge ready)
  - twin-promote-metrics data-promoted-note-ids / note_id-count audit honesty

- Closed (mz, 2026-07-10) **Chase selected twins as floating deep research:**
  - buildTwinChasePayload (questions first) + Chase selected / Chase full
  - launchFloatingDeepResearch chokepoint; selection clears on success

- Closed (na, 2026-07-10) **Twin chase budget soft-gate:**
  - ResearchLaunchBudgetPanel on multi-select + force override
  - parity marketplace iy; never invent $0 when unknown

- Closed (nb, 2026-07-10) **SESSION-ARC mq–na twins promote/chase:**
  - SESSION-ARC-mq-na-twins-promote-chase.md zero-context fleet handoff
  - note-taker path: filter → multi-select → promote/chase → budget gate

- Closed (nc, 2026-07-10) **TwinNotes driver badge + chase metrics:**
  - DecisionTreeDriverBadge on recursive note-taker
  - twin-chase-metrics spawn/model/tier/mode audit attrs

- Closed (nd, 2026-07-10) **Select questions|insights one-click:**
  - twin-select-questions / twin-select-insights multi-select helpers
  - union with existing selection for chase/promote path

- Closed (ne, 2026-07-10) **Invert multi-select visible twins:**
  - twin-invert-selection list-filter-aware
  - multi-select UX path product-complete offline

- Closed (nf, 2026-07-10) **SESSION-ARC mx–ne multi-select chase:**
  - SESSION-ARC-mx-ne-multi-select-chase.md fleet handoff
  - multi-select promote/chase path offline-complete

- Closed (ng, 2026-07-10) **Midnight Oil competitive recommended duration:**
  - mapResearchTierToRecommendedDurationMinutes (fast 3 / deep 10 / wrestle 30)
  - moil-duration-recommend chrome + Use recommended + tier chips
  - parity ResearchProgressPanel mw bands; offline-honest estimate

- Closed (nh, 2026-07-10) **MO soft-sync duration on tier change:**
  - onResearchTierChange updates duration only when still at previous recommended
  - preserves operator custom duration overrides

- Closed (ni, 2026-07-10) **Twin chase note_ids provenance:**
  - goal_hint includes note_ids (truncated preview when >4)
  - twin-chase-metrics data-note-ids for recursive audit
  - suite-proposal AC recheck 4_passed

- Closed (nj, 2026-07-10) **SESSION-ARC ng–ni MO duration + chase provenance:**
  - SESSION-ARC-ng-ni-moil-duration-chase-provenance.md fleet handoff

- Closed (nk, 2026-07-10) **Collective select-all/invert/clear:**
  - multi-select helpers for cohesive unit assembly
  - parity TwinNotes multi-select path

- Closed (nl, 2026-07-10) **Collective dual-gate checklist link:**
  - L6 live multi-agent collective prep surface
  - dual-gate prep now spans attach/MO/marketplace/twins/context/progress/collective

- Closed (nm, 2026-07-10) **SESSION-ARC nk–nl collective multi-select:**
  - SESSION-ARC-nk-nl-collective-multiselect.md fleet handoff
  - dual-gate prep surfaces complete on major engagement panels

- Closed (nn, 2026-07-10) **SpawnMerge dual-gate checklist link:**
  - Completes dual-gate prep on spawn merge path

- Closed (no, 2026-07-10) **Dual-gate UI prep surface index:**
  - DUAL-GATE checklist lists all 8 engagement deep-link testids

- Closed (np, 2026-07-10) **SessionFlywheel dual-gate checklist link:**
  - Completes dual-gate prep on land→twins→Antiek-bench flywheel path
  - Checklist UI prep surfaces now 9 panels

- Closed (nq, 2026-07-10) **SESSION-ARC nl–np dual-gate surfaces:**
  - 9 engagement dual-gate prep deep-links complete offline

- Closed (nr, 2026-07-10) **MO soft-apply duration on Settings depth prefill:**
  - factory default 60m → recommended midpoint for mapped depth-tier
  - preserves custom duration overrides

- Closed (ns, 2026-07-10) **SESSION-ARC ng–nr MO duration path:**
  - SESSION-ARC-ng-nr-moil-duration-path.md fleet handoff
  - MO time-of-work path offline product-complete

- Closed (nt, 2026-07-10) **Antiek-bench dual-gate + NotDiamond L7 banner:**
  - Settings suite proposal panel dual-gate checklist link
  - NotDiamond advisory-only authority chrome (never dispatch)

- Closed (nu, 2026-07-10) **Launch budget dual-gate checklist:**
  - ResearchLaunchBudgetPanel shared chokepoint dual-gate deep-link
  - suite-proposal AC recheck 4_passed

- Closed (nv, 2026-07-10) **SESSION-ARC nt–nu bench + launch budget dual-gate:**
  - Settings suite + shared launch budget dual-gate surfaces documented

- Closed (nw, 2026-07-10) **Antiek-bench usage on session open / twin chase:**
  - sessions/open records usage_event (source twin_chase | floating_deep_research)
  - research_tier → task_class feeds recursive suite rewrite
  - TwinNotes chase metrics data-usage-source / task-class audit

- Closed (nx, 2026-07-10) **Settings known feed sources + by_source chase/DR:**
  - KNOWN_USAGE_FEED_SOURCES incl twin_chase / floating_deep_research
  - usage-summary API returns by_source + known_sources (by_source was missing)
  - Settings legend antiek-bench-usage-known-sources

- Closed (ny, 2026-07-10) **SESSION-ARC nw–nx Antiek-bench chase feed:**
  - SESSION-ARC-nw-nx-bench-chase-feed.md fleet handoff

- Closed (nz, 2026-07-10) **Suite proposal feed sources chase/DR chrome:**
  - data-has-twin-chase / data-has-floating-dr on suite feed sources
  - empty-state lists floating DR + twin chase as feeders

- Closed (oa, 2026-07-10) **DecisionTreeDriverBadge dual-gate checklist:**
  - Shared driver+budget chokepoint dual-gate deep-link

- Closed (ob, 2026-07-10) **Recent DR spawns for collective after window close:**
  - sessionStorage ring (max 24) pushed on launchFloatingDeepResearch
  - collectDeepResearchSpawnIds merges recent + open windows
  - twin chase → collective cohesive unit without losing closed spawn ids

- Closed (oc, 2026-07-10) **Collective clear recent closed-window spawns:**
  - collective-clear-recent-spawns + data-recent-count
  - onRecentSpawnsCleared parent re-collects available list

- Closed (od, 2026-07-10) **SESSION-ARC ob–oc collective recent spawns:**
  - SESSION-ARC-ob-oc-collective-recent-spawns.md fleet handoff

- Closed (oe, 2026-07-10) **Twin chase collective recent_ring chrome:**
  - chase status + metrics data-collective-recent
  - honesty: spawn survives window close for multi-select merge

- Closed (of, 2026-07-10) **Collective recent_ring origin badges:**
  - data-origin-recent + recent badge on multi-select rows
  - data-recent-in-available on list/controls

- Closed (og, 2026-07-10) **Collective select recent only:**
  - collective-select-recent one-click for recent_ring ∩ available
  - twin-chase batch merge into cohesive unit without checkbox grind

- Closed (oh, 2026-07-10) **SESSION-ARC of–og collective recent select:**
  - SESSION-ARC-of-og-collective-recent-select.md fleet handoff

- Closed (oi, 2026-07-10) **Collective merge Antiek-bench usage feed:**
  - record_collective_merge_usage on POST /collective and /merge
  - source=collective_merge in known feed sources for suite rewrite

- Closed (oj, 2026-07-10) **Collective usage_event UI chrome:**
  - collective-unit-metrics data-usage-source/task-class
  - collective-doc-merge-usage bench feed status

- Closed (ok, 2026-07-10) **SESSION-ARC oi–oj collective bench feed:**
  - SESSION-ARC-oi-oj-collective-bench-feed.md fleet handoff
  - twin chase → collective merge → collective_merge usage → suite rewrite

- Closed (ol, 2026-07-10) **Auto-select newest recent_ring spawn:**
  - preferredSpawnId still wins
  - no re-auto after clear of same newest
  - chase → collective one less click

- Closed (om, 2026-07-10) **WriteHome recent_ring collective wire:**
  - listRecentDeepResearchSpawnIds + recentTick + data-recent-count
  - onRecentSpawnsCleared same-tab refresh
  - parity DR host / hosted HTML / ResearchThis (reading≡write)

- Closed (on, 2026-07-10) **Midnight Oil deposit collective + recent_ring:**
  - CollectiveResearchPanel on deposit (parent=document_id)
  - deposit spawn_ids push recent_ring for closed-window multi-select
  - offline swarm → cohesive unit without leaving MO

- Closed (oo, 2026-07-10) **Midnight Oil deposit TwinNotesPanel:**
  - autoLoad / autoSeedIfEmpty / autoPromoteAfterLoad on deposit asset
  - remount after promote + collective onDocMerged
  - recursive note-taker promote/chase without leaving MO

- Closed (op, 2026-07-10) **Midnight Oil deposit ResearchContextPanel:**
  - autoLoad research context pack on deposit asset
  - remount with twins on promote / collective merge
  - full MO engagement spine: twins · context · progress · collective

- Closed (oq, 2026-07-10) **MO offline run → recent_ring without auto-deposit:**
  - rememberSpawnIds chokepoint on run + deposit
  - auto_deposit off still feeds collective multi-select elsewhere

- Closed (or, 2026-07-10) **SESSION-ARC om–oq Write + MO engagement:**
  - SESSION-ARC-om-oq-write-moil-engagement.md fleet handoff
  - DEFERRED-GAPS closed-since-om block

- Closed (os, 2026-07-10) **Settings Antiek-bench MO + collective_merge chrome:**
  - data-has-midnight-oil / data-has-collective-merge on known sources + suite feed
  - empty-state copy includes collective merge

- Closed (ot, 2026-07-10) **MO run metrics recent_ring honesty:**
  - data-recent-ring-count / data-recent-ring-has-run-spawns
  - moil-run-recent-ring-status copy for collective multi-select path

- Closed (ou, 2026-07-10) **ResearchThis recent_ring collective proof:**
  - data-recent-count on research-this-collective-mount
  - vitest wires listRecent → collect → CollectiveResearchPanel (parity om)

- Closed (ov, 2026-07-10) **HostedHtml recent_ring collective proof:**
  - data-recent-count on hosted-html-collective-mount
  - vitest parity Write/ResearchThis (marketplace books ≡ reading)

- Closed (ow, 2026-07-10) **SESSION-ARC om–ov engagement parity:**
  - SESSION-ARC-om-ov-engagement-parity.md fleet handoff
  - full host matrix Write/ResearchThis/Hosted/MO/Settings

- Closed (ox, 2026-07-10) **DeepResearchSessionHost recent_ring proof:**
  - data-recent-count on deep-research-collective-mount
  - vitest pushRecent closed spawn appears in multi-select (parity om/ou/ov)

- Closed (oy, 2026-07-10) **Midnight Oil create pub refs grounding:**
  - arxiv/substack/URL hydrate offline-honest on create
  - Ground publication: handles appended as swarm goals
  - knowledge-dense autonomous research parity Write/ResearchThis

- Closed (oz, 2026-07-10) **SESSION-ARC om–oy engagement + MO pubs:**
  - SESSION-ARC-om-oy-engagement-moil-pubs.md fleet handoff

- Closed (pa, 2026-07-10) **MO budget projection includes pub refs:**
  - promptText concatenates goals + publication refs
  - data-prompt-includes-pub-refs / data-pub-refs-chars honesty

- Closed (pb, 2026-07-10) **MO pub refs dual-gate L1–L2 hydrate link:**
  - moil-pub-refs-dual-gate-link + offline identity default honesty
  - prep only; never enables live arxiv/substack injectors

- Closed (pc, 2026-07-10) **MO job receipt grounded publication goals:**
  - data-grounded-pub-goal-count on ceiling metrics
  - moil-grounded-pub-goals list for swarm grounding audit

- Closed (pd, 2026-07-10) **FUTURE-AGENT-SPEC remaining vision:**
  - FUTURE-AGENT-SPEC-remaining-vision-2026-07-10.md
  - V1–V6 offline product residuals + L1–L7 dual-gate honesty

- Closed (pe, 2026-07-10) **Antiek-bench suite rewrite rationale chrome (V3):**
  - data-has-rationale + feed_source_count on suite metrics
  - rewrite rationale propose≠promote honesty banner

- Closed (pf, 2026-07-10) **SESSION-ARC om–pe engagement + MO + bench:**
  - SESSION-ARC-om-pe-engagement-moil-bench.md fleet handoff

- Closed (pg, 2026-07-10) **DecisionTreeDriverBadge prompt projection (V4):**
  - optional promptText → estimatePromptCost vs remaining budget
  - decision-tree-prompt-projection + remaining-after chrome
  - Midnight Oil wires goals+pub refs into badge projection

- Closed (ph, 2026-07-10) **WriteHome driver badge promptText projection:**
  - DR selection + pub refs → DecisionTreeDriverBadge promptText
  - writing≡research cost foresight before float/full fire

- Closed (pi, 2026-07-10) **ResearchThis driver badge promptText projection:**
  - selection + pub refs → DecisionTreeDriverBadge promptText
  - reading≡write≡MO cost foresight before float/full fire

- Closed (pj, 2026-07-10) **HostedHtml driver badge promptText projection:**
  - selection + pub refs → DecisionTreeDriverBadge promptText
  - marketplace books ≡ reading≡write≡MO cost foresight

- Closed (pk, 2026-07-10) **SESSION-ARC pg–pj driver projection:**
  - SESSION-ARC-pg-pj-driver-projection.md fleet handoff
  - MO/Write/ResearchThis/Hosted cost foresight matrix complete

- Closed (pl, 2026-07-10) **DR host driver badge promptText:**
  - selection + goal → DecisionTreeDriverBadge
  - completes cost foresight matrix across all engagement hosts

- Closed (pm, 2026-07-10) **SESSION-ARC om–pl full session wave:**
  - SESSION-ARC-om-pl-session-wave.md fleet handoff
  - engagement · MO pubs · bench · driver foresight

- Closed (pn, 2026-07-10) **Twin multi-select HTML draft window (V1 partial):**
  - buildTwinDraftHtml pure helper (escape · questions first)
  - twin-draft-selected-html opens hosted HTML floating draft

- Closed (po, 2026-07-10) **twin-draft-metrics after HTML draft open:**
  - data-note-count / data-window-id / data-source=twin_draft_selected

- Closed (pp, 2026-07-10) **Twin draft → Write handoff (twin_seed):**
  - sessionStorage twinWriteSeed store/load + `/write?twin_seed=`
  - TwinNotes Draft HTML → Open Write link
  - WriteHome brainstorm seed + HTML preview + freeform provenance

- Closed (pq, 2026-07-10) **twin_seed create seeds twin notes on new piece:**
  - createWithConnection → seedTwinNotes force_offline from twin seed plain_text
  - recursive note-taker continues into writing asset

- Closed (pr, 2026-07-10) **SESSION-ARC pn–pq twin write path:**
  - SESSION-ARC-pn-pq-twin-write-path.md fleet handoff

- Closed (ps, 2026-07-10) **Twin HTML draft full working-region window:**
  - openTwinDraft(floating|full) shared chokepoint
  - twin-draft-selected-html-full + data-window-mode

- Closed (pt, 2026-07-10) **twin-draft-metrics note_ids provenance:**
  - data-note-ids + note_ids= chrome (truncated when >6)

- Closed (pu, 2026-07-10) **Write twin_seed banner note_ids provenance:**
  - data-note-ids + note_ids= on write-twin-seed-handoff

- Closed (pv, 2026-07-10) **SESSION-ARC pn–pu twin write complete:**
  - SESSION-ARC-pn-pu-twin-write-complete.md fleet handoff

- Closed (pw, 2026-07-10) **mergeTwinChaseNotes pure helper (V1 foundation):**
  - multi-list dedupe by note_id · questions first
  - composes with buildTwinDraftHtml for cross-asset drafts

- Closed (px, 2026-07-10) **cross-asset twin merge UI (FUTURE-AGENT V1):**
  - second asset_id input + Load merge asset (fetchTwinNotes; must differ)
  - secondary multi-select (auto-select all on load)
  - Merge draft HTML/full → mergeTwinChaseNotes → openTwinDraft + Write seed
  - metrics data-source=twin_cross_asset_merge · data-merge-assets=A|B
  - TwinNotesPanel vitest 28 passed

- Closed (py, 2026-07-10) **collective cohesive unit membership (FUTURE-AGENT V2):**
  - sessionStorage map collective_id → spawn_ids (max 24)
  - store on merge / written analysis (document_id) / continue-as-unit
  - Restore last unit → multi-select intersection with available
  - CollectiveResearchPanel + pure helper vitest 22 passed

- Closed (pz, 2026-07-10) **MO Write dual handoff twin seed (FUTURE-AGENT V6):**
  - buildWriteHtmlDraftHref(html_draft + optional twin_seed)
  - MO deposit stores twinWriteSeed source=midnight_oil_deposit
  - Open Write data-has-twin-seed; vitest 24 passed

- Closed (qa, 2026-07-10) **Antiek-bench primary rewrite feed (FUTURE-AGENT V3):**
  - primaryFeedSourceFromBySource (max by_source count)
  - Settings primary-feed chrome + ranked feed sources + metrics attrs
  - vitest 28 passed

- Closed (qb, 2026-07-10) **twin N>2 multi-asset merge (FUTURE-AGENT V1 polish):**
  - mergeBuckets accumulate asset_ids; per-bucket select/remove
  - merge draft label A+B+C · data-merge-assets=A|B|C
  - TwinNotesPanel vitest 29 passed

- Closed (qc, 2026-07-10) **marketplace Write dual handoff (FUTURE-AGENT V5):**
  - buildMarketplaceWriteHref + source=marketplace_host
  - host + library Open Write html_draft+twin_seed
  - vitest 20 passed

- Closed (qd, 2026-07-10) **spawn-merge Write dual handoff:** buildMergedDocWriteHref + twin_seed

- Closed (qe, 2026-07-10) **collective Write dual handoff** twin_seed

- Closed (qf, 2026-07-10) **Write dual-handoff matrix SESSION-ARC** + buildMergedDocWriteHref test

- Closed (qg, 2026-07-10) **collective DecisionTreeDriverBadge promptText** for budget foresight

- Closed (qh, 2026-07-10) **spawn-merge DecisionTreeDriverBadge promptText**

- Closed (qi, 2026-07-10) **TwinNotes DecisionTreeDriverBadge promptText** from chase selection

- Closed (qj, 2026-07-10) **marketplace DecisionTreeDriverBadge promptText** from hosted book

- Closed (qk, 2026-07-10) **SESSION-ARC px–qj** FUTURE-AGENT + dual handoff + driver foresight handoff

- Closed (ql, 2026-07-10) **auto-restore last cohesive unit multi-select on mount** (V2 complete)

- Closed (qm, 2026-07-10) **ResearchProgress DecisionTreeDriverBadge promptText** (spawn/tier/stage)

- Closed (qn, 2026-07-10) **SessionFlywheel DecisionTreeDriverBadge promptText**

- Closed (qo, 2026-07-10) **PublicationAttach DecisionTreeDriverBadge promptText** from pub refs

- Closed (qp, 2026-07-10) **workstation + reading DR entry promptText matrix:**
  - StartResearch / ChatInputArea: question + pub refs
  - TalkToBook draft · MetaReading prompt · BlockDetail selection/node text
  - StartResearch vitest asserts prompt-len + pub-refs stamp

- Closed (qq, 2026-07-10) **ResearchContextPanel DecisionTreeDriverBadge** + prompt_block foresight

- Closed (qr, 2026-07-10) **badge ≡ budget** via composeDriverPromptText (ResearchThis/StartResearch/ChatInput + pub refs)

- Closed (qs, 2026-07-10) **badge ≡ budget** on Write/MO/Hosted via composeDriverPromptText

- Closed (qt, 2026-07-10) **SESSION-ARC qp–qs driver foresight matrix** (badge ≡ budget)

- Closed (qu, 2026-07-10) **HostedHtml Write dual handoff** html_draft+twin_seed (source=hosted_html_document)

## Residual qv · 2026-07-10 — Deep research → Write twin seed
Live deep_research_session host can hand selection+goal into Write as twin_seed
without inventing a server document_id (offline-honest unfinished sessions).
Competitive delta: Perplexity/Elicit/Consensus dump to chat or export PDF;
Antiek keeps the recursive note-taker path HTML-first and session-seeded so
highlight → float DR → Write brainstorm stays one continuous substrate.

## Residual qw · 2026-07-10 — Progress terminal → Write
When multi-minute plan→cite reaches is_terminal, ResearchProgressPanel offers
Open Write with twin_seed of stages/HTML (source=research_progress_complete).
Competitive delta: ChatGPT Deep Research / Perplexity dump chat export; Antiek
closes float-session → terminal → writing substrate without inventing doc ids
and without PDF as the intermediate format.

## Residual qx · 2026-07-10 — Write freeform source provenance
Twin seed freeform is twin_seed:{source}:{n}:{asset} so deep_research_session
and research_progress_complete are visible on writing assets. Competitive
delta: most tools lose origin of "export to doc"; Antiek keeps HTML-first
source tags on the recursive note-taker → Write path for later bench rewrite.

## Residual qy · 2026-07-10 — Write seeds feed Antiek-bench by_source
deep_research_session and research_progress_complete are known usage feed
sources; Write create → twins/seed records them when usage_source is set.
Competitive delta: weekly recursive suite rewrite can learn from highlight→
float DR→Write paths, not only investigation_start / midnight_oil / chase.

## Residual ra · 2026-07-10 — Dual-handoff Write seeds in bench feed
midnight_oil_deposit, marketplace_host, spawn_merge, collective_doc_merge,
hosted_html_document join TWIN_WRITE_SEED_USAGE_SOURCES so Write create from
any dual-handoff surface feeds weekly recursive suite rewrite by_source.

## Residual rb · 2026-07-10 — Evidence pack → Write
Evidence packs (insights + questions + arxiv/substack refs) hand off into Write
as twin_seed source=evidence_pack. Competitive delta: citation-trust packs stay
HTML-first and feed the recursive note-taker writing path + Antiek-bench.

## Residual rc · 2026-07-10 — Publication hydrate → Write
Attached arxiv/substack/URL hydrates hand off into Write as twin_seed
source=publication_hydrate. Competitive delta: knowledge-dense pubs never
dead-end in a sidebar — they seed the recursive note-taker writing path.

## Residual re · 2026-07-10 — Session flywheel complete → Write
After complete_session flywheel, operators Open Write with output + prompt
block as twin_seed (source=session_flywheel_complete). Competitive delta:
float research session never dead-ends — it becomes writing substrate.

## Residual rf · 2026-07-10 — Intelligent search → Write
Context search hits hand off into Write as twin_seed source=context_search.
Competitive delta: intelligent search over the recursive note-taker substrate
becomes writing fuel, not a dead-end results list.

## Residual rh · 2026-07-10 — Hydrate-ref → Write
ResearchContextPanel single hydrate result opens Write twin_seed (reuses
publication_hydrate source). Competitive delta: every arxiv/substack attach
path — multi-pub panel or one-off hydrate — seeds writing.

## Residual ri · 2026-07-10 — Context pack prompt_block → Write
The research context pack that drives prompts opens Write as twin_seed
source=research_context_pack. Competitive delta: the same substrate that
grounds deep-research turns seeds long-form writing without re-export.

## Residual rl · 2026-07-10 — NotDiamond driver delta honesty
Settings shows installed decision-tree driver vs weekly NotDiamond advisory
suggestion (match|differs|no_installed|no_suggestion). Competitive delta:
operators see router-class suggestions without ever granting auto-dispatch
authority — Antiek decision-tree remains the only install path.

## Residual rm · 2026-07-10 — Driver badge → ND advisory Settings
Every DecisionTreeDriverBadge mounts "ND advisory" → /settings#notdiamond-advisory
so research hosts reach weekly suggestion-vs-installed delta without granting
router authority. Competitive delta: model choice stays operator-owned.

## Residual rp · 2026-07-10 — Progress draft → Write mid-flight
Non-terminal multi-minute plan→cite progress offers Open Write (progress draft)
with source=research_progress_draft. Competitive delta: operators capture
synthesis substrate during long-horizon jobs without waiting for terminal.

## Residual rr · 2026-07-10 — Twin promote → Write
After promote→context, TwinNotesPanel offers Open Write with promoted units
as twin_seed (source=twin_promote_context). Competitive delta: recursive
note-taker promote path feeds writing without re-export or PDF.

## Residual rt · 2026-07-10 — Write-seed primary feed honesty
Settings suite primary rewrite feed stamps data-write-seed-feed and labels
"Write seed feed (recursive note-taker → Write)" when the week's top by_source
is a twin_seed path (WRITE_SEED_FEED_SOURCES). Competitive delta: operators
see whether weekly Antiek-bench rewrite was driven by research→Write substrate
vs chase/investigation paths — without inventing promote authority.

## Residual ru · 2026-07-10 — Known-sources Write-seed count
Settings known-sources legend stamps data-write-seed-known-count and labels
how many weekly feed sources are recursive note-taker → Write twin_seed paths.
Competitive delta: Antiek-bench weekly rewrite UI shows substrate composition
(not only raw by_source names) so operators know write-path coverage without
auto-promoting suite changes.

## Residual rv · 2026-07-10 — Ranked feed Write-seed row stamps
Suite proposal ranked by_source list renders per-source rows with
data-write-seed-feed and "[write seed]" when the source is a recursive
note-taker → Write twin_seed path. Competitive delta: weekly rewrite
operators see substrate composition at row level, not only primary feed.

## Residual rw · 2026-07-10 — Usage by_source Write-seed stamps
Weekly usage by_source list stamps data-write-seed-feed / [write seed] per
source (parity suite ranked feeds). Competitive delta: both Antiek-bench
Settings panels (usage + suite proposal) show recursive note-taker → Write
substrate composition for weekly rewrite honesty.

## Residual rx · 2026-07-10 — Usage HTML Write-seed stamps
project_usage_summary_html marks TWIN_WRITE_SEED_USAGE_SOURCES with
[write seed] and a Write seed feeds count paragraph. Competitive delta:
HTML-first weekly Antiek-bench view (not only React Settings) shows whether
usage substrate is recursive note-taker → Write vs chase/investigation.

## Residual ry · 2026-07-10 — Write-seed aggregates SSOT
weekly_usage_summary exposes write_seed_by_source / counts so Settings and
HTML clients share one substrate source of truth (TWIN_WRITE_SEED_USAGE_SOURCES).
Competitive delta: recursive note-taker → Write feed composition is machine-
readable for weekly rewrite without client-side source lists drifting.

## Residual rz · 2026-07-10 — Usage Write-seed weekly metrics
Settings usage panel surfaces write_seed_event_count / source_count /
known_catalog from substrate SSOT. Competitive delta: operators see weekly
recursive note-taker → Write volume at a glance (propose≠promote).

## Residual sa · 2026-07-10 — Decision-tree budget usage bar
Model driver install panel shows daily cap / spent / remaining + usage
progressbar (soft gate, never invents $0) with deep-link to prompt cost
projection. Competitive delta: operators choose the research driver with
budget posture visible at the decision-tree — not only a separate Budget card.

## Residual sb · 2026-07-10 — Decision-tree mini prompt projection
At model driver install, operators project a sample prompt cost against
remaining budget (pricing known / would_exceed / high≈) without leaving the
decision-tree panel. Soft gate never invents $0. Competitive delta: budget
foresight sits with model choice — research drivers are not selected blind.

## Residual sc · 2026-07-10 — Launch budget → decision-tree deep-link
ResearchLaunchBudgetPanel Settings link targets /settings#decision-tree-panel
so research hosts jump to model driver + budget bar + sample projection.
Competitive delta: budget foresight at launch and driver install form one loop.

## Residual sd · 2026-07-10 — Driver/budget deep-links to decision-tree
Engagement surfaces labeled driver & budget (badge, collective, progress,
spawn merge, flywheel, Write, MO, marketplace) deep-link
/settings#decision-tree-panel. Competitive delta: model choice + budget
foresight is one click from any research host.

## Residual se · 2026-07-10 — Hydrate + twin-seed Settings anchors
Settings anchors twin-seed-live-status and hydrate-live-status; TwinNotes /
PublicationAttach / ResearchContext deep-link there. Competitive delta:
offline-honest readiness panels are one click from recursive note-taker and
knowledge-dense pub attach surfaces.

## Residual sf · 2026-07-10 — Evidence pack float HTML window
ResearchContextPanel opens the citation-trust evidence pack as a floating
hosted_html_document (HTML-first, never PDF) alongside Open Write twin_seed.
Competitive delta: Perplexity/OpenAI show citations in chat; Antiek joins
the evidence pack into the reading/research window flywheel as a first-class
HTML asset operators can float while wrestling the primary paper.

## Residual sg · 2026-07-10 — Evidence pack full window
Citation-trust evidence packs open as full working-region HTML windows
(float|full parity with spawn merge / collective). Competitive delta:
operators pin evidence full-screen while the source paper stays in another
region — HTML-first citation workstation, never PDF.

## Residual sh · 2026-07-10 — Evidence pack host twin-seed honesty
Floated evidence packs (source=evidence_pack) stamp host data-evidence-pack
and seed TwinNotes with "Evidence pack (citation trust)" title so recursive
note-taker substrate knows citation-trust provenance. Competitive delta:
evidence windows are not orphaned HTML — they join the twin note-taker path.

## Residual si · 2026-07-10 — Evidence pack Open Write seed source
Hosted evidence windows Open Write with twin_seed source=evidence_pack so
Antiek-bench weekly rewrite learns from citation-trust → Write paths.
Competitive delta: evidence is not a dead-end float — it seeds writing and
bench substrate with honest provenance.

## Residual sj · 2026-07-10 — Context search float|full HTML
Intelligent context search hits open as float|full hosted HTML windows
(source=context_search) with twin-seed Open Write provenance. Competitive
delta: search over the recursive note-taker substrate becomes reading fuel
in the window flywheel — not only a Write seed or dead-end hit list.

## Residual sk · 2026-07-10 — Hydrate-ref float|full HTML
Hydrated arxiv/substack identity HTML opens as float|full hosted documents
(source=publication_hydrate) with note-taker Write provenance. Competitive
delta: knowledge-dense pubs never dead-end as attach rows — they join the
HTML reading flywheel offline-honest (body when injector live).

## Residual sl · 2026-07-10 — Research context pack float|full
The recursive context pack (prompt_block + twin/ref substrate) opens as
float|full HTML (source=research_context_pack). Competitive delta: the same
substrate that drives deep-research turns is first-class reading material —
operators pin context full-screen while wrestling the source document.

## Residual sm · 2026-07-10 — Research progress float|full HTML
Multi-minute plan→cite progress HTML opens as float|full hosted documents
(source=research_progress_complete|draft). Competitive delta: long-horizon
Deep Research jobs leave readable HTML artifacts in the window flywheel —
not only chat timeline or Write seed.

## Residual sn · 2026-07-10 — Session flywheel complete float|full
Completed floating deep-research sessions open as float|full HTML
(source=session_flywheel_complete) with output + context prompt_block.
Competitive delta: autonomous/interactive session close lands a readable
HTML artifact in the window flywheel — not only usage events + Write seed.

## Residual so · 2026-07-10 — Host progress/flywheel twin-seed honesty
HostedHtmlDocumentHost stamps research_progress_* and session_flywheel_complete
sources with note-taker seed titles + Write seed provenance. Competitive
delta: every reading-flywheel HTML window from research surfaces joins the
recursive note-taker path with honest source labels.

## Residual sp · 2026-07-10 — Settings hash deep-link scroll
Settings honors SPA hash anchors (decision-tree, twin-seed, hydrate,
NotDiamond, prompt projection) on mount and hashchange. Competitive delta:
driver/budget/readiness deep-links from research hosts actually land on the
panel — not just change the URL bar.

## Residual sq · 2026-07-10 — Decision-tree → weekly leaderboard
Decision-tree budget panel deep-links to #antiek-bench-leaderboard so operators
can compare weekly Antiek-bench rankings when choosing a model driver.
Competitive delta: model choice sits next to recursive bench evidence without
granting auto-route authority (propose≠promote · ND advisory only).

## Residual sr · 2026-07-10 — Write-seed metrics → suite proposal
Weekly Write-seed metrics deep-link to the suite rewrite proposal panel
(propose≠promote). Competitive delta: recursive note-taker → Write volume
and suite rewrite review sit one click apart without auto-promoting.

## Residual ss · 2026-07-10 — Future-agent brief refresh
FUTURE-AGENT-SPEC re-anchored to tip after write-seed SSOT (rt–rz), driver
foresight (sa–sr), and HTML reading flywheel (sf–so). Competitive delta:
next swarm starts from accurate inventory — no rebuild thrash on closed arcs.

## Residual st · 2026-07-10 — Competitive dogfood v2
Antiek-bench offline dogfood suite gains write-seed, float-evidence, and
budget-foresight task postures (v2). Competitive delta: weekly recursive
bench rewrite can learn from the same product surfaces that differentiate
Antiek from chat-export deep research — without auto-promoting suites.

## Residual su · 2026-07-10 — Dogfood Settings v2 posture honesty
Settings dogfood summary stamps suite version, item count, and write-seed /
float-evidence / budget-foresight postures for v2 fixtures. Competitive
delta: operators see which recursive-spine postures weekly dogfood covers
without auto-promoting suites.

## Residual sv · 2026-07-10 — Decision-tree → dogfood deep-link
Decision-tree budget panel deep-links to competitive dogfood fixtures so
operators inspect recursive-spine postures (write-seed / float / budget)
when choosing a model driver. Competitive delta: model choice sits next to
the offline dogfood that defines Antiek-bench task classes.

## Residual sw · 2026-07-10 — Dual-gate prep strip on Settings
Decision-tree panel mounts offline-honest L1–L4 dual-gate prep links
(hydrate / twin seed / MO checklist / ND advisory). Competitive delta:
operators see live-injector readiness without silent enable — dual-gate
remains operator-owned.

## Residual sy · 2026-07-10 — Write-seed source list parity gate
Pytest asserts apps/reading WRITE_SEED_FEED_SOURCES equals substrate
TWIN_WRITE_SEED_USAGE_SOURCES. Competitive delta: recursive note-taker →
Write feed honesty cannot silently diverge between Settings UI and weekly
rewrite aggregation.

## Residual sz · 2026-07-10 — Settings MO live-step readiness (L4)
Settings mounts Midnight Oil live-step readiness panel (parity hydrate L1–L2
and twin seed L3). Offline-honest by default; dual-gate L4 link targets the
panel. Competitive delta: autonomous research mode readiness is visible in
the same Settings surface as model driver choice — without silent live enable.

## Residual ta · 2026-07-10 — Marketplace filtered free-PD honesty
Catalog metrics stamp visible_free under active free-PD/subject/source/text
filters while preserving full-catalog free_count from server honesty.
Competitive delta: free research spine browsing never confuses filtered
list size with whole-catalog free inventory — HTML host only, no live rails.

## Residual tb · 2026-07-10 — Library free-PD honesty under filter
Account library metrics stamp free_pd counts and filtered free honesty when
text filter is active. Competitive delta: hosted HTML library browsing never
confuses filtered list size with whole-library free inventory (HTML host only).

## Residual tc · 2026-07-10 — Host-land free/PD honesty
Host land stamps data-is-public-domain / data-is-free-host and a free/PD
honesty strip (manual_receipt_only rails). Competitive delta: free research
spine host path is auditably distinct from purchase+host without inventing
live payment rails.

## Residual td · 2026-07-10 — STEM PD electricity spine
Demo catalog gains Faraday Experimental Researches and Maxwell Treatise on
Electricity and Magnetism as free HTML public-domain hosts (physics +
technology + electricity subjects). Competitive delta: free research spine
for tech researchers expands beyond Euclid/Newton/Bacon without inventing
live bookstore connectors.

## Residual te · 2026-07-10 — Host Faraday/Maxwell HTML free PD
host_book_into_account projects Faraday and Maxwell free PD bodies as HTML
(not PDF). Competitive delta: knowledge-dense electricity spine is hostable
into the Antiek account library as HTML reading assets for tech researchers.

## Residual tf · 2026-07-10 — Dogfood v3 Faraday book_qa
Competitive dogfood gains book_qa Faraday induction + free PD HTML hosting
posture (v3). Competitive delta: weekly Antiek-bench rewrite can learn from
marketplace free STEM electricity spine alongside write-seed/float/budget.

## Residual tg · 2026-07-10 — Purchase-host free_host=false honesty
Purchase + host of paid catalog titles stamps free_host=false / not
public_domain with manual_receipt_only rails. Competitive delta: free research
spine honesty has a hard negative case — paid hosts never look free.

## Residual ti · 2026-07-10 — Settings dogfood v3 Faraday posture
Settings dogfood summary stamps Faraday book_qa posture for v3 fixtures.
Competitive delta: operators see free STEM electricity spine coverage in
weekly dogfood without auto-promoting suites.

## Residual tj · 2026-07-10 — Electricity domain chip → Faraday/Maxwell
Subject filter electricity (and technology) surfaces free PD Faraday and
Maxwell hosts. Competitive delta: tech researchers filter knowledge-dense
electricity spine without leaving free HTML catalog.

## Residual tk · 2026-07-10 — UI electricity chip → Faraday/Maxwell
MarketplaceHost electricity subject chip filters free PD Faraday and Maxwell
with filtered free honesty. Competitive delta: tech researchers click
electricity domain and host knowledge-dense free HTML books immediately.

## Residual tm · 2026-07-10 — Host Faraday free PD with electricity subjects
Hosting Faraday free PD stamps electricity subjects + free_host honesty on
host land. Competitive delta: tech researchers go catalog electricity chip →
host → research substrate with domain-aware twin seed continuity.

## Residual tn · 2026-07-10 — Host Maxwell free PD with electricity subjects
Hosting Maxwell free PD stamps free_host honesty + electricity/mathematics
subjects on host land (parity Faraday tm). Competitive delta: full
electricity STEM free host path is product-proven for tech researchers.

## Residual to · 2026-07-10 — Faraday DR goal_hint electricity domains
Hosting Faraday free PD then launching floating deep research puts
domains=electricity (and related STEM tags) into goal_hint. Competitive
delta: free marketplace STEM hosts feed domain-aware deep research without
re-entering domain context by hand (reading ≡ research).

## Residual tp · 2026-07-10 — Maxwell DR full goal_hint electricity domains
Hosting Maxwell free PD then launching full deep research puts electricity
and mathematics domains into goal_hint (parity Faraday float to). Competitive
delta: full working-region research inherits free STEM catalog domain tags.

## Residual tq · 2026-07-10 — Intelligent search host query+hits honesty
Context search float|full windows carry search_query and search_hit_count into
HostedHtmlDocumentHost honesty chrome. Competitive delta: recursive note-taker
intelligent search results stay query-auditable in the reading flywheel — not
a dead-end hit list (HTML · not PDF).

## Residual tr · 2026-07-10 — Collective unit prompt float|full HTML
Multi-select deep-research spawns merged into a cohesive unit can open the
prompt_block as float|full HTML (source=collective_unit_prompt) without
inventing a server document_id. Competitive delta: collective research is
readable HTML workstation material before continue-as-unit or parent merge —
not only a chat prompt block.

## Residual ts · 2026-07-10 — Collective unit host honesty strip
HostedHtmlDocumentHost stamps collective_id + spawn_count honesty for
source=collective_unit_prompt floats. Competitive delta: multi-select
cohesive unit HTML windows stay membership-auditable in the reading flywheel.

## Residual tt · 2026-07-10 — collective_unit_prompt Write-seed catalog
Frontend WRITE_SEED_FEED_SOURCES and substrate TWIN_WRITE_SEED_USAGE_SOURCES
include collective_unit_prompt (known_catalog 15). Competitive delta: cohesive
unit prompt → Write twin_seed events rank in Antiek-bench weekly rewrite
alongside evidence/search/hydrate — recursive note-taker flywheel does not
drop multi-spawn unit prompts from usage honesty.

## Residual tu · 2026-07-10 — twin_seed allowlist for collective_unit_prompt
store/load TwinWriteSeedSource allowlists accept collective_unit_prompt so Open
Write from cohesive unit HTML does not collapse provenance to twin_draft_selected.
Host Open Write title names multi-spawn unit. Competitive delta: catalog (tt)
matches runtime seed path — usage honesty is load-bearing, not decorative.

## Residual tv · 2026-07-10 — dogfood v4 collective unit write-seed
suite-competitive-dogfood-v4 adds dogfood-wrestle-collective-unit-write-seed.
Settings honesty data-has-collective-unit-write-seed-posture. Competitive delta:
Antiek-bench recursive rewrite learns multi-spawn unit → Write twin_seed as a
first-class offline posture (propose≠promote · never auto-activate).

## Residual tw · 2026-07-10 — FUTURE-AGENT tip re-anchor tq–tv
FUTURE-AGENT-SPEC tip → d76ef2ed with closed arcs tq–tv so multi-agent swarms
do not rebuild write-seed SSOT / collective unit allowlist / dogfood v4.
Competitive delta: handoff craftsmanship — parallel agents share one tip truth.

## Residual tx · 2026-07-10 — Boole free PD computing/logic catalog
pd-boole-laws-of-thought joins the marketplace free PD spine (HTML · Gutenberg ·
subjects computing+logic+mathematics). Competitive delta: technology researchers
host foundational logic/calculus texts without payment rails — marketplace is
not only literature/electricity PD.

## Residual ty · 2026-07-10 — Boole computing chip + DR domain goal_hint
MarketplaceHost filters by computing subject, hosts free-PD honesty, and
launches deep research with domains=computing,logic in goal_hint. Competitive
delta: free computing PD feeds domain-aware research (parity Faraday electricity
to/tp) — reading ≡ research for logic/AI researchers.

## Residual tz · 2026-07-10 — dogfood v5 Boole book_qa
suite-competitive-dogfood-v5 adds dogfood-book-boole-laws-of-thought.
Settings data-has-boole-book-qa-posture. Competitive delta: Antiek-bench
recursive rewrite covers free computing PD reading (parity Faraday electricity
book_qa) without auto-promote.

## Residual ua · 2026-07-10 — FUTURE-AGENT tip re-anchor through tz
FUTURE-AGENT-SPEC tip → 89cb9a7d with closed arcs tt–tz (write-seed allowlist,
dogfood v4–v5, Boole free PD path). Competitive delta: multi-agent swarm
handoff stays tip-true so parallel engines do not rebuild closed product.

## Residual ub · 2026-07-10 — Heaviside free PD electricity STEM catalog
pd-heaviside-em joins Faraday/Maxwell free PD electricity spine (HTML ·
engineering subject). Competitive delta: marketplace free STEM path covers
Maxwell → Heaviside engineering reformulation without payment rails.

## Residual uc · 2026-07-10 — Heaviside host + DR electricity/engineering domains
MarketplaceHost free-PD host honesty and float DR goal_hint carry
domains=electricity,engineering for Heaviside. Competitive delta: free
engineering STEM PD feeds domain-aware research (parity Faraday to · Boole ty).

## Residual ud · 2026-07-10 — dogfood v6 Heaviside book_qa
suite-competitive-dogfood-v6 adds dogfood-book-heaviside-em. Settings
data-has-heaviside-book-qa-posture. Competitive delta: Antiek-bench recursive
rewrite covers free electricity engineering PD (Maxwell → Heaviside line)
without auto-promote.

## Residual ue · 2026-07-10 — collective Select open only multi-select
CollectiveResearchPanel Select open (N) selects currently open deep_research
windows without closed recent-ring-only ids. Competitive delta: multi-float
cohesive unit assembly distinguishes live floats from session history —
operator can merge what is on screen now.

## Residual uf · 2026-07-10 — Write + Midnight Oil openSpawnIds parity
Write piece and Midnight Oil deposit mount CollectiveResearchPanel with
openSpawnIds so Select open works across reading ≡ write ≡ MO. Competitive
delta: multi-float cohesive unit UX is surface-complete, not host-only.

## Residual ug · 2026-07-10 — FUTURE-AGENT tip re-anchor through uf
FUTURE-AGENT-SPEC tip → e31d9dce with closed arcs tt–uf. Competitive delta:
swarm handoff stays tip-true after Select open + free STEM + dogfood v6.

## Residual uh · 2026-07-10 — MO Settings L4 live-step deep-link
Midnight Oil mode links Settings #moil-live-step-status with data-l4-prep and
data-never-enables-live. Competitive delta: autonomous swarm prep is one click
from MO without silent live enable — offline-honest dual-gate craftsmanship.

## Residual ui · 2026-07-10 — SESSION-ARC tt–uh wave handoff
SESSION-ARC-tt-uh documents write-seed · free STEM · Select open · MO L4 for
swarm/compaction handoff. Competitive delta: long infinite waves stay auditable.

## Residual uj · 2026-07-10 — hosted book pub-refs L1/L2 hydrate prep honesty
HostedHtmlDocumentHost pub-refs panel stamps offline-default hydrate prep and
deep-links Settings hydrate readiness + dual-gate L1–L4 checklist. Competitive
delta: arxiv/substack grounding on free STEM books is dual-gate honest — never
silent live hydrate.

## Residual uk · 2026-07-10 — ResearchThis pub-refs L1/L2 hydrate prep honesty
ResearchThis pub-refs panel parity with hosted books (uj). Competitive delta:
main reading surface arxiv/substack grounding is dual-gate honest — reading ≡
hosted research workstation.

## Residual ul · 2026-07-10 — FUTURE-AGENT tip re-anchor through uk
FUTURE-AGENT-SPEC tip → 0242e858 with closed arcs tt–uk. Competitive delta:
swarm handoff stays tip-true after hydrate prep honesty + Select open + free STEM.

## Residual um · 2026-07-10 — MO ceiling remaining-after budget projection
Midnight Oil shows projected remaining daily budget if full recommended
ceiling is spent (remaining − ceiling). Competitive delta: approve foresight
beyond binary fit — operator sees how the swarm price ceiling affects the
daily cap before fire (never invent $0 when remaining unknown).

## Residual un · 2026-07-10 — MO custom ceiling remaining-after projection
Custom ceiling input projects remaining-after as the operator types (parity
recommended um). Competitive delta: custom approve path has the same budget
foresight as recommended — no silent over-budget custom approve without chrome.

## Residual uo · 2026-07-10 — SESSION-ARC + FUTURE-AGENT tip through un
SESSION-ARC-tt-un + FUTURE-AGENT tip 313070dc. Competitive delta: 21-commit
infinite wave handoff is compaction-safe for multi-agent swarm.

## Residual up · 2026-07-10 — ungrounded evidence citation-trust hydrate prep
Ungrounded evidence packs deep-link Settings hydrate readiness + dual-gate
L1–L2 checklist with data-offline-hydrate-default. Competitive delta: citation
trust failure is actionable prep — never silent live arxiv/substack enable.

## Residual uq · 2026-07-10 — publication attach ungrounded hydrate prep
PublicationAttachPanel ungrounded path deep-links Settings hydrate readiness
+ dual-gate checklist (parity evidence pack up). Competitive delta: attach
failure surfaces L1/L2 prep without inventing live bodies.

## Residual ur · 2026-07-10 — FUTURE-AGENT tip re-anchor through uq
FUTURE-AGENT-SPEC tip → 5ec87cc5 with closed arcs tt–uq (24 residual ships).
Competitive delta: multi-agent swarm handoff stays tip-true after citation-trust
hydrate prep wave.

## Residual us · 2026-07-10 — dogfood v7 citation-trust ungrounded
suite-competitive-dogfood-v7 adds dogfood-wrestle-citation-trust-ungrounded.
Settings posture honesty. Competitive delta: Antiek-bench recursive rewrite
learns ungrounded → dual-gate hydrate prep as a first-class wrestle task
(propose≠promote · never invent live bodies).

## Residual ut · 2026-07-10 — FUTURE-AGENT tip re-anchor through us
FUTURE-AGENT-SPEC tip → 9bc669dc with closed arcs tt–us (26 residual ships).
Competitive delta: swarm handoff tip-true after dogfood v7 citation-trust wave.

## Residual uu · 2026-07-10 — marketplace host DR pub-refs grounding
MarketplaceHost host-land deep research accepts optional arxiv/substack/URL
refs with offline-default hydrate prep deep-links (parity HostedHtml er/uj).
Competitive delta: free STEM catalog books ground DR without leaving host land.

## Residual uv · 2026-07-10 — FUTURE-AGENT tip re-anchor through uu
FUTURE-AGENT-SPEC tip → 22129e6b with closed arcs tt–uu (28 residual ships).
Competitive delta: swarm handoff tip-true after marketplace host pub-refs wave.

## Residual uw · 2026-07-10 — MO pub-refs Settings hydrate readiness
Midnight Oil create form pub-refs deep-link Settings #hydrate-live-status
(parity marketplace uu). Competitive delta: autonomous swarm grounding has full
L1/L2 prep matrix (Settings + dual-gate checklist).

## Residual ux · 2026-07-10 — SESSION-ARC tt–uw infinite wave
SESSION-ARC-tt-uw documents 30 residual ships (write-seed · free STEM · Select
open · MO foresight · arxiv/substack honesty). Competitive delta: long infinite
waves stay auditable for parallel agents after compaction.

## Residual uy · 2026-07-10 — marketplace L5 payment rails honesty
Catalog stamps L5 deferred · manual_receipt_only · live_payment=false with
dual-gate checklist link. Competitive delta: marketplace never pretends live
checkout exists — purchase+host is operator receipt only.

## Residual uz · 2026-07-10 — FUTURE-AGENT tip re-anchor through uy
FUTURE-AGENT-SPEC tip → 63101044 with closed arcs tt–uy (32 residual ships).
Competitive delta: swarm handoff tip-true; highest leverage is operator merge
PR #465.

## Residual va · 2026-07-10 — grounded evidence hydrate maintain-prep
Grounded evidence packs deep-link Settings hydrate readiness + dual-gate L1–L2
(parity ungrounded up). Competitive delta: citation trust success still exposes
prep for live injectors — never silent capability.

## Residual vb · 2026-07-10 — grounded attach hydrate maintain-prep
PublicationAttachPanel always shows Settings hydrate + dual-gate links
(grounded and ungrounded). Competitive delta: attach success stays L1/L2
prep-visible — full citation-trust matrix with evidence pack va.

## Residual vc · 2026-07-10 — FUTURE-AGENT tip re-anchor through vb
FUTURE-AGENT-SPEC tip → 1a34c354 with closed arcs tt–vb (35 residual ships).
Competitive delta: swarm handoff tip-true; operator merge PR #465 remains
highest leverage.

## Residual vd · 2026-07-10 — twin_cross_asset_merge Write seed provenance
storeTwinWriteSeed accepts twin_cross_asset_merge; TwinNotesPanel cross-asset
merge draft passes source (no collapse to twin_draft_selected). Write-seed
known_count 16. Competitive delta: recursive note-taker cross-asset merge is
bench-auditable Write provenance — same honesty bar as collective_unit_prompt.

## Residual ve · 2026-07-10 — dogfood v8 twin_cross_asset_merge write-seed
suite-competitive-dogfood-v8 adds dogfood-wrestle-twin-cross-asset-merge-write-seed.
Settings posture honesty. Competitive delta: Antiek-bench recursive rewrite
learns multi-asset twin merge Write seed as first-class wrestle task.

## Residual vf · 2026-07-10 — FUTURE-AGENT tip re-anchor through ve
FUTURE-AGENT-SPEC tip → 783ce272 with closed arcs tt–ve (38 residual ships).
Competitive delta: swarm handoff tip-true; operator merge PR #465 remains
highest leverage.

## Residual vg · 2026-07-10 — hosted twin draft Open Write source preservation
buildHostedHtmlWriteHref + HostedHtml Open Write preserve twin_cross_asset_merge
and twin_draft_selected (no collapse to hosted_html_document). Competitive
delta: recursive note-taker float → Open Write path is provenance-complete.

## Residual vh · 2026-07-10 — FUTURE-AGENT tip re-anchor through vg
FUTURE-AGENT-SPEC tip → 447182e2 with closed arcs tt–vg (40 residual ships).
Competitive delta: swarm handoff tip-true; operator merge PR #465 remains
highest leverage.

## Residual vi · 2026-07-10 — twin float host twinSeedTitle cross-asset merge
HostedHtmlDocumentHost seeds TwinNotesPanel with Twin cross-asset merge /
Twin multi-select draft titles. Competitive delta: recursive note-taker twin
floats self-seed honestly when re-opened as reading windows.

## Residual vj · 2026-07-10 — SESSION-ARC + FUTURE-AGENT tip through vi
SESSION-ARC-tt-vi + FUTURE-AGENT tip 22495c4b (42 residual ships). Competitive
delta: compaction-safe handoff for multi-agent swarm; operator merge PR #465
is highest leverage remaining.

## Residual vk · 2026-07-10 — collective_written_analysis Write seed provenance
store/load + hosted Open Write preserve collective_written_analysis (known 17).
Competitive delta: multi-spawn written analysis → Write is bench-auditable —
parity twin_cross_asset_merge and collective_unit_prompt.

## Residual vl · 2026-07-10 — dogfood v9 collective_written_analysis write-seed
suite-competitive-dogfood-v9 adds dogfood-wrestle-collective-written-analysis-write-seed.
Settings posture honesty. Competitive delta: Antiek-bench recursive rewrite
learns multi-spawn written analysis Write seed as first-class wrestle task.

## Residual vm · 2026-07-10 — FUTURE-AGENT tip re-anchor through vl
FUTURE-AGENT-SPEC tip → d2fd555e with closed arcs tt–vl (45 residual ships).
Competitive delta: swarm handoff tip-true; operator merge PR #465 remains
highest leverage.

## Residual vn · 2026-07-10 — hosted collective_written_analysis Open Write test
HostedHtmlDocumentHost stamps Open Write source + twinSeedTitle for
collective_written_analysis. Competitive delta: multi-spawn analysis host path
is mechanically proven (parity twin_cross_asset_merge vg).

## Residual vo · 2026-07-10 — SESSION-ARC tt–vn infinite wave
SESSION-ARC-tt-vn documents 47 residual ships for multi-agent swarm handoff.
Competitive delta: compaction-safe wave map; operator merge PR #465 remains
highest leverage.

## Residual vp · 2026-07-10 — spawn/collective merge hosted Open Write sources
buildHostedHtmlWriteHref + HostedHtml preserve spawn_merge and
collective_doc_merge. Competitive delta: auto-opened merge draft floats keep
Write provenance when operator Open Writes from the host.

## Residual vq · 2026-07-10 — FUTURE-AGENT tip re-anchor through vp
FUTURE-AGENT-SPEC tip → 7ee710a7 with closed arcs tt–vp (49 residual ships).
Competitive delta: swarm handoff tip-true; operator merge PR #465 remains
highest leverage.

## Residual vr · 2026-07-10 — marketplace/MO deposit hosted Open Write sources
buildHostedHtmlWriteHref + HostedHtml preserve marketplace_host and
midnight_oil_deposit. Competitive delta: book host and MO deposit floats keep
Write provenance when Open Write is used from the host.

## Residual vs · 2026-07-10 — FUTURE-AGENT tip re-anchor through vr
FUTURE-AGENT-SPEC tip → 5986da30 with closed arcs tt–vr (51 residual ships).
Competitive delta: swarm handoff tip-true; operator merge PR #465 remains
highest leverage.

## Residual vt · 2026-07-10 — Settings dual-gate L5 payment deferred
Settings dual-gate prep strip stamps L5 payment deferred / live_payment=false.
Competitive delta: deferred marketplace rails are visible on Settings chokepoint
(parity marketplace uy L5 honesty).

## Residual vu · 2026-07-10 — SESSION-ARC + FUTURE-AGENT tip through vt
SESSION-ARC-tt-vt + FUTURE-AGENT tip 8d924665 (53 residual ships). Competitive
delta: compaction-safe handoff; operator merge PR #465 remains highest leverage.

## Residual vv · 2026-07-10 — marketplace/MO hosted Open Write honesty tests
HostedHtmlDocumentHost tests lock marketplace_host and midnight_oil_deposit
Open Write sources. Competitive delta: book host and MO deposit Write paths are
mechanically proven (parity vn).

## Residual vw · 2026-07-10 — FUTURE-AGENT tip re-anchor through vv
FUTURE-AGENT-SPEC tip → 4bce4ada with closed arcs tt–vv (55 residual ships).
Competitive delta: swarm handoff tip-true; operator merge PR #465 remains
highest leverage.

## Residual vx · 2026-07-10 — collective L6 live multi-agent deferred honesty
CollectiveResearchPanel stamps L6 deferred · offline merge unit only. Competitive
delta: multi-select collective is not a silent live multi-agent council —
parity L5 payment deferred honesty.

## Residual vy · 2026-07-10 — FUTURE-AGENT tip re-anchor through vx
FUTURE-AGENT-SPEC tip → 528f5f82 with closed arcs tt–vx (57 residual ships).
Competitive delta: swarm handoff tip-true; operator merge PR #465 remains
highest leverage.

## Residual vz · 2026-07-10 — Settings dual-gate L6 deferred honesty
Settings dual-gate prep stamps L6 live multi-agent deferred · offline merge unit
(parity Collective vx + L5 payment vt). Competitive delta: decision-tree Settings
chokepoint never implies live multi-agent council is available.

## Residual wa · 2026-07-10 — launch remaining-after-prompt projection
ResearchLaunchBudgetPanel stamps remaining − high band after fire (parity
DecisionTree badge pg + MO ceiling um). Competitive delta: every research
Ask surface shows how the proposed prompt would affect the daily cap before
dispatch — budget-before-fire foresight complete on shared launch chokepoint.

## Residual wb · 2026-07-10 — Settings remaining-after-prompt foresight
Decision-tree mini estimate + full prompt-cost-projection stamp remaining − high
(parity launch wa). Competitive delta: Settings driver chokepoint answers
"how does this sample prompt affect my daily cap?" before install/dispatch.

## Residual wc · 2026-07-10 — Settings deferred map honesty
Replaced stale "Coming later" with Deferred (honest): L1–L4 dual-gate, L5/L6
deferred, L7 never-router, vault polish, keyboard map — plus shipped offline
spine note. Competitive delta: Settings never mislabels complete MO/bench as
backlog (propose≠rebuild thrash).

## Residual wd · 2026-07-10 — Shannon free PD + dogfood v10
Catalog hosts A Mathematical Theory of Communication (HTML free PD) with
computing + information_theory subjects; dogfood v10 book_qa Shannon;
Settings posture honesty. Competitive delta: tech-researcher STEM spine now
covers electricity + logic + information theory on HTML-first free path.

## Residual we · 2026-07-10 — dogfood items full list honesty
Settings dogfood fixtures list no longer silently truncates to top-12.
Competitive delta: recursive rewrite feed postures (incl. Shannon v10) remain
operator-visible as the suite grows — no silent caps.

## Residual wf · 2026-07-10 — SESSION-ARC + FUTURE tip through we
SESSION-ARC-vz-we + FUTURE-AGENT tip → 84bbfed2 (64 residual ships). Competitive
delta: compaction-safe multi-agent handoff after budget foresight + Shannon STEM
wave; operator merge PR #465 remains highest leverage.

## Residual wg · 2026-07-10 — dual-gate checklist L5/L6/L7 honesty
Operator checklist documents L5 payment deferred, L6 offline merge unit, L7
ND never-router (parity Settings dual-gate stamps). Competitive delta: deep-links
from engagement surfaces reach a complete deferred map — not L1–L4-only silence.

## Residual wh · 2026-07-10 — Settings dual-gate L5/L6/L7 checklist deep-links
Settings L5/L6 stamps link into dual-gate checklist sections; L7 checklist
link joins ND advisory panel link. Competitive delta: operator dual-gate
chokepoint is navigable end-to-end for deferred + never-router honesty.

## Residual wi · 2026-07-10 — Collective L6 checklist deep-link
CollectiveResearchPanel L6 honesty strip links dual-gate #l6-collective
(parity Settings wh). Competitive delta: multi-select collective surface
navigates deferred live-council policy without inventing injectors.

## Residual wj · 2026-07-10 — Marketplace L5 checklist deep-link
Marketplace L5 payment honesty links dual-gate #l5-payment (parity Settings
wh · Collective wi). Competitive delta: free PD host never implies live
checkout; deferred rails are one click from catalog honesty.

## Residual wk · 2026-07-10 — Settings Deferred map checklist deep-links
Deferred (honest) L5/L6/L7 rows link dual-gate checklist sections. Competitive
delta: Settings bottom deferred map is navigable end-to-end with dual-gate prep
strip (wh) — never silent deferred policy.

## Residual wl · 2026-07-10 — Turing free PD + dogfood v11
Catalog hosts On Computable Numbers (HTML free PD) with computing +
computability subjects; dogfood v11 book_qa Turing; Settings posture honesty.
Competitive delta: tech-researcher STEM spine covers electricity + logic +
information theory + computability on HTML-first free path.

## Residual wm · 2026-07-10 — Turing DR goal_hint domain parity
Hosted Turing free PD launches float DR with computing+computability domains
in goal_hint (parity Shannon). Competitive delta: reading≡research on
computability STEM is mechanically proven.

## Residual wn · 2026-07-10 — FUTURE-AGENT tip re-anchor through wm
FUTURE-AGENT-SPEC tip → d545fac5 with closed arcs vz–wm (14 residual ships).
Competitive delta: swarm handoff tip-true; operator merge PR #465 remains
highest leverage.

## Residual wo · 2026-07-10 — Deferred L7 ND advisory panel deep-link
Settings Deferred (honest) L7 links #notdiamond-advisory in-app panel
alongside checklist. Competitive delta: never-router honesty is one click from
deferred map without leaving Settings.

## Residual wp · 2026-07-10 — computability subject chip for Turing
Catalog subject chip computability isolates Turing free PD (parity Boole
computing chip). Competitive delta: tech researchers domain-filter the free
STEM spine without text search.

## Residual wq · 2026-07-10 — information_theory subject chip for Shannon
Catalog subject chip information_theory isolates Shannon free PD (parity
Turing computability chip). Competitive delta: free STEM domain chips cover
electricity · computing · information theory · computability.

## Residual wr · 2026-07-10 — FUTURE-AGENT tip re-anchor through wq
FUTURE-AGENT-SPEC tip → 24a54cf7. Competitive delta: swarm handoff tip-true
after Shannon/Turing STEM domain chips + dual-gate honesty wave.

## Residual ws · 2026-07-10 — catalog route by_subject Shannon+Turing
Marketplace catalog API by_subject stamps information_theory + computability
with Shannon/Turing entries. Competitive delta: domain chips are server-honest
not client-invented.

## Residual wt · 2026-07-10 — dogfood payload Shannon+Turing v11
dogfood_fixture_payload lists suite-competitive-dogfood-v11 with Shannon and
Turing book_qa items. Competitive delta: Settings dogfood postures are
substrate-true (propose≠promote).

## Residual wu · 2026-07-10 — SESSION-ARC + FUTURE tip through wt
SESSION-ARC-vz-wt + FUTURE tip → 741abb13 (21 residual ships this continuation).
Competitive delta: compaction-safe multi-agent handoff; operator merge PR #465
remains highest leverage.

## Residual wv · 2026-07-10 — free-PD + computability compose for Turing
Catalog free-PD-only composed with computability chip isolates Turing free PD
and excludes paid stubs. Competitive delta: free STEM path never mixes paid
entitlement into domain chips.

## Residual ww · 2026-07-10 — free-PD + information_theory compose for Shannon
Catalog free-PD-only composed with information_theory chip isolates Shannon
(parity Turing computability compose). Competitive delta: free STEM domain
filters never mix paid entitlement.

## Residual wx · 2026-07-10 — Midnight Oil L4 checklist deep-link
MO dual-gate checklist jumps to #l4-moil section. Competitive delta: midnight
oil surface navigates deferred live-step policy without inventing injectors
(parity Settings L5–L7 deep-links).

## Residual wy · 2026-07-10 — Settings dual-gate L4 checklist #l4-moil
Settings L4 checklist deep-links #l4-moil (parity MO wx). Competitive delta:
decision-tree dual-gate prep navigates MO live-step policy section directly.

## Residual wz · 2026-07-10 — FUTURE-AGENT tip re-anchor through wy
FUTURE-AGENT-SPEC tip → f12d6fc4. Competitive delta: swarm handoff tip-true
after MO L4 deep-links + free STEM compose; operator merge PR #465 highest leverage.

## Residual xa · 2026-07-10 — TwinNotes L3 checklist #l3-twin deep-link
TwinNotes dual-gate checklist jumps to #l3-twin. Competitive delta: recursive
note-taker surface navigates live-seed deferred policy without inventing
injectors (parity MO L4 · Settings L5–L7).

## Residual xb · 2026-07-10 — Settings dual-gate L3 checklist #l3-twin
Settings L3 checklist deep-links #l3-twin (parity TwinNotes xa). Competitive
delta: decision-tree dual-gate prep navigates twin live-seed policy section.

## Residual xc · 2026-07-10 — PublicationAttach L1 checklist #l1-arxiv
Publication attach dual-gate checklist jumps to #l1-arxiv (L2 anchor also
landed). Competitive delta: arxiv/substack attach surface navigates hydrate
deferred policy without inventing live body.

## Residual xd · 2026-07-10 — reading/hosted/marketplace hydrate #l1-arxiv
ResearchThis · HostedHtml · MarketplaceHost hydrate dual-gate links jump to
#l1-arxiv (parity PublicationAttach xc). Competitive delta: full reading≡research
hydrate prep matrix navigates deferred L1 policy.

## Residual xe · 2026-07-10 — ResearchContext dual-gate L1 #l1-arxiv
ResearchContext panel + citation-trust dual-gate links jump to #l1-arxiv.
Competitive delta: recursive note-taker context navigates hydrate deferred
policy (parity reading host hydrate matrix xd).

## Residual xf · 2026-07-10 — FUTURE-AGENT tip re-anchor through xe
FUTURE-AGENT-SPEC tip → b94b4c37. Competitive delta: dual-gate L1–L7 section
deep-link matrix complete across engagement surfaces; operator merge PR #465
highest leverage.

## Residual xg · 2026-07-10 — Collective dual-gate checklist #l6-collective
Collective dual-gate checklist prep link jumps to #l6-collective (parity L6
honesty strip wi). Competitive delta: multi-select collective dual-gate prep
and honesty strip share the same deferred live-council policy section.

## Residual xh · 2026-07-10 — Settings dual-gate L1 checklist #l1-arxiv
Settings L1 checklist deep-links #l1-arxiv (parity L3/L4 checklist links).
Competitive delta: decision-tree dual-gate prep strip is complete L1–L7
section navigation.

## Residual xi · 2026-07-10 — Lovelace free PD + dogfood v12
Catalog hosts Sketch of the Analytical Engine (HTML free PD) with computing +
history subjects; dogfood v12 book_qa Lovelace; Settings posture honesty.
Competitive delta: tech-researcher free STEM spine covers electricity + logic +
information theory + computability + computing history on HTML-first free path.

## Residual xj · 2026-07-10 — history subject chip for Lovelace
Catalog subject chip history isolates Lovelace free PD. Competitive delta:
tech researchers domain-filter computing history on free STEM path.

## Residual xk · 2026-07-10 — Lovelace DR goal_hint domain parity
Hosted Lovelace free PD launches float DR with computing+history domains in
goal_hint (parity Turing/Shannon). Competitive delta: reading≡research on
computing-history STEM is mechanically proven.

## Residual xl · 2026-07-10 — free-PD + history compose for Lovelace
Catalog free-PD-only composed with history chip isolates Lovelace (parity
Turing/Shannon free-PD domain compose). Competitive delta: free STEM history
path never mixes paid entitlement.

## Residual xn · 2026-07-10 — SpawnMerge dual-gate #l6-collective
SpawnMerge dual-gate checklist jumps to #l6-collective (parity Collective xg).
Competitive delta: multi-spawn merge prep shares deferred live-council policy.

## Residual xo · 2026-07-10 — catalog route by_subject Lovelace history
Marketplace catalog API by_subject stamps history with Lovelace entry.
Competitive delta: history domain chip is server-honest (parity Shannon/Turing).

## Residual xp · 2026-07-10 — free-PD + computing chip STEM quartet
free-PD-only composed with computing chip surfaces Boole · Shannon · Turing ·
Lovelace and excludes paid stubs. Competitive delta: tech-researcher free
computing STEM path is compose-complete on HTML-first marketplace.

## Residual xq · 2026-07-10 — FUTURE-AGENT tip re-anchor through xp
FUTURE-AGENT-SPEC tip re-anchored after free STEM quartet compose + dual-gate
L1–L7 matrix. Competitive delta: swarm handoff tip-true; operator merge PR #465
highest leverage.

## Residual xr · 2026-07-10 — Settings dual-gate L2 checklist #l2-substack
Settings L2 checklist deep-links #l2-substack (completes L1–L2 pair with xh).
Competitive delta: decision-tree dual-gate prep navigates Substack ToS factory
deferred policy section.

## Residual xs · 2026-07-10 — FUTURE-AGENT tip re-anchor through xr
FUTURE-AGENT-SPEC tip re-anchored after Settings L2 checklist + free STEM
quartet. Competitive delta: swarm handoff tip-true; operator merge PR #465
highest leverage.

## Residual xt · 2026-07-10 — free computing STEM quartet substrate proof
default_demo_catalog filter_by_subject(computing) free PD includes Boole ·
Shannon · Turing · Lovelace as HTML. Competitive delta: free computing STEM
spine is substrate-true (parity frontend compose xp).

## Residual xu · 2026-07-10 — ResearchProgress dual-gate #l4-moil
ResearchProgress dual-gate checklist jumps to #l4-moil (parity MO wx).
Competitive delta: multi-minute progress surface navigates live-step deferred
policy without inventing injectors.

## Residual xv · 2026-07-10 — free electricity STEM trio substrate proof
default_demo_catalog filter_by_subject(electricity) free PD includes Faraday ·
Maxwell · Heaviside as HTML. Competitive delta: free electricity STEM spine is
substrate-true (parity computing quartet xt).

## Residual xw · 2026-07-10 — free-PD + electricity chip STEM trio
free-PD-only composed with electricity chip surfaces Faraday · Maxwell ·
Heaviside and excludes paid stubs. Competitive delta: free electricity STEM
path is compose-complete (parity computing quartet xp).

## Residual xx · 2026-07-10 — FUTURE-AGENT tip re-anchor through xw
FUTURE-AGENT-SPEC tip re-anchored after free electricity STEM trio compose +
computing quartet + dual-gate L1–L7 matrix. Competitive delta: swarm handoff
tip-true; operator merge PR #465 highest leverage.

## Residual xy · 2026-07-10 — MO pub-refs dual-gate #l1-arxiv
Midnight Oil pub-refs hydrate dual-gate jumps to #l1-arxiv (parity reading
hosts xd). Competitive delta: MO knowledge-dense pub-refs prep navigates
hydrate deferred policy without inventing live body.

## Residual xz · 2026-07-10 — FUTURE-AGENT tip re-anchor through xy
FUTURE-AGENT-SPEC tip re-anchored after 53 residual ships (budget foresight ·
dual-gate L1–L7 · free STEM electricity+computing · dogfood v12). Competitive
delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual ya · 2026-07-10 — dogfood list item_count match honesty
antiek-bench-dogfood-items stamps data-item-count-matches-listed. Competitive
delta: Settings never silently diverges listed fixtures from item_count.

## Residual yb · 2026-07-10 — dogfood mock full v12 item list
Settings dogfood test fixture lists all 18 v12 items (matches substrate).
Competitive delta: data-item-count-matches-listed=true for substrate-true path.

## Residual yc · 2026-07-10 — SessionFlywheel dual-gate #l1-arxiv
SessionFlywheel dual-gate checklist jumps to #l1-arxiv. Competitive delta:
land→bench feed prep navigates hydrate deferred policy.

## Residual yd · 2026-07-10 — FUTURE-AGENT tip re-anchor through yc
FUTURE-AGENT-SPEC tip re-anchored after 57 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual ye · 2026-07-10 — Marketplace dual-gate #l5-payment
Marketplace catalog dual-gate checklist jumps to #l5-payment (parity L5
honesty strip wj). Competitive delta: free PD host path dual-gate prep and
payment honesty share deferred rails policy section.

## Residual yf · 2026-07-10 — FUTURE-AGENT tip re-anchor through ye
FUTURE-AGENT-SPEC tip re-anchored after 59 residual ships. Competitive delta:
swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual yg · 2026-07-10 — dogfood summary book_qa/wrestle counts
antiek-bench-dogfood-summary stamps data-book-qa-count and data-wrestle-count
(v12: 7/7). Competitive delta: STEM book_qa expansion is machine-auditable on
Settings dogfood chokepoint.

## Residual yh · 2026-07-10 — dogfood summary full task-class counts
antiek-bench-dogfood-summary stamps distill/synthesize/wrestle/book_qa counts
(v12: 2/2/7/7). Competitive delta: full Antiek-bench dogfood task-class matrix
is machine-auditable on Settings.

## Residual yi · 2026-07-10 — FUTURE-AGENT tip re-anchor through yh
FUTURE-AGENT-SPEC tip re-anchored after 62 residual ships (budget foresight ·
dual-gate L1–L7 · free STEM · dogfood v12 task-class counts). Competitive
delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual yj · 2026-07-10 — Antiek-bench dual-gate #l7-notdiamond
Suite proposal dual-gate checklist jumps to #l7-notdiamond. Competitive delta:
recursive rewrite surface navigates ND never-router policy (parity ND panel
advisory-only link).

## Residual yk · 2026-07-10 — FUTURE-AGENT tip re-anchor through yj
FUTURE-AGENT-SPEC tip re-anchored after 64 residual ships. Competitive delta:
swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual yl · 2026-07-10 — DecisionTree dual-gate offline + L7 ND stamps
DecisionTreeDriverBadge dual-gate entry stamps offline-default and L7 ND
advisory-only. Competitive delta: shared driver+budget chokepoint never
implies silent live injectors or ND dispatch authority.

## Residual ym · 2026-07-10 — launch budget dual-gate offline + L7 ND stamps
ResearchLaunchBudget dual-gate entry stamps offline-default and L7 ND
advisory-only (parity DecisionTree yl). Competitive delta: shared launch
budget chokepoint never implies silent live injectors or ND dispatch authority.

## Residual yn · 2026-07-10 — FUTURE-AGENT tip re-anchor through ym
FUTURE-AGENT-SPEC tip re-anchored after 67 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual yo · 2026-07-10 — free-PD + technology chip tech-researcher path
free-PD-only composed with technology chip surfaces free STEM technology texts
and excludes literature/paid stubs. Competitive delta: tech-researcher default
domain path is free-PD-only + technology.

## Residual yp · 2026-07-10 — free technology STEM substrate spans domains
free technology subject includes Faraday + Shannon + Turing + Lovelace as HTML.
Competitive delta: tech-researcher technology domain is substrate-true for
cross-electricity/computing free STEM (parity frontend compose yo).

## Residual yq · 2026-07-10 — FUTURE-AGENT tip re-anchor through yp
FUTURE-AGENT-SPEC tip re-anchored after 70 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual yr · 2026-07-10 — catalog route by_subject technology count
Marketplace catalog API by_subject technology ≥4 for free STEM span.
Competitive delta: technology domain chip is server-honest for tech-researcher
default path (parity frontend compose yo · substrate yp).

## Residual ys · 2026-07-10 — FUTURE-AGENT tip re-anchor through yr
FUTURE-AGENT-SPEC tip re-anchored after 72 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual yt · 2026-07-10 — dogfood summary data-view-format html
antiek-bench-dogfood-summary stamps data-view-format=html. Competitive delta:
Antiek-bench dogfood human view is HTML-first on Settings chokepoint.

## Residual yu · 2026-07-10 — FUTURE-AGENT tip re-anchor through yt
FUTURE-AGENT-SPEC tip re-anchored after 74 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual yv · 2026-07-10 — dogfood summary data-source honesty
antiek-bench-dogfood-summary stamps data-source=antiek_bench.dogfood_fixtures.
Competitive delta: Settings dogfood provenance is machine-auditable.

## Residual yw · 2026-07-10 — FUTURE-AGENT tip re-anchor through yv
FUTURE-AGENT-SPEC tip re-anchored after 76 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual yx · 2026-07-10 — dogfood summary data-label honesty
antiek-bench-dogfood-summary stamps data-label=antiek-bench-competitive-dogfood.
Competitive delta: suite identity is machine-auditable on Settings.

## Residual yy · 2026-07-10 — FUTURE-AGENT tip re-anchor through yx
FUTURE-AGENT-SPEC tip re-anchored after 78 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual yz · 2026-07-10 — dogfood summary data-settings-panel honesty
antiek-bench-dogfood-summary stamps data-settings-panel=antiek_bench_dogfood_fixtures.
Competitive delta: Settings panel identity is machine-auditable on dogfood chokepoint.

## Residual za · 2026-07-10 — FUTURE-AGENT tip re-anchor through yz
FUTURE-AGENT-SPEC tip re-anchored after 80 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zb · 2026-07-10 — catalog route free_count honesty after STEM
Marketplace catalog free_count ≥16 after Shannon/Turing/Lovelace expansion.
Competitive delta: free PD honesty scales with STEM catalog growth.

## Residual zc · 2026-07-10 — FUTURE-AGENT tip re-anchor through zb
FUTURE-AGENT-SPEC tip re-anchored after 82 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zd · 2026-07-10 — dogfood items list data-view-format html
antiek-bench-dogfood-items stamps data-view-format=html. Competitive delta:
dogfood fixture list is HTML-first (parity summary yt).

## Residual ze · 2026-07-10 — FUTURE-AGENT tip re-anchor through zd
FUTURE-AGENT-SPEC tip re-anchored after 84 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zf · 2026-07-10 — dogfood panel propose≠promote honesty
antiek-bench-dogfood-panel stamps propose≠promote and auto_promoted=false.
Competitive delta: dogfood fixtures panel never implies auto-promotion
(parity suite proposal panel).

## Residual zg · 2026-07-10 — FUTURE-AGENT tip re-anchor through zf
FUTURE-AGENT-SPEC tip re-anchored after 86 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zh · 2026-07-10 — dogfood panel suite version + item count
antiek-bench-dogfood-panel stamps data-suite-version and data-item-count after
fixtures load. Competitive delta: panel shell is suite-identity honest without
opening summary metrics only.

## Residual zi · 2026-07-10 — FUTURE-AGENT tip re-anchor through zh
FUTURE-AGENT-SPEC tip re-anchored after 88 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zj · 2026-07-10 — dogfood payload + API v12 STEM honesty
dogfood_fixture_payload and /settings/antiek-bench/dogfood-fixtures lock v12
with Shannon/Turing/Lovelace HTML + book_qa=7. Competitive delta: Settings
API and substrate dogfood are identity-honest end-to-end.

## Residual zk · 2026-07-10 — FUTURE-AGENT tip re-anchor through zj
FUTURE-AGENT-SPEC tip re-anchored after 90 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zl · 2026-07-10 — SESSION-ARC handoff through zk
SESSION-ARC-vz-zk documents 91 residual ships this continuation. Competitive
delta: compaction-safe multi-agent handoff; operator merge PR #465 highest leverage.

## Residual zm · 2026-07-10 — dogfood panel data-label after load
antiek-bench-dogfood-panel stamps data-label after fixtures load. Competitive
delta: panel shell suite identity complete (version · label · count).

## Residual zn · 2026-07-10 — FUTURE-AGENT tip re-anchor through zm
FUTURE-AGENT-SPEC tip re-anchored after 93 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zo · 2026-07-10 — dogfood panel data-source after load
antiek-bench-dogfood-panel stamps data-source after fixtures load. Competitive
delta: panel shell provenance complete (version · label · source · count).

## Residual zp · 2026-07-10 — FUTURE-AGENT tip re-anchor through zo
FUTURE-AGENT-SPEC tip re-anchored after 95 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zq · 2026-07-10 — dogfood panel data-settings-panel after load
antiek-bench-dogfood-panel stamps data-settings-panel after fixtures load.
Competitive delta: panel shell Settings identity complete.

## Residual zr · 2026-07-10 — FUTURE-AGENT tip re-anchor through zq
FUTURE-AGENT-SPEC tip re-anchored after 97 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zs · 2026-07-10 — dogfood panel book_qa + wrestle counts
antiek-bench-dogfood-panel stamps data-book-qa-count and data-wrestle-count
after load (v12: 7/7). Competitive delta: panel shell STEM book_qa honesty
without opening summary only.

## Residual zt · 2026-07-10 — FUTURE-AGENT tip re-anchor through zs
FUTURE-AGENT-SPEC tip re-anchored after 99 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zu · 2026-07-10 — dogfood panel full task-class counts
antiek-bench-dogfood-panel stamps distill/synthesize/wrestle/book_qa after load
(v12: 2/2/7/7). Competitive delta: panel shell full Antiek-bench task-class
matrix honesty (parity summary yh).

## Residual zv · 2026-07-10 — FUTURE-AGENT tip re-anchor through zu
FUTURE-AGENT-SPEC tip re-anchored after 101 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zw · 2026-07-10 — free technology set size honesty
free technology subject set len ≥4 all free PD HTML. Competitive delta:
tech-researcher technology domain is non-trivial free STEM corpus.

## Residual zx · 2026-07-10 — FUTURE-AGENT tip re-anchor through zw
FUTURE-AGENT-SPEC tip re-anchored after 103 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual zy · 2026-07-10 — free computing set size honesty
free computing subject set len ≥4 all free PD HTML. Competitive delta:
tech-researcher computing domain is non-trivial free STEM corpus (parity
technology zw).

## Residual zz · 2026-07-10 — FUTURE-AGENT tip re-anchor through zy
FUTURE-AGENT-SPEC tip re-anchored after 105 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual aaa · 2026-07-10 — free electricity set size honesty
free electricity subject set len ≥3 all free PD HTML. Competitive delta:
tech-researcher electricity domain is non-trivial free STEM corpus (parity
computing/technology size honesty).

## Residual aab · 2026-07-10 — catalog free_count matches entry is_free
Marketplace catalog free_count equals sum of entry is_free flags. Competitive
delta: free PD honesty has no silent aggregate drift.

## Residual aac · 2026-07-10 — FUTURE-AGENT tip re-anchor through aab
FUTURE-AGENT-SPEC tip re-anchored after 109 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual aad · 2026-07-10 — catalog public_domain_count matches license_class
Marketplace catalog public_domain_count equals sum of entry license_class
public_domain flags. Competitive delta: PD honesty has no silent aggregate drift
(parity free_count aab).

## Residual aae · 2026-07-10 — FUTURE-AGENT tip re-anchor through aad
FUTURE-AGENT-SPEC tip re-anchored after 111 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual aaf · 2026-07-10 — catalog count matches entries length
Marketplace catalog count equals len(entries). Competitive delta: catalog
listing has no silent truncation (parity free_count / PD count honesty).

## Residual aag · 2026-07-10 — FUTURE-AGENT tip re-anchor through aaf
FUTURE-AGENT-SPEC tip re-anchored after 113 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual aah · 2026-07-10 — spawn_merge window source provenance
openMergedResearchWindow default source spawn_merge_panel → spawn_merge so
auto-open merge floats preserve HostedHtml Open Write + Antiek-bench write-seed
feed (no collapse to hosted_html_document). Competitive delta: highlight →
float DR → merge → Write is identity-honest end-to-end.

## Residual aai · 2026-07-10 — marketplace library Write seed aliases
marketplace_library and marketplace_library_rehydrate window sources now map
to marketplace_host for HostedHtml Open Write + Antiek-bench write-seed feed.
Competitive delta: account library → window → Write is identity-honest with
host-land path (no silent hosted_html_document collapse).

## Residual aaj · 2026-07-10 — marketplace_catalog Write seed provenance
Filter-aware catalog HTML floats preserve marketplace_catalog Open Write +
Antiek-bench write-seed feed (known_count 18). Competitive delta: STEM catalog
projection → Write is identity-honest for recursive suite rewrite (not silent
hosted_html_document collapse).

## Residual aak · 2026-07-10 — FUTURE-AGENT tip re-anchor through aaj
FUTURE-AGENT-SPEC tip re-anchored after 117 residual ships this continuation
(write-seed provenance wave aah–aaj closed). Competitive delta: swarm handoff
tip-true; operator merge PR #465 highest leverage.

## Residual aal · 2026-07-10 — marketplace host L2 Substack dual-gate deep-link
Host-land pub-refs prep now deep-links #l2-substack (parity Settings xr) in
addition to #l1-arxiv. Competitive delta: knowledge-dense Substack hydrate prep
is visible on free STEM book → DR launch path (label honesty, not live enable).

## Residual aam · 2026-07-10 — HostedHtml L2 Substack dual-gate deep-link
Hosted book/window pub-refs prep deep-links #l2-substack (parity marketplace aal).
Competitive delta: reading ≡ research HTML host surfaces Substack hydrate prep
honestly beside arxiv (offline-default dual-gate).

## Residual aan · 2026-07-10 — Midnight Oil L2 Substack dual-gate deep-link
MO create-form pub-refs prep deep-links #l2-substack (parity aal/aam). Competitive
delta: autonomous midnight-oil swarm grounding surfaces Substack hydrate prep
beside arxiv before goals+duration approve (offline-default dual-gate).

## Residual aao · 2026-07-10 — ResearchThis L2 Substack dual-gate deep-link
Reading-mode Research This pub-refs prep deep-links #l2-substack (parity aal–aan).
Competitive delta: highlight → deep research on reading surface surfaces Substack
hydrate prep beside arxiv (offline-default dual-gate).

## Residual aap · 2026-07-10 — PublicationAttach L2 Substack dual-gate deep-links
Attach form + post-attach hydrate prep deep-link #l2-substack (parity aal–aao).
Competitive delta: knowledge-dense arxiv/substack attach path surfaces Substack
ToS/factory prep beside arxiv on both pre- and post-attach surfaces.

## Residual aaq · 2026-07-10 — ResearchContext L2 Substack dual-gate deep-links
Research context header + evidence citation-trust (grounded/ungrounded) deep-link
#l2-substack (parity aal–aap). Competitive delta: intelligent search / evidence
pack path surfaces Substack hydrate prep beside arxiv on the workstation chokepoint.

## Residual aar · 2026-07-10 — SESSION-ARC + FUTURE tip through aaq
SESSION-ARC-aah-aaq documents write-seed provenance (aah–aaj) + L2 Substack
dual-gate deep-link wave (aal–aaq). FUTURE tip re-anchored. Competitive delta:
compaction-safe multi-agent handoff; operator merge PR #465 highest leverage.

## Residual aas · 2026-07-10 — SessionFlywheel L2 Substack dual-gate deep-link
Session land dual-gate prep deep-links #l2-substack (parity aal–aaq). Competitive
delta: session flywheel complete path surfaces Substack hydrate prep beside arxiv.

## Residual aat · 2026-07-10 — L6 collective dual-gate label honesty
Spawn merge + collective multi-spawn panels label Dual-gate L6 collective
checklist (href #l6-collective) — no more L1–L4 label/href mismatch. Competitive
delta: multi-spawn merge path honesty matches offline merge unit doctrine.

## Residual aau · 2026-07-10 — L4 Midnight Oil dual-gate label honesty
Research progress panel labels Dual-gate L4 Midnight Oil checklist (href
#l4-moil). Competitive delta: multi-minute plan→cite progress path honesty
matches MO live-step dual-gate doctrine (parity aat L6 label fix).

## Residual aav · 2026-07-10 — free physics STEM set size honesty
Free physics subject set len ≥4 all free PD HTML (Principia + Faraday/Maxwell/
Heaviside). Competitive delta: tech-researcher physics domain is non-trivial free
STEM corpus (parity electricity/computing/technology size honesty).

## Residual aaw · 2026-07-10 — free mathematics STEM set size honesty
Free mathematics subject set len ≥4 all free PD HTML (Elements · Principia ·
Boole · Lovelace). Competitive delta: tech-researcher mathematics domain is
non-trivial free STEM corpus (parity physics aav).

## Residual aax · 2026-07-10 — FUTURE-AGENT tip re-anchor through aaw
FUTURE-AGENT-SPEC tip re-anchored after 131 residual ships this continuation.
Competitive delta: swarm handoff tip-true; operator merge PR #465 highest leverage.

## Residual aay · 2026-07-10 — free science STEM set size honesty
Free science subject set len ≥6 all free PD HTML (Origin · Principia · Elements ·
Novum · Faraday · Shannon). Competitive delta: cross-domain science filter is a
non-trivial free STEM corpus for tech researchers (parity physics/math).

## Residual aaz · 2026-07-10 — L7 ND advisory dual-gate deep-link on chokepoints
DecisionTreeDriverBadge + ResearchLaunchBudgetPanel dual-gate links deep-link
#l7-notdiamond (advisory only · never dispatch authority). Competitive delta:
shared driver+budget chokepoints land operators on ND-never-router doctrine.

## Residual aba · 2026-07-10 — free philosophy set size honesty
Free philosophy subject set len ≥4 all free PD HTML (Novum · Liberty · Discourse ·
Wealth). Competitive delta: critical-reasoning substrate for tech researchers is
a non-trivial free corpus (parity science/physics/math domain honesty).

## Residual abb · 2026-07-10 — SESSION-ARC + FUTURE tip through aba
SESSION-ARC-aat-aba documents dual-gate label honesty + STEM domain size wave.
FUTURE tip re-anchored after 135+ ships. Competitive delta: compaction-safe
multi-agent handoff; operator merge PR #465 highest leverage.

## Residual abc · 2026-07-10 — free biology STEM pair (Origin + Hooke)
Catalog adds Hooke Micrographia free PD HTML (biology · technology · physics ·
method) beside Origin of Species. Competitive delta: free biology filter is a
non-trivial tech-researcher STEM pair (instruments + natural history).

## Residual abd · 2026-07-10 — free method subject Novum + Hooke
Free method subject set includes Novum Organum + Hooke Micrographia (len ≥2 free
PD HTML). Competitive delta: research-methodology filter is a non-trivial free
pair for tech researchers (Baconian method + instrumented observation).

## Residual abe · 2026-07-10 — FUTURE-AGENT tip re-anchor through abd
FUTURE-AGENT-SPEC tip re-anchored after 138 residual ships this continuation
(Hooke biology/method wave abc-abd). Competitive delta: swarm handoff tip-true;
operator merge PR #465 highest leverage.

## Residual abf · 2026-07-10 — free engineering STEM trio honesty
Free engineering subject set len ≥3 all free PD HTML (Heaviside · Shannon ·
Lovelace). Competitive delta: tech-researcher engineering filter is a non-trivial
free STEM corpus (parity electricity trio).

## Residual abg · 2026-07-10 — free_count floor ≥17 after Hooke
Marketplace catalog free_count / public_domain_count floor raised to ≥17 after
Hooke Micrographia free PD HTML. Competitive delta: free STEM catalog non-trivial
size honesty tracks corpus growth.

## Residual abh · 2026-07-10 — free PD HTML spine floor ≥17
Offline free_pd catalog spine floor raised to ≥17 free PD HTML hosts after Hooke.
Competitive delta: free STEM corpus size honesty tracks growth (parity free_count abg).

## Residual abi · 2026-07-10 — catalog HTML free_count/public_domain_count honesty
project_catalog_html header stamps free_count + public_domain_count (parity API
catalog honesty). Competitive delta: filter-aware HTML catalog window is
identity-honest for free/PD STEM browse without a second network hop.

## Residual abj · 2026-07-10 — free_only free_count identity + technology Hooke
free_only catalog HTML free_count equals Entries; free_only+biology free_count=2
(Origin+Hooke); free technology includes Hooke Micrographia (len ≥5). Competitive
delta: filter-aware free STEM HTML browse is identity-honest end-to-end.

## Residual abk · 2026-07-10 — free technology HTML + free physics Hooke
free_only+technology catalog HTML free_count ≥5 includes Hooke; free physics
set includes Hooke (len ≥5); API technology by_subject ≥5. Competitive delta:
instrumented-observation STEM joins tech-researcher free technology/physics filters.

## Residual abl · 2026-07-10 — free method HTML free_count + free science Hooke
free_only+method catalog HTML free_count=2 (Novum+Hooke); free science set
includes Hooke (len ≥7). Competitive delta: research-methodology free filter is
identity-honest; free science spine includes instrumented observation.

## Residual abm · 2026-07-10 — SESSION-ARC + FUTURE tip through abl
SESSION-ARC-abc-abl documents Hooke free STEM + catalog HTML free_count honesty wave.
FUTURE tip re-anchored after 146 residual ships. Competitive delta: compaction-safe
multi-agent handoff; operator merge PR #465 highest leverage.

## Residual abn · 2026-07-10 — free_count is_free only (not OR public_domain)
catalog_honesty_payload free_count counts is_free=True only — never OR
public_domain. Competitive delta: free inventory cannot invent free when a
public_domain entry is not free; public_domain_count stays separate honesty.

## Residual abo · 2026-07-10 — catalog HTML free_count is_free only
project_catalog_html free_count counts is_free only (parity abn API). Competitive
delta: HTML catalog free inventory identity matches API free_count doctrine end-to-end.

## Residual abp · 2026-07-10 — free_only filter is is_free inventory
project_catalog_html free_only filter uses is_free only (parity free_count abn/abo).
Competitive delta: free-PD chip filter and free_count share one free-inventory doctrine.

## Residual abq · 2026-07-10 — MarketplaceHost free chip is is_free only
free-PD catalog chip filter uses is_free only (parity free_count abn/abo + free_only
HTML abp). Competitive delta: UI free spine filter and free inventory honesty share
one doctrine end-to-end (API · HTML · client).

## Residual abr · 2026-07-10 — SESSION-ARC + FUTURE tip through abq
SESSION-ARC-abn-abq documents free inventory is_free-only doctrine (API·HTML·UI).
FUTURE tip re-anchored after 151 residual ships. Competitive delta: compaction-safe
multi-agent handoff; operator merge PR #465 highest leverage.

## Residual abs · 2026-07-10 — host-land free_host is is_free only
Host-land free_host honesty uses catalog is_free only (parity free inventory
abn–abq). Competitive delta: free host path identity is end-to-end (API·HTML·UI·host land).

## Residual abt · 2026-07-10 — FUTURE tip free inventory doctrine through abs
FUTURE + SESSION-ARC free inventory is_free-only doctrine closed API·HTML·UI·host land
(abn–abs). Tip ccb433c2 · 153 ships. Competitive delta: swarm handoff tip-true;
operator merge PR #465 highest leverage.

## Residual abu · 2026-07-10 — library documents is_free free inventory
GET /marketplace/library stamps is_free on each document; client library free
honesty prefers is_free (parity free inventory doctrine abn–abs). Competitive
delta: account library free spine is identity-honest with catalog free inventory.

## Residual abv · 2026-07-10 — FUTURE tip free inventory doctrine through abu
Free inventory is_free-only doctrine closed end-to-end (API·HTML·UI·host·library).
Tip ec8c5e6b · 155 ships. Competitive delta: swarm handoff tip-true; operator merge
PR #465 highest leverage.

## Residual abw · 2026-07-10 — purchased library is_free false
Purchase-and-host library row stamps is_free=false (parity free inventory doctrine).
Competitive delta: paid books never invent free inventory after seamless host port.

## Residual abx · 2026-07-10 — library HTML free_count honesty
list_account_library_html stamps free_count + [license/free|paid] (parity free
inventory doctrine). Competitive delta: library HTML projection is free-inventory
honest for account-hosted books (HTML-first, never PDF).

## Residual aby · 2026-07-10 — FUTURE tip free inventory through abx
Free inventory is_free-only doctrine closed API·HTML·UI·host·library JSON·library HTML
(abn–abx). Tip 08ef962c · 158 ships. Competitive delta: swarm handoff tip-true;
operator merge PR #465 highest leverage.

## Residual abz · 2026-07-10 — free inventory chip copy honesty
Marketplace free chip label/strip say free inventory only / free-only=on (parity
is_free doctrine abn–abx). Competitive delta: operator-facing free filter copy
matches free inventory identity end-to-end.

## Residual aca · 2026-07-10 — FUTURE tip free inventory complete through abz
Free inventory is_free-only doctrine complete end-to-end including operator-facing
free-only chip copy (abn–abz). Tip 2ff4fe73 · 160 ships. Competitive delta: swarm
handoff tip-true; operator merge PR #465 highest leverage; next residuals leave free thrash.

## Residual acb · 2026-07-10 — library API free_count aggregate
GET /marketplace/library returns free_count aggregate (parity catalog free_count).
Competitive delta: account library free inventory honesty is machine-readable
for Settings/metrics without re-summing documents.

## Residual acc · 2026-07-10 — MarketplaceHost prefers library API free_count
Client library free honesty prefers server free_count aggregate (acb) after load
and host/purchase refresh. Competitive delta: library free inventory identity is
server-authoritative when present (parity catalog free_count).

## Residual acd · 2026-07-10 — FUTURE tip free inventory through acc
Free inventory is_free-only doctrine complete including library free_count API+client
(abn–acc). Tip 1516889d · 163 ships. Competitive delta: swarm handoff tip-true;
operator merge PR #465 highest leverage; next leave free-inventory thrash.

## Residual ace · 2026-07-10 — library free_count_source + row free inventory stamps
Library metrics stamp free_count_source=api|client and library-api-free-count;
library rows stamp data-is-free + data-license-class (parity catalog). Competitive
delta: account library free inventory is machine-readable end-to-end after host.

## Residual acf · 2026-07-10 — library Open Write twin_seed body when hosted
Library Open Write dual handoff seeds twin with in-session host HTML body when
document matches (not title-only). Competitive delta: marketplace host → library
→ Write recursive note-taker path keeps body substrate for Antiek-bench write-seed.

## Residual acg · 2026-07-10 — library rehydrate retains body for Open Write
Library rehydrate sets hosted state with HTML body so Open Write twin_seed has
body after rehydrate open (parity acf host path). Competitive delta: seamless
port library → rehydrate → Write recursive note-taker keeps full HTML substrate.

## Residual ach · 2026-07-10 — library rehydrate offline twin seed
Library rehydrate offline-seeds twin notes (force_offline) so recursive note-taker
substrate joins library-opened books (parity host/purchase gj). Competitive delta:
seamless port library → rehydrate → twins → Write is note-taker complete offline.

## Residual aci · 2026-07-10 — library Open Write title-only before rehydrate
Library Open Write stamps data-write-seed-has-body=false until rehydrate/host
provides body. Competitive delta: write-seed body honesty matrix complete
(title-only → rehydrate body → twin seed offline).

## Residual acj · 2026-07-10 — SESSION-ARC + FUTURE tip through aci
SESSION-ARC-acf-aci documents library → Write twin_seed body + rehydrate twins.
Tip 396618e9 · 169 ships. Competitive delta: swarm handoff tip-true; operator merge
PR #465 highest leverage.

## Residual ack · 2026-07-10 — MO deposit Open Write twin_seed has-body honesty
Midnight Oil deposit Open Write stamps data-write-seed-has-body (parity marketplace
acf library path). Competitive delta: autonomous MO deposit → Write recursive
note-taker body honesty is machine-readable.

## Residual acl · 2026-07-10 — spawn merge Open Write twin_seed has-body honesty
Spawn merge Open Write stamps data-write-seed-has-body (parity marketplace acf /
MO ack). Competitive delta: highlight → float DR → merge → Write body honesty
is machine-readable end-to-end.

## Residual acm · 2026-07-10 — collective Open Write twin_seed has-body honesty
Collective Open Write stamps data-write-seed-has-body (parity spawn merge acl /
MO ack / marketplace acf). Competitive delta: multi-spawn collective → Write
body honesty is machine-readable end-to-end.

## Residual acn · 2026-07-10 — HostedHtml Open Write twin_seed has-body honesty
HostedHtml Open Write stamps data-write-seed-has-body (parity acf–acm matrix).
Competitive delta: float/full hosted HTML → Write body honesty is machine-readable
for every float host path (marketplace, MO, merge, evidence, …).

## Residual aco · 2026-07-10 — SESSION-ARC + FUTURE tip through acn
SESSION-ARC-acf-acn documents write-seed has-body honesty matrix across marketplace,
MO, spawn merge, collective, HostedHtml. Tip 2bc6bf23 · 174 ships. Competitive delta:
swarm handoff tip-true; operator merge PR #465 highest leverage.


## Residual ado · 2026-07-10 — Settings dogfood v13 has-body posture
Settings data-has-write-seed-has-body-posture + Spine postures (v13) · write-seed
has-body (substrate fixture adn now operator-visible). Competitive delta:
recursive rewrite dogfood honesty is machine-readable on Settings summary, not
only in item list. Vitest Settings 34 green.

## Residual adp · 2026-07-10 — suite proposal body honesty matrix + API wire
SuiteProposal + Settings surface full body honesty matrix (with_body · title_only ·
unknown); AntiekBenchSuiteProposalResponse now carries title_only (was Pydantic-stripped)
plus with_body/unknown. Competitive delta: recursive rewrite audit is machine-readable
end-to-end from usage events → propose → Settings metrics (parity usage summary acu).
pytest 2 · vitest Settings 34 green.

## Residual adq · 2026-07-10 — twin Write seed has_body → suite rewrite feed
TwinWriteSeedPayload.has_body persisted; marketplace/hosted/merge title-only Open Write
stamps false; Write create seedTwinNotes passes has_body so title-only body_text is not
mis-inferred true for Antiek-bench usage. Competitive delta: recursive rewrite learning
from Open Write is honest end-to-end (Open Write stamp → session seed → create seed →
suite proposal matrix adp). vitest twinWriteSeed+WriteHome 61 green.

## Residual adr · 2026-07-10 — weekly leaderboard by_task_class model quality
Settings Antiek-bench leaderboard shows per-model by_task_class scores and best
model per task class (book_qa/wrestle/distill/synthesize) as advisory only.
Competitive delta: operator can weekly know which models win which tasks without
opening raw HTML or auto-routing dispatch (parity NotDiamond advisory doctrine).
vitest Settings 34 green.

## Residual ads · 2026-07-10 — install best-by-task as decision-tree driver
Leaderboard task winners offer Install as driver (advisory only) so operator can
pick book_qa/wrestle specialists from weekly Antiek-bench into decision-tree.
Competitive delta: model quality for a given task is not only visible (adr) but
actionable without auto-routing (parity NotDiamond install-advisory doctrine).
vitest Settings 35 green.

## Residual adt · 2026-07-10 — SESSION-ARC adn–ads write-seed + model quality
SESSION-ARC-adn-ads documents write-seed body honesty (adn–adq) + weekly model
quality per task (adr–ads). Tip 6d5a12b0 · swarm handoff tip-true. Competitive
delta: multi-agent infinite continues outside closed arcs; operator merge PR #465
highest leverage.

## Residual adu · 2026-07-10 — decision-tree install provenance honesty
Decision-tree status stamps data-install-source (manual | leaderboard_recommended |
leaderboard_task | notdiamond) + data-install-task-class after ads best-by-task install.
Competitive delta: operator can audit why a driver is installed (weekly task winner)
without implying auto-routing. vitest Settings 35 green.

## Residual adv · 2026-07-10 — TwinNotes + MO storeTwinWriteSeed has_body feed
TwinNotes draft storeTwinWriteSeed passes explicit has_body; MO deposit seed stamps
has_body=true when HTML body present. Competitive delta: recursive note-taker Open
Write → Write create usage feed is honest for twin draft and MO deposit paths (closes
adq gap on engagement store call sites). vitest TwinNotesPanel 30 green.

## Residual adw · 2026-07-10 — dogfood has-body → suite rewrite + usage deep-links
Dogfood has-body posture chrome deep-links to suite proposal and usage body matrix
(hash targets). Competitive delta: operator path fixture → recursive rewrite learning
is one-click navigable (parity decision-tree dogfood/leaderboard links). vitest Settings 35 green.

## Residual adx · 2026-07-10 — Midnight Oil live ceiling preview before create
estimateMoilRecommendedCeilingUsd (substrate parity default rates) surfaces
moil-ceiling-preview on create form (duration · fanout · tier · $preview · budget fit).
Competitive delta: operator sees recommended price ceiling before autonomous swarm
create — create job remains authoritative. vitest researchTier+MO 32 green.

## Residual ady · 2026-07-10 — model-aware MO ceiling preview offline rates
MO ceiling preview uses substrate DEFAULT_PRICING offline table (gpt-5.5 · glm-5.2 ·
composer-2.5 · mimo-v2.5 · default). Competitive delta: decision-tree model prefill
moves recommended price ceiling preview before create (create remains authoritative).
vitest researchTier+MO 34 green.

## Residual adz · 2026-07-10 — SESSION-ARC adx–ady MO ceiling preview
SESSION-ARC-adx-ady documents live create-form recommended ceiling preview + model-aware
offline rates. Tip 8fe3b551 · swarm handoff tip-true. Competitive delta: multi-agent
infinite continues outside closed MO preview arc; operator merge PR #465 highest leverage.

## Residual aea · 2026-07-10 — marketplace seamless port honesty
Host metrics + marketplace-seamless-port stamp catalog → account library landed →
HTML host → twin seed status. Competitive delta: operator can audit seamless port
of purchased/hosted books into Antiek account (HTML-first · L5 still deferred).
vitest purchase host path green.

## Residual aeb · 2026-07-10 — budget goes-negative foresight + free host seamless
ResearchLaunchBudgetPanel + DecisionTreeDriverBadge stamp data-goes-negative when
high-band projection burns past remaining (soft foresight · not hard block). Free
host path asserts seamless-port library-landed (parity purchase aea). Competitive
delta: operator can machine-read whether a prompt would go over budget before fire.
vitest 62 green (badge 12 · launch 11 · marketplace 39).

## Residual aec · 2026-07-10 — Settings twin seed L3 gate matrix + checklist
Settings twin-seed-live-status panel stamps data-l3-live-ready + per-gate attrs
(live_env · use_dispatch · injector) and Dual-gate L3 twin checklist deep-link.
Competitive delta: operator dual-gate L3 prep is complete on the readiness panel
itself (parity TwinNotes xa · never enables live). vitest Settings 35 green.

## Residual aed · 2026-07-10 — Settings MO L4 gate matrix + checklist
moil-live-step-status panel stamps data-l4-live-ready + per-gate attrs and Dual-gate
L4 MO checklist (#l4-moil). Competitive delta: L4 prep parity with twin L3 aec on
Settings readiness panels (never enables live worker). vitest Settings 35 green.

## Residual aee · 2026-07-10 — hydrate L1/L2 arxiv+substack gate matrix
Publication hydrate readiness panel stamps L1 arxiv + L2 Substack live_ready
composites and Dual-gate L1/L2 checklist deep-links. Competitive delta: knowledge-dense
pub dual-gate prep is complete on Settings (parity L3/L4 aec–aed · never enables live).
vitest Settings 35 green.

## Residual aef · 2026-07-10 — SESSION-ARC aec–aee dual-gate readiness
SESSION-ARC documents L1/L2 hydrate + L3 twin + L4 MO gate matrices on Settings.
Tip af73dccc · swarm handoff tip-true. Competitive delta: multi-agent infinite continues
outside dual-gate readiness thrash; operator merge PR #465 highest leverage.

## Residual aeg · 2026-07-10 — MO preview vs server recommended match audit
Create captures form preview USD; job ceiling metrics stamp data-preview-usd +
data-preview-matches-server (create remains authoritative). Competitive delta:
operator sees when form preview drifts from server ceiling (fanout/model/tier).
vitest MidnightOil 24 green.

## Residual aeh · 2026-07-10 — collective unit prompt Open Write twin_seed
Cohesive unit prompt offers Open Write (unit prompt) with twin_seed source=
collective_unit_prompt · has_body when prompt_block non-empty · L6 deferred stamp.
Competitive delta: multi-spawn collective unit → recursive note-taker Write path
is complete (float|full + Write). vitest CollectiveResearchPanel 25 green.

## Residual aei · 2026-07-10 — engagement Write builders has_body true
Deep research · progress · evidence · publications · flywheel · context search ·
context pack · twin promote storeTwinWriteSeed stamp has_body=true (content-bearing
builders). Competitive delta: recursive rewrite feed is explicit end-to-end for all
engagement Open Write paths (title-only marketplace/merge keep false). vitest twinWriteSeed 34 green.

## Residual aej · 2026-07-10 — Settings decision-tree projection goes-negative
Mini estimate + full prompt-cost-remaining-after stamp data-goes-negative when
high band burns past remaining (soft foresight · parity aeb launch/badge).
Competitive delta: model-picker budget surface is machine-readable for over-cap
foresight end-to-end. vitest Settings 36 green.

## Residual aek · 2026-07-10 — SESSION-ARC aeh–aej collective Write + budget foresight
SESSION-ARC documents unit prompt Write twin_seed, engagement has_body builders,
and Settings decision-tree goes-negative foresight. Tip b1c42e2b · swarm handoff tip-true.
Competitive delta: multi-agent infinite continues outside thrash; operator merge PR #465 highest leverage.

## Residual ael · 2026-07-10 — DR Open Write seamless reading→research→Write
Deep research Open Write stamps data-parent-asset-id · data-seamless-reading-research-write
· data-spawn-id for highlight→float DR→Write path honesty. Competitive delta: operator
can machine-read when DR session is bound to a reading parent asset. vitest DR host 30 green.

## Residual aem · 2026-07-10 — spawn-merge Open Write draft vs into_parent path
SpawnMerge Open Write stamps data-mode · data-draft-leaves-parent · data-parent-asset-id
· data-spawn-id · data-document-id · data-seamless-merge-write so draft_combined vs
into_parent is machine-readable on the Write handoff (not only metrics). Competitive
delta: merge→Write note-taker path honesty parity with ael reading→DR→Write. vitest
SpawnMergePanel 8 green.

## Residual aen · 2026-07-10 — HostedHtml Open Write seamless host→Write
HostedHtmlDocumentHost Open Write stamps data-document-id · data-seamless-host-write
so reading HTML host → Write note-taker path is machine-readable (parity ael/aem).
vitest HostedHtmlDocumentHost 23 green.

## Residual aeo · 2026-07-10 — marketplace Open Write seamless-port
Host + library Open Write stamp data-seamless-port · data-library-landed ·
data-seamless-host-write · has_body so catalog→account→Write path is
machine-readable on the handoff (not only host metrics aea). vitest MarketplaceHost 39 green.

## Residual aep · 2026-07-10 — Midnight Oil deposit Open Write seamless path
moil-open-write stamps data-document-id · data-job-id · data-seamless-moil-write
· data-seamless-host-write so autonomous deposit → Write note-taker is
machine-readable (parity ael–aeo Write path wave). vitest MidnightOil 24 green.

## Residual aeq · 2026-07-10 — collective Open Write draft vs into_parent path
Collective multi-spawn Open Write stamps data-mode · data-draft-leaves-parent ·
data-parent-asset-id · data-spawn-count · data-seamless-merge-write (parity aem
spawn merge). Competitive delta: multi-select merge→Write note-taker path honesty.
vitest CollectiveResearchPanel 25 green.

## Residual aer · 2026-07-10 — SESSION-ARC ael–aeq seamless Write path
Handoff matrix: DR · spawn merge · HostedHtml · marketplace · MO deposit ·
collective Open Write all stamp path honesty. Do not thrash ael–aeq stamps.
Next: aes+ outside this thrash. PR #465 operator merge remains P0.

## Residual aes · 2026-07-10 — intelligent search + context pack Open Write path
ResearchContext Open Write (pack + context-search) stamps asset/spawn/query/tier
· data-seamless-context-write so intelligent search → Write note-taker is
machine-readable. vitest ResearchContextPanel 12 green.

## Residual aet · 2026-07-10 — evidence pack + hydrate Open Write path
Evidence pack Open Write stamps citation-trust · research_tier · seamless-context-write.
Hydrate Open Write stamps offline-honest · fetched · spawn_id. Competitive
citation bar on Write handoff (grounded vs ungrounded). vitest ResearchContext 12 green.

## Residual aeu · 2026-07-10 — Antiek-bench dogfood v14 seamless Write path
Suite bumps to suite-competitive-dogfood-v14 with wrestle fixtures for seamless
Open Write path honesty and intelligent search/evidence → Write. Settings spine
postures v14. Recursive rewrite substrate learns differentiating tasks from ael–aet.
pytest dogfood 5 · Settings 36 green.

## Residual aev · 2026-07-10 — SESSION-ARC aes–aeu context+bench
Handoff: intelligent search/evidence Open Write (aes–aet) + dogfood v14 (aeu).
Do not thrash ael–aeu stamps/version pins. P0 remains operator merge PR #465.

## Residual aew · 2026-07-10 — twin draft + promote Open Write path
TwinNotes draft and promote Open Write stamp data-seamless-twin-write · asset ·
note-count/promoted · research_tier so recursive note-taker → Write is
machine-readable. vitest TwinNotesPanel 30 green.

## Residual aex · 2026-07-10 — research progress + session flywheel Open Write path
Progress Open Write stamps spawn · progress-source · seamless-progress-write.
Flywheel Open Write stamps session/spawn · seamless-flywheel-write. Plan→cite
and session complete → Write note-taker path honesty. vitest 15 green.

## Residual aey · 2026-07-10 — SESSION-ARC ael–aex Open Write path complete
Full matrix of Open Write path honesty closed (DR→merge→host→marketplace→MO→
collective→context→evidence→twins→progress/flywheel) + dogfood v14. Pivot aez+
outside path thrash. P0 operator merge PR #465.

## Residual aez · 2026-07-10 — Settings L7 ND never-router gate matrix
NotDiamond advisory panel gains L7 gate matrix (advisory_allowed · authority_rejected
· is_dispatch_authority · never_router_posture) parity with L1–L4. Router remains
forever REJECT; install-as-driver stays explicit. vitest Settings 36 green.

## Residual afa · 2026-07-10 — collective unit prompt Open Write path
Collective unit Open Write stamps data-seamless-unit-write · parent_asset_id ·
research_tier so multi-select cohesive unit → Write note-taker is machine-readable
(parity aeq doc merge). L6 live multi-agent remains deferred. vitest Collective 25 green.

## Residual afb · 2026-07-10 — launch budget Antiek-bench best-by-task advisory
ResearchLaunchBudgetPanel surfaces weekly best model for depth→task_class
(fast→distill · deep→synthesize · wrestle→wrestle) vs installed driver.
Advisory only · never auto-routes. Competitive model-quality-per-task at fire.
vitest ResearchLaunchBudgetPanel 12 green.

## Residual afc · 2026-07-10 — DecisionTreeDriverBadge best-by-task advisory
Driver badge on reading/research hosts surfaces Antiek-bench weekly best model
for depth→task_class (parity launch afb). Advisory only · never auto-routes.
vitest DecisionTreeDriverBadge 12 green.

## Residual afd · 2026-07-10 — SESSION-ARC afb–afc model quality at fire
Handoff: Antiek-bench best-by-task advisory at launch (afb) and driver badge
(afc). Advisory only. P0 operator merge PR #465. Pivot afe+ outside thrash.

## Residual afe · 2026-07-10 — install best-for-task from driver badge
When Antiek-bench best-for-task differs from installed driver, badge offers
explicit Install best for {task} (operator click · never auto-route). Completes
model-quality-at-fire loop (ads→afb→afc→afe). vitest DecisionTreeDriverBadge 12 green.

## Residual aff · 2026-07-10 — launch budget install best-for-task
ResearchLaunchBudgetPanel Install best for {task} when bench best differs from
installed driver (parity badge afe). Explicit operator action · never auto-route.
Model-quality-at-fire loop complete at launch + badge. vitest launch budget 12 green.

## Residual afg · 2026-07-10 — written analysis Open Write source honesty
Create written analysis Open Write now stamps twin_seed source=
collective_written_analysis (was incorrectly collective_doc_merge). Competitive
multi-spawn analysis → Write note-taker feed is honest. vitest Collective 25 +
twinWriteSeed 35 green.

## Residual afh · 2026-07-10 — continue-as-unit path honesty
Continue cohesive unit (float|full) stamps data-collective-id · parent_asset_id ·
spawn-count · seamless-unit-continue so multi-select unit re-entry → DR is
machine-readable (parity ael DR parent path). L6 live multi-agent still deferred.
vitest CollectiveResearchPanel 25 green.

## Residual afi · 2026-07-10 — Antiek-bench dogfood v15 collective path fixtures
Suite bumps to suite-competitive-dogfood-v15 with wrestle fixtures for written
analysis Open Write source honesty (afg) and continue-as-unit path (afh).
Settings spine postures v15. pytest dogfood 5 · Settings 36 green.

## Residual afj · 2026-07-10 — SESSION-ARC afg–afi collective multi-spawn path
Handoff: written analysis Open Write source fix + continue-as-unit path stamps +
dogfood v15. P0 operator merge PR #465. Pivot afk+ outside thrash.

## Residual afk · 2026-07-10 — continue-as-unit window path audit
Post-continue window status stamps collective_id · parent · seamless-unit-continue
· L6 deferred + offline re-entry copy. Closes unit→DR audit loop after afh.
vitest CollectiveResearchPanel 25 green.

## Residual afl · 2026-07-10 — restore last unit path honesty
Restore last unit button + membership status stamp data-seamless-unit-restore
(and L6 deferred). Closes multi-select unit membership re-open loop with
continue-as-unit (afh/afk). vitest Collective 25 green.

## Residual afm · 2026-07-10 — SESSION-ARC afg–afl collective multi-spawn complete
Full multi-select unit loop: written analysis Open Write source · continue-as-unit
· window audit · restore membership · dogfood v15. P0 operator merge PR #465.
Pivot afn+ outside thrash.

## Residual afn · 2026-07-10 — Select open path honesty
Select open control stamps data-seamless-select-open · view_format=html ·
open-in-available · L6 deferred. After click: last-select-mode=open on controls
+ selection count + path status (parent_asset_id · seamless select open copy).
Multi-spawn assembly open-window path is machine-readable (parity afl restore).
vitest CollectiveResearchPanel 26 green.

## Residual afo · 2026-07-10 — dogfood v16 select-open + unit-restore
Suite suite-competitive-dogfood-v16 adds wrestle fixtures for Select open path
(afn) and restore last unit path (afl). Settings spine postures v16 + summary
attrs. pytest dogfood 5 · Settings 36 green. propose≠promote.

## Residual afp · 2026-07-10 — Select recent path honesty
Select recent control stamps data-seamless-select-recent · view_format=html ·
recent-in-available · L6 deferred. After click: last-select-mode=recent on
controls + selection count + path status (parity Select open afn). Twin-chase
closed-window multi-select assembly path is machine-readable.
vitest CollectiveResearchPanel 27 green.

## Residual afq · 2026-07-10 — SESSION-ARC afn–afp multi-select assembly
Handoff: Select open path · dogfood v16 · Select recent path. Multi-select
assembly matrix (open|recent|restore) complete offline. P0 operator merge
PR #465. Pivot afr+ outside thrash.

## Residual afr · 2026-07-10 — ResearchWorkstation collective multi-select
/inv/:id InvestigationCenter mounts CollectiveResearchPanel when open or
recent deep_research_session spawns exist (openSpawnIds · recent_ring · parent=
investigationId). Reading ≡ research workstation multi-select assembly.
vitest ResearchWorkstation collective 3 + feel 3 green.

## Residual afs · 2026-07-10 — ResearchWorkstation twin note-taker
/inv/:id InvestigationCenter always mounts TwinNotesPanel (autoLoad ·
autoSeedIfEmpty · seed from investigation.question). Recursive note-taker
substrate on research workstation (parity DR/hosted). vitest RW 8 green.

## Residual aft · 2026-07-10 — RW ResearchContext + twin auto-promote
/inv/:id mounts ResearchContextPanel (autoLoad) and TwinNotes autoPromoteAfterLoad
with shared contextRefreshKey remount (parity DR ea/ec). Intelligent search over
twin substrate on research workstation. vitest RW 10 green.

## Residual afu · 2026-07-10 — SESSION-ARC afr–aft ResearchWorkstation spine
Handoff: collective multi-select · TwinNotes · ResearchContext+autoPromote on
/inv/:id. Reading ≡ research workstation offline spine complete. P0 operator
merge PR #465. Pivot afv+ outside thrash.

## Residual afv · 2026-07-10 — dogfood v17 select-recent + RW spine
Suite suite-competitive-dogfood-v17 adds wrestle fixtures for Select recent
path (afp) and ResearchWorkstation spine (afr–aft). Settings spine postures
v17. pytest dogfood 5 · Settings 36 green. propose≠promote.

## Residual afw · 2026-07-10 — highlight → DR float|full path honesty
FloatMenu Deep-research / Deep-research full stamp data-seamless-highlight-dr
· view-mode · view-format=html so highlight→floating/full deep research path is
machine-readable (shared Read/Research FloatMenu host). vitest FloatMenu 25 green.

## Residual afx · 2026-07-10 — highlight → DR window payload path honesty
openDeepResearchFromHighlight stamps payload.seamless_highlight_dr=true;
launchFloatingDeepResearch result seamless_highlight_dr; host surfaces
data-seamless-highlight-dr (parity FloatMenu afw). vitest window 5 + launch 7 green.

## Residual afy · 2026-07-10 — SESSION-ARC afw–afx highlight DR path
Handoff: FloatMenu seamless-highlight-dr + window payload + host stamp.
End-to-end highlight→floating/full deep research path honesty. P0 operator
merge PR #465. Pivot afz+ outside thrash.

## Residual afz · 2026-07-10 — dogfood v18 highlight→DR path
Suite suite-competitive-dogfood-v18 adds wrestle fixture for highlight→floating
deep research path honesty (afw–afx). Settings spine postures v18. pytest
dogfood 5 · Settings 36 green. propose≠promote.

## Residual aga · 2026-07-10 — highlight → Search path honesty
FloatMenu Search control stamps data-seamless-highlight-search · view_format=html;
SearchPanel surfaces same + hit-count/pending/withheld audit. Highlight→corpus
search path machine-readable (parity highlight→DR afw). vitest FloatMenu 26 green.

## Residual agb · 2026-07-10 — highlight Note+Dialogue path honesty
FloatMenu Note and Dialogue stamp data-seamless-highlight-note|dialogue ·
view_format=html. Completes highlight float-menu action path matrix
(Note · Dialogue · Search · Deep-research float|full). vitest FloatMenu 27 green.

## Residual agc · 2026-07-10 — SESSION-ARC afw–agb FloatMenu highlight path
Handoff: Deep-research path + dogfood v18 + Search + Note + Dialogue. Full
highlight FloatMenu path honesty matrix. P0 operator merge PR #465.
Pivot agd+ outside thrash.

## Residual agd · 2026-07-10 — SESSION-ARC afn–agc infinite continuation
Full wave handoff: multi-select assembly · ResearchWorkstation spine · FloatMenu
highlight path · dogfood v16–v18. P0 operator merge PR #465. Pivot age+ outside thrash.

## Residual age · 2026-07-10 — RW dual-gate L3/L6 checklist prep
/inv/:id mounts dual-gate prep nav with L3 twin seed + L6 collective checklist
deep-links (deferred injectors · offline-honest). Parity MO/marketplace
checklist surfaces. vitest RW 12 green.

## Residual agf · 2026-07-10 — StartResearch L1/L2 dual-gate pub-refs prep
StartResearch publication refs panel mounts dual-gate L1 arxiv + L2 Substack
checklist deep-links (deferred injectors · offline identity default). Parity
MO/HostedHtml pub prep. vitest StartResearch 21 green.

## Residual agg · 2026-07-10 — ChatInputArea L1/L2 dual-gate pub-refs prep
Docked chat publication refs mount dual-gate L1 arxiv + L2 Substack checklist
deep-links (parity StartResearch agf · chase follow-ups). Fixed fetchDepthTiers
mock in refs tests. vitest ChatInputArea.refs 3 green.

## Residual agh · 2026-07-10 — free STEM Gödel incompleteness PD + dogfood v19
Marketplace free HTML PD catalog adds pd-godel-incompleteness (foundations ·
logic · computability). Antiek-bench dogfood v19 book_qa for Gödel. free_pd
floor ≥18 · free computing ≥5. pytest marketplace+dogfood · Settings 36 green.

## Residual agi · 2026-07-10 — highlight Note panel save path honesty
FloatMenu Note panel stamps data-seamless-highlight-note · data-note-saved before
and after save; saved chrome stamps data-source-kind=user. Completes highlight
→ recursive note-taker path for human marginalia. vitest FloatMenu 27 green.

## Residual agj · 2026-07-10 — highlight Dialogue panel path honesty
FloatMenu Dialogue panel stamps data-seamless-highlight-dialogue · dialogue-status
idle|pending|replied|failure; model reply stamps data-source-kind=model. Failure
path chrome separate. Completes highlight dialogue path with Note save (agi).
vitest FloatMenu 28 green.

## Residual agk · 2026-07-10 — SESSION-ARC agh–agj free STEM + panels
Handoff: Gödel free PD + dogfood v19 · Note save path · Dialogue path.
P0 operator merge PR #465. Pivot agl+ outside thrash.

## Residual agl · 2026-07-10 — marketplace foundations + Gödel catalog honesty
Marketplace catalog metrics stamp data-foundations-count · data-has-godel-pd and
show foundations=N copy. Foundations subject chip filters to Gödel free PD HTML.
vitest MarketplaceHost foundations test green.

## Residual agm · 2026-07-10 — TalkToBook TwinNotes recursive note-taker
TalkToBook open panel mounts TwinNotesPanel for documentId (autoLoad ·
autoSeedIfEmpty · seed from title). Book assets get twin insights/questions
substrate while talking (reading ≡ research · recursive note-taker).
vitest TalkToBook 10 green.

## Residual agn · 2026-07-10 — MetaReading TwinNotes recursive note-taker
Meta-reading deliverable mounts TwinNotesPanel for asset_id (autoLoad ·
autoSeedIfEmpty · seed from prompt/report). Corpus synthesis assets get twin
insights/questions substrate (parity TalkToBook agm). vitest MetaReading 13 green.

## Residual ago · 2026-07-10 — SESSION-ARC agm–agn reading twins
Handoff: TalkToBook + MetaReading TwinNotes recursive note-taker. Reading
surface twins complete offline. P0 operator merge PR #465. Pivot agp+ outside thrash.

## Residual agp · 2026-07-10 — dogfood v20 reading twins fixtures
Suite suite-competitive-dogfood-v20 adds wrestle fixtures for TalkToBook twins
(agm) and MetaReading twins (agn). Settings spine postures v20. pytest dogfood 5 ·
Settings 36 green. propose≠promote.

## Residual agq · 2026-07-10 — ResearchThis TwinNotes recursive note-taker
ResearchThis mounts TwinNotesPanel for documentId while spinning deep research
(autoLoad · autoSeedIfEmpty · seed from selection). Book DR launch surface gets
twin substrate (parity TalkToBook/MetaReading). vitest ResearchThis 13 green.

## Residual agr · 2026-07-10 — SESSION-ARC agm–agq reading twins matrix
Handoff: TalkToBook · MetaReading · ResearchThis TwinNotes + dogfood v20.
Reading twins matrix complete offline. P0 operator merge PR #465.
Pivot ags+ outside thrash.

## Residual ags · 2026-07-10 — free STEM Fourier heat PD + dogfood v21
Marketplace free HTML PD catalog adds `pd-fourier-heat` (Analytical Theory of Heat ·
heat · signal_processing · engineering). Antiek-bench dogfood v21 adds
`dogfood-book-fourier-heat` + `dogfood-wrestle-research-this-twins`. free_pd floor
≥19 · item_count 33 · book_qa=9 · wrestle=20. Settings spine postures v21.
Fixed highlight-path posture `.some()` corruption. pytest 41 · Settings 36 green.
P0 operator merge PR #465. Pivot agt+ outside thrash.

## Residual agt · 2026-07-10 — marketplace heat/signal_processing Fourier honesty
MarketplaceHost catalog metrics stamp data-heat-count · data-signal-processing-count ·
data-has-fourier-pd after free STEM Fourier (ags). Subject chips filter heat +
signal_processing. Parity foundations/Gödel agl. vitest MarketplaceHost 41 green.
P0 operator merge PR #465. Pivot agu+ outside free-STEM thrash.

## Residual agu · 2026-07-10 — seamless highlight→DR→merge path honesty
SpawnMergePanel + DeepResearchSessionHost mount stamp data-seamless-spawn-merge ·
data-seamless-highlight-dr-merge when spawn+parent reading asset bound. Draft vs
into_parent action stamps. Completes offline path honesty for highlight float DR
→ merge into reading asset / draft-combined. vitest SpawnMerge 8 · DR host 30 green.
P0 operator merge PR #465. Pivot agv+ outside thrash.

## Residual agv · 2026-07-10 — seamless multi-spawn collective merge path honesty
CollectiveResearchPanel stamps data-seamless-collective-merge · multi-spawn-merge ·
merge-ready when parent reading asset bound (+ ≥1 selected for ready). Draft /
into_parent / written-analysis action stamps. Parity single-spawn agu for
multi-select subagent merge flywheel (vision: merge various deep researches).
vitest Collective 27 green. P0 operator merge PR #465. Pivot agw+ outside thrash.

## Residual agw · 2026-07-10 — dogfood v22 seamless merge path fixtures
Suite suite-competitive-dogfood-v22 adds wrestle fixtures for single-spawn
highlight→DR→merge (agu) and multi-spawn collective merge (agv). Settings spine
postures v22. item_count 35 · wrestle=22 · book_qa=9. Recursive Antiek-bench
rewrite feed (propose≠promote). pytest dogfood 5 · Settings 36 green.
P0 operator merge PR #465. Pivot agx+ outside thrash.

## Residual agx · 2026-07-10 — knowledge-dense publication quick-call presets
PublicationAttachPanel adds curated arxiv/URL quick-call chips (Attention, BERT,
GPT-3, Scaling laws, Lilian Weng, LessWrong example). Insert-only · never
auto-hydrate · data-auto-hydrate=false · offline-honest until Attach + hydrate.
Competitive delta: one-click call knowledge-dense pubs into deep research
(parity competitor source connectors UX without inventing live bodies).
vitest PublicationAttach 6 green. P0 operator merge PR #465. Pivot agy+ outside thrash.

## Residual agy · 2026-07-10 — StartResearch knowledge-dense pub quick-call
StartResearch publication-refs panel mounts shared KNOWLEDGE_DENSE_PUBLICATION_PRESETS
(parity PublicationAttach agx). Quick-call chips insert arxiv/URL with dedupe ·
data-auto-hydrate=false. Launch-path one-click knowledge-dense refs for deep
research Ask. vitest StartResearch 22 green. P0 operator merge PR #465.

## Residual SESSION-ARC ags–agy · 2026-07-10
Wave handoff: Fourier free STEM · heat metrics · seamless single+multi merge ·
dogfood v22 · pub quick-call launch+mid-session. See
SESSION-ARC-ags-agy-fourier-merge-pub-quickcall.md. Pivot agz+ outside thrash.

## Residual agz · 2026-07-10 — ChatInputArea knowledge-dense pub quick-call
Docked chat chase follow-ups mount shared KNOWLEDGE_DENSE_PUBLICATION_PRESETS
(parity StartResearch agy · PublicationAttach agx). Completes launch + mid-session
+ chase quick-call matrix for knowledge-dense arxiv/URL refs. Insert-only · offline
hydrate. vitest ChatInputArea.refs 4 green. P0 operator merge PR #465. Pivot aha+.

## Residual aha · 2026-07-10 — HostedHtml knowledge-dense pub quick-call
Hosted book deep-research ground-with-pubs mounts shared quick-call presets
(parity launch/chase/attach). Reading ≡ research: Fourier free STEM HTML books
can one-click ground float DR with arxiv handles. Insert-only · offline hydrate.
vitest HostedHtml 23 green. P0 operator merge PR #465. Pivot ahb+ outside thrash.

## Residual ahb · 2026-07-10 — marketplace host DR knowledge-dense pub quick-call
MarketplaceHost host-land DR ground-with-pubs mounts shared quick-call presets
(parity hosted aha). Completes knowledge-dense pub quick-call matrix across
launch · chase · mid-session · hosted book · marketplace free STEM.
vitest MarketplaceHost 41 green. See SESSION-ARC-agx-ahb-pub-quickcall-matrix.md.
P0 operator merge PR #465. Pivot ahc+ outside thrash.

## Residual ahc · 2026-07-10 — ResearchThis knowledge-dense pub quick-call
Highlight → Research this passage ground-with-pubs mounts shared quick-call
presets (parity hosted aha · marketplace ahb). Completes reading highlight DR
path in knowledge-dense pub matrix. vitest ResearchThis 13 green.
P0 operator merge PR #465. Pivot ahd+ outside pub-matrix thrash.

## Residual ahd · 2026-07-10 — dogfood v23 knowledge-dense pub quick-call matrix
Suite suite-competitive-dogfood-v23 adds wrestle fixture for the full
knowledge-dense publication quick-call matrix (agx–ahc). Settings spine v23.
item_count 36 · wrestle=23. Recursive Antiek-bench rewrite feed.
pytest dogfood 5 · Settings 36 green. P0 operator merge PR #465.
Pivot ahe+ outside thrash.

## Residual ahe · 2026-07-10 — marketplace paid purchase+host seamless port honesty
Purchase + host buttons stamp data-seamless-purchase-port · L5 deferred ·
live_payment=false · HTML view · manual_receipt_only · receipt-required.
Host land metrics stamp purchased-path for non-PD books. Competitive delta:
digital book buy → seamless Antiek HTML account port without inventing live
checkout rails. vitest MarketplaceHost 41 green. P0 operator merge PR #465.
Pivot ahf+ outside thrash.

## Residual ahf · 2026-07-10 — FUTURE-AGENT L5 digital book seamless port spec
Executable brief for paid digital book → HTML account port when L5 unlocks.
Builds on ahe offline purchase path honesty. Does not invent live checkout.
P0 operator merge PR #465. Pivot ahg+ offline product residual.

## Residual ahg · 2026-07-10 — StartResearch budget foresight pub-ref count
countPublicationRefs + start-research-budget-foresight stamps data-pub-ref-count
after knowledge-dense quick-call. Competitive budget-before-fire honesty when
grounding research with arxiv/URL refs. vitest StartResearch 23 green.
P0 operator merge PR #465. Pivot ahh+.

## Residual ahh · 2026-07-10 — ChatInputArea budget foresight pub-ref count
Chase follow-up budget mount stamps data-pub-ref-count after knowledge-dense
quick-call (parity StartResearch ahg). vitest ChatInputArea.refs green.
P0 operator merge PR #465. Pivot ahi+.

## Residual ahi · 2026-07-10 — ResearchThis budget foresight pub-ref count
Highlight Research-this budget mount stamps data-pub-ref-count after knowledge-dense
quick-call (parity launch ahg · chase ahh). Completes foresight matrix for
budget-before-fire with multi-source grounding. vitest ResearchThis green.
P0 operator merge PR #465. Pivot ahj+ outside thrash.

## Residual ahj · 2026-07-10 — SESSION-ARC ags–ahi wave handoff
17 residuals: Fourier free STEM · seamless merge paths · knowledge-dense pub
quick-call matrix · paid purchase port honesty · L5 FUTURE brief · budget
foresight pub-ref counts. P0 operator merge PR #465. Pivot ahk+ outside thrash.

## Residual ahk · 2026-07-10 — FUTURE-AGENT L6 live multi-agent collective spec
Executable brief for live multi-agent collective council when dual-gate unlocks.
Anchors offline merge unit (agv · written analysis · continue-as-unit). Does not
invent live injectors. P0 operator merge PR #465. Pivot ahl+ offline product.

## Residual ahl · 2026-07-10 — HostedHtml budget foresight pub-ref count
Hosted free STEM book DR depth mount stamps data-pub-ref-count after knowledge-dense
quick-call (parity ResearchThis ahi). vitest HostedHtml green.
P0 operator merge PR #465. Pivot ahm+ outside thrash.

## Residual ahm · 2026-07-10 — MarketplaceHost DR budget foresight with pub refs
Host-land DR budget panel uses composeDriverPromptText with knowledge-dense
pub refs; mount stamps data-pub-ref-count. Completes foresight matrix for free
STEM marketplace path. vitest MarketplaceHost green. P0 operator merge PR #465.
Pivot ahn+ outside thrash.

## Residual ahn · 2026-07-10 — dogfood v24 budget foresight + purchase seamless port
Suite suite-competitive-dogfood-v24 adds wrestle fixtures for budget foresight
with multi-source pubs (ahg–ahm) and paid purchase seamless port honesty (ahe).
item_count 38 · wrestle=25. Settings spine v24. pytest dogfood 5 · Settings 36 green.
P0 operator merge PR #465. Pivot aho+ outside thrash.

## Residual aho · 2026-07-10 — twin seed free/purchased port honesty
Marketplace seedHostedTwins body prefixes free PD vs purchased manual-receipt
port honesty so recursive note-taker substrate records path without inventing
L5 rails. vitest MarketplaceHost 41 green. P0 operator merge PR #465. Pivot ahp+.

## Residual ahp · 2026-07-10 — countPublicationRefs unit tests
driverPromptText.test.ts covers countPublicationRefs non-empty line counting
used by budget foresight (ahg–ahm). vitest driverPromptText green.
P0 operator merge PR #465. Pivot ahq+.

## Residual ahq · 2026-07-10 — FUTURE-AGENT twin note-taker completeness matrix
Maps recursive note-taker mounts across reading/research/write/marketplace and
names offline product gaps (MO deposit twin · domain-aware twin search · unit
float twin). L3 live remains dual-gate. P0 operator merge PR #465. Pivot ahr+.

## Residual ahr · 2026-07-10 — domain-aware twin intelligent search default
ResearchContextPanel prefills intelligent search from domain subjects (heat /
signal_processing for Fourier free STEM). Marketplace host openWindow passes
catalog subjects into HostedHtml twin context. Completes twin completeness gap
#3 from ahq. vitest ResearchContext 14 · Marketplace 41 · HostedHtml 23 green.
P0 operator merge PR #465. Pivot ahs+.

## Residual ahs · 2026-07-10 — dogfood v25 domain-aware twin intelligent search
Suite suite-competitive-dogfood-v25 adds wrestle fixture for domain-aware twin
search (ahr). item_count 39 · wrestle=26. Settings spine v25.
pytest dogfood 5 · Settings 36 green. P0 operator merge PR #465. Pivot aht+.

## Residual aht · 2026-07-10 — collective unit HTML float/full offline twin seed
Opening multi-spawn cohesive unit as float|full HTML seeds recursive note-taker
twins offline (force_offline · L6 never invented). Closes twin completeness gap
#2 (ahq). vitest Collective 27 green. P0 operator merge PR #465. Pivot ahu+.

## Residual ahu · 2026-07-10 — Midnight Oil deposit twin seed port honesty
MO deposit twin reseed body prefixes offline deposit HTML port honesty (L4 live
worker dual-gate deferred). Closes twin completeness gap #1 without inventing
live multi-provider step. vitest MidnightOil 24 green. P0 operator merge PR #465.
Pivot ahv+.

## Residual ahv · 2026-07-10 — SESSION-ARC ahq–ahu twin completeness gaps closed
Twin matrix gaps closed offline: MO deposit honesty (ahu) · collective unit twin
seed (aht) · domain-aware twin search (ahr/ahs). P0 operator merge PR #465.
Pivot ahw+ outside thrash.

## Residual ahw · 2026-07-10 — FUTURE-AGENT NotDiamond advisory-only verdict
Executable reaffirmation: NotDiamond useful as advisor, never as router (L7).
Operator decision-tree + budget foresight remain product control surfaces.
P0 operator merge PR #465. Pivot ahx+.

## Residual ahx · 2026-07-10 — SESSION-ARC ags–ahw infinite continuation handoff
31 residual wave: Fourier STEM · merge paths · pub quick-call · budget foresight ·
purchase port · twin completeness · NotDiamond advisory-only. P0 operator merge
PR #465. Pivot ahy+ outside thrash.

## Residual ahy · 2026-07-10 — Settings L7 FUTURE-AGENT ND advisory-only deep-link
NotDiamond L7 prep nav links FUTURE-AGENT-SPEC-notdiamond-advisory-only.md so
operators reach advisory-only / never-router verdict from Settings. vitest
Settings 36 green. P0 operator merge PR #465. Pivot ahz+.

## Residual ahz · 2026-07-10 — Settings deferred map FUTURE-AGENT L5/L6 deep-links
Deferred map L5/L6 rows link FUTURE-AGENT digital book port + live multi-agent
council briefs. Completes Settings navigation for L5–L7 FUTURE-AGENT doctrine.
vitest Settings 36 green. P0 operator merge PR #465. Pivot aia+.

## Residual aia · 2026-07-10 — Settings deferred twin FUTURE-AGENT matrix deep-link
Deferred map links FUTURE-AGENT twin note-taker completeness matrix. Completes
Settings chokepoint navigation for L5/L6/L7/twin FUTURE-AGENT doctrine.
vitest Settings 36 green. P0 operator merge PR #465. Pivot aib+.

## Residual aib · 2026-07-10 — dogfood v26 collective unit twin + MO deposit twin honesty
Suite suite-competitive-dogfood-v26 adds wrestle fixtures for collective unit
HTML twin seed (aht) and MO deposit twin honesty (ahu). item_count 41 · wrestle=28.
Settings spine v26. pytest dogfood 5 · Settings 36 green. P0 operator merge PR #465.
Pivot aic+ outside thrash.

## Residual aic · 2026-07-10 — StartResearch pub-ref foresight chrome
Operator-visible chrome when knowledge-dense pubs are in the budget projection
(N refs · chars · soft budget below). Competitive budget-before-fire UX for
multi-source grounding. vitest StartResearch green. P0 operator merge PR #465.
Pivot aid+.

## Residual aid · 2026-07-10 — ChatInputArea pub-ref foresight chrome
Chase follow-up shows operator-visible knowledge-dense pub count chrome above
budget panel (parity StartResearch aic). vitest ChatInputArea.refs green.
P0 operator merge PR #465. Pivot aie+.

## Residual aie · 2026-07-10 — ResearchThis pub-ref foresight chrome
Highlight Research-this shows operator-visible knowledge-dense pub chrome
(parity launch aic · chase aid). Completes foresight chrome matrix.
vitest ResearchThis green. P0 operator merge PR #465. Pivot aif+.

## Residual aif · 2026-07-10 — HostedHtml + MarketplaceHost pub-ref foresight chrome
Hosted free STEM book DR and marketplace host-land DR show operator-visible
knowledge-dense pub chrome (N refs · chars · soft budget below). Completes
foresight chrome matrix with launch/chase/highlight. vitest HostedHtml 23 ·
MarketplaceHost 41 green. P0 operator merge PR #465. Pivot aig+ outside thrash.

## Residual aig · 2026-07-10 — dogfood v27 pub-ref foresight chrome matrix
Suite suite-competitive-dogfood-v27 adds wrestle fixture for operator-visible
pub-ref foresight chrome matrix (aic–aif). item_count 42 · wrestle=29.
Settings spine v27. pytest dogfood 5 · Settings 36 green. P0 operator merge PR #465.
Pivot aih+ outside thrash.

## Residual aih · 2026-07-10 — FUTURE-AGENT competitive deep-research quality brief
Executable brief mapping competitor DR patterns to Antiek spine, naming offline
next residuals (citation chain UI · wrestle progress · quality scorecard) and
dual-gate live table. P0 operator merge PR #465. Pivot aii+ offline competitive product.

## Residual aii · 2026-07-10 — Settings competitive DR quality scorecard
Settings surfaces honest competitive DR scorecard (shipped vs deferred vs never).
Operators see multi-agent merge, budget foresight, source connectors shipped
offline; live hydrate/MO/council deferred; ND never router. Links FUTURE-AGENT
competitive brief. vitest Settings 36 green. P0 operator merge PR #465. Pivot aij+.

## Residual aij · 2026-07-10 — evidence pack citation chain honesty
Evidence pack surfaces citation chain chrome: insights→questions→source refs
with data-chain-complete and multi-hop grounding copy when insights+refs present.
Competitive citation-required synthesis honesty. vitest ResearchContext 14 green.
P0 operator merge PR #465. Pivot aik+.

## Residual aik · 2026-07-10 — scorecard citation chain + SESSION-ARC competitive DR
Settings scorecard citation-trust row names citation chain (aij). SESSION-ARC
aih–aij competitive DR quality wave. P0 operator merge PR #465. Pivot ail+.

## Residual ail · 2026-07-10 — dogfood v28 citation chain + competitive DR scorecard
Suite suite-competitive-dogfood-v28 adds wrestle fixtures for citation chain
(aij) and Settings competitive DR scorecard (aii). item_count 44 · wrestle=31.
Settings spine v28. pytest dogfood 5 · Settings 36 green. P0 operator merge PR #465.
Pivot aim+ outside thrash.

## Residual aim · 2026-07-10 — progress panel competitive DR scorecard deep-link
Multi-minute ResearchProgressPanel links Settings competitive DR scorecard so
long-horizon wrestle jobs navigate world-class DR honesty map (aii). vitest
ResearchProgress green. P0 operator merge PR #465. Pivot ain+.

## Residual ain · 2026-07-10 — SESSION-ARC aif–aim foresight + competitive DR
Wave handoff: pub-ref foresight chrome matrix complete · competitive DR quality
brief · Settings scorecard · citation chain · progress deep-link · dogfood v27–v28.
P0 operator merge PR #465. Pivot aio+ outside thrash.

## Residual aio · 2026-07-10 — TwinNotes FUTURE matrix + competitive scorecard deep-links
Recursive note-taker TwinNotesPanel links FUTURE-AGENT twin completeness matrix
and Settings competitive DR scorecard. vitest TwinNotes green. P0 operator merge
PR #465. Pivot aip+.

## Residual aip · 2026-07-10 — decision-tree dual-gate prep competitive scorecard link
Settings decision-tree dual-gate prep strip links competitive DR scorecard.
Model choice chokepoint navigates world-class DR honesty map. vitest Settings 36 green.
P0 operator merge PR #465. Pivot aiq+.

## Residual aiq · 2026-07-10 — SESSION-ARC aim–aip navigation deep-links
Handoff for competitive DR scorecard navigation from progress, TwinNotes, and
decision-tree dual-gate prep. P0 operator merge PR #465. Pivot air+ outside thrash.

## Residual air · 2026-07-10 — multi-hop claim→source evidence pack navigation
Evidence pack substrate emits ordered citation_chain hops (insights → questions →
sources) with stable anchors and chain_complete. ResearchContextPanel renders
navigable hop stages (#anchor links). Never invents supported_by edges.
pytest evidence 4 · vitest ResearchContext 14 green. P0 operator merge PR #465.
Pivot ais+ outside thrash.

## Residual ais · 2026-07-10 — dogfood v29 multi-hop citation chain hops
Suite suite-competitive-dogfood-v29 adds wrestle fixture for multi-hop hop
navigation (air). Settings v29 postures + scorecard names multi-hop hops.
item_count 45 · wrestle=32. pytest dogfood 5 · Settings 36 green.
P0 operator merge PR #465. Pivot ait+ outside thrash.

## Residual ait · 2026-07-10 — evidence pack competitive DR scorecard deep-links
ResearchContext evidence pack deep-links Settings competitive DR scorecard and
FUTURE-AGENT competitive DR brief; hop strip links multi-hop hops row (air/ais).
Parity progress/TwinNotes/decision-tree scorecard navigation. vitest
ResearchContext 14 green. SESSION-ARC air–ait. P0 operator merge PR #465.
Pivot aiu+ outside thrash.

## Residual aiu · 2026-07-10 — Midnight Oil competitive DR scorecard deep-links
Autonomous swarm mode navigates Settings competitive DR scorecard + FUTURE brief
so operators see offline MO shipped vs L4 live deferred honesty before goals+ceiling.
vitest MidnightOil 25 green. P0 operator merge PR #465. Pivot aiv+ outside thrash.

## Residual aiv · 2026-07-10 — CollectiveResearchPanel competitive DR scorecard deep-links
Multi-agent merge unit navigates Settings competitive DR scorecard + FUTURE brief
(offline merge shipped · L6 live deferred). SESSION-ARC ait–aiv scorecard navigation
matrix complete. vitest Collective 28 green. P0 operator merge PR #465. Pivot aiw+.

## Residual aiw · 2026-07-10 — HostedHtml evidence pack multi-hop hop honesty
Float/full evidence pack windows stamp chain_complete + hop-strip honesty from
HTML projection and deep-link competitive DR scorecard (air reading surface).
vitest HostedHtml 24 green. P0 operator merge PR #465. Pivot aix+ outside thrash.

## Residual aix · 2026-07-10 — SpawnMergePanel competitive DR scorecard deep-links
Highlight→DR→merge path navigates Settings competitive DR scorecard + FUTURE brief
(offline spawn merge shipped · L6 live deferred). Scorecard navigation matrix
includes spawn merge (aix). vitest SpawnMerge 8 green. P0 operator merge PR #465.
Pivot aiy+ outside thrash.

## Residual aiy · 2026-07-10 — domain-aware twin search biology/method/physics/math
domainAwareSearchDefault expands free STEM subject defaults beyond Fourier/Gödel
electricity spine for Origin/Hooke/Novum/Principia/Euclid twin intelligent search.
vitest ResearchContext 14 green. P0 operator merge PR #465. Pivot aiz+ outside thrash.

## Residual aiz · 2026-07-10 — collective unit float twin seed path honesty
HostedHtml collective_unit_prompt stamps twin seed Port path honesty (multi-spawn ·
L6 deferred · no invented doc id) + scorecard/twin matrix deep-links. FUTURE twin
matrix gap #2 shipped offline. vitest HostedHtml 24 green. P0 operator merge PR #465.
Pivot aja+ outside thrash.

## Residual aja · 2026-07-10 — SESSION-ARC air–aiz multi-hop twin scorecard wave
Wave handoff documents multi-hop hops · dogfood v29 · scorecard navigation matrix ·
domain-aware STEM twin search · collective unit twin seed. P0 operator merge PR #465.
Pivot ajb+ outside thrash.

## Residual ajb · 2026-07-10 — dogfood v30 domain-aware STEM expanded
Suite suite-competitive-dogfood-v30 learns expanded domainAwareSearchDefault
(biology/method/physics/math from aiy). item_count 46 · wrestle=33. pytest dogfood 5 ·
Settings 36 green. P0 operator merge PR #465. Pivot ajc+ outside thrash.

## Residual ajc · 2026-07-10 — PublicationAttach competitive DR scorecard deep-links
Knowledge-dense arxiv/substack attach navigates Settings competitive DR scorecard +
FUTURE brief (source quick-call shipped · L1/L2 live hydrate deferred). vitest
PublicationAttach 6 green. P0 operator merge PR #465. Pivot ajd+ outside thrash.

## Residual ajd · 2026-07-10 — SessionFlywheel competitive DR scorecard deep-links
Session land / Antiek-bench usage flywheel navigates Settings competitive DR scorecard +
FUTURE brief. vitest SessionFlywheel 6 green. P0 operator merge PR #465. Pivot aje+.

## Residual aje · 2026-07-10 — DecisionTreeDriverBadge competitive DR scorecard deep-link
Shared model driver + budget chokepoint navigates competitive DR scorecard
(ND never router honesty at model choice). vitest DecisionTreeDriverBadge 13 green.
P0 operator merge PR #465. Pivot ajf+ outside scorecard thrash.

## Residual ajf · 2026-07-10 — HostedHtml free STEM subjects → domainSubjects honesty
HostedHtml context mount stamps catalog subjects so ResearchContext domain-aware
twin search defaults fire for free STEM hosted books (reading ≡ research).
vitest HostedHtml 25 green. P0 operator merge PR #465. Pivot ajg+ outside thrash.

## Residual ajg · 2026-07-10 — SESSION-ARC aja–ajf scorecard STEM flywheel
Wave handoff: dogfood v30 · attach/flywheel/badge scorecard · free STEM domainSubjects.
Scorecard matrix dense — next residuals prefer non-scorecard product. P0 merge #465.
Pivot ajh+ outside thrash.

## Residual ajh · 2026-07-10 — public export multi-hop citation chain builders
engagement_spine exports build_citation_chain_hops + citation_chain_complete
for agent-readable multi-hop claim→source API (air). pytest evidence 4 green.
P0 operator merge PR #465. Pivot aji+ outside thrash.

## Residual aji · 2026-07-10 — evidence pack Write seed multi-hop citation chain honesty
buildEvidencePackWriteHref stamps chain_complete · hop strip · stable anchors into
twin_seed plain/HTML so recursive note-taker Write preserves multi-hop honesty.
vitest twinWriteSeed 35 green. P0 operator merge PR #465. Pivot ajj+ outside thrash.

## Residual ajj · 2026-07-10 — SESSION-ARC air–aji multi-hop write path
Wave handoff: substrate hops → UI → dogfood → public API → Write twin_seed.
P0 operator merge PR #465. Pivot ajk+ outside thrash.

## Residual ajk · 2026-07-10 — dogfood v31 evidence Write multi-hop honesty
Suite suite-competitive-dogfood-v31 learns evidence pack → Write twin_seed multi-hop
hop honesty (aji). item_count 47 · wrestle=34. pytest dogfood 5 · Settings 36 green.
P0 operator merge PR #465. Pivot ajl+ outside thrash.

## Residual ajl · 2026-07-10 — MarketplaceHost competitive DR scorecard deep-links
Free STEM HTML marketplace navigates Settings competitive DR scorecard + FUTURE brief
(HTML-first free STEM shipped · L5 payment deferred). vitest MarketplaceHost 41 green.
P0 operator merge PR #465. Pivot ajm+ outside thrash.

## Residual ajm · 2026-07-10 — ResearchLaunchBudget competitive DR scorecard deep-links
Budget-before-fire launch panel navigates Settings competitive DR scorecard + FUTURE
brief (soft foresight · ND never router). Scorecard budget row names launch panel.
vitest ResearchLaunchBudget 12 · Settings 36 green. P0 operator merge PR #465.
Pivot ajn+ outside thrash.

## Residual ajn · 2026-07-10 — twin promote depth-graph node honesty
Twin promote→context metrics stamp content-addressed graph_node_ids, unique counts,
and unit≡node alignment for recursive note-taker depth-graph honesty. FUTURE twin
matrix deep-link. vitest TwinNotes 30 green. P0 operator merge PR #465. Pivot ajo+.

## Residual ajo · 2026-07-10 — twin promote payload depth-graph honesty
twin_promote_context_payload emits graph_node_ids · unique counts ·
content_addressed_alignment; HTML depth-graph strip. Substrate parity with UI
ajn. pytest twin promote 15 green. P0 operator merge PR #465. Pivot ajp+.

## Residual ajp · 2026-07-10 — SESSION-ARC ajm–ajo budget twin depth
Wave handoff: launch budget scorecard · twin promote UI depth-graph · substrate
payload depth-graph honesty. P0 operator merge PR #465. Pivot ajq+ outside thrash.

## Residual ajq · 2026-07-10 — dogfood v32 twin promote depth-graph honesty
Suite suite-competitive-dogfood-v32 learns twin promote depth-graph unit≡node
(ajn/ajo). item_count 48 · wrestle=35. pytest dogfood 5 · Settings 36 green.
P0 operator merge PR #465. Pivot ajr+ outside thrash.

## Residual ajr · 2026-07-10 — TwinNotes prefer API depth-graph honesty fields
twin-promote-metrics prefers substrate graph_node_ids / content_addressed_alignment
when present (ajo) with data-depth-graph-source=api. vitest TwinNotes 30 green.
P0 operator merge PR #465. Pivot ajs+ outside thrash.

## Residual ajs · 2026-07-10 — SESSION-ARC ajn–ajr twin depth-graph path
Wave handoff: UI metrics · substrate payload · dogfood v32 · API-first field prefer.
P0 operator merge PR #465. Pivot ajt+ outside thrash.

## Residual ajt · 2026-07-10 — pure depth_graph_honesty_fields helper
Extract content-addressed unit≡node honesty into pure helper used by promote
payload (ajo). pytest twin promote product 8 green. P0 operator merge PR #465.
Pivot aju+ outside thrash.

## Residual aju · 2026-07-10 — public export depth_graph_honesty_fields
engagement_spine exports pure depth_graph_honesty_fields (ajt) for agent-readable
promote depth-graph audit. pytest public import green. P0 operator merge PR #465.
Pivot ajv+ outside thrash.

## Residual ajv · 2026-07-10 — twin promote Write seed depth-graph honesty
buildTwinPromoteWriteHref stamps depth-graph unique_nodes + unit≡node alignment
into twin_seed for recursive note-taker Write (parity aji multi-hop Write).
vitest twinWriteSeed 35 · TwinNotes 30 green. P0 operator merge PR #465. Pivot ajw+.

## Residual ajw · 2026-07-10 — dogfood v33 twin promote Write depth-graph honesty
Suite suite-competitive-dogfood-v33 learns promote→Write twin_seed depth-graph
honesty (ajv). item_count 49 · wrestle=36. pytest dogfood 5 · Settings 36 green.
P0 operator merge PR #465. Pivot ajx+ outside thrash.

## Residual ajx · 2026-07-10 — SESSION-ARC ajn–ajw twin depth Write path
Wave handoff: promote depth-graph UI · substrate · pure helper · public export ·
Write seed · dogfood v32–v33. P0 operator merge PR #465. Pivot ajy+ outside thrash.

## Residual ajy · 2026-07-10 — NotDiamond install never-dispatch machine honesty
Install advisory control stamps never-dispatch-authority · decision-tree-only ·
advisory_only; ND panel links competitive DR scorecard (L7 never router).
vitest Settings 36 green. P0 operator merge PR #465. Pivot ajz+ outside thrash.

## Residual ajz · 2026-07-10 — scorecard model-choice / ND never rows name ajy
Competitive DR scorecard model-choice and ND-never-router rows name
decision-tree-only install + never-dispatch-authority stamps (ajy).
vitest Settings 36 green. P0 operator merge PR #465. Pivot aka+ outside thrash.

## Residual aka · 2026-07-10 — decision-tree ND install provenance never-dispatch
After NotDiamond advisory install, decision-tree provenance stamps
never-dispatch-authority · decision-tree-only · advisory_only (parity ajy install).
vitest Settings 36 green. P0 operator merge PR #465. Pivot akb+ outside thrash.

## Residual akb · 2026-07-10 — marketplace host-result L5 FUTURE seamless port deep-links
After catalog host land, operators navigate FUTURE L5 digital book seamless port
brief, dual-gate L5 checklist, and competitive DR scorecard (HTML-first ·
manual_receipt_only · live rails deferred). vitest MarketplaceHost 41 green.
P0 operator merge PR #465. Pivot akc+ outside thrash.

## Residual akc · 2026-07-10 — SESSION-ARC ajy–akb ND never-dispatch + L5 honesty
Wave handoff: ND install→decision-tree never-dispatch path · marketplace host
FUTURE L5 seamless port. P0 operator merge PR #465. Pivot akd+ outside thrash.

## Residual akd · 2026-07-10 — FUTURE competitive DR quality brief tip re-anchor
Executable competitive DR brief refreshed with tip SHA and shipped map through
akb (multi-hop · depth-graph · ND never-dispatch · L5 host deep-links · dogfood v33).
P0 operator merge PR #465. Pivot ake+ outside thrash.

## Residual ake · 2026-07-10 — Settings prompt-cost competitive DR deep-links
Settings prompt-cost projection panel links competitive DR scorecard + FUTURE
brief + decision-tree (budget-before-fire Settings surface · parity ajm launch).
vitest Settings 37 green. P0 operator merge PR #465. Pivot akf+ outside thrash.

## Residual akf · 2026-07-10 — scorecard L5 payment FUTURE digital book port link
Competitive DR scorecard payment deferred row deep-links FUTURE-AGENT L5 digital
book seamless port (parity marketplace host akb). vitest Settings 37 green.
P0 operator merge PR #465. Pivot akg+ outside thrash.

## Residual akg · 2026-07-10 — SESSION-ARC aka–akf ND budget L5 honesty
Wave handoff: ND decision-tree provenance · marketplace L5 host · FUTURE brief ·
prompt-cost scorecard · scorecard L5 FUTURE link. P0 operator merge PR #465.
Pivot akh+ outside thrash.

## Residual akh · 2026-07-10 — scorecard deferred live dual-gate deep-links
Competitive DR scorecard deferred live rows deep-link dual-gate L1/L2 hydrate,
L4 Midnight Oil, L6 collective checklist + FUTURE L6 multi-agent brief.
vitest Settings 37 green. P0 operator merge PR #465. Pivot aki+ outside thrash.

## Residual aki · 2026-07-10 — scorecard twin-notes FUTURE completeness matrix deep-link
Competitive DR scorecard twin-notes row deep-links FUTURE twin note-taker
completeness matrix (promote depth-graph path ajn–ajw). vitest Settings 37 green.
P0 operator merge PR #465. Pivot akj+ outside thrash.

## Residual akj · 2026-07-10 — SESSION-ARC akh–aki scorecard deferred map
Wave handoff: scorecard deferred live dual-gate deep-links + twin FUTURE matrix.
Scorecard map dense — prefer non-scorecard product next. P0 operator merge PR #465.
Pivot akk+ outside thrash.

## Residual akk · 2026-07-10 — Midnight Oil Settings prompt-cost projection deep-link
Autonomous Midnight Oil navigates Settings prompt-cost projection for
budget-before-fire foresight (parity ake Settings surface). vitest MidnightOil 26 green.
P0 operator merge PR #465. Pivot akl+ outside thrash.

## Residual akl · 2026-07-10 — ResearchProgress Settings prompt-cost projection deep-link
Multi-minute wrestle progress navigates Settings prompt-cost projection for
budget-before-fire foresight (parity akk Midnight Oil · ake Settings).
vitest ResearchProgress 10 green. P0 operator merge PR #465. Pivot akm+ outside thrash.

## Residual akm · 2026-07-10 — CollectiveResearchPanel prompt-cost projection deep-link
Multi-agent collective merge navigates Settings prompt-cost projection for
budget-before-fire (parity akl progress · akk MO). vitest Collective 29 green.
P0 operator merge PR #465. Pivot akn+ outside thrash.

## Residual akn · 2026-07-10 — SpawnMergePanel prompt-cost projection deep-link
Highlight→DR→merge navigates Settings prompt-cost projection. Completes
budget-before-fire prompt-cost matrix (akk–akn + ake/ajm). vitest SpawnMerge 8 green.
P0 operator merge PR #465. Pivot ako+ outside thrash.

## Residual ako · 2026-07-10 — SessionFlywheel prompt-cost projection deep-link
Session land / Antiek-bench flywheel navigates Settings prompt-cost projection.
Budget-before-fire matrix now includes flywheel (akk–ako). vitest SessionFlywheel 7 green.
P0 operator merge PR #465. Pivot akp+ outside thrash.

## Residual akp · 2026-07-10 — ResearchLaunchBudget prompt-cost projection deep-link
Launch budget foresight panel navigates full Settings prompt-cost projection.
Budget-before-fire matrix complete across launch · MO · progress · collective ·
spawn · flywheel (akk–akp). vitest ResearchLaunchBudget 12 green.
P0 operator merge PR #465. Pivot akq+ outside thrash.

## Residual akq · 2026-07-10 — domain-aware twin search free PD economics/politics/philosophy/engineering
Intelligent twin search defaults expand beyond STEM (aiy) to free PD catalog
subjects: economics (Wealth of Nations), politics (Federalist), bare philosophy
(Discourse/Liberty after method precedence), engineering (after heat|electricity).
FUTURE twin matrix gap #3 updated. vitest ResearchContext 15 green.
P0 operator merge PR #465. Pivot akr+ outside thrash.

## Residual akr · 2026-07-10 — L5 payment adapter boundary offline-honest dual-gate
FUTURE L5 Sprint 1: payment_adapter.py with DeferredPaymentAdapter default
(zero upstream · typed LivePaymentDeferredError · manual opaque receipt) and
LivePaymentAdapter only when ANTIEK_MARKETPLACE_LIVE_PAYMENT + injected
upstream; never invents $0 entitlement. pytest 10 green.
P0 operator merge PR #465. Pivot aks+ outside thrash.

## Residual aks · 2026-07-10 — MarketplaceHost L5 payment adapter Sprint 1 honesty chrome
Catalog + host-land L5 honesty stamps payment-adapter Sprint 1 shipped offline
(akr · DeferredPaymentAdapter · ANTIEK_MARKETPLACE_LIVE_PAYMENT · never $0) and
Sprint 2 purchase path still deferred. vitest MarketplaceHost 41 green.
P0 operator merge PR #465. Pivot akt+ outside thrash.

## Residual akt · 2026-07-10 — ResearchProgress FUTURE competitive DR quality deep-link
Multi-minute wrestle progress navigates FUTURE-AGENT competitive DR quality brief
(parity launch/collective/spawn/flywheel/MO). Progress nav: scorecard · FUTURE ·
prompt-cost · dual-gate L4. vitest ResearchProgress 10 green.
P0 operator merge PR #465. Pivot aku+ outside thrash.

## Residual aku · 2026-07-10 — L5 Sprint 2 purchase path payment adapter offline-safe
record_purchase_and_host accepts checkout_session_id: deferred dual-gate raises
LivePaymentDeferredError with zero host; manual opaque path unchanged; live host
only when adapter confirms charged live_payment. FUTURE L5 Sprint 2 offline-safe.
pytest 9 green. P0 operator merge PR #465. Pivot akv+ outside thrash.

## Residual akv · 2026-07-10 — SESSION-ARC akr–aku L5 payment path
Wave handoff: payment adapter Sprint 1 · MarketplaceHost honesty · progress FUTURE
· purchase path Sprint 2 offline-safe. P0 operator merge PR #465. Pivot akw+ outside thrash.

## Residual akw · 2026-07-10 — domain-aware twin search free PD literature + bare technology
Intelligent twin search defaults complete free PD catalog subject spine:
literature (Pride) · bare technology (after STEM precedence). FUTURE twin matrix
gap #3 expanded. vitest ResearchContext 16 green.
P0 operator merge PR #465. Pivot akx+ outside thrash.

## Residual akx · 2026-07-10 — DecisionTreeDriverBadge FUTURE competitive DR + prompt-cost
Shared model-driver chokepoint navigates FUTURE competitive DR quality brief and
Settings prompt-cost projection (budget-before-fire + competitive map at every
driver badge mount). vitest DecisionTreeDriverBadge 14 green.
P0 operator merge PR #465. Pivot aky+ outside thrash.

## Residual aky · 2026-07-10 — TwinNotes FUTURE competitive DR + prompt-cost deep-links
Recursive note-taker panel navigates competitive FUTURE DR quality brief and
Settings prompt-cost projection (parity driver badge akx · progress akt).
vitest TwinNotes 30 green. P0 operator merge PR #465. Pivot akz+ outside thrash.

## Residual akz · 2026-07-10 — SESSION-ARC akq–aky domain L5 driver twin wave
Wave handoff: domain twin search free PD · L5 payment Sprint 1–2 · progress FUTURE ·
driver + twin FUTURE/prompt-cost. P0 operator merge PR #465. Pivot ala+ outside thrash.

## Residual ala · 2026-07-10 — MarketplaceHost L5 Sprint 3 live-checkout deferred CTA honesty
Paid catalog rows show disabled Live checkout (L5 deferred) CTA + honesty note;
manual Purchase + host remains the only active paid path. Never invents charge.
FUTURE L5 Sprint 3 offline stub. vitest MarketplaceHost 41 green.
P0 operator merge PR #465. Pivot alb+ outside thrash.

## Residual alb · 2026-07-10 — SESSION-ARC akr–ala L5 payment complete offline
Wave handoff: L5 Sprint 1 adapter · Sprint 1 honesty · Sprint 2 purchase path ·
Sprint 3 deferred CTA — offline product-complete for digital book payment.
P0 operator merge PR #465. Pivot alc+ outside thrash (prefer non-L5).

## Residual alc · 2026-07-10 — evidence pack Settings prompt-cost projection deep-link
Evidence/search/hydrate substrate navigates Settings prompt-cost projection for
budget-before-fire (parity progress/driver/twin). Evidence nav: scorecard ·
FUTURE · prompt-cost. vitest ResearchContext 16 green.
P0 operator merge PR #465. Pivot ald+ outside thrash.

## Residual ald · 2026-07-10 — PublicationAttach Settings prompt-cost projection deep-link
Knowledge-dense arxiv/substack attach navigates Settings prompt-cost projection
for budget-before-fire (parity evidence alc · twin aky · driver akx).
vitest PublicationAttach 6 green. P0 operator merge PR #465. Pivot ale+ outside thrash.

## Residual ale · 2026-07-10 — SESSION-ARC akx–ald budget matrix extension
Wave handoff: driver · twin · evidence · attach prompt-cost matrix extension
beyond akk–akp multi-minute spend surfaces. P0 operator merge PR #465.
Pivot alf+ outside thrash (prefer non-deep-link).

## Residual alf · 2026-07-10 — domain-aware twin search bare science catch-all
Intelligent twin search defaults bare science/natural_philosophy after specific
STEM domains (never overrides biology/physics/math). Completes free PD science
spine catch-all. FUTURE twin matrix gap #3 expanded. vitest ResearchContext 16 green.
P0 operator merge PR #465. Pivot alg+ outside thrash.

## Residual alg · 2026-07-10 — FUTURE competitive DR quality brief tip re-anchor
Executable competitive DR brief refreshed with tip alf 2cf218f1 and shipped map
through L5 Sprint 1–3 · free PD domain search spine · budget matrix extension.
P0 operator merge PR #465. Pivot alh+ outside thrash.

## Residual alh · 2026-07-10 — FUTURE competitive brief offline spine map complete
Complete offline spine map on FUTURE competitive DR brief: L5 Sprint 1–3 · free
PD domain search · budget matrix. Inventory handoff prefers non-deep-link product.
P0 operator merge PR #465. Pivot ali+ outside thrash.

## Residual ali · 2026-07-10 — FUTURE competitive execution-order re-anchor
Execution order points at SESSION-ARC akq–aky · akr–ala · akx–ald; prefer
non-deep-link product. P0 operator merge PR #465. Pivot alj+ outside thrash.

## Residual alj · 2026-07-10 — domain-search coverage honesty stamps
domainSearchCoverage reports covered vs uncovered free PD subjects; ResearchContext
controls stamp data-domain-search-* and status strip (never invent empty query).
vitest ResearchContext 17 green. P0 operator merge PR #465. Pivot alk+ outside thrash.

## Residual alk · 2026-07-10 — SESSION-ARC akq–alj domain search complete
Wave handoff: free PD domain-aware twin search product-complete offline (akq–alj)
with coverage honesty. P0 operator merge PR #465. Pivot alm+ outside thrash.

## Residual alm · 2026-07-10 — MarketplaceHost host-land domain-search coverage honesty
After free PD host land, metrics stamp domain-search coverage (alj) so catalog
subjects continue into intelligent twin search. vitest MarketplaceHost 41 green.
P0 operator merge PR #465. Pivot aln+ outside thrash.

## Residual aln · 2026-07-10 — SESSION-ARC alj–alm domain coverage path
Wave handoff: domainSearchCoverage ResearchContext → MarketplaceHost host land.
P0 operator merge PR #465. Pivot alo+ outside thrash.

## Residual alo · 2026-07-10 — HostedHtml domain-search coverage + domainSearchDefaults extract
Pure domainSearchDefaults util; HostedHtml reading host stamps coverage; marketplace
imports pure path. Domain coverage path: ResearchContext · MarketplaceHost · HostedHtml.
vitest 83 green. P0 operator merge PR #465. Pivot alp+ outside thrash.

## Residual alp · 2026-07-10 — SESSION-ARC alj–alo domain coverage full path
Wave handoff: ResearchContext · MarketplaceHost · HostedHtml domain-search coverage
+ pure util extract. P0 operator merge PR #465. Pivot alq+ outside thrash.

## Residual alq · 2026-07-10 — pure domainSearchDefaults unit tests + twin matrix complete
Pure unit tests lock domain-search spine; FUTURE twin matrix gap #3 offline
product-complete (akq–alo). vitest 2 green. P0 operator merge PR #465.
Pivot alr+ outside thrash (prefer non-domain-search).

## Residual alr · 2026-07-10 — DEFERRED-GAPS L5 + domain-search closures
Deferred-gaps brief notes L5 offline Sprint 1–3 complete and free PD domain-search
closed offline. Live injectors remain dual-gate. P0 operator merge PR #465.
Pivot als+ outside thrash.

## Residual als · 2026-07-10 — DEFERRED-GAPS domain-search + L5 closed offline notes
Deferred-gaps items 5–6 record free PD domain-search and L5 Sprint 1–3 offline-closed.
P0 operator merge PR #465. Pivot alt+ outside thrash.

## Residual alt · 2026-07-10 — TwinNotes domainSubjects + domain-search coverage
Recursive note-taker accepts free PD subjects and stamps domain-search coverage;
HostedHtml passes catalog subjects into TwinNotes (reading ≡ research).
vitest TwinNotes 31 · HostedHtml 25 green. P0 operator merge PR #465.
Pivot alu+ outside thrash.

## Residual alu · 2026-07-10 — SESSION-ARC alj–alt domain coverage including TwinNotes
Wave handoff: domain-search coverage path includes TwinNotes recursive note-taker
(alt). P0 operator merge PR #465. Pivot alv+ outside thrash.

## Residual alv · 2026-07-10 — FUTURE competitive tip re-anchor through alu
Competitive DR brief tip e1a6cc61; twin intelligent search residual names full
spine + TwinNotes coverage path. P0 operator merge PR #465. Pivot alw+ outside thrash.
