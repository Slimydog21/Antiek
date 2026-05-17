# ──────────────────────────────────────────────────────────────────────────────
# Antiek production infrastructure.
#
# What this provisions, in dependency order:
#   1. Hetzner SSH key (uploaded from local file)
#   2. Hetzner CCX23 VM in Falkenstein
#   3. Cloudflare A/AAAA records pointing api.antiek.ai at the VM
#   4. Cloudflare CNAME for app.antiek.ai → Cloudflare Pages (Pages project
#      is created separately via the CF dashboard; this just sets up DNS)
#   5. Cloudflare R2 bucket for nightly backups
#   6. Cloudflare zone-wide TLS settings (Full strict, HTTPS-only, TLS 1.2 min)
#
# What this does NOT do:
#   - Configure the VM (that's Ansible's job — see ../ansible/playbooks/setup.yml)
#   - Create the Cloudflare zone (done manually at domain transfer)
#   - Create the Cloudflare Pages project (operator does this via dashboard)
#   - Generate R2 access tokens (operator generates these in the CF dashboard
#     after this apply succeeds; they're used by Ansible's backup playbook)
# ──────────────────────────────────────────────────────────────────────────────

# ── Provider blocks ──────────────────────────────────────────────────────────

provider "hcloud" {
  token = var.hetzner_token
}

provider "cloudflare" {
  api_token = var.cloudflare_token
}

# ──────────────────────────────────────────────────────────────────────────────
# 1. SSH key
#
# Uploaded once at server creation. Hetzner stores the public key; the
# private key never leaves the operator's Mac. Rotating the key after the
# server exists requires either a `cloudinit`-based replace or manual
# replacement of authorized_keys via SSH.
# ──────────────────────────────────────────────────────────────────────────────

