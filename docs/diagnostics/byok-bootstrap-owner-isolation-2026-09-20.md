# Shared provider startup must not spend account keys

## Failure dossier

The startup resolver selected credentials by `pipeline_kind` alone. A credential
stored for any account as `provider:deepseek` could become the shared DeepSeek
provider. `list_credentials` sorts by credential ID, so the selected credential
was not necessarily the newest one, despite the resolver's old comment.

No provider or LLM was contacted to reproduce this. Tests used a temporary
encrypted store and synthetic keys.

1. `bootstrap._maybe_deepseek()` asks `resolve_provider_key` for a shared key.
2. `_lookup_byok_key` selects all matching pipeline records without owner scope.
3. It decrypts the last record and passes it to the shared provider constructor.
4. A personal credential is therefore available to process-wide dispatch.

Inspected signatures on base `f24981db2bde8ce2fb88158fc54460cfd168c294`:

```python
resolve_provider_key(provider_handle: str, env_var: str) -> str | None
_lookup_byok_key(provider_handle: str) -> str | None
load_credential(cred_id: str, *, artifact_path: str | None = None,
                key_bytes: bytes | None = None,
                key_file: str | None = None) -> SecretStr
```

The regression first produced **7 failures and 11 passes**. Six cases admitted
Alice, Bob, or an ownerless key with BYOT-only either enabled or disabled. A
seventh exposed selection of a foreign key from a mixed-owner store.

## Fix and operational contract

Shared startup accepts only credentials with owner `__operator__`, matching
provider pipeline, and authenticated v3 owner binding. Account-owned credentials
must use the existing request-scoped authority gateway. The environment fallback
is preserved when BYOT-only is off, and remains disabled when BYOT-only is on.

Legacy v1/v2 credentials are deliberately excluded because their owner metadata
is not cryptographically authenticated. The current migration tool writes v3
records and its synthetic migration-to-startup regression passes. Re-onboard a
legacy shared key explicitly if shared startup is still required.

PR #3197 adds `--email` migration into a derived personal owner. Such credentials
will intentionally stop qualifying for shared startup under this fix. Do not
restore global access by automatically choosing an allowlisted person's key.
The thought-partner and Write generation consumers still need request-scoped
model authority. Coordinate those consumers before removing all shared keys on
a deployment that still depends on them. This patch does not run a migration.

## Scope map

| Entry point | Evidence | Status |
|---|---|---|
| Shared key resolution | `tests/test_byok_key_source.py` real encrypted multi-owner store, both fallback modes | Tested |
| DeepSeek bootstrap consumer | Same regression calls `_maybe_deepseek` | Tested without network |
| Current env-key migration to shared startup | `test_migrated_operator_key_is_still_available_to_bootstrap` | Tested with synthetic env file |
| Owner metadata tampering and legacy binding | Relabeling and no-decrypt regressions in same test module | Tested |
| Personal Talk-to-Book/research authority | Existing owner suites below | Regression-tested |
| Live account onboarding, production, all AI actions | No live credentials or production changes | Unverified |

## Handoff

### Env Card

| Field | Value |
|---|---|
| Date | 2026-09-20 |
| Repo | `/Users/slimydog/Antiek/.worktrees/byok-bootstrap-owner-isolation-20260920` |
| Branch | `fix/byok-bootstrap-owner-isolation-20260920` |
| Base | `f24981db2bde8ce2fb88158fc54460cfd168c294` |
| Interpreter | `.venv/bin/python`, symlink to canonical platform venv |
| Python | 3.12.13 |
| LLM contacted | GLM independent review only; no Antiek inference |
| Network for tests | None |

### Not proved

Production key migration, live provider requests, account onboarding, and
all-action BYOT are not proved. Concurrent credential migration while startup
is reading the store is outside this patch; the existing migration runbook
requires stopping the API. Shared-key selection preserves credential-ID order,
not a newest-key policy.

### Status

Implementation and local verification complete; independent review pending.

### Files touched

- `substrate/dispatch/providers/byok_key_source.py`
- `tests/test_byok_key_source.py`
- This diagnostic record.

### Milestones

- [x] Reproduce cross-owner startup resolution with real encrypted records.
- [x] Restrict shared startup without changing request-scoped authority.
- [x] Verify current migration, legacy rejection, tampering, and owner consumers.
- [ ] Independent review and draft PR.

### Gate results

Full logs retained under the worktree's `.audit/` directory.

| Command | Result | Log |
|---|---|---|
| `python -m pytest tests/test_byok_key_source.py -q` before fix | 7 failed, 11 passed | `owner-red.log` |
| `python -m pytest tests/test_byok_key_source.py tests/test_dispatch_bootstrap.py tests/tools/test_byot_migrate_env_keys.py tests/byot -q` | 103 passed | `owner-regressions.log` |
| `python -m pytest tests/test_byok_store.py tests/byok/test_store_user_scoping.py tests/test_start_research_owner_dispatch.py tests/test_talk_to_book_owner_byot.py -q` | 36 passed | `owner-authority.log` |
| `python -m ruff check substrate/dispatch/providers/byok_key_source.py tests/test_byok_key_source.py` | Exit 0 | `owner-ruff.log` |
| `python -m mypy --strict --follow-imports=silent substrate/dispatch/providers/byok_key_source.py` | Exit 0 | `owner-mypy.log` |

All Python commands used the interpreter and cwd above. Tests emitted one
existing Starlette/httpx deprecation warning.

### Decisions mid-flight

Require v3 binding as well as owner equality so editing unauthenticated legacy
metadata cannot make a personal key qualify. Preserve the existing fallback
flag instead of introducing another source of routing configuration.

### Assumptions surfaced

`__operator__` here identifies explicitly shared bootstrap credentials, not
the human account selected by a signed-in request. New personal-owner migration
does not imply consent to shared background spending.

### Steelman rejected alternative

Selecting the first allowlisted email's key would keep more legacy actions
working immediately, but would still promote a personal key into shared dispatch
without request authority, payer binding, or the account's operation ledger.

### Open questions

Thought-partner and Write model selection, shared-credential model variants,
and the PR #3197 integration remain required for the full BYOT objective.

### Next sprint can start when

The consumer owner claims are recorded and exact authority/gateway contracts
are mapped. No live credentials are needed to implement those consumers.

### Out-of-scope temptations

No production environment edits, credential migration, model-price changes,
OAuth changes, or unrelated UI redesign.
