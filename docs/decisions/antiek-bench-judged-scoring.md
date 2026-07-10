# Antiek-bench judged scoring decision record

Status: Sprint 1 and Sprint 2 implemented; weekly integration intentionally not yet claimed.

## Decision

Antiek-bench keeps three evidence layers separate:

1. deterministic live facts: receipt attribution, availability, cost, latency, provenance, and
   keyword-proxy coverage;
2. blinded qualitative judgments: closed rubric axes and evidence references;
3. evaluator reliability: position-swap sensitivity, independent-judge disagreement, missing
   coverage, human-anchor calibration, and suppression reasons.

No hidden weighted composite combines these layers. Qualitative output is advisory and retains
`auto_promotion=false`. It has no model-installation, dispatch, suite-selection, or routing
authority.

## Implemented contract

- Evidence schema: `2`.
- Rubric version: `qualitative-v1`; the evidence identity also binds the complete rubric
  fingerprint, so changing axes or bounds without changing the label still invalidates evidence.
- Judge response schema: `1`.
- Judge policy: `blinded-pair-v1`.
- Candidate model/provider identity is absent from the judge request and evidence journal.
- Raw prompts, candidate bodies, free-form rationales, credentials, receipts, and external
  exception text are absent from persisted judged evidence.
- Evidence identity binds week, suite, item hash, ordered blinded candidate hashes, judge model,
  task-context hash, rubric version, and rubric fingerprint.
- Missing judges, failed swaps, position sensitivity, mixed rubrics, self-judging, equal scores,
  Condorcet cycles, excessive axis disagreement, and absent calibration suppress a winner.
- Schema-v1 evidence cannot be upgraded honestly because it lacks task-context and complete-rubric
  identity. Replay raises `EvidenceSchemaMigrationRequiredError`; an operator must reconcile or
  discard it. Repository inspection found no persisted judged JSONL, and paid judged evidence has
  not run.

## Weekly integration seam

The current live journal persists an unsalted SHA-256 `response_hash` for each exact model call.
The judged journal persists salted blinded candidate hashes and intentionally omits physical model
identity. The in-memory `PrivateJoin` currently maps labels to provider/model, but it is not a
durable or signed artifact and does not bind the live response hash to the blinded candidate hash.

Therefore, joining judged rows to weekly model rows by item/task alone, by tuple position, or by
model names supplied later would be unverifiable. Sprint 3 must first add an operator-local,
non-journaled join envelope that binds:

- exact week, suite, item, task, and prompt hash;
- live call ID, provider/model identity, and unsalted live response hash;
- blinded label and salted judged candidate hash;
- blinding policy version and a digest of the complete mapping;
- the exact evidence IDs, judge allowlist, rubric fingerprint, and position-swap pair.

The envelope may exist in process memory or an operator-private store, but must never be sent to a
judge or embedded in the public weekly HTML. The public verdict may embed only its digest and the
derived model-local qualitative axes. A forged prompt, response, model, order, judge, rubric, or
mapping digest must yield `NOT MEASURED`, never a partial join.

## Weekly acceptance threshold

A future advisory qualitative winner may be displayed only when all of the following hold for the
exact task/item panel:

- both live candidates completed with attributed receipts and non-empty response hashes;
- every judged candidate maps through the exact private join envelope to those live responses;
- every allowed independent judge supplied both presentation orders;
- no self-judging, failed evidence, missing panel row, mixed rubric, position sensitivity,
  Condorcet cycle, or indeterminate judge result exists;
- human-anchor calibration is complete for the declared anchor set;
- maximum axis disagreement is at or below the versioned operator policy;
- deterministic live evidence remains complete and within the approved budget cap.

Even then, deterministic facts, qualitative axes, and disagreement/calibration render in separate
columns and JSON sections. The result remains advisory, requires operator acknowledgment for any
future recommendation export, and cannot mutate routing or suite state.

## Evidence still missing

- No paid/live judge sample has run.
- No production judge pricing or approved judge-spend cap is recorded.
- No weekly join envelope implementation or public HTML projection exists yet.
- Human anchor coverage is fixture-only; it does not establish real evaluator accuracy.
- NotDiamond shadow evidence remains an inert comparison and has not proved routing superiority.

Until those gaps close, the weekly report must say `QUALITATIVE: NOT MEASURED`; the existing keyword
metric remains explicitly labeled a proxy and must not be renamed judged quality.
