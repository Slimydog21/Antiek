# ──────────────────────────────────────────────────────────────────────────────
# Lane hosts: Antiek-owned Linux capacity for the compute dispatcher's `node`
# backend (~/.agents/compute, adapter ssh_systemd_run, D-19 / ACTIVATION §N,
# compute 1.6.0 policy entry hosts.nodes.lanes-eun1-1). Not production: a
# separate instance, security group, role and data volume, and nothing
# Antiek on it.
#
# Why this shape (docs/decisions/aws-production-and-agent-backbone-2026-10-07.md):
# agent lanes are waiting-bound (1-5% CPU), RAM-bound (0.5-1 GiB) and
# file-bound, so per-sandbox metering bills mostly idle wait. Packing ~24
# lanes into one r8g.xlarge under cgroups costs ~USD 8.40 per lane-month
# on-demand in eu-north-1 (USD 201.62 all-in / 24; README.md) against
# ~USD 24.5 (Prime, launch rate) and ~USD 30.5 (Modal Sandbox).
#
# The contract with compute 1.6.0 (its CHANGELOG "host checks"), all made
# here at first boot so the host arrives checkable:
#   - account `lanes`, no sudo, key-only SSH from tailnet addresses only;
#     root has no SSH login (break-glass is SSM Session Manager);
#   - lingering user manager with memory/pids/cpu delegated, and a user
#     lanes.slice carrying the aggregate limits: every lane is a transient
#     USER unit (`systemd-run --user --slice=lanes.slice`), so neither the
#     dispatcher nor the lanes account ever needs root;
#   - workroot /srv/lanes on its own volume, owned by lanes;
#   - ~lanes/.config/compute/ (0700) for the per-node key file, which the
#     operator provisions later (D-18/D-19: never copied from the Mini).
#
# Network: NO inbound rule at all. The host joins the tailnet outbound
# (tag:compute-node) and the dispatcher reaches sshd over WireGuard; ufw on
# the host admits only tailscale0:22 as a second layer.
#
# Cost controls: lanes-idle-stop powers the host off when idle; the
# lane-host budget (budgets.tf) stops it at 100% of USD 250 actual. Stop
# protection is therefore deliberately OFF here.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_security_group" "lane_host" {
  count = var.lane_host_count > 0 ? 1 : 0

  name        = "antiek-lane-host"
  description = "Antiek lane hosts: no inbound. Reached only over Tailscale (outbound-initiated)."
  vpc_id      = aws_vpc.this.id

  tags = { Name = "antiek-lane-host", Role = "lane-host" }
}

