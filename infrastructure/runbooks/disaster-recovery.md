# Disaster Recovery — VM Is Gone, Restore From Backup

**Scenarios this covers**:
- Hetzner DC fire / hardware failure / your VM disappears.
- You accidentally `terraform destroy`'d.
- You need to migrate to a new datacenter (Falkenstein → Helsinki, say).
- The DuckDB file got corrupted and the latest backup is the cleanest
  state available.

**What you can recover**:
- DuckDB graph (chunks, nodes, edges, documents, syntheses, outcomes)
- Event log (typed events; trajectory data)
- Knowledge skills (Phase 8 accumulations)

**What you cannot recover**:
- Anything since the last backup. Backups run nightly at 03:00 UTC, so
  worst-case data loss is ~24 hours.
- Secrets — the `secrets.env` is deliberately not backed up. You
  re-populate it manually with `sudoedit` (or from your 1Password / etc.).

**Recovery Time Objective (RTO)**: ~30 minutes if R2 backups are
accessible and you're following this runbook.

**Recovery Point Objective (RPO)**: 24 hours (nightly backups). If
this is unacceptable, change the systemd timer schedule in
`infrastructure/ansible/group_vars/all.yml` to run more frequently
(every 6 hours doubles your R2 storage cost — small, but real).

---

## Step 1 — Provision a new VM

```bash
cd ~/Desktop/Antiek/infrastructure/terraform
terraform apply
```

If the VM was lost but the Terraform state file says it still exists,
first refresh state to detect the drift:

```bash
terraform refresh
terraform apply
```

Wait ~90 seconds. Note the new `server_ipv4` from the output.

If even the Terraform state file is gone (catastrophic — local Mac
disk died), see "Recovering from no Terraform state" at the bottom.

## Step 2 — Update Ansible inventory with the new IP

```bash
cd ~/Desktop/Antiek/infrastructure/ansible
# Edit inventory.ini, replace the old IP with the new server_ipv4
nano inventory.ini
```

## Step 3 — Bring the new VM to the same configured state

```bash
ansible-playbook -i inventory.ini playbooks/setup.yml -e @r2-creds.yml
```

Same playbook as first-deploy.md step 10. Idempotent. ~5 minutes. End
state: substrate code installed, Caddy configured, systemd unit
enabled, backup timer registered, but no state yet and no secrets.

## Step 4 — Download the latest backup from R2

From your Mac (you need rclone configured locally — or do this on the
new VM, where rclone was just configured by setup.yml):

**Option A — list and pick from your Mac** (if your Mac has rclone +
the R2 creds in its config):

```bash
rclone ls r2:antiek-backups/nightly/
# pick the most recent or the one before the corruption event
rclone copyto r2:antiek-backups/nightly/antiek-20260516T030001Z.tar.gz \
    /tmp/antiek-restore.tar.gz
```

**Option B — do it on the new VM** (rclone is already configured
there from setup.yml):

```bash
ssh root@<new-vm-ip>
rclone --config /etc/rclone/rclone.conf ls r2:antiek-backups/nightly/
# pick a backup
rclone --config /etc/rclone/rclone.conf copyto \
    r2:antiek-backups/nightly/antiek-20260516T030001Z.tar.gz \
    /tmp/antiek-restore.tar.gz
```

Backups are named `antiek-<UTC-timestamp>.tar.gz`. The most recent one
is usually what you want unless you're rolling back a corruption event,
in which case pick one from before the corruption.

## Step 5 — Extract on the VM

```bash
ssh root@<new-vm-ip>
cd /tmp
tar -xzf antiek-restore.tar.gz
# Creates /tmp/antiek-backup-<timestamp>/
ls -la /tmp/antiek-backup-*/
# Expected: duckdb/  research_events/  knowledge_skills/
```

## Step 6 — Restore the event log + knowledge skills

These are file copies — straightforward rsync over the empty state
directory:

```bash
RESTORE_DIR=$(ls -d /tmp/antiek-backup-*/ | head -n 1)

# Restore the event log
sudo -u antiek rsync -a "${RESTORE_DIR}/research_events/" \
    /home/antiek/.antiek/research_events/

# Restore the knowledge-skills directory
sudo -u antiek rsync -a "${RESTORE_DIR}/knowledge_skills/" \
    /home/antiek/.antiek/knowledge_skills/
```

