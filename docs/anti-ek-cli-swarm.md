# Anti-Ek multi-CLI swarm playbook

Mac Mini (`slimydog@100.106.253.49`) playbook for a three-role swarm:
**Implementer → Reviewer → Adversary/rights**. Verified 2026-09-17 on this
machine. **Never print API keys, tokens, or values from `~/.config/ai-keys` / `.env`.**

Companion stub (shorter): [`docs/swarm/anti-ek-mac-mini-cli-swarm.md`](./swarm/anti-ek-mac-mini-cli-swarm.md).
Helper: [`scripts/anti-ek-swarm-review.sh`](../scripts/anti-ek-swarm-review.sh).

## Dual-structure rule (read this first)

Antiek has two layers. Mixing them is how we get stored-XSS-adjacent defects
and rights leaks.

| Layer | What it is | What it is not |
|-------|------------|----------------|
| **DuckDB truth** | `documents` (incl. `raw_text`, `content_class`, `metadata`, `ip_holder_id`), typed event log, rights / servability. Single writer (`runtime/db_lock.py`, uvicorn `--workers 1`). | Not a place to stamp HTML-trust bits. `documents.metadata` must **not** carry `sanitized_html_provenance()` / `content_sanitized` for reader bodies. |
| **HTML projections** | Sanitized, versioned artifacts: `document_reader_html` sidecar (`substrate/reader_html/`), `services/html_projection/` research artifacts. Zero-script, content-addressed. | Not the rights gate. A sidecar existing does **not** authorize a serve. Rights first (`serve_full_text_guarded`), then projection. |

