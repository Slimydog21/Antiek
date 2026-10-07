# ── Placement ────────────────────────────────────────────────────────────────

variable "region" {
  description = <<-EOT
    AWS Region. Fixed to eu-north-1 (Stockholm): the operator's AWS project
    is pinned there. Measured 2026-10-07 with the `antiek` profile: the
    project's managed SCP explicitly denies every action this root needs in
    eu-central-1 (IAM policy simulator, aws:RequestedRegion=eu-central-1:
    explicitDeny, AllowedByOrganizations=false) and allows them all in
    eu-north-1. The backend block, the ADR and the cost table assume it.
  EOT
  type        = string
  default     = "eu-north-1"

  validation {
    condition     = var.region == "eu-north-1"
    error_message = "Antiek's AWS project can only create resources in eu-north-1 (docs/decisions/aws-production-and-agent-backbone-2026-10-07.md). Moving Region is a new decision, not a variable."
  }
}

variable "availability_zone" {
  description = "AZ for the single public subnet. Null derives it from the prod type alone (first AZ, sorted, offering it). Pin it in terraform.tfvars after the first apply (output availability_zone): prod, its data volume and the subnet are single-AZ and a moved AZ would plan their replacement."
  type        = string
  default     = null
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "public_subnet_cidr" {
  type    = string
  default = "10.42.1.0/24"
}

variable "enable_ipv6" {
  description = "Give the VPC, subnet and instances IPv6. Off by default: nothing needs it (ingress is the Cloudflare Tunnel; egress uses the instance's public IPv4)."
  type        = bool
  default     = false
}

# ── Production host ──────────────────────────────────────────────────────────

variable "prod_arch" {
  description = <<-EOT
    CPU architecture of the production host. arm64 (Graviton) is the default
    because the prod dependency closure is clean on linux-aarch64 (118 of 118
    packages on 2026-10-07, docs/decisions/aws-production-and-agent-backbone-2026-10-07.md
    §5; tests/test_terraform_aws_invariants.py keeps it so). x86_64 is the
    fallback; changing it on a running host is a deliberate rebuild
    (README.md, "Switching architecture").
  EOT
  type        = string
  default     = "arm64"

  validation {
    condition     = contains(["arm64", "x86_64"], var.prod_arch)
    error_message = "prod_arch must be arm64 or x86_64."
  }
}

variable "prod_instance_type" {
  description = "Null selects the like-for-like 4 vCPU / 16 GiB type for prod_arch: m8g.xlarge (arm64) or m7i.xlarge (x86_64)."
  type        = string
  default     = null
}

variable "prod_ami_id" {
  description = "Pin a specific AMI. Null resolves Canonical's current Ubuntu 24.04 LTS for prod_arch from the public SSM parameter at plan time. Either way the instance ignores later AMI changes (see prod.tf)."
  type        = string
  default     = null
}

variable "prod_hostname" {
  type    = string
  default = "antiek-prod-eun1"
}

variable "prod_root_volume_gib" {
  description = <<-EOT
    Root gp3 size. 60, not 40: measured on the Hetzner box 2026-10-07, the
    root filesystem carries ~9 GB of releases, ~5.8 GB /root/.cache, ~6.4 GB
    /home/antiek/.cache and ~2.1 GB of journal on top of the OS, and
    deploy_atomic.yml refuses to build a release with less than 12 GB free
    under /opt/antiek-releases. 40 GiB would leave no margin for that check.
  EOT
  type        = number
  default     = 60

  validation {
    condition     = var.prod_root_volume_gib >= 50
    error_message = "prod_root_volume_gib below 50 cannot hold releases + caches + the 12 GB deploy free-space floor."
  }
}

variable "prod_data_volume_gib" {
  description = "gp3 data volume mounted at /home/antiek/.antiek. Measured state dir 12 GB (1.19 GB DuckDB, ~7 GB disposable rollback snapshots, 4.5 GB optional arXiv snapshot) plus the backup job's 4x-DB scratch check."
  type        = number
  default     = 120

  validation {
    condition     = var.prod_data_volume_gib >= 40
    error_message = "prod_data_volume_gib below 40 cannot hold the state dir plus four rollback snapshots."
  }
}

variable "ssh_ingress_cidrs" {
  description = <<-EOT
    IPv4 CIDRs allowed to reach tcp/22 on the prod host. Parity with today: the
    deploy workflow SSHes as root from GitHub-hosted runners. On 2026-10-07
    api.github.com/meta listed 5,508 IPv4 `actions` CIDRs, and a security
    group holds 60 inbound rules by default, so the runners cannot be
    allow-listed and the Hetzner box allows 22 from anywhere. Setting
    ["0.0.0.0/0"] reproduces that; the hardening path (SSM / OIDC deploys,
    then an empty list) is in README.md. Port 22 is the only inbound port this
    root will ever open on prod.
  EOT
  type        = list(string)

  validation {
    condition     = alltrue([for c in var.ssh_ingress_cidrs : can(cidrhost(c, 0)) && !strcontains(c, ":")])
    error_message = "ssh_ingress_cidrs must be IPv4 CIDRs."
  }
}

variable "root_authorized_keys" {
  description = <<-EOT
    Public keys installed as /root/.ssh/authorized_keys on the prod host: the
    operator key and the GitHub Actions deploy key (ANTIEK_DEPLOY_SSH_KEY's
    public half). Root login is the existing contract: inventory.ini and the
    deploy workflow both connect as ansible_user=root, and setup.yml copies
    root's keys to the antiek user. Ubuntu AMIs disable root login, so
    cloud-init re-enables it explicitly (key-only).
  EOT
  type        = list(string)

  validation {
    condition     = length(var.root_authorized_keys) > 0 && alltrue([for k in var.root_authorized_keys : can(regex("^(ssh-ed25519|ecdsa-sha2-nistp(256|384|521)|ssh-rsa) [A-Za-z0-9+/=]+( .*)?$", k))])
    error_message = "root_authorized_keys must be one or more OpenSSH public key lines without options."
  }
}

variable "snapshot_retain_count" {
  description = "Daily EBS snapshots of the prod data volume kept by DLM. R2 nightly logical backups stay the primary, verified backup."
  type        = number
  default     = 14
}

variable "snapshot_time_utc" {
  description = "DLM daily snapshot start time (HH:MM UTC). 02:15 sits before the 03:00 backup and the 04:20 arXiv sync."
  type        = string
  default     = "02:15"
}

# ── Budgets (main-root half; the account total is in ./bootstrap) ───────────

variable "alert_email" {
  description = "Recipient for the prod and lane-host budget alerts."
  type        = string
}

variable "prod_monthly_budget_usd" {
  description = <<-EOT
    Alert-only budget on prod instance-hours. Null derives it from the prod
    type: 1.05 x the longest month (744 h) at the on-demand rate in
    local.prod_hourly_usd, rounded up (m8g.xlarge: USD 150; m7i.xlarge:
    USD 168). One instance can never reach it, so it fires only for a second
    instance of the prod type. A type change moves the filter with it; an
    instance of the old type left running shows up in the account budget.
  EOT
  type        = number
  default     = null
}

# ── Lane host (agent-CPU backbone) ───────────────────────────────────────────

variable "lane_host_count" {
  description = "Number of lane hosts. 0 until the operator turns the backbone on; the first host is approved at <= USD 250/month."
  type        = number
  default     = 0

  validation {
    condition     = var.lane_host_count >= 0 && var.lane_host_count <= 2 && floor(var.lane_host_count) == var.lane_host_count
    error_message = "lane_host_count must be 0, 1 or 2. A third host is a new budget decision."
  }
}

variable "lane_host_arch" {
  type    = string
  default = "arm64"

  validation {
    condition     = contains(["arm64", "x86_64"], var.lane_host_arch)
    error_message = "lane_host_arch must be arm64 or x86_64."
  }
}

variable "lane_host_instance_type" {
  description = "r8g.xlarge: 4 Graviton4 vCPU / 32 GiB. Lanes are RAM-bound (0.5-1 GiB each) and waiting-bound (1-5% CPU), so ~24 fit under lanes.slice."
  type        = string
  default     = "r8g.xlarge"
}

variable "lane_host_use_spot" {
  description = "Run lane hosts as persistent Spot with stop-on-interruption. Off by default: lanes resume from PROGRESS files, but an interruption mid-lane still costs work."
  type        = bool
  default     = false
}

variable "lane_host_root_volume_gib" {
  description = "Root gp3. Lanes cannot write to it: their units run ProtectSystem=strict with only their workdir writable, and /tmp and /var/tmp are tmpfs (charged to the writing lane's memory cgroup)."
  type        = number
  default     = 30
}

variable "lane_host_data_volume_gib" {
  description = "gp3 volume mounted at /srv/lanes (staged inputs + lane workdirs). Not backed up: the Mini is the data of record (ACTIVATION §N)."
  type        = number
  default     = 150
}

variable "lane_host_monthly_budget_usd" {
  description = <<-EOT
    Operator-approved cap on ALL lane-host spend (2026-10-07). The stop
    action watches instance-hours only (the Budgets filter is the instance
    type), so it fires at this cap minus every host's fixed EBS + public
    IPv4 cost and the egress allowance (budgets.tf, local.lane_host_cap_usd).
  EOT
  type        = number
  default     = 250
}

variable "lane_host_expected_monthly_usd" {
  description = <<-EOT
    What the lane host(s) are expected to cost in instance-hours with idle
    stop and the daily wake: the alerting budget. 100 is ~55% uptime of one
    r8g.xlarge (USD 182.92 at 730 h). Alerts at 80% and 100% actual and at
    100% forecast, so a host stuck running is flagged well before the cap,
    which one on-demand host cannot reach (USD 186.43 in a 31-day month).
  EOT
  type        = number
  default     = 100
}

variable "lane_host_egress_allowance_usd" {
  description = "Egress the cap reserves room for (not in the instance-type filter). compute stops placing on a host at egress_gib_month (100 GiB in policy 1.6.0), which is <= USD 9 at USD 0.09/GB."
  type        = number
  default     = 10
}

variable "lane_host_name_prefix" {
  description = "Hostname and Tailscale node name prefix; host N is <prefix>-N. Must match the compute policy entry hosts.nodes.lanes-1 (ssh: compute@lanes-1)."
  type        = string
  default     = "lanes"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,40}$", var.lane_host_name_prefix))
    error_message = "lane_host_name_prefix must be a lowercase DNS label."
  }
}

