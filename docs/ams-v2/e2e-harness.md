# AMS-v2 real-app experience-gate harness — run note

The one command + one env var a later sprint (or the operator / SPR-10) runs to
execute the **real-app** experience gate, plus the supporting checks SPR-01 ships.

## TL;DR

```sh
cd apps/reading

# The real-app experience gate (builds the SPA, boots vite preview, runs the
# 5 ams-shell anchors against the REAL authed app on the default route):
npm run e2e:ams

# Point at an already-running SPA instead of auto-booting vite preview:
AMS_APP_URL=http://localhost:4173 npm run e2e:ams

# Everything (Storybook smoke + the real-app gate), the spec's `npm run e2e` gate:
npm run e2e
```

## The one env var

| Env var | Default | Effect |
|---|---|---|
| `AMS_APP_URL` | _(unset)_ → `http://localhost:4173` | The base URL the `ams-real` Playwright project loads the real SPA from. **Unset** ⇒ `playwright.config.ts` auto-boots `vite preview --port 4173` (so `npm run build` must have produced `dist/` first — the `e2e`/`e2e:ams` scripts do this). **Set** ⇒ no preview server is booted; Playwright uses your URL. |

`STORYBOOK_URL` (unchanged) still overrides the Storybook base for the existing
`chromium` project.

## How auth works (no prod app-code bypass)

The harness gets past `RequireAuth` purely at the **Playwright network layer**:
`e2e/_ams/auth.ts` intercepts `GET **/auth/me` and fulfils it with
`200 { user_id, email, auth_method }` (the real `AuthIdentity` contract from
`src/lib/auth.tsx`). The shipped bundle is untouched — only the test browser
context sees the mocked session. Krea is stubbed to graceful-absence so the
**procedural** scene renders with no `KREA_API_TOKEN` (RULE 3).

## What's in the harness

| File | Role |
|---|---|
| `e2e/_ams/visible.ts` | `assertSceneVisible` / `assertWindowOpen` / `assertLabeled` / `assertHotkeyOverlay` / `assertContrast` + pure pixel helpers (`decodePng`, `regionVariance`, `isSolidColor`, `contrastRatio`). |
| `e2e/_ams/auth.ts` | `loginAndGotoApp(page, route)` + `installAuthMock(page)` — the real-app boot + the `/auth/me` mock. |
| `e2e/ams-shell.spec.ts` | The 5 regression anchors (scene/window/igloo/hotkeys/penguin), each `test.fixme` naming the sprint that flips it green. |
| `e2e/_ams/visible.pixel.test.ts` | Vitest calibration: a synthetic solid-ice/space buffer reads SOLID (so `assertSceneVisible` would FAIL on an occluded scene); a gradient reads NOT solid. |
| `playwright.config.ts` | Adds the `ams-real` project + the vite-preview webServer (additive; the Storybook `chromium` project is unchanged). |

## Other SPR-01 checks

```sh
# Anti-fiction ref-lint over a sprint page (exit 0 = clean, non-zero = fiction):
tsx tools/specs/verify_spec_refs.ts <path-to-sprint.html>

# Ref-lint negative test (proves it catches the v1 FloatingSurface fiction):
cd apps/reading && npm run test:reflint

# Typecheck the NEW e2e harness TS (the app's `tsc -b` excludes e2e/):
cd apps/reading && npm run e2e:ams:typecheck

# Pure pixel-helper calibration:
cd apps/reading && npx vitest run e2e/_ams/visible.pixel.test.ts --environment node
```

## Sandbox / CI note (RULE 3)

The 5 anchors are `test.fixme`, so they do **not** run until a later sprint
un-fixmes the one it owns. That means a CI sandbox that can't boot the SPA
stays green. **SPR-10** runs them for real (un-fixme'd) against a built SPA with
`AMS_APP_URL` set or the vite-preview server, and mechanically checks "all five
un-fixme'd and green."
