# Runbook: production cutover, Hetzner → AWS (eu-north-1)

**Decision:** `docs/decisions/aws-production-and-agent-backbone-2026-10-07.md`
**Infrastructure:** `infrastructure/terraform-aws/` (README: preconditions, apply order, cost)
**Adapted from:** the 2026-10-06 planning draft (`~/Antiek/.audit/2026-10-06-aws-migration/AWS-MIGRATION-PLAN.md` §4-§9),
corrected by the 2026-10-07 critic review and the restore rehearsal on `Antiek-v1`.

**Roles.** *Operator agent* runs the steps, holding SSH to both hosts and the
`antiek` AWS profile. *Verifier agent* runs every gate independently and
reports pass or fail, never fixes. *Faisal* gives go/no-go at G0 and T-60 and approves
the two irreversible steps (Hetzner deletion, `Antiek-v1` deletion).

**Phase C does not start without G0 (T-24h).** Phases 0 and B build and
rehearse a host that is born unable to act as production (below) and change
nothing on the Hetzner host.

## Shell variables used below

```bash
HZ=167.235.202.98                       # Hetzner prod (antiek-prod-fsn1)
AWS=$(terraform -chdir=infrastructure/terraform-aws output -raw prod_public_ip)   # from the repo root
TUNNEL=41fc328b-36ed-46c8-80b1-523db2e31eaa   # antiek-api; DNS api.antiek.ai CNAMEs to it
STATE=/home/antiek/.antiek
KEY=~/.ssh/antiek_ed25519
```

zsh does not word-split `$VAR`. Every multi-word value below is written out
or held in an array.

## Choice: move the tunnel credential, do not create a new tunnel

The 10-06 draft proposed a second tunnel plus a staging hostname
(`api-aws.antiek.ai`) behind Cloudflare Access. This runbook moves the
existing `antiek-api` credential instead, strictly sequentially:

- **No DNS or Terraform change.** `api.antiek.ai` keeps its CNAME to
  `$TUNNEL`. The Hetzner Terraform state is stale (it still holds the
  long-gone A/AAAA records; prod-topology §0.9) and an apply there is
  unsafe; a new tunnel would force exactly that change in the cutover.
- **A staging hostname would publish a second copy of production.**
  Cloudflare Access is not configured at all (no apps, no service tokens;
  critic §0.10 [M]), so `api-aws` would be an unauthenticated public API in
  front of a production-data copy, inside the `.antiek.ai` cookie domain.
  Pre-cutover checks run on the host's loopback instead, which exercises the
  same Caddy and uvicorn the tunnel will reach.
- **Rollback is the same speed either way** (stop one connector, start the
  other: seconds), and nothing about it depends on DNS propagation.
- **The risk the new-tunnel plan avoided, two connectors on one tunnel**
  (Cloudflare load-balances across replicas, which would split writes across
  two DuckDB files), is closed by structure: the AWS host is born with
  cloudflared held (`STAGING_HOLD`), Hetzner's cloudflared is stopped, its
  credential moved out of `/etc/cloudflared/` and its unit retired before the
  hold is released, and the release is one step (T+12) with a gate in front
  of it.

## Invariants for the whole procedure

1. **One connector.** cloudflared runs on at most one host, ever. Check
   before every step that touches it: `cloudflared tunnel info $TUNNEL` (on
   the Mac, which holds the account `cert.pem`) shows connectors from at
   most one origin IP.
2. **One writer.** `antiek.service` and its consumers are active on at most
   one host from T+0 onward. Hetzner's writers and its connector are made
   unstartable at T+10 ("Retiring Hetzner's units" below).
3. **The AWS host is held until T+12.** While `/etc/antiek/STAGING_HOLD`
   exists, systemd skips cloudflared, continuous research, arXiv sync,
   backup, backup-freshness and the health probe (`ConditionPathExists=!`
   drop-ins from cloud-init). A start of a held unit succeeds as a skip, so
   `setup.yml` and `deploy_atomic.yml` run unchanged.
4. **No production secrets on AWS before T+3.** Rehearsals use a throwaway
   `secrets.env` (random auth/signing values, every provider, email,
   Stripe, Exa and webhook key empty), exactly as the `Antiek-v1` rehearsal
   did. The real file arrives with the state copy, in the freeze.
5. **Never resize, rebuild or snapshot-restore the Hetzner server.** Any of
   those reprices it from USD 36.99 to USD 101.49 (Hetzner price-adjustment
   page [M]).

## Fresh-host sequence (authoritative for this host and for disaster recovery)

