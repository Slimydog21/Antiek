# `bd` contract: verbatim transcripts

All commands run 2026-09-29 in a scratch git repo (`bd init` then a two-bead dependency), with
`bd` 1.3.0 (Homebrew), on macOS arm64. Empty lines removed for compactness; no other edits.

## Init surface

```
$ bd init
✓ Codex instructions installed
  File: <repo>/AGENTS.md
Installing Beads agent skill...
✓ Beads agent skill installed
  Skill: .agents/skills/beads/SKILL.md
✓ Cursor integration installed (rules + skill + hooks)
  ✓ Committed beads files to git
⚠ No Dolt remote configured
  Issues are stored in local Dolt. .beads/issues.jsonl is an export,
  not cross-machine sync or the source of truth.
✓ bd initialized successfully!
  Backend: dolt   Mode: embedded   Database: bdemo   Issue prefix: bdemo
```

```
$ git show --stat HEAD
 .agents/skills/beads/SKILL.md           |  80 +
 .agents/skills/beads/agents/openai.yaml |   4 +
 .beads/.gitignore                       |  81 +
 .beads/README.md                        |  81 +
 .beads/config.yaml                      |  72 +
 .beads/hooks/post-checkout              |  59 +
 .beads/hooks/post-merge                 |  59 +
 .beads/hooks/pre-commit                 |  59 +
 .beads/hooks/pre-push                   |  59 +
 .beads/hooks/prepare-commit-msg         |  59 +
 .beads/metadata.json                    |   7 +
 .claude/settings.json                   |  15 +
 .codex/config.toml                      |   2 +
 .codex/hooks.json                       |  51 +
 .cursor/hooks.json                      |  20 +
 .cursor/rules/beads.mdc                 |  67 +
 .gitignore                              |   7 +
 AGENTS.md                               | 127 +
 CLAUDE.md                               |  77 +
 19 files changed, 986 insertions(+)
```

## Ledger + dependency

```
$ A=$(bd create "lane A: extract sheet1" -p 1 -t task --json | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
$ B=$(bd create "lane B: verify sheet1" -p 1 -t task --json | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
A=bdemo-1nx B=bdemo-i1b
$ bd dep add $B $A
✓ Added dependency: bdemo-i1b (lane B: verify sheet1) depends on bdemo-1nx (lane A: extract sheet1) (blocks)
```

## Ready filters blocked work

```
$ bd ready
○ bdemo-1nx P1 lane A: extract sheet1
Ready: 1 issues with no active blockers
```

Only the unblocked bead appears; `bdemo-i1b` is held back by its dependency.

## Claim, lease, heartbeat

```
$ bd update bdemo-1nx --claim
✓ Updated issue: bdemo-1nx — lane A: extract sheet1
$ bd heartbeat bdemo-1nx
✓ Heartbeat bdemo-1nx — lane A: extract sheet1 (lease refreshed)
$ bd list --status in_progress --json
[
  {
    "id": "bdemo-1nx", "title": "lane A: extract sheet1", "status": "in_progress",
    "priority": 1, "issue_type": "task",
    "assignee": "Slimydog21",
    "owner": "194121339+Slimydog21@users.noreply.github.com",
    "created_at": "2026-09-29T12:29:24Z",
    "updated_at": "2026-09-29T12:35:24Z",
    "started_at": "2026-09-29T12:35:24Z",
    "lease_expires_at": "2026-09-29T12:40:24Z",
    "heartbeat_at": "2026-09-29T12:35:24Z",
    "dependency_count": 0, "dependent_count": 1, "comment_count": 0
  }
]
```

`started_at` 12:35:24 -> `lease_expires_at` 12:40:24. **Default lease TTL is 5 minutes**, which
is why a long-running lane must heartbeat.

## Reclaim (dead-worker recovery)

```
$ bd reclaim --help
Revert in_progress issues whose lease has gone stale back to ready.
When a worker claims an issue it takes a lease that expires after a TTL, kept
alive by 'bd heartbeat'. A worker that dies stops heartbeating, so its lease
expires and its issue would otherwise stay in_progress forever. reclaim is the
reaper: it finds in_progress issues whose lease expired more than --older-than
ago, clears the assignee, and sets them back to open so another worker can
claim them. The previous owner's stale lease is recorded as a recovery event.
--older-than is a grace window past lease expiry ... Run it from a supervisor on a timer with a window
of roughly 2× the claim TTL.
```

## Merge slot (one writer at a time)

```
$ bd merge-slot create
✓ Created merge slot: bdemo-merge-slot
$ bd merge-slot check
✓ Merge slot available: bdemo-merge-slot
$ bd merge-slot acquire
✓ Acquired merge slot: bdemo-merge-slot
  Holder: Slimydog21
$ bd merge-slot --help
A merge slot is an exclusive access primitive: only one agent can hold it at a time.
The slot uses: status=open (available) | status=in_progress (held);
metadata.holder; metadata.waiters (priority-ordered queue)
```

## Gates (async waits)

```
$ bd gate create --help
Create an ad-hoc gate issue that blocks another issue until resolved.
The blocked issue will not appear in 'bd ready' until the gate is resolved via 'bd gate resolve'.
Gate types:
  human   - Requires manual 'bd gate resolve' (default)
  timer   - Auto-resolves after --timeout duration
  gh:run  - Waits for GitHub Actions workflow
  gh:pr   - Waits for PR merge
Examples:
  bd gate create --blocks bd-abc
  bd gate create --type=human --blocks bd-abc --reason="Need design review"
  bd gate create --type=timer --blocks bd-abc --timeout=2h
  bd gate create --type=gh:pr --blocks bd-abc --await-id=42
Flags: --await-id  --blocks (required)  --reason  --timeout  --title  --type
```

## Swarm (epic -> DAG)

```
$ bd swarm --help
Swarm management commands for coordinating parallel work on epics.
A swarm is a structured body of work defined by an epic and its children,
with dependencies forming a DAG (directed acyclic graph) of work.
Available Commands: create, list, status, validate
```
