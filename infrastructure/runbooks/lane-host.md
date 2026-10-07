# Runbook: lane hosts (the compute dispatcher's `node` backend on AWS)

**Decision:** `docs/decisions/aws-production-and-agent-backbone-2026-10-07.md` §1, §7, §8
**Infrastructure:** `infrastructure/terraform-aws/lane_host.tf` (+ `scripts/`, README)
**Dispatcher side:** `~/.agents/compute` 1.6.0: `backends.node`, policy entry
`hosts.nodes.lanes-1` and the comment above it, `bin/compute-lane-host`;
`~/offload/DECISIONS.md` D-19, `~/offload/ACTIVATION.md` §N

A lane host is Antiek-owned Linux capacity for the research tenants' agent
lanes. It is not production and runs nothing of Antiek: no code, no
credential, no `bd`. The Mac mini's `compute` dispatcher stays the control
plane; the host only executes what the dispatcher starts over SSH, through
one privileged helper.

Evidence labels: **[M]** measured, **[A]** assumed until checked on the host.

## The contract (compute owns it; Terraform installs it)

compute defines the host contract and verifies it with `compute doctor`;
`lane_host.tf` builds exactly that and re-encodes none of it. The helper is
installed byte for byte from the operator's compute checkout
(`compute_lane_host_helper`), and the instance carries its sha256 as the tag
`ComputeHelperSha256`. `tests/test_terraform_aws_invariants.py
::test_lane_host_matches_the_compute_contract` compares this root with the
compute policy wherever one with `hosts.nodes` exists.

| compute expects (`compute doctor` checks the starred rows) | The host provides at first boot |
|---|---|
| `ssh: compute@lanes-1`, `ssh -F /dev/null -i ~/.ssh/compute_lanes_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o BatchMode=yes` * | control account `compute` with the key from `lane_host_dispatcher_authorized_keys`, `from="100.64.0.0/10,fd7a:115c:a1e0::/48"`; `AllowUsers compute`; root has no SSH login |
| `sudo -n /usr/local/sbin/compute-lane-host` allowed, nothing else * | the helper root 0755 from compute's `bin/compute-lane-host`; `/etc/sudoers.d/compute-lane-host`: `compute ALL=(root) NOPASSWD: /usr/local/sbin/compute-lane-host` (visudo-checked) |
| `/etc/compute/lane-host.json` | rendered from this root's variables in the shape of `bin/compute-lane-host.example.json` |
| one system user + group `lane-<project>` per tenant; control account in each group and in `systemd-journal` * | `lane-solcoa`, `lane-inferact`, `lane-volantis` (no shell, no home); `compute` in all of them and in `systemd-journal` |
| systemd >= 254 * | Ubuntu 24.04 (systemd 255 [A]); the bootstrap fails below 254 |
| system `lanes.slice`, MemoryMax below physical RAM * | `/etc/systemd/system/lanes.slice`: MemoryHigh 24G, MemoryMax 26G, TasksMax 12288 |
| workroot `/srv/lanes` on its own volume * ; `<project>` dirs `lane-<p>` 2770; `.records` owned by `compute` 0750 and writable by it * | 150 GiB gp3 at `/srv/lanes` (root 0755), the project dirs and `.records` as stated; not backed up (the Mini is the data of record) |
| `/etc/compute/keys/<NAME>.env`, root 0600, one per key | the directory, root 0700; the files are the operator's step below |
| a timer running `compute-lane-host sweep` every 5 min (dead man, TTLs, stop when idle after `idle_poweroff_min`) | `compute-lane-host-sweep.timer`, enabled before the host touches the network; `idle_poweroff_min = lane_host_idle_stop_minutes` (60) |
| `/usr/bin/rsync` * ; prime-agent at `/opt/prime-agent/bin/prime-agent` * | rsync from the bootstrap; prime-agent is the operator's step below |
| no instance role reachable from the control account * (IMDS security-credentials 000/404) | an nftables table rejects the metadata address for every uid but root (the role exists for the SSM agent and the boot-time key fetch, both root); lane units add `IPAddressDeny` |
| egress allowance `egress_gib_month: 100` (compute counts it) | outbound into the tailnet is denied by ufw; Tailscale does not manage DNS |

Not in compute's contract, added here: `lane-host-failsafe.timer` (below),
tmpfs `/tmp` and `/var/tmp` (a lane can write only its workdir and its
PrivateTmp, which is charged to its own memory cgroup, so lanes cannot fill
the root volume), and `ssh_deletekeys: false` so the pinned host key survives
the reprovision path.

