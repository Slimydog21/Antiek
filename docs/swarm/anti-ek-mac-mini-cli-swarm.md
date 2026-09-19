# Anti-Ek Mac Mini multi-CLI swarm

Reusable roles for speeding implement → review → ship on the Mini.
Canonical playbook with Mini-verified invocations: [`docs/anti-ek-cli-swarm.md`](../anti-ek-cli-swarm.md).
**Never put API keys, tokens, or `.env` values in this doc or in prompts.**

## Available CLIs (PATH)

| CLI | Binary | Noninteractive |
|-----|--------|----------------|
| Claude Code | `claude` | `claude -p "..."` / `--print` |
| Grok Build | `grok` | `grok --single "..."` / `grok -p` |
| GLM Codex | `glm-codex` | `glm-codex review` / `exec` |
| GLMF Codex | `glmf-codex` | `glmf-codex review` / `exec` |
| Codex | `codex` | `codex review` / `exec` |
| MiMo | `mimo` | `mimo run ...` |
| Kimi | `~/.kimi-code/bin/kimi` | `kimi -p ...` (add to PATH) |
| Herdr | `herdr` | `herdr workspace` / `tab` (Antiek **w7**) |

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$HOME/.kimi-code/bin:$PATH"
./scripts/anti-ek-swarm-review.sh --check
```

## Roles → model assignment (default)

| Role | Job | Preferred CLI | Backup |
|------|-----|---------------|--------|
| **Implementer** | Write/fix code on a branch | `glmf-codex exec` | `mimo run` / `glm-codex` |
| **Reviewer** | Diff review: correctness, §9 gates, tests | `claude -p` | `kimi -p` |
| **Adversary** | Attack rights leaks, XSS, auth bypass, DuckDB races + product/UI | `grok --single` + `codex review` | `mimo run` |

Assign **at least two different CLIs** for Reviewer on any merge-bound PR.
Implementer and Adversary should not be the same binary when parallelizing.

## Herdr Antiek w7

Main server workspace: **`w7` / Antiek**. Role tabs use CLI names (`claude`,
`glmf`, `kimi`, …); topic tabs for feature lanes. `--check` inventories live
w7 labels. See canonical playbook — do not invent Herdr features.

## Review prompt skeleton (paste + attach diff)

```
You are reviewing an Antiek PR diff. Focus ONLY on high-confidence issues:
1) §9.0 rights: gated/personal text must not leak on public paths
2) HTML trust: only sanitized sidecar / is_trusted_sanitized may be content_format=html
3) Auth: unauthenticated_local must not gain owner_read
4) DuckDB: no second writer; no prod DB reset
5) Secrets: no tokens in logs/docs
5b) Dual-structure: DuckDB is truth; HTML sidecar is a projection

Output: (a) blocking findings with file:line (b) non-blocking nits (c) LGTM if clean.
Do not suggest weakening gates. Do not invent missing context.
```

## Parallel review recipe

```bash
cd /private/tmp/antiek-main-probe
./scripts/anti-ek-swarm-review.sh --check
./scripts/anti-ek-swarm-review.sh origin/main
# → /tmp/antiek-swarm-review-{claude,glmf,grok}.txt
```

## CI merge bar (standing)

Merge when **tsc + vitest + keystone + mypy/ruff** (and visual if present) pass.
Do **not** block forever on a single hung pytest shard if the other shards passed
(same bar as PR #3100).

## Antiek Mini dogfood context

- Work via SSH: `slimydog@100.106.253.49`
- Dogfood tip-sync tree: `/private/tmp/antiek-main-probe` (platform: `/Users/slimydog/Antiek/platform`)
- Shared DuckDB + isolated events: `scripts/start-shared-duckdb-mac-mini.sh`
- Owner session: `scripts/mac-mini-owner-dev-login.sh` (never print tokens)
- Canonical repo: `Slimydog21/Antiek`
