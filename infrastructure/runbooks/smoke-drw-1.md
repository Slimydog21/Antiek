# Smoke DRW #1 — operator runbook (SPR-LEDGER-05)

Companion to `docs/decisions/deep-research-smoke-checklist.md`. Record results in
`~/specs/antiek-drw-master-ledger/.caffenagent/evidence/smoke-drw-1-live.md`.

## Automated script (VM or laptop with token)

```bash
# On Hetzner (sources /etc/antiek/secrets.env):
set -a; source /etc/antiek/secrets.env; set +a
bash /opt/antiek/tools/ops/smoke_drw_1.sh   # after deploy copies script
```

From repo: `tools/ops/smoke_drw_1.sh` (same contract).

**Prod note (2026-06-24):** if `POST /research/plans` returns 500 with
`RuntimeError: could not create a primitive` in embeddings, set
`ANTIEK_EMBEDDING_PROVIDER=hash` in `/etc/antiek/secrets.env` and restart
`antiek.service`. DRW gather + synthesis still run; semantic match is degraded.

## Preconditions (mechanical)

```bash
curl -sS https://api.antiek.ai/health | python3 -m json.tool
# Expect: status ok, providers_ready true, build_sha matches main deploy
#         drw_gather_mode "exa" — "stub" means NO REAL RETRIEVAL
```

Prod gather: `ANTIEK_DRW_GATHER=exa` + `EXA_API_KEY` on `/etc/antiek/secrets.env`.

> **Corrected 2026-09-20.** This line previously said "(set via ansible)".
> Ansible does not set it. `infrastructure/ansible/templates/secrets.env.j2:64`
> renders `ANTIEK_DRW_GATHER=` and `EXA_API_KEY=` **empty** — the intended
> `=exa` is in a comment two lines above — and `setup.yml` places the file with
> `force: false`, so it is written once on a fresh VM and never updated.
> `_research_loop_factory` reads `os.environ.get("ANTIEK_DRW_GATHER", "stub")`,
> and an empty string is not `"exa"`, so the untouched rendering yields the
> contract stub: no retrieval, while this checklist reads green.
>
> Both values must be set by hand on the box, or the template taught to
> interpolate them. Until then, **verify, do not assume**: `/health` now
> reports `drw_gather_mode`, which is derived from the same branch the cascade
> takes (`tests/test_drw_gather_mode_reported.py` pins them together), so the
> curl above answers the question directly.

Local hermetic gate:

```bash
cd ~/Desktop/Antiek && ./scripts/canonical_verify.sh deep-research
# CANONICAL_VERIFY_OK: deep-research
```

## UI path (recommended)

1. https://antiek.ai → sign in (magic link).
2. Research → enter a **real** question → propose plan → trim → approve → launch.
3. Open the live cascade monitor; wait until researches finish and synthesis completes.

## API poll (after launch)

Export a machine token (never commit; see `magic-link-auth.md`):

```bash
export ANTIEK_OPERATOR_TOKEN='…'   # from /etc/antiek/secrets.env on VM or local operator env
export SESSION_ID='…'              # from launch response
```

Poll parent-terminal fields:

```bash
curl -sS -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" \
  "https://api.antiek.ai/research/sessions/$SESSION_ID" | python3 -m json.tool
```

Check: `deep_research_complete`, `synthesis_tail_error`, leaf `state` terminals.

## Grade

Accept or reject synthesis; if reject, add regression YAML per `tests/regression/agent_failures/README.md`.