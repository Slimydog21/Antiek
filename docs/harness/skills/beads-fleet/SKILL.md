---
name: beads-fleet
description: >-
    Drive a prime-agent subagent swarm from the beads issue ledger (`bd`) so that lanes, claims,
    blockers, waits and dead workers are recorded in a durable DAG instead of living in a prompt.
    Use when fanning work out to several children or lanes, when parallel lanes must not write the
    same artifact at once, when a lane has to wait for CI, a PR merge, a human sign-off or a
    timer, when a child dies mid-task and its unit must be recovered, and when work must survive
    compaction or handoff. Also use when asked what is ready, to claim or close a unit of work, or
    to hand work to another harness. Use the project's own `.agents/skills/beads` skill as well
    when present, for the base CLI tour. Not for same-turn scratch planning, which needs no ledger.
---

# beads-fleet: the swarm ledger

Beads' own skill (installed by `bd init` at `.agents/skills/beads/SKILL.md`, which prime-agent
discovers automatically in that repo) teaches the base CLI. **This skill is the harness layer on
top of it**: how prime-agent's fan-out, lane and merge disciplines map onto beads primitives, so
those disciplines stop being prose in a prompt and become rows in a database.

Verified against `bd` 1.3.0 (Homebrew, `/opt/homebrew/bin/bd`) on this machine, 2026-09-29.
Transcripts in [references/bd-contract.md](references/bd-contract.md); backend, lease and safety
detail in [references/backend-and-safety.md](references/backend-and-safety.md).

## Before a fleet: check the backend

**The default backend cannot serve a fleet.** `bd init --help` states it plainly: "By default,
beads uses an embedded Dolt engine (no external server needed). Pass `--server` to use an
external dolt sql-server instead." Embedded is single-writer, so several children calling `bd`
at once is not a supported configuration, however lucky the first few writes look.

```bash
bd context            # backend identity, prefix, database for this repo
bd where              # the .beads path
```

For more than one writer, initialize with `--server` (or the experimental `--proxied-server`)
and see [references/backend-and-safety.md](references/backend-and-safety.md) before trusting
leases across clones.

## Where state belongs

| Kind of knowledge | Home |
|---|---|
| Project work, blockers, decisions, who owns what | **beads** - shared, survives compaction, visible to other harnesses |
| Harness lessons, routing facts, agent behaviour | **continual harness** (`refine.run`) - private to this agent |
| The current turn's checklist | neither |

`bd remember "..."` exists and is injected at `bd prime` time. Use it for project facts, not for
harness policy.

## The lane protocol

One bead per unit of delegated work; the bead carries the lease.

```bash
bd create "lane A: extract sheet1" --description="why and what" -t task -p 1 --json
bd ready --json                      # unblocked work only
bd ready --claim --json              # ATOMIC: claim the first ready issue in one call
bd heartbeat <id>                    # refresh the lease while working
bd close <id> --reason="..."
bd reclaim --older-than 10m          # supervisor sweeps units whose worker died
```

Measured behaviour worth designing against:

- A claim takes a **lease**. JSON exposes `lease_expires_at`; the default TTL was **5 minutes**
  (12:35:24 start, 12:40:24 expiry). `bd heartbeat` refreshes it and prints `lease refreshed`.
- `bd ready` **filters blocked work out** - a bead depending on another did not appear.
- `bd reclaim` reverts `in_progress` beads whose lease expired past a grace window, records the
  previous owner as a recovery event, and frees the unit for another worker. Its own help
  recommends running it from a supervisor on a timer at roughly **2x the claim TTL**.

**Naming trap.** `bd heartbeat` is NOT prime-agent's `rlm_heartbeat`. One refreshes a Dolt lease
row so a unit is not reclaimed; the other re-enters an agent session. Confusing them either lets
a live child's unit be reclaimed or spawns session prompts that never touch `leases`.

**Consequence for fan-out:** a child must claim its own unit, because the claim is what makes the
unit recoverable if the child never reports. Work handed over by message leaves nothing to reclaim.

## One writer at a time

For any artifact with one writer - a shared workbook, an index, a lockfile, a merge:

