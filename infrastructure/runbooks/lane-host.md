# Runbook: lane hosts (the compute dispatcher's `node` backend on AWS)

**Decision:** `docs/decisions/aws-production-and-agent-backbone-2026-10-07.md` §1, §7, §8
**Infrastructure:** `infrastructure/terraform-aws/lane_host.tf` (+ `scripts/`, README)
**Dispatcher side:** `~/.agents/compute` 1.6.0, policy entry `hosts.nodes.lanes-eun1-1`,
`~/offload/DECISIONS.md` D-19, `~/offload/ACTIVATION.md` §N

A lane host is Antiek-owned Linux capacity for the research tenants' agent
lanes. It is not production and runs nothing of Antiek: no code, no
credential, no `bd`. The Mac mini's `compute` dispatcher stays the control
plane; the host only executes what the dispatcher starts over SSH.

## The contract (what Terraform builds, what compute 1.6.0 expects)

| compute 1.6.0 expects | The host provides (first boot) |
|---|---|
| `ssh: lanes@lanes-eun1-1`, BatchMode, key-only | account `lanes`, no sudo; the dispatcher key from `lane_host_dispatcher_authorized_keys` with `from="100.64.0.0/10,fd7a:115c:a1e0::/48"`; `AllowUsers lanes`; root has no SSH login |
| Tailscale name `lanes-eun1-1`, ACL Mini → `tag:compute-node:22` only | hostname and Tailscale name from `lane_host_name_prefix`; joined with `--advertise-tags=tag:compute-node`; SG with no ingress; ufw admits only `tailscale0:22` |
| `systemd-run --user --unit=lane-<project>-<lane>__<sha8> --slice=lanes.slice …` (systemd >= 254 for `--expand-environment`) | Ubuntu 24.04 (systemd 255 [A until checked on the host]); lingering user manager; memory/pids/cpu delegated (`user@.service.d/50-lanes-delegate.conf`; the bootstrap fails if they are missing) |
| aggregate `lanes.slice` MemoryMax ~26G | `~lanes/.config/systemd/user/lanes.slice`: MemoryHigh 24G, MemoryMax 26G, TasksMax 12288; plus a root-owned `user-.slice` MemoryMax 28G the lanes account cannot raise |
| `workroot: /srv/lanes`, lanes at `<workroot>/<project>/<lane>__<sha8>` | 150 GiB gp3 volume mounted at `/srv/lanes`, owned by lanes; not backed up (the Mini is the data of record) |
| `key_file: /home/lanes/.config/compute/keys.env`, mode 600 | the directory exists (0700); the file is the operator's step below |
| `prime_agent: /home/lanes/.local/bin/prime-agent` | the operator's step below |
| GNU rsync on the host | installed by the bootstrap |

Per-lane limits (MemoryHigh 1G, MemoryMax 2G, TasksMax 512, RuntimeMaxSec)
come from the policy on each `systemd-run`, not from the host.

## Bring-up

Preconditions: the AWS project is on the Paid plan, and the On-Demand
Standard vCPU quota is at least 8 (it was 5 on 2026-10-07; the main root
refuses the plan otherwise). See `infrastructure/terraform-aws/README.md`.

1. **Tailscale.** In the admin console: an auth key that is **tagged**
   (`tag:compute-node`), **pre-approved**, **reusable**, and **not
   ephemeral** (an ephemeral node is removed while the host is stopped for
   idleness, and the bootstrap joins only at first boot). ACLs:
   `tag:mini → tag:compute-node:22`; nothing else may reach
   `tag:compute-node`; `tag:compute-node` reaches nothing on the tailnet
   (sync is pushed and pulled by the Mini). Grok peers and personal devices
   get no access to the node (ACTIVATION §N4).
2. **The key into SSM**, never into Terraform or a shell argument:
   ```bash
   aws ssm put-parameter --profile antiek --region eu-north-1 --type SecureString \
     --name /antiek/lane-host/tailscale-authkey --value file://tskey.txt
   rm tskey.txt
   ```
