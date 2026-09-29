---
name: harness-upstream
description: >-
    Turn lessons from this machine into a reviewable pull request against the product repository -
    the push direction, where harness-drift is the pull direction. Use when asked to upstream a
    lesson, to port a skill into Antiek, to propose harness changes as a PR, or to see which local
    capabilities the product repo does not have. It stages a branch and a commit in a scratch clone
    and never pushes. Not for ordinary code changes, which belong in a normal feature branch.
---

# harness-upstream

`harness-drift` asks "what changed in production?" This asks the other question: **which of my
hard-won lessons should production inherit, and what does that PR look like?**

```bash
python3 ~/.agents/skills/harness-upstream/scripts/harness_upstream.py plan     # what is portable
python3 ~/.agents/skills/harness-upstream/scripts/harness_upstream.py stage    # build the branch
```

## What it proposes, and why that set

- **The rules** — the transferable lessons recorded in the engagement README, each naming the
  incident that produced it. Rules travel; code usually does not.
- **A curated set of skills** — the ones whose *rules* belong in a product repo, listed in
  `~/.prime/agent/harness-portable.json`. Edit that file to change the proposal. The operator's
  whole library is 113 skills, most of them third-party ports; proposing all of them would bury the
  signal in a PR nobody could review.
- **Doctrine deltas, listed but never applied.** `CLAUDE.md` in the repo and
  `~/.prime/agent/APPEND_SYSTEM.md` here overlap. Copying doctrine automatically in either direction
  is how two files start disagreeing; the proposal names the deltas and leaves the judgement.

## The safety model

- It clones `origin/main` into a scratch directory. **It never touches the operator's working tree
  at `~`.**
- It creates a branch and a commit, then **prints** the push and `gh pr create` commands. It does not
  push. A human reads the diff first.
- It refuses to write outside the destination directory.

## The topology this depends on

The git root on this machine is the **home directory** (`master`, remote `Slimydog21/Antiek`), and
`origin/main` is the product's tree - they have diverged by 1,720 and 4,917 commits with unrelated
roots. So "the repo" for this tool means **`origin/main`**, resolved explicitly, never the local
branch.
