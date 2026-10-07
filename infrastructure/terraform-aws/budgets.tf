# ──────────────────────────────────────────────────────────────────────────────
# Budgets that measure the instances this root creates. The whole-account
# budget is in ./bootstrap.
#
# Both filter on InstanceType + Region, not on the Role tag. A tag filter
# reads USD 0 until the operator activates the tag for cost allocation (up to
# 24 h after it first appears on billed usage), and a stop action behind a
# filter that reads 0 can never fire: a vacuous gate. The instance-type
# filter works from the first hour. It requires the prod and lane-host types
# to differ, which lane_host.tf enforces with a precondition.
#
# What the filter covers: instance-hours only (the dominant line). EBS and
# public IPv4 for the lane host are bounded and fixed (~USD 21/month at the
# defaults) and show up in the account-total budget.
#
# Budgets data refreshes roughly three times a day, so the stop action lags
# real spend by up to ~8-12 h, i.e. ~USD 2-3 per lane host at r8g.xlarge
# on-demand in eu-north-1 (USD 0.25058/h). The cap is "about USD 250", not
# to the cent.
#
# At the defaults one r8g.xlarge running 730 h costs USD 182.92, below the
# cap, so with lane_host_count = 1 the action is a backstop against a count,
# type or Spot-price change; the 80% and forecast alerts plus lanes-idle-stop
# carry the day-to-day control.
#
# Once the action has stopped the hosts it does not fire again in the same
# month: an operator who starts a host after the stop has overridden the cap
# for the rest of that month (the alerts still arrive).
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_budgets_budget" "prod" {
  name         = "antiek-prod-instance-monthly"
  budget_type  = "COST"
  limit_amount = format("%.2f", var.prod_monthly_budget_usd)
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
    threshold                  = 110
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}

resource "aws_budgets_budget" "lane_host" {
  count = var.lane_host_count > 0 ? 1 : 0

  name         = "antiek-lane-host-monthly"
  budget_type  = "COST"
  limit_amount = format("%.2f", var.lane_host_monthly_budget_usd)
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
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}

# At 100% of actual spend, stop every lane host. AUTOMATIC: no human approval
# in the loop, which is the point of a cap. The instances stay stopped (the
# monthly reset does not restart them); the operator restarts deliberately.
resource "aws_budgets_budget_action" "stop_lane_hosts" {
  count = var.lane_host_count > 0 ? 1 : 0

  budget_name        = aws_budgets_budget.lane_host[0].name
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
