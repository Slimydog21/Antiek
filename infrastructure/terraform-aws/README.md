# infrastructure/terraform-aws

Antiek's AWS footprint: the production host that replaces the Hetzner CCX23,
and the lane host(s) that give the compute dispatcher an Antiek-owned Linux
backend. The decision and its evidence are in
`docs/decisions/aws-production-and-agent-backbone-2026-10-07.md`; the move
itself is `infrastructure/runbooks/aws-cutover.md`; how the dispatcher uses a
lane host is `infrastructure/runbooks/lane-host.md`. The Hetzner root in
`../terraform/` is untouched and keeps its own state until the old server is
deleted.

Evidence labels below: **[M]** measured (command or file named), **[I]**
inferred from measured facts, **[A]** assumed.

## Two roots

| Root | State | Applied | Creates |
|---|---|---|---|
| `bootstrap/` | local file on the operator's Mac (gitignored) | once | S3 state bucket (versioned, AES256, public access blocked, TLS-only policy, old versions expire after 90 days); EBS encryption by default; IMDSv2-only instance defaults; the whole-account monthly budget (alerts 50/80/100% actual, 100% forecast); optional cost-allocation tags |
| `.` (main) | S3, `use_lockfile = true` (S3-native lock, no DynamoDB) | per change | one VPC + one public subnet + IGW (no NAT gateway); prod EC2 + Elastic IP + encrypted gp3 data volume at `/home/antiek/.antiek`; DLM daily snapshots (keep 14); prod and lane-host budgets, the lane-host stop action; lane host(s) when `lane_host_count > 0` |

The prod and lane-host budgets live in the main root, not in `bootstrap/`,
because their filters name instance types and the stop action names instance
ids, and only the root that creates the instances knows both. A copy in
`bootstrap/` would read USD 0 forever the first time a type changed (a
vacuous gate).

## Preconditions measured on the account (2026-10-07)

Read-only calls with the `antiek` profile (`sts get-caller-identity`,
`freetier get-account-plan-state`, `ec2 describe-*`, `service-quotas
get-service-quota`, `ssm get-parameter`, `iam simulate-principal-policy`,
`ec2 run-instances --dry-run`). Nothing was created.

1. **Region is eu-north-1 (Stockholm), not eu-central-1.** The account is an
   AWS "new experience" project; `~/.aws/config` pins `region = eu-north-1`
   [M], and the project's managed SCP denies every action this code needs in
   eu-central-1: `describe-instance-type-offerings` there returns
   `UnauthorizedOperation` [M], and the policy simulator returns
   `explicitDeny` / `AllowedByOrganizations=false` for RunInstances,
   CreateVolume, CreateVpc, dlm:CreateLifecyclePolicy, s3:CreateBucket,
   ssm:PutParameter, budgets:CreateBudgetAction and the rest with
   `aws:RequestedRegion=eu-central-1`, and `allowed` for all of them in
   eu-north-1 [M]. Global services (IAM, Budgets, Cost Explorer) are allowed
   at us-east-1 [M]. m8g.xlarge, r8g.xlarge, m7i.xlarge and r8g.large are
   offered in all three eu-north-1 AZs [M]. Both roots refuse any other
   Region at plan time.
2. **The project is on the Free plan** (`accountPlanType: FREE`, expires
   2027-04-07) [M]. Upgrade it to the Paid plan in AWS Settings before any
   production resource exists: a Free-plan account is time-limited, and
   AWS's documented behaviour for one that is not upgraded by expiry is
   closure [A: AWS docs not re-read today]. `run-instances --dry-run`
   succeeds for m8g.xlarge and r8g.xlarge [M], but a dry run checks IAM
   only, so whether the Free plan would refuse these types at launch is
   unverified.
3. **Running On-Demand Standard vCPU quota (L-1216C47A) is 5; the Spot
   quota (L-34B43A08) is 5** [M]. Prod (4 vCPU) fits; prod plus one lane
   host (8) does not. Before `lane_host_count = 1`:
   `aws service-quotas request-service-quota-increase --profile antiek --region eu-north-1 --service-code ec2 --quota-code L-1216C47A --desired-value 16`.
   The main root reads both quotas at plan time and refuses a plan that
   exceeds them (`tests/offline.tftest.hcl` run `quota_too_small_is_refused`).
