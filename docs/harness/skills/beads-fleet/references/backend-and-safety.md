# beads backend, leases and safety

Sources: `bd` 1.3.0 on this machine (help text and live runs, 2026-09-29), the project docs at
https://github.com/gastownhall/beads, and a separate research lane that read the same sources
independently. Where a claim is from a lane rather than from my own run, it is marked.

## Backend modes

```
$ bd init --help
By default, beads uses an embedded Dolt engine (no external server needed).
Pass --server to use an external dolt sql-server instead. In server mode,
set connection details with --server-host, --server-port, and --server-user.
      --external          Server is externally managed (skip server startup); use with --shared-server or --server
      --proxied-server    [EXPERIMENTAL] Use a per-workspace proxied dolt sql-server
```

    $ bd context      # effective backend identity and repository context
    $ bd where        # active beads location, prefix, database

- **Embedded (the `bd init` default)** is single-writer. Fine for one agent; not a fleet.
- **`--server`** points at an external `dolt sql-server`. This is the multi-writer path, and it
  adds an always-on local process.
- **`--global`** on other commands targets a shared server database (`beads_global`), which is
  the closest thing to one ledger across repositories.

## Leases, reclaim, and why replication matters

- A claim takes a lease. Measured: `started_at` 12:35:24 -> `lease_expires_at` 12:40:24, so the
  default TTL is **5 minutes**; `bd heartbeat` refreshes it.
- `bd reclaim` reverts `in_progress` beads whose lease expired more than `--older-than` ago,
  clears the assignee, records a recovery event, and returns them to `open`. Its help recommends
  running it from a supervisor on a timer at roughly **2x the claim TTL**.
- Lease rows are **not replicated** (they are `dolt_ignored`, migration 0055). Status and
  assignee do replicate. So on a second clone, `bd reclaim` will skip foreign leases, and
  `--any-replica` lets it steal a live peer's unit. The rule that follows: **the grace window and
  the TTL must both exceed the sync interval**, or reclaim becomes a random work-stealer.
- `bd heartbeat` (Dolt lease) and prime-agent's `rlm_heartbeat` (session re-entry) are unrelated
  commands with a dangerously similar name.

## Init write surface

Default `bd init` on 2026-09-29 wrote 19 files / 986 insertions, including `AGENTS.md` (127
lines), `CLAUDE.md` (77 lines), five git hooks under `.beads/hooks/`, `.claude/settings.json`,
`.codex/{config.toml,hooks.json}` and `.cursor/{hooks.json,rules/beads.mdc}`, and made its own
commit. `--skip-agents` and `--skip-hooks` suppress the harness-config half; `bd setup <tool>`
installs a specific integration later; `--stealth` configures invisible per-repo git settings.

## Telemetry

Measured: `bd config list` reported `metrics.disabled = false` and
`metrics.endpoint = https://gastownhall-eventsapi.com/mp/collect`. On disk, `~/.beads/` held a
`machine-id` and `eventsData/` with 80 `.evtq` queue files, each a JSON payload with a
`distinct_id` hash, `app_name`, `app_version`, `platform` and events such as
`{"name":"cli_command","attributes":[{"key":"command","value":"context"}]}`, plus a
`.last-flush` marker. So command-level events are queued locally and a flush is attempted to
that endpoint. *Whether a payload actually left the machine was not established.*

Disabling it is a **user-scope** setting, not per-repo:

```
$ bd config set metrics.disabled true
Set metrics.disabled = true (in /Users/slimydog/.config/bd/config.yaml)
$ bd config get metrics.disabled
true
```

`~/.config/bd/config.yaml` now reads:

```yaml
metrics:
    disabled: true
    endpoint: https://gastownhall-eventsapi.com/mp/collect
    notice_shown: true
```

## Skew and maintenance

- **Schema skew:** `bd` refuses a database migrated by a newer binary. 1.3.1-rc.1 exists upstream
  and is not what Homebrew installs; do not mix.
- **Dolt CLI skew:** upstream docs pin the `dolt` CLI at 2.2.0 because 2.3.x broke
  `DOLT_RESET('--hard')` on some fresh databases, which `bd flatten`, compaction and the
  merge-settle path use. This machine has **dolt 2.3.5**. The embedded engine links its own copy
  from `go.mod`, so embedded is unaffected - a server-mode rollout here would be off-pin.
- **History growth:** Dolt auto-commits on every write by default (`--dolt-auto-commit on`), so
  `bd compact` and `bd flatten` exist. The scratch database was 3.2 MB after a short session.
- **Actor is not auth:** `bd serve` states that an actor on a request is caller-asserted
  provenance for the audit trail, not authenticated identity - any local process can pass any
  `--actor`. Fine on one laptop; it is not an identity boundary between harnesses.
- **Sync vs GitHub:** `bd sync` talks to a Dolt remote (`refs/dolt/data` on the git remote);
  `bd github sync` talks to the GitHub Issues API and needs its own token.
