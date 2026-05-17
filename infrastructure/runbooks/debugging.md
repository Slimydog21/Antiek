# Debugging — Common Failure Modes

A catalogue of failure symptoms you (or a future agent) will see, paired
with the diagnostic command and the resolution. Triage in the order
below; the earliest matching symptom is usually the actual problem.

---

## Service won't start

**Symptom**: `systemctl status antiek` shows `failed` or
`activating (auto-restart)` in a loop.

**Diagnose**:
```bash
journalctl -u antiek -n 200 --no-pager
```

**Common causes**:

| Log content | Cause | Fix |
|---|---|---|
| `KeyError: 'OPENROUTER_API_KEY'` or `dispatch: skipped providers` | Secrets file empty or malformed | `sudoedit /etc/antiek/secrets.env`; check no stray quotes or whitespace around values |
| `[Errno 98] Address already in use` on port 8001 | A previous uvicorn didn't exit cleanly | `pkill -f uvicorn; systemctl restart antiek` |
| `ModuleNotFoundError: No module named 'X'` | New dependency added to pyproject.toml but venv not refreshed | re-run `ansible-playbook -i inventory.ini playbooks/deploy.yml` — it refreshes the editable install |
| `sqlite3.OperationalError` or DuckDB CatalogException | DB file corrupted, schema migration partial, or another writer present | Check no second uvicorn is running (`ps aux \| grep uvicorn`), then `systemctl restart antiek`. If still broken, restore from backup (`disaster-recovery.md`) |
| `WriteLockTimeout` from `runtime/db_lock.py` | Another process holds the DuckDB write lock | `lsof /home/antiek/.antiek/antiek.duckdb` to find the holder. Almost always a stale uvicorn process. Kill it. |
| Stack trace mentioning `pydantic.ValidationError` on Event payload | Schema drift — substrate code expects a different shape than what's on disk | Probably a downgrade after a schema bump. Either redeploy the newer code or restore the matching backup |

## Health check fails with empty `registered_providers`

**Symptom**: `curl https://api.antiek.ai/health` returns
`{"status":"ok",...,"registered_providers":[]}`. Service is structurally
up but no LLM dispatch will work.

**Diagnose**:
```bash
ssh root@<vm-ip> cat /etc/antiek/secrets.env
```

If the file is empty or has commented-out lines only — that's the
problem. The bootstrap module skips providers whose env keys are
unset.

**Fix**: see `secret-rotation.md`, but in short:
```bash
sudoedit /etc/antiek/secrets.env  # paste OPENROUTER_API_KEY=...
systemctl restart antiek
curl https://api.antiek.ai/health  # should now show ["openrouter"]
```

## Caddy returns 502 Bad Gateway

**Symptom**: `curl https://api.antiek.ai/health` returns
`502 Bad Gateway`.

**Diagnose**:
```bash
ssh root@<vm-ip>
systemctl status antiek    # is uvicorn running?
systemctl status caddy     # is caddy running?
curl -v http://localhost:8001/health  # does the origin answer?
```

**Resolutions**:

- uvicorn down → see "Service won't start" above
- uvicorn up but `localhost:8001/health` hangs → check
  `journalctl -u antiek -n 100` for an exception in an async handler
- both up but external 502 → check Caddy logs:
  `journalctl -u caddy -n 100`; look for "dial tcp 127.0.0.1:8001: connect: connection refused" (uvicorn just restarting) or auth/TLS errors

## TLS certificate not provisioning

**Symptom**: First HTTPS request to `api.antiek.ai` returns a cert error,
or hangs.

**Diagnose**:
```bash
ssh root@<vm-ip> journalctl -u caddy -n 200 --no-pager | grep -i "acme\|certificate\|error"
```

**Most common causes**:

1. **Port 80 not reachable** — Caddy uses ACME HTTP-01 challenge, which
   requires inbound port 80. Verify UFW:
   ```bash
   ufw status verbose | grep "80/tcp"
   ```
   Should show `ALLOW`. If not: `ufw allow 80/tcp && ufw reload`.

