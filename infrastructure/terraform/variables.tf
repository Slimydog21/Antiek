# ──────────────────────────────────────────────────────────────────────────────
# Input variables.
#
# Sensitive values (API tokens) have no default and must be supplied via
# either:
#   - TF_VAR_<name> environment variable (preferred for CI / one-off use)
#   - a terraform.tfvars file (gitignored; see terraform.tfvars.example)
#
# Non-sensitive values have defaults that reflect this deployment's
# specific choices. Changing them is fine but read the consequence note
# in each `description` first.
# ──────────────────────────────────────────────────────────────────────────────

# ── Credentials ──────────────────────────────────────────────────────────────

variable "hetzner_token" {
  type        = string
  sensitive   = true
  description = <<-EOT
    Hetzner Cloud API token with read/write scope on Servers and SSH Keys.
    Generate at: https://console.hetzner.cloud → project → Security → API
    tokens → Generate API token. Use `Read & Write` permissions.
  EOT
}

variable "cloudflare_token" {
  type        = string
  sensitive   = true
  description = <<-EOT
    Cloudflare API token scoped to the antiek.ai zone.
    Required permissions:
      - Zone → DNS → Edit  (for the A/AAAA/CNAME records below)
      - Zone → Zone Settings → Edit  (for the TLS/HTTPS overrides)
      - Account → Workers R2 Storage → Edit  (for the R2 bucket)
    Generate at: https://dash.cloudflare.com → My Profile → API Tokens →
    Create Token → Custom token.
  EOT
}

variable "cloudflare_account_id" {
  type        = string
  description = <<-EOT
    Cloudflare account ID (32-char hex). Found at:
    Cloudflare dashboard → any domain → right sidebar → Account ID → Copy.
    Required for R2 bucket creation (R2 is account-scoped, not zone-scoped).
  EOT
}

variable "cloudflare_zone_id" {
  type        = string
  description = <<-EOT
    Cloudflare zone ID for antiek.ai (32-char hex). Found at:
    Cloudflare dashboard → antiek.ai → right sidebar → Zone ID → Copy.
  EOT
}

# ── SSH ──────────────────────────────────────────────────────────────────────

variable "ssh_public_key_path" {
  type        = string
  default     = "~/.ssh/antiek_ed25519.pub"
  description = <<-EOT
    Local path to the SSH public key authorized on the new VM.
    Generate the pair with:
      ssh-keygen -t ed25519 -f ~/.ssh/antiek_ed25519 -C "antiek-operator@$(hostname)"
    Changing this after the VM is created has no effect on existing access —
    the key is uploaded once at server creation. To rotate, see
    runbooks/secret-rotation.md.
  EOT
}

# ── Server ───────────────────────────────────────────────────────────────────

variable "server_name" {
  type        = string
  default     = "antiek-prod-fsn1"
  description = <<-EOT
    The hcloud server's name (Hetzner UI label + reverse DNS hostname).
    `fsn1` denotes the Falkenstein datacenter — change the suffix if you
    change `datacenter`.
  EOT
}

variable "server_type" {
  type        = string
  default     = "ccx23"
  description = <<-EOT
    Hetzner server SKU. `ccx23` is dedicated AMD EPYC vCPUs:
      4 vCPUs / 16 GiB RAM / 160 GB NVMe / 20 TB egress / ~€26/month.
    The Antiek substrate's working set fits in this comfortably for
    single-investigation workloads.
    VERIFY before changing: Hetzner occasionally renames SKUs. Check
    https://www.hetzner.com/cloud for the current catalogue.
  EOT
}

variable "datacenter" {
  type        = string
  default     = "fsn1-dc14"
  description = <<-EOT
    Hetzner datacenter. `fsn1-dc14` is Falkenstein (Germany, EU). Lowest
    latency to OpenRouter's primary EU PoPs. R2 bucket below is also in
    EU region for the same reason. Changing this means re-thinking the R2
    region too.
  EOT
}

variable "image" {
  type        = string
  default     = "ubuntu-24.04"
  description = <<-EOT
    Base OS image. Ubuntu 24.04 LTS ships Python 3.12, which satisfies the
    substrate's `pyproject.toml` `requires-python = ">=3.11"`. The Ansible
    playbook installs the rest. If you switch to a different image, expect
    to revisit package names in setup.yml.
  EOT
}

# ── DNS ──────────────────────────────────────────────────────────────────────

variable "domain" {
  type        = string
  default     = "antiek.ai"
  description = <<-EOT
    The root domain. Must match the existing Cloudflare zone (we don't
    create the zone here — it was set up manually when the domain was
    transferred to Cloudflare DNS).
  EOT
}

variable "api_subdomain" {
  type        = string
  default     = "api"
  description = <<-EOT
    Subdomain for the substrate API (resolves to `api.antiek.ai`). Caddy
    on the VM expects this hostname for the TLS cert SAN, so changing it
    requires updating the Caddyfile template too.
  EOT
}

# ── R2 ───────────────────────────────────────────────────────────────────────

variable "r2_bucket_name" {
  type        = string
  default     = "antiek-backups"
  description = <<-EOT
    Cloudflare R2 bucket holding nightly backups. R2 bucket names are
    globally unique within an account, not globally globally; this default
    is safe so long as the account doesn't already have a bucket of the
    same name.
  EOT
}

variable "r2_bucket_location" {
  type        = string
  default     = "WEUR"
  description = <<-EOT
    R2 region hint. Cloudflare provider v4.x expects uppercase enum:
    one of `WNAM` (western North America), `ENAM` (eastern), `WEUR`
    (western Europe — recommended for Falkenstein VM), `EEUR` (eastern
    Europe), `APAC` (asia-pacific), `OC` (oceania).
    Flag: if compliance dictates a Middle East or non-EU region, this
    is the knob.
  EOT
}
