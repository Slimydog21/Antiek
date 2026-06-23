# TileRT GLM-5.2 interactive synthesis — measurement verdict

**Status:** Insufficient data (scaffold — ATSB SPR-07)  
**Date:** 2026-06-23  
**Falsifier (operator):** Interactive GLM synthesis verifier pass rate −5pp vs Opus/premium → drop **synthesizer** interactive override only.

## Verdict

**Insufficient data** — no production dogfood batch with `tier=speed` on engaged
synthesizer has been recorded yet. SPR-01 Modal prod gate and live traffic
are prerequisites before any keep / partial-revert / rollback decision.

## Metrics (to fill)

| Metric | GLM (`speed`, brain=glm, interactive) | Premium (`synthesis`) | N investigations |
|--------|----------------------------------------|-------------------------|------------------|
| p50 `latency_ms` (synthesizer) | _TBD_ | _TBD_ | _TBD_ |
| Verifier pass rate | _TBD_ | _TBD_ | _TBD_ |
| $/investigation (dispatch.call sum) | _TBD_ | _TBD_ | _TBD_ |

## Sample investigation ids

_List ≥10 ids or state N too small._

## Decision when data exists

- **Keep** — GLM interactive driving meets falsifier; cost/latency wins documented.
- **Partial revert** — Drop synthesizer from `engagement_policy.interactive` only; keep decomposer/connector on `speed`.
- **Rollback** — Remove interactive `speed` overrides; premium-only driving path.

## How to refresh metrics

```bash
uv run python scripts/tilert_speed_verdict_report.py
```

Copy the generated table into this ADR when `verdict` is not `insufficient_data`.
Verifier pass rate remains manual / follow-up join (milestone 2).

## References

- `docs/decisions/tilert-antiek-placement.md`
- `scripts/tilert_speed_verdict_report.py`
- `/Users/slimydog/specs/antiek-tilert-speed-brain/sprint-07-measurement-falsifiers.html`