2. **Cloudflare proxying enabled on `api.antiek.ai`** — the orange cloud
   in the Cloudflare DNS UI intercepts the ACME challenge. Verify the A
   record for `api` is grey-cloud (proxy off). Terraform sets
   `proxied = false`; if someone toggled it manually, switch back via
   the dashboard or re-run `terraform apply`.

3. **Rate-limited by Let's Encrypt** — Let's Encrypt rate-limits 5
   certs per domain per week. If you've been bouncing the cert
   repeatedly, you might be banned for 7 days. Caddy will retry every
   ~30s; just wait, or switch to the staging endpoint by setting
   `acme_ca` in the Caddyfile during dev.

4. **DNS not resolving to this VM** — if the A record points elsewhere,
   the ACME challenge connects to the wrong server. Verify:
   ```bash
   dig api.antiek.ai +short
   # should match the VM's IPv4
   ```

## Investigation times out at phase 1 (or any phase)

**Symptom**: `run_cold_question` returns `FAILED` with reason like
"phase 1 timed out waiting for role delivery".

**Diagnose**:
```bash
curl https://api.antiek.ai/trajectory/<inv-id> | jq '.events[] | select(.action_type == "dispatch.call")'
```

Look at `latency_ms` on the dispatch.call event. If it's ≥ the role's
configured timeout, the LLM took longer than the orchestrator allows.

**Known reference points**:
- DeepSeek V4 Pro via OpenRouter, decomposer role producing 8 sub-
  questions with rationale: empirically ~226s on 2026-05-17.
- DEFAULT_ROLE_TIMEOUT in `orchestration/loop_one/orchestrator.py` is
  set to 600s as of Sprint 10 hotfix. SYNTHESIZER_TIMEOUT is 900s.

**Fix**:
- If the LLM is just slow (latency_ms much higher than usual), the
  provider is degraded — wait, or switch tier in
  `substrate/dispatch/config.yaml`.
- If the LLM consistently exceeds 600s, bump `DEFAULT_ROLE_TIMEOUT`
  (in `orchestration/loop_one/orchestrator.py`) higher, commit, push,
  redeploy.

## Disk full

**Symptom**: `df -h /` shows /home or / at >90%. New writes start
failing (`ENOSPC` in `journalctl`).

**Diagnose**:
```bash
ssh root@<vm-ip>
du -sh /home/antiek/.antiek/*
du -sh /var/log/*
```

Likely culprits (in order of probability):

1. **Event log growing without bound** — `/home/antiek/.antiek/research_events/`
   accumulates `.jsonl` files per investigation. Each is small but they
   add up over months.

   *Lossless fix*: rsync older files to R2 (or your Mac), then delete
   from VM. This breaks trajectory replay for those investigations
   locally — but the data is in R2 backups.

   *Architectural fix (eventually)*: attach a Hetzner Volume for
   `/home/antiek/.antiek/research_events/`. Volumes are network-attached,
   which violates the local-disk preference for the DuckDB file but is
   fine for append-only event logs. Document the change in this runbook
   if you do it.

2. **Backup staging not cleaned up** — `/var/tmp/antiek-backup-*` should
   be deleted by the backup script's trap. If they're piling up, the
   script is crashing before cleanup. Investigate:
   ```bash
   cat /var/log/antiek-backup.log
   ls -la /var/tmp/antiek-backup-*
   rm -rf /var/tmp/antiek-backup-*  # safe to remove
   ```

3. **systemd journal growing** — journald has a default cap of ~10% of
   disk but can balloon. Check and trim:
   ```bash
   journalctl --disk-usage
   journalctl --vacuum-time=14d  # keep last 14 days
   ```

4. **Caddy access logs** — `/var/log/caddy/access.log` rotates per
   `Caddyfile.j2` settings (100MB, keep 5). If rotation isn't happening,
   manually rotate and restart caddy:
   ```bash
   logrotate -f /etc/logrotate.d/caddy
   systemctl restart caddy
   ```

## WebSocket connections dropping

**Symptom**: `/ws/events` connections close after ~30 seconds. Browser
console shows "WebSocket closed before connection was established" or
similar.

**Diagnose**: `journalctl -u caddy | grep -i websocket` — Caddy logs
upgrade requests.

