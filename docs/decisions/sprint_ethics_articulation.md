# Sprint ethics articulation

**Sprint:** SPR-08 (DDIA-execution) · **Date:** 2026-05-24 · **Owner:** substrate
**Anchor:** Philosophy P9 (ethics is a load-bearing trade-off line in sprint headers, not a closing chapter)

## The rule

A spec or sprint document that mentions a §9.0-relevant term (publisher,
consent, Bartz, etc. — see `tools/lint/ethics_trigger_terms.txt`) MUST
include an Ethics articulation block with four named fields:

- Technical risk
- Societal / user risk
- Reputational risk
- Operator decision

Or, if the trigger mention is genuinely incidental, an explicit
"Ethics N/A — _justification_" line.

Enforced by `tools/lint/sprint_ethics_check.py`. Forward-only.

## Why a lint, not a doc

P9 in the philosophy doc is explicit: engineers articulate trade-offs,
business leaders decide. The articulation IS the work; if it's missing
from the sprint header, the trade-off is being made implicitly. The
lint forces it to be explicit at the cheapest moment (spec authoring).

The lint catches PRESENCE, not quality. A copy-pasted "Technical risk:
something" passes the lint. The quality check is operator + peer
review — the lint just ensures the section exists for them to read.

## Forward-only policy

Antiek already has ~30 spec/decision documents that mention §9.0
trigger terms (master-spec, integration docs, prior decisions). Batch-
retrofitting them is rejected:

- It would invite performative compliance — pretty blocks pasted
  without engagement.
- The cost-benefit is wrong: documents that haven't been touched since
  the trigger landed are already absorbed by reviewers; they don't
  need a retroactive ethics block to surface the trade-off.

Instead: the allowlist in `tools/lint/ethics_allowlist.txt` grandfathers
the existing tree. When one of those documents is NEXT edited, the
author retrofits the block as part of that edit. The lint's job is
preventing NEW drift, not auditing history.

Steelman the "retrofit everything" path: it produces a uniform,
mechanically-checkable corpus. We reject because the lint already
gives the operator the surface they need going forward; uniformity
is not worth the performative-compliance risk.

## Rejected alternatives

### A — Doc only, no lint

Kleppmann's framing keeps applying: structural defenses survive agents
+ scale; documentation alone does not. We have empirical evidence
specific to Antiek — `docs/voice_style.md` exists but voice-discipline
violations land in PRs anyway. P9 deserves a lint, not another doc.

### B — Operator-review gate on every spec PR

Tempting but over-broad: most sprint specs DON'T touch §9.0. A
mandatory operator review on every spec PR introduces latency we don't
need. The trigger-term scan keeps the operator's attention on the
sprints that genuinely need it.

### C — Embed the check inside the spec template tooling

Would require generating specs from a tool that enforces the block.
Antiek's spec authoring is varied (HTML via /htmlspec, hand-written
markdown, in-tree edits to existing docs); a templating approach
wouldn't cover all the entry points. The lint covers all entry points
uniformly.

## Quality check vs presence check

The lint stops at presence. Quality is operator + peer review during
PR.

Anti-pattern that passes the lint but fails review:

```
## Ethics articulation

- Technical risk: Could affect users
- Societal / user risk: Some risks possible
- Reputational risk: Could look bad
- Operator decision: TBD
```

The lint passes (four fields present). The reviewer rejects (platitudes).
This is correct: the lint is the floor, the reviewer is the ceiling.
Lowering the floor is cheap; raising the ceiling requires human
judgment.

## What would change this rule

- The trigger-term list grows or shrinks as §9.0's scope evolves
  (e.g., autoresearch outputs become explicitly in-scope per the
  philosophy doc P9 amendment).
- An operator-review process formalizes such that the lint becomes
  redundant. P9's reconsider-if names this case: when a formal review
  process exists with its own enforcement, the lint can retire.
- The lint produces enough false positives that engineers ignore it.
  Today, expected false-positive rate is near zero (the allowlist
  absorbs the existing tree; new docs touching §9.0 should genuinely
  articulate the trade-off).

## Enforcement matrix

| Surface | Enforcement |
|---|---|
| Local dev | Pre-commit hook (when authoring spec/decision docs) — TODO: add to `.pre-commit-config.yaml` once we move beyond Python-only hooks |
| CI | `.github/workflows/ci.yml` — runs `sprint_ethics_check.py` on the full tree |
| Tests | `tests/test_sprint_ethics_check.py::test_real_tree_clean_under_forward_only_policy` |

## References

- `~/specs/antiek-ddia-philosophy/index.html` — P9.
- `docs/templates/sprint_ethics_block.md` — the template engineers copy.
- `tools/lint/sprint_ethics_check.py` — the lint.
- `tools/lint/ethics_trigger_terms.txt` — the trigger-term list.
- `tools/lint/ethics_allowlist.txt` — the forward-only allowlist.
- master-spec §9.0 — the legal gate the trade-off articulates against.
- Kleppmann interview — "doing the right thing" chapter framing.
