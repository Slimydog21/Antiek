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

  # eu-north-1a lacks r8g.xlarge in this fixture. The AZ is derived from the
  # prod type alone, so it stays 1a; a lane host there is refused unless the
  # operator pins an AZ that offers both (1b).
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

  mock_resource "aws_iam_policy" {
    defaults = { arn = "arn:aws:iam::123456789012:policy/antiek-deny-lane-host-wake" }
  }

  mock_resource "aws_scheduler_schedule" {
    defaults = { arn = "arn:aws:scheduler:eu-north-1:123456789012:schedule/default/antiek-lane-host-wake" }
  }
}

variables {
  alert_email          = "ops@example.invalid"
  ssh_ingress_cidrs    = ["0.0.0.0/0"]
  root_authorized_keys = ["ssh-ed25519 AAAAoperator operator", "ssh-ed25519 AAAAdeploy github-actions-deploy@antiek"]
  # compute's helper lives in ~/.agents/compute, not in this repository.
  compute_lane_host_helper = "tests/fixtures/compute-lane-host"
}

run "prod_defaults" {
  command = plan

  assert {
    condition     = aws_instance.prod.instance_type == "m8g.xlarge"
    error_message = "arm64 default must select m8g.xlarge."
  }

  assert {
    condition     = local.availability_zone == "eu-north-1a"
    error_message = "AZ must follow the prod type alone (first AZ offering m8g.xlarge), whatever the lane-host type."
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

  # 744 h x 0.19076 = 141.92 < 150 < 2 instances: one host never alerts, two do.
  assert {
    condition     = aws_budgets_budget.prod.limit_amount == "150.00"
    error_message = "the prod budget must sit just above one m8g.xlarge month (USD 150)."
  }
}

run "lane_host_on" {
  command = plan

  variables {
    lane_host_count                      = 1
    availability_zone                    = "eu-north-1b"
    lane_host_dispatcher_authorized_keys = ["ssh-ed25519 AAAAdispatcher compute@mini"]
  }

  assert {
    condition     = aws_instance.lane_host[0].instance_type == "r8g.xlarge" && aws_instance.lane_host[0].tags["Role"] == "lane-host"
    error_message = "lane host must be r8g.xlarge tagged Role=lane-host."
  }

  assert {
    condition     = !aws_instance.lane_host[0].disable_api_stop
    error_message = "the budget action and the sweep's idle stop must be able to stop the lane host."
  }

  assert {
    condition     = aws_instance.lane_host[0].metadata_options[0].http_tokens == "required" && aws_instance.lane_host[0].metadata_options[0].http_put_response_hop_limit == 1
    error_message = "lane host must require IMDSv2 with hop limit 1."
  }

  assert {
    condition     = !aws_instance.lane_host[0].user_data_replace_on_change
    error_message = "a user_data edit must be an in-place stop/start, never a replacement (a new tailnet name, a fresh key)."
  }

  assert {
    condition     = aws_instance.lane_host[0].tags["ComputeHelperSha256"] == filesha256("tests/fixtures/compute-lane-host")
    error_message = "the instance must carry the sha256 of the helper it was given."
  }

  # Budgets: alerts at expected spend, the cap at 250 minus fixed costs.
  assert {
    condition     = aws_budgets_budget.lane_host[0].limit_amount == "100.00" && length([for n in aws_budgets_budget.lane_host[0].notification : n if n.notification_type == "ACTUAL"]) == 2
    error_message = "the lane-host alert budget must measure expected spend (USD 100) with ACTUAL alerts at 80% and 100%."
  }

  # 250 - (30 + 150) GiB x 0.0836 - 3.65 - 10 = 221.30
  assert {
    condition     = aws_budgets_budget.lane_host_cap[0].limit_amount == "221.30"
    error_message = "the cap budget must be USD 250 minus the host's fixed EBS + IPv4 and the egress allowance."
  }

  assert {
    condition     = aws_budgets_budget_action.stop_lane_hosts[0].budget_name == "antiek-lane-host-cap" && aws_budgets_budget_action.stop_lane_hosts[0].definition[0].ssm_action_definition[0].instance_ids == toset(aws_instance.lane_host[*].id)
    error_message = "the stop action must hang off the cap budget and target exactly the lane hosts."
  }

  assert {
    condition     = aws_budgets_budget_action.stop_lane_hosts[0].definition[0].ssm_action_definition[0].action_sub_type == "STOP_EC2_INSTANCES" && aws_budgets_budget_action.stop_lane_hosts[0].approval_model == "AUTOMATIC"
    error_message = "the cap must stop instances automatically."
  }

  assert {
    condition     = aws_budgets_budget_action.block_lane_host_wake[0].action_type == "APPLY_IAM_POLICY" && aws_budgets_budget_action.block_lane_host_wake[0].definition[0].iam_action_definition[0].roles == toset([aws_iam_role.lane_host_wake[0].name])
    error_message = "the cap must also detach the wake (deny policy on the wake role), or the schedule restarts a capped host."
  }

  assert {
    condition     = aws_scheduler_schedule.lane_host_wake[0].schedule_expression == "cron(0 5 * * ? *)" && jsondecode(aws_scheduler_schedule.lane_host_wake[0].target[0].input).InstanceIds == aws_instance.lane_host[*].id
    error_message = "the daily wake must start exactly the lane hosts."
  }

  # The rendered cloud-config: compute's host contract.
  assert {
    condition     = aws_instance.lane_host[0].user_data_base64 == base64gzip(local.lane_host_user_data[0]) && startswith(local.lane_host_user_data[0], "#cloud-config\n")
    error_message = "the instance must get the rendered cloud-config, gzipped (cloud-init inflates it)."
  }

  assert {
    condition     = !strcontains(local.lane_host_user_data[0], "tskey-")
    error_message = "no Tailscale key material in user_data; it is read from SSM at boot."
  }

  assert {
    condition     = length(aws_instance.lane_host[0].user_data_base64) <= 21848
    error_message = "lane-host user_data must fit EC2's 16 KiB."
  }

  assert {
    condition     = local.lane_host_names == ["lanes-1"] && yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).hostname == "lanes-1"
    error_message = "host #1 must be lanes-1, the compute policy key (ssh: compute@lanes-1)."
  }

  assert {
    condition = alltrue([
      for k in one(yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).users).ssh_authorized_keys :
      startswith(k, "from=\"100.64.0.0/10,fd7a:115c:a1e0::/48\",")
    ]) && one(yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).users).name == "compute"
    error_message = "the dispatcher key belongs to the compute control account and only from tailnet source addresses."
  }

  assert {
    condition = alltrue([
      strcontains(one([for f in yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).write_files : f.content if f.path == "/etc/ssh/sshd_config.d/10-antiek-lane-host.conf"]), "PermitRootLogin no"),
      strcontains(one([for f in yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).write_files : f.content if f.path == "/etc/ssh/sshd_config.d/10-antiek-lane-host.conf"]), "AllowUsers compute"),
      yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).disable_root,
      !yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).ssh_deletekeys,
    ])
    error_message = "root has no SSH login, compute is the only SSH account, and host keys survive a reprovision."
  }

  assert {
    condition = one([
      for f in yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).write_files : f
      if f.path == "/usr/local/sbin/compute-lane-host"
      ]) == {
      path        = "/usr/local/sbin/compute-lane-host"
      owner       = "root:root"
      permissions = "0755"
      content     = file("tests/fixtures/compute-lane-host")
    }
    error_message = "compute's helper must be installed byte for byte, root-owned 0755."
  }

  assert {
    condition = jsondecode(one([
      for f in yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).write_files : f.content
      if f.path == "/etc/compute/lane-host.json"
      ])) == {
      workroot               = "/srv/lanes"
      slice                  = "lanes.slice"
      systemd_run            = "/usr/bin/systemd-run"
      systemctl              = "/usr/bin/systemctl"
      user_prefix            = "lane-"
      key_dir                = "/etc/compute/keys"
      keys                   = ["DEEPSEEK_API_KEY", "XIAOMI_API_KEY", "ZAI_API_KEY"]
      projects               = { inferact = { retention = true }, solcoa = { retention = true }, volantis = { retention = false } }
      extra                  = ["--expand-environment=no"]
      deadman_min            = 60
      no_retention_ceiling_h = 24
      ttl_days_ok            = 7
      ttl_days_failed        = 14
      idle_poweroff_min      = 60
    }
    error_message = "the helper's config must match compute-lane-host.example.json's shape, filled from this root."
  }

  assert {
    condition = alltrue([
      strcontains(one([for f in yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).write_files : f.content if f.path == "/etc/systemd/system/lanes.slice"]), "MemoryMax=26G"),
      strcontains(one([for f in yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).write_files : f.content if f.path == "/etc/systemd/system/compute-lane-host-sweep.service"]), "ExecStart=/usr/local/sbin/compute-lane-host sweep"),
      strcontains(one([for f in yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).write_files : f.content if f.path == "/etc/systemd/system/lane-host-failsafe.timer"]), "OnBootSec=60min"),
      strcontains(one([for f in yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).write_files : f.content if f.path == "/etc/nftables.d/antiek-imds-root-only.nft"]), "ip daddr 169.254.169.254 meta skuid != 0"),
    ])
    error_message = "system lanes.slice, the helper's sweep timer, the boot failsafe and the root-only IMDS table must all be rendered."
  }

  assert {
    condition     = length([for f in yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).write_files : f if strcontains(f.path, "idle-stop") || strcontains(f.path, "user@.service")]) == 0
    error_message = "idle poweroff has one owner (the helper's sweep); no IaC idle-stop and no user-manager delegation."
  }

  # Order is the failure contract: the failsafe before anything that can fail.
  assert {
    condition = (
      index(yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).runcmd, ["systemctl", "enable", "--now", "lane-host-failsafe.timer"]) <
      index(yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).runcmd, ["/usr/local/sbin/attach-data-volume", "vol-0abc123def4567890", "/srv/lanes", "root", "antiek-lanes"])
      ) && (
      index(yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).runcmd, ["/usr/local/sbin/attach-data-volume", "vol-0abc123def4567890", "/srv/lanes", "root", "antiek-lanes"]) <
      index(yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).runcmd, ["/usr/local/sbin/lane-host-bootstrap"])
    )
    error_message = "the failsafe timer must be armed before the data volume and the bootstrap run."
  }

  assert {
    condition     = toset([for m in yamldecode(trimprefix(local.lane_host_user_data[0], "#cloud-config\n")).mounts : m[1] if m[2] == "tmpfs"]) == toset(["/tmp", "/var/tmp"])
    error_message = "/tmp and /var/tmp must be tmpfs, so no lane can fill the root volume."
  }

  assert {
    condition     = !strcontains(local.lane_host_user_data[0], "secrets.env") && !strcontains(local.lane_host_user_data[0], "ANTIEK_")
    error_message = "no Antiek configuration or credentials on a lane host (D-18/D-19)."
  }
}