4. **Cost Explorer is not available yet**: `ce list-cost-allocation-tags`
   returns `AccessDeniedException` [M]. Leave
   `activate_cost_allocation_tags = false`; no budget depends on tags.
5. **Do not set a project spend limit below the expected bill.** A project
   spend limit *pauses the whole project* when exceeded (AWS starter rules
   for the new experience [M, `scratchpad/aws-toolkit/aws-starter-rules.md`]),
   which is a production outage. The lane-host cap is the Budgets stop
   action below, which touches lane hosts only.
6. Account defaults today: EBS encryption by default **off**, IMDS defaults
   unset (`ManagedBy: account`) [M]. `bootstrap/` turns both on.

## Apply order

Credentials: `aws login --profile antiek` (browser; 12-hour credentials),
then `export AWS_PROFILE=antiek`. Terraform >= 1.10 (tested with 1.13.4,
provider hashicorp/aws 6.67.0 pinned by `.terraform.lock.hcl`).

```bash
# 0. Paid plan (precondition 2). Quota increase if a lane host is planned (precondition 3).

# 1. Account guardrails + state bucket (local state, once)
cd infrastructure/terraform-aws/bootstrap
cp terraform.tfvars.example terraform.tfvars        # alert_email
terraform init && terraform apply
terraform output -raw backend_hcl > ../backend.hcl  # gitignored

# 2. Main root: network, prod host, data volume, snapshots, budgets
cd ..
cat > terraform.tfvars <<'EOF'                      # gitignored
alert_email          = "..."
ssh_ingress_cidrs    = ["0.0.0.0/0"]                # parity with today; see Hardening
root_authorized_keys = [
  "ssh-ed25519 AAAA... antiek-operator@Faisals-Mac-mini.local",
  "ssh-ed25519 AAAA... github-actions-deploy@antiek",
]
EOF
terraform init -backend-config=backend.hcl
terraform plan -out tfplan && terraform apply tfplan

# 3. infrastructure/runbooks/aws-cutover.md (the host is born HELD)

# 4. Later, a lane host: Tailscale key into SSM, then lane_host_count = 1
aws ssm put-parameter --region eu-north-1 --type SecureString \
  --name /antiek/lane-host/tailscale-authkey --value file://tskey.txt   # file://, so the key is not in argv
#   tfvars: lane_host_count = 1, lane_host_dispatcher_authorized_keys = ["ssh-ed25519 ... compute@mini"]
terraform plan -out tfplan && terraform apply tfplan
```

## Operator inputs

| Variable | Root | What | Secret? |
|---|---|---|---|
| `alert_email` | both | Budgets alert recipient | no |
| `ssh_ingress_cidrs` | main | IPv4 CIDRs for tcp/22 on prod | no |
| `root_authorized_keys` | main | operator + GitHub deploy **public** keys, root on prod | no (public keys) |
| `lane_host_count` | main | 0 (default), 1 or 2 | no |
| `lane_host_dispatcher_authorized_keys` | main | the Mini dispatcher's **public** key for `lanes@` | no |
| `tailscale_authkey_param` | main | the *name* of an SSM SecureString | no; the key itself never enters Terraform |
| `prod_arch` | main | `arm64` (default) or `x86_64` | no |

Nothing secret is a Terraform variable. Runtime secrets stay where they are
today: `/etc/antiek/secrets.env` on the host, the tunnel credential in
`cloudflared-creds.yml`, R2 credentials in `r2-creds.yml`, all delivered by
Ansible or copied in the cutover window.

## What the instances get at first boot

Everything above the OS stays Ansible's job, exactly as on Hetzner. cloud-init
does only what must exist before Ansible connects or before a service may
start.

**Prod** (`prod.tf`): root SSH with exactly `root_authorized_keys` (Ubuntu AMIs
disable root; the deploy contract is `ansible_user=root`), password and
keyboard-interactive auth off; the data volume found by
`/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_<volume id without hyphen>`,
ext4 on first use only, mounted at exactly `/home/antiek/.antiek` with
`nofail`, the mountpoint made immutable before mounting so a boot without the
volume cannot write a second state tree onto the root disk;
`RequiresMountsFor=` drop-ins for the six state-dir units;
`/etc/caddy/origin-tls.d/internal.caddy` (`tls internal`); and the
**STAGING_HOLD**: while `/etc/antiek/STAGING_HOLD` exists, `cloudflared` and
every background consumer (continuous research, arXiv sync, backup,
backup-freshness, health probe) are skipped by `ConditionPathExists=!`, so a
fresh host cannot serve the tunnel, upload a backup, sync arXiv or page
anyone. `antiek.service` itself is not held, so the API can be rehearsed on
loopback.

