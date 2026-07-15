# Decision: make Zombies an archival field station

Status: implemented on a production-default-off stacked branch; not merged or deployed.

## Decision

Paperclip Zombies keeps its exact deterministic rules and replaces only its canvas projection.
The board is now a night research field station: a brass accordion-file fort protects the left
edge, ruled evidence traces cross a glacial alpine field, and wholesome articulated paperclips
travel those traces. The trace is the one deliberate visual risk. It connects the game to the
research wait instead of applying an interchangeable arcade skin.

## Visual grammar

- A quiet mono status tape reports wave, score, and fort lives.
- The fort is an archive, not a military bunker; drawers and a single lemon diamond carry the
  Antiek identity without adding a second Werner.
- Enemies are nested paperclip loops with aurora arms and tiny lemon HP pips. There are no guns,
  gore, weapons, military marks, or generic neon.
- Ready, playing, fallen, and exited states use one stable bottom plate with exact action copy.
- All colors and type come from `design/tokens.ts`; no runtime image or generated layout ships.

## Authority boundary

`drawZombiesScene` receives an existing immutable state snapshot and canvas dimensions. It cannot
read input, time, research, storage, network, model, or spend state. It does not mutate the game.
Spawn, movement, hitboxes, score, lives, waves, exit, teardown, focus, and reduced-motion behavior
remain owned by the already-reviewed engine and pure rules.

## Provenance

The Cycle 559 ChatGPT Image field-station concept supplied the archival drawer, brass trace, and
alpine-night direction. The bitmap remains provenance-only and is not imported by product code.
