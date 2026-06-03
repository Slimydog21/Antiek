# Werner execution adapter (ANT-EXEC-H2V SPR-07)

**Status:** Active — binds the **Werner** product htmlspec to ANT-H2V gates without re-running AMS-v2.

## Scope

| In scope (SPR-07) | Out of scope (Werner htmlspec SPR-13→16) |
|-------------------|------------------------------------------|
| Operator verify card for mascot/lag claims | Ice-fishing scene implementation |
| Handoff gates before “Werner done” | Full p95 measurement harness in CI |
| Pointer to `docs/htmlspec/werner-ice-fishing-cursor/` | Product feature shipping |

## Before claiming Werner verification

1. Read `docs/agent-execution/HARD_TO_VARY.md` Phase A→E.
2. Run hermetic gates (no provider):

```bash
./scripts/canonical_verify.sh profile
./scripts/canonical_verify.sh agent-gates
```

3. For **live** mascot/lag claims, complete `docs/agent-execution/OPERATOR_VERIFY_CASCADE_DECOMPOSE.md` only when the claim is cascade-specific; for Werner hop/lag theater use the Werner operator card in `docs/htmlspec/werner-ice-fishing-cursor/` when present, else cite `docs/agent-execution/cascade-case-study.md` §5 (`ccb4c66` / `useMouseFollow` parallel).

## Handoff requirements (F5 / T-09)

| Claim type | Required evidence |
|------------|-------------------|
| “Hop fixed” / “lag gone” | Named commit, filespan, **measured** frame budget or operator video timestamp — not memory |
| “CI green” for craft | Named **blocking** job IDs — informational gates are F7 |
| Platform-wide Werner health | Row in `PLATFORM_EXEC_MATRIX.md` or handoff `### Scope Map` |

## Gate table (SPR-07 adapter)

| gate | command | blocks closure? |
|------|---------|-----------------|
| Profile | `./scripts/canonical_verify.sh profile` | Env Card only |
| Agent gates | `./scripts/canonical_verify.sh agent-gates` | yes (hermetic) |
| Handoff | `./scripts/canonical_verify.sh handoff <packet.md>` | yes |
| Werner product | Werner htmlspec SPR-13→16 after Wave 2 | product, not platform |

## Not proved (default footer)

- Live provider / GPU frame pacing on operator hardware
- Full Werner ice-fishing acceptance without Werner sprint HTML execution
- AMS Mountain Shell UI rows (see `docs/ams-v2/verified-interfaces.md`)