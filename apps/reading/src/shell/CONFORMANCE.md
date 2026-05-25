# Frontend conformance report — four-workflow IA (SPR-08)

The release gate for "four workflows, one surface." This is the durable proof
that the four-workflow IA (Research · Read · Write · Speak) holds on screen and
the contract handed to the four product specs that fill its stubs.

- **Sprint:** SPR-08 (Wave 4 capstone of the frontend-design spec).
- **Branch:** `caffen/SPR-08` (based on `caffen/SPR-05` — the four-workflow
  spine + the Topbar scene chrome).
- **Scope:** tests + ships what SPR-01–07 built. No new IA.

---

## Gate results

| Gate | Verified how | Result |
|---|---|---|
| **axe-core a11y** | `@storybook/test-runner@0.24.4` + the new `.storybook/test-runner.ts` axe `postVisit` hook, `--includeTags a11y-audit`, run against the static Storybook | **GREEN** — 8 audited story files, 16 story tests, **0 serious/critical** violations |
| **e2e four-workflow walk** | `playwright test e2e/four-workflow-ia.spec.ts` (Storybook-driven) | **GREEN** — 6/6 asserts pass; full suite 17/17 |
| **Cutover + rollback** | `vite build` both ways | **GREEN** — v2 (four-workflow IA) is the default; v1 (legacy) builds as the rollback |
| **Bundle budget** | `npm run build:check` | **GREEN** — index 214.62 KB gz (budget 683.59), lemon 48.29 KB gz (budget 58.59) |
| **TS strict / vitest** | `tsc -b --noEmit` · `vitest run` | **GREEN** — tsc clean; 123 unit tests pass |
| **Visual regression (lost-pixel)** | `npx lost-pixel` against committed baselines | **NOT GREEN — see finding below.** Held as a deliberate, operator-approved re-mint, not a silenced regression |

### The axe-core fix (milestone 1) — two real bugs, both fixed

The CI axe step in `.github/workflows/visualtest.yml` was broken two ways:

1. **Dropped flag.** It invoked `@storybook/test-runner` with `--include
   "Design/Primitives Showcase" --include "Components/Lemon/**"`. The runner
   **removed `--include`** — `npx @storybook/test-runner@latest --help` shows
   the modern story filter is `--includeTags` (verified against v0.24.4). The
   job failed on every run.
2. **No assertion.** Even with the flag fixed, the test-runner does **not** run
   axe on its own. `@storybook/addon-a11y` only surfaces violations in the
   Storybook UI at author time; it never asserts in the runner. The CI comment
   that claimed "runs axe via the addon-a11y test hook" was **false** for
   test-runner 0.24.x. The assertion is wired by a `postVisit` hook in
   `.storybook/test-runner.ts` (added this sprint) — it runs axe-core (the same
   `@axe-core/playwright` engine + the same rule set `scripts/a11y_audit.ts`
   uses) and throws on any serious/critical violation.

Story selection is by the `a11y-audit` story tag (NavRail, Topbar, ProjectTree,
AppShell, SceneChrome, ProductsLauncher, FourWorkflowShell, and the Primitives
Showcase). The version is **pinned** (`@0.24.4`, no `@latest`) so a future
runner release can't silently move the flag again.

**The gate is non-vacuous** — proven by a throwaway story with a known
`button-name` + `label` violation: the hook correctly FAILED it while all real
shell stories passed. (The throwaway story was removed.)

No a11y fixes to shell code were needed: the shell renders **0 violations of
any impact** from Antiek elements. The only flagged item across the audit set
was Storybook's own hidden `<h1 id="error-message">` inside `iframe.html`
(`empty-heading`, minor) — confirmed to be Storybook chrome, not shell code,
and added to the shared disabled-rules list alongside the other
iframe-wrapper-noise rules `a11y_audit.ts` already documents.

### A latent bug the gate caught (the gate as functional conscience)

The SPR-05 `Topbar` + `SceneChrome` stories were **silently broken** on this
branch: each wraps its body in its own `<MemoryRouter>`, which — nested inside
the global preview decorator's `<MemoryRouter>` — throws react-router's
"You cannot render a `<Router>` inside another `<Router>`" and renders the
Storybook "No Preview" error screen instead of the chrome. axe was auditing the
error screen (a vacuous PASS) and lost-pixel had minted baselines of it.

