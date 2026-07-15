# Antiek Infrastructure — Agent Skill

You are reading the operational manual for the Antiek substrate's
production deployment. After this file plus `runbooks/SKILL.md`, you
should be able to operate the infrastructure without further context-
gathering.

## Topology

```
                                ┌─ Cloudflare DNS ──┐
                                │  api.antiek.ai   │
                                │  app.antiek.ai   │
                                └────────┬─────────┘
                                         │ A/AAAA (grey cloud, direct)
                                         ▼
                          ┌──────────────────────────────┐
                          │   Hetzner CCX23 VM           │
                          │   Falkenstein (fsn1-dc14)    │
                          │                              │
   ┌───────────────┐      │  ┌────────────────────────┐  │
   │  Client       │──────┼─▶│  Caddy (:443, :80)    │  │
   │ (browser, CLI,│  TLS │  │  - Let's Encrypt cert │  │
   │  ssh, curl)   │      │  │  - 900s timeouts      │  │
   └───────────────┘      │  └───────────┬────────────┘  │
                          │              │ reverse_proxy │
                          │              ▼               │
                          │  ┌────────────────────────┐  │
                          │  │  uvicorn (:8001)      │  │
                          │  │  --workers 1 (!)      │  │
                          │  │  systemd: antiek      │  │
                          │  └───────────┬────────────┘  │
                          │              │ embedded      │
                          │              ▼               │
                          │  ┌────────────────────────┐  │
                          │  │ DuckDB                 │  │
                          │  │ ~/.antiek/antiek.duckdb│  │
                          │  │ + event log (.jsonl)  │  │
                          │  │ on LOCAL NVMe         │  │
                          │  └────────────────────────┘  │
                          └────────────┬─────────────────┘
                                       │ nightly 03:00 UTC
                                       │ rclone S3 (R2)
                                       ▼
                          ┌──────────────────────────────┐
                          │ Cloudflare R2                │
                          │ antiek-backups (EU region)   │
                          │ .tar.gz, R2 lifecycle policy │
                          └──────────────────────────────┘
```

External constants:
- **Domain registrar**: Porkbun (mostly static, holds the WHOIS).
- **DNS**: Cloudflare (nameservers `drew.ns.cloudflare.com` +
  `maeve.ns.cloudflare.com`).
- **LLM dispatch**: claude-less — GLM-5.2 (z.ai direct) primary on every
  tier, DeepSeek V4 Pro + Xiaomi MiMo V2.5 Pro cross-family fallbacks
  (each its own direct API).

## Where state lives — ranked

1. **The repository** (`Antiek/infrastructure/`) — source of truth.
   Terraform `.tf` files, Ansible playbooks, runbooks. Edit here, then
   apply.

2. **The VM filesystem**:
   - `/opt/antiek/` — substrate code (git working tree).
   - `/home/antiek/.antiek/` — runtime state (DuckDB, event log,
     knowledge skills, per-investigation research dirs).
   - `/etc/antiek/secrets.env` — runtime secrets (`Z_AI_API_KEY`,
     `DEEPSEEK_API_KEY`, `XIAOMI_API_KEY`, ...), root:antiek 0640.
   - `/etc/systemd/system/antiek.service` — rendered from
     `ansible/templates/antiek.service.j2`. Do not edit on the VM.
   - `/etc/caddy/Caddyfile` — rendered from `ansible/templates/Caddyfile.j2`.
   - `/usr/local/bin/antiek-backup` — rendered from `backup.sh.j2`.
   - `/etc/cron.d/antiek-backup` — nightly cron.

