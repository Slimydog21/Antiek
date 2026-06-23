# Smoke DRW #1 — operator runbook (SPR-LEDGER-05)

Companion to `docs/decisions/deep-research-smoke-checklist.md`. Record results in
`~/specs/antiek-drw-master-ledger/.caffenagent/evidence/smoke-drw-1-live.md`.

## Preconditions (mechanical)

```bash
curl -sS https://api.antiek.ai/health | python3 -m json.tool
# Expect: status ok, providers_ready true, build_sha matches main deploy
```

Prod gather: `ANTIEK_DRW_GATHER=exa` + `EXA_API_KEY` on `/etc/antiek/secrets.env` (set via ansible).

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