Fix: `.storybook/preview.tsx` now lets a story opt out of the global router via
`parameters: { router: false }` when it owns its own router (Topbar,
SceneChrome, FourWorkflowShell). After the fix, all three render real content
and the axe gate is a true PASS.

---

## e2e four-workflow walk — the asserted path (milestone 3)

`e2e/four-workflow-ia.spec.ts`, Storybook-driven. **Honest constraint:** the
live app gates on auth (`RequireAuth` → `/login` without `api.antiek.ai`), so a
headless live-app e2e isn't runnable in this environment. The established
pattern (see `e2e/{operator-day,smoke}.spec.ts`) is to drive Storybook stories.
So the walk runs against `navigation-fourworkflowshell--walk` — a story that
composes the **real** shell components (NavRail · Topbar scene chrome ·
workflow-scoped ProjectTree · ProductsLauncher), not mocks, under a
`MemoryRouter` with the four workflows' routes wired. It asserts the **IA
wiring**; it does NOT exercise auth, the live substrate, or the production route
tree. The bare-shared-route + the stub assertions reuse the existing SceneChrome
stories.

| # | Assertion | Pass |
|---|---|---|
| 1 | Rail carries exactly the four workflows (`Research/Read/Write/Speak`) | ✓ |
| 2 | Selecting a workflow re-scopes the tree (folders + label change) AND re-routes the scene body (`/` → `/documents` → `/create` → `/interviews`) | ✓ |
| 3 | Scene chrome shows built tabs as live links + soon tabs as disabled "soon" affordances (Research: `Synthesis` link, `Trajectory` soon; Read replaces them) | ✓ |
| 4 | Topbar is bare on a shared/operator route — no action bar, no tab strip (`/billing`) | ✓ |
| 5 | Products launcher lists every mode, grouped (4 workflows + ≥18 mode buttons + group headers); Escape closes | ✓ |
| 6 | A soon tab's surface is the honest `WorkflowStub` ("Not yet available … ships in SPR-07") | ✓ |

---

## Cutover + rollback (milestone 4)

Already satisfied on this branch; SPR-08 confirms + documents it.

- `src/main.tsx`: `VITE_ANTIEK_UI ?? "v2"` — **v2 is the default**, renders
  `<App />` → `<AppShell>` → the four-workflow IA (NavRail + Topbar scene chrome
  + workflow-scoped tree + launcher).
- **Rollback:** set `VITE_ANTIEK_UI=v1` + redeploy → `<AppLegacy />`, the
  intentionally-minimal pre-redesign chrome. Verified: both `vite build` and
  `VITE_ANTIEK_UI=v1 vite build` succeed.
- `.env.example` documents the flag, the rollback, and that retiring v1 + the
  flag is a later operator decision.

