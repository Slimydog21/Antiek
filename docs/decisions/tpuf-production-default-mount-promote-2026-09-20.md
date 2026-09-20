# TurboPuffer `production_default_mount` env wire (2026-09-20)

**Status:** shipped (code) · **ops flip** pending Mini/prod Tailscale deploy  
**Auth:** Faisal widget 2026-09-20 — promote on prod (and Mini if safe).

## Gap
`probe_turbopuffer_health` hardcoded `production_default_mount=False`, so an
env-only promote could not change `/health`.

## Fix
- Read `ANTIEK_TURBOPUFFER_PRODUCTION_DEFAULT_MOUNT` via `_env_truthy` (1/true/yes).
- Default remains **false** when unset (local-safe).
- Ansible `secrets.env.j2` documents the slot for durable prod EnvironmentFile=.
- SERVABLE hybrid resolve (`ANTIEK_TURBOPUFFER_SERVABLE` + key) unchanged; DuckDB SoT intact.

## Ops (after merge)
On prod (and Mini if hybrid_ready + meaningful corpus):

```bash
# /etc/antiek/secrets.env
ANTIEK_TURBOPUFFER_PRODUCTION_DEFAULT_MOUNT=1
sudo systemctl restart antiek
curl -fsS https://api.antiek.ai/health | jq .turbopuffer_production_default_mount
# expect true
```

## Does not
Synquery · G2 counsel · email · invent AppLovin CPM.
