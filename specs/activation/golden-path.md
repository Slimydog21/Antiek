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
| 2 | Select a passage | Selection is stable and the shared FloatMenu appears without layout jump | selected text, visible action labels: `Note`, `Dialogue`, `Search`, `Deep-research` |
| 3 | Start Dialogue from the passage | With provider keys, a passage-anchored multi-turn thread returns a useful first answer; without keys, the UI states the activation boundary honestly | provider status, first answer or exact no-key copy |
| 4 | Spin out research from the passage | With provider keys, research starts with the selected passage as seed and shows a recoverable running state; without keys, the UI states the activation boundary honestly | investigation/session id or exact no-key copy |
| 5 | Click a citation/source marker | The cited real source opens in the same Reader at the cited chunk or nearest available anchor. Reader-origin citation walks carry return-origin context; Write trace-to-source opens directly from the writing surface. | source document id, chunk id/anchor, resulting URL; include `from=<original document id>` for Reader-origin walks |
| 6 | Return to the original paper | Back/return flow preserves reading context closely enough for continued work | note whether scroll/selection/context survived |
| 7 | Use the surface for actual reading work for at least 20 minutes | No dead end blocks the operator from reading, asking, tracing, or returning | free-form operator note with any friction |

For no-key sessions where steps 3 or 4 are marked `"inert"`, record the exact
UI boundary copy as `exact_no_key_copy`. The validator also accepts
`no_key_copy`, `activation_boundary_copy`, or `boundary_copy` aliases so older
operator notes can be normalized without losing the literal copy.

For step 1, record either a screenshot reference (`screenshot`,
`screenshot_url`, or `screenshot_path`) or a visible-reader note
(`visible_content_note`, `structured_content_note`, or `render_note`). For step
2, `menu_labels` must include the four shared FloatMenu actions: `Note`,
`Dialogue`, `Search`, and `Deep-research`. For step 5, `result_url` must be an
HTTP(S) `/read/{source_document_id}` URL carrying the recorded `chunk_id` or
`anchor`. Reader-origin citation walks must also carry `from=<document_id>`
return context. `entry_door` values `write_trace` and `write_trace_to_source`
are valid without `from=` because the operator entered from the Write surface,
not from another Reader document. For step 6, record `return_context_note`;
`context_note` and `scroll_context_note` are accepted aliases.

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

To seed a new operator-authored row without hand-copying the schema, print a
single JSONL-compatible template and replace the evidence before appending it:

```bash
python tools/activation/read_dogfood.py --template inert
python tools/activation/read_dogfood.py --template live
python tools/activation/read_dogfood.py --template live-citation
python tools/activation/read_dogfood.py --template write-trace-citation
```

Use `write-trace-citation` only for a session that starts from the Write
surface trace-to-source affordance. Its step 5 URL opens the traced Reader
source with chunk/anchor evidence but intentionally has no Reader-origin
`from=` return parameter.

To create or extend a dogfood log directly, append the selected template and
then edit the appended line with the real session evidence:

```bash
python tools/activation/read_dogfood.py --template live-citation --append reports/read-dogfood.jsonl
python tools/activation/read_dogfood.py --template write-trace-citation --append reports/read-dogfood.jsonl
python tools/activation/read_dogfood.py --template live-citation --append reports/read-dogfood.jsonl --json
```

It is intentionally a **closure guard**, not a session recorder and not an AI
quality judge. It checks that the log has the required fields, 10 distinct valid
sessions, at least 5 sessions with live provider-backed AI, at least 3 sessions
with citation/source tracing, at least 1 session from a non-Library door, and a
concrete follow-up issue for every logged failure or irritation. A green result
also requires the final record to declare `"verdict": "ACTIVATE"`. The
validator does not judge answer quality; it only checks that the operator's
qualitative verdict is present and belongs to the allowed set. A `"REPAIR"`
verdict must include non-empty `"blocking_issue_ids"`.

For orchestration, `--json` includes `remaining_requirements` with the four
closure counters still missing: valid sessions, live-provider sessions,
citation-traced sessions, and non-Library sessions. These numbers are planning
guidance only; they do not replace the operator's qualitative verdict.

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
  "verdict": "ACTIVATE",
  "steps": {
    "1": {
      "status": "pass",
      "visible_content_note": "visible heading and structured blocks"
    },
    "2": {
      "status": "pass",
      "selected_text": "highlighted passage text",
      "menu_labels": ["Note", "Dialogue", "Search", "Deep-research"]
    },
    "3": {
      "status": "pass",
      "first_answer": "first provider-backed answer"
    },
    "4": {
      "status": "pass",
      "investigation_id": "research-session-1"
    },
    "5": {
      "status": "pass",
      "source_document_id": "source-doc-1",
      "chunk_id": "chunk-1",
      "result_url": "https://app.example/read/source-doc-1?chunk=chunk-1&from=doc-1&fromPage=0"
    },
    "6": {
      "status": "pass",
      "return_context_note": "back/return preserved reading context"
    },
    "7": {
      "status": "pass",
      "operator_note": "read for 22 minutes; no blocking friction"
    }
  }
}
```

For pre-key walks, steps 3 and 4 may use `"status": "inert"`; those sessions do
not satisfy the live-provider count. Any step with `"status": "fail"` or a
non-empty `"irritation"` must include `"followup_issue": "..."`.

Only the final record needs `"verdict"`. It must be one of `"ACTIVATE"`,
`"REPAIR"`, or `"ROLL BACK CLAIM"`. `"REPAIR"` is explicit non-closure and must
also include `"blocking_issue_ids": ["READ-..."]`; `"ROLL BACK CLAIM"` is also
explicit non-closure. Only `"ACTIVATE"` can make the validator exit 0.

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
