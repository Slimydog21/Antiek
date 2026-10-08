# ──────────────────────────────────────────────────────────────────────────────
# Budgets that measure the instances this root creates. The whole-account
# budget is in ./bootstrap.
#
# All filter on InstanceType + Region, not on the Role tag. A tag filter
# reads USD 0 until the operator activates the tag for cost allocation (up to
# 24 h after it first appears on billed usage), and a stop action behind a
# filter that reads 0 can never fire: a vacuous gate. The instance-type
# filter works from the first hour. It requires the prod and lane-host types
# to differ, which lane_host.tf enforces with a precondition.
#
# Each budget is sized so that it CAN fire for the failure it exists to see
# (L17). The 10-07 draft put every threshold above what the instances can
# cost: one r8g.xlarge for a 31-day month is 744 h x USD 0.25058 =
# USD 186.43, under its USD 200 (80%) alert and USD 250 action; one
# m8g.xlarge is USD 141.92, under the prod budget's USD 160.
#
#   prod             alert when spend exceeds one instance-month (a second
#                    prod-type instance, a forgotten rebuild).
#   lane-host        alert at the EXPECTED spend with idle stop and the
#                    daily wake (default USD 100, ~55% uptime of one host),
#                    so a host stuck running is flagged mid-month.
#   lane-host cap    the operator's USD 250 on all lane-host spend, enforced
#                    on instance-hours: the filter cannot see EBS, public
#                    IPv4 or egress, so its limit is the cap minus every
#                    host's fixed EBS + IPv4 cost and an egress allowance
#                    (local.lane_host_cap_usd; USD 221.30 at one host). At
#                    100% two actions run: stop the lane hosts, and detach
#                    the wake's permission so the schedule cannot restart a
#                    capped host. With one on-demand host the cap is a
#                    backstop (a count, type or Spot change can reach it;
#                    one host cannot); the lane-host alert is the
#                    day-to-day control.
#
# Budgets data refreshes roughly three times a day, so alerts and actions
# lag real spend by up to ~8-12 h, i.e. ~USD 2-3 per lane host. Neither
# action has run against a live account yet; lane-host.md carries the drill
# that proves the stop path (L17), to be run once before relying on it.
#
# What the cap does not cover: an operator who starts a capped host by hand
# has overridden it for the rest of the month (the alerts still arrive), and
# EBS keeps billing while the hosts are stopped (already subtracted above).
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # On-demand USD/h in eu-north-1 [M, README.md cost table, AWS price file
  # read 2026-10-07].
  prod_hourly_usd = { "m8g.xlarge" = 0.19076, "m7i.xlarge" = 0.2142 }

  # 5% above the longest month of one instance, rounded up: m8g.xlarge 150,
  # m7i.xlarge 168. Null for a type outside the table, which the prod
  # budget's precondition turns into a request for an explicit value.
  prod_budget_usd = var.prod_monthly_budget_usd != null ? var.prod_monthly_budget_usd : (
    contains(keys(local.prod_hourly_usd), local.prod_instance_type) ? ceil(744 * local.prod_hourly_usd[local.prod_instance_type] * 1.05) : null
  )

  # Fixed monthly cost of one lane host that the instance-type filter cannot
  # see: gp3 at USD 0.0836/GiB-month and one public IPv4 at USD 0.005/h for
  # 730 h [M, README.md].
  lane_host_fixed_usd = (var.lane_host_root_volume_gib + var.lane_host_data_volume_gib) * 0.0836 + 0.005 * 730
  lane_host_cap_usd   = var.lane_host_monthly_budget_usd - var.lane_host_count * local.lane_host_fixed_usd - var.lane_host_egress_allowance_usd
}

resource "aws_budgets_budget" "prod" {
  name         = "antiek-prod-instance-monthly"
  budget_type  = "COST"
  limit_amount = format("%.2f", local.prod_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "InstanceType"
    values = [local.prod_instance_type]
  }

  cost_filter {
    name   = "Region"
    values = [var.region]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }

  lifecycle {
    precondition {
      condition     = local.prod_budget_usd != null
      error_message = "No price on record for ${local.prod_instance_type}: set prod_monthly_budget_usd to ~1.05 x 744 h of its on-demand rate."
    }

    # One instance must never trip it, or the alert is noise; two must.
    precondition {
      condition     = !contains(keys(local.prod_hourly_usd), local.prod_instance_type) || (local.prod_budget_usd > 744 * lookup(local.prod_hourly_usd, local.prod_instance_type, 0) && local.prod_budget_usd < 2 * 672 * lookup(local.prod_hourly_usd, local.prod_instance_type, 0))
      error_message = "prod_monthly_budget_usd must sit between one and two instance-months of ${local.prod_instance_type}."
    }
  }
}

