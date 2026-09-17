# Anti-Ek Mac Mini multi-CLI swarm

Reusable roles for speeding implement → review → ship on the Mini.
**Never put API keys, tokens, or `.env` values in this doc or in prompts.**

## Available CLIs (PATH)

| CLI | Binary | Noninteractive |
|-----|--------|----------------|
| Claude Code | `claude` | `claude -p "..."` / `--print` |
| Grok Build | `grok` | check `grok --help` |
| GLM Codex | `glm-codex` | `glm-codex exec ...` |
| GLMF Codex | `glmf-codex` | `glmf-codex exec ...` |
| Codex | `codex` | `codex exec ...` |
| MiMo | `mimo` | `mimo run ...` |
| Kimi | `~/.kimi-code/bin/kimi` | `kimi ...` (add to PATH) |

```bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.kimi-code/bin:$PATH"
```

## Roles → model assignment (default)

| Role | Job | Preferred CLI | Backup |
|------|-----|---------------|--------|
| **Implementer** | Write/fix code on a branch | `claude -p` or `grok` | `glm-codex exec` |
| **Reviewer** | Diff review: correctness, §9 gates, tests | `claude -p` + `glmf-codex exec` | `glm-codex` / `kimi` |
| **Adversary** | Attack rights leaks, XSS, auth bypass, DuckDB races | `mimo run` or `codex exec` | `glmf-codex` |

Assign **at least two different CLIs** for Reviewer on any merge-bound PR.
Implementer and Adversary should not be the same binary when parallelizing.

## Review prompt skeleton (paste + attach diff)

```
You are reviewing an Antiek PR diff. Focus ONLY on high-confidence issues:
1) §9.0 rights: gated/personal text must not leak on public paths
2) HTML trust: only sanitized sidecar / is_trusted_sanitized may be content_format=html
3) Auth: unauthenticated_local must not gain owner_read
4) DuckDB: no second writer; no prod DB reset
5) Secrets: no tokens in logs/docs

Output: (a) blocking findings with file:line (b) non-blocking nits (c) LGTM if clean.
Do not suggest weakening gates. Do not invent missing context.
```

## Parallel review recipe

```bash
# From worktree with PR checked out:
git diff origin/main...HEAD > /tmp/pr.diff
PROMPT="$(cat docs/swarm/anti-ek-mac-mini-cli-swarm.md | sed -n "/Review prompt skeleton/,/^## Parallel/p" | head -n -2)"

# Terminal A
claude -p "$PROMPT

$(cat /tmp/pr.diff)" > /tmp/review-claude.txt 2>&1 &

# Terminal B
glmf-codex exec "Review this Antiek diff. $PROMPT

$(cat /tmp/pr.diff)" > /tmp/review-glmf.txt 2>&1 &

wait
# Fold only high-confidence fixes; then merge when CI bar is met.
```

## CI merge bar (standing)

Merge when **tsc + vitest + keystone + mypy/ruff** (and visual if present) pass.
Do **not** block forever on a single hung pytest shard if the other shards passed
(same bar as PR #3100).

## Antiek Mini dogfood context

- Work via SSH: `slimydog@100.106.253.49`
- Shared DuckDB + isolated events: `scripts/start-shared-duckdb-mac-mini.sh`
- Owner session: `scripts/mac-mini-owner-dev-login.sh` (never print tokens)
- Canonical repo: `Slimydog21/Antiek`