The 2026-10-07 restore rehearsal on `Antiek-v1` (`REHEARSAL-REPORT.md` §2, §4,
§5) measured that `disaster-recovery.md` followed step by step serves
`setup.yml`'s unpinned editable install (D4), cannot take its next atomic
deploy (D1, D2), rebuilds `secrets.env` without about 20 of its keys (D5),
and mints an empty BYOT usage ledger on first boot (D12). Any rebuilt host,
this AWS host included, is brought up in this order. Phases B and C below
are this sequence with the AWS holds and the Hetzner freeze around it.

| # | Step | Why this position |
|---|---|---|
| F0 | **Transfer artifacts in hand before the host exists:** the live `/etc/antiek/secrets.env` (46 keys on 2026-10-07; the template has 25), the tunnel credential, and the un-backed-up state set: `byok/` (master key and ciphertext together), `auth/`, `settings/`, `antiek.duckdb.research-spend.sqlite3.byot-usage.sqlite3`, `telemetry/`, `turbopuffer-shadow/`, `arxiv_oai_harvest.json`, `arxiv_oai_sync.json`, `arxiv_throttle.json`, `research*/`, `discovery_events/`, `budgets/`, `reports/` | the nightly R2 bundle holds only DuckDB, `research_events/` and `knowledge_skills/` (rehearsal §5). `secrets.env` is a transfer artifact and is never rebuilt from `secrets.env.j2` (D5) |
| F1 | Provision, then `setup.yml --skip-tags deploy_key` (plus `cloudflared` for this host before T-55) | `setup.yml` also installs a code clone at `/opt/antiek`. It is bootstrap tooling only: its venv runs the bundle gate, IMPORT and `deploy_atomic.yml`'s pre-migration CHECKPOINT. It never serves |
| F2 | `systemctl disable antiek` straight after `setup.yml` | `setup.yml` enables the unit. A reboot before F5 would start it on an empty state directory and create a fresh BYOT ledger and settings lock (D12), which a later copy must then overwrite instead of fill |
| F3 | Restore the state with antiek stopped: either the cold rsync of the old host's state directory ("Copy commands" below, the faithful path), or `disaster-recovery.md` steps 4-8 from R2 **plus** the F0 state set; then `chown -R antiek:antiek /home/antiek/.antiek`. For an R2 IMPORT, first pin the tool to the lock: `/opt/antiek/.venv/bin/pip install "duckdb==$(awk '/^name = "duckdb"$/{getline; gsub(/[^0-9.]/,""); print}' /opt/antiek/uv.lock)"` | D12: everything the app creates on first boot must already be there. D4: the rehearsal's IMPORT ran on setup's duckdb 1.5.6 against the lock's 1.5.4; it migrated cleanly [M], but nothing guarantees the next minor will |
| F4 | Install the transfer `secrets.env` (0640 root:antiek) | the deploy's health gate requires `registered_providers` non-empty, and the first start must see the real configuration |
| F5 | `deploy_atomic.yml -e antiek_target_sha=<sha>` | migrates the **restored** database with the lock-exact release venv, cuts the public path over (the setup clone moves to `/opt/antiek-releases/<sha>`, or `legacy-<sha>` when it is at the target SHA: D2), and performs the first start. If `require_green.sh` fails closed on a GitHub API fault, see "GitHub check-runs fallback (D6)" |
| F6 | Verify (loopback `/health`, `build_sha`, `duckdb_integrity_check`, an authenticated read), then `systemctl enable antiek` | F2 disabled it and `deploy_atomic.yml` starts without enabling |
| F7 | After the next successful deploy, delete the setup clone: `rm -rf /opt/antiek-releases/legacy-<sha>` (or `/opt/antiek-releases/<old sha>`) | the release pruner matches only 40-hex names, so a `legacy-` directory is kept until removed by hand; it is the rollback target only until a second release exists |

**Why `setup.yml` keeps its code clone for now.** The rehearsal's fix direction
(D4, D8, D9) is a code-free `setup.yml` with the first release made by the
deploy. `deploy_atomic.yml` cannot do that yet: its "checkpoint the quiesced
previous database before snapshot" task runs `{{ antiek_public_dir }}/.venv/bin/python`
and the snapshot copies an existing `antiek.duckdb`, so on a host with neither the
live block enters rescue, where "No previous release exists" [I, read from the
playbook]. It also always starts the service. A first-release mode (skip both
tasks when there is no previous release, and a no-start switch so a restore can
follow the build) belongs to the deploy lane; until it exists, F1-F5 is the order
that works end to end, and it is the order the rehearsal measured (restore before
the live phase, §2.4).

### GitHub check-runs fallback (D6)

