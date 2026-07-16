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

Cursor model: ice bait instrument (not chase). Station re-home on drag.

