# Offline plan tests for the bootstrap root (mocked AWS provider; no account
# or credentials). Run: terraform init -backend=false && terraform test

mock_provider "aws" {
  override_during = plan

  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }

  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }

  mock_resource "aws_s3_bucket" {
    defaults = {
      id  = "antiek-tfstate-123456789012-eu-north-1"
      arn = "arn:aws:s3:::antiek-tfstate-123456789012-eu-north-1"
    }
  }
}

variables {
  alert_email = "ops@example.invalid"
}

run "guardrails" {
  command = plan

  assert {
    condition     = aws_s3_bucket.tfstate.bucket == "antiek-tfstate-123456789012-eu-north-1"
    error_message = "state bucket name must derive from account id and region."
  }

  assert {
    condition     = aws_s3_bucket_versioning.tfstate.versioning_configuration[0].status == "Enabled"
    error_message = "state bucket must be versioned."
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.tfstate.block_public_acls,
      aws_s3_bucket_public_access_block.tfstate.block_public_policy,
      aws_s3_bucket_public_access_block.tfstate.ignore_public_acls,
      aws_s3_bucket_public_access_block.tfstate.restrict_public_buckets,
    ])
    error_message = "state bucket must block every form of public access."
  }

  assert {
    condition     = aws_ebs_encryption_by_default.this.enabled
    error_message = "EBS encryption by default must be on."
  }

  assert {
    condition     = aws_ec2_instance_metadata_defaults.this.http_tokens == "required" && aws_ec2_instance_metadata_defaults.this.http_put_response_hop_limit == 1
    error_message = "account IMDS default must be IMDSv2-only, hop limit 1."
  }

  assert {
    condition     = aws_budgets_budget.account_total.limit_amount == "500.00"
    error_message = "account budget default is USD 500."
  }

  assert {
    condition     = length(aws_ce_cost_allocation_tag.project_and_role) == 0
    error_message = "cost allocation tags stay inactive until the operator flips the switch."
  }
}