resource "aws_budgets_budget" "lane_host" {
  count = var.lane_host_count > 0 ? 1 : 0

  name         = "antiek-lane-host-expected"
  budget_type  = "COST"
  limit_amount = format("%.2f", var.lane_host_expected_monthly_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "InstanceType"
    values = [var.lane_host_instance_type]
  }

  cost_filter {
    name   = "Region"
    values = [var.region]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }

  lifecycle {
    precondition {
      condition     = var.lane_host_expected_monthly_usd > 0 && var.lane_host_expected_monthly_usd < local.lane_host_cap_usd
      error_message = "lane_host_expected_monthly_usd must be below the instance-hour cap (USD ${format("%.2f", local.lane_host_cap_usd)}), or its alerts arrive only with the stop."
    }
  }
}

resource "aws_budgets_budget" "lane_host_cap" {
  count = var.lane_host_count > 0 ? 1 : 0

  name         = "antiek-lane-host-cap"
  budget_type  = "COST"
  limit_amount = format("%.2f", local.lane_host_cap_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "InstanceType"
    values = [var.lane_host_instance_type]
  }

  cost_filter {
    name   = "Region"
    values = [var.region]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  lifecycle {
    precondition {
      condition     = local.lane_host_cap_usd > 0
      error_message = "lane_host_monthly_budget_usd (${var.lane_host_monthly_budget_usd}) does not cover ${var.lane_host_count} host(s) of fixed EBS + IPv4 (USD ${format("%.2f", local.lane_host_fixed_usd)} each) plus the egress allowance."
    }
  }
}

# At 100% of the cap's actual spend, stop every lane host. AUTOMATIC: no human approval
# in the loop, which is the point of a cap. The instances stay stopped (the
# monthly reset does not restart them); the operator restarts deliberately.
resource "aws_budgets_budget_action" "stop_lane_hosts" {
  count = var.lane_host_count > 0 ? 1 : 0

  budget_name        = aws_budgets_budget.lane_host_cap[0].name
  action_type        = "RUN_SSM_DOCUMENTS"
  approval_model     = "AUTOMATIC"
  notification_type  = "ACTUAL"
  execution_role_arn = aws_iam_role.budget_action[0].arn

  action_threshold {
    action_threshold_type  = "PERCENTAGE"
    action_threshold_value = 100
  }

  definition {
    ssm_action_definition {
      action_sub_type = "STOP_EC2_INSTANCES"
      region          = var.region
      instance_ids    = aws_instance.lane_host[*].id
    }
  }

  subscriber {
    address           = var.alert_email
    subscription_type = "EMAIL"
  }

  depends_on = [aws_iam_role_policy.budget_action]
}

# Same threshold: attach the deny-wake policy to the wake role, so the daily
# schedule cannot restart what the cap stopped. Reverse it (console: Budgets
# > antiek-lane-host-cap > Actions > Reverse) when the operator restarts the
# hosts deliberately or the month turns (lane-host.md).
resource "aws_budgets_budget_action" "block_lane_host_wake" {
  count = length(aws_scheduler_schedule.lane_host_wake)

  budget_name        = aws_budgets_budget.lane_host_cap[0].name
  action_type        = "APPLY_IAM_POLICY"
  approval_model     = "AUTOMATIC"
  notification_type  = "ACTUAL"
  execution_role_arn = aws_iam_role.budget_action[0].arn

  action_threshold {
    action_threshold_type  = "PERCENTAGE"
    action_threshold_value = 100
  }

  definition {
    iam_action_definition {
      policy_arn = aws_iam_policy.deny_lane_host_wake[0].arn
      roles      = [aws_iam_role.lane_host_wake[0].name]
    }
  }

  subscriber {
    address           = var.alert_email
    subscription_type = "EMAIL"
  }

  depends_on = [aws_iam_role_policy.budget_action]
}