variable "lane_host_dispatcher_authorized_keys" {
  description = <<-EOT
    Public key(s) the compute dispatcher on the Mini uses for the host's
    control account (ssh compute@<host> over Tailscale; compute pins
    -i ~/.ssh/compute_lanes_ed25519). Installed for `compute` only, with a
    from= restriction to Tailscale address space; root has no SSH login on a
    lane host (break-glass is SSM Session Manager). The security group
    admits nothing inbound either way.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for k in var.lane_host_dispatcher_authorized_keys : can(regex("^(ssh-ed25519|ecdsa-sha2-nistp(256|384|521)|ssh-rsa) [A-Za-z0-9+/=]+( .*)?$", k))])
    error_message = "lane_host_dispatcher_authorized_keys must be OpenSSH public key lines without options; the from= option is added here."
  }
}

variable "lane_host_projects" {
  description = "Tenants allowed on the host (compute policy hosts.nodes.<host>.projects) and whether their finished workdirs are kept for compute-lane-host's TTLs. Each gets a system user and group lane-<project>."
  type        = map(object({ retention = bool }))
  default = {
    solcoa   = { retention = true }
    inferact = { retention = true }
    volantis = { retention = false }
  }

  validation {
    condition     = alltrue([for p in keys(var.lane_host_projects) : can(regex("^[a-z0-9][a-z0-9_-]{0,23}$", p)) && !contains(["antiek", "lch", "_default"], p)])
    error_message = "lane_host_projects: lowercase names of at most 24 characters; antiek (D-18/D-36) and Mini-only lch never run on a lane host."
  }
}