resource "hcloud_ssh_key" "operator" {
  name       = "antiek-operator"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

# ──────────────────────────────────────────────────────────────────────────────
# 2. The VM.
#
# `user_data` does the absolute minimum — just ensures python3 is present so
# Ansible can connect. Everything else (packages, users, services) belongs
# in Ansible. Cloud-init is hard to debug and not idempotent in the way
# Ansible is; the temptation to "just bootstrap the rest here" leads to
# infrastructure you can't safely re-run.
#
# Backups: Hetzner offers automatic VM snapshots at extra cost. We do
# application-level backups to R2 instead (see ../ansible/templates/
# backup.sh.j2) because they're more portable and you can restore them to
# any provider. Flag for later: enable Hetzner snapshots as a second
# layer of defense if the budget allows.
# ──────────────────────────────────────────────────────────────────────────────

resource "hcloud_server" "antiek" {
  name        = var.server_name
  server_type = var.server_type
  image       = var.image
  datacenter  = var.datacenter

  ssh_keys = [hcloud_ssh_key.operator.id]

  # Minimal cloud-init: ensure python3 is present for Ansible's first
  # connection. Everything else is Ansible's responsibility.
  user_data = <<-EOT
    #cloud-config
    package_update: true
    packages:
      - python3
  EOT

  # Public IPv4 + IPv6 are auto-assigned. We don't disable them because the
  # whole point is that this is a public-facing API host.

  labels = {
    role        = "antiek-substrate"
    environment = "production"
    managed_by  = "terraform"
  }
}

# ──────────────────────────────────────────────────────────────────────────────
# 3. DNS — api subdomain → VM.
#
# `proxied = false` is deliberate. With proxying on, Cloudflare terminates
# TLS at its edge and re-encrypts to the origin — that means Caddy never
# sees the real client IP, the ACME HTTP-01 challenge for Let's Encrypt
# can fail in subtle ways on first provision, and WebSocket support
# requires extra Cloudflare config. For the API host, direct DNS keeps
# things simple.
#
# Tradeoff: no DDoS protection at the edge. If the API ever takes abuse,
# flip to `proxied = true` (orange cloud) and revisit Caddy's TLS config
# at the same time (it can keep using Let's Encrypt — Caddy + Cloudflare
# proxied works — but verify before flipping).
# ──────────────────────────────────────────────────────────────────────────────

resource "cloudflare_record" "api_a" {
  zone_id = var.cloudflare_zone_id
  name    = var.api_subdomain
  value   = hcloud_server.antiek.ipv4_address
  type    = "A"
  ttl     = 300 # 5 min — short so DNS changes propagate fast during deploys
  proxied = false
  comment = "api.antiek.ai → Antiek substrate VM (managed by Terraform)"
}

resource "cloudflare_record" "api_aaaa" {
  zone_id = var.cloudflare_zone_id
  name    = var.api_subdomain
  value   = hcloud_server.antiek.ipv6_address
  type    = "AAAA"
  ttl     = 300
  proxied = false
  comment = "api.antiek.ai IPv6 (managed by Terraform)"
}

# ──────────────────────────────────────────────────────────────────────────────
# 4. DNS — app subdomain → Cloudflare Pages.
#
# The Pages project itself (antiek-ai) is created separately via the
# Cloudflare dashboard (operator's task). Once it exists, its target is
# `antiek-ai.pages.dev`. This CNAME just sends app.antiek.ai there.
#
# `proxied = true` because Pages requires proxying (Cloudflare serves the
# static assets from the edge cache).
# ──────────────────────────────────────────────────────────────────────────────

resource "cloudflare_record" "app_cname" {
  zone_id = var.cloudflare_zone_id
  name    = "app"
  value   = "antiek-ai.pages.dev" # operator must create this Pages project separately
  type    = "CNAME"
  ttl     = 1 # 1 = "automatic" when proxied
  proxied = true
  comment = "app.antiek.ai → Cloudflare Pages (project created via CF dashboard)"
}

# ──────────────────────────────────────────────────────────────────────────────
# 5. R2 bucket for backups.
#
# `location = "eu"` keeps the bucket physically near the VM. R2 charges
# for storage (~$0.015/GB/month) and PUT/POST (~$4.50/million); GET/HEAD
# are free. At our backup cadence and size, expected cost is < $1/month.
#
# Access tokens for this bucket are NOT created here. After this resource
# applies, generate an R2 API token in the Cloudflare dashboard
# (R2 → Manage R2 API Tokens → Create) scoped to this bucket with
# Object Read & Write. Pass those credentials to Ansible via
# --extra-vars @r2-creds.yml.
# ──────────────────────────────────────────────────────────────────────────────

resource "cloudflare_r2_bucket" "backups" {
  account_id = var.cloudflare_account_id
  name       = var.r2_bucket_name
  location   = var.r2_bucket_location
}

# ──────────────────────────────────────────────────────────────────────────────
# 6. Zone-wide TLS settings.
#
# `ssl = "strict"` means Cloudflare validates the origin's certificate
# (Caddy's Let's Encrypt cert is publicly trusted, so this works). The
# alternative `"full"` (non-strict) accepts self-signed origins — fine for
# dev, not for production.
#
# `always_use_https = "on"` rewrites any http:// request at the edge.
# `min_tls_version = "1.2"` and `tls_1_3 = "on"` block ancient clients
# that almost certainly aren't us anyway.
#
# These settings apply zone-wide, so they also affect app.antiek.ai (CF
# Pages) — that's fine, Pages serves HTTPS natively.
# ──────────────────────────────────────────────────────────────────────────────

resource "cloudflare_zone_settings_override" "antiek" {
  zone_id = var.cloudflare_zone_id

  settings {
    ssl              = "strict"
    always_use_https = "on"
    min_tls_version  = "1.2"
    tls_1_3          = "on"
    # Sane defaults below — explicit so a future audit can read intent.
    automatic_https_rewrites = "on"
    opportunistic_encryption = "on"
    brotli                   = "on"
  }
}
