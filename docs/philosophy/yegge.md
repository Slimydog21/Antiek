# Yegge canon — distilled truths

Source: Steve Yegge × Pragmatic Engineer interview, December 2025.
Stimulus pasted by operator 2026-05-24; brainstormed in
`~/specs/antiek-yegge-sharpen/` (per-axis chambers); executed in
`~/specs/antiek-yegge-execute/` (12 sprints, 3 shipped at canon-time).

This file is the **canonical truth set** for Yegge-derived design
decisions in Antiek. Each truth has a stable ID
(`T-Yegge-NNN`, never reused), an Antiek-specific
headline, a body grounded in shipped substrate, the **commit SHA** that
validates it, and the **reversal condition** that would change the call.

Read this file before designing anything in the
heresy-detection / role-shape / token-burn / spawn-orchestration axes.
If you find yourself about to ship a change that contradicts a truth
here, stop and update this file first — the canon is appended-and-revised
deliberately, not silently superseded by adjacent commits.

Companion: `~/specs/antiek-philosophy-canon/` (canon workflow);
sibling canon files for other interview stimuli live alongside.

---

## T-Yegge-001 — Heresy enforcement is mechanical, not prompt-warning

Agents reintroduce wrong invariants across sessions. Prompts and
LLM-judges are unreliable enforcers; pre-commit-time grep / AST gates
are not. Antiek encodes recurrent invariant violations in
`HERESIES.md` with a mechanical detector per entry; the pre-commit hook
refuses commits that introduce new violations.

**Validated by:** SPR-02, commit `e91b820`,
`tools/heresy_detectors/run_all.py` + `.githooks/pre-commit`.

**Reverse if:** a comparable LLM-judge becomes fast (<200ms),
deterministic, and free at pre-commit time. Until then, mechanical wins
because it always runs.

**See also:** T-Yegge-002, T-Yegge-003, T-Yegge-005.

---

## T-Yegge-002 — `syntheses` is single-writer, enforced by H-001 grep

`middleware/archive/archive.py` is the only sanctioned writer to the
`syntheses` table. Test fixtures and `scripts/exercise_substrate.py` are
whitelisted (they seed the table for dev). Every other call site that
issues INSERT/UPDATE/UPSERT/COPY INTO targeting `syntheses` is a heresy
and is blocked at pre-commit. This rule pre-dates the canon (it's also
in `CLAUDE.md` §"Critical invariants" and `docs/master-product-spec.md`
§16); the canon entry is what mechanically enforces it.

**Validated by:** SPR-02, commit `e91b820`,
`tools/heresy_detectors/h001_single_writer_syntheses.py`.

**Reverse if:** the substrate moves off DuckDB to a multi-writer store
with row-level conflict resolution AND the Phase-1 architecture
explicitly endorses multiple writers. Neither is on any roadmap.

**See also:** T-Yegge-003 (db_lock as the swap point); `CLAUDE.md`
critical invariant #1.

---

## T-Yegge-003 — `db_lock.connect_write` is the only sanctioned DuckDB write path

`runtime/db_lock.py` owns the cross-process advisory flock + the
`LockedConnection` forwarder. Raw `duckdb.connect(path)` for writes
bypasses the lock and re-introduces the multi-writer corruption that
prompted db_lock's existence (writer overlap between the daily ingest
cron, the weekly monitor cron, and on-demand workers). H-002 (AST)
catches violations.

**Validated by:** SPR-02, commit `e91b820`,
`tools/heresy_detectors/h002_missing_db_lock.py`. Whitelist
calibrated on 2026-05-24 sweep: `runtime/db_lock.py`,
`substrate/event_log/migrations/`, `tests/` (~30 legitimate
test-fixture cases vs zero production cases).

**Reverse if:** Quack v2.0 ships (per `db_lock.py` module docstring) and
the flock body becomes a Quack client call. The H-002 detector's
whitelist gets the new sanctioned entry; the rule itself stays.

**See also:** T-Yegge-002.

---

## T-Yegge-004 — Escape hatches require a reason, not just `noqa`

Bare `# noqa: H001` doesn't survive code review six months out. The
heresy detectors require `# noqa: HXXX -- <reason ≥12 chars>`; shorter
reasons are rejected at parse time (the regex itself does not match).
Twelve chars was chosen because "test fixture" is exactly 12 — the
shortest legitimate reason. The parser also surfaces the canonical
dashed form (`H-001`) so detector code can compare directly against
the `HERESIES.md` ID convention.

**Validated by:** SPR-02, commit `e91b820`,
`tools/heresy_detectors/_common.py:parse_noqa`.

**Reverse if:** an audit shows that operators consistently exceed the
12-char minimum with substantive reasons AND a tighter threshold would
provide more signal. Until then, the floor stays where the shortest
legitimate reason lands.

