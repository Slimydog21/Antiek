variable "region" {
  description = "The one Region Antiek's AWS project can create resources in: eu-north-1 (Stockholm). See ../variables.tf and docs/decisions/aws-production-and-agent-backbone-2026-10-07.md."
  type        = string
  default     = "eu-north-1"

  validation {
    condition     = var.region == "eu-north-1"
    error_message = "Antiek's AWS project can only create resources in eu-north-1."
  }
}

variable "alert_email" {
  description = "Where AWS Budgets sends alerts. Budgets e-mails directly; no SNS subscription to confirm."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an e-mail address."
  }
}

variable "account_monthly_budget_usd" {
  description = <<-EOT
    Whole-account monthly cost budget (alerts only, no action). Sized to the
    worst steady state at eu-north-1 on-demand prices (README.md cost table):
    prod ~USD 160-167 all-in, plus one lane host running 24x7 at ~USD 202
    all-in (its instance-hours are capped separately at USD 250 in the main
    root), plus slack. Alerts at 50/80/100% actual and 100% forecast.
  EOT
  type        = number
  default     = 500
}

variable "state_bucket_name" {
  description = "Name of the main root's state bucket. Null derives antiek-tfstate-<account-id>-<region>, which is globally unique by construction."
  type        = string
  default     = null
}

variable "state_noncurrent_version_days" {
  description = "Days a superseded state object version is kept. Storage at rest is the billing trap (mini-lessons L9), so old versions expire."
  type        = number
  default     = 90
}

variable "activate_cost_allocation_tags" {
  description = <<-EOT
    Activate the Project and Role tags for cost allocation (Cost Explorer
    grouping). AWS only accepts a tag key after it has appeared on billed
    usage, up to 24 h after the first tagged resource exists, so leave this
    false on the first apply and flip it once Billing > Cost allocation tags
    lists them. No budget here depends on it.

    Measured 2026-10-07: `aws ce list-cost-allocation-tags` returns
    AccessDeniedException on this project while it is on the Free plan, so
    expect the activation to fail until Cost Explorer is available to it.
  EOT
  type        = bool
  default     = false
}
