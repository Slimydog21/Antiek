# Audit wave 4: what the repairs leave open

**Date:** 2026-09-23
**Status:** PROPOSED. Four operator calls, each with a recommendation, and four latent defects recorded with the condition that makes each one live. None of them is executed.
**Owner:** Antiek audit wave 4. It was an executing-refuter audit of eight surfaces wave 3 did not cover, at main `0222ed443`, using 78 agents. It confirmed 18 findings, refuted 17 and left 8 low-severity ones unverified.
**Builds on:** the wave-4 repairs that WERE engineering calls. They shipped as `#3413` (C10 deploy gate), the `fix/audit-wave4` stack (C01 C02 C03 C04 C06 C07 C08 C09 C11 C12 C13 C15 C16 C18, plus the daemon unit variable) and `#3412` (tracked symlink). Each has a test that was red before its fix and a mutation check. C05 (`owner_byot_dispatch.py`) and C14 (`UsagePanel.tsx`) sit inside the BYOT lane's open seam and were handed to it on #3400 rather than fixed in parallel.

---

## Why these are recorded and not built

The four calls in the first part change a policy: who is paid, what the demand test measures, whether a protected file may change, and what an unmetered provider costs on the books. The four latent defects in the second part are real mechanisms that no production path reaches today. Each one becomes live when a specific wiring change lands, so the right time to close it is that change, not now. The audit's rule was "record, recommend, do not guess", and this file is that record.

---

## Operator calls

### 1. Does an opted-out holder keep accruing escrow?

`ip_holders.accrue_escrow` credits a holder in any status. So the frame-attention, book and Speak paths all keep crediting a holder whose documents are still inside the 30-day content-removal window after opt-out. The wave-4 repair made an *unknown* holder raise (`UnknownIpHolderError`) instead of silently losing the money. It did not decide what an *opted-out* holder is owed. The options are (a) keep crediting until removal completes, (b) route the amount to `UNATTRIBUTED_RIGHTS_BUCKET`, or (c) send it to house.

**Recommendation:** (b). An opted-out holder has withdrawn consent to monetised serving. Money earned in the removal window is neither clearly theirs nor clearly the platform's, and the held bucket keeps it recoverable either way. Once decided, it goes in as a status predicate in `accrue_escrow`'s `UPDATE ... WHERE`, with the matching route in `accrue_window`, `book_escrow` and `speak/contributor`.

### 2. Wiring the demand gate's inputs (C17 residual)

The verdict now refuses to run (`GateNotRunnable`) when no in-window `export_offered` event reached a pinned tester. Before the repair it returned RETIRE, reporting missing telemetry as a finding about demand. Making the verdict computable means wiring real inputs. That involves three pieces of work: persisting `ExportRegistry` entries keyed by `(document_id, content_hash)` with the exporter; emitting `export_offered`/`export_taken` from the export routes; and appending `IngestResult.roundtrip_event` to a durable log under the `db_lock` single writer, from a real import route that passes the authenticated actor. The single-file `.antiek.html` branch of `ingest_antiek` never calls `classify_roundtrip`, although the pre-registration names that format. Whoever wires the emitters must route that branch too, or record it as a coverage gap in the verdict.

**Recommendation:** wire the inputs only once the pre-registered window is scheduled. Until then, `GateNotRunnable` is the honest state.

### 3. The daemon's daily cap is an unlocked read-modify-write, in a file the §7.4 tripwire freezes

`DaemonBudget.reserve` reads the day's sidecar, adds, and writes it back with no lock. In a repro, four concurrent runners were granted $12.50 against a $5.00 cap and left the sidecar corrupt. Production spends nothing today because both entry points run `no_op_spawn`. The fix is an `flock` around the read-modify-write, which is about ten lines, but `orchestration/continuous/budget.py` is one of the four files `tests/test_suggestions_surface.py::test_section_7_4_caps_are_byte_unchanged_vs_origin_main` pins byte-identical to `origin/main`. Any change to it goes red by design.

**Recommendation:** make the lock a precondition of the Sprint-14 PR that introduces a real `spawn_fn`. That PR must touch the daemon anyway and will need a deliberate tripwire update. Adding the lock now would require weakening the tripwire for code that spends nothing.

### 4. What a Prime Agent dispatch costs on the books (consequence of C06)

The C06 repair makes `substrate/dispatch/router.py` bill any successful call whose usage is unreported at its ceiling: one input token per prompt byte plus `effective_max_tokens`, at the tier's pricing. Before the repair it recorded a definite $0. `providers/prime_agent.py` always returns `raw_usage={}`, because `prime-agent -p` reports no token counts, so every Prime Agent call now records that ceiling at its base tier's price. A fallback or override inherits the base tier's pricing. This is correct under the finding's principle (unknown usage is not a free call), but it moves the Prime lane's spend figures and budget headroom.

**Recommendation:** if Prime is flat-rate for this operator, put it on a tier with zero pricing (explicitly free). If it is metered, surface real counts from `PrimeAgentRLMBackend`'s receipt as `raw_usage`. The one wrong answer is `reported=True` with zeros, which recreates C06. The owner of the Prime lane (#3399) has been told.

---

## Latent defects: real mechanisms with no production path today

| Where | Mechanism | Becomes live when |
|---|---|---|
| `orchestration/phase_log/log.py:163` + `phase_runner/runner.py:219` | A failed re-verify of a re-entered phase leaves `verified=True` and the earlier evidence in place, so `assert_ready_for_completion` passes. | Some driver continues after a failed verify. Every production driver aborts on one today (`_drive_phase` returns False). |
| `infrastructure/ansible/playbooks/deploy.yml` (`git pull`) | The gate clears one SHA and the pull takes the branch tip, so a merge that lands during the gate is pulled unverified. | The strict up-to-date ruleset is relaxed, or main takes a push outside a PR. Today the ruleset means every tip was tested as a PR head. The hard-to-vary fix pulls `antiek_target_sha`, which leaves the box on a detached HEAD, so it needs a run on the real host first. |
| `substrate/payouts/ledger.py:431-449` | The idempotency key hashes the whole input snapshot, so a retry with a changed non-impression input double-accrues, and `reconcile()` checks the writer's own stamp. | `book_escrow.accrue_reading_session` gets a production caller. It has none today. |
| `services/antiek_format/*` signature boundary | A self-carried key satisfies `signature_valid`. | This is wave-3 call #1 (`audit-wave3-design-calls.md`), which is still open. Wave 4 re-confirmed it. |

The CLI half of the phase-runner finding (a mistyped `--postcondition-module` silently falls back to an always-true check) is owned by draft #3255 and is not repeated here.

---

## Reconsider if

The first latent row is closed the day any orchestrator path is allowed to continue past a failed verify. The deploy row is closed the day `main-gate-integrity` stops being strict. Call 3 is moot if the Sprint-14 spawn wiring is abandoned.
