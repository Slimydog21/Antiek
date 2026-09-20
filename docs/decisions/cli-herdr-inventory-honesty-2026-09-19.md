# Decision: CLI/Herdr inventory honesty (probe tip + w7 tabs)

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** cli-herdr-swarm-ready-2026-09-19 (#3180–#3181); `docs/anti-ek-cli-swarm.md`; Herdr Antiek **w7**.

## Context

`--check` proved core CLIs but: preferred dogfood path still pointed at
`deploy-main-20260917` (often tip-lagged); no live w7 tab inventory; companion
`swarm-review-pr.sh` kept Homebrew-first PATH and `glmf-codex exec` (wrong for
review); books/upload specialty diff silently under-scoped modern Anti-Ek PRs;
playbook kimi version + tab table drifted from Mini probe.

## Decision

1. Prefer `/private/tmp/antiek-main-probe` in `--check` + playbook; report tip
   SHAs; keep legacy trees as secondary OK/MISS.
2. Inventory Herdr: focused workspace, `w7_tab_labels`, soft WARN on missing
   role-ish tabs (`claude` / `glmf|codex|glm` / `herdr`) — never create/rename.
3. `swarm-review-pr.sh` → thin `exec` alias of `anti-ek-swarm-review.sh`.
4. Always full `${BASE}...HEAD` diff (retire books-only specialty path).
5. `tests/scripts/test_anti_ek_swarm_review.sh` — bash -n, wrapper honesty,
   `--dry-run` / `--check` RESULT shape (no model tokens).

## Non-goals

- New Herdr product features / auto-creating tabs.
- Burning model tokens in CI.
- Flipping mount / Synquery / G2 / email / inventing CPM.

## Consequences

CLI/Herdr grade rises with honest tip + tab inventory evidence on Mini
`--check`. Agents stop driving stale worktrees or the deprecated exec wrapper.
