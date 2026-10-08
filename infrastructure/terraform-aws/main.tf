# ──────────────────────────────────────────────────────────────────────────────
# Provider, shared lookups and naming.
#
# File map:
#   network.tf   VPC, one public subnet, IGW, default-SG lockdown
#   prod.tf      production host, its data volume, EIP, security group
#   lane_host.tf lane host(s) for the compute dispatcher's node backend, daily wake
#   iam.tf       instance roles, DLM, budget-action and wake roles
#   dlm.tf       daily snapshots of the prod data volume
#   budgets.tf   prod alert budget, lane-host expected-spend alerts, cap + actions
#   outputs.tf   values the runbooks need (EIP, ids, ...)
# ──────────────────────────────────────────────────────────────────────────────

provider "aws" {
  region = var.region

  default_tags {
    tags = merge(var.extra_tags, {
      Project   = "antiek"
      Stack     = "main"
      ManagedBy = "terraform"
    })
  }
}

data "aws_caller_identity" "current" {}

locals {
  # EC2's architecture names differ from Canonical's SSM path segment.
  ubuntu_ssm_arch = { arm64 = "arm64", x86_64 = "amd64" }

  default_prod_instance_type = { arm64 = "m8g.xlarge", x86_64 = "m7i.xlarge" }
  prod_instance_type         = coalesce(var.prod_instance_type, local.default_prod_instance_type[var.prod_arch])

  # The resolved DuckDB path is part of the TurboPuffer servable pointer's
  # identity (substrate/graph/retrieval_adapters/turbopuffer.py hashes it), so
  # the data volume must be mounted at exactly the path group_vars/all.yml
  # derives for antiek_state_dir, never a symlink to it. Not a variable.
  prod_state_dir = "/home/antiek/.antiek"

  # Units that must not run, or must not run against an empty root-volume
  # directory, without the data volume mounted.
  state_dir_units = [
    "antiek.service",
    "antiek-continuous-research.service",
    "antiek-arxiv-oai-sync.service",
    "antiek-backup.service",
    "antiek-backup-freshness.service",
    "antiek-health-probe.service",
  ]

  # A freshly built prod host is born HELD: while /etc/antiek/STAGING_HOLD
  # exists these units are skipped (ConditionPathExists=!), so the host can
  # be provisioned, deployed and rehearsed with real secrets without uploading
  # a stale database to r2:antiek-backups/nightly/, double-hitting arXiv,
  # spending research budget, paging anyone, or attaching a second connector
  # to the production Cloudflare Tunnel. A start of a held unit succeeds as a
  # skip, so setup.yml and deploy_atomic.yml run unchanged. Cutover (and any
  # DR rebuild) releases the hold by deleting the file:
  # infrastructure/runbooks/aws-cutover.md.
  staging_hold_file = "/etc/antiek/STAGING_HOLD"
  held_units = [
    "cloudflared.service",
    "antiek-continuous-research.service",
    "antiek-arxiv-oai-sync.service",
    "antiek-backup.service",
    "antiek-backup-freshness.service",
    "antiek-health-probe.service",
  ]
}

data "aws_ssm_parameter" "ubuntu_prod" {
  count = var.prod_ami_id == null ? 1 : 0
  name  = "/aws/service/canonical/ubuntu/server/24.04/stable/current/${local.ubuntu_ssm_arch[var.prod_arch]}/hvm/ebs-gp3/ami-id"
}

data "aws_ssm_parameter" "ubuntu_lane_host" {
  count = var.lane_host_count > 0 ? 1 : 0
  name  = "/aws/service/canonical/ubuntu/server/24.04/stable/current/${local.ubuntu_ssm_arch[var.lane_host_arch]}/hvm/ebs-gp3/ami-id"
}

# Plan-time architecture checks: an m7i AMI on a Graviton type fails late and
# confusingly at launch; this fails at plan with the reason.
data "aws_ec2_instance_type" "prod" {
  instance_type = local.prod_instance_type
}

data "aws_ec2_instance_type" "lane_host" {
  instance_type = var.lane_host_instance_type
}

# Running-vCPU quotas, read at plan time so an over-quota launch fails at
# plan with the reason instead of as VcpuLimitExceeded halfway through an
# apply. Measured 2026-10-07 on the new project in eu-north-1: both are 5,
# which fits prod (4) alone but not prod + one lane host (8). Raising
# L-1216C47A to 16 is an operator step in README.md. The check counts only
# the instances this root creates.
data "aws_servicequotas_service_quota" "ondemand_standard_vcpus" {
  service_code = "ec2"
  quota_code   = "L-1216C47A" # Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances
}

data "aws_servicequotas_service_quota" "spot_standard_vcpus" {
  service_code = "ec2"
  quota_code   = "L-34B43A08" # All Standard (A, C, D, H, I, M, R, T, Z) Spot Instance Requests
}

locals {
  prod_vcpus      = data.aws_ec2_instance_type.prod.default_vcpus
  lane_host_vcpus = var.lane_host_count * data.aws_ec2_instance_type.lane_host.default_vcpus

  ondemand_vcpus_needed = local.prod_vcpus + (var.lane_host_use_spot ? 0 : local.lane_host_vcpus)
  spot_vcpus_needed     = var.lane_host_use_spot ? local.lane_host_vcpus : 0
}
