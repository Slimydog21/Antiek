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

The workflow runs the very same `playbooks/deploy_atomic.yml` this runbook used to
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
   ansible-playbook -i inventory.ini playbooks/deploy_atomic.yml \
     -e "antiek_target_sha=$(git rev-parse origin/main)"
   ```

   For an incident rollback release, replace the resolved SHA with the
   exact 40-hex known-good SHA. Never use a branch name or short SHA.

   The playbook will:
   - SSH into the VM as root
   - build the exact SHA under `/opt/antiek-releases/<sha>` while the
     current release keeps serving
   - create a frozen production venv from that SHA's lock, then remove
     the bootstrap `uv`
   - publish the frontend built from the same exact checkout
   - render and verify systemd, Cloudflared, and Caddy configuration
   - quiesce DuckDB writers, checkpoint and snapshot the database, run
     candidate schema initialization and verifiers
   - make one `/opt/antiek` symlink cutover, activate candidate edge
     routes, then start the candidate service
   - GET `https://api.antiek.ai/health` from your Mac and assert
     the exact SHA, non-empty providers, and public parity

   **Expected end**: `failed=0`, `/opt/antiek` resolving to the candidate,
   and a release receipt in the immutable release directory.

   **If verification fails after cutover**, the playbook's rescue path
   restores the previous symlink and Caddy routes, restarts the previous
   release, resumes consumers, and verifies its public health before
   failing the deploy. The DuckDB snapshot remains for database recovery;
   code rollback does not reverse committed application writes.

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
ansible-playbook -i inventory.ini playbooks/deploy_atomic.yml
```

**Option B — restore a retained release on the VM directly** (faster but
leaves the deployed state out of sync with `main`):

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
PREVIOUS=<known-good-40-hex-sha>
LINK=/opt/antiek.rollback.$$
ln -s "/opt/antiek-releases/$PREVIOUS" "$LINK"
mv -Tf "$LINK" /opt/antiek
systemctl restart antiek
```

Then verify with `curl https://api.antiek.ai/health` from your Mac and
confirm `build_sha` equals `$PREVIOUS`. If the candidate changed Caddy
routes and no automatic rollback ran, restore
`/etc/caddy/Caddyfile.pre-atomic-<candidate-sha>` before reload; the SPA
itself follows `/opt/antiek/frontend-dist`, so restoring the release
pointer normally restores both API and SPA.

After Option B, push the rollback to `main` so the next deploy_atomic.yml run
doesn't undo your manual fix.

## What deploy_atomic.yml does NOT do

- It does not reverse committed application writes. The pre-migration
  DuckDB snapshot is a recovery point, not an automatic two-phase
  database rollback.
- It does not update OS packages, Caddy binaries, Cloudflared binaries,
  or Python versions. Those are setup.yml's concern; re-run setup.yml
  (idempotently) when you need OS-level upgrades.
- It does not deploy a mutable ref. Every invocation needs an exact
  40-hex commit SHA and green checks unless `antiek_force_deploy=true`
  is used deliberately.

## Common failure modes

| Symptom | Most likely cause | Fix |
|---|---|---|
| receipt assertion fails | an earlier build of this SHA was interrupted | the playbook removes and rebuilds the unpublished candidate; do not publish it manually |
| lock check or exact sync fails | `uv.lock` is stale or a production extra is missing | run `uv lock` locally, commit the lock, and include every production extra in the playbook contract |
| systemd reports `failed` after restart | a Python import error in the new code | use the playbook rollback if it did not complete; otherwise inspect `journalctl -u antiek -n 100` |
| health check times out | Caddy, tunnel, or uvicorn failed after cutover | inspect `systemctl status antiek caddy cloudflared` and use the recorded previous release only after stopping the candidate |
| `registered_providers: []` after deploy | secrets file got blanked (rare — only if you re-ran setup.yml with `force: yes`) | re-run secret-rotation.md to repopulate |
