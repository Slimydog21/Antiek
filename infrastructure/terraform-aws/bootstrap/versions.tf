# ──────────────────────────────────────────────────────────────────────────────
# Bootstrap root for the Antiek AWS account. Applied ONCE, with local state,
# before the main root (..) exists, because it creates the bucket the main
# root keeps its state in.
#
# Local state is deliberate: a root cannot store its state in a bucket it is
# about to create. The state file stays on the operator's Mac (gitignored).
# Losing it is cheap: every resource here can be re-imported by name.
#
# Terraform >= 1.10 matches the main root, whose S3 backend uses
# `use_lockfile` (S3-native locking, no DynamoDB table).
# ──────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67"
    }
  }
}
