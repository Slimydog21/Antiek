# ──────────────────────────────────────────────────────────────────────────────
# The production host: one EC2 instance, like-for-like with the Hetzner CCX23
# (4 vCPU / 16 GiB), plus a separate encrypted data volume at
# /home/antiek/.antiek, an Elastic IP, and a security group that admits
# tcp/22 and nothing else.
#
# Measured 2026-10-07 on the Hetzner box (prod-topology, critic): CPU 74-89%
# idle, memory 6-10% used, DuckDB 1.19 GB, disk write 2.66 MB/s at 0.17% util,
# egress ~13-20 GB/month. gp3 baseline (3,000 IOPS / 125 MiB/s) is ~50x the
# measured average I/O, and the 1.19 GB database stays in page cache, so no
# provisioned IOPS or throughput.
#
# Everything above the OS is Ansible's job, exactly as on Hetzner
# (setup.yml, then deploy_atomic.yml). cloud-init here does only what must
# exist before Ansible can connect or before the first service may start:
#   1. root SSH with the operator + deploy keys (Ubuntu AMIs disable root;
#      the deploy contract is ansible_user=root),
#   2. the data volume, found by volume id and mounted at the exact path,
#   3. RequiresMountsFor= drop-ins so no state-dir service starts without it,
#   4. the STAGING_HOLD drop-ins (see main.tf locals) so the new host cannot
#      act as production before cutover,
#   5. the host's origin-certificate declaration for Caddy (`tls internal`,
#      docs/decisions/caddy-cert-strategy-2026-10.md). Caddyfile.j2 imports
#      /etc/caddy/origin-tls.d/*.caddy, so every deploy keeps it, including
#      the CI deploy whose generated inventory carries no host variables.
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_security_group" "prod" {
  name        = "antiek-prod"
  description = "Antiek prod: tcp/22 only (deploy + operator). Ingress for the API is the Cloudflare Tunnel, outbound-only."
  vpc_id      = aws_vpc.this.id

  tags = { Name = "antiek-prod", Role = "prod" }
}

resource "aws_vpc_security_group_ingress_rule" "prod_ssh" {
  for_each = toset(var.ssh_ingress_cidrs)

  security_group_id = aws_security_group.prod.id
  description       = "SSH for the GitHub Actions deploy (root) and the operator"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = each.value

  tags = { Role = "prod" }
}

resource "aws_vpc_security_group_egress_rule" "prod_all_ipv4" {
  security_group_id = aws_security_group.prod.id
  description       = "LLM providers, R2, GitHub, apt, Cloudflare edge (tunnel)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "prod_all_ipv6" {
  count = var.enable_ipv6 ? 1 : 0

  security_group_id = aws_security_group.prod.id
  ip_protocol       = "-1"
  cidr_ipv6         = "::/0"
}

resource "aws_ebs_volume" "prod_data" {
  availability_zone = local.availability_zone
  type              = "gp3"
  size              = var.prod_data_volume_gib
  iops              = 3000
  throughput        = 125
  encrypted         = true
  final_snapshot    = true

  tags = {
    Name     = "antiek-prod-state"
    Role     = "prod"
    Snapshot = "antiek-prod-state-daily"
  }

  # The production database lives here. Destroying it takes an explicit edit
  # of this file, and even then a final snapshot is taken.
  lifecycle {
    prevent_destroy = true
  }
}

