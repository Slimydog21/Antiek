# Decision: CLI/Herdr swarm readiness refresh

**Date**: 2026-09-19  
**Status**: accepted  
**Cite**: `docs/anti-ek-cli-swarm.md`; `scripts/anti-ek-swarm-review.sh`; Herdr Antiek **w7**; standing anti-ek rollup CLI/Herdr ~70.

## Context

Playbook was last verified 2026-09-17: stale Claude version/path, preferred
worktree pointed at a legacy `.worktrees/` path, no Herdr w7 tab convention,
and the swarm script had no readiness smoke / argv-size guard / missing-CLI
skips (`claude` unguarded under `set -e`).

## Decision

1. Refresh playbook with Mini-probed 2026-09-19 binaries + dogfood
   `deploy-main-20260917` + Herdr **w7 / Antiek** tab naming convention
   (document existing tabs — do not invent Herdr features).
2. Harden `anti-ek-swarm-review.sh`: `--check`, `--dry-run`, CLI guards,
   diff truncation (`ANTIEK_SWARM_MAX_DIFF_BYTES`), byte summaries.
3. Align companion stub role table with the three-role split (glmf implement /
   claude review / grok adversary).

## Non-goals

- Building new Herdr product surface.
- Burning model tokens in CI for every PR (check is free; review stays manual/on-demand).

## Consequences

Agents and humans can prove swarm readiness before burning reviews. CLI/Herdr
grade climbs with evidence (`--check` → `core_ready=true` on Mini).
