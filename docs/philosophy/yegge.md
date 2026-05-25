# Yegge canon — distilled truths

Source: Steve Yegge × Pragmatic Engineer interview, December 2025.
Stimulus pasted by operator 2026-05-24; brainstormed in
`~/specs/antiek-yegge-sharpen/` (per-axis chambers); executed in
`~/specs/antiek-yegge-execute/` (12 sprints; 5 shipped at canon v2 time —
SPR-02 + SPR-03 + SPR-09 + SPR-11 + SPR-12, the substrate-fit subset).

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

## T-Yegge-009 — Agent-loved REST envelope is additive; new routes adopt, legacy migrates later

Antiek's REST surface for new routes uses
`ResponseEnvelope[T] = {ok: bool, data?: T, error?: {code, message, details}}`.
The error-code set is **closed** (11 entries; expanding requires a
deliberate code-review touch on the constant) so that agent callers
can match on `error.code` rather than parsing strings. Failure paths
raise `EnvelopedHTTPException` so the central exception handler short-circuits
the dependency stack cleanly; the canonical failure shape comes from
one place. Legacy routes are intentionally NOT wrapped in the same
sprint that ships the convention — the operator has in-flight
parallel work on `app.py` + route modules, and a wrap-everything
migration would create guaranteed merge conflicts with zero
functional benefit. Migration is future-batch.

**Validated by:** SPR-09, commit `611eb6d`,
`interfaces/research/api/envelope.py` (ERROR_CODES closed-set test at
`tests/test_yegge_api_envelope.py::test_error_codes_set_is_closed`).

**Reverse if:** FastAPI ships a built-in envelope convention that
matches Antiek's needs; deprecation note + convention shift.

**See also:** T-Yegge-010 (idempotency); SPR-09's README at
`interfaces/research/api/README_yegge_spr09.md` for the convention
paste-templates.

---

## T-Yegge-010 — Idempotency: in-process, per-route, no cross-restart replay

POST/PUT routes opting in require an `Idempotency-Key` header;
cached responses keyed by `(route_id, key)`; replays return
`error.code="IDEMPOTENCY_REPLAY"` with the prior response in
`details`. The cache is **in-process only** (not persisted across
restarts) — deliberately, so a stale replay from a different code
revision cannot return the wrong shape after a deploy. Per-route
namespacing means the same key on different routes does not collide.
TTL default 24h + max 10000 entries (env-configurable;
FIFO eviction at capacity).

**Validated by:** SPR-09, commit `611eb6d`,
`interfaces/research/api/idempotency.py`. Per-route isolation +
TTL + eviction tests in `tests/test_yegge_api_envelope.py`.

**Reverse if:** a route legitimately needs cross-restart replay
(none today). Persistent storage adds operational surface and the
"stale replay across deploys" risk; current call is conservative.

**See also:** T-Yegge-009 (envelope).

---

## T-Yegge-011 — Federation is PULL-only with signed manifests + receiver-side quality gate

The federation contract is the substrate's design choice for
multi-instance knowledge exchange: receivers fetch (never push),
manifests are signed (HMAC-SHA256 scaffold, Ed25519-swap-ready
interface), each item content-addressed (sha256), receivers verify
signature + run the §13.9 quality gate + write only PASS items into
the receiver's own DB. The single-writer invariant
(`CLAUDE.md` critical invariant §1) survives by construction —
federation moves *artifacts* between substrates, never write
permissions.

This truth is the **substrate-fit rebuttal** to the brainstorming
chamber's proposed "message envelope + idempotency-key +
conflict-resolution clause" contract: PULL-only sidesteps all three
(no inbound writes → no conflicts; content-addressed manifests →
natural idempotency; `SliceManifest` IS the envelope). Documented
in `docs/federation/CONTRACT.md` with the rejection rationale
explicit.

