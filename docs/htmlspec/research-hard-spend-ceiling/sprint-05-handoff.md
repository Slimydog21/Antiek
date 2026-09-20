# ANT-RHC SPR-05 handoff

**Status:** implemented and locally verified

**Base:** `origin/main@459afb58164c8d0dcfa8cc0ce06ec53f60c2501b`

**Checked:** 2026-07-13

## Result

No evaluated provider qualifies for paid research hard-ceiling mode. Exa Agent,
Tavily Research, Perplexity Agent, and OpenAI Responses all expose useful
pricing, provider-generated operation identity, or final usage evidence. None
documents the complete pair Antiek needs after an ambiguous create: a
provider-enforced caller idempotency key and authoritative lookup by that same
key returning exact billed cost or authoritative not-found.

The implementation keeps every route available under stop-limit semantics and
adds a closed qualification registry. Server catalog construction now rejects
any paid route that claims durable idempotency, authoritative reconciliation,
and disabled hidden retries unless the exact provider/model/operation record has
all five evidence dimensions passing and a `qualified` verdict.

## Decisive trace

Antiek reserves and marks dispatch possible; the provider accepts and may bill
the POST; the response carrying the provider ID is lost. Recovery has only
Antiek's deterministic key, while provider retrieval requires the unknown
provider ID. Retrying may double-charge and releasing may hide the original
charge. Callbacks, metadata, aggregate usage, and per-operation API keys do not
atomically close that identity gap.

## Evidence and review

- Primary contracts and reversal conditions are recorded in
  `docs/decisions/research-hard-ceiling-provider-qualification.md` and the
  machine-readable registry.
- A grounded Codex architecture critic tried the strongest callback/metadata
  refutation and upheld refusal.
- MiMo's independent run produced no usable result and was terminated; it is not
  counted as evidence.
- Final Codex diff review found no defects and verified the registry ships in the
  built wheel.
- `hardenx . --strict`: LOW, zero real findings, 14 unrelated advisories.

## Verification

- `.venv/bin/python -m pytest -q tests/test_research_provider_qualification.py tests/test_research_cost_projection.py`: 36 passed.
- `.venv/bin/python -m pytest -q tests/test_research_provider_gateway.py tests/test_cascade_api.py -k 'hard_ceiling or provider or projection'`: 18 passed, 32 deselected.
- Codex review reran a combined slice: 54 passed, 32 deselected.
- `.venv/bin/ruff check runtime/research_runner/provider_qualification.py runtime/research_runner/cost_projection.py tests/test_research_provider_qualification.py tests/test_research_cost_projection.py`: passed.
- `.venv/bin/mypy --follow-imports=skip runtime/research_runner/provider_qualification.py`: passed.
- `python -m json.tool runtime/research_runner/provider_qualification.json`: passed.
- `uv build --wheel`: passed; wheel includes both research-runner JSON registries.
- `git diff --check`: passed.

The clean worktree initially lacked the `dev` optional dependencies. Running
the system `uv run pytest` command then resolved an unrelated installed
`runtime` package; `uv sync --extra dev` followed by the repository interpreter
restored the expected environment. This was an environment setup issue, not a
product failure.

## Reversal procedure

Refresh official create, retrieve, billing, pricing, and retry contracts. A
route may change to `qualified` only when every dimension passes for its exact
provider/model/operation. Then pin the server pricing snapshot and expiry,
implement a one-send adapter with hidden retries disabled, and fault-inject an
accepted create whose response is lost. Recovery must settle or release from
provider evidence keyed by Antiek's persisted idempotency key before hard mode
can expose that route.
