# Antiek Infrastructure Provisioning — Prompt for Claude Code

## 0. What This Is and Why

You are generating production infrastructure-as-code for `antiek.ai`, an event-driven research substrate this operator has built over twelve sprints (1,158 tests passing as of Sprint 10, end-to-end validated against real LLMs on a local Mac mini). The substrate is functionally complete. Today's task is to deploy it to a public-facing host so the operator can iterate on a web-app surface while the substrate runs accessibly.

The deliverable is a `infrastructure/` directory at the repository root containing Terraform, Ansible, and runbooks. The whole tree is committed to git. Real secrets and per-environment inventory live in gitignored files alongside committed `.example` templates.

You are NOT executing the deploy. You are writing the code that the operator will run.

## 1. Architectural Commitments (Read Before Designing Anything)

These commitments come from `docs/architecture_notes.md` and twelve sprints of test scaffolding around them. Violating them is a regression. Generating code that requires violating them is also wrong.

**Single-writer DuckDB.** The substrate's write path is funnelled through `runtime/db_lock.py::connect_write`, which takes an exclusive flock on a sidecar file before opening DuckDB for writes. The actual corruption-prevention happens at the flock layer, per-write-transaction. But cheap defence-in-depth is `--workers 1` on the uvicorn process: more workers won't corrupt the file (the flock holds), they'll just serialize and create mysterious latency under load. The systemd `ExecStart` MUST therefore be `--workers 1`. Do not propose `--workers 4` "for performance"; do not propose horizontal scaling; do not propose a load balancer fronting multiple backends.

**Long-running orchestrator awaits.** Single decomposer calls under OpenRouter load have been measured at 226 s (DeepSeek V4 Pro). Investigation-level awaits can exceed 600 s. The reverse proxy must not impose a 60 s default timeout. Caddy is the choice because its default upstream timeout is generous and its config is one file. The Caddyfile must NOT set a shorter timeout than the substrate needs; if you set one explicitly, match the uvicorn `--timeout-keep-alive` (900 s).

**Persistent local NVMe.** Both `~/.antiek/research_events/*.jsonl` (append-only event log) and `~/.antiek/antiek.duckdb` (mutated in place) live on the VM's local disk. Hetzner CCX23 ships with local NVMe. Do NOT propose attaching a Hetzner Volume (network-attached block storage) for these paths — a network blip becomes data loss.

