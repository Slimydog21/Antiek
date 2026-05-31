# Invariant-registry reconcile — rescue the stranded keystone onto live main

**Decision date:** 2026-05-31
**Status:** ✅ Reconciled onto live main (registry package + meta-check added clean; 2 guards flipped @unguarded with evidence below)
**Owner:** SPR-02 (Antiek Flywheel Foundation)

The CI-green-means invariant registry (`substrate/invariants/` + the anti-stub-hack
meta-check `tests/test_invariant_registry_meta.py`) was built by the prior
foundation spec's SPR-06 at commit `203eefb`, on branch `foundation/integration`,
and **stranded there** — it was never merged to main. It is the keystone the
flywheel work depends on: a data-driven enumeration of Antiek's load-bearing
invariants, each declaring a guard test that must be COLLECTED (not skipped /
xfailed), NON-VACUOUS (carry a fail-before/pass-after, negative-control, or
mutation proof), and PASS — so "CI is green" *means* the invariants hold. It was
born from the §14.4 fake-green incident: a "seam test" asserted the synthesis pin
against a *synthetic* config, never loaded the real `config.yaml`, and hid a
money/provenance/measurement displacement bug (Opus → DeepSeek on the human-read
synthesis artifact) for weeks.

SPR-02 reconciles that stranded keystone onto **live main** (`771f30d`, which
already carries SPR-01's anti-stranding gate). The spec's base SHA (`e779537`) is
a generation-time reference only; everything here is reconciled to live main.

## The reconcile is an ADD, not a rebase-with-conflicts

`substrate/invariants/` is **absent** on main, and so is
`tests/test_invariant_registry_meta.py`. The package is stdlib-only
(`tomllib`, 3.11+) and adds with no conflicts; I recreated each file from
`git show 203eefb:<path>` verbatim (the `__init__.py` loader, README, ON-RAMP,
the meta-check, and the TOMLs whose guards are present on main). So the
"rebase-vs-absorb-and-supersede" framing collapses: the *mechanism* is an add.

**The real decision is per-guard:** for each invariant the registry registers,
does its guard genuinely COLLECT + PASS against live main? A guard pointed at a
test that does not exist — or that imports production code that stranded with
`203eefb` and never landed on main — would fail at *collection* (ImportError).
Declaring such a guard `guarded` is the exact fake-completeness this registry
exists to cure: a green-looking registration whose guard cannot even run.
Honesty rule (rigor #1): **an absent guard is `@unguarded` with a named owner,
never a `guarded` entry pointing at a non-existent file.**

## Per-guard reachability table (verified against `771f30d`)

| Invariant | 203eefb status | Guard node | Live-main reachability | SPR-02 call |
|---|---|---|---|---|
| `section-14-4-synthesis-pin` | guarded | `tests/test_dispatch_synthesis_pin.py::test_default_deep_synthesizer_stays_pinned_to_opus_with_deepseek_live` | node present (L131); collects + PASSES | **keep guarded** |
| `provenance-chain-no-copy` | guarded | `tests/test_seam_no_copy.py::test_read_to_write_copy_fails_the_guard` | node present (L93); collects + PASSES | **keep guarded** |
| `single-writer-remote-exec` | guarded | `tests/test_remote_exec_isolation.py::test_connect_write_only_in_funnel` | node present (L70); collects + PASSES | **keep guarded** |
| `single-writer-per-graph` | guarded | `tests/test_graph_handle_isolation.py::test_two_handles_locks_do_not_contend` | guard imports `substrate.graph_handle` — **module ABSENT on main**; collection fails `ModuleNotFoundError: No module named 'substrate.graph_handle'` | **flip @unguarded, owner SPR-04** |
| `providers-pinned-primary-fails-loud` | guarded | `tests/test_provider_bootstrap.py::test_synthesis_primary_absent_raises_loud` | guard imports `ProviderRegistrationError` + `_pinned_primary_providers` + `require_pinned`/`config_path` params + `scripts/dev_bootstrap.py` — **all ABSENT on main**; collection fails `ImportError: cannot import name 'ProviderRegistrationError'` | **flip @unguarded, owner operator (flag for ratification)** |
| `first-light-e2e` | unguarded (owner SPR-05) | — | guard `tests/test_first_light_e2e.py` not on main; no First-Light sprint in THIS spec | keep @unguarded; re-point owner → **operator (flag for ratification)** |
| `section-9-0-servability-polarity` | unguarded (owner SPR-08) | — | no production-path polarity guard on main | keep @unguarded; re-point owner → **SPR-03** (this spec's §9.0 servability sprint) |
| `section-5-voice-style` | unguarded (operator) | — | not mechanically guarded; may be human-judged | keep @unguarded, operator-owned (unchanged) |

The two "flip" calls are not assumed — they were **empirically proven** by
bringing each stranded sibling into the worktree and running it against live
main:

```
$ python -m pytest tests/test_graph_handle_isolation.py -q
E   ModuleNotFoundError: No module named 'substrate.graph_handle'
!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!

$ python -m pytest tests/test_provider_bootstrap.py -q
E   ImportError: cannot import name 'ProviderRegistrationError' from
    'substrate.dispatch.providers'
!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!
```

The siblings were then **deleted** (not committed); the two TOMLs carry no
`guard` / `[non_vacuity]` and instead name an honest owner sprint. Bringing the
guards alone would have re-introduced the §14.4 disease one vector over: a
registration that *looks* complete but whose guard cannot run. Bringing the
*production code* the guards need (`substrate/graph_handle.py`, the strict-posture
bootstrap, `scripts/dev_bootstrap.py`) is explicitly out of SPR-02's scope — that
code is owned by later sprints, and SPR-02 must not drag unowned guarded code onto
main to make a registration fit.

## Why a registry at all — the steelman and its rebuttal (fairness)

**Steelman — "skip the registry; rely on per-test coverage."** Every invariant
here already has (or will have) a test. A test suite that is green *is* the
proof the invariants hold. A second meta-layer enumerating those tests is
ceremony: it adds a file to maintain, a CI step to run, and a place for the
enumeration to drift from the tests it points at. Just keep the guards green and
delete the registry.

**Rebuttal — the §14.4 counterexample.** Per-test coverage cannot detect a
*vacuous* test. The §14.4 seam test was green for weeks — it asserted the pin
against a synthetic dict and never loaded the real `config.yaml`, so it passed on
code that had the displacement bug. A green suite told the operator nothing,
because "green" did not *mean* the invariant held. The registry's meta-check is
exactly the layer that closes this: it does not re-test the invariant, it proves
each guard is **collected + non-vacuous** — a guard with no recorded proof of
teeth is, by definition, NOT declared (the `[non_vacuity]` requirement), and a
guard that is skipped / xfailed / xpassed / missing reddens the meta-check
(proven on deliberately-broken fixtures, and freshly re-proven this session by
seeding a `@pytest.mark.skip` onto the real §14.4 guard → meta-check went RED →
revert → GREEN). The enumeration *cannot* silently drift from its guards because
the meta-check runs each guard node in-process every CI run; a deleted or renamed
guard reddens it immediately. That detection is impossible from per-test coverage
alone — which is precisely why the registry earns its keep.

## What would reverse each call

- **`single-writer-per-graph` → guarded.** Reverses the instant
  `substrate/graph_handle.py` (the GraphHandle seam) lands on main and
  `tests/test_graph_handle_isolation.py::test_two_handles_locks_do_not_contend`
  collects + passes there — SPR-04 (knowledge-units) composes the graph substrate
  through the single-writer path and is positioned to land it. Flip the TOML to
  `guarded`, restore the `negative_control` `[non_vacuity]` proof, and re-run the
  meta-check in the same PR (per ON-RAMP).
- **`providers-pinned-primary-fails-loud` → guarded.** Reverses the instant the
  strict-posture bootstrap (`require_pinned` / `config_path` /
  `ProviderRegistrationError` / `_pinned_primary_providers` /
  `scripts/dev_bootstrap.py`) re-lands on main and
  `tests/test_provider_bootstrap.py::test_synthesis_primary_absent_raises_loud`
  collects + passes. No sprint in THIS spec owns that feature, so the owner is
  flagged for operator ratification to assign.
- **`section-9-0-servability-polarity` → guarded.** Reverses when SPR-03 lands a
  production-path polarity guard (deny-by-default; serve full text only after the
  publish gate; no money on un-opted-in text).
- **`first-light-e2e` → guarded.** Reverses when an owner sprint is assigned and
  `tests/test_first_light_e2e.py` lands as an `@integration`-marked live-LLM run.
- **Keeping the 3 present guards `guarded`.** Reverses only if their guard nodes
  are deleted/renamed or stop loading the real `config.yaml` — at which point the
  meta-check reddens and the registration must follow the code honestly.

## Operator ratification (built ≠ ratified)

The registry *mechanism* is reconciled and wired for CI. Adopting it as binding
canon, defining the mandatory-invariant set + who may ratify an `@unguarded`
exemption, and the §5-voice feasibility question all remain **operator decisions**
— carried forward verbatim from `substrate/invariants/ON-RAMP.md` (Operator
ratification). SPR-02 adds two ratification flags: assign an owner sprint for
`first-light-e2e`, and assign the sprint that re-lands the strict-posture provider
bootstrap so `providers-pinned-primary-fails-loud` can flip back to guarded.
