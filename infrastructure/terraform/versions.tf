# ──────────────────────────────────────────────────────────────────────────────
# Provider version pins.
#
# Why pin?
#
# The Cloudflare provider in particular has had naming churn — resource and
# attribute names changed between v4.x and v5.x (e.g. `cloudflare_record`
# became `cloudflare_dns_record`). Pinning to a known-good major version
# means a future `terraform init -upgrade` won't silently rewrite resource
# semantics under you.
#
# Upgrade discipline:
#   1. Read the upstream CHANGELOG for the provider you're bumping.
#   2. Bump the version constraint here, in its own commit.
#   3. `terraform init -upgrade && terraform plan` — review diffs carefully.
#   4. Only then apply.
#
# `required_version` for Terraform itself: ≥ 1.6 introduces stable
# behaviour around `import` blocks and ephemeral resources. 1.6 was
# released October 2023; the operator's `brew install terraform` will pull
# something newer.
# ──────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    # Hetzner Cloud — provisions the VM, SSH key, network primitives.
    # https://registry.terraform.io/providers/hetznercloud/hcloud/latest
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }

    # Cloudflare — DNS records, R2 bucket, zone-wide TLS settings.
    # https://registry.terraform.io/providers/cloudflare/cloudflare/4.20.0
    #
    # NOTE: this pin assumes the v4.x provider API (resource:
    # `cloudflare_record`, `cloudflare_r2_bucket`,
    # `cloudflare_zone_settings_override`). v5.x renamed `cloudflare_record`
    # to `cloudflare_dns_record`. If you upgrade past v5, every record
    # block here needs renaming + plan-reviewing.
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.20"
    }
  }
}
