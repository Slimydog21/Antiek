# WIRING — consuming the deep_research bridge in the Antiek-bench weekly cycle

Audience: the PR #465 owner of `substrate/antiek_bench/` (frozen; this lane made
zero diffs there). The bridge is PULL-based: `deep_research_eval` registers
nothing and imports nothing from `antiek_bench`. One import + one call from the
weekly cycle is the entire integration.

## What the bridge gives you

`substrate.deep_research_eval.bench_bridge.deep_research_bench_record(run)` —
a pure function from a complete `EvalRun` to a `dict[str, Any]` shaped like the
stored-run records `BenchStore.put_run` already holds (`run_id`, `week_id`,
`suite_version`, `mean_score`, `by_task_class`, plus `by_task="deep_research"`,
`by_axis`, `coverage_hit_rate`, `comparability_key`, `rubric_version`,
`judge_model_id`, `view_format="none"` — v1 has no UI, never claim html).

Fail-closed contract: it **raises `IncompleteRunError`** for a run with any
`NOT_MEASURED` query. Do not catch-and-default; skip recording that week and
surface the failure.

## Exact handoff

File: `substrate/antiek_bench/product_path.py`
Function: `run_offline_dogfood_product(*, week_id, store, ...)` (the weekly
cycle entry that records one run per model and refreshes the leaderboard).

One-line diff sketch (plus its import), placed after the per-model `run_suite`
loop, where `dre_run` is the week's `EvalRun` (produced by
`substrate.deep_research_eval.run_eval` and/or replayed from
`EvalRunJournal.read_all()[-1]`):

```python
from substrate.deep_research_eval import deep_research_bench_record
...
        store.put_run((rec := deep_research_bench_record(dre_run))["run_id"], rec)
```

That single `put_run` makes the deep_research record visible to the same
`BenchStore` surfaces (`list_runs`, leaderboard/week aggregation) as core-suite
runs. If the leaderboard should also display it, no schema change is needed —
`by_task_class` carries the single `"deep_research"` class.

## Comparability guardrails (I-9)

`comparability_key = (dataset_id@version, RUBRIC_VERSION, JUDGE_MODEL_ID)` is
passed through verbatim. Week-over-week comparison belongs to
`substrate.deep_research_eval.compare_runs`, which raises `NotComparableError`
on key mismatch or incomplete runs — do not re-implement comparison over the
bridged dicts.
