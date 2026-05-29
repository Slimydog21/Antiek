# Run deploy.yml from a checkout matching the deploy branch (2026-05-29)

**Date:** 2026-05-29
**Surfaced by:** the Antiek Knowledge Base backend deploy (see `antiek-knowledge-base-ship-2026-05-29.md`)
**Status:** Operational finding + recommended guard. The finding is recorded; the guard is a proposed follow-up, not yet shipped.

## The finding

`infrastructure/ansible/playbooks/deploy.yml` has two phases. Phase B, on the
VM, does `git pull` of `antiek_repo_branch` (`main`) into `/opt/antiek` — so the
**Python backend** comes from `main` regardless of what the operator's laptop
has checked out. But Phase A and the Caddy/template tasks use Ansible's
`template`/`copy`/local-build steps, which read from the **control node's
working tree** (the laptop), not from the VM's pulled repo. The frontend is
built locally and rsynced; `Caddyfile.j2` is rendered locally.

The consequence: if the control-node checkout is on a branch other than `main`,
the deploy ships **correct backend code with stale templated config**, silently.

## How it bit

The deploy was run with the laptop on `read/workflow-execution` (an in-flight
track), not `main`:

1. Phase A (`build apps/reading`) failed outright — that branch had an
   uncommitted TypeScript error, unrelated to the ship. `--skip-tags frontend`
   got past it (the canonical frontend is Cloudflare Pages, auto-built from
   `main`, so the local build/rsync isn't needed for a backend ship).
2. The backend then deployed correctly — the VM pulled `main` (`5413fdc`) and
   restarted. But `GET /library` and `/api/ad/*` still returned the SPA, because
   the **Caddyfile was rendered from the `read/workflow-execution` template**,
   whose `@api_routes` allowlist predates the SPR-09 routes. `main`'s
   `Caddyfile.j2` had the routes; the control node didn't.
3. Re-running the deploy from a worktree checked out on `origin/main` (with the
   real, untracked `inventory.ini` passed by absolute path) re-rendered the
   Caddyfile with the SPR-09 routes — `re-render Caddyfile: changed` — and the
   routes went live (401-auth-gated JSON, no longer SPA HTML).

## Why this is the right framing (not "the deploy was broken")

The playbook is correct. The latent trap is that **templated config provenance
is the control node, while code provenance is the VM's pull** — two different
sources that agree only when the control-node tree is on the deploy branch and
clean. A deploy from any feature branch silently mixes that branch's templates
with `main`'s code. `inventory.ini` being untracked (local-only) is a second
edge: a fresh `main` worktree has no inventory, so it must be passed by absolute
path (or the play matches no hosts and no-ops, which also happened here).

## Recommended guard (proposed, not yet shipped)

A pre-flight assertion at the top of `deploy.yml` that **fails loudly** unless
the control node is on `antiek_repo_branch` with a clean tree — converting a
silent stale-config deploy into a refusal. Sketch:

```yaml
- name: Antiek — pre-flight (control node must match the deploy branch)
  hosts: localhost
  gather_facts: false
  tasks:
    - command: git rev-parse --abbrev-ref HEAD
      register: cn_branch
      changed_when: false
    - command: git status --porcelain
      register: cn_dirty
      changed_when: false
    - assert:
        that:
          - cn_branch.stdout == antiek_repo_branch
          - cn_dirty.stdout | trim == ""
        fail_msg: >-
          Control node is on '{{ cn_branch.stdout }}' (dirty={{ (cn_dirty.stdout | trim) != '' }}),
          but templates render from HERE. Check out '{{ antiek_repo_branch }}' clean, or run from a
          matching worktree, before deploying.
```

## Reconsider-if

If the deploy is reworked so that templated config is rendered from the VM's
pulled `/opt/antiek` (not the control node) — e.g. render Caddyfile on the VM
from the pulled tree — this guard becomes unnecessary for config, though the
local frontend build would still want it. Until then, the rule stands: **run
`deploy.yml` from a checkout matching `main`, or from a `main` worktree with
`inventory.ini` passed by absolute path.**
