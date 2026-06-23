# Grok execution brief — ANT-AUTH-DIAG

**Spec root:** `docs/htmlspec/auth-diagnostic-precision/`  
**Open master:** `open docs/htmlspec/auth-diagnostic-precision/index.html`

## Wave execution order

| Wave | Sprints | Parallel? |
|------|---------|-----------|
| 1 | SPR-01, SPR-02 | Yes (disjoint files; sync on `authDiagnosticCodes.ts` from SPR-01) |
| 2 | SPR-03, SPR-04 | Yes after Wave 1 merged |
| 3 | SPR-05 → SPR-06 | Sequential (05 needs 03; 06 needs 04 probe) |

## Recommended caffenagent /implement pattern

```text
/implement Execute ANT-AUTH-DIAG Wave 1 from docs/htmlspec/auth-diagnostic-precision/
  - SPR-01: docs/diagnostics/auth-failure-mode-matrix.md + authDiagnosticCodes.ts
  - SPR-02: auth.tsx + Login/index.tsx + auth.test.ts
  Gate: pytest not required for W1; vitest + matrix line count
```

```text
/implement Execute ANT-AUTH-DIAG Wave 2 ...
  Gate: pytest tests/test_magic_link_auth.py -k callback; python tools/auth_probe.py
```

```text
/implement Execute ANT-AUTH-DIAG Wave 3 ...
  Gate: playwright --project=login-real; operator SSH for SPR-06 M3 if approved
```

## todo_write template

1. SPR-01 M1 matrix doc  
2. SPR-01 M2 TS union  
3. SPR-02 client taxonomy + tests  
4. SPR-03 callback redirect  
5. SPR-04 auth_probe composed  
6. SPR-05 playwright login-real  
7. SPR-06 middleware split + prod onboarding  

## Subagent personas

| Sprint | Persona | Focus |
|--------|---------|-------|
| SPR-01 | explore + plan | Matrix rows, ops false positives |
| SPR-02 | implementer | Frontend only |
| SPR-03 | implementer + reviewer | Backend redirect security |
| SPR-04 | security-auditor | Probe must not leak secrets |
| SPR-05 | implementer | Playwright hermetic harness |
| SPR-06 | reviewer | Middleware/auth.py consistency |

## Non-negotiables from egghead review

- **Never** document allowlist miss as cause of UI `Failed to fetch`.
- **Never** add `not_allowlisted` response code on `/auth/request`.
- **Always** paste probe/curl output in handoff — no paraphrase.

## Operator gate (SPR-06)

SSH to Hetzner requires explicit approval. Without it, sprint completes through M2 with status **blocked** on M3.