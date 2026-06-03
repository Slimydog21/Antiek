# Reachability probe gate

**The fifth done-bar.** A feature is not "done" because a brick passes — a
unit test, a contract test, a mocked harness. It is done when it is
**reachable from the real product**: the app boots the way prod boots, you
drive the feature through its real route, and an **observable outcome**
holds.

This gate exists because Antiek's flagship compounding flywheel shipped
**dead in prod** and every gate in the build passed. The single launch
entrypoint (`interfaces/research/api/cascade_routes.py:367`) builds
`HostLocalRunner(...)` with `retrieval_substrate` left at its default
`None`; the reuse hook (`runtime/research_runner/host_local.py:259`)
early-returns on `None`; so no `knowledge.reused` event fires and `/health`
reports `knowledge_reuse_count=0`. The compounding *benchmark* passes CI
only because its harness (`compounding/benchmark/harness.py:344`) **injects**
the substrate prod never injects. Every gate verified a brick; nothing
verified the feature was reachable from the factory. This gate does.

---

## The fifth done-bar criterion (for a caffenagent orchestrator)

> **≥ 1 reachability proof for each feature the sprint declares
> reachable-from-prod.** Zero is allowed only for explicitly internal-only
> work (a lint, a migration, a refactor that ships no user-facing route),
> and only with a one-line written justification in the sprint handoff.
> A reachability proof is a probe under `tools/reachability/probes/` that
> boots via the production `create_app()` factory, drives the feature's real
> route(s), and asserts an observable outcome — registered so
> `python -m tools.reachability.probe_runner` runs it.

A sprint that declares "X is now reachable from prod" without a green (or
known-red-with-expiry) probe for X has not met the bar, regardless of how
many unit tests pass.

---

## The probe descriptor contract

A probe lives in its own module under `tools/reachability/probes/` and
exposes a single module-level `PROBE`:

```python
from tools.reachability.probe_runner import Probe, ProbeResult

def _probe() -> ProbeResult:
    from interfaces.research.api.app import create_app   # the PROD factory
    from fastapi.testclient import TestClient
    app = create_app()                                   # bare — see the rule
    client = TestClient(app)
    r = client.post("/your/real/route", json={...})      # drive the feature
    if r.status_code == 404:
        return ProbeResult(ok=False, reason="route 404", failure_mode="route_404")
    outcome = _read_observable_outcome(...)              # /health or event log
    if outcome_holds:
        return ProbeResult(ok=True)
    return ProbeResult(ok=False, reason="<why>", failure_mode="feature_dead")

PROBE = Probe(id="your_feature", feature="your feature (human name)", run=_probe)
```

Fields:

| field        | meaning |
|--------------|---------|
| `id`         | the `--only` selector **and** the `known_red.json` key. Stable. |
| `feature`    | human name printed in `[REACHABLE]` / `[BLOCKED]`. |
| `run`        | zero-arg callable returning a `ProbeResult`; boots via `create_app()`. |
| `timeout_s`  | per-probe wall-clock ceiling (default `DEFAULT_PROBE_TIMEOUT_S` = 30 s). |

`ProbeResult.failure_mode` is one of: `reachable`, `feature_dead`,
`boot_fail`, `route_404`, `timeout`, `error` — so a BLOCKED probe is never
ambiguous between "the app could not boot" and "the feature is dead."

**Isolate your writes.** Set `ANTIEK_DUCKDB_PATH` and
`ANTIEK_RESEARCH_EVENTS_DIR` to per-PID temp paths inside the probe (and
restore them in a `finally`) so the probe never touches the live shared
DuckDB held under the `--workers 1` single-writer lock, and reads a clean
event log it alone wrote. **Assert on a per-investigation signal** (the
event log for the investigation you launched), not a process-global counter
that other runs mutate — a global counter makes the assertion flaky. See
`probes/flywheel.py` for the worked example.

## The rule: boot via the real factory

> **A probe MUST boot via `create_app()` the production way: no
> `retrieval_substrate=`, no `register_providers=False`, no stubbed
> providers, no pre-wired dependency prod does not wire.**

### The fixture-injection anti-pattern (named, so it is forbidden)

The reason the dead flywheel passed CI is that the compounding benchmark
constructs the runner with the dependency injected:

```python
# compounding/benchmark/harness.py:344  — THE ANTI-PATTERN. DO NOT COPY.
runner = HostLocalRunner(
    loop_fn=...,
    events_dir=events_dir,
    retrieval_substrate=reuse_substrate,   # <-- prod NEVER passes this
)
```

That harness is a fine *brick* test of the reuse machinery, but it can
**never** catch a wire that is missing at the prod call site, because it
supplies the wire itself. A reachability probe that injected
`retrieval_substrate` (or stubbed a provider, or constructed
`HostLocalRunner` directly instead of going through the launch route) would
recreate the exact blind spot — it would go green on the dead flywheel.
So injection is forbidden here. The probe drives the **route**; the route
builds the runner the way prod builds it.

## The known-red escape valve (with a hard expiry)

A probe can be **intentionally red during a fix window** — e.g. SPR-01 ships
the flywheel probe RED on purpose, before SPR-02 wires the flywheel, so
SPR-02's fix is verified by a probe that is demonstrably red today. To merge
SPR-01 without faking green **and** without the red being ignored forever,
list the probe in `known_red.json`:

```json
{
  "probes": [
    {
      "probe_id": "flywheel",
      "until_issue_link": "<tracking link>",
      "until_date": "2026-07-03"
    }
  ]
}
```

While the entry is unexpired, the runner reports the probe's RED as
`[BLOCKED (known-red, expires …)]` but **exits 0** (does not fail the
build). When the fix lands, **delete the entry** (the probe goes green on
its own). If the entry **expires** before the fix lands, the valve
**self-closes**: the runner reds the build and prints an explicit
`known-red window EXPIRED` line, forcing an explicit decision — extend the
date with a fresh justification, or land the fix. A malformed `until_date`
is treated as expired (fail-closed). Every entry **must** carry both a
tracking link and a hard expiry; an entry with neither is the silent-permanent
valve this design forbids.

## How a sprint registers a probe

1. Add `tools/reachability/probes/<feature>.py` exposing a `PROBE`.
2. Run `python -m tools.reachability.probe_runner --only <feature>` and make
   it green (or list it in `known_red.json` with a linked expiry if it is
   intentionally red during a fix window).
3. The `reachability` CI job (`.github/workflows/ci.yml`) runs the full set
   on every PR and main push; it is BLOCKING.

## Commands

```sh
python -m tools.reachability.probe_runner            # run all probes (blocking)
python -m tools.reachability.probe_runner --only flywheel
python -m tools.reachability.probe_runner --list     # ids + features
python -m pytest tests/test_reachability_runner.py -q # the runner's self-test
```

## Relationship to the other "reachability" gate

`tools/lint/reachability_gate.py` (in the `pytest` job) is a **static**
zero-importer / no-inbound-link lint: it reds when a module nothing imports
or a route nothing links to is added ("shipped into purgatory"). This gate
is **dynamic and outcome-asserting**: it boots the app and checks the
feature actually works end-to-end. They are complementary — static catches
"nothing can reach this code"; this catches "the code runs but the feature
is dead at the entrypoint."

See `docs/decisions/reachability-gate.md` for why this gate is blocking +
pre-merge + outcome-asserting (every weaker form already failed here).
