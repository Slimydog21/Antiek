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
| `KeyError: 'Z_AI_API_KEY'` or `dispatch: skipped providers` | Secrets file empty or malformed | `sudoedit /etc/antiek/secrets.env`; the three keys routing actually depends on are `Z_AI_API_KEY`, `DEEPSEEK_API_KEY` and `XIAOMI_API_KEY`. Check no stray quotes or whitespace around values |
| `[Errno 98] Address already in use` on port 8001 | A previous uvicorn didn't exit cleanly | `pkill -f uvicorn; systemctl restart antiek` |
| `ModuleNotFoundError: No module named 'X'` | New dependency added to pyproject.toml but lock not synced | merge the lock change, then run `ansible-playbook -i inventory.ini playbooks/deploy_atomic.yml` — it builds a frozen release venv |
| `sqlite3.OperationalError` or DuckDB CatalogException | DB file corrupted, schema migration partial, or another writer present | Check no second uvicorn is running (`ps aux \| grep uvicorn`), then `systemctl restart antiek`. If still broken, restore from backup (`disaster-recovery.md`) |
| `WriteLockTimeout` from `runtime/db_lock.py` | Another process holds the DuckDB write lock | The lock is a sidecar file, not the database. `cat /home/antiek/.antiek/antiek.duckdb.write.lock` names the holder's PID and purpose; `lsof` that same `.write.lock` path to see who is queued behind it. A waiter blocked on the flock has never opened the `.duckdb` file, so `lsof` on the database shows nothing while a writer is plainly stuck. The exception text quotes the right path itself. Almost always a stale uvicorn process. Kill it. |
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

**Fix**: see `secret-rotation.md`, but in short — and mind which key
you paste. Routing is claude-less and OpenRouter-free: every tier in
`substrate/dispatch/config.yaml` resolves to one of three direct
endpoints (z.ai, api.deepseek.com, api.mimo.xiaomi.com).
`OPENROUTER_API_KEY` survives in `secrets.env.j2` only as an optional
bypass key that no tier points at, so setting it makes bootstrap
register the provider and `/health` print the string you were hoping
for while dispatch stays exactly as dead. Set the routed keys instead:

```bash
sudoedit /etc/antiek/secrets.env  # Z_AI_API_KEY, DEEPSEEK_API_KEY, XIAOMI_API_KEY
systemctl restart antiek
curl -s https://api.antiek.ai/health | jq '{registered_providers, providers_ready}'
```

A healthy box answers `providers_ready: true` with `zai`,
`zai_reasoning`, `deepseek` and `xiaomi` in the list (`hermes` rides
along beside them).

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

## TLS or certificate errors reaching `api.antiek.ai`

**Symptom**: an HTTPS request to `api.antiek.ai` returns a cert error,
or hangs.

**Read the topology before you touch anything.** TLS is terminated at
the Cloudflare edge, not on the VM. `api.antiek.ai` is a *proxied*
CNAME to the Cloudflare Tunnel; `cloudflared` carries traffic to Caddy
on loopback `127.0.0.1:443`; and that loopback hop runs with
`noTLSVerify: true` (`templates/cloudflared-config.yml.j2`). Two things
follow. The certificate a client sees is Cloudflare's, so Caddy's own
ACME state cannot produce a public cert error on its own — Caddy's
Let's Encrypt complaints in `journalctl -u caddy` are cosmetic for
client traffic, because the tunnel accepts whatever the origin
presents. And ports 80 and 443 are *deliberately closed* on the VM, so
there is no ACME HTTP-01 challenge on port 80 to protect.

**Diagnose**:
```bash
curl -sv https://api.antiek.ai/health 2>&1 | grep -E 'server:|subject:'
# healthy: `server: cloudflare` with `subject: CN=antiek.ai`
```

**Most common causes**:

1. **The tunnel is not connected** — nothing behind the edge means the
   edge has nothing to serve. On the VM:
   ```bash
   systemctl status cloudflared
   journalctl -u cloudflared -n 100 --no-pager
   cloudflared tunnel info <tunnel-id>   # id is `cloudflared_tunnel_id`, terraform/variables.tf:167
   ```

2. **Someone grey-clouded the record.** That is the incident, never the
   fix. `api.antiek.ai` must stay orange-cloud: grey-clouding it points
   DNS straight at an origin whose 80 and 443 are closed, and the API
   goes dark. `main.tf:104-115` records exactly that hazard — the old
   `api_a`/`api_aaaa` resources were `terraform state rm`'d precisely
   because a `terraform apply` would re-assert a grey-cloud A record at
   a closed port. Beware the superseded `proxied = false` rationale that
   still sits at `main.tf:91-101`, directly above the live
   `proxied = true` resource at `:116-123`. It is a stale comment, not
   the configuration.

