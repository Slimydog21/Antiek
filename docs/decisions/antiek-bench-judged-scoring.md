# Antiek-bench judged weekly scoring

Status: Sprint 3 implemented; advisory evidence only.

The weekly verdict keeps deterministic live facts, qualitative axes, and evaluator uncertainty as three independent evidence layers. It deliberately defines no scalar composite. Existing callers receive the version-1 serialized payload unchanged; an explicit version-1 join manifest produces the version-2 weekly payload with judged fields.

Salted judged item and candidate-content hashes cannot be reconstructed from live records. The manifest is therefore the only authorized join bridge. Each entry fixes week, suite, task, live item and prompt hash, each model's exact live response hash and salted candidate hash, rubric version, evidence schema, and allowed judge panel. Both A/B and B/A records must match exactly. Task, item, model, response, order, rubric, judge, prompt, schema, panel, incomplete coverage, and budget variants fail closed as `NOT MEASURED` with structured suppression reasons.

Accepted evidence is reprocessed through the Sprint 2 disagreement, position-swap, anchor-calibration, and qualitative-verdict functions. JSON and self-contained HTML expose only hashes, fixed scores/statuses, versions, sample counts, digests, and structured derived reports. Prompts, responses, free-form rationales, evidence-reference excerpts, and secrets are excluded.

`auto_promotion` remains false. A separate `operator_acknowledgment_required` flag is true, but this sprint adds no export, install, selection, dispatch, routing, registry, or suite mutation authority. A future recommendation export may only be considered after operator acknowledgment and a separately reviewed authority change.

Live paid judging was not run, so live judged quality is **NOT MEASURED**. Calibration coverage, judge cost, real-world disagreement, and a defensible minimum sample threshold remain unproved. Until representative live samples cover every task, item, allowed judge, position order, rubric/policy version, and anchor set within budget, this is not a router benchmark and cannot justify routing or promotion.