resource "aws_vpc_security_group_egress_rule" "lane_host_all_ipv4" {
  count = var.lane_host_count > 0 ? 1 : 0

  security_group_id = aws_security_group.lane_host[0].id
  description       = "Tailscale coordination/DERP, provider APIs, apt, SSM"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "lane_host_all_ipv6" {
  count = var.lane_host_count > 0 && var.enable_ipv6 ? 1 : 0

  security_group_id = aws_security_group.lane_host[0].id
  ip_protocol       = "-1"
  cidr_ipv6         = "::/0"
}

resource "aws_ebs_volume" "lane_data" {
  count = var.lane_host_count

  availability_zone = local.availability_zone
  type              = "gp3"
  size              = var.lane_host_data_volume_gib
  encrypted         = true

  tags = {
    Name = "${local.lane_host_names[count.index]}-data"
    Role = "lane-host"
  }
}

locals {
  lane_host_names = [for i in range(var.lane_host_count) : format("%s-%d", var.lane_host_name_prefix, i + 1)]

  # Tailscale's IPv4 CGNAT range and IPv6 ULA prefix: the dispatcher's key
  # works only from inside the tailnet even if a rule ever opened port 22.
  lane_host_key_lines = [
    for k in var.lane_host_dispatcher_authorized_keys :
    "from=\"100.64.0.0/10,fd7a:115c:a1e0::/48\",no-agent-forwarding,no-port-forwarding,no-X11-forwarding ${k}"
  ]

  lane_host_cloud_config = [
    for i in range(var.lane_host_count) : {
      hostname          = local.lane_host_names[i]
      preserve_hostname = false
      ssh_pwauth        = false
      # No default "ubuntu" user and no root login: `lanes` is the only SSH
      # account (cloud-init creates it before runcmd, so the data-volume
      # script finds it).
      disable_root = true
      users = [{
        name                = "lanes"
        gecos               = "compute lanes (D-19)"
        shell               = "/bin/bash"
        lock_passwd         = true
        ssh_authorized_keys = local.lane_host_key_lines
      }]

      write_files = [
        {
          path        = "/etc/ssh/sshd_config.d/10-antiek-lane-host.conf"
          permissions = "0644"
          content     = <<-EOT
            # cloud-init (infrastructure/terraform-aws/lane_host.tf)
            PermitRootLogin no
            PasswordAuthentication no
            KbdInteractiveAuthentication no
            AllowUsers lanes
          EOT
        },
        {
          path        = "/etc/default/antiek-lane-host"
          permissions = "0644"
          content     = <<-EOT
            AWS_REGION=${var.region}
            TAILSCALE_AUTHKEY_PARAM=${var.tailscale_authkey_param}
            TAILSCALE_HOSTNAME=${local.lane_host_names[i]}
            TAILSCALE_TAGS=${var.tailscale_tags}
            LANES_USER=lanes
            LANES_WORKROOT=/srv/lanes
            LANES_SLICE_MEMORY_HIGH=${var.lanes_slice_memory_high}
            LANES_SLICE_MEMORY_MAX=${var.lanes_slice_memory_max}
            LANES_SLICE_TASKS_MAX=${var.lanes_slice_tasks_max}
            LANES_IDLE_STOP_MINUTES=${var.lane_host_idle_stop_minutes}
          EOT
        },
        {
          # systemd >= 252 already delegates these to user@.service; saying
          # so here makes the compute host check ("memory/pids/cpu listed in
          # user@UID.service cgroup.controllers") independent of the default.
          path        = "/etc/systemd/system/user@.service.d/50-lanes-delegate.conf"
          permissions = "0644"
          content     = <<-EOT
            [Service]
            Delegate=cpu cpuset io memory pids
          EOT
        },
        {
          # Root-owned outer ceiling for every user-<uid>.slice. The lanes
          # account owns its own lanes.slice file and could raise it; it
          # cannot raise this one.
          path        = "/etc/systemd/system/user-.slice.d/50-lanes-ceiling.conf"
          permissions = "0644"
          content     = <<-EOT
            [Slice]
            MemoryMax=${var.lane_host_user_slice_memory_max}
          EOT
        },
        {
          path        = "/etc/systemd/system/lanes-idle-stop.service"
          permissions = "0644"
          content     = <<-EOT
            [Unit]
            Description=Power the lane host off when no lane has run for LANES_IDLE_STOP_MINUTES

            [Service]
            Type=oneshot
            ExecStart=/usr/local/sbin/lanes-idle-stop
          EOT
        },
        {
          path        = "/etc/systemd/system/lanes-idle-stop.timer"
          permissions = "0644"
          content     = <<-EOT
            [Unit]
            Description=Check lane-host idleness every 5 minutes

            [Timer]
            OnBootSec=15min
            OnUnitActiveSec=5min

            [Install]
            WantedBy=timers.target
          EOT
        },
        {
          path        = "/usr/local/sbin/attach-data-volume"
          permissions = "0755"
          content     = file("${path.module}/scripts/attach-data-volume.sh")
        },
        {
          path        = "/usr/local/sbin/lane-host-bootstrap"
          permissions = "0755"
          content     = file("${path.module}/scripts/lane-host-bootstrap.sh")
        },
        {
          path        = "/usr/local/sbin/lanes-idle-stop"
          permissions = "0755"
          content     = file("${path.module}/scripts/lanes-idle-stop.sh")
        },
      ]

      runcmd = [
        ["systemctl", "try-reload-or-restart", "ssh.service"],
        ["systemctl", "daemon-reload"],
        ["/usr/local/sbin/attach-data-volume", aws_ebs_volume.lane_data[i].id, "/srv/lanes", "lanes", "antiek-lanes"],
        ["/usr/local/sbin/lane-host-bootstrap"],
      ]
    }
  ]
}

resource "aws_instance" "lane_host" {
  count = var.lane_host_count

  ami                    = try(data.aws_ssm_parameter.ubuntu_lane_host[0].insecure_value, null)
  instance_type          = var.lane_host_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.lane_host[0].id]
  iam_instance_profile   = aws_iam_instance_profile.lane_host[0].name
  ipv6_address_count     = var.enable_ipv6 ? 1 : 0

  # Outbound to the tailnet, provider APIs and SSM without a NAT gateway.
  associate_public_ip_address = true

  # The budget action and lanes-idle-stop must be able to stop this host.
  disable_api_stop                     = false
  disable_api_termination              = false
  instance_initiated_shutdown_behavior = "stop"

  dynamic "instance_market_options" {
    for_each = var.lane_host_use_spot ? [1] : []

    content {
      market_type = "spot"

      spot_options {
        spot_instance_type             = "persistent"
        instance_interruption_behavior = "stop"
      }
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.lane_host_root_volume_gib
    encrypted             = true
    delete_on_termination = true
    tags = {
      Name = "${local.lane_host_names[count.index]}-root"
      Role = "lane-host"
    }
  }

  user_data                   = "#cloud-config\n${yamlencode(local.lane_host_cloud_config[count.index])}"
  user_data_replace_on_change = true

  tags = {
    Name = local.lane_host_names[count.index]
    Role = "lane-host"
  }

  lifecycle {
    # Lane hosts are cattle: a newer AMI is picked up on the next deliberate
    # replace (terraform apply -replace), not on every plan.
    ignore_changes = [ami]

    precondition {
      condition     = contains(data.aws_ec2_instance_type.lane_host.supported_architectures, var.lane_host_arch)
      error_message = "${var.lane_host_instance_type} does not support ${var.lane_host_arch}."
    }

    precondition {
      condition     = var.lane_host_instance_type != local.prod_instance_type
      error_message = "The lane-host budget isolates lane-host cost by instance type; it must differ from the prod type (${local.prod_instance_type})."
    }

    precondition {
      condition     = local.ondemand_vcpus_needed <= data.aws_servicequotas_service_quota.ondemand_standard_vcpus.value && local.spot_vcpus_needed <= data.aws_servicequotas_service_quota.spot_standard_vcpus.value
      error_message = "prod + lane hosts need ${local.ondemand_vcpus_needed} On-Demand and ${local.spot_vcpus_needed} Spot vCPUs; the quotas are ${data.aws_servicequotas_service_quota.ondemand_standard_vcpus.value} (L-1216C47A) and ${data.aws_servicequotas_service_quota.spot_standard_vcpus.value} (L-34B43A08). Request an increase first (README.md)."
    }
  }
}

resource "aws_volume_attachment" "lane_data" {
  count = var.lane_host_count

  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.lane_data[count.index].id
  instance_id = aws_instance.lane_host[count.index].id
}