`tools/deploy/require_green.sh` fails closed when GitHub answers
`commits/<sha>/check-runs` with HTTP 5xx; on 2026-10-07 it did so for every
recent main commit while githubstatus.com reported "All Systems Operational"
[M rehearsal `03-deploy-build-attempt1-gate500.log`]. A DR deploy must not wait
on that. Override only when **all** of these hold, and paste their output into
the deploy record:

```bash
SHA=<40-hex target>
gh api "repos/Slimydog21/Antiek/commits/$SHA/check-runs" -i 2>&1 | head -1    # the fault: HTTP 5xx, not a red or pending check
gh api "repos/Slimydog21/Antiek/compare/$SHA...main" --jq '.status'          # identical or behind: the SHA is on main
gh api "repos/Slimydog21/Antiek/actions/runs?head_sha=$SHA&per_page=50" \
  --jq '.workflow_runs[] | [.name, .status, .conclusion] | @tsv'             # CI and deploy-backend completed/success
```

Then rerun with `-e antiek_force_deploy=true`. A red, pending or skipped check
is never overridden this way; a 4xx is a credential problem, not an outage.
Teaching `require_green.sh` this fallback is a follow-up for its owner (below).

## Phase 0. Preconditions (days before)

| # | Check | Pass |
|---|---|---|
| P1 | AWS project on the **Paid** plan | `aws freetier get-account-plan-state --profile antiek --region us-east-1` shows `PAID` |
| P2 | No project spend limit below ~USD 500/month (a limit pauses the whole project) | AWS Settings > Billing |
| P3 | `infrastructure/terraform-aws/bootstrap` and the main root applied with `lane_host_count = 0` | `terraform output prod_public_ip` |
| P4 | Restore-rehearsal defects D1/D2 fixed on main (the `deploy_atomic.yml` hunks and `tests/test_deploy_atomic_fresh_host.py` from branch `feat/aws-backbone-infra-20261007`), or this runbook's workaround in B4 used | `git log origin/main -- tests/test_deploy_atomic_fresh_host.py` is non-empty |
| P5 | `cloudflared-creds.yml` and `r2-creds.yml` present (gitignored) in `infrastructure/ansible/`, and the tunnel credential in it is byte-identical to Hetzner's | `ssh root@$HZ sha256sum /etc/cloudflared/$TUNNEL.json` vs the Mac copy, hashes only |
| P6 | Inventory of what is about to move, names only | `ssh root@$HZ "grep -oE '^[A-Z_0-9]+=' /etc/antiek/secrets.env | sort | uniq -c"` (46 keys on 2026-10-07; the template has 25: defect D5) |
| P7 | Unit environment parity recorded: Hetzner has a hand-placed `antiek.service.d/flywheel-events.conf` no playbook renders | `ssh root@$HZ systemctl show antiek -p Environment` saved for B6 |

Open operator questions to settle before G0 (critic §6): drop the dead
`CF_ACCESS_*` and live `ANTIEK_DEV_LOGIN_TOKEN` entries during the copy, or
copy verbatim (this runbook copies verbatim); keep or drop the
`*.antiek.ai → pixie.porkbun.com` wildcard.

## Phase B. Build and rehearse the AWS host (T-3 days to T-1 day)

**B1. Confirm the host was born held and mounted.**

```bash
ssh -i $KEY root@$AWS 'findmnt /home/antiek/.antiek; ls -l /dev/disk/by-id/ | grep Elastic_Block_Store;
  test -f /etc/antiek/STAGING_HOLD && echo HELD; cat /etc/caddy/origin-tls.d/internal.caddy;
  cloud-init status --long | head -5'
```

Pass: the mount source is `nvme-Amazon_Elastic_Block_Store_<volume id>`,
`HELD` prints, the snippet ends `tls internal`, cloud-init `status: done`.

**B2. `setup.yml` without the tunnel.** From `infrastructure/ansible/`, with
`inventory.aws.ini` copied from the example *in this directory* (defect D10):

```bash
ansible-playbook -i inventory.aws.ini playbooks/setup.yml -e @r2-creds.yml --skip-tags cloudflared,deploy_key
```

The R2 credentials are the real ones (the R2 restore in B5 reads with
them); the backup units that could write with them are held. `deploy_key`
is skipped because the repository is cloned over public HTTPS and the
uploaded key would be an unneeded credential on the host (rehearsal D8).
Then `ssh -i $KEY root@$AWS systemctl disable antiek` (fresh-host step F2:
`setup.yml` enabled it, and no boot may start it before the real state is in).

