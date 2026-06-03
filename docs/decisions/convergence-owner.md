# The convergence-owner role — runbook

**Date:** 2026-06-04
**Status:** ✅ Settled (Antiek — Convergence SPR-07)
**Owner:** operator + SPR-07
**Scope:** process-as-code. Installs the convergence DISCIPLINE (a registry, a
CI anti-fork meta-check, a combined sweep, this runbook). Ships NO product
feature and converges NO fork (SPR-03 converged the §9.0 retrieval gate; SPR-04
verified the Werner reading shell; SPR-05 ruled dispatch fidelity).

---

## Why this role exists

The Antiek build loop — `/htmlspec` authors parallel sprint pages →
`/caffenagent` executes each → `/PRcrouch` ships — optimises spec THROUGHPUT.
It has **no force for convergence**: sprints run parallel-and-independent by
design; there is no integration owner. Two failure classes recur:

1. **Forks** — two competing implementations of ONE substrate concern (the §9.0
   retrieval gate had two; the Werner shell was alleged to). A fork ships when
   two sprints each implement the same concern and no one notices both landed.
2. **Dead-in-prod features** — a feature whose reachability depends on a wire no
   single sprint owns (the compounding flywheel: every brick passed, the feature
   was dead in prod).

The convergence-owner is the role (a hat the operator or an agent wears after a
wave) that runs the convergence PASS so neither class survives a merge. The pass
is **mechanically backed**:

| Failure class | Mechanical guard | Where |
|---|---|---|
| Fork | uniqueness registry (anti-fork meta-check) | `tools/lint/uniqueness_registry.py` (CI `pytest` job step) |
| Dead-in-prod | reachability probe runner | `tools/reachability/probe_runner.py` (CI `reachability` job) |
| Both, one command | combined sweep | `tools/reachability/sweep.py` (operator entrypoint) |

---

## Procedure A — the post-wave convergence pass

Run this **after every wave, before the wave's sprints are declared merged.**

1. **List the open PRs in the wave** and the files each touches.
   `gh pr list --state open` → for each, `gh pr diff <n> --name-only`.
2. **Flag PRs that touch the same registered-concern files.** For each concern
   in the registry, take its `canonical` path + its check's search roots
   (`substrate/graph/`, `substrate/dispatch/`, `apps/reading/src/werner/`); if
   two open PRs both touch one of those, treat it as a candidate fork and read
   both diffs before merging either.
3. **Run the uniqueness sweep.**
   `python tools/lint/uniqueness_registry.py` → expect exit 0 and one
   `[UNIQUE] <concern>` per row. A `[FORK] <concern>: <path:line>` means a
   registered concern has two impls (or zero) — go to Procedure B.
4. **Run the reachability sweep.**
   `python -m tools.reachability.probe_runner` (boots the app via the production
   `create_app()` factory) → expect every probe `[REACHABLE]`. A `[BLOCKED]`
   probe outside an unexpired known-red window means a feature is dead-in-prod —
   wire it (the SPR-02 flywheel pattern) or register a known-red entry with a
   linked issue + hard expiry (`tools/reachability/known_red.json`).
5. **Both halves in ONE command (preferred):**
   `python -m tools.reachability.sweep` → aggregates both, exits non-zero iff
   EITHER fails, prints one combined `[UNIQUE]/[FORK]` + `[REACHABLE]/[BLOCKED]`
   report. (It does not short-circuit: a fork AND a dead probe both appear.)
6. **Scan for dormant built-but-unreachable features** the probes do not yet
   cover. Cross-check the static anti-stranding gate
   (`python tools/lint/reachability_gate.py`) for a NEW zero-importer module or
   an unlinked route. A genuinely dormant feature is either WIRED (add a probe +
   the wire) or explicitly DEFERRED behind a named gate (e.g. the §9.0-gated
   monetization surfaces SPR-04 kept parked — see
   `acv-spr04-read-shell-convergence.md`, Finding 2). Never silently amputate a
   §9.0-gated surface (that crosses the legal gate).
7. **Declare the wave merged only when 3, 4, 5 are green** (or every red is a
   recorded, expiring known-red / a documented deferral).

CI runs steps 3 and 4 on every PR already (the registry step in the `pytest`
job + the `reachability` job). The post-wave pass is the human cross-PR check
(step 2) that CI — which sees one PR at a time — cannot do: **CI catches a fork
that lands in one PR; the convergence-owner catches a fork that lands as two
PRs that are individually clean but collectively duplicate.**

---

## Procedure B — how to converge a fork

When step 3 reds (or step 2 finds two PRs implementing one concern):

1. **Pick the canonical.** Prefer the impl that is (a) more tested, (b) already
   the one other code imports, (c) ruled canonical by a prior decision record.
   If neither is clearly stronger, the operator rules (record it).
