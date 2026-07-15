# Werner ambient authority — Cycle 569

Status: verified and transport-ready; no merge or deployment.

## Decision

Pointer idle has one live owner: the selected station activity's ambient. It
must not also impersonate a product event and mount the bounded sleeping emote.
`stationAmbientClass` is now the pure decision point for whether an activity's
pointer-active or pointer-idle class may run. Product emotes, directed travel,
return-home, drag, hidden tabs, reduced motion, and disabled activity all
withhold ambient authority.

## Contradiction removed

Before this slice, the same `pointerIdle >= 2s` level did two independent
things in `PenguinMascot`: it added the activity's `werner-fishing` class and
emitted `ProductExperience "idle"`, which the reaction bus translated into a
2.4-second sleeping overlay. The base fishing rig became hidden while its CSS
gag continued underneath, then reappeared mid-cycle. That was neither a
persistent sleep lifecycle nor one-character choreography.

The generic reaction vocabulary now contains only product facts: highlight,
deep-research start/complete/error, and failure. Sleeping remains an available
authored emote for a future truthful lifecycle, but pointer idleness no longer
fires it.

## Truth table

The activity class for the current pointer level is returned only when it
exists, the activity is enabled, motion is allowed, the page is visible, and
Werner is not dragging, travelling out, returning home, or showing a product
emote. Every foreground-owned or undeclared combination returns `null`.

## Why waking remains deferred

The ChatGPT Image waking asset still has no truthful predecessor state. This
slice is the prerequisite ownership repair, not permission to import that
asset. A later sleep→wake state must define persistence, interruption and
cleanup across the same foreground gates and prove its live production caller.

## Engine audit

Codex GPT-5.6-sol and MiMo V2.5 Pro completed repository inspection but their
initial continuation calls emitted no final verdict. GLM `/ultracode` at
maximum effort activated twice but swallowed the attached task and waited for
input. No multi-model consensus is claimed. After two documentation findings
were sharpened, an independent GPT-5.6-sol adversarial re-review returned exact
`VERDICT: ACCEPT`. The decision follows directly from the reproduced dual owner
in production and preserves the ratified endless-fishing behavior.

## Withheld authority

No waking asset import, persistent sleep/wake lifecycle, fifth mood,
time-of-day/scene authority, activity registry redesign, fishing timing/art,
pointer threshold, route, cursor/game rule, backend, network, model spend,
merge, or deployment.
