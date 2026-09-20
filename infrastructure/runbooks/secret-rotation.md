# Secret Rotation — OpenRouter Key (and others)

**When to do this**:
- Routinely every 90 days as hygiene.
- Immediately if the key was exposed (shared in chat, committed to git,
  leaked in a screenshot).
- After any operator turnover.

**Time**: ~3 minutes.

---

## Rotate the OpenRouter key

1. **Generate a new key in OpenRouter.**

   - https://openrouter.ai/keys → **Create Key**
   - Name it descriptively (e.g. `antiek-prod-2026-05`)
   - Copy the new key. It starts with `sk-or-v1-` and is ~70 characters.

   Do not revoke the old key yet — that comes in step 4, after the new
   key is verified working.

2. **Edit the secrets file on the VM.**

   ```bash
   ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
   sudoedit /etc/antiek/secrets.env
   ```

   Replace the existing line:
   ```
   OPENROUTER_API_KEY=sk-or-v1-<old-key>
   ```
   with:
   ```
   OPENROUTER_API_KEY=sk-or-v1-<new-key>
   ```

   Save and exit. `sudoedit` respects `$EDITOR` — vim's `:wq`, nano's
   Ctrl+X.

3. **Restart the substrate** to pick up the new env var:

   ```bash
   systemctl restart antiek
   exit
   ```

   (Back on your Mac:)

   Verify the restart succeeded:
   ```bash
   curl https://api.antiek.ai/health
   ```
   Should return `{"status":"ok",...,"registered_providers":["openrouter"]}`.

4. **Verify the new key actually works** by triggering a real dispatch.
   The `/health` endpoint only confirms the key is *loaded*, not that
   it's *valid* — a typo'd key still shows up in `registered_providers`
   because bootstrap just checks the env var is non-empty.

   The cheapest valid-key check is a 1-token throwaway dispatch:

   ```bash
   cd ~/Desktop/Antiek
   source .venv/bin/activate
   OPENROUTER_API_KEY=sk-or-v1-<new-key> python3 -c "
   from substrate.dispatch.router import reset_provider_registry
   from substrate.dispatch.providers import register_default_providers
   from substrate.dispatch import dispatch
   reset_provider_registry()
   register_default_providers(quiet=True)
   r = dispatch('Reply with one word: ok', 'tier_assigner', investigation_id='inv-key-rotation-test')
   print(f'OK: provider={r.provider} model={r.model} cost=\${r.cost_usd:.6f} text={r.text!r}')
   "
   ```

   Expected: `OK: provider=openrouter model=deepseek/deepseek-v4-flash
   cost=$0.000... text='ok'`. Costs ~$0.00002.

   If you see `HTTP 401` or `Authentication failed`, the key is wrong.
   Go back to step 2.

5. **Revoke the old key in the OpenRouter dashboard.**

   - https://openrouter.ai/keys
   - Find the old key in the list
   - **Disable** (or **Delete**)

   From this point onward, any process still holding the old key value
   in env will start failing. The Antiek substrate has the new key (you
   verified in step 4), so this only affects ad-hoc dev sessions on
   your Mac.

## Rotating other keys

`ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, and `NOTDIAMOND_API_KEY` follow the same procedure —
substitute the dashboard URL:

- Anthropic: https://console.anthropic.com/settings/keys
- DeepSeek: https://platform.deepseek.com/api_keys
- NotDiamond: https://notdiamond.ai

In the current deployment, these are unset (everything routes through
OpenRouter), so this section is for a future state where you've added
direct provider keys for cost optimisation.

## Rotating the R2 access token

The R2 token used by the backup script lives in `/etc/rclone/rclone.conf`
on the VM, NOT in `secrets.env`. To rotate:

1. Generate a new R2 token in the Cloudflare dashboard (R2 → Manage R2
   API Tokens → Create API Token), scoped to the `antiek-backups`
   bucket, Object Read & Write.
2. Update `~/Desktop/Antiek/infrastructure/ansible/r2-creds.yml` on
   your Mac with the new values.
3. Re-run the setup playbook (the rclone-config task is idempotent and
   will overwrite with the new credentials):
   ```bash
   cd ~/Desktop/Antiek/infrastructure/ansible
   ansible-playbook -i inventory.ini playbooks/setup.yml -e @r2-creds.yml --tags backup
   ```
4. Trigger a backup to confirm the new token works:
   ```bash
   ansible-playbook -i inventory.ini playbooks/backup.yml
   ```
   Should print a "backup complete" line.
5. Revoke the old R2 token in the Cloudflare dashboard.

## Rotating the Hetzner or Cloudflare API tokens

These are only used at Terraform-apply time, not by the running
substrate. To rotate:

1. Generate new tokens in the respective dashboards.
2. Update `~/Desktop/Antiek/infrastructure/terraform/terraform.tfvars`
   (gitignored) with the new values.
3. Run `terraform plan` from `infrastructure/terraform/` — should show
   "0 to add, 0 to change, 0 to destroy" (no resource changes, the
   tokens are only used for authentication).
4. Revoke the old tokens.

## Rotating the SSH key

Painful — the SSH key is uploaded to Hetzner at VM creation and copied
to `authorized_keys` for both `root` and `antiek` users on the VM. To
rotate without losing access:

1. Generate the new key pair: `ssh-keygen -t ed25519 -f
   ~/.ssh/antiek_ed25519_new -C "antiek-operator@$(hostname)-rotated"`
2. While still able to SSH with the old key, append the new public key:
   ```bash
   ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
   echo "$(cat ~/.ssh/antiek_ed25519_new.pub)" >> /root/.ssh/authorized_keys
   echo "$(cat ~/.ssh/antiek_ed25519_new.pub)" >> /home/antiek/.ssh/authorized_keys
   ```
3. From your Mac, verify the new key works:
   `ssh -i ~/.ssh/antiek_ed25519_new root@<vm-ip>`
4. Once verified, remove the old key from `authorized_keys` on both
   users on the VM.
5. Replace the old keypair on your Mac:
   `mv ~/.ssh/antiek_ed25519 ~/.ssh/antiek_ed25519.old`
   `mv ~/.ssh/antiek_ed25519_new ~/.ssh/antiek_ed25519`
6. (Optional) Update Hetzner: the old SSH key in their console is
   stale. Delete it via the console UI or via Terraform (`terraform
   taint hcloud_ssh_key.operator && terraform apply` — but this is
   only useful if you ever re-provision a VM).
