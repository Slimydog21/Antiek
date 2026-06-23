# Runbook — PostHog analytics

**Single entry point for the Antiek reading-app's PostHog integration.** Read
this first. It points at the four decision records that hold the reasoning, the
tools that operate the integration, and the exact commands to verify capture,
manage the North Star dashboard, run the taxonomy gate, and rotate keys.

> **⚠️ NEVER verify capture with an automated browser.** posthog-js's bot filter
> drops ALL capture for Playwright / Selenium / headless Chrome (`navigator.webdriver`
> + headless signals → "likely bot" → zero `/i/v0/e/`). A zero from an automated
> browser is the filter working, **not** a prod outage. A multi-turn misdiagnosis
> once shipped a fix chasing this phantom. **Verify capture server-side only.**
> See `docs/decisions/posthog-bot-filter.md`.

## File map — who owns what

| Concern | File |
|---|---|
| SDK init, capture config, `before_send` firewall, `posthogEnabled` | `apps/reading/src/lib/posthogClient.ts` |
| Typed event taxonomy + `track()` / `trackException()` no-op gate | `apps/reading/src/lib/analytics.ts` |
| Person model — `identify()` on auth, `reset()` on sign-out | `apps/reading/src/lib/auth.tsx` |
| Firewall behaviour tests (incl. the 3 chain leaks SPR-04 closed) | `apps/reading/src/lib/posthogClient.test.ts` |
| §9.0 firewall posture (decision) | `docs/decisions/posthog-content-firewall.md` |
| Bot-filter gotcha + verification protocol (decision) | `docs/decisions/posthog-bot-filter.md` |
| Activation: token via CF Pages prod env (decision) | `docs/decisions/posthog-activation.md` |
| Capture config: explicit flags vs `defaults` bundle (decision, OPEN) | `docs/decisions/posthog-capture-config-tradeoff.md` |
| CF Pages project wiring (`antiek`, build env) | `infrastructure/runbooks/cloudflare-pages-setup.md` |

## Decision records (the reasoning, no transcript needed)

- `docs/decisions/posthog-content-firewall.md` — why autocapture is ON but
  scrubbed at `before_send`; what's scrubbed; `identified_only`;
  session-recording OFF; the fail-CLOSED never-undefined guard; the deferred
  `$elements_chain` skeletonize follow-up.
- `docs/decisions/posthog-bot-filter.md` — the bot-filter gotcha, told straight;
  the correct server-side verification protocol.
- `docs/decisions/posthog-activation.md` — token in CF Pages prod env, baked at
  build time; the no-op-without-token safety.
- `docs/decisions/posthog-capture-config-tradeoff.md` — explicit capture flags
  (PR #74) vs the dated `defaults` bundle; both steelmanned; **operator decides**.

## Verify capture (server-side ONLY)

**Tool: `tools/posthog/verify_capture.py` — to be created by SPR-02.** Once it
lands, it is the sanctioned way to verify: it queries the PostHog events API for
recent events on the project (independent of any browser) and reports what
actually arrived.

```bash
# (to be created by SPR-02)
python tools/posthog/verify_capture.py --since 1h
```

Until SPR-02 lands, verify by querying the PostHog events API directly for recent
events in the project, filtered by event name and time window.

**The only other valid local check** is a throwaway build with
`opt_out_useragent_filter: true` to let an automated browser capture so you can
watch the `/i/v0/e/` POST in devtools. **Never ship that flag to production.**

## Recreate / update the North Star dashboard

**Tool: `tools/posthog/sync_dashboards.py` + `tools/posthog/north_star.json` —
to be created by SPR-03.** The dashboard is defined as code in `north_star.json`
and synced (create-or-update) to the PostHog project by the sync script, so the
dashboard can be recreated from the repo rather than hand-built in the UI.

```bash
# (to be created by SPR-03)
python tools/posthog/sync_dashboards.py --apply       # create/update from north_star.json
python tools/posthog/sync_dashboards.py --dry-run     # preview without writing
```

Event names referenced by the dashboard must exist in the taxonomy
(`apps/reading/src/lib/analytics.ts`) — see the taxonomy gate below.

## Taxonomy gate

**Owned by SPR-01.** The taxonomy gate keeps the event surface honest: every
emitted event name is declared in the typed `AnalyticsEvents` map in
`apps/reading/src/lib/analytics.ts` (an off-taxonomy name is a TypeScript compile
error at the call site, because `track()` is generic over `keyof AnalyticsEvents`).
The SPR-01 gate additionally checks that no event sends a content-bearing
property — consistent with the `CONTENT_PROPERTY_DENYLIST` backstop in
`apps/reading/src/lib/posthogClient.ts`. Run it as part of the reading-app checks
(SPR-01 wires the exact command); a new event MUST be added to the taxonomy map
before it can be tracked.

## Rotate keys

Two distinct credentials are involved. Neither lives in the repo.

### 1. PostHog project token (`phc_…`) — and personal API key (`phx_…`)

- The **project token** (`phc_…`) is the client-side write token baked into the
  bundle via `VITE_POSTHOG_PROJECT_TOKEN` (see
  `docs/decisions/posthog-activation.md`). To rotate: create a new project token
  in the PostHog project settings, update `VITE_POSTHOG_PROJECT_TOKEN` in the
  `antiek` Cloudflare Pages **production** env, then trigger a Pages rebuild
  (push to `main` or manual redeploy) so the new token is baked in.
- A **personal API key** (`phx_…`) is the server-side read key used by
  `verify_capture` / `sync_dashboards` (SPR-02/03) to call the PostHog API. Rotate
  it in PostHog → personal API keys; store the new value wherever those tools read
  it (per the tool docs SPR-02/03 ship). It is read-side; rotating it never
  affects browser capture.

### 2. Cloudflare API token (used to set the Pages env)

- Lives at `~/.config/cloudflare/credentials.env` (operator machine, not in repo).
  Used to set the Pages production env vars via the CF API. To rotate: create a
  new CF API token scoped to the `antiek` Pages project, replace the value in
  `~/.config/cloudflare/credentials.env`. See
  `infrastructure/runbooks/cloudflare-pages-setup.md` for the Pages project
  wiring.

## Where to look when something seems wrong

1. **"Analytics looks broken / zero events."** First, confirm you are NOT checking
   via an automated browser — see the warning at the top and
   `docs/decisions/posthog-bot-filter.md`. Verify server-side.
2. **Capture is genuinely zero from real users.** Check the capture config in
   `posthogClient.ts` is explicit flags (not a future-dated `defaults` bundle —
   that zero-captures); see `docs/decisions/posthog-capture-config-tradeoff.md`.
3. **No events at all in any env, no error.** Likely a missing token —
   `posthogEnabled` is false, everything no-ops (CI/Storybook/local without keys);
   see `docs/decisions/posthog-activation.md`.
4. **Worried content is leaking into events.** The firewall scrubs at
   `before_send`; read `docs/decisions/posthog-content-firewall.md`. Do NOT
   "fix" it by disabling autocapture — that hides leaks rather than closing them.
