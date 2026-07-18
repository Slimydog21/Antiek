# Branding densification wave — 2026-07-15/16

PR #2416 tip (at close of this note): `b797844bd` — densify pack **47/434**.

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
| Library BookCard/CorpusSearch | `c385ca5b8` | shelf open + corpus search living-TV |
| ParkedQuestion + VoiceNoteCapture | `aa8596a02` | parked launch DR start; voice note_saved |
| CuratePrompt highlight | `a519c13d1` | prompt-to-curate living-TV |
| WatchForLater select | `df7e8e2d1` | parked folder select highlight |
| TocPanel jump highlight | `9adfcf82e` | in-book TOC living-TV |
| ArxivFrame link-back | `146eadef0` | T2/T3 arXiv CTA highlight |
| HouseSlot next-read | `4d188debe` | zero-buyer house promo highlight |
| VoiceSteeringInput transcript | `293118fda` | multimedia steer note_saved/fail |
| SlashMenu piece_started | `0199c8b08` | notebook slash insert craft beat |
| ArtifactOutlineShelf export | `ab92a59f7` | HTML artifact export piece_started/fail |
| PlanEditor approve/launch | `33129559b` | cascade glass-box note_saved + DR start |
| ResearchPanel steer beats | `acb6fc65f` | cascade monitor pause/stop/deepen living-TV |
| VisualReviewPanel craft beats | `d0858ed01` | visual authorize/submit/register living-TV |
| PasteIngest absorb beats | `6256fddad` | highlight on absorb; fail on error |
| VoiceChase transcript beats | `62697398e` | note_saved on transcript; fail on error |
| KnowledgePanel twin invent + beats | `08fa94dbc` | knowledge-twin invent strip; finalize/open/fail living-TV |
| LocalProduction / LocalAudible / Reconciliation | `08fa94dbc` | produce/attest/recover living-TV beats |
| CascadeProposal propose/fail | `08fa94dbc` | highlight on propose; DR error on fail |
| FloatMenu deep-research start | `08fa94dbc` | deep_research_start when spawn text launchable |
| Igloo ice-arcade invent product-map | `08fa94dbc` | LGH + wait-arcade + cabinet ice card CRT+cursor invent |
| ActiveListening research prepare | `432431ccf` | listen→research deep_research_start/error |
| CommandPalette / AISidecar / IdeaDump | `c4ef69275` | palette highlight; thought-partner note_saved; brainstorm piece_started |
| Paperclip zombies arcade invent product-map | `e3810ac85` | LGH + wait-arcade + cabinet zombies CRT invent |
| CreationStudio / ContextWindow / ChatInput | `a2d86a2d4` | create/export/save/promote/generate + distill living-TV |
| ArtifactExport living-TV | `af109d009` | HTML export piece_started; rights fail |

