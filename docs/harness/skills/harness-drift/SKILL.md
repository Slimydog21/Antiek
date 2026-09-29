---
name: harness-drift
description: >-
    Track the harness surface in the production repository against this machine, so a lesson
    learned locally can travel out as a PR and a change made in production can be brought back in.
    Use when asked what changed in production, whether the local harness matches the deployed one,
    before porting a production change onto this machine, or when auditing drift between the two.
    Also use to inspect this machine's git topology, which is unusual. Not for ordinary code review,
    which the code-review and ocr-review-gate skills cover.
---

# harness-drift

The harness lives in two places, and nothing used to watch either:

| Side | What it is |
|---|---|
| **Production** | `origin/main` of `github.com/Slimydog21/Antiek` - the tree deployed to antiek.ai. Its harness surface is `CLAUDE.md`, `skills/` (21 files), `specs/` |
| **This machine** | `~/.agents/skills/`, `~/.prime/agent/` (doctrine, extensions), the audit report |

```bash
python3 ~/.agents/skills/harness-drift/scripts/harness_drift.py scan      # drift + skill comparison
python3 ~/.agents/skills/harness-drift/scripts/harness_drift.py diff      # production vs last baseline
python3 ~/.agents/skills/harness-drift/scripts/harness_drift.py compare   # same-named skills, both sides
python3 ~/.agents/skills/harness-drift/scripts/harness_drift.py apply <repo-path>   # withdraw one file
python3 ~/.agents/skills/harness-drift/scripts/harness_drift.py baseline  # accept current prod state
```

## The topology here is unusual, and it matters

Measured 2026-09-29:

- **The git root is the HOME DIRECTORY.** `~/.git` exists; `~/Antiek` has no `.git` of its own.
  `git rev-parse --show-toplevel` from anywhere under `~` returns `/Users/slimydog`.
- That repo's remote is `github.com/Slimydog21/Antiek.git`, on branch **`master`**.
- **`master` and `origin/main` have diverged hard**: `1720` commits on master not in main, `4917`
  on main not in master, both with commits from the same day. Their root trees are unrelated:
  - `master`: `.gitignore`, `Antiek/`, `brain-on-a-motorbike/`
  - `origin/main`: `.github`, `CLAUDE.md`, `README.md`, `skills/`, `specs/`, HANDOFF files...

So the home repo and the product repo share one remote but are effectively two different
repositories. Anything the scanner reports about `origin/main` is the **product's** harness, not
this machine's tree.

**A secret sweep was run while establishing this**: all 2,960 tracked files were grepped for
`sk-`, `sk-ant-`, `xai-`, `ghp_`, `AKIA`, `AIza` and PEM private-key headers. **Zero matches.** The
home-directory-as-repo structure is not leaking credentials - worth re-running whenever a new
credential file is added, because the blast radius if that changes is a public push.

## What the scanner will not do

- It will not guess a mapping between production `skills/` and local `~/.agents/skills/`. They are
  different kinds of thing: production `skills/` holds Python packages (`domain/extract.py`,
  `verification/rlm.py`), while local skills are `SKILL.md` directories. `compare` reports only
  exact same-name matches, and 0 of them exist today - correctly, not as a failure.
- It will not `apply` anything outside `skills/`. Doctrine (`CLAUDE.md`, `APPEND_SYSTEM.md`) and the
  `.infinite/` control plane need human judgement; the tool refuses and says so.
- It never writes to the repository. `apply` withdraws *from* it.

## Bringing a production change back

```bash
python3 .../harness_drift.py diff                     # what moved in production
git -C ~ show origin/main:CLAUDE.md | less            # read it
python3 .../harness_drift.py apply skills/verification/rlm.py   # withdraw one file (backs up)
python3 .../harness_drift.py baseline                 # accept the new state once reviewed
```

The weekly `estate-audit` runs `diff` and reports the counts, so drift arrives without being asked
for.
