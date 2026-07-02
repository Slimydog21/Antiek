# The reachable-from-prod declaration — meta-rule + RECOMMENDED skill amendments

**Date:** 2026-06-04
**Status:** ✅ In-repo meta-rule SETTLED + skill amendments RECOMMENDED (NOT applied)
**Owner:** operator (applies the skill amendments) + SPR-07 (authored them)
**Scope:** process-as-code. This decision (a) states the reachable-from-prod
meta-rule and where the declaration lives, and (b) gives the operator the
VERBATIM, paste-ready blocks to amend the two skills. **This sprint did NOT edit
`~/.claude/skills/htmlspec/` or `~/.claude/skills/caffenagent/`** — those are the
operator-apply actions (see "Operator-apply actions" below). Editing the skill
files is the cardinal SPR-07 scope violation; this sprint recommends in-repo
only.

---

## The meta-rule

> **A PR or sprint that touches a USER-FACING feature MUST either (a) register a
> reachability probe under `tools/reachability/probes/` that boots the app via
> the production `create_app()` factory, drives the feature's real route, and
> asserts an observable outcome — OR (b) carry a written internal-only
> justification.** Internal-only work (a lint, a migration, a refactor, a piece
> of process-as-code that ships no user-facing route or surface) is exempt with
> a one-line justification. A feature declared "reachable from prod" without a
> green (or known-red-with-expiry) probe has not met the bar, however many unit
> tests pass.

This is the SPR-01 fifth done-bar (`tools/reachability/README.md`), promoted
from a probe-runner convention to a declared meta-rule with a home.

### Where the declaration lives

| Carrier | Status | What it does |
|---|---|---|
| `tools/reachability/probes/<feature>.py` | LIVE (SPR-01) | the probe itself — the machine-checked form of the declaration |
| `tools/reachability/known_red.json` | LIVE (SPR-01) | the escape valve: an intentionally-red probe with a linked issue + hard expiry |
| `.github/PULL_REQUEST_TEMPLATE.md` → "Reachability declaration (ACV SPR-07)" | LIVE (SPR-07) | the in-repo PR-author carrier: pick "registers a probe" / "internal-only + justification" / "registry row exists" |
| htmlspec `templates/sprint.html` → "Entry Points / reachability declaration" | **RECOMMENDED (operator-apply)** | makes every NEW sprint page PROMPT the author to declare reachability |
| caffenagent done-test 5th criterion | **RECOMMENDED (operator-apply)** | makes the executor REFUSE to mark a sprint `done` without the declaration met |

Until the two skill amendments are applied, the meta-rule is enforced in this
repo by the SPR-01 reachability gate + the SPR-07 combined sweep + the
PR-template checkbox. It is NOT yet injected into newly-authored sprint pages or
the caffenagent done-test — that is what the amendments add.

---

## RECOMMENDED skill amendment 1 — htmlspec `templates/sprint.html`

**File to edit (operator):** `~/.claude/skills/htmlspec/templates/sprint.html`
**Where:** insert a new `<section class="block">` immediately AFTER the existing
`Goal` section (the `<section class="block"><h2>Goal</h2>…</section>` that ends
just before the `TECHNICAL MILESTONES` comment) and BEFORE the
`<!-- TECHNICAL MILESTONES -->` comment.
**Paste-ready block (verbatim — matches the template's `<section class="block">`
/ `<h2>` / `{{PLACEHOLDER}}` idiom):**

