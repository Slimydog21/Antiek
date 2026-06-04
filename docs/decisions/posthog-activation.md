# PostHog activation — token via Cloudflare Pages production env

**Decision date:** 2026-06-04
**Status:** ✅ Active (token set in the `antiek` Cloudflare Pages production env)
**Owner:** operator (PostHog Analytics Hardening)

## The decision

Analytics is activated by setting the PostHog **project token** as a build-time
environment variable in the `antiek` Cloudflare Pages production environment, not
by committing it to the repo. Two variables:

- `VITE_POSTHOG_PROJECT_TOKEN=phc_…` — the PostHog project (write) token.
- `VITE_POSTHOG_HOST=https://eu.i.posthog.com` — the EU ingestion host
  (GDPR-resident; matches the `identified_only` posture in
  `posthog-content-firewall.md`).

Both are `VITE_`-prefixed, so Vite **bakes them into the static bundle at build
time**. The `antiek` Pages project rebuilds from `main` on push (see
`infrastructure/runbooks/cloudflare-pages-setup.md`), so the token reaches prod
on the next Pages build after it is set — there is no runtime injection.

## How it was set

Set via the **Cloudflare API** against the `antiek` Pages project's production
environment variables (the same project documented in
`infrastructure/runbooks/cloudflare-pages-setup.md`, alongside the existing
`VITE_API_BASE_URL=https://api.antiek.ai`). The CF API token used lives at
`~/.config/cloudflare/credentials.env` (operator machine, not in the repo). After
setting the vars, a Pages rebuild (push to `main`, or a manual redeploy) bakes
them in. Rotation of either the PostHog token or the CF API token is in
`docs/runbooks/posthog-analytics.md`.

## The no-op-without-token safety

`apps/reading/src/lib/posthogClient.ts` reads the token at module load and
derives `export const posthogEnabled = Boolean(projectToken)`. `posthog.init(…)`
runs **only** when `posthogEnabled` is true. Every emit path is gated on the same
flag:

- `track(…)` / `trackException(…)` in `apps/reading/src/lib/analytics.ts` early-
  return when `!posthogEnabled`.
- the identify/reset effect in `apps/reading/src/lib/auth.tsx` early-returns when
  `!posthogEnabled`.

So a build with **no token** — CI, Storybook, a local dev checkout without keys —
initializes nothing and emits nothing: analytics is a clean no-op, never a crash
and never a silent half-init. This is why ~all of the app's tests run with
analytics simply absent rather than mocked at every call site.

## Reconsider if

- **Reconsider the build-time-baked token** if Antiek ever needs to flip
  analytics on/off without a rebuild, or to vary the token per environment at
  runtime — then a runtime-config fetch (or a Pages preview-vs-production split)
  would replace the baked `VITE_` var. Today, one production token baked at build
  is the simplest correct thing.
- **Reconsider the EU host** only if the project's data-residency requirement
  changes; `eu.i.posthog.com` is deliberate, not a default.
- **Reconsider the no-op-without-token gate** never in the direction of removing
  it: it is what keeps CI/Storybook/local from emitting to prod and what makes a
  missing token a no-op rather than a crash.

## Defensibility

The activation path (token type, EU host, build-time baking via Pages env set
through the CF API, the `~/.config/cloudflare/credentials.env` credential, the
`posthogEnabled` no-op gate) is recorded here so a future operator can re-set or
move the token without re-deriving where it lives or why a tokenless build is
silent rather than broken.