variable "lane_host_provider_keys" {
  description = "NAMES of the per-node provider keys (compute policy hosts.nodes.<host>.keys). The operator provisions each as /etc/compute/keys/<NAME>.env (root 0600); values never enter Terraform."
  type        = list(string)
  default     = ["DEEPSEEK_API_KEY", "XIAOMI_API_KEY", "ZAI_API_KEY"]

  validation {
    condition     = alltrue([for k in var.lane_host_provider_keys : can(regex("^[A-Z][A-Z0-9_]{0,63}$", k))])
    error_message = "lane_host_provider_keys are environment variable names (A-Z, 0-9, _)."
  }
}

variable "compute_lane_host_helper" {
  description = <<-EOT
    Path, on the machine running Terraform, of compute's bin/compute-lane-host
    (the one privileged helper on a lane host). compute owns it; cloud-init
    installs exactly that file root-owned at /usr/local/sbin/compute-lane-host
    and the instance carries its sha256 as a tag. Read only when
    lane_host_count > 0.
  EOT
  type        = string
  default     = "~/.agents/compute/bin/compute-lane-host"
}

variable "tailscale_authkey_param" {
  description = "Name of an SSM SecureString holding a single-use, pre-authorised, tagged Tailscale auth key. Created by the operator out of band; Terraform only references it, so the key never enters user_data or state. The bootstrap deletes it after a successful join."
  type        = string
  default     = "/antiek/lane-host/tailscale-authkey"

  validation {
    condition     = can(regex("^(/[A-Za-z0-9_.-]+){2,}$", var.tailscale_authkey_param))
    error_message = "tailscale_authkey_param must be a fully qualified SSM parameter name with at least one path level (the prod role's deny covers that path)."
  }
}

