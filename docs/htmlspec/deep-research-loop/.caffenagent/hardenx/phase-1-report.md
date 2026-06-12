# hardenx₁ — post exec-1 (ANT-DRL)

- **Date:** 2026-06-12
- **Target:** `/Users/slimydog/Desktop/Antiek` @ `bfed09d`
- **Scope:** In-scope DRL (substrate/engine/harness); Exa/web API excluded

## Command

```bash
hardenx --strict .
```

## Verdict

| Field | Value |
|---|---|
| Exit code | 0 |
| hardenx band | **LOW** |
| REAL | **0** |
| ADVISORY | 11 |
| Filtered | 31 |
| Corpus certified | **no** |

## Gate

**PASS** — egghead-2 unblocked.

## Advisory summary (no secret values)

- `.env` API keys in gitignored file (correct handling)
- High-entropy strings in `schema.py`, `synquery/client.py` (verify by eye)
- Manifest-floor CVEs for packages not in resolved `.venv`

## DRL surfaces

No REAL findings on `cascade_routes`, `cascade_session`, `session_evidence_pack`, `deep_research_complete`, CI workflow changes.

## Re-scan trigger

Wave 6 (Exa) or new deps/config in exec-2.