3. **Provider dashboards** (Hetzner, Cloudflare) — reflect state but
   should NEVER be edited directly. Editing here creates drift; the
   next `terraform apply` reverts it. The one exception is generating
   R2 API tokens (Terraform doesn't have a resource for those —
   it's a known provider gap).

## Common operations

| Task | Command summary | Runbook |
|---|---|---|
| Ship a code change | `cd ansible && ansible-playbook -i inventory.ini playbooks/deploy.yml` | `runbooks/code-update.md` |
| Rotate a dispatch key (z.ai/DeepSeek/MiMo) | `sudoedit /etc/antiek/secrets.env && systemctl restart antiek` | `runbooks/secret-rotation.md` |
| Trigger a backup manually | `cd ansible && ansible-playbook -i inventory.ini playbooks/backup.yml` | (in `runbooks/disaster-recovery.md`) |
| Restore from backup | (multi-step — see runbook) | `runbooks/disaster-recovery.md` |
| Check service health | `curl https://api.antiek.ai/health` | (in `runbooks/debugging.md`) |
| View live logs | `ssh root@<vm-ip> journalctl -u antiek -f` | (in `runbooks/debugging.md`) |
| Provision a new VM (rare) | `cd terraform && terraform apply` then setup.yml | `runbooks/first-deploy.md` |

## Constraints that look weird

These are non-negotiable architectural commitments from the substrate
layer. An agent unfamiliar with them will propose "obvious" changes
that silently break things. Read once, internalise.

### `--workers 1` in the systemd unit

The Antiek substrate uses DuckDB as its primary store. **DuckDB is an
embedded single-writer database** — two processes opening the file
for write will corrupt it (typically within the first concurrent
write). `runtime/db_lock.py` enforces this via flock and a second
writer will refuse to start, but the symptom (mysterious "lock
acquire failed" errors at boot) is much harder to diagnose than just
respecting the constraint.

If load ever genuinely exceeds what one `uvicorn --workers 1` on a
CCX23 can handle, the correct architectural move is migrating DuckDB
→ Postgres (and externalising the typed event log to S3/R2). That's
a sprint of work, not a config flag. Do not propose `--workers 4`.

### Caddy, not nginx

Caddy's defaults are sane for long-running LLM calls (it doesn't have
the 60s timeout nginx ships with). Its config is one file. Its
automatic Let's Encrypt eliminates a whole class of TLS-renewal
operational burden. We use it.

The Caddyfile sets `read_timeout 900s` and `write_timeout 900s`
explicitly anyway — partly for documentation, partly because
synthesizer calls to GLM-5.2 (thinking on) routinely take 20-30s
end-to-end and sometimes longer. The 900s ceiling matches the
orchestrator's `SYNTHESIZER_TIMEOUT`.

### No load balancer, no second backend

The substrate's `InvestigationCoordinator` (in
`orchestration/loop_one/coordinator.py`) holds per-investigation
asyncio futures in-process. Splitting across processes breaks the
coordinator — the bridge handler emits a `*.delivered` event in
process A, but the orchestrator is `await`ing the future in process
B, so the wait_for never resolves.

Solving this properly requires a message bus (Redis pub/sub or NATS
or similar) and refactoring the coordinator to subscribe rather than
hold futures directly. That's Sprint 11+ work. For now: one VM, one
process, one coordinator.

### Local NVMe, not network volume

The DuckDB file MUST be on local disk. Network-attached storage
(Hetzner Volumes, EBS, etc.) introduces latency that the substrate's
synchronous DuckDB writes can't absorb — a 5ms network round-trip per
write is fine for one write but cripples a tight write loop. Also,
network volumes can disappear (provider outage) leaving the substrate
running but unable to persist; better to have the whole VM go than to
have a phantom-write scenario.

The event log (`.jsonl` files) and knowledge-skills directory ARE
candidates for migration to a network volume if disk space becomes
the binding constraint. Document the trade in `runbooks/debugging.md`
"Disk full" if you do it.

### Single-writer, but the orchestrator + roles + bridges all run in
that single process

The substrate's design is "one Python event loop owns the substrate."
Multiple coroutines (orchestrator + 5 role bridges + WebSocket
fan-out + cron-triggered cleanups) cooperate inside that loop. They
do NOT run as separate processes. Splitting any of them out requires
a message bus (see "No load balancer" above).

## What to read next

- For specific operational tasks: `runbooks/SKILL.md` is the runbook
  index.
- For substrate-level architectural commitments (why DuckDB, why
  event-log-as-primary, why typed events): `../docs/architecture_notes.md`.
- For substrate code orientation: `interfaces/research/api/app.py`
  (HTTP surface), `orchestration/loop_one/orchestrator.py` (the 8-
  phase Loop 1), `substrate/dispatch/router.py` (LLM routing).

## Open questions intentionally left to flag

These were deferred during initial provisioning. Revisit when the
prompting situation arises:

- **Repository visibility.** Currently assumed public (no SSH deploy
  key needed in setup.yml). If you flip to private, add an SSH deploy
  key on the VM and update `antiek_repo_url` to `git@github.com:...`.
- **R2 bucket region.** Default `eu`. For compliance reasons the
  operator may want a different region (Middle East has no R2 region
  as of early 2026; `eu` is the closest GDPR-aligned choice).
- **Caddy version pinning.** Currently installs from Caddy's stable
  apt repo (whatever the latest 2.x is). Pinning requires apt-pinning
  configuration; worth doing eventually for reproducibility.
- **Hetzner snapshots vs R2 backups.** We do R2 application-level
  backups only. Hetzner offers VM snapshots at ~$0.012/GB/month as a
  second defence layer.
- **DNSSEC at the registrar.** Porkbun doesn't have DNSSEC enabled.
  Cloudflare can sign the zone, but the DS record has to be set at
  Porkbun. Security improvement to revisit.
- **CI/CD pipeline.** None. Manual `ansible-playbook deploy.yml`.
  Correct when there are multiple committers.
- **Metrics / alerting.** None. `journalctl` + `caddy access.log`.
  Correct when traffic justifies aggregate dashboards.
