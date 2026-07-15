# Decision: embed the arcade in live Deep Research

Status: implemented on a production-default-off stacked branch; not merged or deployed.

## Decision

Paperclip Zombies is offered inside the existing Deep Research monitor after eight seconds of
a valid, nonterminal durable session. It is dynamically loaded and starts only after an explicit
button press. A standalone cabinet is deferred because it does not satisfy the operator's core
promise: something playful to do while a series of researches is actually running.

The durable `useResearchSession` snapshot owns eligibility. The arcade cannot infer completion,
pause research, delay results, or survive an all-terminal render. Partial results, cost,
reconnecting truth, and steering remain mounted throughout play.

## Identity and race policy

One wait episode is `${sessionId}:${sessionGeneration}`. The generation matters because plan
relaunch can reuse a deterministic session ID. A new episode remounts the host and resets the
offer timer, opt-in, focus state, cartridge, and score. Terminal state and reduced motion remove
the lazy subtree synchronously; `ArcadeMount` cleanup then stops its loop and input listeners.

## Accessibility

The offer never moves focus. Explicit Play may focus the canvas. Escape and a visible Exit game
button both leave gameplay. Voluntary exit returns focus to the Play button; authoritative
completion returns focus to the stable monitor heading only when focus was inside the arcade.
Keyboard capture is scoped to the host subtree, so redirect inputs and workstation controls keep
their normal keys. Reduced-motion users receive the unchanged professional monitor and do not
load the arcade surface.

## Authority and non-goals

The flag `VITE_WERNER_RESEARCH_WAIT_ARCADE=1` is required; default is off. There is no route,
cabinet, autoplay, automatic focus, persistence, leaderboard, telemetry, network, research
content access, backend change, model/spend authority, generated runtime bitmap, second Werner,
or result/reaction semantic change. Calm mode has no authoritative current product signal and is
therefore not invented in this slice.

Primitive canvas shapes prove mechanics only. A future visual-craft sprint may replace game
rendering after live product/browser acceptance, without changing this lifecycle contract.
