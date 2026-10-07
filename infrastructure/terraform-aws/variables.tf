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
  description = "AZ for the single public subnet. Null picks the first AZ (sorted) that offers both the prod and lane-host instance types."
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
  description = "Alert-only budget on prod instance-hours. On-demand m8g.xlarge in eu-north-1 is USD 0.19076/h = USD 139.25 per 730 h month; more than that means a second prod-type instance or a type change."
  type        = number
  default     = 160
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
  type    = number
  default = 30
}

variable "lane_host_data_volume_gib" {
  description = "gp3 volume mounted at /srv/lanes (staged inputs + lane workdirs). Not backed up: the Mini is the data of record (ACTIVATION §N)."
  type        = number
  default     = 150
}

variable "lane_host_monthly_budget_usd" {
  description = "Operator-approved hard cap (2026-10-07). At 100% actual, a budget action stops every lane host."
  type        = number
  default     = 250
}

variable "lane_host_name_prefix" {
  description = "Hostname and Tailscale node name prefix; host N is <prefix>-N. Must match the compute policy entry hosts.nodes.lanes-eun1-1 (ssh: lanes@lanes-eun1-1)."
  type        = string
  default     = "lanes-eun1"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,40}$", var.lane_host_name_prefix))
    error_message = "lane_host_name_prefix must be a lowercase DNS label."
  }
}

variable "lane_host_dispatcher_authorized_keys" {
  description = <<-EOT
    Public key(s) the compute dispatcher on the Mini uses to reach the lanes
    account (ssh lanes@<host> over Tailscale, BatchMode). Installed for the
    `lanes` user only, with a from= restriction to Tailscale address space;
    root has no SSH login on a lane host (break-glass is SSM Session
    Manager). The security group admits nothing inbound either way.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for k in var.lane_host_dispatcher_authorized_keys : can(regex("^(ssh-ed25519|ecdsa-sha2-nistp(256|384|521)|ssh-rsa) [A-Za-z0-9+/=]+( .*)?$", k))])
    error_message = "lane_host_dispatcher_authorized_keys must be OpenSSH public key lines without options; the from= option is added here."
  }
}

variable "tailscale_authkey_param" {
  description = "Name of an SSM SecureString holding a pre-authorised, tagged Tailscale auth key. Created by the operator out of band; Terraform only references it, so the key never enters user_data or state."
  type        = string
  default     = "/antiek/lane-host/tailscale-authkey"

  validation {
    condition     = startswith(var.tailscale_authkey_param, "/")
    error_message = "tailscale_authkey_param must be a fully qualified SSM parameter name."
  }
}

variable "tailscale_tags" {
  type    = string
  default = "tag:compute-node"
}

variable "lanes_slice_memory_high" {
  description = "The lanes user's lanes.slice MemoryHigh (all lanes together): reclaim pressure starts here."
  type        = string
  default     = "24G"
}

variable "lanes_slice_memory_max" {
  description = "The lanes user's lanes.slice MemoryMax (compute 1.6.0 host check: an aggregate ~26G of 32 GiB). The OOM killer acts inside the slice, never on sshd, tailscaled or the SSM agent."
  type        = string
  default     = "26G"
}

variable "lanes_slice_tasks_max" {
  description = "lanes.slice TasksMax: 24 lanes x 512 tasks (D-19 per-lane TasksMax)."
  type        = number
  default     = 12288
}

variable "lane_host_user_slice_memory_max" {
  description = "Root-owned ceiling on every user-<uid>.slice. The lanes account owns its lanes.slice file and could raise it; it cannot raise this."
  type        = string
  default     = "28G"
}

variable "lane_host_idle_stop_minutes" {
  description = "Power off (instance stops; EBS keeps billing, compute does not) after this many minutes with no task in lanes.slice and no login session. 0 disables."
  type        = number
  default     = 60
}

variable "extra_tags" {
  type    = map(string)
  default = {}
}
