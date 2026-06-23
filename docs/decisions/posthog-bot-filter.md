# PostHog bot-filter — automated browsers capture ZERO; verify server-side

**Decision date:** 2026-06-04
**Status:** ✅ Active warning (the lesson is permanent; the verification protocol below is the standing rule)
**Owner:** operator + reading-app analytics (PostHog Analytics Hardening)

## The gotcha, told straight

posthog-js ships a built-in **bot filter**. It inspects the browser for
automation signals — `navigator.webdriver`, headless user-agent strings, and
related signatures — and when it concludes the client is "likely a bot," it
**captures nothing**: zero `POST` to `/i/v0/e/`. This fires for **Playwright in
both headless AND headed mode** (the `webdriver` flag is set under automation
regardless of head), and for most other automated-browser tooling.

Real human browsers do not trip this. Capture works fine in production for
actual users.

## What actually happened (do NOT launder this)

During the hardening work, an automated-browser capture probe (a Playwright
script driving the live site) observed **zero `/i/v0/e/` requests** and the
session concluded, across multiple turns, that **production analytics was
broken**. A fix — **PR #74** — was shipped chasing that conclusion. PR #74 did
contain a separate, real fix (the explicit-capture-config change; see
`posthog-capture-config-tradeoff.md`), but the **zero-capture symptom that
motivated the investigation was a phantom**: the integration was not broken; the
probe was an automated browser that the bot filter silently dropped.

This record exists so the next agent does not repeat the misdiagnosis. State it
plainly: **the integration was not broken; an automated-browser probe produced a
false zero-capture; a fix was shipped chasing it.** It is NOT "we proactively
hardened capture" — calling it that would launder a multi-turn misdiagnosis into
a virtue and destroy this record's value as a warning.

## The correct verification protocol

**NEVER trust an automated-browser capture probe as evidence that production
capture is or isn't working.** A zero from Playwright/Selenium/headless Chrome is
the EXPECTED result of the bot filter, not a signal about prod health. Two valid
ways to verify capture:

1. **Server-side (preferred, ground truth).** Query the PostHog events API for
   recent events on the project (filter by event name / time window). This sees
   what actually arrived, independent of any client. This is what the
   `verify_capture` tool **to be created by SPR-02** does (`tools/posthog/`); use
   it once it lands. Until then, query the events API directly.
2. **A LOCAL-ONLY opt-out build.** Initialize posthog-js with
   `opt_out_useragent_filter: true` (and `advanced_disable_decide`/local config
   as needed) in a throwaway local build ONLY. This makes an automated browser
   capture so you can watch the `/i/v0/e/` POST in devtools. **Never ship
   `opt_out_useragent_filter: true` to production** — it would let real bot
   traffic pollute the dataset.

## Reconsider if

- **Reconsider this record's standing** only if posthog-js removes or
  fundamentally changes its bot filter such that automated browsers begin
  capturing by default. Until then the rule holds: an automated-browser
  zero-capture is the filter working, never proof of a prod outage.
- **Reconsider the server-side-first protocol** never in the direction of
  trusting a browser probe; if a faster check is wanted, it must still be
  server-side (events API) or an explicitly-marked LOCAL opt-out build.

## Defensibility

The single most expensive lesson of this initiative — a multi-turn false
diagnosis and a fix shipped against a phantom — is written down here so it costs
the next agent one read instead of one re-discovery. The `verify_capture` tool
(SPR-02) operationalizes the server-side protocol so the correct check is the
easy one to run.