2. **Supersede the other.** Delete the non-canonical definition; repoint its
   callers to import from the canonical. (This is what #65 did to #53's second
   retrieval gate; what SPR-08 did to the second servability predicate.)
3. **Harvest non-overlapping parts.** If the superseded impl had a real
   capability the canonical lacks, port that capability INTO the canonical
   before deleting — do not lose work, do not keep a second home.
4. **Add or confirm the registry row** (Procedure C) so the convergence is
   guarded against re-forking. If the concern is already registered, confirm
   `python tools/lint/uniqueness_registry.py` is green after the supersede.
5. **Write a one-paragraph decision record** under `docs/decisions/` naming the
   canonical + why (so the next convergence-owner does not re-litigate it).

---

## Procedure C — how to add a concern to the registry

Add a concern ONLY once it has a **ruled canonical** (a decision record or a
commit that says "this is the one home"). Do NOT pre-register a concern with no
ruled canonical (SPR-07 out-of-scope rule).

1. Open `tools/lint/uniqueness_registry.py`.
2. Write the concern's `check` callable: `(repo: Path) -> (ok: bool, offenders:
   list[str])`. Match the DEFINITION syntax of the concern's language and
   exclude test files:
   - **Python symbol** → AST-walk for a `def`/`async def` of that name (reuse
     `_check_dispatch_router` as the template; or import an existing detector
     the way `_check_retrieval_gate` imports SPR-03's `find_violations`).
   - **TS/TSX symbol** → regex for `function|const|class <Name>` (reuse
     `_check_reading_shell` as the template — it already distinguishes a
     definition from an import / re-export / JSX mount / call).
   The check must (i) count DEFINITION sites, not usages; (ii) return `ok=False`
   on TWO definitions (a fork) AND on ZERO (a deleted canonical — never a silent
   pass); (iii) not false-positive on the canonical itself (count by symbol, not
   by path, so a moved canonical is still one).
3. Append a `Concern(name=…, canonical=…, check=…, converged_by=…, ruled_by=…)`
   row to `REGISTRY`. `converged_by` names the sprint that converged it;
   `ruled_by` names the decision record that ruled the canonical.
4. **No change to `run_all` is required** — the engine is concern-agnostic
   (proved in `tests/test_uniqueness_registry.py::test_adding_a_row_adds_
   enforcement_without_touching_run_all`).
5. Add a planted-duplicate proof for the new concern to
   `tests/test_uniqueness_registry.py` (add the concern's name to `_PLANTERS`
   with a planter that writes a second definition into the tmp tree). The proof
   is what makes the new row's enforcement real (rigor #3).
6. Run `python tools/lint/uniqueness_registry.py` (green) and
   `python -m pytest tests/test_uniqueness_registry.py -q` (green).

---

## The in-repo vs recommended-skill boundary

This sprint shipped, **LIVE in this repo**:

- the registry (`tools/lint/uniqueness_registry.py`) + its blocking CI step;
- the combined sweep (`tools/reachability/sweep.py`);
- the planted-duplicate proof (`tests/test_uniqueness_registry.py`);
- the in-repo reachability-declaration carrier (the new section in
  `.github/PULL_REQUEST_TEMPLATE.md`).

This sprint **RECOMMENDED ONLY** (the operator applies; the skill files were NOT
edited by this sprint — see `docs/decisions/reachable-from-prod-declaration.md`):

- the htmlspec sprint-template "Entry Points / reachability declaration" section;
- the caffenagent 5th-done-bar criterion phrasing.

Until those two skill amendments are applied, the reachable-from-prod meta-rule
is enforced in this repo by the SPR-01 reachability gate + this sprint's sweep +
the PR-template checkbox — but a NEW sprint authored by htmlspec will not be
PROMPTED to declare reachability until the operator applies the amendment. The
combined sweep is the operator/runbook entrypoint (Procedure A step 5); CI
enforcement is the uniqueness step + the reachability job (the sweep is not a
third CI step — see the sweep's module docstring for why).

---

## References

- `tools/lint/uniqueness_registry.py` — the registry + the three concern checks.
- `tools/reachability/probe_runner.py` — the SPR-01 reachability runner.
- `tools/reachability/sweep.py` — the combined sweep.
- `tools/reachability/README.md` — the fifth done-bar + probe contract.
- `docs/decisions/reachable-from-prod-declaration.md` — the skill-amendment
  recommendation (operator-apply).
- `docs/decisions/acv-spr04-read-shell-convergence.md` — why #54 is the
  canonical reading shell + the dormant-surface deferral discipline.
- `docs/decisions/acv-spr05-dispatch-fidelity.md` — the dispatch-router ruling.