**Cause**: Caddy's WebSocket support is automatic but it inherits the
parent server's `transport http` timeouts. If we're somehow under a
30s timeout, that's the bug. Verify the Caddyfile's `transport http`
block has `read_timeout 900s` and `write_timeout 900s`. If not,
re-render from the template:

```bash
cd ~/Desktop/Antiek/infrastructure/ansible
ansible-playbook -i inventory.ini playbooks/deploy.yml --tags caddy
```

## DuckDB queries are slow

**Symptom**: A `/trajectory/<inv-id>` request takes >5 seconds when it
used to be sub-second.

**Diagnose**: Probably the event log directory has grown enough that
the trajectory reader is doing too many file reads.

```bash
ssh root@<vm-ip>
ls /home/antiek/.antiek/research_events/ | wc -l
du -sh /home/antiek/.antiek/research_events/
```

**Fix**: trajectory reading walks `.jsonl` files; the substrate doesn't
index them. At thousands of investigations this becomes noticeable.
The architectural answer (out of scope for this sprint) is to migrate
trajectory storage to DuckDB Parquet shards keyed on `investigation_id`.
The tactical answer right now is to archive completed investigations'
event files to R2:

```bash
# (To be scripted later — at present, do this carefully by hand.)
```

## Backups not running

**Symptom**: `rclone ls r2:antiek-backups/nightly/` shows old or no
recent backups.

**Diagnose**:
```bash
ssh root@<vm-ip>
cat /etc/cron.d/antiek-backup           # cron entry present?
tail -100 /var/log/antiek-backup.log    # any recent runs?
sudo -u root /usr/local/bin/antiek-backup  # try running it manually
```

**Most common cause**: rclone's R2 token expired or got revoked.
Re-issue per `secret-rotation.md` "Rotating the R2 access token".

## Cloudflare/DNS changes not propagating

**Symptom**: `terraform apply` succeeded, but `dig api.antiek.ai`
returns old values.

**Diagnose**: TTL on the existing record. Records are configured at
300s in `main.tf`. If they were set higher previously, the cached
response will hold for that period. Just wait, or force-clear your
local resolver cache:
```bash
sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder  # macOS
```

## Out of disk after a Python deps upgrade

**Symptom**: `ansible-playbook deploy.yml` fails on the `pip install`
task with disk-full errors.

**Cause**: pip's build cache + the venv together grew. Most common
when a heavy dep (sentence-transformers, torch) was added.

**Fix**:
```bash
ssh root@<vm-ip>
sudo -u antiek /opt/antiek/.venv/bin/pip cache purge
sudo -u antiek rm -rf /tmp/pip-*
df -h /
```

Then re-run `deploy.yml`.

---

## When in doubt

Three commands that surface 80% of what's wrong:

```bash
ssh root@<vm-ip> systemctl status antiek caddy
ssh root@<vm-ip> journalctl -u antiek -n 50 --no-pager
curl -v https://api.antiek.ai/health
```

If those three don't tell you the problem, the trajectory itself
usually does:
```bash
curl https://api.antiek.ai/trajectory/<inv-id> | jq .
```

## Known gaps in operational tooling

These are deliberate omissions for the current sprint. Documented here
so the next engineer or agent knows what to expect:

- **No Prometheus / Grafana**. Use `journalctl` for application logs and
  `caddy` access logs for traffic. Adding metrics + dashboards is a
  separate sprint when the substrate has enough traffic to make
  aggregate views meaningful.
- **No alerting**. SSH + `journalctl` is the level of operational
  surveillance this scale warrants. Add PagerDuty / Sentry / etc. when
  the operator actually has on-call rotations.
- **No CI/CD pipeline**. Manual `ansible-playbook deploy.yml` from the
  operator's Mac. Adding GitHub Actions or similar is correct when
  there are multiple committers; right now it's just the operator.
- **No staging environment**. One production VM. Test changes against
  the local development substrate (`uvicorn ... --port 8001` on Mac)
  before pushing. A second `antiek-staging-fsn1` VM would be 2x cost
  for marginal benefit at this stage.
