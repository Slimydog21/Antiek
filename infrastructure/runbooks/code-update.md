# Code Update — Ship a Substrate Change

**Audience**: you, after the first deploy, pushing a routine update.

**Time**: ~2 minutes typing + ~2 minutes for the playbook to run.

---

## Happy path

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

### Continuous-research lifecycle and intentional pause

The continuous-research daemon is production-always-live by default. Every
deploy starts it if it was stopped and restarts it after code or unit changes.
A manual `systemctl stop antiek-continuous-research` is therefore temporary
drift, not a durable pause.

For an intentional pause, set this boolean under `[antiek_prod:vars]` in the
operator's gitignored `inventory.ini`, then deploy:

```ini
antiek_continuous_research_paused=true
```

The playbook stops and disables the service, preserving the pause across later
deploys and reboots. Set it back to `false` and deploy to resume. This is the
daemon lifecycle policy; per-investigation pause/resume controls do not stop the
daemon. Likewise, `/health`'s `flywheel_ready` is historical compounding
evidence (graph readability plus prior `knowledge.reused` events), not proof
that this systemd process is currently active. The deploy verifies process
liveness directly with `systemctl is-active`.

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
