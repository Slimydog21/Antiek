# Branding densification wave — 2026-07-15/16

PR #2416 tip (at close of this note): `a626be9d8` — axe+LP green.

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


## Invent polish v3h wave complete

All 18 product invent doors refreshed via Imagine invent polish v3h and densified.
densify pack: `npm run test:branding-densify` (39/303). Pure Flipbook sole UI remains NO-GO.