The path is exact because TurboPuffer's servable pointer hashes the resolved
DuckDB path (`substrate/graph/retrieval_adapters/turbopuffer.py`); a symlink or
another mountpoint silently turns the default search mount off.

**Lane host** (`lane_host.tf`): account `lanes` (no sudo) with the dispatcher's
key restricted to Tailscale source addresses; root has no SSH login (SSM
Session Manager is break-glass); `PermitRootLogin no`, `AllowUsers lanes`;
data volume at `/srv/lanes`; lingering user manager with memory/pids/cpu
delegated; `~lanes/.config/systemd/user/lanes.slice` (MemoryHigh 24G,
MemoryMax 26G, TasksMax 12288) under a root-owned `user-.slice` ceiling of
28G; ufw admitting only `tailscale0:22`; Tailscale joined with an auth key
read from SSM at boot into a 0600 file under `/run`; `lanes-idle-stop.timer`
(power off after 60 idle minutes). No Antiek code or credential. Per-node
provider keys and prime-agent are installed later (`lane-host.md`).

## Cost (USD per month, 730 h, eu-north-1)

Prices [M] from AWS's public price files, read 2026-10-07: EC2 on-demand
`b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/EU%20(Stockholm)/Linux/index.json`
(published 2026-10-06T17:24Z); Savings Plans
`pricing.us-east-1.amazonaws.com/savingsPlan/v1.0/aws/AWSComputeSavingsPlan/20261006182900/eu-north-1/index.json`
(EC2 Instance SP, 1-year, No Upfront); EBS
`.../meteredUnitMaps/ec2/USD/current/ebs.json` (gp3 USD 0.0836/GB-month,
snapshots USD 0.0475/GB-month); VPC `.../vpc/USD/current/vpc.json` (public
IPv4 USD 0.005/h); data transfer `.../datatransfer/USD/current/datatransfer.json`
(internet egress USD 0.09/GB after the free 100 GB/month).

| Line | $/h on-demand | On-demand | 1-yr EC2 Instance SP |
|---|---|---|---|
| **Prod m8g.xlarge** (4 vCPU / 16 GiB, Graviton4) | 0.19076 | 139.25 | 92.12 |
| Prod m7i.xlarge (x86 fallback) | 0.2142 | 156.37 | 103.43 |
| Prod r8g.large (2 / 16, right-size candidate) | 0.12529 | 91.46 | 60.20 |
| Prod EBS: 60 GiB root + 120 GiB data, gp3 baseline | | 15.05 | 15.05 |
| Prod Elastic IP | | 3.65 | 3.65 |
| Prod DLM snapshots, 14 dailies (incremental; ~1 to ~8) [I] | | 1-8 | 1-8 |
| Prod egress: measured 13-20 GB/month (critic §0.2), inside the free 100 GB | | ~0 | ~0 |
| **Prod all-in, m8g.xlarge** | | **~159-166** | **~112-119** |
| **Lane host r8g.xlarge** (4 / 32 GiB) | 0.25058 | 182.92 | 120.39 |
| Lane host EBS: 30 GiB root + 150 GiB data | | 15.05 | 15.05 |
| Lane host public IPv4 (only while running) | | 3.65 | 3.65 |
| **Lane host all-in, 24x7** | | **201.62** | **139.09** |
| per lane-month at 24 lanes | | 8.40 | 5.80 |
| Lane host at 50% / 25% uptime (idle stop), on-demand | | 108.33 / 61.69 | n/a |

Reading it:

- The lane host's instance-hours are capped at USD 250/month by the budget
  action (operator approval, 2026-10-07); 24x7 on-demand is USD 182.92, so
  the cap is a backstop. A Savings Plan bills the commitment whether the host
  runs or not, so it pays only for a host that is busy most of the month.
- Buy no Savings Plan before 30 days of measured prod CPU/RAM on AWS. An
  EC2 Instance SP is locked to family and Region; a Compute SP is portable.
