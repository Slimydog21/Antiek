# ──────────────────────────────────────────────────────────────────────────────
# Main root for Antiek on AWS (eu-north-1): network, the production host and
# its data volume, snapshots, the optional lane host(s), and the two budgets
# that measure them.
#
# Apply order and operator inputs: README.md. The Hetzner root in
# ../terraform/ is untouched and keeps its own local state until the Hetzner
# server is decommissioned.
#
# State lives in the bucket ./bootstrap creates. The backend block is partial
# on purpose: the bucket name contains the account id, so it is supplied at
# init time from backend.hcl (gitignored; shape in backend.hcl.example):
#
#   terraform init -backend-config=backend.hcl
#
# use_lockfile = true is S3-native state locking (Terraform >= 1.10): a
# `.tflock` object next to the state, so two applies cannot interleave and no
# DynamoDB table is needed.
# ──────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.10.0"

  backend "s3" {
    region       = "eu-north-1"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67"
    }
  }
}
