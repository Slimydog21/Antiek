# Branding densification wave — 2026-07-15/16

PR #2416 tip (at close of this note): `92dad8cbe` — axe+LP green.

## Product surfaces now UI-consuming session brand

| Surface | Asset | testid |
|---|---|---|
| Werner moods thinking/celebrate | session PNGs | via brand/Werner.tsx |
| ArcadeCabinet chrome + ice/zombies art | session PNGs | cabinet-brand-* |
| Research wait arcade | session ice/zombies | research-wait-arcade |
| Library Read door | thinking | library-werner-brand |
| Research home | thinking | research-home-werner-brand |
| Write door | celebrate | write-home-werner-brand |
| Settings Antiek-bench | thinking | antiek-bench-werner |
| Login desk | thinking | login-werner-brand |
| Speak door | thinking (Werner mood) | speak-home-werner-brand |
| Thought partner panel | desk scene webp | thought-partner-desk-art |

## Living-TV interaction

- Scenery product map + hover glance (once/hotspot) + sun focus ring
- Product click highlight owned by AppShell map; peak-left ambient owns click highlight
- Cabinet play → highlight; budget over → fail; Midnight Oil arm → deep_research_start
- Arcade: ice fishing, clam catcher, zombies + LoadingGameHost

## Imagine inventory (not product-mapped)

`docs/design-assets/session-20260715/` including clam catcher candidate.

## Pulse

`branding-doors-pulse.log` — 76 tests / 12 files green (2026-07-16).

## Honest gaps still open

- Pure Flipbook sole UI NO-GO
- CF Pages external-pending often
- Operator merge wall on #2416

## Clam Catcher session promote (2026-07-16)

- Invent `session-20260715/werner_clam_catcher_refedit_v1.jpg` →
  `poses/session/werner_clam_catcher_session_v1.png` via `cut_session_fringe.py`
- Opaque provenance retained; four corners alpha=0; cabinet card uses session PNG
- Authored webp key art remains for in-game visual kit (no Werner on sprites)

## Thought-partner desk promote (2026-07-16)

- Invent `session-20260715/werner_thought_partner_desk_refedit_v1.jpg` →
  `poses/session/werner_thought_partner_desk_session_v1.webp` (1200×800, q88)
- Full-bleed scene art (not alpha character mark) on ThoughtPartnerPanel
- CTA emits Werner `highlight` living-TV beat

## Living-TV densify wave (2026-07-16 continuation)

| Delta | Tip | Behavior |
|---|---|---|
| Living-TV invent v2 → LGH strip | `8017e9d7a` | `werner_living_tv_session_v1.webp` on wait host; highlight on opt-in |
| `piece_started` product experience | `505adcc1f` | Write create → happy craft emote |
| Home doors PRODUCT_ACTIVATE | `c67016794` | `emoteForProductDoor` before navigate |
| Library open highlight | `df7069737` | shelf open/openAtPage → curious glance |
| Speak thinking brand | `a5c8b6f44` | `speak-home-werner-brand` session mood |
| Speak create | `7462661ae` | piece_started happy craft beat |
| Research absorb | `639ae47b0` | highlight on corpus attach |
| Home igloo arcade invent | `145cb173f` | scene webp + thinking mark on Home arcade card |
| Cabinet igloo banner | `77862e281` | same invent on ArcadeCabinet chrome |
| Antiek-bench desk strip | `c86a6a9fd` | thought-partner desk webp in Settings |
| Midnight Oil living-TV | `385909143` | living-TV invent + highlight on goal add |
| Login / Research / Write / Library / Speak living-TV | `3dd97e639`–`611cf6b33` | door invent strips complete |
| ReadingCompanion glass-box | `68bd0c484` | thinking mark + living-TV invent on in-book rail |
| ResearchThis spin | `68bd0c484` | notifyResearchStarted living-TV DR beat |
| TalkToBook / VoiceNote / Biography | `61ee9273b` | open highlight, note_saved, thinking brand |
| MetaReading / PersonalSpace | `062f54e23`–`b89d4f9f9` | living-TV invent strips on reading surfaces |
| Outcomes / Notebooks / Wrestle empty | `d0894b8a3` | thinking + living-TV brand chrome on audit, notebooks, wrestle doors |
| Documents / Investigations / Settings / Home living-TV | (wave) | substrate index doors + settings + home invent strip; inv start → deep_research_start |
| Sources / Brainstorm empty | (wave) | arXiv ingest door + watch-for-later empty; ingest highlight; launch deep_research_start |
| Midnight Oil invent promote | `306c12c65` | late-night desk webp on Midnight Oil panel |
| SessionBrandChrome + residual doors | `30479746b` | shared chrome; Trust/Billing/Pricing/Map/Stats/Replay/Fed/Loop3 |
| Payouts / SkillRules / Interviews | (wave) | audit + skill + interview doors via SessionBrandChrome |
| CRT invent Home + Coordination/Backtest | `9b9412745` | penguin-as-TV invent strip; residual operator densify |
| CrossGraph / SkillRuleDetail | `454f23df9` | citation + skill detail brand chrome |
| Twin notes / Notebook canvas / CreationStudio | (wave) | recursive note-taker + literate surfaces densify |
| Living-TV ambient heartbeat | `521a18d15` | 90s quiet → idle/sleeping; re-arm on product experience |
| AutoNotebook densify | `d7b399549` | derived research notebook header brand chrome |
| Biography invent + Outcomes detail | `f01eea8d5` | living-TV strip + grading surface SessionBrandChrome |
| SpeakInvite phone densify | `e7a7ae27e` | invitee landing thinking + living-TV invent | |