locals {
  prod_cloud_config = {
    hostname          = var.prod_hostname
    preserve_hostname = false
    # No default "ubuntu" user: root is the only login, as on Hetzner.
    users        = []
    disable_root = false
    ssh_pwauth   = false

    write_files = concat(
      [
        {
          path        = "/etc/ssh/sshd_config.d/10-antiek-root.conf"
          permissions = "0644"
          content     = <<-EOT
            # cloud-init (infrastructure/terraform-aws/prod.tf). Root is the
            # deploy identity (ansible_user=root); keys only.
            PermitRootLogin prohibit-password
            PasswordAuthentication no
            KbdInteractiveAuthentication no
          EOT
        },
        {
          path        = "/var/lib/antiek-bootstrap/root_authorized_keys"
          permissions = "0600"
          content     = "${join("\n", var.root_authorized_keys)}\n"
        },
        {
          path        = "/usr/local/sbin/attach-data-volume"
          permissions = "0755"
          content     = file("${path.module}/scripts/attach-data-volume.sh")
        },
        {
          path        = "/etc/caddy/origin-tls.d/internal.caddy"
          permissions = "0644"
          content     = <<-EOT
            # cloud-init (infrastructure/terraform-aws/prod.tf). Imported into
            # the api site block by Caddyfile.j2. The only TLS client is
            # cloudflared over loopback (noTLSVerify); ACME cannot validate
            # this host. docs/decisions/caddy-cert-strategy-2026-10.md
            tls internal
          EOT
        },
        {
          path        = local.staging_hold_file
          permissions = "0644"
          content     = <<-EOT
            This host is HELD. While this file exists, cloudflared and every
            Antiek background consumer are skipped by systemd conditions
            (/etc/systemd/system/<unit>.d/90-staging-hold.conf), so the host
            cannot serve production traffic, upload backups, sync arXiv or
            spend research budget.

            Delete this file only at step T+12 of
            infrastructure/runbooks/aws-cutover.md, after the previous
            production host's cloudflared is stopped and retired and the
            tunnel shows no connector. A DR rebuild releases it the same way.
          EOT
        },
      ],
      [for unit in local.state_dir_units : {
        path        = "/etc/systemd/system/${unit}.d/10-state-volume.conf"
        permissions = "0644"
        content     = <<-EOT
          # cloud-init (infrastructure/terraform-aws/prod.tf): never run
          # against the bare root-volume directory under the mountpoint.
          [Unit]
          RequiresMountsFor=${local.prod_state_dir}
        EOT
      }],
      [for unit in local.held_units : {
        path        = "/etc/systemd/system/${unit}.d/90-staging-hold.conf"
        permissions = "0644"
        content     = <<-EOT
          # cloud-init (infrastructure/terraform-aws/prod.tf): skipped while
          # ${local.staging_hold_file} exists. See that file.
          [Unit]
          ConditionPathExists=!${local.staging_hold_file}
        EOT
      }],
    )

    runcmd = [
      # Written here, after cloud-init's ssh module, so the file is exactly
      # these keys with no "Please login as" command prefix.
      ["install", "-d", "-m", "0700", "/root/.ssh"],
      ["install", "-m", "0600", "/var/lib/antiek-bootstrap/root_authorized_keys", "/root/.ssh/authorized_keys"],
      ["systemctl", "try-reload-or-restart", "ssh.service"],
      ["/usr/local/sbin/attach-data-volume", aws_ebs_volume.prod_data.id, local.prod_state_dir, "antiek", "antiek-state"],
      ["systemctl", "daemon-reload"],
    ]
  }
}

resource "aws_instance" "prod" {
  ami                    = coalesce(var.prod_ami_id, try(data.aws_ssm_parameter.ubuntu_prod[0].insecure_value, null))
  instance_type          = local.prod_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.prod.id]
  iam_instance_profile   = aws_iam_instance_profile.prod.name
  ipv6_address_count     = var.enable_ipv6 ? 1 : 0

  disable_api_termination              = true
  disable_api_stop                     = true
  instance_initiated_shutdown_behavior = "stop"
  monitoring                           = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.prod_root_volume_gib
    encrypted             = true
    delete_on_termination = true
    tags = {
      Name = "antiek-prod-root"
      Role = "prod"
    }
  }

  user_data                   = "#cloud-config\n${yamlencode(local.prod_cloud_config)}"
  user_data_replace_on_change = false

  tags = {
    Name = "antiek-prod"
    Role = "prod"
  }

  lifecycle {
    # A newer Ubuntu AMI or an edited cloud-config must never stop or replace
    # the production instance: user_data applies at first boot only, and an
    # AMI change would force replacement. OS updates are unattended-upgrades'
    # job; a deliberate rebuild is a runbook, not a plan diff.
    ignore_changes = [ami, user_data]

    precondition {
      condition     = contains(data.aws_ec2_instance_type.prod.supported_architectures, var.prod_arch)
      error_message = "${local.prod_instance_type} does not support ${var.prod_arch}."
    }

    precondition {
      condition     = local.prod_vcpus <= data.aws_servicequotas_service_quota.ondemand_standard_vcpus.value
      error_message = "${local.prod_instance_type} needs ${local.prod_vcpus} vCPUs; the On-Demand Standard quota (L-1216C47A) is ${data.aws_servicequotas_service_quota.ondemand_standard_vcpus.value}. Request an increase first (README.md)."
    }
  }
}

resource "aws_volume_attachment" "prod_data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.prod_data.id
  instance_id = aws_instance.prod.id

  # Detach only from a stopped instance, so a forced detach can never pull
  # the database out from under a running DuckDB writer.
  stop_instance_before_detaching = true
}

# A stable address for ANTIEK_PROD_HOST and ANTIEK_PROD_KNOWN_HOSTS. Ingress
# for users is the Cloudflare Tunnel, not this address.
resource "aws_eip" "prod" {
  domain   = "vpc"
  instance = aws_instance.prod.id

  tags = {
    Name = "antiek-prod"
    Role = "prod"
  }

  depends_on = [aws_internet_gateway.this]
}
