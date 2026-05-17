# ──────────────────────────────────────────────────────────────────────────────
# Outputs.
#
# Run `terraform output` after `apply` to see these. The Ansible inventory
# template (`../ansible/inventory.ini.example`) references the IPv4 output
# explicitly — the operator copies that value into a new `inventory.ini`
# during first deploy.
# ──────────────────────────────────────────────────────────────────────────────

output "server_ipv4" {
  value       = hcloud_server.antiek.ipv4_address
  description = "Public IPv4 of the Antiek VM. Paste this into ansible/inventory.ini."
}

output "server_ipv6" {
  value       = hcloud_server.antiek.ipv6_address
  description = "Public IPv6 of the Antiek VM."
}

output "ssh_command" {
  value = format(
    "ssh -i %s root@%s",
    replace(var.ssh_public_key_path, ".pub", ""),
    hcloud_server.antiek.ipv4_address,
  )
  description = "Copy-paste SSH command for root login on the new VM."
}

output "r2_endpoint" {
  value = format(
    "https://%s.r2.cloudflarestorage.com",
    var.cloudflare_account_id,
  )
  description = <<-EOT
    S3-compatible endpoint for the R2 bucket. Use this with rclone or aws-cli.
    Pair with R2 API tokens generated separately in the Cloudflare dashboard
    (Terraform can't create R2 tokens — that's a known limitation).
  EOT
}

output "next_steps" {
  value = <<-EOT

  ── Terraform apply complete. Next: ────────────────────────────────────────

  1. Copy the IPv4 below into ../ansible/inventory.ini (use inventory.ini.example
     as the template):

         server_ipv4 = ${hcloud_server.antiek.ipv4_address}

  2. Generate an R2 API token in the Cloudflare dashboard:
       R2 → Manage R2 API Tokens → Create API Token
       - Permission: Object Read & Write
       - Specify bucket: ${var.r2_bucket_name}
     Save the Access Key ID + Secret Access Key into ../ansible/r2-creds.yml
     (gitignored). See runbooks/first-deploy.md step 10 for the exact shape.

  3. Run the Ansible setup playbook:

         cd ../ansible
         ansible-playbook -i inventory.ini playbooks/setup.yml -e @r2-creds.yml

  4. SSH in and populate /etc/antiek/secrets.env with your OpenRouter key.
     See runbooks/first-deploy.md step 12.

  5. Start the substrate:  ssh root@${hcloud_server.antiek.ipv4_address} systemctl start antiek

  ───────────────────────────────────────────────────────────────────────────
  EOT
  description = "Human-readable next-actions block printed after apply."
}
