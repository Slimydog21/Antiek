# ──────────────────────────────────────────────────────────────────────────────
# IAM: service roles only, nothing for humans.
#
#   prod       AmazonSSMManagedInstanceCore, plus an explicit DENY on the
#              lane-host parameter path. Session Manager is the break-glass
#              shell and the hardening path off public port 22. No S3, no
#              Secrets Manager: the app's secrets stay in
#              /etc/antiek/secrets.env and its backups go to Cloudflare R2,
#              exactly as on Hetzner.
#   lane-host  SSM core + read and delete the one Tailscale auth-key
#              parameter (single use: the bootstrap deletes it after joining).
#   dlm        Data Lifecycle Manager's snapshot role (dlm.tf).
#   budgets    The lane-host cap's execution role: stop Role=lane-host
#              instances, detach the wake's permission (budgets.tf).
#   wake       EventBridge Scheduler: start Role=lane-host instances.
#
# What scoping does NOT do: AmazonSSMManagedInstanceCore itself allows
# ssm:GetParameter(s) on Resource "*" (policy v2, read 2026-10-07), and the
# default aws/ssm key admits in-account callers through SSM. Any principal
# holding that policy can read any parameter unless a Deny says otherwise.
# Hence the Deny on prod, the deletion after the join, and on the lane host
# the nftables rule that leaves the metadata service (and so the role's
# credentials) to root (lane_host.tf).
# ──────────────────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# ── prod ─────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "prod" {
  name               = "antiek-prod-instance"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = { Role = "prod" }
}

resource "aws_iam_role_policy_attachment" "prod_ssm_core" {
  role       = aws_iam_role.prod.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

locals {
  tailscale_authkey_param_arn = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.tailscale_authkey_param}"
  tailscale_authkey_path_arn  = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${dirname(var.tailscale_authkey_param)}"
}

