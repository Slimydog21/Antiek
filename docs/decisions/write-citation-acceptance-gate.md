# Write citation acceptance gate

Status: executable closure of Write SPR-06

## Problem

Write validates generated citations but treats the result as advisory. A response
with a substantive uncited paragraph or a fabricated inline citation can still
return `generated`, replace the durable section draft, emit
`section.draft_generated`, and mount in the editor.

That contradicts the existing SPR-06 promise that every claim is cited. It also
breaks the evidence chain established before writing: exact synthesis provenance
and evidence-backed outline blocks do not protect the final artifact if generated
prose can cross the acceptance boundary without them.

## Decision

Citation validation is an acceptance gate, not a warning. A response may return
`generated` only when all of these conditions hold:

1. the creative-writer response parses;
2. the voice gate passes;
3. every substantive paragraph carries an inline citation;
4. each paragraph's inline citation set exactly matches its
   `prose_provenance` set; and
5. every cited block was attached to the section.

Failure of conditions 3-5 returns `citation_failed`. Rejected prose may be
reported for diagnosis, but its provenance is not returned as accepted state,
it is not persisted, no draft-generated event is emitted, and the browser does
not mount it as editable prose.

An attached block need not appear in the final draft. `uncited_blocks` remains a
legal declaration of non-use. Paragraphs shorter than the existing substantive
claim threshold remain structural and may be uncited, but any provenance on such
a paragraph must still agree with its inline citations.

## Ordering

```text
dispatch
  → parse structural response
  → validate inline citations against provenance and attached blocks
  → enforce voice gate
  → reject citation or voice failure without persistence
  → persist prose + provenance and emit draft event only on generated
```

## Required red proofs

- A clean cited response remains generated and persists once.
- One substantive uncited paragraph rejects the whole response.
- Provenance without a matching inline citation rejects the response.
- An inline citation without matching provenance rejects the response.
- Different inline and provenance block sets reject the response.
- A fabricated inline block id rejects the response.
- An unused attached block does not reject otherwise grounded prose.
- A short structural paragraph remains legal without a citation.
- Rejection preserves an earlier accepted draft and emits no draft event.
- The HTTP response and both Write generation surfaces distinguish citation
  failure and never mount rejected prose in the editor.

## Honest boundary

This is paragraph-level structural grounding. It proves that accepted paragraphs
name attached evidence consistently; it does not prove semantic entailment at
sentence or claim-span granularity. That deeper check requires a separately
specified verifier and must not be implied by this gate.

The production-factory route is exercised with a deterministic injected model
response, and both browser entry points are rendered in component tests. A
no-stub live-provider reachability probe cannot deterministically force a
citation failure without spending against an external model, so that smoke is
`NOT RUN` in this slice. This record does not claim provider-live verification.