**No horizontal scaling.** `InvestigationCoordinator` holds per-investigation futures in-process. Splitting backends breaks coordination. If concurrency outgrows one CCX23 (it won't, this sprint), the next architectural sprint migrates to Postgres + an external event bus. That is a separate sprint and out of scope.

**Append-only event log; in-place DuckDB.** The event log can be rsynced live. The DuckDB file CANNOT be `cp`'d while open — the snapshot is inconsistent. Use `EXPORT DATABASE` to produce a re-importable Parquet/SQL bundle, then back up that bundle.

## 2. Codebase Anchors You Must Match Exactly

Verified against the current `/Users/slimydog/Desktop/Antiek/` tree on 2026-05-17. Hard-code these; do not invent variants.

| Concern | Value |
|---|---|
| FastAPI app import path | `interfaces.research.api.app:app` |
| Health endpoint | `GET /health` returns `{version, schema_version, registered_providers}` |
| Provider registration | `create_app()` calls `register_default_providers()` automatically at startup; no extra wiring needed |
| State root env var | `ANTIEK_HOME` (default `~/.antiek`). **NOT `ANTIEK_STATE_DIR`** — that name does not exist in the codebase |
| Knowledge skills override | `ANTIEK_KNOWLEDGE_SKILLS_DIR` (default `${ANTIEK_HOME}/knowledge_skills`) |
| DuckDB file | `${ANTIEK_HOME}/antiek.duckdb` |
| Event log | `${ANTIEK_HOME}/research_events/*.jsonl` |
| Python | `requires-python = ">=3.11"` per `pyproject.toml`. Ubuntu 24.04 ships 3.12 by default; install `python3.12` + `python3.12-venv` |
| Install command | `pip install -e .[arxiv,pdf,urls,embedding,interview,youtube,rss]` from `/opt/antiek`. Skip `dev` extra in production |
| Smoke-test script | `tools/demo/run_cold_question.py` (already exists) |
| Single-writer enforcement | `runtime/db_lock.py::connect_write` (flock-based; not optional, not pluggable today) |

## 3. Target Topology (Single VM)

```
Client (browser, curl, app.antiek.ai)
        │
        ▼  HTTPS
Cloudflare DNS (proxied=false for api.*, proxied=true for app.*)
        │
        ▼  TCP/443
Hetzner CCX23 (Falkenstein, 4 vCPU AMD EPYC, 16 GB, 160 GB NVMe)
   ├── Caddy   :443  → TLS termination via Let's Encrypt (HTTP-01)
   │              → reverse_proxy localhost:8001
   ├── uvicorn :8001 → interfaces.research.api.app:app
   │                 → reads /etc/antiek/secrets.env, writes ~/.antiek/
   └── cron 03:00 UTC → /usr/local/bin/antiek-backup → R2

R2 bucket: antiek-backups (EU region, S3-compatible)
```

Domain `antiek.ai` is registered at Porkbun, nameservers already delegated to Cloudflare (`drew.ns.cloudflare.com` / `maeve.ns.cloudflare.com`). The Cloudflare zone exists. No Hetzner account exists yet; the operator creates it and generates an API token before running `terraform apply`.

## 4. Directory Layout to Produce

```
infrastructure/
├── README.md
├── SKILL.md
├── terraform/
│   ├── versions.tf
│   ├── variables.tf
│   ├── main.tf
│   ├── outputs.tf
│   ├── terraform.tfvars.example
│   └── .gitignore
├── ansible/
│   ├── inventory.ini.example
│   ├── .gitignore
│   ├── group_vars/all.yml
│   ├── playbooks/{setup.yml,deploy.yml,backup.yml}
│   └── templates/{antiek.service.j2,Caddyfile.j2,backup.sh.j2,secrets.env.j2}
└── runbooks/
    ├── SKILL.md
    ├── first-deploy.md
    ├── code-update.md
    ├── secret-rotation.md
    ├── disaster-recovery.md
    └── debugging.md
```

Every file is committed. Real `.tfvars`, `inventory.ini`, and `r2-creds.yml` are gitignored.

## 5. File-by-File Requirements

### 5.1 `terraform/versions.tf`

Pin Terraform `>= 1.6.0`. Pin providers explicitly because both have had naming churn:

- `hetznercloud/hcloud ~> 1.45`
- `cloudflare/cloudflare ~> 4.40` — **stay on the 4.x line.** Cloudflare provider 5.0+ renamed `cloudflare_record` → `cloudflare_dns_record` and removed `cloudflare_zone_settings_override`. The resource names in §5.3 below assume 4.x. If you migrate to 5.x later, that is its own runbook.

Comment block stating: pin majors strictly, allow minor/patch, read each provider's CHANGELOG before bumping.

### 5.2 `terraform/variables.tf`

Sensitive variables (no defaults; supplied via `TF_VAR_*` env vars or gitignored `terraform.tfvars`):
- `hetzner_token`, `cloudflare_token`, `cloudflare_account_id`, `cloudflare_zone_id`

Non-sensitive with defaults:
- `ssh_public_key_path` → `~/.ssh/antiek_ed25519.pub`
- `server_name` → `antiek-prod-fsn1`
- `server_type` → `ccx23`
- `datacenter` → `fsn1-dc14`
- `image` → `ubuntu-24.04`
- `domain` → `antiek.ai`
- `api_subdomain` → `api`
- `app_subdomain` → `app`
- `pages_target` → `antiek-ai.pages.dev` (operator confirms the actual Pages project name after creating it in the dashboard)
- `r2_bucket_name` → `antiek-backups`
- `r2_region` → `eu` (lowest latency to Falkenstein; flag in comment that operator may have compliance reasons to pick another)

Every variable has a `description` explaining what it controls and what the consequence of changing it is. No invented secrets — sensitive defaults are explicitly `null` with a comment.

### 5.3 `terraform/main.tf`

Resources in dependency order, each preceded by a comment block:

1. `hcloud_ssh_key.operator` — uploads the public key.
2. `hcloud_server.antiek` — `ccx23` in `fsn1-dc14`, Ubuntu 24.04, attached to the SSH key. `user_data` is minimal cloud-init that only ensures `python3` is installed (Ansible owns the rest). Output IPv4 and IPv6.
3. `cloudflare_record.api_a` — A record `api.antiek.ai` → `hcloud_server.antiek.ipv4_address`. `proxied = false` initially (Let's Encrypt HTTP-01 must reach the origin). Comment: enabling the proxy later is a one-line change once the cert is provisioned and the operator wants Cloudflare edge protection on the API.
4. `cloudflare_record.api_aaaa` — AAAA record for the IPv6.
5. `cloudflare_record.app_cname` — CNAME `app.antiek.ai` → `var.pages_target`, `proxied = true`.
6. `cloudflare_r2_bucket.backups` — `antiek-backups` in the EU region.
7. `cloudflare_zone_settings_override.zone_security` — `ssl = "strict"`, `always_use_https = "on"`, `min_tls_version = "1.2"`, `tls_1_3 = "on"`.

For each resource, comments explain the *why* (not the *what*).

### 5.4 `terraform/outputs.tf`

Outputs the operator copies into the Ansible inventory and runbooks:
- `server_ipv4`, `server_ipv6`
- `ssh_command` — formatted string the operator can paste
- `r2_endpoint` — S3-compatible URL (`https://<account_id>.r2.cloudflarestorage.com`)
- `next_step` — string: `"Run: cd ../ansible && cp inventory.ini.example inventory.ini, edit it with the IP above, then ansible-playbook -i inventory.ini playbooks/setup.yml"`

### 5.5 `terraform/.gitignore` + `terraform.tfvars.example`

Gitignore: `*.tfstate`, `*.tfstate.*`, `*.tfvars`, `.terraform/`, `crash.log`. Keep `.terraform.lock.hcl` committed (lockfile determinism).

`terraform.tfvars.example` shows the variable shape with placeholder values clearly marked `<HETZNER_TOKEN>`, etc.

### 5.6 `ansible/group_vars/all.yml`

```yaml
antiek_user: antiek
antiek_repo_url: "<https://github.com/<operator>/Antiek.git>"  # TODO: operator fills in
antiek_repo_branch: main
antiek_home: /home/antiek
antiek_install_dir: /opt/antiek
antiek_state_dir: /home/antiek/.antiek      # value of ANTIEK_HOME at runtime
antiek_secrets_file: /etc/antiek/secrets.env
python_package: python3.12                   # Ubuntu 24.04 default; matches pyproject's >=3.11
uvicorn_port: 8001
api_domain: api.antiek.ai
r2_bucket: antiek-backups
r2_endpoint: ""                              # filled in from Terraform output by operator
```

Repo visibility is a decision point. **Default proposal: keep the repo public during prototyping** — there are no secrets in code (all keys are runtime env vars), and a public repo lets Ansible clone with no SSH key dance. Add a comment offering the private-repo alternative (deploy key on the VM, HTTPS token, or SSH-agent forwarding).

### 5.7 `ansible/templates/antiek.service.j2`

```ini
[Unit]
Description=Antiek substrate (FastAPI + Loop 1 orchestrator)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={{ antiek_user }}
Group={{ antiek_user }}
WorkingDirectory={{ antiek_install_dir }}
EnvironmentFile={{ antiek_secrets_file }}
Environment="PATH={{ antiek_install_dir }}/.venv/bin:/usr/bin:/bin"
Environment="ANTIEK_HOME={{ antiek_state_dir }}"
# --workers 1 is mandatory: the substrate's write path goes through
# runtime/db_lock.py::connect_write, which serializes via flock. Extra workers
# don't corrupt the DB (the flock holds), they just queue and create mysterious
# latency. Keep it at 1.
# --timeout-keep-alive 900 matches the orchestrator's longest measured await
# (DeepSeek V4 Pro under OpenRouter load: 226 s/call observed; 600+ s end-to-end).
ExecStart={{ antiek_install_dir }}/.venv/bin/uvicorn interfaces.research.api.app:app \
  --host 127.0.0.1 --port {{ uvicorn_port }} --workers 1 --timeout-keep-alive 900
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={{ antiek_state_dir }} /tmp /var/tmp
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

[Install]
WantedBy=multi-user.target
```

Note the env var is `ANTIEK_HOME`, not `ANTIEK_STATE_DIR`. The codebase reads `ANTIEK_HOME` in `orchestration/phase_runner/postconditions.py::default_knowledge_skills_dir` and parallel sites; renaming it breaks the substrate silently.

### 5.8 `ansible/templates/Caddyfile.j2`

```
{{ api_domain }} {
    reverse_proxy localhost:{{ uvicorn_port }}

    # Caddy's default upstream read/write timeouts are unbounded (until the
    # upstream closes the connection or the client disconnects). That matches
    # the substrate's expected wall-clock per investigation. Do not add
    # explicit shorter timeouts. WebSocket upgrade is automatic on /ws/events.

    encode gzip zstd

    log {
        output file /var/log/caddy/access.log {
            roll_size 100mb
            roll_keep 5
            roll_keep_for 720h
        }
        format json
    }
}
```

Caddy auto-provisions Let's Encrypt certs on first request. Note for the operator: the Cloudflare A record above is `proxied = false` precisely so HTTP-01 can complete; flipping it to `proxied = true` requires switching Caddy to a DNS-01 challenge (separate runbook, deferred).

### 5.9 `ansible/templates/backup.sh.j2`

```bash
#!/usr/bin/env bash
set -euo pipefail

# Antiek nightly backup.
# Runs as root via cron at 03:00 UTC. Output to /var/log/antiek-backup.log.
#
# Strategy:
#   1. DuckDB → EXPORT DATABASE to a staging dir (consistent snapshot).
#      Copying the .duckdb file while substrate is running produces a torn
#      snapshot; EXPORT is the supported way.
#   2. Event log → rsync (append-only .jsonl, safe to copy hot).
#   3. Knowledge skills → rsync (Phase 8 patches accumulate here).
#   4. tar+gzip, upload to R2, prune local staging.
#   5. Drop R2 objects older than 14 days (keep last fortnight).

readonly STATE_DIR="{{ antiek_state_dir }}"
readonly R2_BUCKET="{{ r2_bucket }}"
readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly STAGING="/var/tmp/antiek-backup-${TIMESTAMP}"
readonly ARCHIVE="${STAGING}.tar.gz"

log() { echo "[$(date -u --iso-8601=seconds)] $*"; }

log "backup starting"
mkdir -p "${STAGING}"

# 1. DuckDB consistent snapshot
sudo -u {{ antiek_user }} duckdb "${STATE_DIR}/antiek.duckdb" \
    "EXPORT DATABASE '${STAGING}/duckdb' (FORMAT PARQUET);"

# 2. Event log
rsync -a "${STATE_DIR}/research_events/" "${STAGING}/research_events/"

# 3. Knowledge skills (Phase 8 compounding artefacts)
if [[ -d "${STATE_DIR}/knowledge_skills" ]]; then
    rsync -a "${STATE_DIR}/knowledge_skills/" "${STAGING}/knowledge_skills/"
fi

# 4. Compress and upload
tar -czf "${ARCHIVE}" -C "/var/tmp" "$(basename "${STAGING}")"
rclone copyto "${ARCHIVE}" "r2:${R2_BUCKET}/nightly/antiek-${TIMESTAMP}.tar.gz"

# 5. Prune local staging
rm -rf "${STAGING}" "${ARCHIVE}"

# 6. Retention — keep last 14 nightlies. Document the policy in
#    runbooks/disaster-recovery.md; revisit as trajectory volume grows.
rclone delete --min-age 14d "r2:${R2_BUCKET}/nightly/" --include "*.tar.gz" || true

log "backup complete"
```

### 5.10 `ansible/templates/secrets.env.j2`

```
# Antiek runtime secrets. Mode 0640, owner root:antiek.
# Edit on the VM: sudoedit /etc/antiek/secrets.env
# After editing: systemctl restart antiek
#
# OpenRouter is the only required key for first deploy — the substrate
# routes DeepSeek, Anthropic, and OpenAI through OpenRouter via
# substrate.dispatch.providers.bootstrap.
OPENROUTER_API_KEY=
# ANTHROPIC_API_KEY=     # only if direct, not via OpenRouter
# DEEPSEEK_API_KEY=      # only if direct, not via OpenRouter
# OPENAI_API_KEY=        # only if direct, not via OpenRouter
```

### 5.11 `ansible/playbooks/setup.yml`

Idempotent initial bring-up, runs as `root`. Tasks in order; every task uses a proper Ansible module (`apt`, `user`, `git`, `template`, `systemd`, `ufw`, `copy`, `lineinfile`) — no bare `shell` where a module exists. Required actions:

1. `apt update && apt upgrade -y`. If kernel updated, reboot and wait for connection.
2. Install base packages: `python3.12`, `python3.12-venv`, `python3-pip`, `git`, `build-essential`, `caddy`, `ufw`, `unattended-upgrades`, `rclone`, `duckdb` (the CLI, for backups).
3. Configure `unattended-upgrades` for security patches only; no automatic reboots.
4. UFW: default deny incoming. Allow 22, 80, 443. Port 80 stays open because Let's Encrypt's HTTP-01 challenge reaches Caddy on 80. Enable UFW.
5. Create user `antiek` (home `/home/antiek`, shell `/bin/bash`, no sudo). Sudo operations are the operator's, via root.
6. Authorize the operator's SSH key on `antiek` (copy from `/root/.ssh/authorized_keys`) so `ssh antiek@<ip>` works directly.
7. Clone the repo to `/opt/antiek/`, checkout configured branch, set ownership to `antiek:antiek`.
8. Create venv at `/opt/antiek/.venv`, install with `pip install -e .[arxiv,pdf,urls,embedding,interview,youtube,rss]`.
9. Create `/etc/antiek/`, mode 0750, owner `root:antiek`. Render `secrets.env` template with empty placeholders, mode 0640. Do not start the service yet.
10. Create `{{ antiek_state_dir }}/` tree owned by `antiek:antiek`: `research_events/`, `knowledge_skills/`, and an empty parent.
11. Render `/etc/systemd/system/antiek.service` from template. `systemctl daemon-reload`, enable (but do not start).
12. Render `/etc/caddy/Caddyfile` from template. Reload Caddy.
13. Render `/usr/local/bin/antiek-backup` from template, mode 0750, owner `root:antiek`.
14. Configure rclone for R2 at `/root/.config/rclone/rclone.conf`. R2 credentials come from `--extra-vars @r2-creds.yml` (gitignored, operator generates the access keys in the Cloudflare dashboard after Terraform creates the bucket). If R2 creds are absent, skip this step with a warning — the service still works; backups just don't run.
15. Install cron: `/etc/cron.d/antiek-backup` containing `0 3 * * * root /usr/local/bin/antiek-backup >> /var/log/antiek-backup.log 2>&1`.
16. Final notification: print the remaining manual step. Exact text: `Next: ssh root@<ip> sudoedit /etc/antiek/secrets.env, paste OPENROUTER_API_KEY=sk-or-..., then ssh root@<ip> systemctl start antiek.`

### 5.12 `ansible/playbooks/deploy.yml`

Subsequent code deploys, idempotent:
1. `git pull` in `/opt/antiek/` (as `antiek` user).
2. `pip install -e .[arxiv,pdf,urls,embedding,interview,youtube,rss]` in the venv to pick up dependency changes.
3. Re-render templates; restart Caddy only if the Caddyfile changed; restart antiek only if the systemd unit or backup script changed OR the deploy was code-only (always restart antiek on code-only deploys).
4. Health-check: `uri` module hitting `https://{{ api_domain }}/health` from the controller. Assert HTTP 200, JSON `registered_providers` non-empty. Fail loudly if not — a broken deploy should surface immediately, not on the next investigation.

### 5.13 `ansible/playbooks/backup.yml`

Manual backup trigger. Runs `/usr/local/bin/antiek-backup` on the VM, streams output back. Useful before risky operations (a deploy you're unsure about, a Python upgrade).

### 5.14 Runbooks

Each is a single Markdown file, written to be readable by an agent without further context. Style: numbered steps; expected output after each command; one paragraph per step explaining the most common failure mode.

- **`first-deploy.md`** — zero-to-running. Steps cover: token generation (Hetzner + Cloudflare scopes spelled out), SSH key generation, nameserver-propagation verification (`dig @1.1.1.1 NS antiek.ai +short` must show both Cloudflare nameservers), `terraform init/plan/apply`, populating `inventory.ini` from Terraform outputs, running `setup.yml`, generating R2 access keys in the Cloudflare dashboard, re-running `setup.yml` with `r2-creds.yml`, populating `secrets.env`, `systemctl start antiek`, hitting `/health`, smoke test via `python -m tools.demo.run_cold_question --question "what is two plus two" --endpoint https://api.antiek.ai`. For each step the expected output and the diagnostic for the most common failure.
- **`code-update.md`** — happy path is `git push main && ansible-playbook -i inventory.ini playbooks/deploy.yml`. Unhappy path: `git revert HEAD && ansible-playbook ... playbooks/deploy.yml`, or pin the VM to a prior commit via `-e antiek_repo_branch=<sha>` and re-run. Document rollback explicitly; it's the only safety net.
- **`secret-rotation.md`** — OpenRouter key rotation: generate new key, `sudoedit /etc/antiek/secrets.env`, `systemctl restart antiek`, verify via dispatch test (curl a known-good investigation seed and check the log for a successful call), revoke old key in OpenRouter dashboard. Same pattern works for Anthropic/DeepSeek/OpenAI direct keys when those get wired.
- **`disaster-recovery.md`** — VM is gone, restore from R2: `terraform apply` to provision a new VM, update inventory, run `setup.yml`, `rclone copyto r2:antiek-backups/nightly/antiek-<latest>.tar.gz /tmp/`, untar, `rsync` event log and knowledge_skills back into place, `duckdb antiek.duckdb "IMPORT DATABASE '/tmp/.../duckdb'"`, `chown -R antiek:antiek ~/.antiek`, re-populate secrets, start service. RTO ~30 min if backups accessible; RPO 24h because backups are nightly. Document explicitly so the operator can decide later if RPO is acceptable or needs tightening.
- **`debugging.md`** — catalogue keyed by symptom:
  - *Service won't start* → `journalctl -u antiek -n 200`. Common causes: empty secrets file, port 8001 occupied, venv missing deps.
  - *`/health` returns `registered_providers: []`* → secrets file empty or malformed; check via `ssh root@<ip> cat /etc/antiek/secrets.env`. Restart after fixing.
  - *Caddy returns 502* → uvicorn is down; `systemctl status antiek`.
  - *Caddy can't get cert* → port 80 blocked (UFW or Cloudflare proxy enabled). Cloudflare A record must be `proxied = false` for HTTP-01.
  - *Investigation times out at phase 1* → check `DEFAULT_ROLE_TIMEOUT` in `substrate/constants.py`; OpenRouter under load needs ≥600 s for Pro tier.
  - *Disk full* → event log growing without bound. Two options: prune old `.jsonl` (lossy for trajectory replay) or attach a Hetzner Volume for `research_events/` only (changes local-disk assumption — separate runbook needed before doing this).
  - *DuckDB write errors after a crash* → stuck lock file at `${ANTIEK_HOME}/.duckdb.lock` (or whatever sidecar `runtime/db_lock.py` writes). Check `cat` of that file shows a non-running PID, delete, restart.
- **`SKILL.md`** (in `runbooks/`) — one-paragraph index of every runbook, written last so it can reference what actually shipped.

### 5.15 Top-level `infrastructure/SKILL.md`

Agent-facing entry point. Sections, in order:

1. **Topology** — same ASCII diagram as §3 of this prompt.
2. **Where state lives** — three places: (a) repo (source of truth for `.tf`/`.yml`/runbooks); (b) VM filesystem (`/opt/antiek/`, `/home/antiek/.antiek/`, `/etc/antiek/`); (c) provider dashboards (reflect state, never edit directly — `terraform apply` will revert drift).
3. **Common operations** — numbered list with one-line summary and pointer to specific runbook for: deploy code change, rotate secret, restore from backup, check service status, view logs, run a smoke-test investigation.
4. **Constraints that look weird** — `--workers 1`, Caddy not nginx, no load balancer, local disk not network volume. One line each on the *why*. Pre-empts the next agent's plausible-but-wrong optimizations.
5. **What to read next** — pointers to `runbooks/`, `docs/architecture_notes.md`, and `pyproject.toml`.

### 5.16 `infrastructure/README.md`

Two pages. Sections: *What this is*, *Prerequisites* (specific Hetzner token scopes: Servers + SSH Keys; specific Cloudflare token scopes: `Zone:DNS:Edit` on the `antiek.ai` zone, `Account:R2:Edit`; `terraform >= 1.6`; `ansible >= 9.0`; SSH key pair at `~/.ssh/antiek_ed25519`; an OpenRouter API key), *First-time setup* (numbered top-level steps with pointer to `runbooks/first-deploy.md` for the line-by-line walkthrough), *Operating model* (no SSH-and-edit; every change goes through code edits), *Cost* (~$30/mo Hetzner CCX23 + ~$0.50/mo R2 + Cloudflare free + per-investigation LLM costs separately).

## 6. Quality Bar

- **Idempotency.** Every Ansible task re-runnable. Use `creates:`/`removes:` guards on `shell` tasks; never `command: echo X >> file` (use `lineinfile`).
- **Comments explain *why*.** The *what* is in the code. Every Terraform resource and every Ansible task block has a one- to three-line comment justifying the choice. Future-agent-Claude shouldn't reverse-engineer intent.
- **No cleverness.** No bash one-liners that do something fancy. Write it out.
- **Shell scripts are strict.** Every `*.sh` template starts with `set -euo pipefail`. Every command that can fail has an explicit handling (`|| true` if expected, an error message if not).
- **No invented credentials.** Where the operator supplies a value, use a clearly placeholder string: `<HETZNER_TOKEN>`, `# TODO: operator pastes Cloudflare account ID here`. Never a real-looking string.
- **Document tested assumptions.** Where you assume Hetzner's `ccx23` SKU is still right, Cloudflare's R2 API hasn't shifted, Caddy's automatic HTTPS works as remembered — say so in a comment so the operator knows what to verify against current docs.

## 7. Hard "Do Not"s

A consolidated list. Each item shares the same underlying reason: this is one VM running one Python process with one local DuckDB file, and the substrate is built around that.

- **No Docker, Kubernetes, Nomad, ECS, Fargate, App Runner, Cloud Run.** Containers add image-build/registry/restart-semantics overhead that doesn't earn its keep at this scale and complicates the single-writer invariant. Revisit after the architecture stabilizes and after the operator decides containers are worth their cost.
- **No horizontal scaling, no load balancer, no second backend.** `InvestigationCoordinator` is in-process.
- **No "DuckDB-as-a-service" or remote-DB layer.** DuckDB is embedded by design.
- **No CI/CD pipeline yet.** Manual `ansible-playbook deploy.yml` from the operator's Mac is the right friction level for a prototyping operator. CI/CD becomes correct when there's a second committer or manual deploys become a bottleneck.
- **No Prometheus/Grafana/Sentry/alerting.** systemd journal + Caddy access logs are sufficient for this stage. Document this as a known gap in `debugging.md`. The operator will SSH in and `journalctl` when something is wrong.
- **No inventing provider API behavior.** If you are not 100% certain about a Cloudflare or Hetzner resource argument's shape under the pinned version, say so in a comment and direct the operator to the relevant docs URL.

## 8. Generation Order

Produce in this order so each file can reference the previous. After each file, state one sentence about what it does. After the final file, produce a single "next actions" block listing the exact commands (with placeholders) the operator types to go from "nothing exists" to "antiek.ai serving traffic."

1. `terraform/versions.tf`
2. `terraform/variables.tf`
3. `terraform/main.tf`
4. `terraform/outputs.tf`
5. `terraform/.gitignore` + `terraform.tfvars.example`
6. `ansible/group_vars/all.yml`
7. `ansible/templates/antiek.service.j2`
8. `ansible/templates/Caddyfile.j2`
9. `ansible/templates/backup.sh.j2`
10. `ansible/templates/secrets.env.j2`
11. `ansible/inventory.ini.example` + `ansible/.gitignore`
12. `ansible/playbooks/setup.yml`
13. `ansible/playbooks/deploy.yml`
14. `ansible/playbooks/backup.yml`
15. `runbooks/first-deploy.md`
16. `runbooks/code-update.md`
17. `runbooks/secret-rotation.md`
18. `runbooks/disaster-recovery.md`
19. `runbooks/debugging.md`
20. `runbooks/SKILL.md`
21. `infrastructure/SKILL.md`
22. `infrastructure/README.md`

## 9. Acceptance Criteria (Testable)

The generated work is acceptable when:

1. Every file path in §4 exists with non-trivial content.
2. `--workers 1` appears in `antiek.service.j2` AND is explained in at least three places: the systemd template, `infrastructure/SKILL.md`, and `runbooks/debugging.md`.
3. Every reference to the state root uses `ANTIEK_HOME`, not `ANTIEK_STATE_DIR`.
4. The FastAPI app import path is exactly `interfaces.research.api.app:app`.
5. The Python version installed by `setup.yml` satisfies `>=3.11` per `pyproject.toml` (defaulting to `python3.12` on Ubuntu 24.04).
6. Every `*.sh` template starts with `set -euo pipefail`.
7. `deploy.yml` includes a post-deploy health check that fails the playbook if `/health` returns non-200 or empty `registered_providers`.
8. The backup script uses DuckDB `EXPORT DATABASE` (not raw file copy) for the DuckDB snapshot.
9. The Cloudflare A record for `api.antiek.ai` is `proxied = false`, with a comment explaining the Let's Encrypt HTTP-01 dependency.
10. `terraform/.gitignore` excludes `*.tfstate*` and `*.tfvars`; no real secret values appear anywhere in committed files.
11. Following `runbooks/first-deploy.md` end-to-end, with no other documentation, takes the operator from a blank Hetzner account to a `/health`-responding deployment.
12. The single-writer DuckDB invariant is described (with the *consequence* of violating it spelled out: serialized writes under flock, no corruption, but mysterious latency) in at least the systemd template comment and `debugging.md`.

## 10. Open Questions — Flag, Don't Decide

When you hit these, leave a code comment proposing a default and explaining the tradeoff. Do not pick silently.

- **Repository visibility.** Public repo simplifies cloning; private repo needs a deploy key. Default proposal: public during prototyping. Flag the alternative.
- **R2 bucket region.** EU minimizes latency from Falkenstein. If the operator has Saudi data-residency or US-availability reasons, this changes. Flag in a Terraform comment.
- **Caddy version pinning.** `apt install caddy` pulls the current `cloudsmith` repo version. Pinning to a specific minor requires apt-pinning config — worth doing eventually, skip on day one.
- **Hetzner snapshot vs. R2 backup.** Hetzner offers VM snapshots ($0.012/GB/mo) as a separate mechanism. R2 backups are application-level and portable. Both have merit. Flag in `disaster-recovery.md`.
- **DNSSEC at the registrar.** Porkbun panel shows DNSSEC unconfigured. Cloudflare can sign the zone but the DS record must be set at Porkbun. Flag as a post-deploy security improvement.

## 11. Operator Context

The operator (Faisal Nazer, based in Jeddah) is a deep-tech investment analyst who built this substrate himself with extensive AI assistance. Linux fluency and command-line comfort can be assumed. Terraform-specific and Ansible-specific patterns should be explained where they appear, not assumed prior knowledge. Where decisions have tradeoffs, name the tradeoffs explicitly rather than burying them under a default — the operator wants to understand his own infrastructure, not just have it work.

Now produce the files in the order specified in §8.