Per-lane limits (MemoryHigh 1G, MemoryMax 2G, TasksMax 512, RuntimeMaxSec)
come from compute on each start, through the helper.

## Bring-up

Preconditions: the AWS project is on the Paid plan, the On-Demand Standard
vCPU quota is at least 8 (it was 5 on 2026-10-07; the main root refuses the
plan otherwise), and the operator's compute checkout has
`bin/compute-lane-host` (compute 1.6.0 with the system-unit helper). See
`infrastructure/terraform-aws/README.md`.

1. **Tailscale ACL.** The Mini carries no tags today (`tailscale status
   --json`: `Self.Tags` = null, 10 peers [M, 2026-10-07]), so a
   `tag:mini` rule would match nothing. Name the Mini by its address:
   ```jsonc
   "tagOwners": { "tag:compute-node": ["autogroup:admin"] },
   "hosts":     { "mini": "<the Mini's 100.x address: tailscale ip -4>/32" },
   "acls": [
     { "action": "accept", "src": ["mini"], "dst": ["tag:compute-node:22"] }
     // nothing else names tag:compute-node, as src or dst
   ]
   ```
   With the default `"*" → "*:*"` rule removed, nothing else reaches the
   node, and the node reaches nothing (also denied on the host).
   Grok peers and personal devices get no access (ACTIVATION §N4).
2. **Auth key**: tagged `tag:compute-node`, pre-approved, **single use**
   (not reusable), not ephemeral (an ephemeral node is removed while the
   host is stopped for idleness), shortest expiry that covers the apply.
   Into SSM, never into Terraform or a shell argument:
   ```bash
   aws ssm put-parameter --profile antiek --region eu-north-1 --type SecureString \
     --name /antiek/lane-host/tailscale-authkey --value file://tskey.txt
   rm tskey.txt
   ```
   The bootstrap deletes the parameter after it joins. Until then the prod
   role cannot read it (explicit Deny) and on the lane host only root can
   reach the instance role.
3. **Dispatcher key**, the file compute pins (`backends.node.ssh_identity`):
   `ssh-keygen -t ed25519 -f ~/.ssh/compute_lanes_ed25519 -C compute@mini`.
   Its *public* half goes in `lane_host_dispatcher_authorized_keys`. No
   `~/.ssh/config` stanza: compute runs ssh with `-F /dev/null`.
4. **Apply** with `lane_host_count = 1` and `availability_zone` pinned (see
   README). The plan shows one r8g.xlarge tagged `Role=lane-host` and
   `ComputeHelperSha256` = `shasum -a 256 ~/.agents/compute/bin/compute-lane-host`;
   budgets `antiek-lane-host-expected` (100.00) and `antiek-lane-host-cap`
   (221.30) with two actions; the `antiek-lane-host-wake` schedule.
5. **Watch first boot** over SSM (nothing else reaches it yet):
   `aws ssm start-session --profile antiek --region eu-north-1 --target <instance id>`, then
   `sudo cloud-init status --long; sudo tail -50 /var/log/cloud-init-output.log; ls /var/lib/antiek-lane-host/`.
   Pass: `lane-host-bootstrap: done (100.x.y.z)`, a `provisioned` file, no
   `bootstrap-failed`, and `aws ssm get-parameter --name /antiek/lane-host/tailscale-authkey`
   on the Mac returns ParameterNotFound (consumed). A failed or hung boot
   powers itself off 60 minutes after boot (`lane-host-failsafe`); to keep
   it up while debugging, `sudo systemctl stop lane-host-failsafe.timer`
   (this boot only).