```bash
bd merge-slot create      # once per repo: creates <prefix>-merge-slot
bd merge-slot check       # free, or held by whom
bd merge-slot acquire     # exclusive
bd merge-slot release
```

This holds `status`, `metadata.holder` and `metadata.waiters`, so a second lane waits instead of
racing. It is the primitive the shared-artifact lane policies were approximating in prose.

## Waiting on the outside world

```bash
bd gate create --blocks <id> --type=gh:pr --await-id <pr-number>
bd gate create --blocks <id> --type=gh:run --await-id <run-id>
bd gate create --blocks <id> --type=timer --timeout=2h
bd gate create --blocks <id> --type=human --reason="owner sign-off"
bd gate check                 # evaluate and close resolved gates
bd gate resolve <gate-id>     # close a human gate
```

A gated bead disappears from `bd ready` until the gate resolves. Limits: cross-rig bead gates do
not resolve on their own, and a proxied-server `bd close` cannot verify a bead gate. Trust
`human` and `timer` first.

## Binding artifacts to a unit

```bash
bd provenance record <id> --kind commit --ref <sha>
bd provenance log <id>
```

Append-only, idempotent, and it binds a bead to an external artifact (git SHA, PR, branch,
work-id, transcript). Use it instead of pasting what was done into a closing comment.

## Adopting it in a repo

```bash
bd init --skip-agents --skip-hooks    # then add the integrations you actually want
```

`bd init` is not small. Measured 2026-09-29 the **default** init wrote **19 files / 986
insertions** and made its own commit:

- `.agents/skills/beads/SKILL.md` - which prime-agent discovers in that repo automatically,
- `AGENTS.md` (127 lines) and `CLAUDE.md` (77 lines) - prime-agent reads `AGENTS.md` as context,
- `.beads/` (config, embedded Dolt database, README, `.gitignore`),
- **git hooks**: `pre-commit`, `pre-push`, `post-merge`, `post-checkout`, `prepare-commit-msg`,
- config for other harnesses: `.claude/settings.json`, `.codex/{config.toml,hooks.json}`,
  `.cursor/{hooks.json,rules/beads.mdc}`.

`--skip-agents --skip-hooks` avoids rewriting the colleague harnesses' config as a side effect of
setting up a queue. `bd setup <claude|cursor|codex|...>` installs those integrations explicitly
when they are wanted; `--stealth` configures invisible per-repo git settings.

**Telemetry is on by default and is now off on this machine.** `bd` queues command events under
`~/.beads/eventsData/*.evtq` with a machine-id, targeting
`https://gastownhall-eventsapi.com/mp/collect`. Disable it in the user config, which is
`~/.config/bd/config.yaml` and covers every repo:

```bash
bd config set metrics.disabled true     # writes ~/.config/bd/config.yaml
bd config get metrics.disabled          # true
```

## Machine-readable by default

```bash
bd list --json | python3 -c "import sys,json; [print(i['id'], i['status'], i['title']) for i in json.load(sys.stdin)]"
bd create "title" --json | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])"
```

## Anti-patterns

- **Do not run a fleet on the embedded backend.** Single writer. Use `--server` first.
- **Do not treat `.beads/issues.jsonl` as the source of truth** or as a backup, and do not
  `bd import` during normal operation. It is an export.
- **Do not use `bd edit`** - it opens an interactive editor and will hang a headless agent. Use
  `bd update` flags.
- **Do not create markdown TODO files** as the project's work record when beads is present.
- **Do not close a bead to tidy a list.** A closed bead is a claim that the work is done, and
  `bd provenance` keeps the receipt.
- **Do not skip `bd prime` after compaction** when workflow context is missing.
- **Do not mix `bd` versions against one database.** `bd` refuses a database migrated by a newer
  binary, and `BD_IGNORE_SCHEMA_SKEW` is not a plan.

## Verification

```bash
bd --version                 # expect: bd version 1.3.0 (Homebrew)
bd where                     # .beads path, prefix, database
bd ready --json              # only unblocked issues
bd merge-slot check          # available | held by <holder>
bd gate list                 # open gates
bd config get metrics.disabled   # expect: true on this machine
```
