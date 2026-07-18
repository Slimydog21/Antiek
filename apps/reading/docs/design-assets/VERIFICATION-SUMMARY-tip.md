# Branding verification tip — shell-launch re-proof

**Tip:** `062f54e23` (`goal/twin-autoload-session-alpha`, PR #2416)
**Date:** 2026-07-16

## Shell-launch (plan gate 2)

Harness: `shell-launch-worktree.mjs` (SCRATCH), vite `:5213`, authenticated via stubbed `/auth/me`.

| Pass | lastClick | nonForceClickWorked | penguin | reactionChanged | unexpected errors |
|---|---|---|---|---|---|
| 1 | `peak-left` | true | 1 | true | 0 |
| 2 | `peak-left` | true | 1 | true | 0 |

**ok=true ×2** — honest runtime `data-last-click` on `[data-testid=scene-hotspots]` after real `mouse.click` on peak-left; center worksurface + topbar free of hotspots.

### Harness fix (this re-proof)

Broken Krea stubs returned `{art,mood}` without `failures:[]`, crashing `SceneStatusBadge` (`status.failures.at(-1)`). Fixed stubs:

- `/krea/status` → full disabled snapshot with `failures: []`, `gate_verdict: no_key`
- `/krea/scene` → 503 typed disabled

Evidence: SCRATCH `shell-launch-reproof-fixed-a/b.log`, `shell-launch-result-tip.json`.

## Unit densify pulse (this wave)

- door living-TV complete: 60/60
- reading surface brand: 9/9
- talk/voice/bio: 21/21
- meta-reading brand: 11/11
- scenery units: 12/12
