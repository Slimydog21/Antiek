# ARE-01 — mypy --strict guardrail for substrate core

**Date:** 2026-05-25
**Branch:** `are/wave-1-substrate-additive`
**Source spec:** `~/specs/antiek-rust-execution/` ARE-01
**Status:** ✅ Enforcement slice landed — substrate-core is strict-clean + a baseline guardrail locks it.

## The reversal

The Wave 1 ADR (`are-wave-1-substrate-additive.md`, 2026-05-24) documented **35 `mypy --strict` errors** in `runtime/db_lock.py` + `substrate/event_log/events.py`, deferred as ARE-01 because fixing the invariant-#1 enforcement file in-place was too risky to do without operator review.

Between then and now, the parallel DDIA-execution stream fixed them. Commit `f6c64b0 feat(ddia-exec): db_lock I2 fix + dispatch idempotency contract` and adjacent commits cleaned up the type annotations. As of this commit:

```
$ ./.venv/bin/mypy --strict runtime/db_lock.py substrate/event_log/
Success: no issues found in 6 source files
```

So ARE-01's *fix* half happened — via a different stream, deliberately, with operator-stream review (the right way). What was missing was the *guardrail* half: nothing prevents the 36th strict error from landing tomorrow.

## What landed

`tools/lints/mypy_strict_baseline.py` — capture/enforce mypy-strict errors against a baseline, reusing the `tools/lints/baseline.py` infrastructure (the same ViolationKey / grandfathering / stale-detection the no_raise + bypass lints use). A mypy error becomes a `ViolationKey` with `kind = "mypy:<error-code>"`.

The key adapter deliberately **excludes the human-readable message** from the identity — two errors of the same code at the same location are "the same offense" even if mypy's wording changes across versions. Code + location is the stable key; including the message would make the baseline brittle to mypy upgrades.

`tools/lints/baselines/mypy_strict_substrate_core.json` — captured today: **0 grandfathered errors**. This is the strongest possible floor — zero tolerance. Any NEW strict error in `runtime/db_lock.py` or `substrate/event_log/` fails the gate, because there are no pre-existing errors to grandfather.

## Why a baseline at 0 rather than no guardrail

The substrate-core being clean today is not self-enforcing — the next refactor could reintroduce an untyped def or an `Optional` leak. The empty baseline + the enforce check makes the clean state a *ratchet*: it can only stay clean or the operator must consciously re-capture (which surfaces in PR review as a baseline change). This is the PostHog discipline — once you've paid down a class of debt, install the guardrail so it can't silently return.

## Usage

```bash
# CI / pre-merge: fail on any NEW strict error in substrate-core
python -m tools.lints.mypy_strict_baseline enforce \
    --paths runtime/db_lock.py substrate/event_log/ \
    --baseline-file tools/lints/baselines/mypy_strict_substrate_core.json \
    --check-stale

# After a deliberate change that adds a justified strict error,
# re-capture (the change shows up in PR review):
python -m tools.lints.mypy_strict_baseline capture \
    --paths runtime/db_lock.py substrate/event_log/ \
    --baseline-file tools/lints/baselines/mypy_strict_substrate_core.json
```

## Tests

16 tests in `tests/test_lints_mypy_strict_baseline.py`:

- Parser: extracts errors not notes/summary; captures code + location; handles col-present / col-absent / code-absent; ignores unmatched lines; empty output → empty.
- Key adapter: excludes message (mypy-version robustness); kind prefix; distinguishes codes.
- Capture/enforce flow (fake mypy via monkeypatch): capture writes baseline; enforce-after-capture returns 0; enforce flags a NEW error; `--check-stale` flags a fixed entry (rc=1 so operator re-captures); missing baseline → rc=2; mypy-invocation-failure → rc=2.

The unit tests use a captured real-mypy-output fixture string + a monkeypatched `run_mypy_strict` — no live subprocess (which would couple to the venv's mypy version + the live substrate error count).

## Wiring into the substrate floor

The operator can add this to `.github/workflows/substrate_floor.yml` as a step:

```yaml
      - name: mypy --strict guardrail (substrate core, baseline-enforced)
        run: |
          python -m tools.lints.mypy_strict_baseline enforce \
            --paths runtime/db_lock.py substrate/event_log/ \
            --baseline-file tools/lints/baselines/mypy_strict_substrate_core.json \
            --check-stale
```

Not added automatically in this commit because the floor workflow's path-trigger list would need to include `runtime/db_lock.py` + `substrate/event_log/**`, and that file is owned by the parallel DDIA-execution stream — coordinating the trigger-list edit needs operator sign-off to avoid colliding with their CI changes.

## What ARE-01 still does NOT do

The guardrail enforces "stay clean." It does NOT:
- Extend strict enforcement to other substrate packages (only db_lock + event_log; the floor extends one package at a time).
- Fix the `runtime/db_lock.py:510` Optional/`open()` site that the Wave 1 ADR flagged — that's now resolved by the parallel stream's fix (mypy is clean), so the concern is closed.

## Self-ratification

- **Intellectual honesty:** the Wave 1 ADR predicted 35 errors needing a risky fix; the honest update is "the parallel stream fixed them, so my contribution is the guardrail, not the fix." Documented the reversal plainly rather than claiming I fixed them.
- **Fairness:** considered grandfathering-35 vs guardrail-at-0. The 35 are gone, so a baseline at 0 is both available and strictly stronger. Chose it; documented why (ratchet discipline).
- **Rigor:** the message-exclusion in the key adapter is a deliberate robustness choice tested explicitly (`test_mypy_error_to_key_excludes_message`). Parser tested against real captured mypy output, not a synthetic string.
- **Diligence:** reused `tools/lints/baseline.py` rather than inventing a parallel grandfathering mechanism. Verified the substrate-core is actually clean (`Success: no issues found in 6 source files`) before capturing the empty baseline.
- **Defensibility:** the CI wiring snippet is in this ADR so the operator can add the step when ready; the reason it's not auto-added (trigger-list collision with parallel stream) is recorded.
