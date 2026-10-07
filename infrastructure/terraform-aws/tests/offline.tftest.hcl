# Offline plan/apply tests for the main root: a mocked AWS provider, so no
# credentials, no account and no API calls. They evaluate the real
# expressions (cloud-config rendering, counts, filters, preconditions) that
# `terraform validate` cannot see.
#
#   terraform init -backend=false && terraform test
#
# tests/test_terraform_aws_invariants.py runs this when terraform is on PATH.

mock_provider "aws" {
  # Mocked computed values (volume and instance ids) are needed at plan time;
  # plan-only runs never create test state, so nothing has to be torn down
  # (an apply would trip prevent_destroy on the data volume at teardown).
  override_during = plan

  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }

  mock_data "aws_availability_zones" {
    defaults = { names = ["eu-north-1a", "eu-north-1b", "eu-north-1c"] }
  }

  # eu-north-1a lacks r8g.xlarge in this fixture, so the AZ selection must
  # skip it whenever a lane host type is in play.
  mock_data "aws_ec2_instance_type_offerings" {
    defaults = {
      instance_types = ["m8g.xlarge", "m8g.xlarge", "r8g.xlarge", "m7i.xlarge", "m7i.xlarge", "r8g.xlarge"]
      locations      = ["eu-north-1a", "eu-north-1b", "eu-north-1b", "eu-north-1a", "eu-north-1b", "eu-north-1c"]
      location_types = ["availability-zone", "availability-zone", "availability-zone", "availability-zone", "availability-zone", "availability-zone"]
    }
  }

  mock_data "aws_ec2_instance_type" {
    defaults = { supported_architectures = ["arm64"], default_vcpus = 4 }
  }

  # 16 is the value README.md asks the operator to request; the measured
  # starting value (5) is exercised by quota_too_small_is_refused.
  mock_data "aws_servicequotas_service_quota" {
    defaults = { value = 16 }
  }

  mock_data "aws_ssm_parameter" {
    defaults = { insecure_value = "ami-0123456789abcdef0" }
  }

  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }

  mock_resource "aws_ebs_volume" {
    defaults = { id = "vol-0abc123def4567890" }
  }

  # Provider-side validation still runs under mocks, so ARNs must be ARNs.
  mock_resource "aws_instance" {
    defaults = { id = "i-0123456789abcdef0" }
  }

  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/mock" }
  }

  mock_resource "aws_iam_instance_profile" {
    defaults = { arn = "arn:aws:iam::123456789012:instance-profile/mock" }
  }
}

variables {
  alert_email          = "ops@example.invalid"
  ssh_ingress_cidrs    = ["0.0.0.0/0"]
  root_authorized_keys = ["ssh-ed25519 AAAAoperator operator", "ssh-ed25519 AAAAdeploy github-actions-deploy@antiek"]
}

