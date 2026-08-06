# SWARM BRIEF — deepseek-cc — BYO-tools: YouTube + Financial Modeling Prep connectors

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. STACKED on the round-1 BYO-tools lane — the connector chassis + SEC EDGAR
connector already exist here (read them first, reuse the chassis). (A prior agent left this
sub-goal unbuilt; you are building it fresh.)

## Hard guardrails
- Work ONLY inside this worktree (`/tmp/antiek-swarm3/deepseek-tools`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm3/byo-tools-youtube-fmp`.
- NO stub-theater. If blocked, `BLOCKED.md` + stop. Tests use `httpx.MockTransport` only, NO live
  calls. NEVER print/echo secrets. venv: `~/Antiek/platform/.venv/bin/python`, run from worktree root.
- ruff + mypy --strict on new code. Match the existing connector chassis style exactly.

## Context already on this branch (do NOT rebuild — reuse)
`runtime/connectors/base.py` (the `Connector` base + paste-a-key chassis + rate governor) and
`acquisition/edgar/client.py` (the EDGAR connector) — follow this exact pattern.

## The sub-goal
Add two paste-a-key BYO-tools connectors on the SAME chassis. Read this spec IN FULL first
(build order 2 = YouTube, 4 = FMP):
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/byo-tools-connectors.md`

### Scope (bounded — exactly this)
1. **YouTubeConnector** — BYO Google Data API v3 key: `search(query, ...) -> results` via
   `GET https://www.googleapis.com/youtube/v3/search?part=snippet&q=...&key=...`; account for
   quota units (search = 100 units) and expose remaining daily quota if derivable; parse items
   into structured results. Key held via the chassis, never echoed.
2. **FmpConnector** (Financial Modeling Prep) — BYO key: company profile
   (`/api/v3/profile/{symbol}?apikey=...`) + an earnings-transcript endpoint; paste-a-key; ensure
   the apikey query param is REDACTED in any logged URL.

### Acceptance (must pass for real)
Tests (`httpx.MockTransport`, NO live calls): each connector builds the correct URL with key +
params; a fixture JSON response parses into structured results; the key is never echoed in
logs/errors; YouTube quota-unit accounting is asserted. Reuse the chassis (do NOT fork it). Report
exact pass counts. mypy --strict clean.

### Non-goals
NO OAuth connectors (Reddit/X). NO other vendors (Polygon/Prolific/Third Bridge). NO frontend.
Just the two connectors on the existing chassis.

## When done
`git add -A && git commit -m "feat(connectors): YouTube + FMP paste-a-key connectors"`, then write
`DONE.md`: files, exact test command + real result, honest gaps.
