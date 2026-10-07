# ──────────────────────────────────────────────────────────────────────────────
# IAM: three service roles and nothing for humans.
#
#   prod       AmazonSSMManagedInstanceCore only. Session Manager is the
#              break-glass shell and the hardening path off public port 22.
#              No S3, no Secrets Manager: the app's secrets stay in
#              /etc/antiek/secrets.env and its backups go to Cloudflare R2,
#              exactly as on Hetzner.
#   lane-host  SSM core + read ONE SecureString (the Tailscale auth key).
#   dlm        Data Lifecycle Manager's snapshot role (dlm.tf).
#   budgets    The lane-host budget action's execution role (budgets.tf).
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
    sid       = "ReadTailscaleAuthKey"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.tailscale_authkey_param}"]
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

  name   = "read-tailscale-authkey"
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

# Least privilege for STOP_EC2_INSTANCES: Budgets starts the AWS-owned
# AWS-StopEC2Instance automation as this role, and the automation stops the
# instance. StopInstances is limited to instances tagged Role=lane-host, so
# this role cannot stop production even if an instance id were wrong.
data "aws_iam_policy_document" "budget_action" {
  statement {
    sid       = "StartStopAutomation"
    actions   = ["ssm:StartAutomationExecution"]
    resources = ["arn:aws:ssm:${var.region}:*:automation-definition/AWS-StopEC2Instance:*"]
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
