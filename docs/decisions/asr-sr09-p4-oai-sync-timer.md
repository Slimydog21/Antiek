# ASR SR-09 P4: arXiv OAI sync timer

**Date:** 2026-06-30
**Sprint:** SR-09 P4
**Status:** partial — local systemd artifact landed; live enablement/run remains operator proof.

## Decision

The arXiv OAI-PMH sync runs as a systemd timer over the existing
`tools.arxiv_oai_sync incremental` CLI. The service is `Type=oneshot`; systemd
owns the daily schedule while the Python driver owns the across-run high-water
mark and the harvester owns mid-run crash resume.

The unit pins all arXiv state under `{{ antiek_state_dir }}`:

| state | path |
|-------|------|
| DuckDB | `{{ antiek_state_dir }}/antiek.duckdb` |
| throttle | `{{ antiek_state_dir }}/arxiv_throttle.json` |
| governor flock | `{{ antiek_state_dir }}/arxiv_throttle.json.governor.lock` |
| OAI mid-harvest cursor | `{{ antiek_state_dir }}/arxiv_oai_harvest.json` |
| sync high-water mark | `{{ antiek_state_dir }}/arxiv_oai_sync.json` |
| run census | `{{ antiek_state_dir }}/reports/arxiv_oai_census.json` |
| source-value census | `{{ antiek_state_dir }}/reports/source_census.json` |

## Why this shape

P4 is not a second daemon. A long-running process would duplicate state and
restart behavior that the sync driver already handles. A timer also keeps the
arXiv shared-flock invariant mechanical: the OAI harvester still routes its send
through the host-global governor, and every run uses the same throttle state and
lock path as other arXiv jobs on the box.

After a successful OAI sync, the service emits the SR-10 source-value census from
the same live DuckDB via `python -m tools.source_census --source arxiv`. That
keeps the corpus-value gate artifact coupled to the corpus update that produced
it, while still leaving first production evidence and threshold calibration to
the operator.

## Verification

```bash
python -m pytest tests/test_arxiv_oai_sync_systemd.py -q
python -m pytest tests/test_arxiv_oai_sync.py -q
python -m pytest tests/test_rate_governor.py::test_oai_harvest_send_is_inside_the_host_global_governor_flock -q
python tools/lint/rate_governor_check.py
python tools/lint/source_gate.py
```

## Remaining operator proof

Deploy must render and start `antiek-arxiv-oai-sync.timer`, then the operator
must capture the first production run evidence: `systemctl status
antiek-arxiv-oai-sync.timer`, `journalctl -u antiek-arxiv-oai-sync.service`, and
the emitted `{{ antiek_state_dir }}/reports/arxiv_oai_census.json` plus
`{{ antiek_state_dir }}/reports/source_census.json`.
