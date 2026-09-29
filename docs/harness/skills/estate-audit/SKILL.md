---
name: estate-audit
description: >-
    Run a report-only health check of this machine's agent estate - credential state, provider
    lanes, Modal billing and volumes, skill frontmatter defects, shadowed binaries, stale state
    files, disk, tailnet exposure, and drift in the production harness. Use when asked whether the
    harness is healthy, what changed, what is broken or costing money, before a long unattended run,
    or when the weekly report at ~/.prime/agent/estate-report.md looks stale. The report is injected
    at session start by the estate-report extension. Not a fixer.
---

# estate-audit

One command answers "is anything quietly wrong with this estate":

```bash
python3 ~/.agents/skills/estate-audit/scripts/estate_audit.py          # human summary
python3 ~/.agents/skills/estate-audit/scripts/estate_audit.py --json   # machine-readable
```

It writes `~/.prime/agent/estate-report.md`. The **`estate-report` extension reads that file at
session start** and injects the warnings, so drift arrives without being asked for. A weekly launchd
job (`com.prime-agent.estate-audit`, Mondays 09:00) refreshes it.

## It reports; it never fixes

That is deliberate. On 2026-09-29 a "fix" of mine turned a loud, correct failure into a quiet wrong
success (a local-model preflight went green while every real request failed). An audit that changes
things can do the same. Fixes are the operator's call.

## What it checks

| Area | Catches |
|---|---|
| credentials | `gws` auth state, the X CLI's real call, Modal auth |
| modal | cash due this cycle and the volume count |
| skills | frontmatter that will not parse, a description over 1024 chars, a name that does not match its directory |
| binaries | a broken symlink on PATH, or several installs of one name |
| state | provider-health files with stale `exhausted` flags, dead daemons |
| disk · tailnet | the data volume, grok peers, and whether a bot's Docker API answers *from here* |
| drift | production harness changes since the last baseline (via `harness-drift`) |

## Two lessons baked into the checks themselves

- **A check must not cry wolf.** An early version flagged 24 skills for a colon-space in the
  description; they all load fine, so the heuristic was removed. A report that raises false alarms
  gets ignored, which is worse than no report.
- **A source-blind check must say so.** The tailnet check can only see reachability *from this
  machine*, so when a firewall scopes a port to this host it reports "accepts connections from this
  Mac" as information, not as a warning about exposure.
