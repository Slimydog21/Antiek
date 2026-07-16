# Antiek branding — living TV show (Werner at home)

Craft doctrine for the branding/UI session: **Antiek is the home of the penguin.**
Werner is an asynchronous TV-show living in the background of the HTML shell —
not a pure Flipbook pixel stream, but Flipbook *feel* over real product chrome.

## Product surfaces (shipped on PR stack)

| Surface | Behavior |
|---|---|
| Flipbook scenery hotspots | Edge-only adaptive rects; click → product routes; peak-left ambient for honesty proof |
| Product map | igloo→`/arcade`, horizon→`/`, peak-right→`/library`, sky-aurora→`/home` |
| Session brand PNGs | thinking/celebrate moods + ice fishing/zombies/clam catcher cabinet key art (alpha integrity gated) |
| Arcade cabinet | Club Penguin–style Ice Fishing + Clam Catcher + Paperclip Zombies easter egg; play emits Werner highlight |
| Research wait arcade | Same session key art during deep research waits |
| LoadingGameHost | Opt-in wait host with pure policy (`waitHostLogic`) + shared cartridge factory |
| Reaction bus | Product experiences → Werner emotes (highlight, deep research lifecycle, fail) |
| Settings | Live decision tree (server) + heuristic tree + NotDiamond shadow + Midnight Oil preflight |
| Budget projection | Over budget → Werner `fail`; within budget → `highlight` |
| Product doors | Library + Research home: session thinking mark; Write home: session celebrate mark; Antiek-bench panel: thinking mark |
| Cursor / station | Werner does **not** chase the cursor; ice bait is the cursor instrument |

## Imagine inventory (not product-mapped)

`session-20260715/` — living TV, ice fishing, zombies candidates from Grok Imagine
and reference-edit off the product thinking pose. Promote only through
`sessionAssets` + integrity tests + UI import.

## Flipbook honesty

Pure generative Flipbook (no HTML, video stream only) remains **NO-GO** for the
sole product UI. HTML + adaptive hotspots + living scene is the executable path.
Modal/Krea remain available for scenery enrichment under cost discipline.

## Craft bar

James Hawkins / PostHog: every visual and interaction element must be load-bearing.
No inventory-only PNGs in the product path. No auto-launched games over primary work.

## Densify wave (2026-07-16) — product experiences

| Trigger | Experience / event | Emote |
|---|---|---|
| Product door (scenery / Home cards) | PRODUCT_ACTIVATE / emoteForProductDoor | per-door map |
| Library open book | highlight | curious |
| Write create piece | piece_started | happy |
| Speak create project | piece_started | happy |
| LoadingGameHost opt-in play | highlight | curious |
| Thought partner open sidecar | highlight | curious |
| Cabinet play | highlight | curious |
| Deep research lifecycle | deep_research_* | thinking/happy/dizzy |
| FloatMenu confirmed note | note_saved | noted |
| Budget over | fail | dizzy |
| Biography CTA | piece_started | happy |
| Midnight Oil goal add | highlight | curious |
| Research corpus absorb | highlight | curious |

## Living-TV invent chrome (session webp/PNG, 2026-07-16)

UI-consumed invent strips (not inventory-only):

- Login, Research, Write, Library, Speak doors — `werner_living_tv_session_v1.webp`
- Home arcade + ArcadeCabinet — `werner_igloo_arcade_session_v1.webp`
- ThoughtPartner + Antiek-bench — `werner_thought_partner_desk_session_v1.webp`
- LoadingGameHost — game-specific session PNG via `waitHostBrandArt` (default living-TV webp)
- Midnight Oil panel — living-TV webp
- ReadingCompanion (in-book glass-box) — thinking mark + living-TV webp
- ResearchThis page spin — `notifyResearchStarted` → deep_research_start
- TalkToBook open/answer — highlight / note_saved / fail
- VoiceNote save — note_saved
- Biography landing — session thinking brand mark
- PersonalSpace / MetaReading — living-TV invent strips
- Outcomes audit door — thinking mark + living-TV invent (`outcomes-home-*`)
- Notebooks door — thinking mark + living-TV invent (`notebooks-home-*`)
- Wrestle empty state — thinking mark + living-TV invent (`wrestle-empty-*`)
- Documents / Investigations doors — thinking + living-TV invent
- Settings operator door — thinking + living-TV invent
- Home front door — living-TV invent strip under hero Werner
- Investigations start → `deep_research_start` living-TV beat
- Sources door — thinking + living-TV invent; ingest → `highlight`
- Brainstorm empty — thinking + living-TV invent; launch → `deep_research_start`
- Midnight Oil panel — dedicated midnight-oil invent webp (late-night desk swarm)
- Operator / Privacy dashboards — thinking + living-TV invent
- Residual doors via `SessionBrandChrome` — Trust, Billing, Pricing, Map,
  Stats, Replay, Federation, Loop3, Payouts, SkillRules, Interviews, Multimedia

## Product-door emote map (expanded 2026-07-16)

| Product id family | Emote |
|---|---|
| research, library, investigations, documents, notebooks | thinking |
| read, speak, arcade, sources | curious |
| write, home, create | happy |
| more, settings, billing, pricing | noted |
| midnight-oil / midnight_oil | sleeping |
| (other) | hit |

DRW glass-box densify: ComposeBar CRT invent + PlanEditor living-TV strip;
cascade create → `piece_started`; plan approve → `highlight`; launch →
`notifyResearchStarted` / deep_research_start.

## Ambient living-TV heartbeat (2026-07-16)

`installLivingTvAmbient` (wired in `PenguinMascot`) emits a soft `idle` →
sleeping emote after ~90s without product experiences, re-arms after any
`antiek:werner-experience`, and stays off under `prefers-reduced-motion`.
Cursor model unchanged: ice bait instrument, no chase.

## SessionBrandChrome (densify hard-to-vary)

`src/brand/SessionBrandChrome.tsx` is the load-bearing header pattern for
operator/product index doors: session thinking PNG + living-TV invent strip +
prefixed testids (`{prefix}-werner-brand`, `{prefix}-living-tv-art`). Prefer this
component for new doors over hand-rolled invent chrome so invent never stays
inventory-only.

Cursor model: ice bait instrument (not chase). Station re-home on drag.

## Honest residuals (branding)

- Pure Flipbook sole UI: **NO-GO** (HTML + adaptive hotspots is the path)
- Curious v2 session PNG: alpha-honest candidate; product curious remains
  CSS/SVG semantic reactions (Werner moods stay 4-slot: idle/thinking/empty/celebrate)
- Operator merge wall on PR #2416

