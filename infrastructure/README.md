# Antiek Infrastructure

Infrastructure-as-code for the Antiek substrate's production
deployment. Provisions a single Hetzner VM, configures it, deploys the
substrate, points `antiek.ai` at it via Cloudflare DNS, and snapshots
state nightly to Cloudflare R2.

## What this is

This directory is the *source of truth* for everything that runs at
`api.antiek.ai`. Two layers:

- **Terraform** (`terraform/`) — provisions the cloud resources:
  Hetzner VM + SSH key, Cloudflare DNS records, R2 bucket, zone-wide
  TLS settings.
- **Ansible** (`ansible/`) — configures the VM: installs Caddy +
  Python venv + the substrate, writes the systemd unit, sets up the
  backup cron.

Plus runbooks (`runbooks/`) walking through specific operational tasks,
and `SKILL.md` for agent-level operability.

## Prerequisites

- **Hetzner Cloud account** with an API token (Read & Write).
- **Cloudflare account** with `antiek.ai` already in DNS (zone exists,
  nameservers `drew.ns.cloudflare.com` + `maeve.ns.cloudflare.com`).
  An API token scoped to that zone with `Zone:DNS:Edit`, `Zone:Zone
  Settings:Edit`, `Account:R2:Edit`.
- **Local tools**: `terraform >= 1.6`, `ansible >= 9.0`. Install via:
  ```bash
  brew install terraform ansible
  ```
- **SSH key pair**:
  ```bash
  ssh-keygen -t ed25519 -f ~/.ssh/antiek_ed25519 -C "antiek-operator@$(hostname)"
  ```
- **Dispatch API keys** — z.ai (`Z_AI_API_KEY`, GLM-5.2 primary), plus
  DeepSeek + Xiaomi MiMo fallbacks; populated into
  `/etc/antiek/secrets.env` on the VM after first deploy.

## First-time setup

Follow `runbooks/first-deploy.md` line-by-line. Summary of the path:

1. Generate API tokens (Hetzner + Cloudflare).
2. Generate SSH key pair.
3. Verify nameserver propagation (`dig @1.1.1.1 NS antiek.ai +short`).
4. Populate `terraform/terraform.tfvars` from `terraform.tfvars.example`.
5. `terraform init && terraform apply` — provisions the VM and DNS.
6. Generate R2 API token in Cloudflare dashboard, save to
   `ansible/r2-creds.yml`.
7. Populate `ansible/inventory.ini` from `inventory.ini.example`
   with the new VM's IP.
8. `ansible-playbook -i inventory.ini playbooks/setup.yml -e @r2-creds.yml`
   — configures the VM, ~5 minutes.
9. `sudoedit /etc/antiek/secrets.env` on the VM — paste `Z_AI_API_KEY`
   (required — the primary for every tier) plus `DEEPSEEK_API_KEY` and
   `XIAOMI_API_KEY` (cross-family fallbacks).
10. `systemctl start antiek` on the VM.
11. `curl https://api.antiek.ai/health` from your Mac — expect a JSON
    response with `registered_providers` including `zai`/`zai_reasoning`.

End-to-end first time: ~45 minutes. Subsequent deploys (code changes
only) are ~2 minutes via `ansible-playbook playbooks/deploy.yml`.

## Operating model

**All infrastructure changes go through code.** If you find yourself
about to SSH in and edit a file, stop. Either:

- The change belongs in a template (`ansible/templates/*.j2`) →
  edit the template, commit, re-run `deploy.yml`.
- The change belongs in a playbook task (`ansible/playbooks/*.yml`)
  → edit the playbook, commit, re-run.
- The change is genuinely one-off (e.g. unsticking a wedged process)
  → SSH in, do it, **then** document it in `runbooks/debugging.md` so
  the next person doesn't have to re-derive the fix.

This is not bureaucracy. It's the only way a future-you or a future-
agent six months from now can understand what's actually running.

## Cost

- **Hetzner CCX23**: ~€26/month (4 dedicated AMD EPYC vCPUs, 16GB RAM,
  160GB NVMe, 20TB egress).
- **Cloudflare R2**: storage scales with the independently configured bucket
  lifecycle policy; the backup host never deletes recovery points.
- **Cloudflare DNS + TLS**: free tier.
- **Domain renewal**: Porkbun, ~$15/year for `.ai`.

LLM API costs are **separate** and per-investigation. Reference: the
photonic-interconnects validation run (Sprint 10) cost $0.162 — a
substantive cited-thesis run; the claude-less config routes flash/pro
via GLM-5.2 and synthesis via GLM-5.2 (thinking on), with DeepSeek +
MiMo as cross-family fallbacks.

## Directory layout

```
infrastructure/
├── README.md                       (this file — operator-facing summary)
├── SKILL.md                        (agent-facing topology + constraints)
├── terraform/
│   ├── versions.tf                 (provider pins)
│   ├── variables.tf                (input variables + defaults)
│   ├── main.tf                     (resources: VM, DNS, R2, zone settings)
│   ├── outputs.tf                  (IPs, SSH command, next steps)
│   ├── terraform.tfvars.example    (operator copies → terraform.tfvars)
│   └── .gitignore                  (excludes state and tfvars)
├── ansible/
│   ├── inventory.ini.example       (operator copies → inventory.ini)
│   ├── .gitignore                  (excludes inventory.ini, r2-creds.yml)
│   ├── group_vars/
│   │   └── all.yml                 (non-secret variables)
│   ├── playbooks/
│   │   ├── setup.yml               (initial VM bring-up)
│   │   ├── deploy.yml              (subsequent code deploys)
│   │   └── backup.yml              (manual backup trigger)
│   └── templates/
│       ├── antiek.service.j2       (systemd unit)
│       ├── Caddyfile.j2            (reverse proxy + TLS config)
│       ├── backup.sh.j2            (nightly backup script)
│       └── secrets.env.j2          (empty template, operator populates)
└── runbooks/
    ├── SKILL.md                    (runbook index)
    ├── first-deploy.md             (zero → live)
    ├── code-update.md              (deploy a code change)
    ├── secret-rotation.md          (rotate API keys)
    ├── disaster-recovery.md        (rebuild from backup)
    └── debugging.md                (common failure modes)
```

## Quick command reference

```bash
# First deploy
cd ~/Desktop/Antiek/infrastructure/terraform
terraform init && terraform apply
# (then populate ansible/inventory.ini with the new IP)
cd ../ansible
ansible-playbook -i inventory.ini playbooks/setup.yml -e @r2-creds.yml
# (then ssh in, sudoedit /etc/antiek/secrets.env, paste Z_AI_API_KEY + fallbacks)
# (then ssh in, systemctl start antiek)

# Deploy a code change
cd ~/Desktop/Antiek/infrastructure/ansible
ansible-playbook -i inventory.ini playbooks/deploy.yml

# Manual backup
ansible-playbook -i inventory.ini playbooks/backup.yml

# Check health
curl https://api.antiek.ai/health

# Live application logs
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip> journalctl -u antiek -f

# Decommission the whole thing
cd ~/Desktop/Antiek/infrastructure/terraform
terraform destroy
```

## When something breaks

`runbooks/debugging.md` indexes failure symptoms to diagnostic
commands and fixes. The three triage commands at the bottom of that
runbook surface 80% of issues.
