# ASR SR-09 P4: arXiv OAI sync systemd operator surface

**Date:** 2026-06-30  
**Sprint:** SR-09 (P4 OAI daemon / operator wiring)  
**Depends on:** arXiv OAI sync code path + host-global arXiv governor

## Decision

The arXiv OAI-PMH metadata sync is now a first-class production timer:

- `antiek-arxiv-oai-sync.service` runs
  `python -m tools.arxiv_oai_sync incremental --census-json ...`.
- `antiek-arxiv-oai-sync.timer` fires daily at 04:20 UTC with
  `Persistent=true` and jitter.
- `setup.yml` and `deploy.yml` both render the service and timer; deploy also
  starts/restarts the timer so a code deploy cannot strand the operator surface.

The service uses the live Antiek venv, `/etc/antiek/secrets.env`, and the same
state root as the substrate. It pins:

- `ANTIEK_DUCKDB_PATH={{ antiek_state_dir }}/antiek.duckdb`
- `ANTIEK_ARXIV_OAI_SYNC_PATH={{ antiek_state_dir }}/arxiv_oai_sync.json`
- `ANTIEK_ARXIV_OAI_STATE_PATH={{ antiek_state_dir }}/arxiv_oai_harvest.json`
- `ANTIEK_ARXIV_THROTTLE_PATH={{ antiek_state_dir }}/arxiv_throttle.json`
- `ANTIEK_ARXIV_GOVERNOR_LOCK_PATH={{ antiek_state_dir }}/arxiv_governor.lock`

## Invariants preserved

- Live arXiv HTTP sends still go through the host-global arXiv governor flock,
  so OAI, PDF, and search jobs share the same spacing and ban sentinel.
- DuckDB writes still go through `runtime.db_lock.connect_write`; the sync
  service is not a second uncoordinated writer.
- The timer writes only under `{{ antiek_state_dir }}` plus `/tmp`/`/var/tmp`
  and keeps the same systemd hardening posture as the substrate services.
- `ConditionPathExists={{ antiek_state_dir }}/antiek.duckdb` makes first
  provision safe: `setup.yml` may start the timer before the operator starts
  `antiek.service`, but the sync oneshot skips until the live DB exists.
- `MemoryDenyWriteExecute=true` intentionally matches the existing Python
  systemd units (`antiek.service` and `antiek-continuous-research.service`).

## Verification

```bash
uv run --extra dev pytest tests/test_arxiv_oai_sync.py tests/test_arxiv_oai_systemd.py -q
ansible-playbook --syntax-check infrastructure/ansible/playbooks/setup.yml
ansible-playbook --syntax-check infrastructure/ansible/playbooks/deploy.yml
uv run --extra dev pytest tests/test_rate_governor.py::test_oai_harvest_send_is_inside_the_host_global_governor_flock tests/test_rate_governor.py::test_pdf_fetch_send_is_inside_the_host_global_governor_flock tests/test_rate_governor.py::test_client_search_send_is_inside_the_host_global_governor_flock -q
```
