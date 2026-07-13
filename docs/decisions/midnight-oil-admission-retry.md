# Midnight Oil graph-admission retry

**Status:** executing offline; no live provider or production smoke
**Date:** 2026-07-13
**Authority:** the authenticated job owner explicitly initiates each retry

## Decision

Expose `POST /midnight-oil/jobs/{job_id}/graph-admission/retry` as an empty-body,
projection-only recovery action. The route authorizes ownership before reading
detail state and accepts only a terminal operation/job whose graph state is
`pending` with one of the three closed transient reasons:

- `internal_local_chunk_temporarily_missing`
- `operational_artifact_pending`
- `graph_lock_unavailable`

The action reuses `resume_terminal_projection`. It cannot accept a model,
budget, source, policy, or dispatch override. It performs no retrieval, provider
dispatch, worker lease, budget hold, or new research. A completed/refused result
returns the canonical job response with HTTP 200; a still-transient result
returns the same response with HTTP 202. Invalid authority/state fails before
the projection seam.

## Status-code contract

- `200`: retry was processed and graph state is now terminal.
- `202`: retry was processed but the graph state remains transient/pending.
- `404`: the authenticated owner cannot resolve the job.
- `409`: the job is not safely retryable or now requires reconciliation.
- `503`: graph recovery composition or durable recovery is unavailable.

All responses are `Cache-Control: no-store`.

## Rejected

- Automatic polling/retry: no durable attempt limit or backoff policy exists.
- Reusing the run/deposit endpoint: its broader authority obscures the
  projection-only/no-spend proof.
- Retrying deterministic refusals: repetition cannot repair legacy authority,
  missing evidence coverage, forged receipts, external-only evidence, policy
  drift, or deterministic row conflicts.

## Reconsider if

Automatic retry may be specified only after operational evidence shows repeated
transient failures and a separate contract defines durable attempt limits,
backoff, cancellation, observability, and operator controls.
