# `mutants/` — the bounded mutant set for the fake-gate detector

This directory is the **data** half of `tools/fake_gate_detector.py` (Antiek ×
Beck Test-Integrity, SPR-02). It holds a **bounded, hand-curated, operator-
reviewed** set of mutant declarations plus the grandfathered survivor baseline.

The detector reads every `*.toml` here, flips ONE load-bearing line per mutant,
runs that mutant's targeting tests against the **existing (mocked) suite** (no
live model), and reports whether ≥1 test caught it. A surviving mutant — code
broken, suite still green — is a **fake gate**, the finding. See the tool's
module docstring for the engine + the SAFETY (byte-for-byte sha256 restore)
contract.

## Why a bounded set, and NOT mutmut / cosmic-ray (the CI-cost decision)

Full mutation testing (mutmut, cosmic-ray) generates thousands of mutants and
**reruns the affected test suite per mutant**. On Antiek's ~5,088-test suite
under the repo's **40-minute CI ceiling**, a whole-tree mutation campaign is
unaffordable: even a few hundred mutants × a multi-minute suite run blows the
budget by orders of magnitude, and most auto-generated mutants are noise (a
flipped log level, an off-by-one in an unreachable branch) whose survival means
nothing. That is the **rejected alternative** (master spec out-of-scope).

This tool is **mutation-LITE**: a *named handful* of lines each chosen because
Antiek **already treats it as load-bearing**, each carrying a `rationale` that
defends it, each pointing its `test_selector` at the **single module** that
should catch it. The whole set runs in well under a minute (the heaviest seed
selector is <3s; the per-mutant timeout is 300s, ~100× headroom). It fits the CI
ceiling **by design** and produces signal, not noise. It generalizes `ci.yml`'s
**invariant-registry meta-check** ("the §14.4 fake-green disease" kill) from one
registry to this bounded named set.

It proves a gate is **behavior-sensitive** (not fake). It **cannot** prove a gate
is **fully real** (that the mocked behavior matches the live model) — that
residual is first-light's job.

## The bounded-set policy (how the set grows)

- The set is **bounded by design**. It grows **only by operator-reviewed
  addition** — never automatically, never by a generator. (`fake_gate_detector`
  has no `--add` mode; auto-adding mutants is explicitly out of scope.)
