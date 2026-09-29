# Harness lessons ported from the operator's machine

Generated 2026-09-29 19:20 from `/Users/slimydog` against `origin/main`.

These are rules that were paid for in production incidents, not preferences.
Each one names the observed failure, so a reader can judge whether it applies here.

## The rules

1. **Assert payload SHAPE, not a status code** — `data.uspto.gov` returns HTTP 200 with a 20,666-byte application shell instead of data. A bare 200 is not evidence.
2. **Probe the workload, not the preflight** — A local-model `/v1/models` list shows *available* models, not *loaded* ones: `--check` went green while every real request 400'd. The same trap appeared in my own X checker, which read `x env` (exit 0) instead of `x me`.
3. **Never disable TLS verification to work around a failure** — A lane concluded Treasury hosts needed `-k`. The real cause was Anaconda's curl on PATH with its own CA bundle; system curl returned 302 on the same URL. Check which binary ran before blaming the host.
4. **A failover tool's state file can silently disable its best provider** — Exa was flagged exhausted for six weeks; every search skipped it. Read state files; verify with the tool's own accounting (spend moved by exactly $0.007).
5. **Never let an adapter define the primary driver** — Four projects were rejected for wanting to sit above the driver. Define primary by role, not vendor.
6. **A resemblance score is not a precision gate** — Mastra's scorers grade the reply against the *question*, not the truth; adopting them would optimise for parroting the prompt.
7. **Report-only beats auto-fix for estate drift** — A "fix" turned a loud failure into a quiet success once; the audit now never changes anything.
8. **A child that finishes in seconds with no artifact is a dead lane, not a completed task** — Read its transcript before trusting or re-tasking it.
9. **Verify a requester-named tool exists before building against it** — `gws` did not exist on PATH; the answer was to ask, not to substitute.
10. **Skills have two silent frontmatter defects** — (a folded description over 1024 chars, and a colon-space that creates a nested mapping). Neither stops the skill loading; only a live launch reveals them.

## Skills that exist on the machine and not in this repo

- `beads-fleet`
- `estate-audit`
- `grokbot-resource`
- `harness-drift`
- `harness-upstream`
- `media-information`
- `modal-compute`
- `ocr-review-gate`
- `public-data`

## Local extensions worth reviewing

- `beads-prime.ts`
- `estate-report.ts`

## Doctrine deltas to consider by hand

These are NOT applied automatically - doctrine is judgement, not a file copy:

- `CLAUDE.md` here and `~/.prime/agent/APPEND_SYSTEM.md` there overlap. Where a rule
  exists in only one, decide which side owns it rather than copying both ways.
- The Google/Gmail path changed: `gog` is dead, `gws` is current. If this repo
  documents `gog auth login` anywhere, that instruction is stale.
