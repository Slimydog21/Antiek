# First Deploy — Zero to antiek.ai Live

**Audience**: the operator, doing this once. Subsequent code changes use
`code-update.md`.

**Time budget**: ~45 minutes the first time you do it, ~20 minutes once
you've done it before. The slow steps are Terraform creating the Hetzner
VM (~90s) and Ansible installing packages (~5min).

**Cost the moment Terraform applies**: ~€26/month Hetzner VM + ~$0.50/month
R2 storage. You can `terraform destroy` to stop the charge any time.

---

## Step 1 — Generate API tokens

**Hetzner Cloud token.**

- Open https://console.hetzner.cloud
- Project (or create one) → top-right cog → **Security** → **API tokens**
- **Generate API token**
- Description: `antiek-terraform`
- Permissions: **Read & Write**
- Copy the token immediately (only shown once)

**Cloudflare token.**

- Open https://dash.cloudflare.com → top-right profile → **My Profile** →
  **API Tokens**
- **Create Token** → **Custom token** → **Get started**
- Permissions (add three rows):
  | Section | Resource | Permission |
  |---|---|---|
  | Zone | DNS | Edit |
  | Zone | Zone Settings | Edit |
  | Account | Workers R2 Storage | Edit |
- Zone Resources: **Include** → **Specific zone** → **antiek.ai**
- Account Resources: **Include** → your account
- **Continue to summary** → **Create Token**
- Copy immediately.

**Cloudflare account ID** + **zone ID** (paste later into `terraform.tfvars`):

- https://dash.cloudflare.com → click on **antiek.ai**
- Right sidebar shows both. Copy both 32-character hex strings.

## Step 2 — Generate SSH key pair

```bash
ssh-keygen -t ed25519 -f ~/.ssh/antiek_ed25519 -C "antiek-operator@$(hostname)"
```

When asked for a passphrase, hit enter twice (no passphrase). The
tradeoff: convenience now versus your key being usable by anyone with
access to your Mac if it's stolen. Revisit if you ever leave the laptop
unattended in a context where that matters.

You'll end up with `~/.ssh/antiek_ed25519` (private, do not share) and
`~/.ssh/antiek_ed25519.pub` (public, fine to share).

**Expected**:
```
Generating public/private ed25519 key pair.
Your identification has been saved in /Users/<you>/.ssh/antiek_ed25519
Your public key has been saved in /Users/<you>/.ssh/antiek_ed25519.pub
```

## Step 3 — Verify nameservers have propagated

```bash
dig @1.1.1.1 NS antiek.ai +short
```

**Expected output**:
```
drew.ns.cloudflare.com.
maeve.ns.cloudflare.com.
```

