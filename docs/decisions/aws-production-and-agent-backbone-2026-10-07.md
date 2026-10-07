# Decision: production moves to AWS (eu-north-1); the agent-CPU backbone is Antiek-owned lane hosts under the compute dispatcher

**Date:** 2026-10-07 (Asia/Riyadh)
**Status:** accepted. Operator approvals of 2026-10-07: the AWS account; one
lane host with a hard cap of USD 250/month, stopped when idle; one restore
rehearsal on the orphan `Antiek-v1` and its later deletion. The cutover
itself waits for the operator's go (runbook gate G0).
**Lane:** `opus-aws-backbone-infra-20261007`
**Implements:** `infrastructure/terraform-aws/`, `infrastructure/runbooks/aws-cutover.md`,
`infrastructure/runbooks/lane-host.md`, `docs/decisions/caddy-cert-strategy-2026-10.md`
**Supersedes:** the region and sizing of the 2026-10-06 planning draft
(`~/Antiek/.audit/2026-10-06-aws-migration/AWS-MIGRATION-PLAN.md` v3), which
predates the corrections below.

Evidence labels: **[M]** measured (command or file named), **[I]** inferred
from measured facts, **[A]** assumed. "Forensics" means the nine reports and
the critic review written on 2026-10-07 for this decision (session
`a880aa51`, `scratchpad/forensics/*.md`); the numbers this record depends on
are restated here so it stands without them.

## Context

### Production today (Hetzner CCX23, fsn1)

- **Idle and small.** CPU 74-89% idle (daily averages, 8 days of `sar`);
  memory 6-10% used of 16 GiB; DuckDB file 1.19 GB; disk 2.66 MB/s average
  write at 0.17% utilisation; about 3,100 requests a day, a third of them
  probes; 76 research trajectories in total since 2026-05-17 [M,
  prod-topology §1, critic §0.3, §3.1].
- **Egress about 13-20 GB/month** (Hetzner's counter is per billing period,
  cross-checked against `sar` tx rates) [M/I, critic §0.2]. On AWS that is
  inside the free 100 GB.
- **Billed about USD 37/month, grandfathered.** Hetzner's 2026-06-15 price
  change applies to new orders and *rescales*: CCX23 USD 36.99 old,
  USD 101.49 new [M, Hetzner price-adjustment page]. Any rebuild, resize or
  disaster replacement on Hetzner costs USD 101.49 [M]. The invoice itself
  was not read [I].
- **Every deploy is downtime.** 91 restarts of `antiek.service` in 7 days,
  median 81 s, 124 minutes in total (≈98.8% availability from restarts
  alone) [M, critic §0.6]. The DuckDB single-writer stop/migrate/start shape
  causes it, and it moves with the host unchanged.
- **The rebuild path was broken until today's rehearsal measured it.** A
  host built from `setup.yml` then `deploy_atomic.yml` fails its first live
  task (D1), refuses the cutover (D2) and cannot get an origin certificate
  (D3); measured RTO 44 min 47 s with hand fixes, ~12 min projected once
  fixed [M/I, restore rehearsal 2026-10-07 on `Antiek-v1`].
- **State outside the nightly backup**: `byok/` (master key + ciphertext),
  `auth/passkeys.json`, `settings/`, two SQLite ledgers, the TurboPuffer
  pointer, arXiv cursors, `/etc/antiek/secrets.env` (46 keys), the tunnel
  credential [M, prod-topology §7, rehearsal §5].

### The agent workload (on the Mac mini, not on prod)

- Lanes are **waiting-bound** (median 1.0% CPU per prime-agent process,
  173 processes, 288% CPU in total), **RAM-bound** (0.5-1 GiB per lane; the
  two measurements disagree because both were taken under swap pressure)
  and **file-bound** [M/I, market-sandboxes §1, critic C15].
- Demand: lane-hours 10-05 to 10-07 Solcoa 79, Inferact 173, Volantis 54,
  LCH 10.5; 24 queued at a cap of 24 while the Mini sat at load 19 with
  19.2 GiB swap [M, critic §0.8, §4.4]. Prod adds ≈0.
- These tenants run under the Mini's `compute` dispatcher, which already has
  a Modal and a Prime backend, budgets, an exit-code taxonomy and a ledger.
  Its policy declares a `node` backend (D-19, adapter `ssh_systemd_run`)
  that compute 1.6.0 implements: system units started as `lane-<project>`
  by one validating root helper on a Linux host [M, compute 1.6.0 at
  `406a856` (review fixes, which replaced the user-unit design of `457ddcf`):
  `policy.yaml` `backends.node` / `hosts.nodes`, `bin/compute-lane-host`].