**B3. Throwaway secrets.** Replace the empty template `setup.yml` placed with
a rehearsal file: `ANTIEK_AUTH_SECRET`, `ANTIEK_OPERATOR_TOKEN` and the two
signing keys set to fresh random values, `ANTIEK_EMBEDDING_PROVIDER=hash`,
every other key empty. Mode 0640 root:antiek. Keep the operator token in a
local variable for authenticated reads; delete it after the rehearsal.

**B4. First atomic deploy, pinned to the SHA Hetzner serves.**
`deploy_atomic.yml` verifies its result against public
`https://api.antiek.ai/health`, which is still Hetzner. Deploying any other
SHA makes that check fail and the play roll the AWS host back; deploying
Hetzner's SHA makes it pass *vacuously* (it reads Hetzner), so B6 is the
real check.

Defects D1/D2 (restore rehearsal): on a host where `setup.yml` cloned the
repo into `/opt/antiek`, the first atomic deploy failed (`git rev-parse` as
root on an antiek-owned clone) or refused the cutover (the clone was at the
target SHA). With P4 met, the play reads the clone with a per-task
`safe.directory` and moves a same-SHA clone to `/opt/antiek-releases/legacy-<sha>`,
so no preparation is needed. Without P4 there is no clean workaround: the
earlier advice here, moving the clone aside so the play takes its fresh-host
`ln -s` branch, leaves the pre-migration CHECKPOINT task with no venv to run
(see "Why `setup.yml` keeps its code clone"), and the live block enters
rescue [I, read from the playbook]. Wait for P4.

```bash
SHA=$(curl -s https://api.antiek.ai/health | python3 -c 'import json,sys; print(json.load(sys.stdin)["build_sha"])')
# control node: (cd ../../apps/reading && npm ci)   # the playbook builds the SPA but does not npm ci (D7)
ansible-playbook -i inventory.aws.ini playbooks/deploy_atomic.yml -e antiek_target_sha=$SHA --skip-tags cloudflared
```

`--skip-tags cloudflared` on every `deploy_atomic.yml` run before T-55: B2
skipped the tunnel role, so `/etc/cloudflared/` does not exist, and the play's
tunnel-ID lookup falls back to `cloudflared_tunnel_id`, which no group_vars
define; the UUID assert would fail the deploy. Never work around it by
passing the tunnel ID or credential: the production tunnel credential first
reaches AWS at T-55 (Invariant 4 keeps every real secret off the host until
the freeze, and STAGING_HOLD must not be the only thing between a second
connector and the tunnel).

If `require_green.sh` fails closed on a GitHub API 500 (D6), confirm
independently (`gh api repos/Slimydog21/Antiek/compare/$SHA...main`, the
Actions runs for `$SHA`) and rerun with `-e antiek_force_deploy=true`,
recording why.

**B5. Restore rehearsal from R2 (measures the DR path on arm64).** On
throwaway state B4 and B5 may run in either order; to rehearse F3-F5 exactly,
run B5 first and B4 second. Follow
`disaster-recovery.md` steps 4-8 with the *release* venv
(`/opt/antiek/.venv`), antiek stopped. Record wall-clock per step. Pass:
`tools.backup_bundle_contract` passes, IMPORT completes, 82/82 tables and
row counts match `source_manifest.json` (2,635,604 rows on 2026-10-07).

**B6. Loopback checks (the gate the vacuous public check cannot be).**

```bash
ssh -i $KEY root@$AWS 'systemctl start antiek; sleep 8
  curl -sk --resolve api.antiek.ai:443:127.0.0.1 https://api.antiek.ai/health | python3 -m json.tool | grep -E "\"(status|build_sha|duckdb_ready|duckdb_integrity_check|duckdb_wal_present|schema_version)\""
  openssl s_client -connect 127.0.0.1:443 -servername api.antiek.ai </dev/null 2>/dev/null | openssl x509 -noout -issuer -dates
  uname -m; /opt/antiek/.venv/bin/python -c "import duckdb, torch, numpy; print(duckdb.__version__, torch.__version__)"
  systemctl show antiek -p Environment'
```

Pass: `status` ok, `build_sha` = `$SHA`, DuckDB ready and integrity ok; the
certificate issuer is Caddy's local authority (`tls internal`);
`aarch64`; imports succeed; the Environment line matches P7's except the
expected secret-free differences. An authenticated read with the throwaway
token (`GET /library` → 200) proves the restored graph serves.

Also measure, for the record: schema-migrate time inside B4 against
Hetzner's last deploy log (gp3 vs local NVMe; investigate above 1.5x).

**B7. Prove the holds hold.**

```bash
ssh -i $KEY root@$AWS 'for u in antiek-continuous-research antiek-arxiv-oai-sync antiek-backup antiek-backup-freshness antiek-health-probe; do
  systemctl start $u.service; printf "%s %s\n" $u "$(systemctl show $u.service -p ConditionResult --value)"; done'
```