3. **Dispatcher key.** On the Mini: `ssh-keygen -t ed25519 -f ~/.ssh/compute_lanes -C compute@mini`.
   Put the *public* half in `lane_host_dispatcher_authorized_keys`.
4. **Apply** with `lane_host_count = 1`. Check the plan shows one
   r8g.xlarge tagged `Role=lane-host`, the `antiek-lane-host-monthly`
   budget at 250.00 and the stop action naming that instance.
5. **Watch first boot** (SSM, since nothing else can reach it yet):
   `aws ssm start-session --profile antiek --region eu-north-1 --target <instance id>`, then
   `sudo cloud-init status --long; sudo tail -50 /var/log/cloud-init-output.log`.
   Pass: `lane-host-bootstrap: done (100.x.y.z)`.

## Host checks before `enabled: true` (compute 1.6.0 CHANGELOG)

Run from the Mini, as the dispatcher will:

```bash
H=lanes@lanes-eun1-1
ssh -i ~/.ssh/compute_lanes $H 'systemd --version | head -1
  loginctl show-user lanes -p Linger
  cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers
  systemctl --user cat lanes.slice | grep -E "Memory|Tasks"
  df -h /srv/lanes; command -v rsync; ls -ld ~/.config/compute'
ssh -i ~/.ssh/compute_lanes $H 'U=lane-smoke-check__00000000
  systemd-run --user --quiet --unit=$U --slice=lanes.slice -p MemoryMax=64M -p RuntimeMaxSec=60 \
    -p RemainAfterExit=yes --expand-environment=no /bin/sh -c "echo lane-smoke-ok"
  sleep 3; systemctl --user show $U -p Result -p ExecMainStatus -p ControlGroup
  journalctl --user -u $U -o cat --no-pager | tail -2; systemctl --user stop $U'
```