**Validated by:** SPR-11, commit `b36f29b`,
`docs/federation/CONTRACT.md` + `docs/federation/ADAPTERS.md` +
the substrate at `substrate/federation/{__init__,protocol,signing,slice}.py`
(shipped pre-canon; this truth catches the canon up to the code).

**Reverse if:** partner relationships shift to "push artifacts when
generated" semantics (e.g., real-time collaboration). That would
require a new write-side invariant; today no partner has expressed
this need and the Sprint 30+ thread (`docs/sprint30_thread_decisions.md`
§2 Thread 1) gates partner relationships explicitly.

**See also:** T-Yegge-002 (single-writer); T-Yegge-012 (substrate-fit
discipline).

---

## T-Yegge-012 — Substrate-fit wins over spec fidelity; document the rejection

This is the meta-truth. SPR-01, SPR-04, SPR-05, SPR-07, SPR-08, SPR-10
were authored against an event_log assumed-to-be-generic; reality is
the event_log is the RL-trajectory store with a 60+-entry ActionType
enum scoped to investigations. SPR-11's brainstormed contract assumed a
multi-writer federation; reality is PULL-only-with-quality-gate. SPR-03
assumed class-based role decorators; reality is package-shaped roles
needing module-level constants. In every case the substrate-fit answer
is different from the spec answer — and the substrate-fit answer wins.

The discipline: **when the spec disagrees with the substrate, the
substrate is the truth and the spec gets a documented rejection with
the substrate-fit reason.** SPR-11's CONTRACT.md does this explicitly
in its "Why no message envelope / idempotency-key / conflict-resolution
clause" section. SPR-03's commit message does this for the
package-level-metadata reframing. This canon entry generalizes the
discipline.

**Validated by:** the entire SPR-02..SPR-12 shipped batch. Five sprints
delivered against twelve specced; the seven not-delivered are documented
in the "Pending validation" section below with the substrate-fit reason
for the deferral.

**Reverse if:** a future stimulus produces a spec that survives substrate
contact cleanly — at which point the spec was substrate-fit from the
start and this canon entry was an over-correction. The audit lives in
the per-sprint PR descriptions; the operator can confirm or refute.

---

## Pending validation (truths the brainstorming surfaces; substrate-fit
defers)

The remaining seven sprints from the brainstorm are deferred. Each has
a substrate-fit reason that's stronger than "not yet implemented."

- **SPR-01 — Event-log schema delta for `token_burn` + `worker_identity`
  event types.** Antiek's `event_log` is the RL-trajectory store scoped
  to `investigation_id` with a 60+-entry ActionType taxonomy
  (`substrate/schemas/events.py`). Adding `token_burn` and
  `worker_identity` as peer event-types would semantically pollute the
  trajectory store. The right answer is either (a) attach token usage
  to the existing `ROLE_CALL_END` span as a payload field, or (b) add
  a separate telemetry store with its own primitives. Either way is a
  larger design conversation than a one-sprint commit.
- **SPR-04 — Worker identity & registry.** Same substrate misfit:
  worker identity in Antiek is per-investigation, not global.
  A registry primitive would need to integrate with the existing
  `investigation_id`-scoped event_log.
- **SPR-05 — Token-burn middleware + dashboard.** Awaits SPR-01.
- **SPR-06 — Bitter-lesson sunset batch 1.** Risky without a dedicated
  operator-blessed sunset list; the operator's continuous-research
  daemon path is the highest-risk surface for unilateral removals.
- **SPR-07 — `spawn_variants` slot-machine primitive.** Awaits SPR-04.
- **SPR-08 — Operator attention budget + digest queue.** Awaits SPR-05
  signals.
- **SPR-10 — Recursive-summarization notebook cell.** Awaits SPR-04
  worker identity for grouping live workers.

Each candidate's path forward is recorded in the PR descriptions of
the shipped sprints + the SPR-12 v2 commit. A future stimulus or an
operator-blessed design conversation can convert any of these into a
T-Yegge-NNN entry once the substrate-fit shape is clear.