- Every mutant **must** carry a defensible `rationale`: a no-op of the line must
  change **user-visible behavior**. A no-op of a logging/comment line *should*
  survive and is **not** a fake gate — such lines do not belong in this set
  (rigor #2: steelman every mutant as load-bearing before adding it).
- Anchors are **AST-resolvable** (`qualname` + a statement `match` substring),
  **not** bare line numbers — so a refactor that moves the line does not silently
  produce a false pass. If the anchor no longer resolves, the detector reports
  `anchor-stale` (a loud signal to re-anchor the mutant), never a pass.

## The mutant TOML format

Each file carries one or more `[[mutant]]` array-of-tables entries:

```toml
[[mutant]]
id = "serve_gate.drift_check_invert"        # unique, stable id (sort key)
target = "substrate/books/serve_guard.py"   # repo-relative path
op = "invert_guard"                          # noop | early_return | invert_guard | swap_compare
anchor = { qualname = "serve_full_text_guarded", match = "if ctx.tier is not None and not body_servable(ctx.tier):" }
test_selector = ["tests/test_serve_guard.py", "-k", "drift or t1_servable"]
rationale = """why this line is load-bearing (a no-op changes user-visible behavior)"""
added = "2026-06-04"
added_by = "abt-02 fake-gate-detector seed"
# swap = "=="   # swap_compare only: the exact comparison token to flip (optional)
```

**Fields**: `id`, `target`, `op`, `anchor` (`qualname` + `match`),
`test_selector` (a pytest arg list — a path/node and/or `-k` expr that SHOULD
catch the mutation), `rationale`, `added`, `added_by`, and `swap` (optional,
`swap_compare` only).

**Mutation ops**:
- `noop` — replace the matched statement with `pass` (the statement does nothing).
- `early_return` — replace the matched statement with `return` (the function exits
  before it / the rest of the body).
- `invert_guard` — flip a single-line `if`/`elif`/`while` guard
  (`if X:` → `if not (X):`; `if not X:` → `if (X):`).
- `swap_compare` — flip one comparison operator (`==`↔`!=`, `in`↔`not in`,
  `is`↔`is not`, `>=`↔`<`, …) on the matched line.

The detector **verifies the mutated source PARSES** before running it — a mutant
whose op cannot mutate its anchor (e.g. `swap_compare` on a line with no
comparison) is a mutant-authoring error, surfaced as `anchor-stale`, never run.

## Outcomes (what the detector reports per mutant)

| Outcome | Meaning |
|---|---|
| `killed` | ≥1 targeting test **ran and FAILED** on the mutation — the gate is **real** (good). |
| `survived` | all targeting tests that ran **PASSED** on broken code — **FAKE GATE**, the finding. |
| `no-tests` | the selector matched **zero runnable tests** (or only collection errors) — also a finding: an unguarded load-bearing line, or a selector defect. |
| `anchor-stale` | the anchor no longer resolves (a refactor moved/removed the line) — re-anchor the mutant; **NOT** a false pass. |
| `timed-out` | the test run exceeded the per-mutant timeout (default 300s) — **NOT** survived, **NOT** killed; the file is restored. |

### Collection errors and node-level setup ERRORs are not blindly counted as kills (rigor #1)

A **COLLECTION error** (a file that fails to import, e.g. a missing optional dep)
is **never** counted as a kill — it reds whether or not the code is mutated, so
counting it as a kill would mask a fake gate. Selectors must point at
**cleanly-collectable** tests; a selector that only produces collection errors is
reported as `no-tests` (a selector defect to fix). This is enforced by the
parser (`_parse_pytest_output` separates runtime FAILED tests from collection
errors) and unit-tested.

A **node-level setup/fixture ERROR** (`ERROR tests/x.py::test_foo`, a `::` node —
not a file) is the tool's **cardinal risk** and is handled with the same
discipline. Such an ERROR is **not** a test-body `FAILED`; it is a setup/fixture
error on a *collected* test. A **mutation-caused** one is a legitimate kill (e.g.
the `db_lock.connect_write_open_early_return` mutant makes `connect_write` return
`None`, so every fixture that opens a write connection ERRORs), **but** a
**pre-existing** broken fixture on a survivor's selector would ERROR *identically*
without any mutation — and crediting that as a kill is a **FALSE kill that MASKS a
fake gate** (the exact disease this tool fights).

**The kill rule (mutation-causation, round-2 sharpen):** a node-level ERROR
counts toward a kill **only if it is NEW under the mutation** — i.e., it does
**not** also ERROR on the **clean (un-mutated) tree**. The parser
(`_parse_pytest_output`) stays **neutral**: it harvests node ERRORs into
`node_error_nodes` but does **not** fold them into `n_ran` / `n_failed_runtime`.
`run_mutant` then resolves causation: when (and only when) the mutated run
produced node ERRORs, it re-runs the same selector once on the **restored clean
tree** and subtracts the node ERRORs that already ERROR there; only the remaining
(new) ones are credited as kills. The clean re-run happens **only** in the
node-error case (the common path has none → zero extra cost, determinism
unchanged), and it restores the **same original bytes** the engine's `finally`
restores, so the sha256 restore-integrity proof is untouched. If **all** observed
node ERRORs are pre-existing, the mutant is reported `no-tests` (a selector/fixture
defect to fix), **never** a false `killed`. (If the clean re-run itself times out,
the conservative direction is taken — node ERRORs are treated as new/kills —
since masking a fake gate is the worse failure.) Both halves are unit-tested:
the parse-layer neutrality + bare-node-ERROR non-kill, the end-to-end
pre-existing→`no-tests`, and the end-to-end mutation-caused→`killed`.

## The survivor baseline (`survivors_baseline.json`)

On a suite the autopsy calls **diseased**, the first run finds survivors. Per
`docs/decisions/ci-informational-gates.md` you **cannot fail CI on a backlog**.
`survivors_baseline.json` grandfathers the known survivors, mirroring **exactly**
the capture/enforce/stale contract of `tools/lints/cli_with_baseline.py` +
`tools/lints/baseline.py` (schema-versioned, sorted, diff-stable JSON):

- `--capture` writes the current findings (survivors + no-tests) to the baseline;
  the operator commits it. Each entry records `id`, `path_line`, `kind`,
  `rationale`, and `captured_at` — so the backlog is a **visible to-do with
  provenance**, not a hidden free pass.
- `--enforce` reds (**exit 1**) **only** on a finding NOT in the baseline — a NEW
  fake gate. Grandfathered findings exit 0.
- `--enforce --stale` additionally reports baselined findings now `killed`
  (someone wrote a real test) so the operator can shrink the baseline — it only
  ever moves **down**, never silently up.

The detector exits 0 in `--measure` (it reports); exit 1 only in `--enforce` on a
NEW survivor. SPR-06 wires it into CI **informational-first** (no CI workflow is
edited here).

## Current seed set (9 mutants)

Seeded from lines Antiek **already** treats as load-bearing, plus the census's
five lowest-predictiveness modules as context:

| file | mutants | the load-bearing line(s) |
|---|---|---|
| `serve_gate.toml` | `serve_gate.drift_check_invert`, `serve_gate.linkback_invert` | §9.0 serve-boundary: the license-tier drift cross-check + the arXiv link-back invariant in `serve_full_text_guarded`. |
| `db_lock.toml` | `db_lock.connect_write_open_early_return`, `db_lock.stale_pid_liveness_noop` | the DuckDB single-writer connection-open in `connect_write` (a real, **killed** gate), and `_stale_pid_check`'s `os.kill(pid, 0)` dead-holder probe — whose true effect is **stale-lock-FILE hygiene** (unlinking the orphaned `<db>.write.lock` + its stamped PID a dead writer left behind), **not** deadlock prevention: the OS auto-releases the flock on death and `connect_write` re-creates the lock file via `os.open(..., O_CREAT)` at `db_lock.py:280`, so a new writer acquires the lock regardless. This is the lone grandfathered **survivor** (an under-tested hygiene path, not a tool bug). |
| `rubric.toml` | `rubric.voice_weight_constant_noop`, `rubric.insufficient_evidence_floor_noop` | §14.4 inline rubric: the heaviest composite weight `W_VOICE_STYLE`, and the insufficient-evidence floor in `score_synthesis`. |
| `rate_governor.toml` | `rate_governor.is_arxiv_url_host_match_swap`, `rate_governor.govern_if_arxiv_guard_invert` | arXiv egress guard: the host membership check in `is_arxiv_url` + the routing guard in `govern_if_arxiv`. |
| `positive_control.toml` | `positive_control.owner_boundary_second_owner_invert` | **KNOWN-REAL positive control** — the second-owner flag in the `owner_boundary_check` lint that backs the `boundary` invariant (already covered by `ci.yml`'s invariant-registry meta-check). Must be `killed`; if it is not, the detector's kill detection is broken. |

The two fixture-only mutants the detector's own tests use live separately in
`tools/tests/fixtures/fake_gate/mutants.toml` and are **not** part of this real
set.
