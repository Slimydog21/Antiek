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
