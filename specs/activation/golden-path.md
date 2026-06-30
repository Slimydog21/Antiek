# Activation golden path — Read

**Status:** frozen activation contract for Reader unboxing and dogfood.
**Created:** 2026-06-30.
**Source handoff:** `docs/specs/antiek-reader/handoff-to-activation.md`.

This is the operator-facing gate after antiek-reader SPR-09. CI proves
structural convergence; this file defines the live-use evidence required before
anyone may say "Read is done." The rule is simple: **CI is the floor; use is the
gate.**

## Non-closure banner

Reader SPR-09 green does **not** close Read. It proves:

- all open-document doors converge on the one Reader;
- forbidden production renderers are gone;
- document ingest/serve/render round-trip has a conformance test;
- cassette AI paths are labeled honestly.

It does **not** prove live Dialogue quality, live research spin-out quality,
deployed latency/recovery feel, or whether the operator would use the surface
for real work for 10 days.

## Activation dependencies

| Dependency | Required for | Evidence before walk |
|------------|--------------|----------------------|
| SPR-03 provider keys | Dialogue, research spin-out, enter-escalate search | `/health` or equivalent provider probe reports configured keys |
| Deployed app build | Real operator unboxing | exact URL, build SHA, and date recorded in dogfood log |
| Corpus paper with provenance | citation-open step | document id and cited source id recorded before walk |
| Dogfood log | activation SPR-07 closure | 10 distinct operator sessions, each with pass/fail notes |

If provider keys are absent, the walk may still run, but AI steps must remain
marked **INERT** and cannot count as activation closure.

## Golden path steps

Record every run in a dogfood log with date, build SHA, URL, operator, document
id, and the result of each step.

| Step | Operator action | Pass condition | Evidence to record |
|------|-----------------|----------------|--------------------|
| 1 | Open a real corpus paper through any normal door | The one Reader opens at `/read/:documentId` and renders rich structured blocks, not a flat fallback unless the source genuinely lacks `structured_blocks` | URL, document id, screenshot or note of visible heading/table/math/figure where present |
| 2 | Select a passage | Selection is stable and the shared FloatMenu appears without layout jump | selected text, action menu labels visible |
| 3 | Start Dialogue from the passage | With provider keys, a passage-anchored multi-turn thread returns a useful first answer; without keys, the UI states the activation boundary honestly | provider status, first answer or exact no-key copy |
| 4 | Spin out research from the passage | With provider keys, research starts with the selected passage as seed and shows a recoverable running state; without keys, the UI states the activation boundary honestly | investigation/session id or exact no-key copy |
| 5 | Click a citation/source marker | The cited real source opens in the same Reader at the cited chunk or nearest available anchor | source document id, chunk id/anchor, resulting URL |
| 6 | Return to the original paper | Back/return flow preserves reading context closely enough for continued work | note whether scroll/selection/context survived |
| 7 | Use the surface for actual reading work for at least 20 minutes | No dead end blocks the operator from reading, asking, tracing, or returning | free-form operator note with any friction |

## Dogfood closure rule

Activation SPR-07 closes only after **10 distinct operator sessions** satisfy the
dogfood log discipline:

- at least 5 sessions must use live provider-backed AI steps;
- at least 3 sessions must include citation/source tracing;
- at least 1 session must start from a non-Library door such as search, command
  palette, DRW citation, or Write trace-to-source;
- every failure or irritation gets a concrete follow-up row, not a vague note.

The final verdict must be one of:

- **ACTIVATE** — Read is daily-driver acceptable; remaining issues are bounded.
- **REPAIR** — one or more blockers prevent daily-driver use; list the blocking
  issue ids.
- **ROLL BACK CLAIM** — structural convergence remains useful, but the product
  claim "Read is done" is withdrawn.

## Executable log check

The dogfood log is JSONL: one session object per line. The validator is:

```bash
python tools/activation/read_dogfood.py path/to/read-dogfood.jsonl
```

It is intentionally a **closure guard**, not a session recorder and not an AI
quality judge. It checks that the log has the required fields, 10 distinct valid
sessions, at least 5 sessions with live provider-backed AI, at least 3 sessions
with citation/source tracing, at least 1 session from a non-Library door, and a
concrete follow-up issue for every logged failure or irritation. A green result
means the log satisfies the mechanical closure rule; the operator's session
notes still carry the qualitative verdict.

Minimal record shape:

```json
{
  "session_id": "2026-06-30-faisal-001",
  "date": "2026-06-30",
  "build_sha": "abc123",
  "url": "https://app.example/read/doc-1",
  "operator": "Faisal",
  "document_id": "doc-1",
  "entry_door": "library",
  "provider_status": "ready",
  "live_provider_ai": true,
  "citation_traced": true,
  "minutes_reading": 22,
  "steps": {
    "1": {"status": "pass"},
    "2": {"status": "pass"},
    "3": {"status": "pass"},
    "4": {"status": "pass"},
    "5": {"status": "pass"},
    "6": {"status": "pass"},
    "7": {"status": "pass"}
  }
}
```

For pre-key walks, steps 3 and 4 may use `"status": "inert"`; those sessions do
not satisfy the live-provider count. Any step with `"status": "fail"` or a
non-empty `"irritation"` must include `"followup_issue": "..."`.

## CI proxy

These commands remain useful before the live walk, but they do not replace it:

```bash
uv run --extra dev --extra urls --extra extraction python -m pytest substrate/contracts/__tests__/test_reader_conformance.py -q
cd apps/reading && npm test -- --run src/__tests__/oneReader.conformance.test.ts
cd apps/reading && npx tsc -b
```

The Storybook cassette proxy is:

```bash
cd apps/reading && npm run e2e -- operator-day.spec.ts
```

Passing the proxy means the walk script shape is intact. It does not mean live
AI or deployed operator feel is acceptable.