3. **UFW has been opened too far** — the expected posture is `22/tcp`
   and nothing else:
   ```bash
   ufw status verbose
   ```
   80 or 443 showing ALLOW is a regression to close (D10 in #3328), not
   a fault to fix. All ingress is the tunnel.

4. **DNS answering something other than Cloudflare**:
   ```bash
   dig api.antiek.ai +short
   # healthy: Cloudflare anycast (104.21.x / 172.67.x / 188.114.x),
   # NOT the VM's IPv4 — the VM's own address here means grey cloud
   ```
   Do not expect `dig api.antiek.ai CNAME +short` to show the tunnel:
   Cloudflare flattens proxied CNAMEs, so it returns nothing even on a
   perfectly healthy record. The tunnel target is visible only in the
   dashboard or via `terraform state show cloudflare_record.api_cname`.

## Investigation times out at phase 1 (or any phase)

**Symptom**: `run_cold_question` returns `FAILED` with reason like
"phase 1 timed out waiting for role delivery".

**Diagnose**:
```bash
curl -fsS -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" \
  https://api.antiek.ai/trajectory/<inv-id> \
  | jq '.events[] | select(.action_type == "dispatch.call")
        | .payload | {target_role, provider, model, latency_ms, finish_reason}'
```

`/trajectory` is operator-authenticated. Without the header it answers
401, and the pipe then dies with `jq: error … Cannot iterate over null`
— which reads like corrupt trajectory data when the real problem is
that you never got a trajectory. `-fsS` turns the 401 into an explicit
curl failure instead of feeding an error object to jq.

Mind the shape while you're in there: `action_type` sits at the top
level of each event, but `latency_ms`, `provider`, `model` and
`target_role` live one level down under `payload`. Selecting those
names off the event itself returns a tidy row of nulls at exit 0.

Look at `latency_ms` on the dispatch.call payload. If it's ≥ the role's
configured timeout, the LLM took longer than the orchestrator allows.

**Known reference points**:
- DeepSeek V4 Pro via OpenRouter, decomposer role producing 8 sub-
  questions with rationale: empirically ~226s on 2026-05-17. Treat that
  as a historical figure — routing no longer goes through OpenRouter at
  all, so today's numbers come off the direct endpoints and are not
  comparable line for line.
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

2. **Backup staging not cleaned up** — staging lives under
   `/var/lib/antiek-backup/`, as `antiek-backup.XXXXXXXX` directories
   (`backup.sh.j2:80` and `:136`). It is not in `/var/tmp`, and cannot
   be: the unit runs `PrivateTmp=true` with
   `ReadWritePaths=/var/lib/antiek-backup /var/log /home/antiek/.antiek`,
   so it is structurally unable to leave anything in the host's
   `/var/tmp`. Looking there reports clean on a box that is genuinely
   failing. Investigate:
   ```bash
   du -sh /var/lib/antiek-backup/
   ls -la /var/lib/antiek-backup/
   cat /var/log/antiek-backup.log
   ```
   Don't hand-remove what you find. `backup.sh.j2:135` already sweeps
   its own root on every run
   (`find "${STAGING_ROOT}" -maxdepth 1 -name 'antiek-backup.*' -mtime +2 -exec rm -rf -- {} +`),
   so a pile-up means the script is dying before its trap. The log is
   the thing to read, not the directory.

3. **systemd journal growing** — journald has a default cap of ~10% of
   disk but can balloon. Check and trim:
   ```bash
   journalctl --disk-usage
   journalctl --vacuum-time=14d  # keep last 14 days
   ```

4. **Caddy access logs** — `/var/log/caddy/access.log` rolls per the
   `Caddyfile.j2` log block (`roll_size 100mb`, `roll_keep 5`,
   `roll_keep_for 720h`). Caddy does that itself; there is no logrotate
   config for Caddy anywhere in `infrastructure/`, so `logrotate -f
   /etc/logrotate.d/caddy` has nothing to act on and errors out. Reach
   for Caddy's own state instead:
   ```bash
   ls -la /var/log/caddy/                        # access.log plus access-<ts>.log.gz rolls
   grep -A4 'output file' /etc/caddy/Caddyfile   # did roll_size/roll_keep survive the last render?
   caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
   ```
   If rolling really has stopped, re-render and reload rather than
   restarting — a restart drops live connections for nothing:
   ```bash
   cd ~/Desktop/Antiek/infrastructure/ansible
   ansible-playbook -i inventory.ini playbooks/deploy_atomic.yml --tags caddy
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
ansible-playbook -i inventory.ini playbooks/deploy_atomic.yml --tags caddy
```

This tag is safe only when the exact gated SHA already has a complete
release and receipt under `/opt/antiek-releases`. The atomic playbook
validates a candidate Caddyfile without changing live routing, cuts the
public release chain first, then atomically activates and reloads the
candidate routes before starting the candidate API. If no complete
release exists for the target SHA, run the normal deploy instead of
trying to apply an edge-only change.

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

Backups are a systemd timer, not cron. `/etc/cron.d/antiek-backup` is
deleted on every ansible run (`deploy.yml:234-238`, `setup.yml:638-642`),
so `cat` on it answers "No such file or directory" on a perfectly
healthy box — don't read that as the fault. (The comment at
`playbooks/backup.yml:8` still says "Cron runs …"; it is stale for the
same reason.)