Pass: every line ends `no` (skipped by the hold condition).

**B8. Reset.** Stop and disable antiek; empty the state directory's contents (not the
mountpoint); delete the throwaway secrets file and the operator token. The
host waits, held, at the deployed SHA.

## Phase C. The cutover window (choose a low-traffic hour outside 02:00-05:00 UTC)

The 03:00 UTC backup, 02:15 UTC snapshot and 04:20 UTC arXiv sync must not
overlap the window.

| T | Step | Gate |
|---|---|---|
| **T-24h** | **G0: Faisal approves the window.** Then `gh workflow disable deploy_backend.yml`. Hetzner's SHA is now frozen; merges to main continue and deploy after T+20. If B4 deployed an older SHA, redeploy AWS to Hetzner's current SHA now, with `--skip-tags cloudflared` as in B4. Post the maintenance notice. | no deploy run in progress: `gh run list --workflow=deploy_backend.yml --limit 3` |
| **T-60** | **Final go from Faisal** (G0 still stands). Verifier re-runs B1 and B7 on AWS. | go recorded; B1, B7 pass |
| T-55 | Install the tunnel credential on AWS under the hold: `ansible-playbook -i inventory.aws.ini playbooks/setup.yml -e @r2-creds.yml -e @cloudflared-creds.yml --tags cloudflared`. | `systemctl show cloudflared -p ActiveState,ConditionResult` = `inactive`, `no`; `cloudflared tunnel info $TUNNEL` lists connectors from Hetzner only |
| T-50 | Hot pre-sync of everything that does not change under a running API, so the freeze copies only deltas (see "Copy commands"). | rsync exit 0 |
| T-5 | Verifier: AWS `build_sha` (loopback) = Hetzner public `build_sha`; AWS antiek stopped; state dir on AWS holds only the pre-sync. | equal; inactive |
| T-2 | Capture Hetzner's public baseline for G3: `curl -s https://api.antiek.ai/health`, and `curl -s -o /dev/null -w '%{http_code} %{content_type}\n' -H 'Accept: application/json' https://api.antiek.ai/does-not-exist`. | saved |
| **T+0** | **Freeze Hetzner.** `systemctl stop antiek-arxiv-oai-sync.timer antiek-backup.timer antiek-backup-freshness.timer antiek-health-probe.timer antiek-continuous-research.service antiek-arxiv-oai-sync.service antiek-health-probe.service antiek-backup-freshness.service`, then `systemctl stop antiek`. The API is down from here; the edge answers 502. | all inactive |
| T+1 | On Hetzner, wait for the write lock: `flock -w 30 $STATE/antiek.duckdb.write.lock true`. | lock free; no `antiek.duckdb.wal` |
| T+2 | Write the source manifest on Hetzner (file hashes + DuckDB table counts). | manifest written |
| T+3 | Final rsync Hetzner → AWS with `--delete`; copy `/etc/antiek/secrets.env`. | rsync exit 0 |
| T+6 | **G1** on AWS: `chown -R antiek:antiek $STATE`; `sha256sum -c` of the manifest; DuckDB counts identical. Spot-check the never-backed-up set exists with matching hashes: `byok/byok_master.key`, `byok/credentials.enc`, `auth/passkeys.json`, `settings/user_models.json`, `settings/tool_connections.json`, `antiek.duckdb.research-spend.sqlite3.byot-usage.sqlite3`, `telemetry/preferences.sqlite`, `turbopuffer-shadow/active.json`, `arxiv_oai_harvest.json`. | **zero mismatches** |
| T+8 | Start antiek on AWS (cloudflared still held): `systemctl enable --now antiek` (F2/B2 left it disabled; the state and `secrets.env` it needs arrived at T+3, so this is the first production start, as D12 requires). **G2**, on loopback: `status` ok; `build_sha`; `duckdb_ready`; `duckdb_integrity_check`; `registered_providers` non-empty (the real secrets arrived); `turbopuffer_active_pointer` and `turbopuffer_pointer_context_ok` true (the mount path is exact). | **all green** |
| T+10 | **Hetzner: stop the connector and make it and every writer unstartable** ("Retiring Hetzner's units"). | `cloudflared tunnel info $TUNNEL` (Mac, uses `~/.cloudflared/cert.pem`): **no connector**; public `/health` fails |
| **T+12** | **Release the hold on AWS.** `rm /etc/antiek/STAGING_HOLD && systemctl daemon-reload && systemctl start cloudflared`, then start the consumers: `systemctl start antiek-continuous-research.service antiek-backup.timer antiek-health-probe.timer antiek-backup-freshness.timer antiek-arxiv-oai-sync.timer` | `cloudflared tunnel info $TUNNEL`: connectors only from `$AWS` |
| T+14 | **G3**, public: `/health` ok with the same `build_sha`; `python3 tools/prod_parity/check.py --url https://api.antiek.ai --expected-sha $SHA`; one operator magic-link sign-in; one passkey sign-in (proves `auth/passkeys.json` arrived); one BYOK credential read (proves the master key arrived); the unknown-path probe answers as in the T-2 baseline. | **all green** |
| T+20 | **CI follows the host.** Update the three repository secrets (below); `gh workflow enable deploy_backend.yml`; when quiet, `gh workflow run deploy_backend.yml -f force=true` for the current SHA (one ~80 s restart) to prove SSH + Ansible + the gate against AWS. | deploy job green; `/health.build_sha` = target |
| T+30 | Close the window; post the all-clear. Record actual timings next to this table. | — |