If you see anything else (e.g. Porkbun's defaults), nameserver propagation
isn't complete yet. **Stop. Wait.** Nameserver propagation takes 1-48
hours after you change them at the registrar. Re-run `dig` periodically;
proceed only when it returns the two Cloudflare nameservers above.

## Step 4 — Populate terraform.tfvars

```bash
cd ~/Desktop/Antiek/infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` (it's gitignored) and paste in:
- `hetzner_token` — from step 1
- `cloudflare_token` — from step 1
- `cloudflare_account_id` — from step 1
- `cloudflare_zone_id` — from step 1

Leave the optional overrides commented out unless you have a specific
reason to change them.

## Step 5 — Initialise Terraform

```bash
cd ~/Desktop/Antiek/infrastructure/terraform
terraform init
```

**Expected output ends with**:
```
Terraform has been successfully initialized!
```

If you see a checksum error on a provider download, your network might
be flaky — retry once.

## Step 6 — Plan, then apply

```bash
terraform plan
```

Review the plan. You should see:
- **2 to add** for the Hetzner SSH key + server
- **3 to add** for the three Cloudflare DNS records (A, AAAA, CNAME)
- **1 to add** for the R2 bucket
- **1 to add** for the zone settings override

Total: **7 resources to add, 0 to change, 0 to destroy.**

If the plan shows destroying anything, **stop**. Something is wrong;
don't apply.

```bash
terraform apply
```

Type `yes` when prompted. Apply takes ~90 seconds (most of it the
Hetzner VM boot).

**Save the outputs.** Terraform prints them at the end:

```
Outputs:

next_steps = <<EOT
  ── Terraform apply complete. Next: ...
EOT

r2_endpoint = "https://abc...xyz.r2.cloudflarestorage.com"
server_ipv4 = "203.0.113.42"
server_ipv6 = "2a01:..."
ssh_command = "ssh -i ~/.ssh/antiek_ed25519 root@203.0.113.42"
```

If at any point in the next few hours you want them again:
```bash
terraform output
```

## Step 7 — Verify you can SSH into the new VM

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<server_ipv4>
```

Accept the host key fingerprint on first connection. You should land in
a root shell on Ubuntu 24.04. Type `exit` to come back to your Mac.

If SSH refuses, wait 30 seconds (cloud-init may still be running) and
try again.

## Step 8 — Set up Ansible inventory

```bash
cd ~/Desktop/Antiek/infrastructure/ansible
cp inventory.ini.example inventory.ini
```

Edit `inventory.ini` and replace `<IPV4_FROM_TERRAFORM_OUTPUT>` with the
real `server_ipv4` from step 6.

## Step 9 — First run of setup playbook (without R2 yet)

R2 access tokens have to be generated AFTER the R2 bucket exists, but
the bucket was just created in step 6. We need R2 credentials before
the setup playbook will run (it asserts they're present in step 0).

Generate them now:

- https://dash.cloudflare.com → **R2** in the left sidebar
- **Manage R2 API Tokens** (top right) → **Create API Token**
- Token name: `antiek-backup-writer`
- Permission: **Object Read & Write**
- Specify bucket: `antiek-backups`
- TTL: leave at "Forever" (rotate manually later)
- **Create API Token**
- Copy both the **Access Key ID** and the **Secret Access Key** — they
  are shown only once.

Create `~/Desktop/Antiek/infrastructure/ansible/r2-creds.yml` (gitignored):

```yaml
r2_endpoint: "https://<YOUR_ACCOUNT_ID>.r2.cloudflarestorage.com"
r2_access_key: "<ACCESS_KEY_ID_FROM_CLOUDFLARE>"
r2_secret_key: "<SECRET_ACCESS_KEY_FROM_CLOUDFLARE>"
```

The `r2_endpoint` is also in your `terraform output r2_endpoint`.

## Step 10 — Run the setup playbook

```bash
cd ~/Desktop/Antiek/infrastructure/ansible
ansible-playbook -i inventory.ini playbooks/setup.yml -e @r2-creds.yml
```

**Expected runtime**: ~5 minutes. Tasks run in order: apt update → base
packages → UFW → Caddy → user creation → repo clone → venv → secrets
file → state dirs → systemd unit → Caddyfile → rclone config → backup
cron.

**Expected end**: a green "PLAY RECAP" with `failed=0` and a printed
banner with three next steps.

**If a task fails**, the playbook stops at that task. Read the error.
Common ones:

- *"Unable to clone repo: Permission denied (publickey)"* — your
  `antiek_repo_url` in `group_vars/all.yml` still says
  `REPLACE_WITH_OPERATOR_USERNAME`. Edit it to your real GitHub URL
  (e.g. `https://github.com/yourname/Antiek.git`), commit, push, then
  re-run.
- *"r2_endpoint is undefined"* — you forgot `-e @r2-creds.yml`. Re-run
  the command exactly as printed above.
- *"Could not find the requested URL on this server" (Caddy apt repo)* —
  Caddy sometimes rotates their repo URL. Check
  https://caddyserver.com/docs/install#debian-ubuntu-raspbian for the
  current install instructions; update the `caddy --` tasks in
  `setup.yml` to match.

## Step 11 — Populate the secrets file

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<server_ipv4>
sudoedit /etc/antiek/secrets.env
```

The file opens empty (except for comments). Replace the empty line:

```
OPENROUTER_API_KEY=
```

with your real key:

```
OPENROUTER_API_KEY=sk-or-v1-...your-actual-key...
```

Save and exit (`:wq` in vim, `Ctrl+X` then `Y` then enter in nano —
`sudoedit` respects `$EDITOR`).

Verify it took:
```bash
sudo cat /etc/antiek/secrets.env
```

You should see your key. Exit back to your Mac (`exit`).

## Step 12 — Start the substrate

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<server_ipv4> systemctl start antiek
```

Check that it came up:

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<server_ipv4> systemctl status antiek
```

**Expected**: a green `active (running)` line and a few log lines from
uvicorn.

If you see `failed`, run:
```bash
ssh -i ~/.ssh/antiek_ed25519 root@<server_ipv4> journalctl -u antiek -n 50
```

and see `debugging.md` for the most common causes.

## Step 13 — Verify the public endpoint

From your Mac:

```bash
curl https://api.antiek.ai/health
```

**Expected**:
```json
{"status":"ok","param_version":"0.1.0","schema_version":3,"subscriber_count":0,"registered_providers":["openrouter"]}
```

The first request triggers Caddy to fetch a Let's Encrypt cert; that can
take ~10 seconds the very first time. If you see a TLS error, wait 30
seconds and retry.

**If `registered_providers` is `[]`**, your secrets file is empty or
malformed. Re-run step 11.

## Step 14 — Smoke-test a real investigation

A trivial cold question, to keep cost minimal (~$0.05):

```bash
cd ~/Desktop/Antiek
source .venv/bin/activate
python -m tools.demo.run_cold_question \
    --base-url https://api.antiek.ai \
    --question "What is one fundamental tradeoff in adaptive filter design? Cite a single source." \
    --topic-slug substrate-smoke
```

This should complete in ~5-10 minutes and print `=== Investigation
inv-... → COMPLETED ===` plus a thesis summary.

If it completes, **the substrate is live in production.** 

---

## Done — what now?

- For code changes: `code-update.md`
- To rotate the OpenRouter key: `secret-rotation.md`
- If something is on fire: `debugging.md`
- If the VM is gone and you need to restore: `disaster-recovery.md`
- One-line summary of how to operate the whole stack: `../SKILL.md`