---

## T-Yegge-005 — Warn-only detectors are valid when the fix path isn't shipped yet

Shipping a blocking detector before its prerequisite either blocks all
existing call sites (loud false positives) or requires a whitelist that
adds no signal. H-004 (unobservable spawn) is the canonical example: at
Wave-1 it warns to stderr and lets the commit through, because the
worker registry doesn't ship until SPR-04. Flipping `MODE = "warn_only"`
to `"blocking"` is a one-line change when SPR-04 lands; the rest of the
detector is identical.

**Validated by:** SPR-02, commit `e91b820`,
`tools/heresy_detectors/h004_unobservable_spawn.py:MODE`. Lock-test in
`tests/test_heresy_detectors.py::test_h004_is_warn_only_at_wave_1`
prevents premature flipping.

**Reverse if:** SPR-04 (or a successor) ships `register_worker(...)`
and the H-004 mode flips. The test will fail at flip time — a
deliberate prompt to update HERESIES.md H-004 entry alongside.

---

## T-Yegge-006 — Two role shapes only: polecat or crew (no hybrids)

Yegge's load-bearing claim: there are only two natural role shapes.
*Polecats* are min-context, typed I/O, single-turn, ephemeral. *Crew*
are max-context, free-form I/O, multi-turn, cross-module. A "hybrid"
label is rationalization — when faced with one, split the role.
`substrate/role_shape.py:RoleMetadata.__post_init__` raises if shape is
neither.

**Validated by:** SPR-03, commit `a8a9e0d`,
`substrate/role_shape.py`. Audit at `tools/role_audit.py` reports
distribution: 9 polecat + 5 crew across Antiek's 14 roles as of
2026-05-24.

**Reverse if:** the next two model generations surface a workload
pattern that's stable, durable, and genuinely between the two shapes —
not a transient hack. Bitter-lesson framing: be skeptical.

**See also:** T-Yegge-007 (annotation pattern).

---

## T-Yegge-007 — Role metadata lives at the package level, not on decorators

Antiek's roles are package-shaped (a bundle of prompt + parser + helpers
spread across multiple files), not class-shaped. A decorator on one
entrypoint would lie to readers of the other files. Each role's
`__init__.py` declares a module-level `__role_metadata__` constant of
type `RoleMetadata`; the audit walks `roles/<name>/__init__.py` and
imports the constant. This is the Antiek-fit reframing of the spec's
original decorator proposal.

**Validated by:** SPR-03, commit `a8a9e0d`, 14 roles annotated,
`tools/role_audit.py` exits 0 in `--check` mode.

**Reverse if:** Antiek refactors roles into a class-based abstraction
(no current plan; would require a large parallel substrate change).

**See also:** T-Yegge-006.

---

## T-Yegge-008 — `spawn_pattern_doc` replaces tribal knowledge

Every role's metadata carries a 30+-char `spawn_pattern_doc` describing
what the caller passes and what to expect back. Validation enforces the
length at construction time so an author cannot ship a role without
writing it. The doc is the artifact a future agent reads to call the
role correctly — replacing the "ask Slack" / "read the prompt" mode.

**Validated by:** SPR-03, commit `a8a9e0d`,
`substrate/role_shape.py:_SPAWN_DOC_MIN_CHARS = 30`. Audit also flags
docs that are pure-repeated-character filler.

**Reverse if:** an audit shows operators consistently exceed 100 chars
with substantive content, suggesting the floor could rise. Currently 30
is the minimum-viable-sentence threshold.

---

## Pending validation (truths a future SPR could promote)

These are truths that the brainstorming chambers at
`~/specs/antiek-yegge-sharpen/` surface but no shipped sprint has
validated yet. Listed here as a checklist for future SPR-12-style passes.

- **Token burn is a first-class metric, never estimated.** Awaits SPR-05
  (`feature/yegge-spr-05-token-burn-middleware`), which Wave-2-fit
  ruled out for this batch because it requires a separate sprint to
  fit cleanly into Antiek's event_log RL-trajectory semantics.
- **Workers ≥100ms run-time must be first-class registered.** Awaits
  SPR-04 (worker registry).
- **Slot-machine `spawn_variants` requires verifier + external-kill.**
  Awaits SPR-07.
- **Operator attention is a finite resource defended by `OperatorAttentionBudget`.**
  Awaits SPR-08.
- **Agent-loved REST envelope: `{ok, data?, error?}` + idempotency-key.**
  Awaits SPR-09 (scoped to new + top-3 existing routes).
- **Notebook IS the face; voice/persona deferred.** Awaits SPR-10.
- **Federation contract is aspirational; Hermes is the reference adapter.**
  Awaits SPR-11.

Each is a candidate for promotion to a T-Yegge-NNN entry once the
corresponding sprint ships.
