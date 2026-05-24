# Integration admission protocol

Hashimoto's vouching pattern, adapted from open-source PRs to external
integrations. Every vendor or external package that crosses Antiek's
boundary occupies a slot on a four-tier ladder. CI enforces.

The registry is `integrations.toml`. The CI gate is
`scripts/check_integration_tiers.py`. The Tier-3 mirror is
`substrate/integrations.py::PROD_VENDORS`.

## The four tiers

| Tier | What it means | Where imports are allowed |
|------|----------------|---------------------------|
| **0** | Spec only — documented but not yet adopted | **Nowhere.** Import = violation. |
| **1** | Local prototype — under evaluation | `tools/`, `scripts/`, `experiments/`, `tests/`, `benchmarks/`, `docs/` only. Never under production layers. |
| **2** | Prod call-site with sunset clock | Only at the file paths listed in the registry's `prod_call_sites`. Defaults to a **90-day sunset** from `vouched_at`; sunset_date in the past is a violation. |
| **3** | Adopted indefinitely | Anywhere. Must also appear in `substrate/integrations.py::PROD_VENDORS`. |

## Promotion path

```
Tier 0 (spec)
   │  operator writes the integration spec doc
   ▼
Tier 1 (local prototype)
   │  operator vouches; imports allowed under prototype zones only
   ▼
Tier 2 (prod call-site)
   │  operator wires the first prod call-site, lists it in prod_call_sites,
   │  picks a sunset_date (default +90 days), commits
   ▼
Tier 3 (adopted)
   │  sunset clock runs out OR operator promotes early;
   │  mirror entry into substrate/integrations.py::PROD_VENDORS
   ▼
(stable; revisit only on operator demotion)
```

## Demotion path

A Tier-3 integration can be demoted to Tier 2 (with a fresh sunset) at
any time. A Tier-2 integration whose `sunset_date` passes without
promotion is treated as a violation by CI — the operator must either
promote, extend the date (with new justification), or remove the
integration entirely.

## Adding a new integration

1. **Write the spec doc** at `docs/integration_<vendor>.md`. Per the
   memory-recorded pattern: REJECTs first, INTEGRATE last, with named
   wedges if applicable.
2. **Append to `integrations.toml`**:
   ```toml
   [your_vendor]
   package = "your_vendor"      # PyPI package name (top-level import)
   tier = 0                     # start at the bottom
   voucher = ""                 # set when promoting to ≥ 1
   vouched_at = "YYYY-MM-DD"
   justification = "..."        # ≤ 300 chars; cite the spec + the wedge
   spec_doc = "docs/integration_your_vendor.md"
   ```
3. **Run** `python scripts/check_integration_tiers.py` locally; expect
   clean exit.
4. **Commit** the spec doc + the registry append in one commit.

## Promoting an integration

1. **Tier 0 → 1:** Add `voucher` (operator handle). No code change yet.
2. **Tier 1 → 2:** Wire the first prod call-site; add its path to
   `prod_call_sites`; add `sunset_date = "<vouched_at + 90 days>"`.
   The 90 days is a discipline, not a deadline — it forces the
   operator to revisit. If the integration delivers, promote to 3
   before the sunset; if not, remove it.
3. **Tier 2 → 3:** Bump `tier` to `3`; remove `sunset_date`; add the
   integration name to `substrate/integrations.py::PROD_VENDORS`.

## Inline exception

A single import that genuinely needs to bypass the gate may carry
an inline `# tier-allow: <reason>` comment. The CI script logs every
override to `tier_overrides.log` (regenerated each run; not committed
to git unless the operator wants to track them).

```python
# Example — operator-justified override:
import vendor_zero  # tier-allow: emergency hotfix, ticketed; revert by 2026-06-15
```

Use sparingly. Each override is a private dispensation visible in CI
logs; the right long-term move is to promote the integration with
a real voucher rather than accumulate overrides.

## Denouncing a vendor

Not yet implemented as a separate mechanic. For now: set `tier = 0`,
update `justification` to name the cause, and add the vendor to
`integrations.toml`'s spec_doc reference. A future enhancement could
add a `denounced = true` field and a separate denounced-vendor list
that CI checks against not only imports but also dependency declarations
in `pyproject.toml`.

## Spec

- Engineering: `~/specs/antiek-hashimoto-engineering/sprint-e3-vouching.html`
- Philosophy: `~/specs/antiek-philosophy/rounds/round-01-hashimoto/sprint-04-vouching.html`
- Hashimoto source: 2026-Q1 podcast interview, "AI makes it trivial to
  create plausible-looking but incorrect and low-quality contributions...
  Before we had default trust; now it's default deny and you must get
  trust by somebody."
