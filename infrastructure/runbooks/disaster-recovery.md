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
- Marketplace hosted documents, account memberships, and opaque receipts

**What you cannot recover**:
- Anything since the last backup. Backups run nightly at 03:00 UTC, so
  worst-case data loss is ~24 hours.
- Secrets — the `secrets.env` is deliberately not backed up. You
  re-populate it manually with `sudoedit` (or from your 1Password / etc.).

**Recovery Time Objective (RTO)**: ~30 minutes if R2 backups are
accessible and you're following this runbook.

**Recovery Point Objective (RPO)**: 24 hours (nightly backups). If
this is unacceptable, change the cron schedule in
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
enabled, backup cron registered, but no state yet and no secrets.

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
set -euo pipefail
RESTORE_ROOT=$(mktemp -d /tmp/antiek-restore.XXXXXX)
tar -xzf /tmp/antiek-restore.tar.gz -C "${RESTORE_ROOT}"
mapfile -t RESTORE_DIRS < <(
    find "${RESTORE_ROOT}" -mindepth 1 -maxdepth 1 \
        -type d -name 'antiek-backup-*' -print
)
if [[ "${#RESTORE_DIRS[@]}" -ne 1 ]]; then
    echo "Expected exactly one backup directory; found ${#RESTORE_DIRS[@]}" >&2
    exit 1
fi
RESTORE_DIR=${RESTORE_DIRS[0]}
printf '%s\n' "${RESTORE_DIR}" > /tmp/antiek-restore-dir
ls -la "${RESTORE_DIR}"
# Expected: duckdb/  marketplace-host.sqlite3  research_events/  knowledge_skills/
# marketplace-host.sqlite3 is absent in backups created before its rollout.
```

## Step 6: Stop the substrate and restore file-backed state

Stop the service before replacing state. Event logs and knowledge skills are
directory copies. The marketplace database in the archive is already an
online-consistent SQLite snapshot; restore it as a single mode-0600 file.

```bash
set -euo pipefail
RESTORE_DIR=$(</tmp/antiek-restore-dir)
[[ -d "${RESTORE_DIR}" ]]
systemctl stop antiek
if systemctl is-active --quiet antiek; then
    echo "antiek service is still active; refusing to replace state" >&2
    exit 1
fi

# Replace directory-backed state exactly, never overlay it. Preserve the prior
# directories by rename so rollback remains possible without mixing generations.
# Current backups always contain both directories, including empty generations.
# For a historical archive that omitted a genuinely nonexistent directory, the
# operator must explicitly export ALLOW_LEGACY_EMPTY_DIRS=1 before this block.
ALLOW_LEGACY_EMPTY_DIRS=${ALLOW_LEGACY_EMPTY_DIRS:-0}
for NAME in research_events knowledge_skills; do
    if [[ ! -d "${RESTORE_DIR}/${NAME}" ]]; then
        if [[ "${ALLOW_LEGACY_EMPTY_DIRS}" != 1 ]]; then
            echo "Backup is missing ${NAME}; refusing an implicit empty restore" >&2
            exit 1
        fi
        mkdir -p "${RESTORE_DIR}/${NAME}"
    fi
done

RESTORE_STAMP=$(date -u +%Y%m%dT%H%M%SZ)-$$
for NAME in research_events knowledge_skills; do
    TARGET="/home/antiek/.antiek/${NAME}"
    if [[ -e "${TARGET}" ]]; then
        mv "${TARGET}" "${TARGET}.pre-restore-${RESTORE_STAMP}"
    fi
    install -d -o antiek -g antiek -m 0700 "${TARGET}"
    if [[ -d "${RESTORE_DIR}/${NAME}" ]]; then
        sudo -u antiek rsync -a "${RESTORE_DIR}/${NAME}/" "${TARGET}/"
    fi
done

MARKETPLACE_RESTORE_TMP=/home/antiek/.antiek/.marketplace-host.restore.sqlite3
MARKETPLACE_RESTORE_ABSENT=/home/antiek/.antiek/.marketplace-host.restore.absent
rm -f "${MARKETPLACE_RESTORE_TMP}" \
    "${MARKETPLACE_RESTORE_TMP}-wal" \
    "${MARKETPLACE_RESTORE_TMP}-shm" \
    "${MARKETPLACE_RESTORE_TMP}-journal" \
    "${MARKETPLACE_RESTORE_ABSENT}"

# Stage marketplace state when present (older archives do not contain it).
# Clearing the staging name above is unconditional, so a historical archive
# cannot accidentally consume residue from an earlier failed restore.
# Do not overwrite the current database until this copy has been validated.
if [[ -f "${RESTORE_DIR}/marketplace-host.sqlite3" ]]; then
    install -o antiek -g antiek -m 0600 \
        "${RESTORE_DIR}/marketplace-host.sqlite3" \
        "${MARKETPLACE_RESTORE_TMP}"
else
    touch "${MARKETPLACE_RESTORE_ABSENT}"
fi
```

## Step 7 — Restore the DuckDB graph

The backup is a directory of Parquet shards + a `load.sql` script
(produced by DuckDB's `EXPORT DATABASE`). Reconstitute with `IMPORT
DATABASE`:

```bash
RESTORE_DIR=$(</tmp/antiek-restore-dir)
[[ -d "${RESTORE_DIR}/duckdb" ]]

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

