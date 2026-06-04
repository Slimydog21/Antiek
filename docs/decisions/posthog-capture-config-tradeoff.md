# PostHog capture config — explicit flags vs the dated `defaults` bundle

**Decision date:** 2026-06-04
**Status:** ⚖️ OPEN — both options are presented; the operator decides. Current code (PR #74) uses explicit flags.
**Owner:** operator (PostHog Analytics Hardening)

## The trade-off

`apps/reading/src/lib/posthogClient.ts` configures capture **explicitly**:

```
capture_pageview: true,   // initial load + SPA route changes
capture_pageleave: true,
autocapture: true,        // element text scrubbed by before_send
person_profiles: "identified_only",
disable_session_recording: true,
before_send: sanitizeOutgoingEvent,
```

This replaced a dated **`defaults: "2026-01-30"`** bundle. The two are genuine
alternatives, and the choice is not obvious — both sides are steelmanned below.
**This record does not decide it; the operator does** (it is an Open Question in
the master spec).

### Steelman for the explicit config (current, PR #74)

- **Hard-to-vary + verifiable.** Every capture behaviour is stated in code at the
  call site; you can read posthogClient.ts and know exactly what is captured. No
  hidden, version-dated behaviour.
- **It fixed a real zero-capture.** A future-dated `defaults: "2026-01-30"` left
  prod initialized but capturing ZERO events — the SDK had no defaults set for a
  future date, so remote config / flags / surveys loaded but nothing egressed on
  load, SPA navigation, or click (confirmed against the live bundle and the
  PostHog events API; no JS errors, no opt-out, no quota). Explicit flags make
  capture fully determined and cannot be silently emptied by a date the SDK
  doesn't recognize.
- **Aligns with the §9.0 posture.** Explicit `autocapture: true` paired with the
  `before_send` firewall makes the autocapture-ON-but-scrubbed decision legible
  in one file (see `posthog-content-firewall.md`).

### Steelman for reverting to the `defaults` bundle

This is a real option, presented fairly:

- **It auto-enables features the explicit config DROPS.** PostHog's defaults
  bundle turns on `rageclick`, **web-vitals** (Core Web Vitals / performance),
  **heatmaps**, and dead-click / exception-autocapture style signals that the
  five explicit flags above do **not** enable. Those are genuinely useful
  product/UX signals the current config silently forgoes.
- **It is PostHog's recommended path.** The vendor steers integrators to the
  dated `defaults` bundle precisely so new SDK-default behaviours arrive without a
  code change; pinning to a date is the supported way to opt into "current best
  defaults, frozen."
- **A correctly-dated bundle would not have zero-captured.** The zero-capture was
  caused by a **future** date the SDK didn't know, not by the bundle mechanism
  itself. A `defaults` value the SDK actually ships (a real, past-or-current
  date) captures normally — so the failure argues for "use a valid date," not
  necessarily "abandon the bundle."

### Why the §9.0 firewall argues FOR scrub-don't-disable (relevant to either choice)

Whichever capture config wins, **do not respond to a content-leak fear by
disabling autocapture.** SPR-04 found and closed an `attr__href` (and broader
`$elements_chain`) content leak. Had autocapture been *disabled* to play it safe,
that leak would have been **hidden, not closed** — and a later re-enable would
have re-opened it silently. The firewall (`before_send` scrub, see
`posthog-content-firewall.md`) is the durable answer; the capture-config choice
here is about which *behavioural signals* to collect, not about whether to scrub.

## The revert path

PR #74 is revertible. Reverting to a bundle = replace the five explicit capture
flags in `posthog.init(…)` (`posthogClient.ts`) with a single
`defaults: "<a-real-SDK-shipped-date>"` (NOT a future date — that is what
zero-captured), keeping `before_send: sanitizeOutgoingEvent`,
`person_profiles: "identified_only"`, and `disable_session_recording: true`
explicitly so the §9.0 posture is never delegated to the bundle. Then verify
capture **server-side** (events API / SPR-02 `verify_capture`), never via an
automated-browser probe (see `posthog-bot-filter.md`).

## Reconsider if

- **Reconsider reverting to the `defaults` bundle** if the operator decides the
  dropped auto-features (rageclick / web-vitals / heatmaps) are worth more than
  the explicit config's hard-to-vary legibility — at which point switch to a
  **real, SDK-shipped** `defaults` date (never a future date) and re-verify
  capture server-side.
- **Reconsider staying explicit** as the default whenever a posthog upgrade
  changes what a `defaults` bundle silently enables in a way that could touch
  §9.0 (a new content-bearing autocapture channel); explicit flags keep that
  decision in-repo and reviewable.
- **Whichever way it goes, never disable autocapture to address a content fear** —
  scrub at `before_send` instead; disabling hides leaks rather than closing them.

## Defensibility

Both sides are recorded so the operator (or a future agent) can make or revisit
the call from this record, not from whoever last touched the file. The one thing
this record does decide is the meta-rule: the §9.0 answer is the firewall, not
disabling capture — that part is not the operator's to trade away.