**BookReader path (PR #3101):** uploads write a sanitized sidecar. Full-text
endpoints may **prefer** that sidecar as `content_format=html` **only after**
rights already released `full_text`, **only** when `serve_reader_html` returns
`available` + `content_format=html` + a body. Gated / taken-down / missing /
stale-version sidecars stay on the text path. Public `/books/{id}/full-text`
uses `owner=False`; owner path requires `_owner_read_policy_tag`.

Thesis: [`docs/html-first-design-thesis.md`](./html-first-design-thesis.md).
Mini dogfood: [`docs/anti-ek-mac-mini-dogfood.md`](./anti-ek-mac-mini-dogfood.md).

## PATH (required)

```bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.kimi-code/bin:$PATH"
```

Binaries on this Mini (2026-09-17):

| CLI | Path | Version |
|-----|------|---------|
| `claude` | `/opt/homebrew/bin/claude` | Claude Code 2.1.42 |
| `grok` | `~/.local/bin/grok` | grok 1.0.30 |
| `glm-codex` | `~/.local/bin/glm-codex` | Codex CLI 0.154.0 |
| `glmf-codex` | `~/.local/bin/glmf-codex` | Codex CLI 0.154.0 |
| `codex` | `~/.local/bin/codex` | Codex CLI 0.154.0 |
| `mimo` | `~/.local/bin/mimo` | 0.1.0 |
| `kimi` | `~/.kimi-code/bin/kimi` | 0.43.0 |
| `gh` | `/opt/homebrew/bin/gh` | installed |

Worktree: `/Users/slimydog/Antiek/.worktrees/anti-ek-use-main-20260917`

## Role split (speed + quality)

Use **three different binaries**. Do not let the implementer grade its own patch.

| Role | Job | Preferred on this Mini | Backup |
|------|-----|------------------------|--------|
| **Implementer** | Write/fix the patch on a branch. Fast iteration. | `glmf-codex exec` or `glm-codex exec` | `mimo run` |
| **Reviewer** | Correctness, tests, dual-structure, §9 gates. Careful. | `claude -p` | `kimi -p` |
| **Adversary / rights** | Attack rights leaks, XSS (`content_format=html` on unsanitized bytes), auth bypass (`unauthenticated_local` → `owner_read`), DuckDB second-writer, product/UI mismatch. | `grok -p` / `--single` (product/UI) + `codex review` (rights) | `mimo run` |

**When to use which**

- **glmf / glm** — fast code. `glmf-codex exec "..."` to implement; `glmf-codex review --base origin/main` for a second-pass mechanical review. Prefer **review** over **exec** when you only want findings (exec will tool-wander).
- **claude** — careful review. `claude -p "..."` with the diff in the prompt (or `--print`). Best Reviewer.
- **grok** — product/UI critique. `grok -p "..."` (`--single`). Ask whether `/read/:id` actually gets HTML-native rendering, empty states, rights copy.
- **mimo** — alternate implementer. `mimo run "..."`. Use when glm/claude is busy or you want a second patch sketch.
- **kimi** — print mode works: `kimi -p "..." --output-format text`. Use if Claude is saturated; do not assume tool use in `-p` without `--auto`.
- **codex** (upstream) — same shape as glm forks: `codex review` / `codex exec`. Use as extra Adversary if glm slots are full.

Assign **at least two different CLIs** as Reviewer on any merge-bound PR.

## Exact noninteractive invocations (this Mini)

All of these are headless. Do not paste secrets into prompts.

### Claude Code — print / review

```bash
claude -p "Review this Antiek diff. High-confidence only.

$(git diff origin/main...HEAD)" --output-format text
```

Optional: `--model sonnet` / `--effort medium`. Tool-using print:

```bash
claude -p "Apply the one-line test assertion described below." --allowedTools "Read,Edit,Bash(git:*)"
```

Do **not** use `--dangerously-skip-permissions` on the Mini (it has network +
the real DuckDB). Review-only prompts should not need Bash/Edit.

### Grok Build — single-turn

```bash
grok -p "Product/UI critique of this Antiek BookReader change. Does /read/:id get HTML-native content? Any empty-state or rights-copy miss?

$(git diff origin/main...HEAD)" --permission-mode plan --disable-web-search
```

Equivalent flag: `grok --single "..."`. Headless agent (stdio) is `grok agent stdio`, not needed for swarm reviews.

### GLM / GLMF / Codex — review (preferred) or exec

```bash
# Mechanical review of git changes vs main (no need to stuff the diff in argv)
glmf-codex review --base origin/main "Antiek PR review. High-confidence only. Dual-structure: DuckDB truth, HTML sidecar projection. §9 rights, no metadata HTML-trust stamp."

# Fast implement
glmf-codex exec "On this branch, add a public-path assertion to tests/test_sources_upload.py: personal_reading upload must not serve content_format=html on GET /books/{id}/full-text."

# Fallbacks
glm-codex review --base origin/main "..."
codex review --base origin/main "..."
```

`review` is noninteractive by design. `exec` will read the tree with tools —
fine for implement, noisy for review.

**Mini gotcha (Codex 0.154.0):** `glmf-codex review --base origin/main "prompt"` errors with `cannot be used with '[PROMPT]'`. Use `--base` alone, or put custom instructions in `claude -p` / `grok --single` / `glmf-codex exec`.

### MiMo — run

```bash
mimo run "Implement the public-path full-text assertion for personal_reading uploads. Do not refactor." --dir "$(pwd)"
```

Noninteractive auto-approve (only if you intend writes): `--dangerously-skip-permissions`.

### Kimi — print mode (works)

```bash
kimi -p "Review this Antiek diff. High-confidence only.

$(git diff origin/main...HEAD)" --output-format text
```

`--auto` / `-y` only when you want it to edit. Default `-p` prints and exits.

## Parallel review recipe

```bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.kimi-code/bin:$PATH"
cd /Users/slimydog/Antiek/.worktrees/anti-ek-use-main-20260917   # or current PR worktree
./scripts/anti-ek-swarm-review.sh origin/main
# writes /tmp/antiek-swarm-review-{claude,glmf,grok}.txt — no secrets
```

Manual (product files only, exclude swarm docs):

```bash
git diff origin/main...HEAD -- interfaces/research/api/books.py \
  interfaces/research/api/upload_routes.py tests/test_sources_upload.py \
  > /tmp/antiek-swarm-pr.diff

PROMPT='You are reviewing an Antiek PR. High-confidence only.
1) §9.0 rights: gated/personal text must not leak on public paths
2) HTML trust: only sanitized sidecar / is_trusted_sanitized may be content_format=html
3) Auth: unauthenticated_local must not gain owner_read
4) DuckDB: no second writer; no prod DB reset
5) Dual-structure: DuckDB is truth; HTML sidecar is a projection
Output: (a) blocking file:line (b) nits (c) LGTM if clean.
Do not suggest weakening gates.'

claude -p "${PROMPT}

$(cat /tmp/antiek-swarm-pr.diff)" --output-format text \
  > /tmp/antiek-swarm-review-claude.txt 2>&1 &

glmf-codex review --base origin/main \
  > /tmp/antiek-swarm-review-glmf.txt 2>&1 &

grok --single "Product/UI adversary. ${PROMPT}

$(cat /tmp/antiek-swarm-pr.diff)" --disable-web-search \
  > /tmp/antiek-swarm-review-grok.txt 2>&1 &

wait
```

Fold **only** high-confidence trivial fixes onto the PR branch. No force-push
if another executor is merging. `git fetch` first.

## CI merge bar (standing)

Merge when **tsc + vitest + keystone + mypy/ruff** (and visual if present) pass.
Do **not** block forever on a single hung pytest shard if the other shards
passed (same bar as PR #3100).

## Coordination

- Canonical repo: `Slimydog21/Antiek`
- Shared DuckDB + isolated events: `scripts/start-shared-duckdb-mac-mini.sh`
- Owner session: `scripts/mac-mini-owner-dev-login.sh` (never print tokens)
- Another agent may already be on the PR branch — `git fetch`; do not force-push.
