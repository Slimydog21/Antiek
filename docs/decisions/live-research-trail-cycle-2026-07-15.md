# Live research trail — cycle decision

## Decision

Keep `roles.cascade_planner.PlanTree` as Antiek's only cascade-plan model. A successful launch writes an immutable approved-tree receipt plus exact plan-local and graph-node leaf identities to `cascade.launched`. Session status projects that receipt as a read-only HTML research trail and routes controls only to affirmatively live runner handles.

## Why

Before this cycle, approval structure disappeared at launch and direct-route recovery rebuilt only a flat list. Reloading the current graph tree was rejected because later edits could rewrite what an existing session appeared to have launched. PR #2055's caller-supplied advisory tree was also rejected: it duplicates the planner vocabulary, persists nothing, executes nothing, and remains stacked on a closed base.

## Invariants

- `cascade.launched` is a success receipt emitted only after every runner handle exists.
- The receipt pins the exact approved tree/version used for launch; the status API never reloads a mutable replacement.
- Every displayed leaf maps by both plan-local ID and graph question-node ID. Duplicate, missing, malformed, swapped, or incomplete mappings suppress the trail rather than guessing.
- A deterministic relaunch receives a strictly increasing durable generation allocated under an inter-process file lock. Its reservation remains an exclusive durable lease until background completion writes a terminal marker; another worker receives a conflict instead of sharing deterministic child identities. A crash after reservation fails closed and recovery never resurrects the older receipt.
- The generation is copied into every child lifecycle and synthesis-failure event; recovery selects and filters by that number, never wall-clock order, so clock skew and equal timestamps cannot cross-contaminate episodes.
- DeepResearchComplete additionally requires both a new parent completion emitted during the current tail run and a durable synthesis-completion marker for the current launch generation. Prior parent events and artifacts cannot bless a relaunch.
- Launch ownership rejects concurrent work against the same deterministic session IDs. Runner-start failure, receipt-write failure, and a silently dropped telemetry write all cancel and drain accepted work before the error escapes.
- Controls require `control_available === true`; omission and recovered sessions fail closed.
- Structural nodes remain context only. Existing runner commands remain the sole execution authority.

## Verification

- 71 coupled backend/API/orchestration/convergence/runner tests passed, including adversarial clock skew, inter-worker atomic reservation, failed-attempt generation consumption, duplicate-generation rejection, exact receipt verification, concurrent ownership, silently dropped receipts, current-generation parent completion, and generation-isolated synthesis failures.
- 12 DeepResearchWorkspace suites / 67 tests passed.
- Ruff, TypeScript, token lint, type-scale lint, production build, and Storybook build passed.
- HardenX strict: LOW, 0 REAL, 14 repository-wide advisories; corpus certification unavailable because no corpus file exists.
- Strict mypy could not reach the changed scope because existing package-relative import failures and an unrelated arXiv syntax error stop analysis.
- The repository a11y harness reported PASS while every configured story reported a load error; that run is not claimed as accessibility evidence. Component semantic coverage and Storybook build passed, but a trustworthy live axe run remains a harness gap.
- GLM-CC `/ultracode` xhigh was invoked and returned HTTP 429.

## Non-decisions

No new branch/deprioritize/spawn plan semantics, alternate plan status vocabulary, model/provider work, generated imagery, Werner behavior, merge, or deployment.