```html
  <!-- ============================================================ -->
  <!-- ENTRY POINTS / REACHABILITY DECLARATION                      -->
  <!-- ============================================================ -->
  <section class="block">
    <h2>Entry points — reachability declaration</h2>
    <p class="lede">A feature is not done because a brick passes; it is done when it is reachable from the real product. Declare, for this sprint, how each user-facing feature it ships is reached from prod — or declare the sprint internal-only.</p>
    <ul>
      <li><strong>User-facing features this sprint makes reachable:</strong> {{REACHABLE_FEATURES}} — for each, the real route/entrypoint a user hits and the observable outcome that proves it works.</li>
      <li><strong>Reachability proof:</strong> {{REACHABILITY_PROBE}} — a probe under <code>tools/reachability/probes/</code> that boots the production <code>create_app()</code> factory (no fixture injection), drives the route, and asserts the outcome; green under <code>python -m tools.reachability.probe_runner</code>. (Or a known-red entry with a linked issue + hard expiry during a fix window.)</li>
      <li><strong>If internal-only</strong> (a lint / migration / refactor / process-as-code shipping no user-facing route): {{INTERNAL_ONLY_JUSTIFICATION}} — the one-line justification that exempts this sprint from a probe.</li>
    </ul>
    <div class="callout callout--warn">
      <strong>The reachability bar:</strong> declaring "X is reachable from prod" without a green (or known-red-with-expiry) probe for X does not meet the bar, regardless of how many unit tests pass. See <code>tools/reachability/README.md</code> and <code>docs/decisions/reachable-from-prod-declaration.md</code>.
    </div>
  </section>
```

---

## RECOMMENDED skill amendment 2 — caffenagent done-test 5th criterion

**File to edit (operator):** `~/.claude/skills/caffenagent/SKILL.md`
**Where:** in the `**k. Done-test.** The sprint is `done` iff ALL hold:` numbered
list, append as item **5** (after the existing item 4, "At least one sharpen
round has run").
**Paste-ready block (verbatim — phrased as caffenagent applies it, matching the
existing numbered done-test idiom):**

```markdown
5. **The reachable-from-prod declaration is met.** For every user-facing
   feature the sprint declares reachable, there is ≥ 1 GREEN (or
   known-red-with-unexpired-expiry) reachability probe under
   `tools/reachability/probes/` that boots the production `create_app()`
   factory, drives the real route, and asserts an observable outcome — run for
   real this round (`python -m tools.reachability.probe_runner`, or the combined
   `python -m tools.reachability.sweep`). A sprint may claim the exemption ONLY
   for explicitly internal-only work (a lint / migration / refactor /
   process-as-code shipping no user-facing route), and only with the one-line
   internal-only justification recorded in the handoff. "Unit tests pass" does
   NOT satisfy this criterion — it is the dead-in-prod failure class this bar
   exists to kill (the compounding flywheel shipped dead with every brick
   green). See `docs/decisions/reachable-from-prod-declaration.md`.
```

---

## Operator-apply actions (the ONLY manual step; skills NOT edited here)

This sprint authored the two blocks above but **did not edit the skill files.**
The two operator-apply paths, stated unambiguously:

1. `~/.claude/skills/htmlspec/templates/sprint.html` — paste amendment 1.
2. `~/.claude/skills/caffenagent/SKILL.md` — paste amendment 2.

**Explicit statement (SPR-07 rigor #1, intellectual honesty):** SPR-07 did NOT
modify `~/.claude/skills/htmlspec/` or `~/.claude/skills/caffenagent/`. Both
amendments are recommendations the operator applies. Until they are applied, the
reachable-from-prod meta-rule is active in this repo ONLY via the in-repo
enforcement — the SPR-01 reachability gate (`tools/reachability/probe_runner.py`,
CI `reachability` job), this sprint's combined sweep
(`tools/reachability/sweep.py`), and the PR-template checkbox — and newly
htmlspec-authored sprint pages / the caffenagent done-test will NOT yet prompt or
require the declaration.

---

## References

- `tools/reachability/README.md` — the fifth done-bar + the probe contract.
- `tools/reachability/probe_runner.py` — the SPR-01 runner the meta-rule cites.
- `tools/reachability/sweep.py` — the SPR-07 combined sweep.
- `.github/PULL_REQUEST_TEMPLATE.md` — the in-repo declaration carrier.
- `docs/decisions/convergence-owner.md` — the role that runs the sweep + uses
  this declaration.
