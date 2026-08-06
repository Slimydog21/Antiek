# SWARM BRIEF — kimi-cc — BYO-tools chassis + SEC EDGAR connector

You are an autonomous coding agent. Execute this ONE bounded sub-goal completely, in THIS
worktree only. Real production code for the Antiek platform.

## Hard guardrails (violating these fails the task)
- Work ONLY inside this worktree (CWD `/tmp/antiek-swarm/kimi-byotools`). NEVER `cd` out, NEVER
  touch `~/Antiek/platform` or another worktree, NEVER modify `main`.
- NEVER `git push`. Commit locally to `swarm/byo-tools-edgar` only.
- NO stub-theater. If genuinely blocked, write `BLOCKED.md` and stop — never fake green.
- Tests use `httpx.MockTransport` / fixtures — NO live network calls. NEVER print secrets.
- Match house style (read neighbors, e.g. `acquisition/`). venv:
  `~/Antiek/platform/.venv/bin/python`. Run tests from this worktree root.

## The sub-goal
Build the first "bring your own tools" connector: a **paste-a-key chassis** + the **SEC EDGAR**
connector (free, keyless — the degenerate case of paste-a-key). Read this spec IN FULL first:
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/byo-tools-connectors.md`

### Scope (bounded — exactly this)
1. Create a connector package (use the location/name the spec designates; if none, use
   `substrate/connectors/`) with a small **`Connector` base** + a **paste-a-key chassis**
   (a connector that holds an optional user key via the existing secret-storage posture —
   grep `runtime/byok` — and never echoes it; keyless is the degenerate case).
2. **`EdgarConnector`** — SEC EDGAR full-text search
   (`https://efts.sec.gov/LATEST/search-index?q=...` / `https://www.sec.gov/cgi-bin/...`):
   requires a descriptive `User-Agent` header (SEC mandates one), throttled to ≤10 req/s.
   Expose a `search(query, ...) -> list[result]` that builds the correct URL, sends with the
   UA header, and parses the JSON response. Keyless.

### Acceptance (must pass for real)
Tests with `httpx.MockTransport` (NO live calls) proving: `search()` builds the correct EDGAR
URL; the required `User-Agent` header is present on the request; a fixture response parses into
structured results; the throttle spaces successive requests (inject a fake clock). Report exact
pass counts.

### Non-goals
NO OAuth connectors (Reddit/X/YouTube). NO other vendors (Polygon/FMP/Prolific). NO frontend.
Just the chassis + EDGAR + tests.

## When done
`git add -A && git commit -m "feat(connectors): paste-a-key chassis + SEC EDGAR connector"`, then
write `DONE.md`: files, exact test command + real result, honest gaps.
