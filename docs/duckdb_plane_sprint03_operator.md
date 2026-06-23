# DuckDB plane — Sprint 03 operator runbook

**Spec:** `specs/antiek-duckdb-plane/sprint-03-analytics-prod.html`  
**Cycle:** caffenagent exec-2 closure for prod analytics plane.

## Preconditions

- Code with `scripts/run_analytics_plane.sh`, `export_*`, `rebuild_analytics_duckdb.py` deployed to `/opt/antiek` on the Hetzner VM (`infrastructure/SKILL.md`).
- `~/.antiek/antiek.duckdb` on **local NVMe** (Stage 0 prod default).
- Ansible inventory reachable (`infrastructure/ansible/inventory.ini`).

## 1. Install cron (if not yet on VM)

From operator machine with vault/SSH:

```bash
cd infrastructure/ansible
ansible-playbook -i inventory.ini playbooks/setup.yml --tags analytics
```

Expect: `/usr/local/bin/antiek-analytics-plane`, cron file `antiek-analytics`, log `>> /var/log/antiek-analytics.log`.

Vars: `group_vars/all.yml` — Sunday 04:00 UTC (`analytics_cron_*`).

## 2. Manual plane run (proof)

On VM as root or via ansible ad-hoc:

```bash
sudo /usr/local/bin/antiek-analytics-plane
```

Or from repo on VM:

```bash
sudo -u antiek env ANTIEK_DUCKDB_PATH=/home/antiek/.antiek/antiek.duckdb \
  /opt/antiek/scripts/run_analytics_plane.sh
```

**Pass:** dated dir under `~/.antiek/exports/parquet/YYYYMMDD/manifest.json` with `antiek_param_version` + `table_layers`; `~/.antiek/analytics.duckdb` mtime fresh.

## 3. View smoke (readonly)

```bash
sudo -u antiek duckdb -readonly /home/antiek/.antiek/analytics.duckdb \
  -c "SELECT * FROM v_engine_dispatch_by_workflow LIMIT 5;"
```

Empty result set is OK; **error** is not.

## 4. Operator proof (close sprint)

Append one line to `docs/OPERATOR_ACTIONS.md` **OA-DUCKDB-ANALYTICS-PLANE** with:

- UTC timestamp
- export path used
- one sentence: what decision the query informed (even “idle — zero dispatch rows”)

## Live health (2026-06-23)

`curl https://api.antiek.ai/health` → `status: ok`, `build_sha` **does not** include local DuckDB plane commits until deploy (Sprint 06).