# The lane type must be offered in the AZ prod's type chose (1a in the
# fixture lacks r8g.xlarge); prod's AZ never moves for a lane host.
run "lane_type_not_offered_in_prod_az_is_refused" {
  command = plan

  variables {
    lane_host_count = 1
  }

  expect_failures = [aws_instance.lane_host]
}

run "lane_host_without_wake" {
  command = plan

  variables {
    lane_host_count         = 1
    availability_zone       = "eu-north-1b"
    lane_host_wake_schedule = null
  }

  assert {
    condition     = length(aws_scheduler_schedule.lane_host_wake) == 0 && length(aws_budgets_budget_action.block_lane_host_wake) == 0 && length(aws_budgets_budget_action.stop_lane_hosts) == 1
    error_message = "without a wake there is nothing to detach; the stop action stays."
  }
}

# Two hosts: 250 - 2 x 18.70 - 10 = 202.60.
run "cap_subtracts_fixed_costs_per_host" {
  command = plan

  variables {
    lane_host_count   = 2
    availability_zone = "eu-north-1b"
  }

  assert {
    condition     = aws_budgets_budget.lane_host_cap[0].limit_amount == "202.60"
    error_message = "the cap must leave room for every host's fixed EBS + IPv4."
  }
}

run "expected_spend_above_the_cap_is_refused" {
  command = plan

  variables {
    lane_host_count                = 1
    availability_zone              = "eu-north-1b"
    lane_host_expected_monthly_usd = 240
  }

  expect_failures = [aws_budgets_budget.lane_host]
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

  # m8g.xlarge is offered in the derived AZ, so only the type rule fails.

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
    lane_host_count   = 1
    availability_zone = "eu-north-1b"
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
