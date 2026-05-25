# Substrate / dispatch boundary — vendor SDKs only in `providers/`

**Decision date:** 2026-05-25 (formalized; invariant predates this — CLAUDE.md §16)
**Status:** ✅ Enforced by `tools/lint/boundary_check.py` (CI: ci.yml "Substrate/dispatch boundary check")
**Owner:** the product consolidation (DDIA-execution SPR-03 intent)

## The invariant

The substrate is **vendor-agnostic**. Concrete vendor SDKs — `openai`,
`anthropic`, `daytona`, `browserbase`, `modal`, and the rest — may be imported
**only** inside the adapter layer `substrate/dispatch/providers/`. Every other
module under `substrate/` must reach inference/execution through the dispatch
router's vendor-neutral interface, never a vendor SDK directly.

## Why

- **Swappable dispatch posture (§16).** Dispatch is Hermes-primary; vendors are
  pluggable. If substrate modules imported a vendor SDK directly, swapping or
  adding a provider would ripple through unrelated code.
- **A clean provenance/single-writer core.** The graph, event log, and
  single-writer machinery must not carry vendor coupling — it would entangle
  the moat with a third party's client.
- **One place to audit.** All vendor surface lives in `providers/`, so a
  security/cost/rate-limit review has a single directory to read.

## Enforcement

`tools/lint/boundary_check.py` walks `substrate/**/*.py`, skips
`substrate/dispatch/providers/`, and fails (exit 1, `path:line`) on any
`import`/`from` of a vendor SDK (matched by exact module or dotted prefix, so
`google.generativeai` does not flag the unrelated `google.protobuf`). CI runs it
in the `pytest` job. The consolidated tree passes (zero violations).

## Provenance note

The CI step was introduced by DDIA-execution SPR-03, but the lint script and
this decision record were never landed in the product tree — the step pointed at
a non-existent `tools/lint/boundary_check.py`. Both are created here, implemented
to the stated invariant and verified clean, rather than deleting the gate.

## Reconsider-if

A substrate module has a genuine, unavoidable need to import a vendor SDK
directly (none today) — then add an explicit, commented allowlist entry to the
lint, not a silent exception.
