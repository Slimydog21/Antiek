# ──────────────────────────────────────────────────────────────────────────────
# Lane hosts: Antiek-owned Linux capacity for the compute dispatcher's `node`
# backend (~/.agents/compute, adapter ssh_systemd_run, D-19 / ACTIVATION §N,
# compute 1.6.0 policy entry hosts.nodes.lanes-1). Not production: a separate
# instance, security group, role and data volume, and nothing Antiek on it.
#
# Why this shape (docs/decisions/aws-production-and-agent-backbone-2026-10-07.md):
# agent lanes are waiting-bound (1-5% CPU), RAM-bound (0.5-1 GiB) and
# file-bound, so per-sandbox metering bills mostly idle wait. Packing ~24
# lanes into one r8g.xlarge under cgroups costs ~USD 8.40 per lane-month
# on-demand in eu-north-1 (USD 201.62 all-in / 24; README.md) against
# ~USD 24.5 (Prime, launch rate) and ~USD 30.5 (Modal Sandbox).
#
# The contract with compute (policy.yaml, the comment above hosts.nodes, and
# bin/compute-lane-host; `compute doctor` verifies it over SSH). compute owns
# it; this file installs it and re-encodes none of it:
#   - control account `compute`: key-only SSH from tailnet addresses, in
#     systemd-journal and every lane-<project> group, and exactly one sudoers
#     line, for the helper. Root has no SSH login (break-glass is SSM);
#   - one system user + group lane-<project> per tenant (no shell, no home).
#     Every lane is a transient SYSTEM unit the helper starts as that user
#     under lanes.slice (NoNewPrivileges, ProtectSystem=strict, PrivateTmp,
#     IPAddressDeny=IMDS), so a lane cannot forge its exit record, leave the
#     slice, read another tenant's workdir or any key it was not given;
#   - compute's helper, byte for byte from var.compute_lane_host_helper, at
#     /usr/local/sbin/compute-lane-host (root 0755), configured by
#     /etc/compute/lane-host.json; per-node keys in /etc/compute/keys (root
#     0700; the operator writes them later, D-18/D-19);
#   - a system lanes.slice whose MemoryMax caps all lanes together;
#   - workroot /srv/lanes on its own volume: <project> dirs lane-<p> 2770,
#     .records owned by compute 0750;
#   - compute-lane-host-sweep.timer, every 5 min: the dead man, the workdir
#     TTLs and stop-when-idle. Idle poweroff has exactly that one owner.
#
# Added here, outside compute's contract:
#   - lane-host-failsafe.timer, armed before anything that can fail: powers
#     the host off 60 min after a boot on which it is not provisioned, its
#     workroot is not mounted or the sweep is not running (L11/L17/L21);
#   - the metadata service answers root only (nftables). The instance role
#     exists for the SSM agent and the boot-time key fetch, both root; lanes
#     and the control account see no role (compute doctor's IMDS check);
#   - /tmp and /var/tmp are tmpfs, so the only disk a lane can write is its
#     workdir on the data volume (PrivateTmp lives on them, charged to the
#     lane's memory cgroup): lanes cannot fill the root disk (L8);
#   - outbound into the tailnet is denied on the host (ufw), and Tailscale
#     never takes over DNS.
#
# Network: NO inbound rule at all. The host joins the tailnet outbound
# (tag:compute-node) and the dispatcher reaches sshd over WireGuard.
#
# Cost controls (budgets.tf): the sweep's idle stop; a daily wake (below) so
# the backbone returns after idle stops; an alerting budget at expected
# spend; a cap budget whose actions stop the hosts and detach the wake's
# permission. Stop protection is therefore deliberately OFF here.
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

  # compute's names for the host side of the contract (policy.yaml
  # backends.node / hosts.nodes, bin/compute-lane-host defaults).
  # tests/test_terraform_aws_invariants.py compares them with the compute
  # policy whenever one with a hosts.nodes entry is present.
  lane_host_control_user = "compute"
  lane_host_user_prefix  = "lane-"
  lane_host_workroot     = "/srv/lanes"
  lane_host_slice        = "lanes.slice"
  lane_host_helper_path  = "/usr/local/sbin/compute-lane-host"
  lane_host_key_dir      = "/etc/compute/keys"

  lane_host_helper_src = pathexpand(var.compute_lane_host_helper)

  # Tailscale's IPv4 CGNAT range and IPv6 ULA prefix: the dispatcher's key
  # works only from inside the tailnet even if a rule ever opened port 22.
  lane_host_key_lines = [
    for k in var.lane_host_dispatcher_authorized_keys :
    "from=\"100.64.0.0/10,fd7a:115c:a1e0::/48\",no-agent-forwarding,no-port-forwarding,no-X11-forwarding ${k}"
  ]

  # bin/compute-lane-host.example.json, filled from this root's variables.
  lane_host_helper_config = jsonencode({
    workroot    = local.lane_host_workroot
    slice       = local.lane_host_slice
    systemd_run = "/usr/bin/systemd-run"
    systemctl   = "/usr/bin/systemctl"
    user_prefix = local.lane_host_user_prefix
    key_dir     = local.lane_host_key_dir
    keys        = var.lane_host_provider_keys
    projects    = var.lane_host_projects
    extra       = ["--expand-environment=no"]
    # deadman_min and no_retention_ceiling_h MUST equal compute policy
    # backends.node.deadman_min and the helper example (compute 1.6.1);
    # tests/test_terraform_aws_invariants.py pins the values.
    deadman_min            = 60
    no_retention_ceiling_h = 24
    ttl_days_ok            = 7
    ttl_days_failed        = 14
    idle_poweroff_min      = var.lane_host_idle_stop_minutes
  })

  lane_host_cloud_config = [
    for i in range(var.lane_host_count) : {
      hostname          = local.lane_host_names[i]
      preserve_hostname = false
      ssh_pwauth        = false
      # Host keys survive the reprovision path (`cloud-init clean --reboot`,
      # lane-host.md) so the key pinned in the Mini's known_hosts stays
      # valid. Canonical's AMIs ship no host keys; first boot generates them.
      ssh_deletekeys  = false
      ssh_genkeytypes = ["ed25519", "ecdsa", "rsa"]
      # No default "ubuntu" user and no root login: `compute` is the only
      # SSH account (created before runcmd, so the bootstrap finds it).
      disable_root = true
      users = [{
        name                = local.lane_host_control_user
        gecos               = "compute dispatcher control account (D-19)"
        shell               = "/bin/bash"
        lock_passwd         = true
        ssh_authorized_keys = local.lane_host_key_lines
      }]

      # tmpfs /tmp and /var/tmp: lane units write only their workdir
      # (ProtectSystem=strict) and their PrivateTmp, which lives here and is
      # charged to the lane's own memory cgroup. Nothing a lane does can fill
      # the root volume that sshd, journald and tailscaled live on.
      mounts = [
        ["tmpfs", "/tmp", "tmpfs", "mode=1777,nosuid,nodev,size=8G", "0", "0"],
        ["tmpfs", "/var/tmp", "tmpfs", "mode=1777,nosuid,nodev,size=4G", "0", "0"],
      ]

      write_files = [
        {
          path        = "/etc/ssh/sshd_config.d/10-antiek-lane-host.conf"
          permissions = "0644"
          content     = <<-EOT
            # cloud-init (infrastructure/terraform-aws/lane_host.tf)
            PermitRootLogin no
            PasswordAuthentication no
            KbdInteractiveAuthentication no
            AllowUsers ${local.lane_host_control_user}
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
            LANES_CONTROL_USER=${local.lane_host_control_user}
            LANES_USER_PREFIX=${local.lane_host_user_prefix}
            LANES_PROJECTS="${join(" ", sort(keys(var.lane_host_projects)))}"
            LANES_WORKROOT=${local.lane_host_workroot}
            LANES_SLICE=${local.lane_host_slice}
            LANES_HELPER=${local.lane_host_helper_path}
            LANE_HOST_FAILSAFE_MINUTES=${var.lane_host_failsafe_minutes}
          EOT
        },
        {
          path        = "/etc/compute/lane-host.json"
          permissions = "0644"
          content     = "${local.lane_host_helper_config}\n"
        },
        {
          path        = local.lane_host_helper_path
          owner       = "root:root"
          permissions = "0755"
          content     = file(local.lane_host_helper_src)
        },
        {
          path        = "/etc/systemd/system/${local.lane_host_slice}"
          permissions = "0644"
          content     = <<-EOT
            # cloud-init (infrastructure/terraform-aws/lane_host.tf). Every
            # compute lane is a system unit in this slice; these limits cap
            # them together. Per-lane limits come from each unit.
            [Unit]
            Description=compute lanes (compute-lane-host start)

            [Slice]
            MemoryAccounting=yes
            MemoryHigh=${var.lanes_slice_memory_high}
            MemoryMax=${var.lanes_slice_memory_max}
            TasksAccounting=yes
            TasksMax=${var.lanes_slice_tasks_max}
            CPUAccounting=yes
          EOT
        },
        {
          path        = "/etc/systemd/system/compute-lane-host-sweep.service"
          permissions = "0644"
          content     = <<-EOT
            [Unit]
            Description=compute-lane-host sweep: lane dead man, workdir TTLs, stop when idle
            RequiresMountsFor=${local.lane_host_workroot}

            [Service]
            Type=oneshot
            ExecStart=${local.lane_host_helper_path} sweep
          EOT
        },
        {
          path        = "/etc/systemd/system/compute-lane-host-sweep.timer"
          permissions = "0644"
          content     = <<-EOT
            [Unit]
            Description=compute-lane-host sweep every 5 minutes

            [Timer]
            OnBootSec=5min
            OnUnitActiveSec=5min

            [Install]
            WantedBy=timers.target
          EOT
        },
        {
          path        = "/etc/systemd/system/lane-host-failsafe.service"
          permissions = "0644"
          content     = <<-EOT
            [Unit]
            Description=Power off a lane host that is not provisioned, mounted and sweeping

            [Service]
            Type=oneshot
            ExecStart=/usr/local/sbin/lane-host-failsafe
          EOT
        },
        {
          path        = "/etc/systemd/system/lane-host-failsafe.timer"
          permissions = "0644"
          content     = <<-EOT
            [Unit]
            Description=Lane-host failsafe, once per boot

            [Timer]
            OnBootSec=${var.lane_host_failsafe_minutes}min

            [Install]
            WantedBy=timers.target
          EOT
        },
        {
          path        = "/etc/nftables.d/antiek-imds-root-only.nft"
          permissions = "0644"
          content     = <<-EOT
            # Instance metadata for root only (lane_host.tf). Its own table,
            # independent of ufw's rules.
            table inet antiek_imds
            delete table inet antiek_imds
            table inet antiek_imds {
              chain output {
                type filter hook output priority 0; policy accept;
                ip daddr 169.254.169.254 meta skuid != 0 counter reject
                ip6 daddr fd00:ec2::254 meta skuid != 0 counter reject
              }
            }
          EOT
        },
        {
          path        = "/etc/systemd/system/imds-root-only.service"
          permissions = "0644"
          content     = <<-EOT
            [Unit]
            Description=Instance metadata reachable by root only
            DefaultDependencies=no
            Before=network-pre.target
            Wants=network-pre.target

            [Service]
            Type=oneshot
            RemainAfterExit=yes
            ExecStart=/usr/sbin/nft -f /etc/nftables.d/antiek-imds-root-only.nft
            ExecStop=/usr/sbin/nft delete table inet antiek_imds

            [Install]
            WantedBy=multi-user.target
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
          path        = "/usr/local/sbin/lane-host-failsafe"
          permissions = "0755"
          content     = file("${path.module}/scripts/lane-host-failsafe.sh")
        },
      ]

      # The failsafe is armed FIRST: every later step can fail or hang, and
      # cloud-init runs runcmd once per instance, so nothing would retry.
      runcmd = [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "lane-host-failsafe.timer"],
        ["systemctl", "try-reload-or-restart", "ssh.service"],
        ["/usr/local/sbin/attach-data-volume", aws_ebs_volume.lane_data[i].id, local.lane_host_workroot, "root", "antiek-lanes"],
        ["/usr/local/sbin/lane-host-bootstrap"],
      ]
    }
  ]

  # Delivered gzipped (user_data_base64 below): compute's helper and the
  # three scripts alone are 25 KB, over EC2's 16 KiB of user data, which a
  # run with the real helper (compute 406a856) hit. cloud-init detects and
  # inflates gzip itself.
  lane_host_user_data = [for c in local.lane_host_cloud_config : "#cloud-config\n${yamlencode(c)}"]
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

  # The budget action and the sweep's idle stop must be able to stop it.
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

  # A user_data edit (a key rotation, a slice size, a new helper) is an
  # in-place stop/start, never a replacement: a replaced host re-joins the
  # tailnet under a suffixed name compute cannot reach, and needs a fresh
  # auth key. cloud-init does not re-run on a restart; the reprovision step
  # in lane-host.md applies the new user data (`cloud-init clean --reboot`).
  user_data_base64            = base64gzip(local.lane_host_user_data[count.index])
  user_data_replace_on_change = false

  tags = {
    Name = local.lane_host_names[count.index]
    Role = "lane-host"
    # Which compute helper this host was given; lane-host.md compares it
    # with the Mini's copy.
    ComputeHelperSha256 = filesha256(local.lane_host_helper_src)
  }

  lifecycle {
    # A newer AMI is picked up on the next deliberate replace (terraform
    # apply -replace, lane-host.md), not on every plan.
    ignore_changes = [ami]

    precondition {
      condition     = contains(data.aws_ec2_instance_type.lane_host.supported_architectures, var.lane_host_arch)
      error_message = "${var.lane_host_instance_type} does not support ${var.lane_host_arch}."
    }

    precondition {
      condition     = contains(lookup(local.azs_offering, var.lane_host_instance_type, []), coalesce(local.availability_zone, "none"))
      error_message = "${var.lane_host_instance_type} is not offered in ${coalesce(local.availability_zone, "the prod AZ")}, which prod's type decides. Choose a lane type offered there; never move prod's AZ for a lane host."
    }

    precondition {
      condition     = startswith(file(local.lane_host_helper_src), "#!/usr/bin/python3") && strcontains(file(local.lane_host_helper_src), "def op_sweep")
      error_message = "${local.lane_host_helper_src} is not compute's bin/compute-lane-host (compute_lane_host_helper)."
    }

    # EC2 limits user data to 16 KiB before base64: here, the gzip stream.
    precondition {
      condition     = length(base64gzip(local.lane_host_user_data[count.index])) <= 21848
      error_message = "lane-host user_data is over EC2's 16 KiB limit."
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

# ── Daily wake ───────────────────────────────────────────────────────────────
# The sweep stops an idle host and compute never calls AWS, so without this
# the backbone is up only between manual starts and every lane placed while
# it is stopped falls through to the Mini. EventBridge Scheduler starts the
# host(s) once a day; the sweep stops them again after idle_poweroff_min if
# nothing arrives. The role may start only Role=lane-host instances, and the
# cap budget's second action detaches that permission (budgets.tf), so a
# capped host is not woken.
resource "aws_scheduler_schedule" "lane_host_wake" {
  count = var.lane_host_count > 0 && var.lane_host_wake_schedule != null ? 1 : 0

  name                         = "antiek-lane-host-wake"
  schedule_expression          = var.lane_host_wake_schedule
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
    role_arn = aws_iam_role.lane_host_wake[0].arn
    input    = jsonencode({ InstanceIds = aws_instance.lane_host[*].id })

    retry_policy {
      maximum_retry_attempts = 3
    }
  }
}