**Steelman of shipping without the flag** (rigor #2): one code path, no flag
debt — simpler. Rejected because a four-workflow rail over mostly-stubbed
Read/Write/Speak is a large surface change and the established `VITE_ANTIEK_UI`
rollback is cheap insurance (one env var + a Cloudflare Pages redeploy, no code
change). Retire the flag in a later sprint once the IA is proven in prod —
operator's call.

---

## Bundle numbers (milestone 5)

Source: `npm run build:check` (`vite build` + `scripts/check_bundle.ts`) on the
default (v2) build.

| Chunk | gzipped | budget | headroom |
|---|---|---|---|
| `index` (entry) | 214.62 KB | 683.59 KB | 468.98 KB |
| `lemon` (primitives) | 48.29 KB | 58.59 KB | 10.30 KB |

SPR-08 added **zero application code** — only stories (`*.stories.tsx`),
Storybook config (`preview.tsx`, `test-runner.ts`), the e2e spec, the CI yaml,
`.env.example`, and this report. None ship in the app bundle. The `lemon` and
`index` chunk hashes/sizes are unchanged from the SPR-05 baseline; the shell
additions (which already existed on SPR-05) did not balloon the entry chunk.

---

## Real-vs-stub matrix → handoff to the four product specs

The single source of truth is `src/shell/sceneRegistry.ts` (`SCENE_REGISTRY`);
a tab is `built` only where its `to` route is mounted in `App.tsx` today, and
the `sceneRegistry.test.ts` invariant forbids a `built` tab without a route. The
**chrome slot** a product sprint fills is the named tab (`builtState: 'soon'`):
shipping its surface = giving that tab a `to` route and flipping it to `built`,
at which point the Topbar renders it as a live `NavLink` and the `WorkflowStub`
is never reached for it. No code change to the chrome is required — the flip is
the registration.

### Research — scene = the investigation

| Tab | State | Slot contract (what the product sprint fills) |
|---|---|---|
| Synthesis | **built** → `/` | research home; the synthesis view |
| Trajectory | `soon` | a standalone trajectory route (today replay is per-investigation `/replay/:id` only); flip when a `/…/trajectory` route mounts |
| Sources | **built** → `/documents` | the source corpus |
| Notebook | **built** → `/notebooks` | the literate notebook index |

### Read — scene = the document

| Tab | State | Slot contract |
|---|---|---|
| Reader | **built** → `/wrestle` | the Wrestle single-document deep reader |
| Notes | **built** → `/notebooks` | reading notes in the notebook surface |
| Rabbit hole | `soon` | the per-reading evidentiary-gap (rabbit-hole) route — **Read product spec** |
| Ad border | `soon` | the ad-border / IP-attribution reader surface (master-spec §9) — **Read product spec** |

### Write — scene = the deliverable

| Tab | State | Slot contract |
|---|---|---|
| Outline | `soon` | the outline view of a deliverable (today the studio is one route) — **Write product spec** |
| Editor | **built** → `/create` | the creation studio home (the editor) |
| Sources | **built** → `/documents` | the deliverable's cited sources → the corpus |
| Style | `soon` | the voice/style panel (master-spec §5) — **Write product spec** |

### Speak — scene = the interview-as-acquisition

| Tab | State | Slot contract |
|---|---|---|
| Interviews | **built** → `/interviews` | the interviews index |
| Corroboration | `soon` | the corroboration view (master-spec §10.4) — **Speak product spec** |
| Contributors | `soon` | the contributors / IP-holder view (master-spec §9.2) — **Speak product spec** |
| Biography | `soon` | the assembled biography view (master-spec §10.5) — **Speak product spec** |

**Built:** 8 tabs (real routes today). **Soon:** 8 tabs (named slots for the
four product specs). When a product sprint ships a surface, the gate confirms
the flip didn't break the IA: the e2e re-runs the four-workflow walk, axe
re-audits the chrome, and lost-pixel holds (or deliberately re-mints) the
baseline.

---

## Re-mint policy (lost-pixel) — and the open finding

**Policy.** A lost-pixel diff is decided per shot, never silenced:
- An **intended** visual change (a deliberate chrome edit, or a story that now
  renders correctly where it previously rendered the error screen) → re-mint
  with `npm run visualtest:update`, commit the `.png` updates **in the same PR
  as the source change**, with the rationale in the PR.
- A **regression** (an unintended diff) → fix the code, do not touch the
  baseline.

**Open finding — lost-pixel is NOT green and cannot honestly be minted from
this worktree.** A local `npx lost-pixel` run shows:

1. **`navigation-topbar--{research,investigation,deep-route}`** (all 3 widths)
   **diff** — because they now render the real chrome where their committed
   baselines captured the broken "No Preview" error screen (see the router-fix
   note above). These are **legitimate re-mints**, not regressions.
2. **`navigation-scenechrome--*`, `navigation-fourworkflowshell--walk`,
   `navigation-productslauncher--open`** have **no baselines** (new/now-rendering
   stories) — additions to be minted.
3. **`navigation-{appshell,navrail,projecttree}--*`** also diff locally even
   though their code is unchanged — evidence the committed baselines were minted
   in CI's `ubuntu-22.04` Chromium, which renders fonts differently from macOS.

Conclusion: minting these baselines **on macOS would make the CI gate red**
(cross-platform font rendering at the 0.4% threshold). So the re-mint must be
performed **in the CI environment** (`ubuntu-22.04`) — either by running
`npm run visualtest:update` there and committing the result, or by promoting the
CI `lostpixel-diff` artifact's `current/` images to `baseline/`. This is a
deliberate, operator-approved re-mint, and is **intentionally left undone here
rather than papered over with host-specific PNGs that would fail CI.**

`workspace-demo--scene` continues to show sub-frame framer-motion spring diffs;
it is already documented as a known-flaky exclusion in `lostpixel.config.ts`.