run "prod_defaults" {
  command = plan

  assert {
    condition     = aws_instance.prod.instance_type == "m8g.xlarge"
    error_message = "arm64 default must select m8g.xlarge."
  }

  assert {
    condition     = local.availability_zone == "eu-north-1b"
    error_message = "AZ must be the first one offering both m8g.xlarge and r8g.xlarge (1a lacks r8g in the fixture)."
  }

  assert {
    condition     = aws_instance.prod.metadata_options[0].http_tokens == "required" && aws_instance.prod.metadata_options[0].http_put_response_hop_limit == 1
    error_message = "prod must require IMDSv2 with hop limit 1."
  }

  assert {
    condition     = aws_instance.prod.disable_api_termination && aws_instance.prod.disable_api_stop
    error_message = "prod must have termination and stop protection."
  }

  assert {
    condition     = aws_instance.prod.root_block_device[0].encrypted && aws_ebs_volume.prod_data.encrypted
    error_message = "every prod volume must be encrypted."
  }

  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.prod_ssh) == 1 && alltrue([for r in aws_vpc_security_group_ingress_rule.prod_ssh : r.from_port == 22 && r.to_port == 22 && r.ip_protocol == "tcp"])
    error_message = "prod ingress must be tcp/22 only."
  }

  # The rendered cloud-config is the contract with the box: decode it and
  # check the parts the runbooks rely on.
  assert {
    condition     = startswith(aws_instance.prod.user_data, "#cloud-config\n")
    error_message = "user_data must be a cloud-config document."
  }

  assert {
    condition = contains(
      yamldecode(trimprefix(aws_instance.prod.user_data, "#cloud-config\n")).runcmd,
      ["/usr/local/sbin/attach-data-volume", "vol-0abc123def4567890", "/home/antiek/.antiek", "antiek", "antiek-state"],
    )
    error_message = "cloud-init must mount the prod data volume, by its id, at exactly /home/antiek/.antiek."
  }

  assert {
    condition = length([
      for f in yamldecode(trimprefix(aws_instance.prod.user_data, "#cloud-config\n")).write_files : f
      if endswith(f.path, "/10-state-volume.conf") && strcontains(f.content, "RequiresMountsFor=/home/antiek/.antiek")
    ]) == 6
    error_message = "all six state-dir units need RequiresMountsFor on the data volume."
  }

  assert {
    condition = toset([
      for f in yamldecode(trimprefix(aws_instance.prod.user_data, "#cloud-config\n")).write_files :
      trimsuffix(trimprefix(f.path, "/etc/systemd/system/"), ".d/90-staging-hold.conf")
      if endswith(f.path, "/90-staging-hold.conf") && strcontains(f.content, "ConditionPathExists=!/etc/antiek/STAGING_HOLD")
    ]) == toset(["cloudflared.service", "antiek-continuous-research.service", "antiek-arxiv-oai-sync.service", "antiek-backup.service", "antiek-backup-freshness.service", "antiek-health-probe.service"])
    error_message = "the new host must be born held: cloudflared and every background consumer gated on STAGING_HOLD."
  }

  assert {
    condition     = contains([for f in yamldecode(trimprefix(aws_instance.prod.user_data, "#cloud-config\n")).write_files : f.path], "/etc/antiek/STAGING_HOLD")
    error_message = "cloud-init must create the STAGING_HOLD file."
  }

  assert {
    condition = anytrue([
      for f in yamldecode(trimprefix(aws_instance.prod.user_data, "#cloud-config\n")).write_files :
      f.path == "/etc/caddy/origin-tls.d/internal.caddy" && can(regex("(?m)^tls internal$", f.content))
    ])
    error_message = "the prod host must declare its origin certificate (tls internal) where Caddyfile.j2 imports it."
  }

  assert {
    condition     = !contains([for f in yamldecode(trimprefix(aws_instance.prod.user_data, "#cloud-config\n")).write_files : f.path], "/etc/systemd/system/antiek.service.d/90-staging-hold.conf")
    error_message = "antiek.service itself must not be held: rehearsal needs the API running."
  }

  assert {
    condition     = yamldecode(trimprefix(aws_instance.prod.user_data, "#cloud-config\n")).disable_root == false && length(yamldecode(trimprefix(aws_instance.prod.user_data, "#cloud-config\n")).users) == 0
    error_message = "root must be the only login (no default ubuntu user)."
  }

  assert {
    condition     = length(aws_instance.lane_host) == 0 && length(aws_budgets_budget_action.stop_lane_hosts) == 0 && length(aws_security_group.lane_host) == 0
    error_message = "lane_host_count defaults to 0: no lane host, budget action or SG."
  }

  assert {
    condition     = tolist(one([for f in aws_budgets_budget.prod.cost_filter : f.values if f.name == "InstanceType"])) == tolist(["m8g.xlarge"])
    error_message = "the prod budget must filter on the prod instance type."
  }
}