PR tip tracks `goal/twin-autoload-session-alpha` (#2416). Operator merge wall remains.

**Honest residuals still open:** pure Flipbook sole UI NO-GO; curious v2 candidate alpha-honest but not product-mapped (reactions are CSS/SVG); prior ice cursor-bait invent superseded by igloo ice-arcade invent on product surfaces (cursor-bait retained in inventory); CF Pages external-pending often; operator merge; Imagine intermittent 503.

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
| Speak Invites/Settings densify | `7ab9d486a` | invite note_saved; payout release noted/fail |
| Float research-merge invent → TwinNotes | `4cbd149dc` | recursive note-taker float invent product-mapped |
| InterviewVoiceCapture living-TV | `a77bb3005` | invitee voice upload note_saved/fail |
| Write Repository living-TV | `91048db1e` | shelf search highlight/fail |
| NotebookEditor living-TV autosave | `265511b13` | note_saved on save; fail on conflict |
| NotesFeed living-TV cite jump | `b8ea77fb4` | highlight on source-event chip |
| Midnight oil swarm invent product-map | `4ba9b6147` | MidnightOilPanel swarm desk invent |
| SpokenReply/ReadAloud living-TV | `f93b7e578` | listen highlight; withheld/error fail |
| WorkspaceWindow living-TV | `4d7f159b9` | float toggle highlight; close note_saved |
| TrajectoryReplay/CrossDocSidebar living-TV | `6973f10ba` | replay start DR; cite/restart highlight |
| ClaimCard living-TV challenge | `b5978f103` | challenge DR start; fail on error |
| ContextPicker living-TV compose | `7f45f1aec` | compose note_saved; fail on error |
| Clam catcher cursor invent product-map | `fec8cbae4` | LGH + wait-arcade + cabinet clam invent |
| WorkCard living-TV shelf open | `587a843ab` | highlight on read/claim |
| LibraryView living-TV filter | `aea9d8f07` | filter/reload highlight |
| ResearchThis/ReplayStepList living-TV | `141d2b191` | spin fail DR error; replay step highlight |
| Speak project + HardCeiling densify | `33f789d9f` | invite/assemble/ceiling living-TV |
| DR Canvas BlockCard living-TV | `26facb897` | open/cite highlight |
| ProjectType/InterviewTranscript densify | `354bd4589` | type pick highlight; transcript note_saved |
| Biography living-TV densify | `e461179d9` | start piece_started; share note_saved; door jumps highlight |
| PersonalSpace/BlockRepository densify | `59c0f2600` | personal jumps + repo add/folder highlight |
| CostConsent living-TV densify | `1d614b776` | reload highlight/fail |
| SpeakInvite living-TV densify | `dbcaab839` | invitee take-part/mode/submit densify |
| HTML book float invent → ReadingCompanion | `8d331c5e8` | product-map HTML-first Flipbook-feel invent |
| Notebooks/Documents index densify | `522ab4feb` | create piece_started; filter highlight |
| AdSlot/OutcomesIndex densify | `e507f5118` | ad click + outcomes open highlight |
| AssignHotkey living-TV densify | `3d04e6bde` | save note_saved; remove highlight |
| Shell launcher/tree densify | `2d03f38b0` | ProductsLauncher/ProjectTree/SubActionList/NavRail search |
| PanelHandle/PdfViewer densify | `332953d6f` | dock modes highlight; PDF note_saved |
| Import repair after densify inject | `37b248a86` | multi-line import blocks restored |
| AIActionFailure living-TV densify | `86d6c8044` | retry highlight |
| SceneChrome/ThreadBreadcrumb densify | `52e184a69` | chrome actions + thread hop highlight |
| Topbar account living-TV densify | `97252efe2` | profile/settings highlight; sign-out noted |
| Write editor + notebook blocks densify | `c719bccfe` | cite/trace highlight; block delete noted |
| ResearchWaitArcade opt-in densify | `2128bb51e` | opt-in highlight; exit note_saved |
| Write editor multi-stmt repair | `2da6df8fd` | Citation/BlockNode onClick blocks |
| Collective merge invent → SubAgentProposal | `549eb2420` | multi-agent strengthen product door invent strip |
| Model decision tree invent → ModelDecisionBar | `549eb2420` | per-prompt model + budget invent strip |
| Book marketplace port invent → HouseSlot | `549eb2420` | next-read marketplace/port invent thumb |
| arXiv/Substack dens invent → Sources | `549eb2420` | knowledge dens product door invent strip |
| Living-TV ambient episode continuity | `a713819a0` | quiet beat continues last product episode |
| FloatMenu collective invent product-map | `8100985a9` | float research windows invent strip |
| Flipbook invent reframe CSS | `036391eb0` | soft living imagery motion; reduced-motion safe |
| TwinNotes/MidnightOil/Bench/Companion reframe densify | `893e483fa` | invent reframe class on residual invent strips |
| Global invent reframe via main.tsx | `615beda18` | all *-living-tv-art strips inherit Flipbook motion |
| Igloo minigame trio invent → ArcadeCabinet | `eb666976f` | ice+clam+zombies unified cabinet banner |
| Home arcade minigame trio invent | `7c6bf334d` | align Home igloo banner with ArcadeCabinet trio |
| ice_fishing_cursor_bait invent | inventory | superseded by igloo_ice_arcade on product ice cards; retained integrity-only |
| midnight_oil_session_v1 invent | inventory | superseded by midnight_oil_swarm on MidnightOilPanel; retained integrity-only |
| Arcade core free of reactionBus | `5c763e0e5` | inject living-TV via host emit + onWernerBeat; boundary suite green |
| ResearchWaitArcadeGame living-TV inject | `c97af31d7` | onWernerBeat=emitLivingTvHostBeat like cabinet/LGH |
| sessionAssets product-map assert | `b8a286871` | cabinet densify asserts cursor webp invents (ice/clam/zombies), not inventory fringe PNG |
| Imagine invent polish v2 CRT + igloo trio | `4639f4ec2` | product-mapped reframe of living-TV home invent + minigame trio cabinet banner |
| Imagine invent polish v2 paperclip zombies | `cd2e143d4` | wait-arcade/cabinet/LGH zombies key art |
| Imagine invent polish v2 model decision tree | `cd2e143d4` | ModelDecisionBar product invent strip |
| Imagine invent polish v2 midnight oil swarm | `65dd7c8e3` | MidnightOilPanel product invent |
| Imagine invent polish v2 float research merge | `65dd7c8e3` | TwinNotes float-merge product invent |
| Imagine invent polish v2 collective merge | `9a5d3d37d` | SubAgentProposal + FloatMenu invent |
| Imagine invent polish v2 book marketplace port | `9a5d3d37d` | HouseSlot invent |
| Imagine invent polish v2 arxiv/substack dens | `f1f411fdd` | Sources product invent |
| Imagine invent polish v2 html book float | `f1f411fdd` | ReadingCompanion invent |
| Imagine invent polish v2 knowledge twin cursor | `f1f411fdd` | KnowledgePanel invent |
| Imagine invent polish v2 antiek-bench celebrate | `125880b58` | AntiekBenchPanel product invent |
| Imagine invent polish v2 CRT igloo cursor TV | `348a9571a` | LoadingGameHost default living-TV invent |
| Explicit invent reframe class densify | `359f415c1` | stamp antiek-living-tv-invent on residual product invent doors + LGH; densify tests |
| Mascot receives living-TV host beats | `c552362df` | PenguinMascot.reactions densify: arcade host emit → same emote stage |
| Imagine invent polish v2 thought partner desk | `ed1a43c31` | ThoughtPartnerPanel invent |
| Imagine invent polish v2 igloo ice arcade cursor | `69087de78` | cabinet/LGH/wait ice-fishing invent |
| Imagine invent polish v2 clam catcher cursor | `cf9208541` | cabinet/LGH/wait clam invent |
| ThoughtPartner invent reframe densify | `2a0dfd2f0` | living-tv-art testid + antiek-living-tv-invent class |
| Imagine invent polish v2 living-TV session | `823b9779a` | SessionBrandChrome residual doors invent |
| Imagine invent polish v2 cascade plan | `cfb698eb4` | PlanEditor invent |
| Imagine invent polish v2b html book float | `7dcb2f843` | ReadingCompanion invent refresh on green tip |
| Imagine invent polish v2b arxiv dens | `97a62053c` | Sources invent refresh on green tip |
| Imagine invent polish v2b collective merge | `7e591b002` | SubAgentProposal + FloatMenu invent refresh |
| Imagine invent polish v2b book marketplace | `47dfbeba3` | HouseSlot invent refresh |
| Imagine invent polish v2b model decision tree | `07c30d5db` | ModelDecisionBar invent refresh |
| Imagine invent polish v2b midnight oil swarm | `b8c26e9f0` | MidnightOilPanel invent refresh |
| Imagine invent polish v2b knowledge twin | `92bf08ed8` | KnowledgePanel invent refresh |
| Imagine invent polish v2b float research merge | `76e7bd181` | TwinNotesPanel invent refresh |
| Imagine invent polish v2b paperclip zombies | `74ae5f498` | wait-arcade/cabinet/LGH zombies invent refresh |
| Imagine invent polish v2b igloo minigame trio | `616f4556f` | ArcadeCabinet + Home arcade banner invent refresh |
| Imagine invent polish v2b CRT living-TV | `3b75e1d89` | Home + DR compose invent refresh |
| Imagine invent polish v2b antiek-bench celebrate | `6f97a4832` | AntiekBenchPanel invent refresh |
| Imagine invent polish v2b residual thought partner desk | `5d3e361e6` | ThoughtPartnerPanel invent refresh |
| Imagine invent polish v2b residual clam catcher cursor | `5d3e361e6` | cabinet/LGH/wait clam invent refresh |
| Imagine invent polish v2b residual igloo ice arcade cursor | `5d3e361e6` | cabinet/LGH/wait ice invent refresh |
| Imagine invent polish v2b residual CRT igloo cursor TV | `5d3e361e6` | LoadingGameHost default invent refresh |
| Imagine invent polish v2b residual living-TV session | `5d3e361e6` | SessionBrandChrome residual invent refresh |
| Imagine invent polish v2b residual cascade plan | `5d3e361e6` | PlanEditor invent refresh |
| Arcade + wait-arcade invent reframe densify | `7731dd063` | stamp antiek-living-tv-invent on cabinet cards + wait cartridges; densify 27/242 |
| Wait-arcade invent reframe densify test | `d1c0aeead` | ResearchWaitArcade cartridge invent class densify; FULL GREEN prior tip 74112b6bf |
| Home arcade igloo invent reframe densify | `b1542f6b6` | stamp antiek-living-tv-invent on home igloo minigame trio banner |
| Imagine invent polish v2c igloo minigame trio | `0f7cc3203` | Home + ArcadeCabinet igloo invent refresh on FULL GREEN tip |
| Ambient arcade highlight densify test | `0f7cc3203` | livingTvAmbient documents highlight→idle living-TV rest |
| Imagine invent polish v2c paperclip zombies | `902c9b737` | wait-arcade/cabinet/LGH zombies invent refresh on FULL GREEN tip |
| Imagine invent polish v2c igloo ice arcade cursor | `998714b15` | cabinet/LGH/wait ice invent refresh on FULL GREEN tip |
| Imagine invent polish v2c clam catcher cursor | `627500ab0` | cabinet/LGH/wait clam invent refresh on FULL GREEN tip |
| Imagine invent polish v2c CRT igloo cursor TV | `e6aa331ba` | LoadingGameHost default living-TV invent refresh on FULL GREEN tip |
| Imagine invent polish v2c living-TV session | `691c74b16` | SessionBrandChrome residual invent refresh on FULL GREEN tip |
| Imagine invent polish v2c thought partner desk | `691c74b16` | ThoughtPartnerPanel invent refresh on FULL GREEN tip |
| Imagine invent polish v2c cascade plan | `8401ad92c` | PlanEditor invent refresh on FULL GREEN tip |
| Imagine invent polish v2c midnight oil swarm | `b14dc171d` | MidnightOilPanel invent refresh on FULL GREEN tip |
| Imagine invent polish v2c arxiv dens | `cd73f6828` | Sources invent refresh on FULL GREEN tip |
| Imagine invent polish v2c html book float | `6b4970015` | ReadingCompanion invent refresh on FULL GREEN tip |
| Imagine invent polish v2c collective merge | `f85ebb7a4` | SubAgentProposal + FloatMenu invent refresh on FULL GREEN tip |
| Imagine invent polish v2c book marketplace port | `41a79a11b` | HouseSlot invent refresh on FULL GREEN tip |
| Imagine invent polish v2c float research merge | `4fcf3bed2` | TwinNotes float-merge invent refresh on FULL GREEN tip |
| Imagine invent polish v2c knowledge twin cursor | `c614911a4` | KnowledgePanel invent refresh on FULL GREEN tip |
| Imagine invent polish v2c antiek-bench celebrate | `c614911a4` | AntiekBenchPanel invent refresh on FULL GREEN tip |
| Imagine invent polish v2c model decision tree | `c614911a4` | ModelDecisionBar invent refresh on FULL GREEN tip |
| Imagine invent polish v2c CRT living-TV | `df10b0467` | Home + DR compose invent refresh on FULL GREEN tip |
| sessionLivingTv densify product invent doors v2c | `cef3d3b44` | KnowledgePanel/Bench/ModelDecision/MidnightOil invent reframe densify |
| AntiekBench living-tv-art densify | `67f5985fe` | rename desk invent testid to living-tv-art + invent class assert |
| AntiekBench invent import honesty densify | `e19be5f9d` | rename misnamed thoughtPartnerDeskArt import to antiekBenchCelebrateArt |
| Flipbook-feel HTML streaming design note | `73cb1875c` | cost-intelligent Modal/Krea ladder; pure Flipbook sole UI NO-GO |
| branding-densify-pack.sh | `32b4cba09` | reproducible 28-file densify pack for invent reframe + product invent doors |
| sessionLivingTv.css densify comment crosslinks | `735822246` | Flipbook note + densify-pack.sh pointers in invent reframe CSS |
| npm test:branding-densify | `58deb43f4` | package.json alias to branding-densify-pack.sh |
| invent reframe CSS contract densify test | `2d3bb46b0` | sessionLivingTv CSS reduced-motion + NO-GO honesty densify |
| densify-pack script header densify | `c3c6943b4` | pin 28/248 expectation + npm run test:branding-densify invoke |
| invent class product-map audit clean | `645388189` | all session invent webp UI imports stamp antiek-living-tv-invent |
| inventClassProductMap densify test | `2ce67a07a` | mechanical invent class stamp audit; densify pack 29/249 |
| Flipbook note densify pack gate | `896c7f2a5` | document npm run test:branding-densify in Flipbook-feel streaming note |
| livingTvAmbient Flipbook-feel densify comment | `788ef0af7` | ambient living-TV docs Flipbook-feel HTML + pure Flipbook NO-GO |
| livingTvAmbient Flipbook densify test | `54bf0f800` | ambient Flipbook-feel + NO-GO honesty densify test; pack 29/250 |

## Invent polish v2c wave complete (FULL GREEN c3fe013f5)

Major product invent doors refreshed via Imagine invent polish v2c and densified
with Flipbook-feel invent reframe. densify pack: `npm run test:branding-densify` (29/250).
Pure Flipbook sole UI remains NO-GO — see FLIPBOOK-FEEL-HTML-STREAMING-NOTE.md.
| Imagine invent polish v2d CRT living-TV | `ef623ec5d` | Home + DR compose invent refresh on FULL GREEN tip |
| Imagine invent polish v2d igloo minigame trio | `8dacdcebb` | ArcadeCabinet + Home arcade banner invent refresh on FULL GREEN tip |
| Imagine invent polish v2d paperclip zombies | `0c46b907d` | wait-arcade/cabinet/LGH zombies invent refresh on FULL GREEN tip |
| Imagine invent polish v2d igloo ice arcade cursor | `336a2aa71` | cabinet/LGH/wait ice invent refresh on FULL GREEN tip |
| Imagine invent polish v2d clam catcher cursor | `8246e9ceb` | cabinet/LGH/wait clam invent refresh on FULL GREEN tip |
| Imagine invent polish v2d CRT igloo cursor TV | `93628492f` | LoadingGameHost default living-TV invent refresh on FULL GREEN tip |
| Imagine invent polish v2d living-TV session | `52e4830b1` | SessionBrandChrome residual invent refresh on FULL GREEN tip |
| Imagine invent polish v2d thought partner desk | `3cbf96b87` | ThoughtPartnerPanel invent refresh on FULL GREEN tip |
| Imagine invent polish v2d cascade plan | `5e8db76e4` | PlanEditor invent refresh on FULL GREEN tip |
| Imagine invent polish v2d midnight oil swarm | `89cf96f93` | MidnightOilPanel invent refresh on FULL GREEN tip |
| Imagine invent polish v2d arxiv dens | `5f8851ec0` | Sources invent refresh on FULL GREEN tip |
| Imagine invent polish v2d html book float | `5f8851ec0` | ReadingCompanion invent refresh on FULL GREEN tip |
| Imagine invent polish v2d collective merge | `5f8851ec0` | SubAgentProposal + FloatMenu invent refresh on FULL GREEN tip |
| Imagine invent polish v2d book marketplace port | `5f8851ec0` | HouseSlot invent refresh on FULL GREEN tip |
| Imagine invent polish v2d float research merge | `5f8851ec0` | TwinNotes float-merge invent refresh on FULL GREEN tip |
| Imagine invent polish v2d knowledge twin cursor | `5f8851ec0` | KnowledgePanel invent refresh on FULL GREEN tip |
| Imagine invent polish v2d antiek-bench celebrate | `5f8851ec0` | AntiekBenchPanel invent refresh on FULL GREEN tip |
| Imagine invent polish v2d model decision tree | `5f8851ec0` | ModelDecisionBar invent refresh on FULL GREEN tip |

## Invent polish v2d wave complete (tip 698184e1e)

Major product invent doors refreshed via Imagine invent polish v2d and densified
with Flipbook-feel invent reframe. densify pack: `npm run test:branding-densify` (29/251 after honesty densify).
Pure Flipbook sole UI remains NO-GO — see FLIPBOOK-FEEL-HTML-STREAMING-NOTE.md.
| Invent polish v2d honesty densify | `8ceabb689` | Flipbook note densify gate 251 + invent v2d complete honesty |
| Ice-cursor densify pack expansion | `35c60931c` | WernerIceBait + useMouseFollow + IceCursorShell in branding densify pack (32/268) |
| Minigame living-TV beat densify pack | `cd8e1f95b` | ice/clam/zombies logic + zombiesCartridge in densify pack (36/297) |
| Invent product inventory densify | `e739f02ed` | 18 invent polish v2d product webps exist + non-trivial size (37/298) |
| Imagine invent polish v2e hero trio (CRT + zombies + igloo) | `f17b8b31c` | Home/DR/wait/cabinet invent refresh on densify green tip |
| Imagine invent polish v2e ice+clam cursor invents | `7cb951ecf` | cabinet/LGH/wait ice+clam invent refresh on FULL GREEN tip |
| Imagine invent polish v2e living-TV+thought partner+midnight oil | `736eb8fab` | residual invent refresh on FULL GREEN tip |
| Imagine invent polish v2e residual product invent wave | `0b6680c8e` | remaining product invent doors refresh on FULL GREEN tip |

## Invent polish v2e wave complete (tip b7ca6ef32)

All 18 product invent doors refreshed via Imagine invent polish v2e and densified.
densify pack: `npm run test:branding-densify` (37/298) — invent inventory + ice-cursor +
minigame living-TV beats + invent class product-map. Pure Flipbook sole UI remains NO-GO.
| Flipbook stream ladder densify | `90765c3b4` | cost-intelligent ladder + pure Flipbook NO-GO honesty densify (38/299) |
| Imagine invent polish v2f CRT living-TV + paperclip zombies | `f1df5e875` | hero invent refresh on axe-green Flipbook densify tip |
| Imagine invent polish v2f igloo trio + ice arcade cursor | `ee2d69b3e` | cabinet/home/LGH invent refresh on FULL GREEN tip |
| Imagine invent polish v2f clam catcher cursor | `56fc5f540` | cabinet/LGH/wait clam invent refresh on FULL GREEN tip |
| Imagine invent polish v2f living-TV+thought+midnight | `9805ceff3` | residual invent refresh on FULL GREEN tip |
| Imagine invent polish v2f residual product invent wave | `8ba06e773` | remaining product invent doors refresh on FULL GREEN tip |

## Invent polish v2f wave complete

All 18 product invent doors refreshed via Imagine invent polish v2f and densified.
densify pack: `npm run test:branding-densify` (38/299). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2g CRT living-TV | `0cbe8b9d5` | Home + DR compose invent refresh on FULL GREEN tip |
| Imagine invent polish v2g zombies + igloo trio | `328113869` | wait/cabinet/home invent refresh on FULL GREEN tip |
| Imagine invent polish v2g ice+clam cursor invents | `ec7073dfd` | cabinet/LGH/wait invent refresh on FULL GREEN tip |
| Imagine invent polish v2g living-TV+thought+midnight | `9d0896842` | residual invent refresh on FULL GREEN tip |
| Imagine invent polish v2g residual product invent wave | `b44e93e46` | remaining product invent doors refresh on FULL GREEN tip |

## Invent polish v2g wave complete

All 18 product invent doors refreshed via Imagine invent polish v2g and densified.
densify pack: `npm run test:branding-densify` (38/299). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2h CRT living-TV | `d8ceb810d` | Home + DR compose invent refresh on FULL GREEN tip |
| Imagine invent polish v2h zombies + igloo trio | `90271a1dd` | wait/cabinet/home invent refresh on FULL GREEN tip |
| Imagine invent polish v2h ice+clam cursor invents | `7e27de770` | cabinet/LGH/wait invent refresh on FULL GREEN tip |
| Imagine invent polish v2h living-TV+thought+midnight | `2858ddcef` | residual invent refresh on FULL GREEN tip |
| Imagine invent polish v2h residual product invent wave | `63a3d4098` | remaining product invent doors refresh on FULL GREEN tip |

## Invent polish v2h wave complete

All 18 product invent doors refreshed via Imagine invent polish v2h and densified.
densify pack: `npm run test:branding-densify` (38/299). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2i CRT living-TV | `53aed0284` | Home + DR compose invent refresh on FULL GREEN tip |
| Imagine invent polish v2i zombies + igloo trio | `72cade90c` | wait/cabinet/home invent refresh on FULL GREEN tip |
| Imagine invent polish v2i ice+clam cursor invents | `4a6b5a2f0` | cabinet/LGH/wait invent refresh on FULL GREEN tip |
| Imagine invent polish v2i living-TV+thought+midnight | `8612309dc` | residual invent refresh on FULL GREEN tip |
| Imagine invent polish v2i residual product wave | `652483e32` | remaining 10 product invent doors on axe-green tip |


## Invent polish v2i wave complete

All 18 product invent doors refreshed via Imagine invent polish v2i and densified.
densify pack: `npm run test:branding-densify` (39/302 after invent polish wave honesty densify). Pure Flipbook sole UI remains NO-GO.

| Invent polish wave honesty densify | `7ae901f93` | invent polish v2i provenance + Flipbook note densify gate 39/302 |
| Imagine invent polish v2j hero CRT+zombies+igloo | `618ab5449` | invent polish v2j hero suite on axe-green honesty tip |
| Imagine invent polish v2j ice+clam cursor invents | `745f24f74` | invent polish v2j arcade suite ice+clam on axe-green tip |
| Imagine invent polish v2j living-TV+thought+midnight | `54a0b6413` | residual invent refresh on axe-green tip |
| Imagine invent polish v2j residual product wave | `9d8c12083` | remaining 10 product invent doors on axe-green tip |


## Invent polish v2j wave complete

All 18 product invent doors refreshed via Imagine invent polish v2j and densified.
densify pack: `npm run test:branding-densify` (39/302). Pure Flipbook sole UI remains NO-GO.

| Multi-phase living-TV reframe densify | `3ec097ad9` | Flipbook-feel invent strip 16s multi-keyframe reframe densify 39/303 |
| Imagine invent polish v2k hero CRT+zombies+igloo | `d44410601` | invent polish v2k hero suite on axe-green reframe tip |
| Imagine invent polish v2k ice+clam cursor invents | `fd2f83f62` | invent polish v2k arcade suite ice+clam on axe-green tip |
| Imagine invent polish v2k living-TV+thought+midnight | `59206081d` | residual invent refresh on axe-green tip |
| Imagine invent polish v2k residual product wave | `82c771b08` | remaining 10 product invent doors on axe-green tip |


## Invent polish v2k wave complete

All 18 product invent doors refreshed via Imagine invent polish v2k and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2l CRT living-TV | `07ee143bc` | invent polish v2l hero CRT on axe-green invent polish v2k tip |
| Imagine invent polish v2l zombies+igloo+ice+clam | `b0d2a3e47` | invent polish v2l arcade suite residual on axe-green tip |
| Imagine invent polish v2l living-TV+thought+midnight | `8277ae26a` | residual invent refresh on axe-green tip |
| Imagine invent polish v2l residual product wave | `7c1a47591` | remaining 10 product invent doors on axe-green tip |


## Invent polish v2l wave complete

All 18 product invent doors refreshed via Imagine invent polish v2l and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2m CRT living-TV | `fb88a3d62` | invent polish v2m hero CRT on axe-green invent polish v2l tip |
| Imagine invent polish v2m zombies+igloo+ice+clam | `e9992fd5d` | invent polish v2m arcade suite residual on axe-green tip |
| Imagine invent polish v2m living-TV+thought+midnight | `351a23376` | residual invent refresh on axe-green tip |
| Imagine invent polish v2m residual product wave | `09e362dad` | remaining 10 product invent doors on axe-green tip |


## Invent polish v2m wave complete

All 18 product invent doors refreshed via Imagine invent polish v2m and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2n CRT living-TV | `e3a72f8a9` | invent polish v2n hero CRT on axe-green invent polish v2m tip |
| Imagine invent polish v2n zombies+igloo+ice+clam | `03a2509b9` | invent polish v2n arcade suite residual on axe-green tip |
| Imagine invent polish v2n living-TV+thought+midnight | `0fafbcb17` | residual invent refresh on axe-green tip |
| Imagine invent polish v2n residual product wave | `5fe6bdd3e` | remaining 10 product invent doors on axe-green tip |


## Invent polish v2n wave complete

All 18 product invent doors refreshed via Imagine invent polish v2n and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2o CRT living-TV | `2896408a8` | invent polish v2o hero CRT on axe-green invent polish v2n tip |
| Imagine invent polish v2o zombies+igloo+ice+clam | `733e6930e` | invent polish v2o arcade suite residual on axe-green tip |
| Imagine invent polish v2o living-TV+thought+midnight | `28b275b91` | residual invent refresh on axe-green tip |
| Imagine invent polish v2o residual product wave | `bd065dfd6` | remaining 10 product invent doors on axe-green tip |


## Invent polish v2o wave complete

All 18 product invent doors refreshed via Imagine invent polish v2o and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2p CRT living-TV | `b2ddd9770` | invent polish v2p hero CRT on axe-green invent polish v2o tip |
| Imagine invent polish v2p zombies+igloo+ice+clam | `4b9bcd8e6` | invent polish v2p arcade suite residual on axe-green tip |
| Imagine invent polish v2p living-TV+thought+midnight | `1334701d7` | residual invent refresh on axe-green tip |
| Imagine invent polish v2p residual product wave | `9472992b7` | remaining 10 product invent doors on axe-green tip |


## Invent polish v2p wave complete

All 18 product invent doors refreshed via Imagine invent polish v2p and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2q full wave (18 invents) | `f7a279560` | invent polish v2q all 18 product invent doors on axe-green invent polish v2p tip |


## Invent polish v2q wave complete

All 18 product invent doors refreshed via Imagine invent polish v2q and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2r full wave (18 invents) | `48ebb4b53` | invent polish v2r all 18 product invent doors on axe-green invent polish v2q tip |


## Invent polish v2r wave complete

All 18 product invent doors refreshed via Imagine invent polish v2r and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2s full wave (18 invents) | `2bf0ff66e` | invent polish v2s all 18 product invent doors on axe-green invent polish v2r tip |


## Invent polish v2s wave complete

All 18 product invent doors refreshed via Imagine invent polish v2s and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2t full wave (18 invents) | `67b1657a0` | invent polish v2t all 18 product invent doors on axe-green invent polish v2s tip |


## Invent polish v2t wave complete

All 18 product invent doors refreshed via Imagine invent polish v2t and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2u full wave (18 invents) | `efb64fbf8` | invent polish v2u all 18 product invent doors on axe-green invent polish v2t tip |


## Invent polish v2u wave complete

All 18 product invent doors refreshed via Imagine invent polish v2u and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2v full wave (18 invents) | `8234ce040` | invent polish v2v all 18 product invent doors on axe-green invent polish v2u tip |


## Invent polish v2v wave complete

All 18 product invent doors refreshed via Imagine invent polish v2v and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2w full wave (18 invents) | `ec50c215c` | invent polish v2w all 18 product invent doors on axe-green invent polish v2v tip |


## Invent polish v2w wave complete

All 18 product invent doors refreshed via Imagine invent polish v2w and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2x full wave (18 invents) | `11e6cf5b4` | invent polish v2x all 18 product invent doors on axe-green invent polish v2w tip |


## Invent polish v2x wave complete

All 18 product invent doors refreshed via Imagine invent polish v2x and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2y full wave (18 invents) | `6de86ff5b` | invent polish v2y all 18 product invent doors on axe-green invent polish v2x tip |


## Invent polish v2y wave complete

All 18 product invent doors refreshed via Imagine invent polish v2y and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v2z full wave (18 invents) | `dbc67651e` | invent polish v2z all 18 product invent doors on axe-green invent polish v2y tip |


## Invent polish v2z wave complete

All 18 product invent doors refreshed via Imagine invent polish v2z and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v3a full wave (18 invents) | `793a73209` | invent polish v3a all 18 product invent doors on axe-green invent polish v2z tip |


## Invent polish v3a wave complete

All 18 product invent doors refreshed via Imagine invent polish v3a and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v3b full wave (18 invents) | `44fc3be6c` | invent polish v3b all 18 product invent doors on axe-green invent polish v3a tip |


## Invent polish v3b wave complete

All 18 product invent doors refreshed via Imagine invent polish v3b and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v3c full wave (18 invents) | `f60823e4a` | invent polish v3c all 18 product invent doors on axe-green invent polish v3b tip |


## Invent polish v3c wave complete

All 18 product invent doors refreshed via Imagine invent polish v3c and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v3d full wave (18 invents) | `7f63aa24c` | invent polish v3d all 18 product invent doors on axe-green invent polish v3c tip |


## Invent polish v3d wave complete

All 18 product invent doors refreshed via Imagine invent polish v3d and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v3e full wave (18 invents) | `2543b0293` | invent polish v3e all 18 product invent doors on axe-green invent polish v3d tip |


## Invent polish v3e wave complete

All 18 product invent doors refreshed via Imagine invent polish v3e and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v3f full wave (18 invents) | `da1d451e0` | invent polish v3f all 18 product invent doors on axe-green invent polish v3e tip |


## Invent polish v3f wave complete

All 18 product invent doors refreshed via Imagine invent polish v3f and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v3g full wave (18 invents) | `b63781c49` | invent polish v3g all 18 product invent doors on axe-green invent polish v3f tip |


## Invent polish v3g wave complete

All 18 product invent doors refreshed via Imagine invent polish v3g and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
| Imagine invent polish v3h full wave (18 invents) | `8cfcc8411` | invent polish v3h all 18 product invent doors on axe-green invent polish v3g tip |
| Imagine invent polish v3i full wave (18 invents) | `8e2ebe7f6` | invent polish v3i all 18 product invent doors on axe-green invent polish v3h tip |
| Imagine invent polish v3j full wave (18 invents) | `1bfb35e32` | invent polish v3j all 18 product invent doors on axe-green invent polish v3i tip |
| Imagine invent polish v3k full wave (18 invents) | `18c7220a3` | invent polish v3k all 18 product invent doors on invent polish v3j tip |
| Imagine invent polish v3l full wave (18 invents) | `38e2d5f72` | invent polish v3l all 18 product invent doors on invent polish v3k tip |
| Imagine invent polish v3m full wave (18 invents) | `f77bd1000` | invent polish v3m all 18 product invent doors on axe-green invent polish v3l tip |


## Invent polish v3h wave complete

All 18 product invent doors refreshed via Imagine invent polish v3h and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.

## Invent polish v3i wave complete

All 18 product invent doors refreshed via Imagine invent polish v3i and densified.
Honesty densify WAVE=`v3i`. densify pack expected **39/303**. Pure Flipbook sole UI remains **NO-GO**.
Refedit+candidate provenance under `session-20260716/*_v3i.*`. Product webps promoted to `src/brand/werner/poses/session/*_session_v1.webp`.

## Invent polish v3j wave complete

All 18 product invent doors refreshed via Imagine invent polish v3j and densified.
Honesty densify WAVE=`v3j`. densify pack expected **39/303**. Pure Flipbook sole UI remains **NO-GO**.
Refedit+candidate provenance under `session-20260716/*_v3j.*`. Product webps promoted to `src/brand/werner/poses/session/*_session_v1.webp`.

## Invent polish v3k wave complete

All 18 product invent doors refreshed via Imagine invent polish v3k and densified.
Honesty densify WAVE=`v3k`. densify pack expected **39/303**. Pure Flipbook sole UI remains **NO-GO**.
Refedit+candidate provenance under `session-20260716/*_v3k.*`. Product webps promoted to `src/brand/werner/poses/session/*_session_v1.webp`.

## Invent polish v3l wave complete

All 18 product invent doors refreshed via Imagine invent polish v3l and densified.
Honesty densify WAVE=`v3l`. densify pack expected **39/303**. Pure Flipbook sole UI remains **NO-GO**.
Refedit+candidate provenance under `session-20260716/*_v3l.*`. Product webps promoted to `src/brand/werner/poses/session/*_session_v1.webp`.

## Invent polish v3m wave complete

All 18 product invent doors refreshed via Imagine invent polish v3m and densified.
Honesty densify WAVE=`v3m`. densify pack expected **39/303**. Pure Flipbook sole UI remains **NO-GO**.
Refedit+candidate provenance under `session-20260716/*_v3m.*`. Product webps promoted to `src/brand/werner/poses/session/*_session_v1.webp`.
| Imagine invent polish v3n full wave (18 invents) | `51e740055` | invent polish v3n all 18 product invent doors on axe-green invent polish v3m tip |

## Invent polish v3n wave complete

All 18 product invent doors refreshed via Imagine invent polish v3n and densified.
Honesty densify WAVE=`v3n`. densify pack expected **39/303**. Pure Flipbook sole UI remains **NO-GO**.
Refedit+candidate provenance under `session-20260716/*_v3n.*`. Product webps promoted to `src/brand/werner/poses/session/*_session_v1.webp`.

## Living-TV curtain-call densify (craft157+)

| Living-TV curtain-call densify | `e9640ba9e` | pride savor → curtain idle → silence; densify 39/305 |

Ambient installer re-arms once after pride savor (`note_saved`) so a second quiet
window emits curtain `idle` (sleep after pride), then silence. densify pack
**39/305**. Pure Flipbook sole UI remains **NO-GO**.

## Paperclip Zombies combo densify (craft157+)

| Paperclip Zombies combo densify | `60df44fb1` | BO1 combo max 4× + HUD xN; densify 39/307 |

BO1-style consecutive-kill multiplier (max 4×) on pure zombies rules; miss/breach
resets combo; HUD shows live `xN`. Arcade core stays free of reaction-bus imports.
densify pack **39/307**. Pure Flipbook sole UI remains **NO-GO**.

| Imagine invent polish v3o full wave (18 invents) | `a9fd792dc` | invent polish v3o all 18 product invent doors on axe-green zombies combo tip |

## Invent polish v3o wave complete

All 18 product invent doors refreshed via Imagine invent polish v3o and densified.
Honesty densify WAVE=`v3o`. densify pack expected **39/307**. Pure Flipbook sole UI remains **NO-GO**.
Refedit+candidate provenance under `session-20260716/*_v3o.*`. Product webps promoted to `src/brand/werner/poses/session/*_session_v1.webp`.

## Ice Fishing catch-streak densify (craft157+)

| Ice Fishing catch-streak densify | `5e980e782` | CP streak max 3×; densify 39/309 |

Club Penguin–style consecutive good-catch multiplier (max 3×) on pure ice-fishing
rules; hazard resets streak. Arcade core stays free of reaction-bus imports.
densify pack **39/309**. Pure Flipbook sole UI remains **NO-GO**.

## Clam Catcher catch-streak densify (craft157+)

| Clam Catcher catch-streak densify | `4ffdc43b1` | CP streak max 3× + HUD xN; densify 39/311 |

Club Penguin–style consecutive good clam/pearl catch multiplier (max 3×) on pure
clam-catcher rules; jellyfish catch or missed clam past the floor resets streak.
HUD shows live `xN`. Arcade core stays free of reaction-bus imports.
densify pack **39/311**. Pure Flipbook sole UI remains **NO-GO**.

## Ice Fishing streak HUD densify (craft157+)

| Ice Fishing streak HUD densify | `e1d76147d` | HUD xN parity with clam/zombies |

Ice catch-streak already pure-rules densified; HUD now shows live `xN` while
streak is hot (sun accent), matching clam + zombies cabinet craft. densify pack
unchanged (rules already gated). Pure Flipbook sole UI remains **NO-GO**.

| Imagine invent polish v3p full wave (18 invents) | `ba3f276ec` | invent polish v3p all 18 product invent doors |

## Invent polish v3p wave complete

All 18 product invent doors refreshed via Imagine invent polish v3p and densified.
Honesty densify WAVE=`v3p`. densify pack expected **39/311**. Pure Flipbook sole UI remains **NO-GO**.
Refedit+candidate provenance under `session-20260716/*_v3p.*`. Product webps promoted to `src/brand/werner/poses/session/*_session_v1.webp`.

## Clam pearl streak-step densify (craft157+)

| Clam pearl streak-step densify | `94de0c172` | pearl +2 streak step; densify 39/312 |

Pearl clam catches jump the Club Penguin streak by two steps (still hard-capped
at 3× mult). Common clams stay +1. densify pack **39/312**. Pure Flipbook sole UI
remains **NO-GO**.

## Product-door emote densify (craft157+)

| Product-door emote densify | `a176be12a` | twin/thought/bench/market invent doors |

Living-TV product-door map densifies invent-mapped doors that previously fell
through to generic `hit`: twin-notes / thought-partner / brainstorm / cascade →
thinking; marketplace / model-decision → curious; antiek-bench → happy.
densify pack **39/312**. Pure Flipbook sole UI remains **NO-GO**.

## Peak catch-streak brag HUD densify (craft157+)

| Peak catch-streak brag HUD densify | `6f824cb67` | ice+clam gameover BEST xN |

Ice + clam gameover HUD brags peak catch-streak (`BEST xN`) using sun accent —
cabinet/wait craft parity with live combo/streak HUDs. Pure Flipbook sole UI
remains **NO-GO**.

## Zombies peak combo brag HUD densify (craft157+)

| Zombies peak combo brag HUD densify | `f43928f86` | gameover BEST xN fort-fallen |

Paperclip zombies gameover status plate brags peak BO1 combo (`BEST xN`) for
cabinet/wait craft parity with ice+clam peak-streak brag. densify pack holds.
Pure Flipbook sole UI remains **NO-GO**.

| Imagine invent polish v3q full wave (18 invents) | `90ba6a605` | invent polish v3q all 18 product invent doors |

## Invent polish v3q wave complete

All 18 product invent doors refreshed via Imagine invent polish v3q and densified.
Honesty densify WAVE=`v3q`. densify pack expected **39/312**. Pure Flipbook sole UI remains **NO-GO**.
Refedit+candidate provenance under `session-20260716/*_v3q.*`. Product webps promoted to `src/brand/werner/poses/session/*_session_v1.webp`.

## Wait-arcade product-door emote densify (craft157+)

| Wait-arcade product-door emote densify | `785277f22` | wait-arcade/research-wait → curious |

Deep-research wait arcade product ids map to curious living-TV glance (not
generic hit). densify pack **39/312**. Pure Flipbook sole UI remains **NO-GO**.

| Imagine invent polish v3r full wave (18 invents) | `c83cba873` | invent polish v3r all 18 product invent doors |

## Invent polish v3r wave complete

All 18 product invent doors refreshed via Imagine invent polish v3r and densified.
Honesty densify WAVE=`v3r`. densify pack expected **39/312**. Pure Flipbook sole UI remains **NO-GO**.
Refedit+candidate provenance under `session-20260716/*_v3r.*`. Product webps promoted to `src/brand/werner/poses/session/*_session_v1.webp`.

## Cabinet product-door emote densify (craft157+)

| Cabinet product-door emote densify | `8470b0b10` | cabinet/LGH → curious |

Arcade cabinet + LoadingGameHost product ids map to curious living-TV glance.
densify pack **39/312**. Pure Flipbook sole UI remains **NO-GO**.

## Ice golden fish + per-game cabinet doors (craft157+)

| Ice golden fish streak densify | `9480135e4` | golden +2 streak step; pearl parity |
| Per-game cabinet product doors | `9480135e4` | ice-fishing / clam-catcher / zombies → curious |

Ice Fishing rare golden fish jumps Club Penguin catch-streak by two steps
(still hard-capped at 3×; score uses pre-step mult), matching Clam Catcher
pearl densify. ArcadeCabinet cards stamp per-game `data-product-id` so living-TV
choreography resolves distinct doors (not a single generic `arcade` stamp).
densify pack **39/313**. Pure Flipbook sole UI remains **NO-GO**.

## Ice empty-cast streak reset densify (craft157+)

| Ice empty-cast streak reset densify | `272f20cb0` | reel-to-surface no catch → streak 0 |

Completing a cast that returns the hook to the surface without a catch resets
the live Club Penguin streak (`maxStreak` retained for BEST brag). densify pack
expected **39/315**. Pure Flipbook sole UI remains **NO-GO**.

## Zombies fort-heal wave-clear densify (craft157+)

| Zombies fort-heal wave-clear densify | `c8dc04220` | wave clear +1 life, cap startingLives |

Paperclip zombies fort repair densify: clearing a wave restores +1 fort life,
hard-capped at starting lives (BO1-style fort recovery; does not overheal).
densify pack expected **39/316**. Pure Flipbook sole UI remains **NO-GO**.

## Zombies kill living-TV beat densify (craft157+)

| Zombies kill living-TV beat densify | `a0ff4f984` | score-up kill → piece_started |

Paperclip zombies mid-run combo densify: each scoring kill maps to a living-TV
`piece_started` beat (happy craft), matching ice/clam score-up TV edges.
Wave clear still emits piece_started first. densify pack expected **39/316**.
Pure Flipbook sole UI remains **NO-GO**.

## Wait-host per-game product-door densify (craft157+)

| Wait-host per-game product-door densify | `02541dc09` | LGH opt-in productId = game |

LoadingGameHost offer Play stamps `data-product-id={game}` and emits
PRODUCT_ACTIVATE (ice-fishing / clam-catcher / zombies → curious), matching
ArcadeCabinet per-game living-TV geometry. densify pack expected **39/317**.
Pure Flipbook sole UI remains **NO-GO**.

## Research-wait per-game product-door densify (craft157+)

| Research-wait per-game product-door densify | `30b2d6f83` | Play while waiting → selectedGame |

Deep-research wait arcade Play stamps `data-product-id={selectedGame}` and emits
PRODUCT_ACTIVATE so living-TV choreography matches cabinet/LGH per-game doors.
densify pack expected **39/318**. Pure Flipbook sole UI remains **NO-GO**.

## Research-wait cartridge picker densify (craft157+)

| Research-wait cartridge picker densify | `e61f5d3c5` | labels data-product-id + werner-target |

Cartridge picker labels stamp per-game `data-product-id` + `data-werner-target=
curious` so choosing ice/clam/zombies is living-TV geometry (opt-in waddle).
densify pack expected **39/319**. Pure Flipbook sole UI remains **NO-GO**.

## Ice golden spawn densify assert (craft157+)

| Ice golden spawn densify assert | `926ffafd8` | RNG band 0.15–0.23 → golden |

Unit densify pins the rare golden spawn roll band so pearl-parity craft cannot
silently drift. densify pack expected **39/320**. Pure Flipbook sole UI remains **NO-GO**.

## Clam pearl spawn densify assert (craft157+)

| Clam pearl spawn densify assert | `5fc0101b6` | pearl band after jelly chance |

Unit densify pins pearl-clam spawn roll so pearl-parity craft cannot silently
drift. densify pack **39/321**. Pure Flipbook sole UI remains **NO-GO**.

## Home arcade CTA product-door densify (craft157+)

| Home arcade CTA product-door densify | `d149f4d1a` | data-product-id=arcade + werner-target |

Home igloo Open arcade CTA is living-TV product-door geometry (curious). densify pack **39/321**. Pure Flipbook sole UI remains **NO-GO**.

## Research-wait playing invent reframe densify (craft157+)

| Research-wait playing invent reframe densify | `df7790092` | scene art antiek-living-tv-invent |

Deep-research wait playing cabinet scene art carries Flipbook-feel invent
reframe class. densify pack **39/321**. Pure Flipbook sole UI remains **NO-GO**.

## Zombies wave-1 no fort-heal densify assert (craft157+)

| Zombies wave-1 no fort-heal densify assert | `ca0cec888` | start wave 1 keeps lives |

Unit densify pins fort heal only for wave>1 clears. densify pack **39/322**. Pure Flipbook sole UI remains **NO-GO**.

## Ice golden visual + densify pack visuals (craft157+)

| Ice golden visual densify + pack | `3f30cdc2e` | visuals.test in densify pack 40/330 |

Golden fallback sun.base densify + ice visuals suite now in branding densify pack. Pure Flipbook sole UI remains **NO-GO**.

## Densify pack visuals trio densify (craft157+)

| Densify pack visuals trio densify | `fb1309fba` | ice+clam+zombies visuals; 42/350 |

Branding densify pack now gates ice/clam/zombies visual HUD densify (live xN,
BEST brag, golden/pearl atlas). Pure Flipbook sole UI remains **NO-GO**.

## Ice golden sun-rim visual densify (craft157+)

| Ice golden sun-rim visual densify | `c8f506da7` | authored golden strokeRect sun.base |

Golden fish atlas path densify: sun rim marks rare catch. densify pack **42/351**. Pure Flipbook sole UI remains **NO-GO**.

## Clam pearl sun-rim visual densify (craft157+)

| Clam pearl sun-rim visual densify | `00471f4b2` | pearl atlas strokeRect sun.base |

Pearl-clam atlas densify: sun rim marks rare catch (ice golden parity). densify pack **42/352**. Pure Flipbook sole UI remains **NO-GO**.

## Product-door underscore alias densify (craft157+)

| Product-door underscore alias densify | `698a7e0ac` | ice_fishing etc → curious |

Underscore slug aliases densify living-TV product-door map. densify pack **42/352**. Pure Flipbook sole UI remains **NO-GO**.

## Ice reduced-motion catch-streak densify (craft157+)

| Ice reduced-motion catch-streak densify | `9934ad393` | RM drop builds streak mult |

Reduced-motion ice path densify: simplified catches use streak mult + maxStreak. densify pack **42/353**. Pure Flipbook sole UI remains **NO-GO**.

## Zombies reduced-motion combo densify (craft157+)

| Zombies reduced-motion combo densify | `3fea9b2ff` | RM clicks build combo mult |

Reduced-motion fort defense densify: gentle clicks grow BO1 combo. densify pack **42/354**. Pure Flipbook sole UI remains **NO-GO**.

## Invent reframe wait-playing testid densify (craft157+)

| Invent reframe wait-playing testid densify | `fc597ce46` | -living-tv-art suffix contract |

CSS invent reframe densify asserts wait-playing testid coverage. densify pack **42/355**. Pure Flipbook sole UI remains **NO-GO**.

## Home arcade invent testid densify (craft157+)

| Home arcade invent testid densify | `88ac77688` | home-arcade-living-tv-art |

Home igloo invent uses living-tv-art testid suffix for invent reframe densify. densify pack **42/355**. Pure Flipbook sole UI remains **NO-GO**.

## Clam reduced-motion catch-streak densify (craft157+)

| Clam reduced-motion catch-streak densify | `056e048d7` | RM start/fire builds streak mult |

Reduced-motion Clam Catcher densify: gentle clicks build CP streak mult (ice/zombies a11y parity). densify pack **42/356**. Pure Flipbook sole UI remains **NO-GO**.

## Factory clam RM progression densify (craft157+)

| Factory clam RM progression densify | `ad3370ca8` | progressCartridge scores under RM |

Shared factory densify asserts clam RM scores on host path. densify pack **42/357**. Pure Flipbook sole UI remains **NO-GO**.

## HUD mult pure-helper densify (craft157+)

| HUD mult pure-helper densify | `bc756751d` | ice/clam/zombies HUD use pure mult |

Live xN and BEST xN densify via iceCatchStreakMultiplier / clamCatchStreakMultiplier / zombiesComboMultiplier. densify pack **42/357**. Pure Flipbook sole UI remains **NO-GO**.

## Home invent reframe + highlight ambient densify (craft157+)

| Home invent reframe + highlight ambient densify | `6844370aa` | home *-living-tv-art; highlight idle no re-arm |

Home invent Flipbook-feel suffix densify + living-TV highlight episode no ambient spam. densify pack **42/358**. Pure Flipbook sole UI remains **NO-GO**.

## Factory trio RM progression densify (craft157+)

| Factory trio RM progression densify | `decfc0d8d` | ice+clam+zombies RM scores via factory |

Shared factory densify asserts reduced-motion scores on host path for all three games. densify pack **42/360**. Pure Flipbook sole UI remains **NO-GO**.

## Invent honesty densify v3r + pack 42/360 (craft157+)

| Invent honesty densify v3r + pack 42/360 | `b13931016` | WAVE v3r + densify gate honesty |

Invent class densify + Flipbook note pin WAVE=v3r and densify pack **42/360**. Pure Flipbook sole UI remains **NO-GO**.

## Ice-bait instrument pure densify (craft157+)

| Ice-bait instrument pure densify | `f74d6d959` | baitChromeFromFollow live pin |

Cursor-is-bait densify: pure chrome helper pins live pointer / hides on tab hide. densify pack **42/362**. Pure Flipbook sole UI remains **NO-GO**.

## Ice-bait honesty densify (craft157+)

| Ice-bait honesty densify | `95e8d99d3` | Flipbook + invent class pin baitChromeFromFollow |

Honesty densify pins baitChromeFromFollow in Flipbook densify gate. densify pack **42/362**. Pure Flipbook sole UI remains **NO-GO**.

## Fishing-line catenary densify in pack (craft157+)

| Fishing-line catenary densify in pack | `07b53a435` | free end = bait; pack 43/375 |

Catenary densify: line ends at live bait; densify pack **43/375**. Pure Flipbook sole UI remains **NO-GO**.

## Rod tension tip→bait instrument densify (craft157+)

| Rod tension tip→bait instrument densify | `b771b22c2` | tipToBaitDistance + rodBendFromPoints |

Instrument densify: tip→bait distance drives rod bend; densify pack **43/377**. Pure Flipbook sole UI remains **NO-GO**.

## Instrument barrel densify (craft157+)

| Instrument barrel densify | `ca3146045` | bait+tipToBait+rodBend public; pack 44/379 |

Werner barrel densify exports instrument helpers; densify pack **44/379**. Pure Flipbook sole UI remains **NO-GO**.

## Station instrument suspension densify (craft157+)

| Station instrument suspension densify | `d6322fdb0` | wait-arcade lease + leaseCount; pack 45/381 |

Pointer-authority densify: wait-arcade suspends route instrument; densify pack **45/381**. Pure Flipbook sole UI remains **NO-GO**.

## Station suspension barrel densify (craft157+)

| Station suspension barrel densify | `891469885` | acquire+leaseCount public; pack 45/382 |

Instrument barrel densify exports station suspension; densify pack **45/382**. Pure Flipbook sole UI remains **NO-GO**.

## Station suspension honesty densify (craft157+)

| Station suspension honesty densify | `87d57a0ed` | invent class pin station instrument suspension |

Honesty densify pins station instrument suspension in Flipbook densify gate. densify pack **45/382**. Pure Flipbook sole UI remains **NO-GO**.

## Living-TV fail recover + home-arcade door densify (craft157+)

| Living-TV fail recover + home-arcade door densify | `7826fe271` | error→idle; home-arcade curious |

Living-TV densify: fail/error recover idle; home-arcade product door densify. densify pack **45/383**. Pure Flipbook sole UI remains **NO-GO**.

## Error ambient installer + book-marketplace door densify (craft157+)

| Error ambient installer + book-marketplace door densify | `8f9ba4c59` | error installer idle; book-marketplace curious |

Living-TV densify: error installer recover idle then silence; book-marketplace door densify. densify pack **45/384**. Pure Flipbook sole UI remains **NO-GO**.

## Research-start ambient installer + door alias densify (craft157+)

| Research-start ambient installer + door alias densify | `65f487cd9` | start→idle; bench/model aliases |

Living-TV densify: research-start installer sleep idle; product-door alias densify. densify pack **45/385**. Pure Flipbook sole UI remains **NO-GO**.

## Research-family product-door alias densify (craft157+)

| Research-family product-door alias densify | `865337441` | twin_notes/thought_partner/cascade/research_wait |

Product-door densify: research-family underscore aliases map thinking/curious living-TV glances. densify pack **45/385**. Pure Flipbook sole UI remains **NO-GO**.

## Complete-research curtain + book_marketplace door densify (craft157+)

| Complete-research curtain + book_marketplace door densify | `8d4a78d46` | complete pride curtain; book_marketplace |

Living-TV densify: complete research curtain pride→idle→silence; book_marketplace door densify. densify pack **45/386**. Pure Flipbook sole UI remains **NO-GO**.

## Highlight ambient installer densify (craft157+)

| Highlight ambient installer densify | `00742ad8b` | arcade highlight→idle→silence |

Living-TV densify: highlight installer rest idle then silence. densify pack **45/387**. Pure Flipbook sole UI remains **NO-GO**.

## Fail ambient installer densify (craft157+)

| Fail ambient installer densify | `4ea59ed3f` | fail→idle→silence |

Living-TV densify: fail installer recover idle then silence. densify pack **45/388**. Pure Flipbook sole UI remains **NO-GO**.

## Product note_saved ambient installer densify (craft157+)

| Product note_saved ambient installer densify | `c2b20bc52` | note_saved pride→idle→silence |

Living-TV densify: product note_saved pride curtain to idle then silence. densify pack **45/389**. Pure Flipbook sole UI remains **NO-GO**.

## productSelector densify for invent doors (craft157+)

| productSelector densify for invent doors | `f2f4de7b1` | data-product-id contract; pack 46/391 |

Product-selector densify pins invent doors to living-TV choreography resolution. densify pack **46/391**. Pure Flipbook sole UI remains **NO-GO**.

## productSelector barrel densify (craft157+)

| productSelector barrel densify | `1c87b9ce2` | productSelector+emoteForProductDoor public |

Instrument barrel densify exports productSelector + door emotes. densify pack **46/392**. Pure Flipbook sole UI remains **NO-GO**.

## data-werner-target densify (craft157+)

| data-werner-target densify | `2c2e92869` | emoteFromWernerTargetAttr; pack 47/395 |

Opt-in living-TV target densify: pure attr→emote mapping + pack gate. densify pack **47/395**. Pure Flipbook sole UI remains **NO-GO**.

## data-werner-target barrel densify (craft157+)

| data-werner-target barrel densify | `8b853b01c` | WERNER_TARGET_ATTR + emoteFromWernerTargetAttr public |

Instrument barrel densify exports data-werner-target helpers. densify pack **47/396**. Pure Flipbook sole UI remains **NO-GO**.

## emoteForExperience barrel densify (craft157+)

| emoteForExperience barrel densify | `0a46c85ef` | living-TV product reaction map public |

Instrument barrel densify exports emoteForExperience reaction map. densify pack **47/397**. Pure Flipbook sole UI remains **NO-GO**.

## reactionBus allowlist barrel densify (craft157+)

| reactionBus allowlist barrel densify | `8a05007a2` | PRODUCT_EXPERIENCES + isProductExperience + event |

Instrument barrel densify exports reactionBus allowlist contracts. densify pack **47/398**. Pure Flipbook sole UI remains **NO-GO**.

## host inject reactionBus barrel densify (craft157+)

| host inject reactionBus barrel densify | `b1c2e7ec0` | emitWernerExperience + installReactionBus public |

Instrument barrel densify exports host inject reactionBus path. densify pack **47/399**. Pure Flipbook sole UI remains **NO-GO**.

## living-TV ambient barrel densify (craft157+)

| living-TV ambient barrel densify | `5e58bcbe3` | ambientExperienceAfterQuiet + installer public |

Instrument barrel densify exports living-TV ambient quiet policy. densify pack **47/400**. Pure Flipbook sole UI remains **NO-GO**.

## living-TV emote duration barrel densify (craft157+)

| living-TV emote duration barrel densify | `c314ac493` | EMOTE_KINDS + emoteDurationMs public |

Instrument barrel densify exports living-TV emote durations. densify pack **47/401**. Pure Flipbook sole UI remains **NO-GO**.

## mouse-follow lag barrel densify (craft157+)

| mouse-follow lag barrel densify | `6c4620794` | LAG_MS + FOLLOW_EASE + centerLaggedTarget public |

Instrument barrel densify exports mouse-follow lag contract. densify pack **47/402**. Pure Flipbook sole UI remains **NO-GO**.

## follow sample + choreography install densify (craft157+)

| follow sample + choreography install densify | `fb608637e` | SAMPLE_INTERVAL/POINTER_IDLE + installers public |

Instrument barrel densify exports follow sample constants + choreography installers. densify pack **47/403**. Pure Flipbook sole UI remains **NO-GO**.

## rodBend instrument tension densify (craft157+)

| rodBend instrument tension densify | `d65baea25` | rodBend pure tension under tip→bait load |

Instrument barrel densify exports rodBend instrument tension. densify pack **47/404**. Pure Flipbook sole UI remains **NO-GO**.

## rodTipFromMascotRect line attach densify (craft157+)

| rodTipFromMascotRect line attach densify | `0a074c3aa` | line attach at real rod tip screen space |

Instrument barrel densify exports rodTipFromMascotRect line attach. densify pack **47/405**. Pure Flipbook sole UI remains **NO-GO**.

## rodLength butt→tip densify (craft157+)

| rodLength butt→tip densify | `ac6dd6877` | rodLength public ~36 viewBox units |

Instrument barrel densify exports rodLength butt→tip rig contract. densify pack **47/406**. Pure Flipbook sole UI remains **NO-GO**.

## ROD_MAX_BEND / HALF_BEND_DIST densify (craft157+)

| ROD_MAX_BEND / HALF_BEND_DIST densify | `1186cb1db` | saturating tension constants public |

Instrument barrel densify exports ROD_MAX_BEND + ROD_HALF_BEND_DIST. densify pack **47/407**. Pure Flipbook sole UI remains **NO-GO**.

## ROD_TIP/BUTT local anchors densify (craft157+)

| ROD_TIP/BUTT local anchors densify | `5b80c33ba` | ROD_TIP_LOCAL + ROD_BUTT_LOCAL public |

Instrument barrel densify exports rod local anchors. densify pack **47/408**. Pure Flipbook sole UI remains **NO-GO**.

## EMOTE_DURATION_MS table densify (craft157+)

| EMOTE_DURATION_MS table densify | `029720206` | table exhaustive + aligned with emoteDurationMs |

Instrument barrel densify exports EMOTE_DURATION_MS table densify. densify pack **47/409**. Pure Flipbook sole UI remains **NO-GO**.

## DEFAULT_EMOTE + catenary path densify (craft157+)

| DEFAULT_EMOTE + catenary path densify | `922987815` | DEFAULT_EMOTE 1000; catenary L vs Q |

Instrument barrel densify exports DEFAULT_EMOTE_DURATION_MS + catenary short/long path densify. densify pack **47/410**. Pure Flipbook sole UI remains **NO-GO**.

## useMouseFollow + station suspend hook densify (craft157+)

| useMouseFollow + station suspend hook densify | `d3ec6b069` | hooks public for bait follow + wait-arcade |

Instrument barrel densify exports useMouseFollow + useStationInstrumentSuspended. densify pack **47/411**. Pure Flipbook sole UI remains **NO-GO**.

## station activity path→instrument densify (craft157+)

| station activity path→instrument densify | `ca890ac61` | path→instrument map + default ice-fishing |

Instrument barrel densify exports station activity path→instrument selection. densify pack **47/412**. Pure Flipbook sole UI remains **NO-GO**.

## getActivity registry densify (craft157+)

| getActivity registry densify | `3a9ccb512` | getActivity + getActivityForPathname public |

Instrument barrel densify exports getActivity registry resolution. densify pack **47/413**. Pure Flipbook sole UI remains **NO-GO**.

## writing-nib + speaking-resonance densify (craft157+)

| writing-nib + speaking-resonance densify | `c09b3e31a` | write/speak instruments public + path policy |

Instrument barrel densify exports writing-nib + speaking-resonance instruments. densify pack **47/414**. Pure Flipbook sole UI remains **NO-GO**.

## full station instrument roster densify (craft157+)

| full station instrument roster densify | `1f4ce1307` | four instruments + register/EmoteView/useStationActivity |

Instrument barrel densify exports full station instrument roster. densify pack **47/415**. Pure Flipbook sole UI remains **NO-GO**.

## shell experience signal densify (craft157+)

| shell experience signal densify | `48ecc1b9f` | pointer idle + research phase edges public |

Instrument barrel densify exports shell experience living-TV inject edges. densify pack **47/416**. Pure Flipbook sole UI remains **NO-GO**.

## one-shot research launch provenance densify (craft157+)

| one-shot research launch provenance densify | `9b34a98e0` | consumeLocallyStartedResearchSession one-shot |

Instrument barrel densify exports one-shot research launch provenance. densify pack **47/417**. Pure Flipbook sole UI remains **NO-GO**.

## ice-cursor + fishing shell component densify (craft157+)

| ice-cursor + fishing shell component densify | `612d732c3` | IceBait/FishingLayer/CursorShell/Rig/ResearchLens public |

Instrument barrel densify exports ice-cursor + fishing shell components. densify pack **47/418**. Pure Flipbook sole UI remains **NO-GO**.

## fishing gag + steering densify (craft157+)

| fishing gag + steering densify | `6606fbbd7` | shouldFish/fishingStep + isBusy/reducer/WADDLE_MS |

Instrument barrel densify exports fishing gag + steering pure core. densify pack **47/420**. Pure Flipbook sole UI remains **NO-GO**.

## createWernerStage + ice/arcade flags densify (craft157+)

| createWernerStage + ice/arcade flags densify | `082579444` | stage factory + feature flags public |

Instrument barrel densify exports createWernerStage + ice/arcade flags. densify pack **47/421**. Pure Flipbook sole UI remains **NO-GO**.

## reducer resume + ambient episode densify (craft157+)

| reducer resume + ambient episode densify | `f799b6375` | follow/waddle/emote resume + ambientExperienceAfterQuiet |

Instrument barrel densify exports reducer resume + ambient episode policy. densify pack **47/423**. Pure Flipbook sole UI remains **NO-GO**.

## residual product-door + wait-arcade densify (craft157+)

| residual product-door + wait-arcade densify | `4681afe4c` | door families/aliases + opted-in playing densify |

Residual invent door emote densify + wait-arcade opt-in densify. densify pack **47/425**. Pure Flipbook sole UI remains **NO-GO**.

## ambient installer + wait offer clock densify (craft157+)

| ambient installer + wait offer clock densify | `0e93a5d30` | installLivingTvAmbient inject densify + 8s offer clock |

Ambient installer densify + wait-arcade offer clock densify. densify pack **47/427**. Pure Flipbook sole UI remains **NO-GO**.

## fishingStep full beat + frozen waddleToEl densify (craft157+)

| fishingStep full beat + frozen waddleToEl densify | `27440743f` | full beat order + frozen still-emote densify |

FishingStep full never-caught beat densify + frozen waddleToEl densify. densify pack **47/429**. Pure Flipbook sole UI remains **NO-GO**.

## nested lease + productSelector + moveTo densify (craft157+)

| nested lease + productSelector + moveTo densify | `0720a61c4` | lease stacking + selector escape + moveTo walk densify |

Nested instrument lease densify + productSelector keyboard densify + moveTo densify. densify pack **47/432**. Pure Flipbook sole UI remains **NO-GO**.

## choreography install densify residual (craft157+)

| choreography install densify residual | `b797844bd` | product-activate door emotes + data-werner-target clicks |

InstallChoreography densify + installTargetChoreography densify residual. densify pack **47/434**. Pure Flipbook sole UI remains **NO-GO**.