variable "tailscale_tags" {
  type    = string
  default = "tag:compute-node"
}

variable "lanes_slice_memory_high" {
  description = "lanes.slice MemoryHigh (all lanes together): reclaim pressure starts here."
  type        = string
  default     = "24G"
}

variable "lanes_slice_memory_max" {
  description = "lanes.slice MemoryMax (compute doctor: below physical RAM; 26G of 32 GiB). The OOM killer acts inside the slice, never on sshd, tailscaled or the SSM agent."
  type        = string
  default     = "26G"
}

variable "lanes_slice_tasks_max" {
  description = "lanes.slice TasksMax: 24 lanes x 512 tasks (D-19 per-lane TasksMax)."
  type        = number
  default     = 12288
}

variable "lane_host_idle_stop_minutes" {
  description = "compute-lane-host's idle_poweroff_min: its sweep powers the host off (the instance stops; EBS keeps billing, compute does not) after this many minutes with no live lane unit. 0 disables."
  type        = number
  default     = 60
}

variable "lane_host_failsafe_minutes" {
  description = "Minutes after every boot at which the host powers itself off unless it is provisioned, its workroot is mounted and the sweep timer is active. Covers a failed or hung first boot, which the sweep cannot (it may never have been installed)."
  type        = number
  default     = 60

  validation {
    condition     = var.lane_host_failsafe_minutes >= 30
    error_message = "lane_host_failsafe_minutes below 30 can cut off a healthy first boot (the data-volume wait alone allows 10 minutes)."
  }
}

variable "lane_host_wake_schedule" {
  description = <<-EOT
    EventBridge Scheduler expression (UTC) that starts the lane host(s) again
    after an idle stop; null disables the wake. Default: daily at 05:00 UTC
    (08:00 Riyadh). The budget cap also detaches the wake's permission, so a
    capped host stays stopped (budgets.tf).
  EOT
  type        = string
  default     = "cron(0 5 * * ? *)"
}

variable "extra_tags" {
  type    = map(string)
  default = {}
}
