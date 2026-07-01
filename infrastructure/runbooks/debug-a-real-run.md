# Debug a Real Run — reconstruct Loop-1 from its event log

**Audience**: the operator. You are reading a trajectory that already exists;
you launch nothing. The real run is the operator's go-live call.

**Time**: ~5 minutes against the fixture trajectories; longer only when the
real event log is large.

Every command below runs against `tests/fixtures/trajectories`, so rehearse the
procedure before touching a real Loop-1 run. For a real run, keep the same
commands and swap only the event directory / investigation id.

---

## Steps

### 1. Which phase was slow?

Start with phase latency. For one investigation, the slowest completed
`phase.exit` rows print first.

```bash
python tools/eventlog_query.py which-phase-slowest --events-dir tests/fixtures/trajectories --investigation-id healthy
```

Expect `Final synthesis` (phase 6) at the top for the healthy fixture. To see
the same question across every trajectory in the directory:

```bash
python tools/eventlog_query.py which-phase-slowest --events-dir tests/fixtures/trajectories
```

Use JSON when you need to paste the result into a handoff without table
wrapping.

```bash
python tools/eventlog_query.py which-phase-slowest --events-dir tests/fixtures/trajectories --investigation-id healthy --json
```

### 2. Where did it stall, or did it finish?

Next, decide whether the run completed, failed, or entered a phase without
leaving it.

```bash
python tools/eventlog_query.py where-did-it-stall --events-dir tests/fixtures/trajectories --investigation-id healthy
```

For `healthy`, expect `status` = `completed`; the stall columns are `-`.

### 3. Did a provider fail?

Provider failures are counted from `dispatch.call` errors and paired
`role.call.failed` rows. Run this before blaming retrieval or synthesis code.

```bash
python tools/eventlog_query.py which-provider-fails --events-dir tests/fixtures/trajectories --investigation-id provider_error
```

For `provider_error`, expect `openai` / `gpt-4.1-mini` with `error_rate` = `1`.

### 4. Localize the cause

Run the bisector on the same event log. It does not guess beyond the observed
rows; it returns `DATA`, `CODE`, `DISPATCH`, or `INCONCLUSIVE`.

```bash
python tools/eventlog_bisect.py --events-dir tests/fixtures/trajectories --investigation-id provider_error
```

Use JSON for machine-readable handoff evidence.

```bash
python tools/eventlog_bisect.py --events-dir tests/fixtures/trajectories --investigation-id provider_error --json
```

### 5. Pull the run and its fan-out children by one key

On SPR-04+ logs, scope any query to the root run's correlation id. That pulls
the run and its fan-out children by one key. These fixtures are older and do
not carry `correlation_id`, so this rehearsal command exits cleanly and warns
that no rows matched.

```bash
python tools/eventlog_query.py which-phase-slowest --correlation-id fixture-root --events-dir tests/fixtures/trajectories
```

Keep the observability surface vendor-free before merge.

```bash
python tools/lint/o11y_vendor_check.py
```

---

## Worked example

Run the bisector across the three bad trajectories and the healthy control.

```bash
python tools/eventlog_bisect.py --events-dir tests/fixtures/trajectories --investigation-id empty_retrieval
```

Expected verdict: `CAUSE: DATA` because retrieval returned 0 chunks.

```bash
python tools/eventlog_bisect.py --events-dir tests/fixtures/trajectories --investigation-id provider_error
```

Expected verdict: `CAUSE: DISPATCH`; the evidence names
`openai/gpt-4.1-mini`.

```bash
python tools/eventlog_bisect.py --events-dir tests/fixtures/trajectories --investigation-id code_bug
```

Expected verdict: `CAUSE: CODE` because retrieval and dispatch succeeded, but
synthesis delivered empty output.

```bash
python tools/eventlog_bisect.py --events-dir tests/fixtures/trajectories --investigation-id healthy
```

Expected verdict: `CAUSE: INCONCLUSIVE`; there is nothing to localize.

## What this procedure does NOT do

- It does not launch Loop-1, replay the run, or mutate the substrate. It reads
  an event log that already exists.
- It does not add a metrics store, daemon, dashboard, or hosted UI. The surface
  is this runbook plus terminal commands.
- It does not change event schema or regenerate code. If a row is missing, the
  tool reports that absence instead of inventing evidence.

## §16 never do

Never add a monitoring vendor to make this easier. Prometheus, Grafana,
Datadog, Sentry, and OpenTelemetry are forbidden here. The
`python tools/lint/o11y_vendor_check.py` lint enforces their absence in CI.