run "lane_host_on" {
  command = plan

  variables {
    lane_host_count                      = 1
    lane_host_dispatcher_authorized_keys = ["ssh-ed25519 AAAAdispatcher compute@mini"]
  }

  assert {
    condition     = aws_instance.lane_host[0].instance_type == "r8g.xlarge" && aws_instance.lane_host[0].tags["Role"] == "lane-host"
    error_message = "lane host must be r8g.xlarge tagged Role=lane-host."
  }

  assert {
    condition     = !aws_instance.lane_host[0].disable_api_stop
    error_message = "the budget action and idle-stop must be able to stop the lane host."
  }

  assert {
    condition     = aws_instance.lane_host[0].metadata_options[0].http_tokens == "required"
    error_message = "lane host must require IMDSv2."
  }

  assert {
    condition     = aws_budgets_budget.lane_host[0].limit_amount == "250.00"
    error_message = "the operator-approved lane-host cap is USD 250."
  }

  assert {
    condition     = aws_budgets_budget_action.stop_lane_hosts[0].definition[0].ssm_action_definition[0].instance_ids == toset(aws_instance.lane_host[*].id)
    error_message = "the stop action must target exactly the lane hosts."
  }

  assert {
    condition     = aws_budgets_budget_action.stop_lane_hosts[0].definition[0].ssm_action_definition[0].action_sub_type == "STOP_EC2_INSTANCES" && aws_budgets_budget_action.stop_lane_hosts[0].approval_model == "AUTOMATIC"
    error_message = "the cap must stop instances automatically."
  }

  assert {
    condition     = !strcontains(aws_instance.lane_host[0].user_data, "tskey-")
    error_message = "no Tailscale key material in user_data; it is read from SSM at boot."
  }

  assert {
    condition     = local.lane_host_names == ["lanes-eun1-1"] && yamldecode(trimprefix(aws_instance.lane_host[0].user_data, "#cloud-config\n")).hostname == "lanes-eun1-1"
    error_message = "host #1 must be lanes-eun1-1, the compute 1.6.0 policy key (ssh: lanes@lanes-eun1-1)."
  }

  assert {
    condition = alltrue([
      for k in one(yamldecode(trimprefix(aws_instance.lane_host[0].user_data, "#cloud-config\n")).users).ssh_authorized_keys :
      startswith(k, "from=\"100.64.0.0/10,fd7a:115c:a1e0::/48\",")
    ]) && one(yamldecode(trimprefix(aws_instance.lane_host[0].user_data, "#cloud-config\n")).users).name == "lanes"
    error_message = "the dispatcher key belongs to the lanes account and only from tailnet source addresses."
  }

  assert {
    condition = alltrue([
      strcontains(one([for f in yamldecode(trimprefix(aws_instance.lane_host[0].user_data, "#cloud-config\n")).write_files : f.content if f.path == "/etc/ssh/sshd_config.d/10-antiek-lane-host.conf"]), "PermitRootLogin no"),
      yamldecode(trimprefix(aws_instance.lane_host[0].user_data, "#cloud-config\n")).disable_root,
    ])
    error_message = "root has no SSH login on a lane host."
  }

  assert {
    condition = alltrue([
      strcontains(one([for f in yamldecode(trimprefix(aws_instance.lane_host[0].user_data, "#cloud-config\n")).write_files : f.content if f.path == "/etc/default/antiek-lane-host"]), "LANES_SLICE_MEMORY_MAX=26G"),
      strcontains(one([for f in yamldecode(trimprefix(aws_instance.lane_host[0].user_data, "#cloud-config\n")).write_files : f.content if f.path == "/etc/systemd/system/user-.slice.d/50-lanes-ceiling.conf"]), "MemoryMax=28G"),
      strcontains(one([for f in yamldecode(trimprefix(aws_instance.lane_host[0].user_data, "#cloud-config\n")).write_files : f.content if f.path == "/etc/systemd/system/user@.service.d/50-lanes-delegate.conf"]), "memory pids"),
    ])
    error_message = "the user lanes.slice limit, the root-owned user-slice ceiling and controller delegation must all be rendered."
  }

  assert {
    condition     = !strcontains(aws_instance.lane_host[0].user_data, "secrets.env") && !strcontains(aws_instance.lane_host[0].user_data, "ANTIEK_")
    error_message = "no Antiek configuration or credentials on a lane host (D-18/D-19)."
  }
}

run "x86_fallback" {
  command = plan

  variables {
    prod_arch = "x86_64"
  }

  override_data {
    target = data.aws_ec2_instance_type.prod
    values = { supported_architectures = ["x86_64", "i386"] }
  }

  assert {
    condition     = aws_instance.prod.instance_type == "m7i.xlarge"
    error_message = "x86_64 fallback must select m7i.xlarge."
  }

  assert {
    condition     = strcontains(data.aws_ssm_parameter.ubuntu_prod[0].name, "/amd64/")
    error_message = "x86_64 must resolve Canonical's amd64 AMI."
  }
}

run "arch_mismatch_is_refused" {
  command = plan

  variables {
    prod_instance_type = "m7i.xlarge"
  }

  override_data {
    target = data.aws_ec2_instance_type.prod
    values = { supported_architectures = ["x86_64"] }
  }

  expect_failures = [aws_instance.prod]
}

run "lane_type_equal_to_prod_type_is_refused" {
  command = plan

  variables {
    lane_host_count         = 1
    lane_host_instance_type = "m8g.xlarge"
  }

  expect_failures = [aws_instance.lane_host]
}

run "other_region_is_refused" {
  command = plan

  variables {
    region = "me-central-1"
  }

  expect_failures = [var.region]
}

# The 10-07 plan's Region. The project's SCP denies it (README.md), so the
# root refuses it at plan rather than failing every API call at apply.
run "eu_central_1_is_refused" {
  command = plan

  variables {
    region = "eu-central-1"
  }

  expect_failures = [var.region]
}

# Measured 2026-10-07: the new project's On-Demand Standard vCPU quota is 5.
# Prod (4) fits; prod + one lane host (8) must fail at plan, not at launch.
run "quota_too_small_is_refused" {
  command = plan

  variables {
    lane_host_count = 1
  }

  override_data {
    target = data.aws_servicequotas_service_quota.ondemand_standard_vcpus
    values = { value = 5 }
  }

  expect_failures = [aws_instance.lane_host]
}

run "key_with_options_is_refused" {
  command = plan

  variables {
    root_authorized_keys = ["command=\"/bin/true\" ssh-ed25519 AAAAx y"]
  }

  expect_failures = [var.root_authorized_keys]
}