# An internet-facing host must never be able to read the lane-host join key,
# whatever SSM core allows. Explicit Deny wins over any Allow.
data "aws_iam_policy_document" "prod_deny_lane_host_params" {
  statement {
    sid    = "NoLaneHostParameters"
    effect = "Deny"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
      "ssm:GetParameterHistory",
    ]
    resources = [
      local.tailscale_authkey_param_arn,
      local.tailscale_authkey_path_arn,
      "${local.tailscale_authkey_path_arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "prod_deny_lane_host_params" {
  name   = "deny-lane-host-parameters"
  role   = aws_iam_role.prod.id
  policy = data.aws_iam_policy_document.prod_deny_lane_host_params.json
}

resource "aws_iam_instance_profile" "prod" {
  name = "antiek-prod-instance"
  role = aws_iam_role.prod.name
}

# ── lane host ────────────────────────────────────────────────────────────────

resource "aws_iam_role" "lane_host" {
  count = var.lane_host_count > 0 ? 1 : 0

  name               = "antiek-lane-host-instance"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = { Role = "lane-host" }
}

resource "aws_iam_role_policy_attachment" "lane_host_ssm_core" {
  count = var.lane_host_count > 0 ? 1 : 0

  role       = aws_iam_role.lane_host[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "lane_host_tailscale_key" {
  statement {
    sid       = "ReadThenDeleteTailscaleAuthKey"
    actions   = ["ssm:GetParameter", "ssm:DeleteParameter"]
    resources = [local.tailscale_authkey_param_arn]
  }

  # Needed only if the parameter is encrypted with a customer-managed key; the
  # default aws/ssm key's policy already admits in-account callers via SSM.
  statement {
    sid       = "DecryptViaSsmOnly"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "lane_host_tailscale_key" {
  count = var.lane_host_count > 0 ? 1 : 0

  name   = "read-delete-tailscale-authkey"
  role   = aws_iam_role.lane_host[0].id
  policy = data.aws_iam_policy_document.lane_host_tailscale_key.json
}

resource "aws_iam_instance_profile" "lane_host" {
  count = var.lane_host_count > 0 ? 1 : 0

  name = "antiek-lane-host-instance"
  role = aws_iam_role.lane_host[0].name
}

# ── DLM ──────────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "dlm_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["dlm.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dlm" {
  name               = "antiek-dlm-snapshots"
  assume_role_policy = data.aws_iam_policy_document.dlm_assume.json
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

# ── Budget action (lane hosts) ───────────────────────────────────────────────

data "aws_iam_policy_document" "budgets_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

# STOP_EC2_INSTANCES: Budgets starts the AWS-owned AWS-StopEC2Instance
# automation as this role, and the automation stops the instance. The SSM
# resources are those of the AWS-managed
# AWSBudgetsActions_RolePolicyForResourceAdministrationWithSSM (v2, read
# 2026-10-07): the document, its automation definition and the execution;
# with the definition alone StartAutomationExecution is denied (policy
# simulator, reviewer 2026-10-07). Narrower than that policy in two ways:
# Stop only (no Start, no RDS), and only instances tagged Role=lane-host, so
# this role cannot stop production even if an instance id were wrong.
#
# APPLY_IAM_POLICY: the cap's second action attaches the deny-wake policy
# to the wake role; this role may attach or detach exactly that policy on
# exactly that role.
data "aws_iam_policy_document" "budget_action" {
  statement {
    sid     = "StartStopAutomation"
    actions = ["ssm:StartAutomationExecution"]
    resources = [
      "arn:aws:ssm:${var.region}:*:document/AWS-StopEC2Instance",
      "arn:aws:ssm:${var.region}:*:automation-definition/AWS-StopEC2Instance:*",
      "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:automation-execution/*",
    ]
  }

  statement {
    sid       = "ReadAutomation"
    actions   = ["ssm:GetAutomationExecution", "ec2:DescribeInstances", "ec2:DescribeInstanceStatus"]
    resources = ["*"]
  }

  statement {
    sid       = "StopLaneHostsOnly"
    actions   = ["ec2:StopInstances"]
    resources = ["arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Role"
      values   = ["lane-host"]
    }

    condition {
      test     = "ForAnyValue:StringEquals"
      variable = "aws:CalledVia"
      values   = ["ssm.amazonaws.com"]
    }
  }

  dynamic "statement" {
    for_each = var.lane_host_wake_schedule != null ? [1] : []

    content {
      sid       = "DetachTheWake"
      actions   = ["iam:AttachRolePolicy", "iam:DetachRolePolicy"]
      resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/antiek-lane-host-wake"]

      condition {
        test     = "ArnEquals"
        variable = "iam:PolicyARN"
        values   = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/antiek-deny-lane-host-wake"]
      }
    }
  }
}

resource "aws_iam_role" "budget_action" {
  count = var.lane_host_count > 0 ? 1 : 0

  name               = "antiek-budget-stop-lane-hosts"
  assume_role_policy = data.aws_iam_policy_document.budgets_assume.json
  tags               = { Role = "lane-host" }
}

resource "aws_iam_role_policy" "budget_action" {
  count = var.lane_host_count > 0 ? 1 : 0

  name   = "stop-lane-hosts"
  role   = aws_iam_role.budget_action[0].id
  policy = data.aws_iam_policy_document.budget_action.json
}

# ── Wake schedule (lane hosts) ───────────────────────────────────────────────

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

data "aws_iam_policy_document" "lane_host_wake" {
  statement {
    sid       = "StartLaneHostsOnly"
    actions   = ["ec2:StartInstances"]
    resources = ["arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/Role"
      values   = ["lane-host"]
    }
  }
}

resource "aws_iam_role" "lane_host_wake" {
  count = var.lane_host_count > 0 && var.lane_host_wake_schedule != null ? 1 : 0

  name               = "antiek-lane-host-wake"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = { Role = "lane-host" }
}

resource "aws_iam_role_policy" "lane_host_wake" {
  count = length(aws_iam_role.lane_host_wake)

  name   = "start-lane-hosts"
  role   = aws_iam_role.lane_host_wake[0].id
  policy = data.aws_iam_policy_document.lane_host_wake.json
}

# Attached to the wake role by the cap budget's APPLY_IAM_POLICY action, never
# by Terraform. While attached, the schedule's StartInstances is denied.
data "aws_iam_policy_document" "deny_lane_host_wake" {
  statement {
    sid       = "CapReached"
    effect    = "Deny"
    actions   = ["ec2:StartInstances"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "deny_lane_host_wake" {
  count = length(aws_iam_role.lane_host_wake)

  name        = "antiek-deny-lane-host-wake"
  description = "Attached by the lane-host cap budget action: a capped lane host is not woken."
  policy      = data.aws_iam_policy_document.deny_lane_host_wake.json
}