- Hetzner today: the CCX23 is grandfathered at about USD 37/month, and any
  rebuild, resize or new order is USD 101.49 (critic §0.1, market-hosting
  §2.1). Prod on AWS on-demand is ~4.3x the grandfathered box and ~1.6x a
  Hetzner rebuild; on a 1-year plan ~1.1-1.2x a rebuild.
- The 10-07 plan priced eu-central-1 (market-hosting §2.2: m8g.xlarge
  USD 0.21508/h, r8g.large 0.14212/h). eu-north-1 is ~11% cheaper for the
  same types [M].
- Metered alternatives per right-sized lane-month (market-sandboxes): Prime
  ~USD 24.5 at the launch rate (unpriced after 2026-12-22), Modal Sandbox
  ~USD 30.5 (Sandboxes bill 3x Function rates).

## Switching architecture (the arm64 fallback)

`prod_arch` picks the instance type and the Ubuntu AMI. The instance ignores
later AMI changes on purpose, so flipping `prod_arch` on a running host does
not quietly replace it; an in-place type change across architectures is also
impossible (an arm64 AMI cannot boot on m7i). Switching is a deliberate
rebuild, and the state survives it because it lives on the data volume:

1. Stop Antiek on the host (`systemctl stop antiek` and the consumers, as a
   deploy does), so the DuckDB file is closed.
2. `aws ec2 modify-instance-attribute --no-disable-api-termination` and
   `--no-disable-api-stop` on the prod instance.
3. Set `prod_arch = "x86_64"`, then
   `terraform apply -replace=aws_instance.prod`. The volume attachment
   detaches only from a stopped instance (`stop_instance_before_detaching`);
   the volume itself is `prevent_destroy` and is reattached to the new
   instance, whose cloud-init finds the existing ext4 and mounts it as-is.
4. `setup.yml`, then a deploy of the same SHA (the new host is born HELD
   again; release the hold as in the cutover runbook). The Elastic IP moves
   with the replacement, so `ANTIEK_PROD_HOST` stays; the host key changes,
   so `ANTIEK_PROD_KNOWN_HOSTS` must be updated.

## Security posture and the hardening path

- Inbound on prod: tcp/22 from `ssh_ingress_cidrs`, nothing else, ever; the
  API arrives through the outbound Cloudflare Tunnel. Inbound on a lane host:
  nothing. The tests in `tests/test_terraform_aws_invariants.py` fail on any
  80/443 rule or any lane-host ingress.
- Why 22 is open to the world on day one: the deploy workflow SSHes as root
  from GitHub-hosted runners, and `api.github.com/meta` listed 5,508 IPv4
  `actions` CIDRs on 2026-10-07, against a default limit of 60 inbound rules
  per security group, so the runners cannot be allow-listed. This is parity
  with the Hetzner box, whose ufw admits 22 from anywhere.
- Path off it, in order: (1) deploy over SSM instead of SSH: a GitHub OIDC
  role allowed `ssm:StartSession` on the prod instance only (the instance
  profile already carries `AmazonSSMManagedInstanceCore`), with Ansible's
  `community.aws.aws_ssm` connection or an SSH-over-SSM ProxyCommand;
  (2) operator access through Session Manager or Tailscale;
  (3) `ssh_ingress_cidrs = []`. Step 1 edits `.github/workflows/deploy_backend.yml`,
  which another lane owns.
- IMDSv2 only, hop limit 1, on every instance and as the account default.
  Termination and stop protection on prod; neither on lane hosts (the budget
  action and idle stop must be able to stop them).
- IAM: prod gets `AmazonSSMManagedInstanceCore` only. The lane host adds
  `ssm:GetParameter` on one parameter. The budget-action role may stop only
  instances tagged `Role=lane-host`.

## Verification (offline)

```bash
cd infrastructure/terraform-aws && terraform init -backend=false && terraform validate && terraform test
cd bootstrap && terraform init -backend=false && terraform validate && terraform test
./.venv/bin/python -m pytest tests/test_terraform_aws_invariants.py -q     # from the repo root
```

The `terraform test` suites use a mocked provider: no account, no
credentials, no API calls. They render the real cloud-config and assert on
it (mount path, held units, origin-TLS file, lane-host user and limits,
budget filters, the stop action's targets, arch and quota preconditions).
