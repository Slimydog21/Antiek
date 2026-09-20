# Code Update — Ship a Substrate Change

**Audience**: you, after the first deploy, pushing a routine update.

**Time**: none. Merging to `main` is the whole procedure.

---

## Happy path — automatic (default since 2026-09-20)

**You do not run anything.** `.github/workflows/deploy_backend.yml` deploys
the backend whenever a commit on `main` has every required check green.

1. Merge the PR into `main`.
2. Wait for the required checks. When the last one goes green, the
   `deploy-backend` workflow fires on its own.
3. Watch it if you want:

   ```bash
   gh run list --workflow deploy-backend --limit 3
   gh run watch $(gh run list --workflow deploy-backend --limit 1 --json databaseId --jq '.[0].databaseId')
   ```

The workflow runs the very same `playbooks/deploy.yml` this runbook used to
ask you to run by hand, from an ubuntu runner instead of your Mac, and then
asserts prod parity independently of the playbook's own assertion.

**What it will NOT do**, by design:

- deploy a commit whose required checks are not all `success` — it reads
  each of main's 8 required contexts for that exact SHA, so a green `CI`
  with a red mypy cannot ship;
- deploy anything on a push, only after a gating workflow has *finished*;
- restart a service that is already on the target SHA (it reads
  `/health.build_sha` first);
- run two deploys at once (`concurrency: deploy-backend-prod`, and an
  in-flight deploy is never cancelled).

**To force one** (e.g. after changing something on the box by hand):

```bash
gh workflow run deploy-backend -f force=true
```

**To pause automatic deploys**, add a required reviewer to the `production`
environment (Settings → Environments → production). Deploys then queue for
your approval instead of going out. To stop them entirely, disable the
workflow: `gh workflow disable deploy-backend`.

**Credentials it uses**: repo secrets `ANTIEK_DEPLOY_SSH_KEY` (a deploy-only
ed25519 key, separate from your personal `~/.ssh/antiek_ed25519`),
`ANTIEK_PROD_HOST`, `ANTIEK_PROD_KNOWN_HOSTS` (the pinned host key — the
workflow never `ssh-keyscan`s at run time). To revoke CI's access without
touching your own, drop its line from the box:

```bash
ssh root@167.235.202.98 \
  "sed -i '/github-actions-deploy@antiek/d' /root/.ssh/authorized_keys"
```

---

## Manual path — fallback

Use this when the runner is down, you are mid-incident, or you are
deploying a ref that is deliberately not `main`.

1. **Push the change to the configured branch.**

   The branch is `main` by default (set in
   `infrastructure/ansible/group_vars/all.yml` as
   `antiek_repo_branch`). If you work on a different branch, either
   merge to `main` or temporarily edit that variable.

   ```bash
   cd ~/Desktop/Antiek
   git push origin main
   ```

2. **Run the deploy playbook from your Mac.**

   ```bash
   cd ~/Desktop/Antiek/infrastructure/ansible
   ansible-playbook -i inventory.ini playbooks/deploy.yml
   ```

   The playbook will:
   - SSH into the VM as root
   - `git pull` in `/opt/antiek`
   - re-install editable Python deps (fast — usually no-op when nothing
     changed in pyproject.toml)
   - re-render `antiek.service` / `Caddyfile` / `backup.sh` from
     templates, reloading systemd/Caddy if any actually changed
   - `systemctl restart antiek`
   - poll `systemctl is-active antiek` until it reports active
   - GET `https://api.antiek.ai/health` from your Mac and assert
     `registered_providers` is non-empty

   **Expected end**: `failed=0` and a success_msg confirming registered
   providers.

   **If the health check fails**, the playbook fails too. Read the
   `assert` block's `fail_msg` — most often the issue is the secrets
   file was wiped (it shouldn't be by deploy.yml, but if you ran
   setup.yml since the last code change with `force: yes` toggled, it
   would have been; default is `force: false`).

3. **(Optional) Spot-check a quick investigation** — same as first-deploy
   step 14, against a cheap throwaway question.

## Unhappy path — rollback

If the new code has a bug and the substrate is misbehaving:

**Option A — git revert** (preferred; preserves history):

```bash
cd ~/Desktop/Antiek
git revert HEAD              # or the bad commit's SHA
git push origin main
cd infrastructure/ansible
ansible-playbook -i inventory.ini playbooks/deploy.yml
```

**Option B — checkout an old commit on the VM directly** (faster but
leaves the deployed state out of sync with `main`):

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
cd /opt/antiek
sudo -u antiek git fetch
sudo -u antiek git checkout <known-good-sha>
systemctl restart antiek
```

Then verify with `curl https://api.antiek.ai/health` from your Mac.

After Option B, push the rollback to `main` so the next deploy.yml run
doesn't undo your manual fix.

## What deploy.yml does NOT do

- It does not run database migrations. The substrate's DuckDB schema is
  managed in code (`substrate/graph/schema.py` is idempotent on
  startup); the migration happens implicitly when uvicorn restarts.
- It does not back up before deploying. If you're deploying a risky
  change, run `playbooks/backup.yml` first.
- It does not update Caddy or Python versions. Those are setup.yml's
  concern; re-run setup.yml (idempotent) when you need OS-level upgrades.

## Common failure modes

| Symptom | Most likely cause | Fix |
|---|---|---|
| `git pull` reports merge conflict | someone edited code on the VM directly | `ssh ... && cd /opt/antiek && git stash` then re-run deploy.yml |
| `pip install` fails on a new dep | new optional extra added but not in `[pdf,urls,embedding]` | edit `deploy.yml`'s pip task to add the new extra |
| systemd reports `failed` after restart | a Python import error in the new code | `ssh ... journalctl -u antiek -n 100` to see the traceback |
| health check times out | Caddy refusing to talk to uvicorn (probably port 8001 already bound by an old uvicorn) | `ssh ... && pkill -f uvicorn && systemctl restart antiek` |
| `registered_providers: []` after deploy | secrets file got blanked (rare — only if you re-ran setup.yml with `force: yes`) | re-run secret-rotation.md to repopulate |
