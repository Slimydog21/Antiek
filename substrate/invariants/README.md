# `substrate/invariants/` — the CI-green-means invariant registry

> One registry of every load-bearing invariant, each bound to a guard test that
> **fails when the invariant is violated** — so "CI is green" *means* something.
> A stub / empty / always-pass guard counts as **NOT declared**.

Built by **SPR-06** of the Antiek Foundation spec (the KEYSTONE: SPR-08/09/10
register into it). Mechanism built ≠ ratified — see *Operator ratification*
in `ON-RAMP.md`.

## Why this exists

This session proved CI could be **fake-green** on Antiek's most consequential
invariant. The §14.4 synthesizer pin had a "seam test" that asserted the
desired tier against a *synthetic* config and never loaded the real
`config.yaml` — so a money / provenance / measurement displacement bug
(Opus → DeepSeek on the human-read synthesis artifact) passed CI for weeks.

Five independent brainstorm lenses converged on the same fix: a registry where
every invariant declares its guard, and a meta-check that *proves each guard is
non-vacuous*. An empty / stubbed signal is the disease; surfacing it is the cure.

## The format — one file per invariant

Each invariant is its own `substrate/invariants/<id>.toml`. One declaration per
file keeps registrants **file-disjoint** (SPR-08/09/10 each add their own file;
no shared manifest serializes them). The file is **data, not prose** — parsed
with the stdlib `tomllib`, consumed mechanically by the meta-check.

```toml
[invariant]
id = "section-14-4-synthesis-pin"        # MUST equal the filename stem
statement = """Why it matters — the COST if violated, not just a name."""
status = "guarded"                        # "guarded" | "unguarded"
guard = "tests/test_x.py::test_node"      # path::node (pytest) or a script path
guard_kind = "pytest"                     # "pytest" (default) | "script"
assertion = "What the guard proves, in one line."
sunset = "Sprint-20 §14.4 verdict"        # "" if permanent

# Required for status="guarded": proof the guard is NOT fake-green.
[non_vacuity]
method = "fail_before_pass_after"         # | "negative_control" | "mutation"
detail = "fail_before=7 pass_after=27 @7dc7ed5"
```

For an **honest gap** (no real guard yet):

```toml
[invariant]
id = "section-9-0-servability-polarity"
statement = """..."""
status = "unguarded"
owner = "SPR-08"                          # the sprint that supplies the guard
assertion = "..."
# NO guard, NO non_vacuity — the meta-check FAILS if an unguarded entry claims one.
```

## Fields

| Field | Required | Meaning |
|---|---|---|
| `invariant.id` | yes | Stable slug; **must equal the filename stem**. |
| `invariant.statement` | yes | WHY it matters — the cost if violated (rigor #5). |
| `invariant.status` | yes | `guarded` or `unguarded`. |
| `invariant.assertion` | yes | What the guard proves, one line. |
| `invariant.guard` | guarded only | `path::node` (pytest) or a script path. |
| `invariant.guard_kind` | no | `pytest` (default) or `script`. |
| `invariant.sunset` | no | When the invariant retires (`""` = permanent). |
| `invariant.owner` | unguarded only | The sprint that will supply the guard. |
| `[non_vacuity].method` | guarded only | `fail_before_pass_after` \| `negative_control` \| `mutation`. |
| `[non_vacuity].detail` | guarded only | Free-text proof description. |

## What the meta-check enforces

`tests/test_invariant_registry_meta.py` is the anti-stub-hack gate. For every
declaration it asserts:

* **guarded** → the guard file exists, the node id is **collected** by pytest,
  is **not** `@pytest.mark.xfail` (neither a genuinely-failing xfail nor an
  incidentally-passing xpass counts as a live guard), runs **green** at call
  time, and a `[non_vacuity]` proof is present and well-formed. A guard that is
  missing, skipped, xfailed, xpassed, or stubbed-to-always-pass **reddens** the
  meta-check (proven on deliberately-broken fixtures in the same test file).
* **unguarded** → an `owner` sprint is named and **no** guard / non-vacuity is
  claimed (an unguarded entry cannot fake completeness).

Run it:

```bash
pytest tests/test_invariant_registry_meta.py -q
```

## Invariant inventory + guard status (SPR-06 M1)

The diligence pass that seeded this registry. "fake-green found" is the §14.4
seam test — the canonical example of what the meta-check must catch.

> **Reconciled to live main by SPR-02 (Antiek Flywheel Foundation).** This
> registry was authored on the prior foundation branch and *stranded* there
> (never merged to main). Three guards land guarded because their nodes genuinely
> collect + pass on main. Two staged invariants flip to **@unguarded** because
> their guards target production code that stranded too and is NOT on main —
> declaring them guarded would point at a guard that ImportErrors at collection,
> the exact fake-completeness this registry cures. See
> `docs/decisions/2026-05-31-invariant-registry-reconcile.md`.

| Invariant | Status | Guard (node / owner) | Classification |
|---|---|---|---|
| §14.4 synthesis pin | guarded | `tests/test_dispatch_synthesis_pin.py::test_default_deep_synthesizer_stays_pinned_to_opus_with_deepseek_live` | **was fake-green** (synthetic-config seam test, never loaded real `config.yaml`) → now guarded non-vacuously by SPR-01 (fail_before=7 → pass_after=27); node present on main |
| provenance chain — no-copy seams | guarded | `tests/test_seam_no_copy.py::test_read_to_write_copy_fails_the_guard` | guarded non-vacuously (forked-id rejected; composed in `test_integration_invariants`); node present on main |
| single graph writer (remote-exec funnel) | guarded | `tests/test_remote_exec_isolation.py::test_connect_write_only_in_funnel` | guarded non-vacuously (writer-is-real-not-absent half); node present on main |
| single-writer per graph | **@unguarded** | owner SPR-04 | guard targets `substrate/graph_handle.py` — **absent on main** (stranded); declaring guarded would ImportError at collection. Flips to guarded when SPR-04 lands the GraphHandle seam |
| providers pinned-primary fails-loud | **@unguarded** | owner operator (flag for ratification) | guard targets the strict-posture bootstrap (`require_pinned` / `ProviderRegistrationError` / `scripts/dev_bootstrap.py`) — **absent on main** (stranded); main's `register_default_providers` takes only `quiet`/`only`. Flips to guarded when the strict bootstrap re-lands |
| §9.0 servability polarity | **@unguarded** | owner SPR-03 | no production-path guard yet — honest gap; SPR-03 (this spec's servability sprint) supplies it |
| §5 voice/style discipline | **@unguarded** | owner: operator (unassigned) | not mechanically guarded; may be human-judged — flag for operator |
| First Light e2e | **@unguarded** | owner operator (flag for ratification) | guard `tests/test_first_light_e2e.py` not on main; no First-Light sprint in this spec — flagged for the operator to assign an owner |

The existing single-source discipline this registry **extends** (not reinvents):
`tools/codegen/check_conformance.py` (a registry-of-rows exit-code gate),
`tools/codegen/emit_types.py` (Pydantic→TS codegen staleness gate), and
`tests/test_integration_invariants.py` (a data-manifest of seam guards). The
registry mirrors their "declarations are data, one meta-check verifies them" shape.

## Adding an invariant

See `ON-RAMP.md` — the recipe SPR-08/09/10 follow.