- **Metered sandboxes bill the wait.** Per right-sized lane-month: Prime
  ~USD 24.5 at the launch rate (no public rate after 2026-12-22), Modal
  Sandbox ~USD 30.5 (Sandboxes bill 3x Function rates; Functions are what
  D-10 priced), a packed lane host ~USD 5.8-8.4 (table in
  `infrastructure/terraform-aws/README.md`) [M prices, I lane model,
  market-sandboxes §0, §2].

### The AWS account (read-only probes with the `antiek` profile, 2026-10-07)

- It is an AWS "new experience" project pinned to **eu-north-1**. The
  managed SCP explicitly denies every action this decision needs in
  eu-central-1 (policy simulator: `explicitDeny`,
  `AllowedByOrganizations=false`; `describe-instance-type-offerings`
  returns `UnauthorizedOperation`) and allows them all in eu-north-1 [M].
- Free plan, active, expires 2027-04-07 [M]. On-Demand Standard vCPU quota
  5, Spot 5 [M]. Cost Explorer calls are denied [M]. EBS default encryption
  off, IMDS defaults unset [M].

## Decision

### 1. The agent-CPU backbone is Antiek-owned Linux lane hosts, governed by the compute dispatcher

Lane host #1 is an AWS **r8g.xlarge** (Graviton4, 4 vCPU / 32 GiB) in the
same account and VPC as production, a separate instance that is never the
production box. About 24 lanes at ≤1-2 GiB fit under a system `lanes.slice`
(MemoryMax 26G). The dispatcher on the Mini stays the control plane: it holds
the lease, admits by PSI and slots, and over SSH as the host's control
account asks compute's one privileged helper (`sudo -n
/usr/local/sbin/compute-lane-host start …`) to start one transient system
unit per lane, run as `lane-<project>` under `lanes.slice`; it collects the
terminal state from a root-written exit record. compute owns that host
contract and `compute doctor` verifies it; Terraform installs it (the helper
byte for byte from the operator's compute checkout) and re-encodes none of
it. Cost: ~USD 202/month all-in 24x7 on-demand. The approved USD 250 cap
covers all lane-host spend; AWS Budgets enforces it on instance-hours at
250 minus fixed EBS/IPv4 and an egress allowance (USD 221.30 for one host),
stopping the hosts and detaching their daily wake. The helper's sweep powers
an idle host off after 60 minutes, a daily schedule starts it again, and an
alerting budget at expected spend (USD 100) flags a host stuck running.

Why not a sandbox vendor as the backbone: lanes spend almost all their time
waiting on model APIs, and per-sandbox metering bills that wait. Packing
waiting-bound, RAM-bound lanes into one host under cgroups is 3-5x cheaper
per lane-month, gives cgroup kill-the-tree semantics and node-local dedupe
(a duplicate unit name is refused), and keeps lanes resumable from PROGRESS
files without a 24-hour session cap.

The lane host carries **no Antiek code or credential** (D-18/D-19/D-36;
compute 1.6.0 refuses project `antiek` on hosts). It holds per-node,
spend-limited provider keys the operator provisions. The tenants are the
research projects (solcoa, volantis, inferact). Antiek's own in-product
seams (`ExecutionBackend`, `RemoteExecProvider`, the unmerged
`runtime/compute_admission/` of PR #3728) are a separate system held for
the §16 amendment and ADR 0017; this decision does not touch them.

### 2. Modal and Prime stay, as tiers

- **Modal Functions**: the stateless CPU burst tier (`render.pdf`,
  `batch.cpu`), preemptible, behind the D-20 equivalence gate.
- **Prime sandboxes**: overflow and isolated execution for cloud-ok tenants,
  with idempotency keys (a duplicate Prime launch, job `b602da8ed975`, was
  measured on 2026-10-06 [M, critic C7]).
- **Modal Sandboxes are not used**: 3x the Function price and a 24-hour cap.

Neither is the backbone: both meter the wait (above), and neither suits a
long single-writer workload.

### 3. Production moves to one EC2 instance in eu-north-1

- **m8g.xlarge** (Graviton4, 4 vCPU / 16 GiB), like-for-like with the CCX23;
  **m7i.xlarge** is the x86 fallback behind one variable (`prod_arch`).
  Right-sizing to r8g.large waits for 30 days of AWS measurements.
- A separate encrypted gp3 data volume (120 GiB, baseline 3,000 IOPS /
  125 MiB/s, `prevent_destroy`) mounted at exactly `/home/antiek/.antiek`,
  found by its NVMe serial (the volume id), so the TurboPuffer pointer's
  path hash is unchanged. Daily DLM snapshots, 14 kept. R2 nightly logical
  backups stay the verified backup of record.
- Ingress unchanged: the existing Cloudflare Tunnel, whose credential moves
  to the new host in a strictly sequential cutover (no DNS change; runbook).
  No inbound 80/443, ever. tcp/22 stays open for the root-SSH deploy,
  exactly as on Hetzner, until deploys move to SSM/OIDC.
- IMDSv2 only, termination and stop protection, an instance profile with
  `AmazonSSMManagedInstanceCore` only. The host is born **held**: cloudflared
  and every background consumer stay off until the cutover deletes
  `/etc/antiek/STAGING_HOLD`.
- Origin TLS: `tls internal` (separate record).

### 4. Region: eu-north-1, because the account allows nothing else

The 10-07 plan chose eu-central-1 (Frankfurt). The account the operator
created cannot create resources there (measured above), so the decision is
eu-north-1 (Stockholm). It remains in the EU, so PR #3728's "Antiek-user jobs
require a backend declared EU" rule is satisfied; the same instance types
are offered in all three AZs; prices are ~11% lower. Latency to Gulf users
changes by little behind Cloudflare's edge [I]. Both Terraform roots refuse
any other Region at plan time; moving Region is a new decision.

### 5. ARM64 readiness: production is arm64-clean, so the default is m8g.xlarge

Method, three independent ways, all on 2026-10-07 at base `7e6366dda`:

1. a walk of `uv.lock` from the project's core dependencies plus exactly the
   extras `deploy_atomic.yml` installs (`pdf`, `urls`, `embedding`, `docs`,
   `turbopuffer_shadow`), markers evaluated for linux / cp312, each package
   checked for a wheel whose platform is `any` or `manylinux*_aarch64` at or
   below Ubuntu 24.04's glibc 2.39;
2. `uv export --frozen --no-dev` with the same extras, markers evaluated
   independently, wheels checked against the same lock entries;
3. `uv pip install --dry-run --python-platform aarch64-manylinux_2_39
   --python-version 3.12 --only-binary :all:` against the exported pins.

Result: **118 of 118 packages install from wheels on linux-aarch64**: 69
pure-Python, 49 binary `manylinux*_aarch64` (duckdb, numpy, scipy,
scikit-learn, torch 2.14.0, triton, tokenizers, safetensors, hf-xet, orjson,
uvloop, pydantic-core, pynacl, cryptography, pillow, pypdfium2, the CUDA
runtime wheels torch pulls on Linux, ...). The highest glibc any chosen wheel
needs is 2.28. No sdist-only package, no blocker. Methods 1 and 2 produce the
same 118 names; method 3 resolves and would install 118.
`tests/test_terraform_aws_invariants.py` turns method 1 into a gate for both
architectures, so a future dependency without an aarch64 wheel fails CI
rather than the first Graviton deploy.

Outside Python [M unless marked]:

| Item | arm64 status |
|---|---|
| rclone v1.75.1 (`setup.yml`) | **was amd64-only**: the zip and checksum were hard-coded. Fixed in one hunk: the build follows `ansible_architecture`; the arm64 checksum `03f25041…dff9` is from rclone's PGP-signed SHA256SUMS (good signature, key `FBF737EC…FF3B54FA`), and the downloaded zip hashes to it |
| Caddy (Cloudsmith apt, `any-version`) | `binary-arm64/Packages` lists caddy up to 2.11.7 |
| cloudflared (pkg.cloudflare.com) | `binary-arm64/Packages` lists 2026.10.0 |
| uv 0.11.15 (bootstrapped by `deploy_atomic.yml`) | aarch64 manylinux wheel resolves |
| DuckDB `vss` extension (installed at runtime) | `extensions.duckdb.org/v1.5.4/linux_arm64/vss.duckdb_extension.gz` answers 200 |
| Ubuntu packages (ocrmypdf, tesseract, poppler, build-essential) | served from ports.ubuntu.com for arm64 [I, standard archive] |
| The SPA build | runs on the GitHub runner, not the host |
| Other `amd64` / `x86_64` literals in `setup.yml`, `deploy_atomic.yml`, templates | none besides rclone |

Residual risk: nothing has run on arm64 hardware yet. The first rehearsal on
the AWS host is the proof. If it fails, the fallback is a deliberate
instance rebuild with `prod_arch = "x86_64"` (README, "Switching
architecture"); the data volume, and so the state, survives it.

### 6. DigitalOcean: not a substitute for AWS here

DigitalOcean competes with Hetzner on simplicity, not with AWS on what this
move is for. It has no Gulf or KSA region, no ARM instances, and no IAM
roles, KMS or SSM-class session access; a like-for-like 4/16 Droplet is
USD 126/month, about the same as AWS on a 1-year plan [M,
market-hosting §2.3, §5]. Its one structural advantage is pooled egress,
and production's measured egress is 13-20 GB/month. It would be a
reasonable Hetzner replacement for an operator who wanted no IAM at all; it
is the wrong stop for a backbone that pairs production with owned lane
hosts and security primitives.

### 7. Beads: the dispatcher is the only writer

`bd` 1.3.0 is installed and there are zero live workspaces [M,
memory-beads]. Embedded Dolt is single-writer and machine-local [M, bd help
and the beads-fleet skill]. So:

- a bead id **is** the compute lane key (`compute run --bead ID`);
- the dispatcher on the Mini is the only process that writes beads,
  serialised under its own flock (compute 1.6.0: `state/beads.lock`;
  admitted → `in_progress`, done → closed with the ledger reference,
  failed → blocked with a note);
- lanes and lane hosts never run `bd` (topology D). Lane hosts get no `bd`
  binary and no `.beads` directory; results return through the
  dispatcher's stage-out rsync and the dispatcher records them;
- multiple writers only through Dolt server mode on a private network,
  later, as its own decision.

### 8. What overloading the Mini taught, built into this design

| Lesson (mini-lessons) | Where it is structural here |
|---|---|
| L1 admission before create; L5 per-project caps don't sum | the dispatcher admits before any remote start; the host's system lanes.slice (root-owned, MemoryMax 26G of 32 GiB) caps the sum, not each lane |
| L2 retry must prove the prior attempt gone | node-local dedupe: a duplicate `lane-…` unit name is refused (exit 3) |
| L4 lease held by the thing doing the work | the Mini's supervising process holds the lease; the unit's ExecStopPost record is the terminal state |
| L8 TMPDIR runaway / ENOSPC | a lane unit can write only its workdir on `/srv/lanes` (ProtectSystem=strict, ProtectHome, HOME = the workdir) and its PrivateTmp, which lives on tmpfs `/tmp` and `/var/tmp` charged to its own memory cgroup; the root volume that sshd, journald and tailscaled need is not writable by lanes. (The 10-07 draft's lanes account had its HOME on the root volume.) |
| L9 storage at rest is the billing trap | snapshots capped at 14, state-bucket old versions expire after 90 days, the lane data volume is not backed up (the Mini is the data of record) |
| L11 / L21 one-shot boot work fails silently, nothing retries | the boot failsafe is armed before any step that can fail and powers off a host that is not provisioned, mounted and sweeping 60 minutes after boot; every external wait in the bootstrap is bounded; a `bootstrap-failed` marker is left for the SSM check |
| L17 vacuous gates | budgets filter on instance type, which reads from the first hour, not on a tag that reads USD 0 until activated; each budget is sized so it can fire for its failure (one prod instance cannot trip the prod budget, two do; the lane-host alert sits at expected spend, below one host's month); the stop action is tag-scoped and carries the SSM resources of AWS's own budget-action policy. It has not run against the live account: the runbook's Budgets-path drill is the bar, owed before it is relied on. The quota and AZ checks fail at plan |
| L18 low CPU with long wall time is billed waiting | the backbone is a packed host, not per-sandbox metering |
| L24 control-plane checks must not run on the overloaded host | lane-host health is PSI read over SSH by the dispatcher; budget enforcement and the daily wake are AWS-side |
| L27 a terminal-state contract | the ExecStopPost exit record plus `.DONE` tested on the node |

## Consequences

- Production cost rises from ~USD 37 to ~USD 159-166/month on-demand
  (~USD 112-119 on a 1-year EC2 Instance Savings Plan, bought only after 30
  days of measurements). Against a Hetzner rebuild (USD 101.49) that is
  1.1-1.6x. One lane host adds up to ~USD 202 at 24x7, less when idle.
- Idle stop trades offload for money. A lane submitted while the host is
  stopped falls through to the Mini (compute warns `node_unreachable`); the
  daily 05:00 UTC wake bounds that to the hours between an idle stop and the
  next wake or manual start: lanes the tenants start overnight land on the
  Mini whenever the host idled off in the evening (how often that happens
  is not measured yet; compute's `node_unreachable` warns count it). If the
  Mini's load returns, move the wake earlier or add a second one, or raise
  `idle_poweroff_min`, and accept the cost.
- The lane host keeps an instance profile, where compute's host comment asks
  for none: the SSM agent (break-glass, reprovision) and the boot-time
  Tailscale key fetch need it, both as root. The metadata service is
  rejected for every other uid, which is what `compute doctor` measures
  ("no instance role reachable" from the control account), and the key is
  single use and deleted after the join.
- The rebuild path becomes code: Terraform for the machine, cloud-init for
  the mount, root access, hold and origin-TLS declaration, Ansible for
  everything above, the cutover runbook for the state. The restore
  rehearsal's D1/D2 defects (the first atomic deploy on a `setup.yml`-fresh
  host) are worked around in the runbook, not fixed here; their owner is
  the deploy lane.
- Deploy downtime per release is unchanged (the single-writer shape moves
  as-is).
- The trust-centre processor list must change from Hetzner to AWS in the
  same release as the cutover (critic §3.1 item 9).
- Operator gates before any `terraform apply`: upgrade the project to the
  Paid plan; request the On-Demand vCPU quota increase before the lane host;
  set no project spend limit that would pause production.
- Interpretation this record relies on, for the operator to confirm: D-18's
  "Antiek credentials stay on the Mini" governs Antiek *development* on the
  compute layer, not the production host, which holds its runtime
  credentials on AWS exactly as it did on Hetzner (critic C17).

## What would change this

- **The AWS project gains eu-central-1** (advanced features) or the
  announced KSA Region reaches GA and runs cleanly for ~6 months: re-evaluate
  Region, as a new decision.
- **Arm64 fails in rehearsal**: rebuild with `prod_arch = "x86_64"`.
- **Lane demand moves into Antiek's product** (an operator §16 / ADR 0017
  ruling, PR #3728): the in-product seams get their own placement decision;
  lane hosts would need an Antiek-credential policy they do not have today.
- **A metered vendor stops billing idle wait** (per-active-CPU pricing at
  lane scale) or Prime publishes a post-launch price below a packed host:
  revisit item 2.
- **Measured lane footprint on Linux** (cgroup `memory.peak`, 24 h) differs
  from 0.5-1 GiB by more than 2x: resize the host or the slot count.

## Evidence

- Forensics 2026-10-07 (session `a880aa51` scratchpad, `forensics/`):
  `prod-topology.md`, `compute-code.md`, `agent-runtime.md`,
  `memory-beads.md` (+ `bd-help/*.txt`), `research-workloads.md`,
  `mini-lessons.md` (L1-L27), `vendor-accounts.md`, `market-sandboxes.md`,
  `market-hosting.md`, and `critic.md`, whose corrections override the
  others (Hetzner billed ~USD 37 not 101; egress 13-20 GB/month; prod
  research load ≈0; PR #3728's EU rule; 124 min/week of restarts; six DNS
  records; Cloudflare Access not configured).
- Restore rehearsal on `Antiek-v1`, 2026-10-07 (`scratchpad/rehearsal/REHEARSAL-REPORT.md`).
- Planning drafts of 2026-10-06: `~/Antiek/.audit/2026-10-06-aws-migration/AWS-MIGRATION-PLAN.md`,
  `~/Antiek/.audit/2026-10-06-compute-portability/{PROVIDER-RECOMMENDATION,HANDOFF-BACKEND,PRIME-VS-MODAL,DATA-MEMORY-ARCHITECTURE}.md`.
- Compute governance: `~/offload/DECISIONS.md` (D-18, D-19, D-35, D-36,
  D-39, D-41), `~/offload/ACTIVATION.md` §N, `~/.agents/compute/policy.yaml`,
  compute 1.6.0 CHANGELOG (node backend, beads).
- AWS price files and account probes: `infrastructure/terraform-aws/README.md`.
