# ──────────────────────────────────────────────────────────────────────────────
# Account-level guardrails for the Antiek AWS account.
#
# What this provisions:
#   1. The main root's state bucket: versioned, encrypted, private, TLS-only,
#      old versions expire.
#   2. Region-level defaults that every later EC2 resource inherits: EBS
#      encryption on, instance metadata IMDSv2-only.
#   3. The whole-account monthly budget (alerts).
#   4. Optional activation of the Project/Role cost-allocation tags.
#
# What this does NOT do (and why):
#   - The prod and lane-host budgets live in the main root, next to the
#     instances they measure. Their filters name the instance types and the
#     lane-host stop action names the instance ids; both are known only to the
#     root that creates the instances. A copy here would drift the first time
#     the main root changed a type or replaced a host, and a budget that
#     filters on the wrong type reads USD 0 forever (a vacuous gate).
#   - No IAM users or access keys. The operator works through an SSO/Identity
#     Center profile created in the console when the account is opened.
# ──────────────────────────────────────────────────────────────────────────────

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "antiek"
      Stack     = "bootstrap"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  state_bucket_name = coalesce(var.state_bucket_name, "antiek-tfstate-${data.aws_caller_identity.current.account_id}-${var.region}")
}

# ── 1. State bucket ──────────────────────────────────────────────────────────

resource "aws_s3_bucket" "tfstate" {
  bucket = local.state_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning is what makes a bad apply recoverable: the previous state object
# survives, and the S3-native lock file (use_lockfile) needs nothing else.
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    id     = "expire-superseded-state"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.state_noncurrent_version_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.tfstate]
}

data "aws_iam_policy_document" "tfstate_tls_only" {
  statement {
    sid     = "DenyNonTLS"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.tfstate.arn,
      "${aws_s3_bucket.tfstate.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  policy = data.aws_iam_policy_document.tfstate_tls_only.json

  # A bucket policy is a public-policy candidate until the access block exists.
  depends_on = [aws_s3_bucket_public_access_block.tfstate]
}

# ── 2. Region-level EC2 defaults ─────────────────────────────────────────────

# Every new EBS volume and snapshot in this region is encrypted with the
# AWS-managed key, including volumes a human creates in the console. The main
# root still sets encrypted = true on each volume, so the invariant does not
# rest on this one switch.
resource "aws_ebs_encryption_by_default" "this" {
  enabled = true
}

# New instances default to IMDSv2-only with a hop limit of 1, so a process in
# a container or a forwarded request cannot read instance credentials. The
# main root also pins metadata_options on every instance.
resource "aws_ec2_instance_metadata_defaults" "this" {
  http_tokens                 = "required"
  http_put_response_hop_limit = 1
  http_endpoint               = "enabled"
  instance_metadata_tags      = "disabled"
}

# ── 3. Whole-account budget ──────────────────────────────────────────────────

resource "aws_budgets_budget" "account_total" {
  name         = "antiek-account-total-monthly"
  budget_type  = "COST"
  limit_amount = format("%.2f", var.account_monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = [50, 80, 100]

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.alert_email]
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}

# ── 4. Cost-allocation tags (opt-in, see variables.tf) ───────────────────────

resource "aws_ce_cost_allocation_tag" "project_and_role" {
  for_each = var.activate_cost_allocation_tags ? toset(["Project", "Role"]) : toset([])

  tag_key = each.value
  status  = "Active"
}