Validate the staged marketplace snapshot before replacing the current file.
The verifier checks version, tables, column constraints, foreign keys, required
indexes, schema objects, `quick_check`, and `foreign_key_check`. Before either
replacement or intentional absence, hard-link the current main file and all
SQLite sidecars into a timestamped rollback directory. Remove live sidecars,
then atomically rename the validated staged snapshot over the live main path.
For a historical archive with no marketplace state, remove the live generation
after preserving it so startup creates a fresh empty store rather than a hybrid.

```bash
MARKETPLACE_DB=/home/antiek/.antiek/marketplace-host.sqlite3
MARKETPLACE_RESTORE_TMP=/home/antiek/.antiek/.marketplace-host.restore.sqlite3
MARKETPLACE_RESTORE_ABSENT=/home/antiek/.antiek/.marketplace-host.restore.absent
set -euo pipefail

MARKETPLACE_OUTCOMES=0
if [[ -f "${MARKETPLACE_RESTORE_TMP}" ]]; then
    MARKETPLACE_OUTCOMES=$((MARKETPLACE_OUTCOMES + 1))
fi
if [[ -f "${MARKETPLACE_RESTORE_ABSENT}" ]]; then
    MARKETPLACE_OUTCOMES=$((MARKETPLACE_OUTCOMES + 1))
fi
if [[ "${MARKETPLACE_OUTCOMES}" -ne 1 ]]; then
    echo "Expected exactly one marketplace restore outcome" >&2
    exit 1
fi

preserve_marketplace_state() {
    if [[ ! -e "${MARKETPLACE_DB}" \
          && ! -e "${MARKETPLACE_DB}-wal" \
          && ! -e "${MARKETPLACE_DB}-shm" \
          && ! -e "${MARKETPLACE_DB}-journal" ]]; then
        return
    fi
    RESTORE_STAMP=$(date -u +%Y%m%dT%H%M%SZ)-$$
    PREVIOUS_DIR="${MARKETPLACE_DB}.pre-restore-${RESTORE_STAMP}"
    install -d -o antiek -g antiek -m 0700 "${PREVIOUS_DIR}"
    for CURRENT in \
        "${MARKETPLACE_DB}" \
        "${MARKETPLACE_DB}-wal" \
        "${MARKETPLACE_DB}-shm" \
        "${MARKETPLACE_DB}-journal"; do
        if [[ -e "${CURRENT}" ]]; then
            ln "${CURRENT}" "${PREVIOUS_DIR}/$(basename "${CURRENT}")"
        fi
    done
}

if [[ -f "${MARKETPLACE_RESTORE_TMP}" ]]; then
    cd /opt/antiek
    sudo -u antiek .venv/bin/python3 -c "
from pathlib import Path
from substrate.marketplace_host import verify_sqlite_host_store
p = Path('/home/antiek/.antiek/.marketplace-host.restore.sqlite3')
verify_sqlite_host_store(p)
print('staged marketplace restore verified')
"
    rm -f "${MARKETPLACE_RESTORE_TMP}-wal" \
        "${MARKETPLACE_RESTORE_TMP}-shm" \
        "${MARKETPLACE_RESTORE_TMP}-journal"
    preserve_marketplace_state
    rm -f "${MARKETPLACE_DB}-wal" \
        "${MARKETPLACE_DB}-shm" \
        "${MARKETPLACE_DB}-journal"
    mv "${MARKETPLACE_RESTORE_TMP}" "${MARKETPLACE_DB}"
    chown antiek:antiek "${MARKETPLACE_DB}"
    chmod 0600 "${MARKETPLACE_DB}"
elif [[ -f "${MARKETPLACE_RESTORE_ABSENT}" ]]; then
    preserve_marketplace_state
    rm -f "${MARKETPLACE_DB}" \
        "${MARKETPLACE_DB}-wal" \
        "${MARKETPLACE_DB}-shm" \
        "${MARKETPLACE_DB}-journal"
fi
rm -f "${MARKETPLACE_RESTORE_TMP}-wal" \
    "${MARKETPLACE_RESTORE_TMP}-shm" \
    "${MARKETPLACE_RESTORE_TMP}-journal" \
    "${MARKETPLACE_RESTORE_ABSENT}"
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
RESTORE_DIR=$(</tmp/antiek-restore-dir)
RESTORE_ROOT=$(dirname "${RESTORE_DIR}")
if [[ "${RESTORE_ROOT}" != /tmp/antiek-restore.* ]]; then
    echo "Refusing unexpected cleanup path: ${RESTORE_ROOT}" >&2
    exit 1
fi
rm -rf "${RESTORE_ROOT}"
rm -f /tmp/antiek-restore-dir
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

The backup script keeps the last 14 daily backups in R2 (configurable
via `backup_retention_days` in `infrastructure/ansible/group_vars/all.yml`).
Beyond 14 days, backups are deleted. If you need longer retention:

- Increase `backup_retention_days` and re-run setup.yml (the backup
  script template gets re-rendered).
- Or manually pull periodic backups out of R2 to durable local storage
  (Mac Time Machine, etc.) — at most weekly is plenty given the
  substrate's growth rate.

Cost trade: ~$0.015/GB/month at R2 EU. A 100MB backup × 30 days =
0.045 GB × $0.015 = $0.0007/month. Storage is not the bottleneck.