6. **Pin the host key.** In the SSM session:
   `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. On the Mini:
   `ssh-keyscan -t ed25519 lanes-1 2>/dev/null | tee /tmp/lanes-1.key | ssh-keygen -lf -`;
   if the fingerprints match, `cat /tmp/lanes-1.key >> ~/.ssh/known_hosts`.
   compute connects with `StrictHostKeyChecking=yes` and never prompts.

## Host checks before `enabled: true`

Run from the Mini, with compute's own SSH options, so the check exercises the
path placement will use:

```bash
S='ssh -F /dev/null -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -i ~/.ssh/compute_lanes_ed25519 compute@lanes-1'
$S 'df -h / /srv/lanes /tmp; ls -ld /srv/lanes/* /srv/lanes/.records; systemctl is-active compute-lane-host-sweep.timer lane-host-failsafe.timer imds-root-only.service'
$S 'curl -s -m 2 -o /dev/null -w "%{http_code}\n" -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60"'
$S 'nc -zw3 <the Mini 100.x address> 22; echo "tailnet egress rc=$?"'
compute doctor
```

Pass: `/` well below full and `/tmp` a tmpfs; the project dirs `drwxrws---`
owned by `lane-<p>`, `.records` owned by `compute`; all three units active;
the metadata request prints `000` (rejected for non-root); `nc` fails
(rc 1); `compute doctor` lists every host check OK except `prime_agent`
until the step below. From any tailnet device that is not the Mini,
`nc -zw3 lanes-1 22` must fail (ACL). Then run one smoke lane through compute
(`compute run --class agent.lane --project volantis --backend node -- ...`)
and confirm its exit record lands in `/srv/lanes/.records`.

## Per-node keys and prime-agent (operator)

- Create **new** API keys for DeepSeek, Xiaomi and Z.ai, used only on this
  host, with spend limits wherever the provider supports them. Never copy
  `~/.config/ai-keys` or any Mini key file (D-19, D-36).
- Write them as root through SSM, without echoing values. In
  `aws ssm start-session ... --target <id>`, per key name:
  ```bash
  sudo bash -c 'umask 077; read -rs v; printf "%s=%s\n" DEEPSEEK_API_KEY "$v" > /etc/compute/keys/DEEPSEEK_API_KEY.env'
  ```
  (paste the value, Enter). Check by names only:
  `sudo stat -c '%U %a %n' /etc/compute/keys/*.env; sudo cut -d= -f1 /etc/compute/keys/*.env`.
  A unit loads only the keys its job names; lanes cannot read the directory.
- prime-agent: the official installer, as root, into `/opt/prime-agent`
  with the binary at `/opt/prime-agent/bin/prime-agent` (units run with
  `ProtectHome`, so nothing under `/home` is visible to a lane). The
  installer's prefix handling is unverified [A]; `compute doctor` checks the
  path. API-key providers only (ACTIVATION §N6): no Prime CLI config, no
  team or personal Prime login. A lane's `HOME` is its workdir, so its
  prime-agent configuration arrives with compute's stage-in, not as host
  state.

## Enabling it in compute

Set `enabled: true` under `hosts.nodes.lanes-1` (a policy minor bump,
operator-owned). Placement additionally needs a passing `compute doctor`
less than `doctor_max_age_h` old (`compute health` re-runs it daily). From
then on `agent.lane` prefers the host for the allowed projects (solcoa,
volantis, inferact) whose `projects.<p>.node_sync` is declared, and any
placement refusal (host stopped, PSI high, slots full, disk below 15% free,
egress at 100 GiB) falls through to the next backend. A started job never
moves between backends.

Refused on lane hosts by compute: project `antiek` (D-18/D-36),
`agent.sub` / `agent.code` and every subscription-login role (D-26),
Mini-only projects (`lch`), `--cwd`.

## Data: stage-in, stage-out, beads

- **Only declared paths cross.** `projects.<p>.node_sync.push` (inputs,
  Mini → host) and `.pull` (outputs, host → Mini), over rsync on SSH on the
  tailnet, rate-limited per policy. Results flow only host → Mini, pulled
  by the Mini.
- **Beads stay on the Mini.** The bead id is the lane key; the dispatcher is
  the only `bd` writer (under its own lock). The host has no `bd` binary and
  no `.beads` directory; a lane never writes a bead.
- **Disk.** `/srv/lanes` is scratch; the sweep purges finished workdirs on
  compute's TTLs (7 days ok, 14 failed, immediately for a no-retention
  project) and compute refuses admission below 15% free.

## Availability and cost

- **Idle stop**: the helper's sweep powers the host off after 60 minutes
  with no live lane unit, which *stops* the instance (compute and its public
  IPv4 stop billing; EBS keeps billing). There is one owner of idle poweroff;
  the failsafe above only covers boots on which that owner cannot run.
  During maintenance over SSM, `sudo systemctl stop compute-lane-host-sweep.timer`
  keeps it up until the next boot.
- **Wake**: EventBridge Scheduler starts the host daily at 05:00 UTC
  (`lane_host_wake_schedule`). A lane submitted while the host is stopped
  falls through to the Mini (compute logs `warn node_unreachable`); the
  daily wake bounds how long that lasts. Start it off-schedule with
  `aws ec2 start-instances --profile antiek --region eu-north-1 --instance-ids <id>`.
  compute never calls AWS.
- **Budgets**: `antiek-lane-host-expected` alerts at 80% and 100% of
  USD 100 actual and at 100% forecast: a host stuck running is flagged by
  mid-month. `antiek-lane-host-cap` is the operator's USD 250 on all lane
  spend, enforced on instance-hours at 250 − fixed EBS/IPv4 per host − USD 10
  egress = USD 221.30 for one host; one on-demand host cannot reach it
  (USD 186.43 in a 31-day month), so it is the backstop for a count, type or
  Spot change. At 100% it stops the hosts and attaches
  `antiek-deny-lane-host-wake` to the wake role, so the schedule cannot
  restart them. Starting a capped host by hand overrides the cap for the
  rest of the month; reverse the IAM action (Budgets console → the cap →
  Actions → Reverse) when restarting deliberately or when the month turns.
  Budgets data lags spend by up to ~8-12 h.
- **Prove the stop path once (L17)**, before relying on it: neither action
  has run against the live account, and only Budgets can assume the
  execution role (its trust names `budgets.amazonaws.com`), so the drill
  goes through Budgets itself. With the host idle, a throwaway budget that
  this month's instance-hours already exceed, and two MANUAL actions with
  the cap's role, one on the lane host and one on prod:
  ```bash
  A=<account id>; R=arn:aws:iam::$A:role/antiek-budget-stop-lane-hosts
  aws budgets create-budget --profile antiek --account-id $A --budget '{"BudgetName":"antiek-stop-drill","BudgetLimit":{"Amount":"0.01","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST","CostFilters":{"InstanceType":["r8g.xlarge"],"Region":["eu-north-1"]}}'
  for I in <lane host id> <prod id>; do
    aws budgets create-budget-action --profile antiek --account-id $A --budget-name antiek-stop-drill \
      --notification-type ACTUAL --action-type RUN_SSM_DOCUMENTS --approval-model MANUAL \
      --action-threshold ActionThresholdValue=100,ActionThresholdType=PERCENTAGE \
      --definition "{\"SsmActionDefinition\":{\"ActionSubType\":\"STOP_EC2_INSTANCES\",\"Region\":\"eu-north-1\",\"InstanceIds\":[\"$I\"]}}" \
      --execution-role-arn $R --subscribers SubscriptionType=EMAIL,Address=<alert email>
  done
  # once Budgets has refreshed (status PENDING, up to ~12 h), approve each:
  aws budgets execute-budget-action --profile antiek --account-id $A --budget-name antiek-stop-drill \
    --action-id <id> --execution-type APPROVE_BUDGET_ACTION
  aws budgets describe-budget-action-histories --profile antiek --account-id $A --budget-name antiek-stop-drill --action-id <id>
  aws budgets delete-budget --profile antiek --account-id $A --budget-name antiek-stop-drill
  ```
  Pass: the lane-host action ends in success and the instance is stopped;
  the prod action fails on authorization and prod keeps running (stop
  protection would also refuse it; the history must show the IAM denial).
  Record both histories. The cap's APPLY_IAM_POLICY action is proven the
  same way with an `IamActionDefinition` on the wake role, then reversed.
- **Egress**: provider API traffic is small; stage-out to the Mini is the
  term to watch. compute stops placing at `egress_gib_month` (100 GiB);
  the account's first 100 GB/month of internet egress is free and
  production uses ~13-20 GB of it; beyond that, USD 0.09/GB.

## Changing the host's configuration

Every input of the cloud-config (dispatcher key, slice sizes, projects, key
names, idle minutes, a new compute helper) is user data. A plan that
changes it shows `~ update in-place` on `aws_instance.lane_host[0]`: the
provider stops the instance, replaces the user data and starts it. It is
never a replacement (`user_data_replace_on_change = false`). cloud-init
does not re-run on a restart, so apply it explicitly:

1. Wait until no lane runs (`compute status`), then `terraform apply`.
2. Over SSM: `sudo cloud-init clean --logs --reboot`. The next boot re-runs
   every module with the new user data; host keys are kept
   (`ssh_deletekeys: false`), the tailnet node is already joined (no auth
   key needed), and the bootstrap is idempotent.
3. Re-run the host checks and `compute doctor`.

A **replacement** (`terraform apply -replace='aws_instance.lane_host[0]'`,
for a new AMI) needs: the old node removed in the Tailscale admin console
first (or the new one registers as `lanes-1-1`, which compute cannot reach),
a fresh single-use key in SSM, and after it `ssh-keygen -R lanes-1` and
bring-up step 6. The data volume is kept; it is scratch either way.

## Never

- Antiek code, checkouts, `secrets.env`, or any Antiek credential on a lane
  host; the production host as a lane host (D-35).
- Mini key files, subscription logins, Prime CLI config, the Modal profile.
- `bd` on the host.
- Inbound security-group rules. Reach is Tailscale only;
  `tests/test_terraform_aws_invariants.py` fails on any lane-host ingress.
