# NotDiamond Wave 1 Summary

Branch: `caffen/notdiamond-wave1-main`
Base: `origin/main @ c4d93c11`
Spec: `/Users/slimydog/specs/antiek-notdiamond/`

## Shipped

- SPR-01: added `runtime/notdiamond/` advisory adapter.
  - Optional extra: `antiek[notdiamond]` pins `notdiamond==1.7.0`.
  - SDK import is lazy inside `select_model()`.
  - Missing SDK/key/timeouts/SDK failures map to adapter-owned `NotDiamondError`
    subclasses so callers can fail closed to normal dispatch.
  - `NOTDIAMOND_API_KEY` is documented in env templates/runbook and is resolved
    at first call, never at import.
- SPR-02: added honest additive event schema bump on current main.
  - Current main was `EVENT_SCHEMA_VERSION = 31`; this branch bumps to `32`.
  - `DispatchCallPayload` now has seven defaulted/nullable `nd_*` attribution
    fields.
  - `record_nd_decision()` stages attribution in a `ContextVar` and writes no
    event itself.
  - Both existing `dispatch.call` emitters drain the staged attribution:
    `substrate/dispatch/router.py::_emit_dispatch_call` and
    `runtime/remote_exec/cost.py::record_remote_dispatch`.
  - JSONL/Parquet event-log migration is an explicit no-op because old rows
    validate through schema-on-read defaults.

## Gates

- `PYTHONPATH=/private/tmp/antiek-c288-nd-wave1 uv run --extra dev python -m pytest runtime/notdiamond/test_adapter.py runtime/notdiamond/test_smoke.py tests/substrate/dispatch/test_nd_attribution.py tests/test_dispatch.py::test_dispatch_emits_dispatch_call_event tests/test_dispatch.py::test_fallback_chain_triggers_on_primary_failure tests/test_remote_exec_budget.py::test_dispatch_call_emitted_in_host_local_shape tests/test_worker_identity_event.py::test_event_schema_version_bumped tests/test_codegen.py::test_committed_ts_matches_current_schema -q`
  - Result: `27 passed, 1 skipped`
  - Skip: live ND smoke skipped because `NOTDIAMOND_API_KEY` is unset.
- `PYTHONPATH=/private/tmp/antiek-c288-nd-wave1 uv run --extra dev ruff check runtime/notdiamond substrate/dispatch/nd_attribution.py tests/substrate/dispatch/test_nd_attribution.py substrate/dispatch/router.py runtime/remote_exec/cost.py substrate/schemas/events.py`
  - Result: pass.
- `PYTHONPATH=/private/tmp/antiek-c288-nd-wave1 uv run --extra dev mypy runtime/notdiamond substrate/dispatch/nd_attribution.py tests/substrate/dispatch/test_nd_attribution.py`
  - Result: pass.
- `uv lock`
  - Result: pass, added `notdiamond v1.7.0`.
- `uv run python tools/codegen/emit_types.py`
  - Result: pass, regenerated `apps/reading/src/generated/types.ts`.

## Residual

- Live NotDiamond smoke was not exercised because no `NOTDIAMOND_API_KEY` is
  present in this environment.
- No dispatch integration was added. That remains SPR-03; ND is advisory only.
- No multimedia, Hermes, or Caddy files were touched.
- A standalone mypy invocation including pre-existing `substrate/dispatch/router.py`
  and `runtime/remote_exec/cost.py` still exposes existing import-shim issues in
  those modules. The changed runtime behavior there is covered by the focused
  pytest gates above.

## Rejected Alternatives

- `litellm` would provide provider abstraction and observability with less custom
  adapter code, but it is rule/proxy oriented and would not answer the Wave 1
  measurement question: whether ND recommendations improve dispatch outcomes.
- A separate `nd_decisions` event/table would keep attribution isolated, but it
  would introduce a join and a second write surface. Additive fields on the
  existing `dispatch.call` payload preserve the single per-call event contract.
