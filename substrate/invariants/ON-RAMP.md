# Registrant on-ramp — how SPR-08/09/10 (and anyone) register an invariant

The invariant registry (`substrate/invariants/`) is the **KEYSTONE** of the
Antiek Foundation spec. SPR-08 (§9.0 servability), SPR-09 (boundary-lint /
upstream-watcher), and SPR-10 (reachability gate) all **register into it**.
Because each invariant is **one file**, registrants are file-disjoint and land
in parallel — no shared manifest to serialize on.

## The three-step recipe

### 1. Land the guard test FIRST

Write the test that **fails when the invariant is violated**, and record its
non-vacuity proof. The canonical proof is a **fail-before / pass-after** count:
run the guard against the broken code (it must FAIL), then against the fix (it
must PASS), and record both counts + the commit. A **negative-control** (the
guard's own test feeds a deliberately-broken input and asserts rejection, in the
same file) or a named **mutation** the guard catches are equally valid.

> A guard with no recorded proof of teeth is, by this registry's definition,
> **NOT declared**. That is the anti-stub-hack: it is exactly how the §14.4
> fake-green (a test that passed against a synthetic config and never loaded the
> real `config.yaml`) is caught.

### 2. Add ONE declaration file

Create `substrate/invariants/<id>.toml`. The `id` **must equal the filename
stem**. See `README.md` for the full field table. Guarded example:

```toml
[invariant]
id = "section-9-0-servability-polarity"
status = "guarded"
statement = """Why it matters — the COST if violated (rigor #5)."""
guard = "tests/test_servability_polarity.py::test_denies_by_default"
guard_kind = "pytest"          # or "script" for an exit-code gate
assertion = "What the guard proves, one line."
sunset = ""                    # or e.g. "Sprint-20 §14.4 verdict"

[non_vacuity]
method = "fail_before_pass_after"
detail = "fail_before=N pass_after=M @<commit>"
```

If the real guard does not exist yet, register the **honest gap** instead — and
flip it to `guarded` in the same PR that lands the guard:

```toml
[invariant]
id = "section-9-0-servability-polarity"
status = "unguarded"
owner = "SPR-08"               # the sprint that will supply the guard
statement = """..."""
assertion = "OWNED BY SPR-08: ..."
# NO guard, NO [non_vacuity] — the meta-check fails if an unguarded entry has either.
```

### 3. Run the meta-check — it must stay green

```bash
pytest tests/test_invariant_registry_meta.py -q -p no:cacheprovider -p no:xdist
```

The meta-check parametrizes over every declaration, so a new file is picked up
automatically — no edit to the meta-check is needed. It will FAIL if your guard
is missing, skipped, xfailed, or carries no non-vacuity proof. CI runs the same
step (`.github/workflows/ci.yml` → "Invariant-registry meta-check").

### Script-kind guards (SPR-09's lints, the conformance gate)

A guard that is an exit-code gate rather than a pytest node sets
`guard_kind = "script"` and points `guard` at the script path
(e.g. `tools/lint/boundary_check.py`). The meta-check verifies the file exists
and the non-vacuity proof is present; the script's own CI step exercises that it
actually reddens (the meta-check does not run arbitrary scripts in-process).
Cite that CI step in `non_vacuity.detail`.

---

## Operator ratification (built ≠ ratified)

The registry **mechanism** is built and wired into CI. The following are
**operator decisions**, deliberately NOT self-ratified by this sprint
(rigor #1, #5; the spec's Out-of-scope list):

1. **Ratify the registry as canon.** Adopt `substrate/invariants/` + the
   meta-check as the project's binding "CI-green-means" mechanism (e.g. a
   `docs/decisions/` ADR + a `docs/philosophy/` clause).
2. **Decide the mandatory-invariant set.** No canon clause yet says *which*
   invariants are mandatory, nor who may ratify an `@unguarded` exemption (an
   `owner` is named, but the authority to leave something unguarded is not
   defined). Until then the registry surfaces gaps; it does not enforce a
   minimum set.
3. **Define the deferred governance clauses the philosophy pass named** (and the
   spec puts out-of-scope): the **tier-ladder** clause and the
   **measurement-gate-sunset** clause (e.g. §14.4's Sprint-20 window). These are
   policy, not mechanism — do not invent them here.
4. **§5 voice/style** is registered `@unguarded` with no sprint owner because no
   sprint in this spec owns a §5 guard, and it may be an inherently human-judged
   invariant. The operator decides whether a non-vacuous guard is feasible at
   all, or whether it stays an explicitly-accepted human-judged gap.

These items are also recorded in the SPR-06 handoff packet.