**Diagnose**:
```bash
ssh root@<vm-ip>
systemctl list-timers antiek-backup.timer --all   # when did it last fire? when next?
systemctl status antiek-backup.timer antiek-backup.service
journalctl -u antiek-backup -n 100 --no-pager     # did the run start, and how did it exit?
tail -100 /var/log/antiek-backup.log              # the script's own output lands here
sudo -u root /usr/local/bin/antiek-backup         # try running it manually
```

The unit sends stdout and stderr to `/var/log/antiek-backup.log`
(`antiek-backup.service.j2`), so the journal carries the unit's
lifecycle and exit status while the log carries the detail. Read both.

**Most common cause**: rclone's R2 token expired or got revoked.
Re-issue per `secret-rotation.md` "Rotating the R2 access token".

## Cloudflare/DNS changes not propagating

**Symptom**: `terraform apply` succeeded, but `dig api.antiek.ai`
returns old values.

**Diagnose**: not the TTL. `api.antiek.ai` is a proxied CNAME at
`ttl = 1` — "automatic", which Cloudflare requires on proxied records
(`main.tf:122`). There is no 300s record in `main.tf`, and on a proxied
record what the world sees is governed at the edge, not by an origin
TTL, so "just wait for the TTL" is waiting on the wrong mechanism.

If `dig` disagrees with Terraform, suspect state drift rather than
caching: run `terraform plan` and read `main.tf:104-115` before any
apply. An apply against the retired `api_a`/`api_aaaa` resources
re-asserts a grey-cloud A record pointing at a closed port and takes
the API down. Your own resolver cache is still worth clearing:
```bash
sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder  # macOS
```

## Out of disk after a Python deps upgrade

**Symptom**: `ansible-playbook deploy_atomic.yml` fails the release-root
headroom guard before building the candidate.

**Cause**: retained immutable releases plus the database snapshot exceed
the playbook's required 12 GB release-root headroom.

**Fix**:
```bash
ssh root@<vm-ip>
sudo -u antiek /opt/antiek/.venv/bin/pip cache purge 2>/dev/null || true
df -h / /opt/antiek-releases
sudo find /opt/antiek-releases -mindepth 1 -maxdepth 1 -type d -printf '%TY-%Tm-%Td %p\n' | sort
```

Do not delete the current or immediately previous release. After freeing
headroom, re-run `deploy_atomic.yml`.

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
curl -fsS -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" \
  https://api.antiek.ai/trajectory/<inv-id> | jq .
```

Keep the header. Without it the route answers 401 and `jq .` cheerfully
pretty-prints the error body at exit 0 — which looks exactly like a
short trajectory that came back fine, and is the worst thing to be
reading at the point in an incident where you've reached for this.

## Known gaps in operational tooling

Mostly deliberate omissions for the current sprint, plus one line that
is no longer a gap at all. Documented here so the next engineer or
agent knows what to expect:

- **No Prometheus / Grafana**. Use `journalctl` for application logs and
  `caddy` access logs for traffic. Adding metrics + dashboards is a
  separate sprint when the substrate has enough traffic to make
  aggregate views meaningful.
- **No alerting**. SSH + `journalctl` is the level of operational
  surveillance this scale warrants. Add PagerDuty / Sentry / etc. when
  the operator actually has on-call rotations.
- **Backend deploy is automatic**, and during an incident that changes
  what you should do. `.github/workflows/deploy_backend.yml` deploys on
  `workflow_run`, after both `CI` and `enforce-declared-bar` report, so
  a merge to main reaches prod without anyone at a keyboard. Check what
  CD is doing before you hand-run `deploy_atomic.yml` —
  `gh run list --workflow=deploy_backend.yml -L 5` — because a manual
  deploy from your Mac racing an in-flight CD run is two writers to one
  prod box.
- **No staging environment**. One production VM. Test changes against
  the local development substrate (`uvicorn ... --port 8001` on Mac)
  before pushing. A second `antiek-staging-fsn1` VM would be 2x cost
  for marginal benefit at this stage.