Failing G1 or G2: rollback A. Failing G3: rollback A if AWS has taken no
writes, else B.

### Copy commands

Hetzner pushes to AWS directly (Falkenstein → Stockholm), authenticated by
the operator's key through agent forwarding, so no key is ever written to
either host. Pin AWS's host key on Hetzner first:

```bash
ssh-keyscan -t ed25519 $AWS > /tmp/aws_known_hosts
ssh -i $KEY root@$AWS ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub   # compare the fingerprint before trusting the scan
scp -i $KEY /tmp/aws_known_hosts root@$HZ:/root/aws_known_hosts
```

Excluded from every copy: the deploy rollback snapshots
(`antiek.duckdb.pre-atomic-*`, 4 x 1.19 GB; AWS's deploys make their own),
the stale August copies (`antiek.duckdb.precompact-*`, `.preimport-*`), the
lock sidecars (`*.write.lock`, `.write.waiters/`, `.arxiv_bulk_run.lock`),
the legacy `research_graph.duckdb*`. Each copy runs as one script on Hetzner,
fed on stdin, so nothing is re-parsed by a second shell:

```bash
# T-50 hot pre-sync: everything except the live database (the static 4.5 GB arXiv snapshot included)
ssh -A -i $KEY root@$HZ "AWS=$AWS MODE=presync bash -s" < cutover-copy.sh
# T+3 final copy, Hetzner frozen: exact mirror of the included set, plus secrets.env
ssh -A -i $KEY root@$HZ "AWS=$AWS MODE=final bash -s" < cutover-copy.sh
```

where `cutover-copy.sh` (kept in the operator's working directory for the
window, not on either host) is:

```bash
set -euo pipefail
STATE=/home/antiek/.antiek
SSHC="ssh -o UserKnownHostsFile=/root/aws_known_hosts -o StrictHostKeyChecking=yes"
EXCL=(--exclude='antiek.duckdb.pre-atomic-*' --exclude='antiek.duckdb.precompact-*'
      --exclude='antiek.duckdb.preimport-*' --exclude='*.write.lock' --exclude='.write.waiters/'
      --exclude='.arxiv_bulk_run.lock' --exclude='research_graph.duckdb*'
      --exclude='/lost+found')   # the AWS volume's own; excluded also protects it from --delete
case "$MODE" in
  presync)
    rsync -aHAX --info=stats2 "${EXCL[@]}" --exclude='antiek.duckdb' --exclude='antiek.duckdb.wal' \
      -e "$SSHC" "$STATE/" "root@$AWS:$STATE/" ;;
  final)
    if systemctl is-active --quiet antiek; then echo "antiek still active on Hetzner" >&2; exit 1; fi
    rsync -aHAX --delete --info=stats2 "${EXCL[@]}" -e "$SSHC" "$STATE/" "root@$AWS:$STATE/"
    rsync -a -e "$SSHC" /etc/antiek/secrets.env "root@$AWS:/etc/antiek/secrets.env" ;;
  *) echo "MODE must be presync or final" >&2; exit 2 ;;
esac
```

rsync running as root maps owners by name (no `--numeric-ids`), so the
files should already belong to the AWS host's `antiek`; the `chown -R
antiek:antiek` at T+6 is the DR runbook's step 8, kept because a uid
mismatch would otherwise surface only as a permission error at start.

### Manifest (T+2 on Hetzner, checked at T+6 on AWS)

`cutover-manifest.sh`, run on each host the same way
(`ssh -i $KEY root@<host> "OUT=/root/cutover bash -s" < cutover-manifest.sh`):

```bash
set -euo pipefail
cd /home/antiek/.antiek
mkdir -p "$OUT"
find . -type f ! -name '*.write.lock' ! -path './.write.waiters/*' ! -name 'antiek.duckdb.pre-atomic-*' \
  ! -name 'antiek.duckdb.precompact-*' ! -name 'antiek.duckdb.preimport-*' ! -name '.arxiv_bulk_run.lock' \
  ! -name 'research_graph.duckdb*' -print0 | sort -z | xargs -0 sha256sum > "$OUT/state.sha256"
/opt/antiek/.venv/bin/python - > "$OUT/duckdb-counts.tsv" <<'PY'
import duckdb
con = duckdb.connect("/home/antiek/.antiek/antiek.duckdb", read_only=True)
tables = con.execute(
    "select table_schema, table_name from information_schema.tables"
    " where table_type = 'BASE TABLE' order by 1, 2"
).fetchall()
for schema, name in tables:
    n = con.execute(f'select count(*) from "{schema}"."{name}"').fetchone()[0]
    print(f"{schema}.{name}\t{n}")
PY
wc -l "$OUT/state.sha256" "$OUT/duckdb-counts.tsv"
```

Copy Hetzner's two files to AWS through the Mac (`scp`). On AWS, antiek
still stopped and after the `chown`: `cd /home/antiek/.antiek && sha256sum -c --quiet /root/cutover/state.sha256`
(no output means zero mismatches), then the Python block alone with the AWS
venv, diffed against Hetzner's TSV (empty diff).

### Retiring Hetzner's units (T+10)

`systemctl mask` cannot be used here: it refuses units whose files live in
`/etc/systemd/system/`, which is where Ansible renders every Antiek unit
and where `cloudflared service install` put cloudflared's. Instead, the same
mechanism the AWS host's hold uses, plus moving the tunnel credential out of
the directory cloudflared and `deploy_atomic.yml` read it from:

```bash
ssh -i $KEY root@$HZ bash -s <<'EOF'
set -euo pipefail
systemctl disable --now cloudflared cloudflared-update.timer
mkdir -p /root/retired && mv /etc/cloudflared/*.json /root/retired/
touch /etc/antiek/RETIRED
for u in cloudflared antiek antiek-continuous-research antiek-arxiv-oai-sync antiek-backup antiek-backup-freshness antiek-health-probe; do
  mkdir -p "/etc/systemd/system/$u.service.d"
  printf '[Unit]\nConditionPathExists=!/etc/antiek/RETIRED\n' > "/etc/systemd/system/$u.service.d/95-retired.conf"
done
systemctl daemon-reload
systemctl disable antiek antiek-continuous-research antiek-arxiv-oai-sync.timer antiek-backup.timer antiek-backup-freshness.timer antiek-health-probe.timer
for u in cloudflared antiek; do systemctl start $u; printf '%s %s\n' $u "$(systemctl show $u -p ConditionResult --value)"; done
EOF
```

Pass: both lines end `no`. A stray CI deploy to Hetzner now fails at
"resolve the tunnel ID" instead of reconnecting it.

### GitHub secrets at T+20

The deploy workflow reads exactly three repository secrets (no environment
secrets, no variables [M]):

- `ANTIEK_PROD_HOST` → the Elastic IP: `gh secret set ANTIEK_PROD_HOST --body "$AWS"`.
- `ANTIEK_PROD_KNOWN_HOSTS` → AWS's host key, from the scan whose
  fingerprint was compared above: `gh secret set ANTIEK_PROD_KNOWN_HOSTS < /tmp/aws_known_hosts`.
- `ANTIEK_DEPLOY_SSH_KEY` → unchanged on the day: its public half is one of
  `root_authorized_keys`, so the existing private key already works. Rotate
  it afterwards as a separate change: new keypair, add the public half to
  `/root/.ssh/authorized_keys` on AWS (cloud-init applied it once; Terraform
  will not re-apply it), `gh secret set ANTIEK_DEPLOY_SSH_KEY < newkey`,
  run a forced deploy, then remove the old public key from the host and
  from `terraform.tfvars`.

## Rollback

**A. AWS has taken no user writes** (any time up to and including a failed
G3 when the `write_log` count on AWS still equals the T+2 manifest's):

1. AWS: `systemctl disable --now cloudflared antiek antiek-continuous-research`
   and `touch /etc/antiek/STAGING_HOLD && systemctl daemon-reload`.
   *Disable*, not just stop: `antiek.service` is not covered by the hold
   (rehearsal needs the API), and deploy_atomic enabled it, so after a
   reboot a stopped-but-enabled unit would start a second production
   instance, with the real secrets copied at T+3, beside the restored
   Hetzner writer (its startup workers write the diverged DuckDB copy). A
   later retry re-enables it through the deploy.
2. Hetzner (if T+10 ran): `rm /etc/antiek/RETIRED && mv /root/retired/*.json /etc/cloudflared/ && systemctl daemon-reload`;
   then `systemctl enable --now antiek antiek-continuous-research antiek-arxiv-oai-sync.timer antiek-backup.timer antiek-backup-freshness.timer antiek-health-probe.timer`
   and, once `cloudflared tunnel info $TUNNEL` shows no AWS connector,
   `systemctl enable --now cloudflared cloudflared-update.timer`.
3. Hetzner's state was never modified after T+0. RTO about 3 minutes.
   Re-enable the deploy workflow only if the secrets were not yet rotated.

**B. AWS has taken writes:**

1. Freeze AWS (T+0 and T+1 steps there), hold it again (A.1).
2. Manifest on AWS (T+2 commands with paths unchanged), rsync AWS → Hetzner
   with the same excludes and `--delete`, `chown`, verify on Hetzner
   (`sha256sum -c`, counts).
3. Hetzner: A.2. Revert the three GitHub secrets if T+20 ran.
4. RTO about 15-20 minutes; Phase B can rehearse it on the AWS host.

Roll back on any of, within the window or the first 24 hours: a failed gate;
`/health` not ok for 5 consecutive minutes; 5xx above 2% over 10 minutes;
`turbopuffer_hybrid_ready` false; sign-in or BYOK reads failing; the first
AWS nightly backup failing.

## After the window

**First 72 hours.** Watch: `antiek-health-probe` and
`antiek-backup-freshness` results (journald; `ANTIEK_ALERT_WEBHOOK` is empty
in the copied secrets, so nobody is paged: set it); the first two 03:00 UTC
backups land in `r2:antiek-backups/nightly/` with SHA-256 read-back OK and
`/health.backup_fresh` true; the 04:20 UTC arXiv sync (it failed daily on
Hetzner since 2026-09-27; record whether the AWS address fares differently);
the first DLM snapshot after 02:15 UTC (`aws ec2 describe-snapshots --filters Name=tag:SnapshotCreator,Values=dlm`);
Caddy's access-log 5xx rate; `journalctl -u antiek | grep -i lock` for
writer contention.

**Hetzner stays stopped for 14 days.** Its units are retired from T+10. At
T+24h power it off (`hcloud server poweroff`, or the console): it is still
billed at the legacy price, and powered off it cannot start a writer or a
connector by accident; rollback B then begins with a power-on (~1 min). Do
not resize, rebuild or restore it (Invariant 5).

**Point of no return: deleting Hetzner.** Only with Faisal's explicit
approval, and only after all of: 14 days on AWS; two consecutive good AWS
nightly backups; one restore of an AWS-made backup onto a scratch host
(B5's procedure) that passes. Deleting it gives up the legacy price; a
future Hetzner server costs USD 101.49.

**The orphan `Antiek-v1` (id 131479504, nbg1, 46.225.116.24).** It holds a
full copy of production data from the 2026-10-07 rehearsal (restored DuckDB
with account rows, 1.7 GB) on a host with password SSH on and ~55k failed
logins in its auth log. Deletion was approved in principle with the
rehearsal; **confirm with Faisal at the time of deletion**, because it is
irreversible. Before deleting, prove it is not production (name
`Antiek-v1`, IP 46.225.116.24, no `cloudflared`, `ss -ltn` shows only :22),
then `ssh root@46.225.116.24 'systemctl stop antiek caddy; rm -rf /home/antiek/.antiek'`
and delete the server in the Hetzner console. It costs ~USD 37/month until
then.

**Follow-ups owned elsewhere (not in this runbook's scope):** the trust-centre
processor list (Hetzner → AWS) ships with the cutover release; `CLAUDE.md`
"What's running on prod"; `disaster-recovery.md` steps 1-3 and 10-11 rewritten
for AWS (defect D13); D5 (every prod key name in `secrets.env.j2`, and on AWS
the file delivered from SSM Parameter Store/KMS instead of copied); D7 (build
the SPA in CI as an artifact keyed by SHA and have the playbook fetch it,
`deploy_backend.yml` is another lane's); a first-release mode for
`deploy_atomic.yml` so `setup.yml` can drop its code clone (D4/D8/D9, "Why
`setup.yml` keeps its code clone"); the GitHub check-runs fallback inside
`require_green.sh` (D6); deploys moved off public SSH (terraform-aws README,
"Hardening path"). D1, D2 and D11 are fixed on this branch.