Pass: systemd >= 254; `Linger=yes`; the controllers line includes `cpu`,
`memory` and `pids`; MemoryMax=26G in the slice; the smoke unit reports
`Result=success`, `ExecMainStatus=0` and a `ControlGroup` under
`…/user@<uid>.service/lanes.slice/`, and its journal shows `lane-smoke-ok`
(read over SSH, as compute's monitor does). Then
`compute doctor` on the Mini shows the host's PSI line. From any device
that is not the Mini, `nc -zw3 lanes-eun1-1 22` must fail (ACL).

## Per-node keys and prime-agent (operator)

- Create **new** API keys for DeepSeek, Xiaomi and Z.ai, used only on this
  host, with spend limits wherever the provider supports them. Never copy
  `~/.config/ai-keys` or any Mini key file (D-19, D-36).
- Deliver them without echoing values: write `keys.env` locally with
  `KEY=value` lines (names: `DEEPSEEK_API_KEY`, `XIAOMI_API_KEY`,
  `ZAI_API_KEY`), then
  `ssh -i ~/.ssh/compute_lanes lanes@lanes-eun1-1 'umask 077; cat > ~/.config/compute/keys.env' < keys.env`
  and delete the local file. Check by names only:
  `ssh … 'stat -c %a ~/.config/compute/keys.env; cut -d= -f1 ~/.config/compute/keys.env'`.
- prime-agent: the official installer, as `lanes`, to
  `~/.local/bin/prime-agent`; `~/.prime/agent/` holds only `APPEND_SYSTEM.md`
  (copied from the Mini) and a `models.json` limited to the API-key
  providers (ACTIVATION §N6). No Prime CLI config, no team or personal Prime
  login.

## Enabling it in compute

Set `enabled: true` under `hosts.nodes.lanes-eun1-1` (a policy minor bump,
operator-owned). From then on `agent.lane` prefers the host for the allowed
projects (solcoa, volantis, inferact) whose `projects.<p>.node_sync` is
declared, and any placement refusal (host stopped, PSI high, slots full,
disk below 15% free) falls through to the next backend. A started job never
moves between backends. After 7 days of smoke lanes, add `node` to
`agent.lane` backends (ACTIVATION §N12).

What compute does on the host, per launch: one SSH round trip to start the
transient user unit (a duplicate unit name is refused, exit 3, which is
node-local dedupe); one round trip per poll (unit state, the ExecStopPost
exit record, `.DONE` tested on the host, new journal lines by cursor);
`systemctl --user stop` to cancel. Lanes run with the host's key file via
EnvironmentFile; key values never cross from the Mini.

Refused on lane hosts by compute: project `antiek` (D-18/D-36),
`agent.sub` / `agent.code` and every subscription-login role (D-26),
Mini-only projects (`lch`), `--cwd`.

## Data: stage-in, stage-out, beads

- **Only declared paths cross.** `projects.<p>.node_sync.push` (inputs,
  Mini → host) and `.pull` (outputs, host → Mini), relative to the project
  root, via rsync over SSH on the tailnet, `--bwlimit` 20000 KB/s,
  `--safe-links`. Outputs are pulled every 10 minutes and after each launch.
  Results flow only host → Mini.
- **Beads stay on the Mini.** The bead id is the lane key; the dispatcher is
  the only `bd` writer (under its own lock). The host has no `bd` binary and
  no `.beads` directory; a lane never writes a bead. Never install `bd` here.
- **Disk.** `/srv/lanes` is scratch. compute refuses admission when it is
  below 15% free. Clear finished lanes deliberately:
  `ssh lanes@lanes-eun1-1 'find /srv/lanes -mindepth 2 -maxdepth 2 -type d -mtime +7 -print'`
  first, then the same with `-exec rm -rf {} +` once the list is right.

## Egress and cost

- The **USD 250 cap is on instance-hours** (budget filtered on r8g.xlarge
  in eu-north-1; the stop action fires at 100% actual, lagging spend by up
  to ~8-12 hours). EBS (~USD 15) and egress show up only in the account
  budget.
- **Egress**: provider API traffic is small; stage-out to the Mini is the
  term to watch. The account's first 100 GB/month of internet egress is
  free and production uses ~13-20 GB of it; beyond that, USD 0.09/GB.
  compute records wire bytes on every row (`bytes_out` = host egress), so
  the month's total, taking each job's last row (rows repeat per state), is
  `jq -s 'map(select(.backend=="node" and .job)) | group_by(.job) | map(last.bytes_out // 0) | add / 1e9' ~/.agents/compute/ledger/$(date +%Y-%m).jsonl`
  (GB). Investigate above 50 GB/month: a lane pulling a corpus it should
  have been given read-only.
- **Idle stop**: no process in the lanes user's `lanes.slice` and no login
  session for 60 minutes → `poweroff`, which *stops* the instance (compute
  and its public IPv4 stop billing; EBS keeps billing). The dispatcher then
  sees the host as unreachable and falls through. Start it again with
  `aws ec2 start-instances --profile antiek --region eu-north-1 --instance-ids <id>`;
  compute never calls AWS.
- **Budget stop**: the same fall-through. Starting the host again in the
  same month overrides the cap for the rest of it; the alerts still arrive.

## Replacing or rebuilding a host

`terraform apply -replace='aws_instance.lane_host[0]'` (the data volume is
kept; it is scratch either way). Before it, remove the old node in the
Tailscale admin console so the new one gets the same name; after it, the host
key changed: `ssh-keygen -R lanes-eun1-1` on the Mini and accept the new key
once, comparing its fingerprint with the one in the SSM session
(`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`).

## Never

- Antiek code, checkouts, `secrets.env`, or any Antiek credential on a lane
  host; the production host as a lane host (D-35).
- Mini key files, subscription logins, Prime CLI config, the Modal profile.
- `bd` on the host.
- Inbound security-group rules. Reach is Tailscale only;
  `tests/test_terraform_aws_invariants.py` fails on any lane-host ingress.