| CostMeter / BlockDetail densify | `c1980850f` | budget living-TV beats + block chase DR start |
| Zombies living-TV beats | `c1980850f` | start/wave/gameover Werner experiences |
| Ice + Clam living-TV beats | `f2a9073af` | Club Penguin wait games living-TV contract |
| Cascade plan invent | `f2d5855ec` | PlanEditor cascade invent webp |
| Arcade cabinet product-id | `be7a29660` | cards stamp `data-product-id=arcade` + PRODUCT_ACTIVATE |
| Accrual/Chase/trust living-TV beats | `ea49628ac` | invent + DR spawn/error + notify/delete beats |
| TwinNotes living-TV invent | `6eb4a9373` | recursive note-taker companion invent strip |
| DistillView + MyResearch densify | `204eeaae9` | complete/fail/chase + SessionBrandChrome monitor |
| BookReader open/fail beats | `3d6f97d4a` | highlight on open; fail on load error |
| NotesPanel + ThinkingStream beats | `d71580cf5` | challenge + status-transition living-TV |
| SuggestedResearch chase beats | `e746c1588` | flywheel Chase this → deep_research_start |
| MasterMdViewer invent + complete | `992f51e0f` | answer surface invent + deep_research_complete |
| Cursor-bait invent inventory | `b50b145f3` / `bfbdf4acb` | ice-fishing cursor-bait jpg+webp invent |
| Cursor-bait → LGH ice-fishing | `c64b69545` | wait-host ice-fishing strip uses cursor-bait session webp |
| TrajectoryView living-TV | `22f01168c` | invent strip + terminal complete/error beats |
| ChunkModal open/fail beats | `0c6ae5403` | highlight on chunk open; fail on fetch error |
| ChatInputArea DR beats | `c909aed01` | docked composer start/error living-TV |
| InvestigationSidebar brand | `bc4032924` | thinking mark + nav highlight |
| VoiceToDraft note_saved | `d1a9aacb8` | user-sourced voice draft living-TV |
| ConnectResearch link/spawn | `d16f53357` | highlight + deep_research_start/error |
| CRT igloo cursor-TV invent | `0b101bd91` | Flipbook-feel CRT+igloo+cursor invent inventory |
| Xray regenerate piece_started | `9e66cdca5` | write rewrite craft living-TV beat |
| CRT igloo invent LGH default | `9e66cdca5` | Flipbook-feel default wait-host invent strip |
| SubAgentProposal accept/reject | `169ba0606` | write sub-agent spin living-TV beats |
| Outline generate piece_started | `ddae1e6d2` | section draft craft living-TV beat |
| Wait-arcade ice cursor-bait | `27bfd54e7` | ResearchWaitArcade ice card product-maps invent |
| ArcadeCabinet ice cursor-bait | `68ac542d8` | cabinet ice card invent aligns LGH/wait-arcade |
| ModelDecisionTree pick/budget beats | `e2ccf7a9a` | model pick highlight; over-budget fail |
| AddModelPanel BYOK beats | `312f7e4ba` | model add/remove note_saved/fail |
| AntiekBench load beats | `4c91ee255` | weekly evidence highlight/fail |
| Antiek-bench celebrate invent | `3d0efae83` | celebrate invent product-mapped desk strip |
| NotDiamond toggle living-TV | `6280f9274` | advisor mode note_saved/highlight |
| PasteIngest absorb beats | `6256fddad` | highlight on absorb; fail on error |
| VoiceChase transcript beats | `62697398e` | note_saved on transcript; fail on error |

PR tip tracks `goal/twin-autoload-session-alpha` (#2416). Operator merge wall remains.

**Honest residuals still open:** pure Flipbook sole UI NO-GO; curious v2 candidate alpha-honest but not product-mapped (reactions are CSS/SVG); invent `living_tv_imagine_v1` superseded by promoted refedit v2; cursor-bait invent inventory-only; CF Pages external-pending often; operator merge; Imagine intermittent 503.

## Living-TV product-door emotes (choreography)

| Product id family | Emote |
|---|---|
| research, library, investigations, documents, notebooks | thinking |
| read, speak, arcade, sources | curious |
| write, home, create | happy |
| more, settings, billing, pricing | noted |
| midnight-oil / midnight_oil | sleeping |
| (other) | hit |

Exported as `emoteForProductDoor` from `werner` barrel. Expanded 2026-07-16 on tip `8bc22c346`.