## Step 7 — Restore the DuckDB graph

The backup is a directory of Parquet shards + a `load.sql` script
(produced by DuckDB's `EXPORT DATABASE`). Reconstitute with `IMPORT
DATABASE`:

```bash
RESTORE_DIR=$(ls -d /tmp/antiek-backup-*/ | head -n 1)

# Ensure no stale DuckDB file exists (IMPORT requires a fresh DB)
rm -f /home/antiek/.antiek/antiek.duckdb

# Run IMPORT DATABASE as the antiek user so file ownership is right
sudo -u antiek /opt/antiek/.venv/bin/python3 -c "
import duckdb
con = duckdb.connect('/home/antiek/.antiek/antiek.duckdb')
con.execute(\"IMPORT DATABASE '${RESTORE_DIR}/duckdb';\")
con.close()
print('IMPORT complete')
"
```

Expected output: `IMPORT complete`. Takes seconds for a small graph,
minutes for a large one.

## Step 8 — Fix ownership (defensive)

```bash
chown -R antiek:antiek /home/antiek/.antiek/
```

## Step 9 — Populate the secrets file

Same as first-deploy.md step 11:

```bash
sudoedit /etc/antiek/secrets.env
# Paste OPENROUTER_API_KEY=sk-or-v1-...
```

## Step 10 — Start the substrate

```bash
systemctl start antiek
systemctl status antiek
```

Should report `active (running)`. Exit back to your Mac:

```bash
exit
curl https://api.antiek.ai/health
```

Should return `{"status":"ok",...}`.

DNS may take a moment to repoint to the new IP — Terraform updated the
A and AAAA records when you ran `terraform apply` in step 1, but DNS
caches at the resolver layer have a TTL. The records are set to 300s
TTL, so worst case wait 5 minutes for clients (including your `curl`)
to pick up the new IP.

## Step 11 — Verify the restored state

```bash
# Trigger a tiny investigation — confirms substrate + key + dispatch
# are all working together, AND that the restored corpus is searchable.
cd ~/Desktop/Antiek
source .venv/bin/activate
python -m tools.demo.run_cold_question \
    --base-url https://api.antiek.ai \
    --question "Based on the restored corpus, name one previously-ingested document. Cite the chunk." \
    --topic-slug post-restore-smoke
```

If this returns a real citation (not `insufficient_evidence`), the
substrate is healthy AND the restored graph is queryable end-to-end.

## Cleanup

```bash
rm /tmp/antiek-restore.tar.gz
rm -rf /tmp/antiek-backup-*/
```

---

## Recovering from no Terraform state

This is the bad case — local Mac died, `terraform.tfstate` is gone.

The infrastructure still exists in Hetzner and Cloudflare — Terraform
just doesn't know about it. Two paths:

**Path A — adopt existing resources** (cleaner; preserves naming and
manual overrides):

For each resource in `main.tf`, run `terraform import` with the
resource ID from the provider's dashboard:

```bash
terraform import hcloud_ssh_key.operator <hetzner-ssh-key-id>
terraform import hcloud_server.antiek <hetzner-server-id>
terraform import cloudflare_record.api_a <zone-id>/<record-id>
# etc. for each resource
```

`terraform plan` after each import should show "0 to change" for that
resource. If it shows changes, your `.tf` files have drifted from
what's actually in the cloud — reconcile case by case.

**Path B — re-create from scratch** (simpler, loses the IP — clients
have to re-resolve DNS):

1. Delete the old VM and DNS records via the provider dashboards.
2. Run `terraform apply` to provision fresh.
3. Proceed from step 2 of this runbook to restore data.

Path B is what most operators do in practice. Path A is for when you
specifically need to preserve resource IDs (rare).

## Backup retention policy

The host never deletes remote backups. Host clock skew or compromise must not
be able to erase the last known-good recovery point. Configure retention as an
R2 bucket lifecycle rule in Cloudflare, and enable object versioning when the
account/bucket supports it. Keep periodic copies in a separately administered
store for recovery from bucket-credential compromise.

Cost trade: ~$0.015/GB/month at R2 EU. A 100MB backup × 30 days =
0.045 GB × $0.015 = $0.0007/month. Storage is not the bottleneck.
