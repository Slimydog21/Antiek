# Owner-privileged read path — SPR-owner-read (2026-06-04)

**Date:** 2026-06-04  
**Status:** Built + verified (code + tests + CI + invariant)  
**Source branch:** `caffen/owner-read`  
**Predecessor:** PR #43 Personal-Reading Lane (9aeb2c9) — non-owners excluded from
`personal_reading`; owner's own corpus remained inaccessible even to the owner.

## Problem

The §9.0 deny-by-default retrieval gate (PR #72 ancestor, RG-01..RG-06) closes
the `personal_reading` corpus to non-owners — a necessary loss-of-access for
security. But the gate *also* closes an owner's *own* `restricted_pending_opt_in`
(gated pending publisher opt-in) and `personal_reading` corpus to the owner
herself, making the read product incomplete: an authenticated owner cannot
talk-to-book, search, or see what she owns. This sprint restores that access —
the owner can read her own gated/personal corpus via the authenticated read
endpoints (talk-to-book + corpus search) by retrieval with the PRIVILEGED
`operator_only` §9.0 policy tag, while non-owners stay fully gated.

## The Design: Retrieval-time privilege only, fail-closed on multi-operator

The owner-read path wires `ask_book` + `corpus_search` (interfaces/research/api/books.py)
to resolve the policy tag through `_owner_read_policy_tag(request)`, a helper that:

1. **Returns the PRIVILEGED `operator_only` tag ONLY when:**
   - The auth middleware has stamped `request.state.auth_method` with one of the
     four authenticated methods (`antiek_session_cookie`, `cloudflare_access_email`,
     `cloudflare_service_token`, `bearer_token`) — a positive proof the caller
     proved owner identity with a real credential, AND
   - The deployment is single-operator: `operator_allowlist_from_env()` resolves
     ≤ 1 operator email (`ANTIEK_OPERATOR_EMAIL`).

2. **Returns the non-privileged `attribution_eligible` tag for all other cases:**
   - `unauthenticated_local` (enforcement OFF, no auth env set) — deliberately
     excluded per the fail-closed rule: the §9.0 bypass must bind to a real
     credential, never to "auth happened to be disabled."
   - Any multi-operator config (2+ emails) — FAILS CLOSED STRUCTURALLY: the
     helper cannot distinguish which owner (which tenant) is reading, so it
     refuses the bypass entirely. Retrieval applies no `owner_user_id` filter
     (the column exists at `schema.py:81` but `search()` ignores it today), so
     granting both tenants `operator_only` would hand either one read access to
     the *other's* `personal_reading` corpus — a cross-tenant leak.

The SINGLE-OPERATOR ENFORCEMENT (at commit 7c84165) closes the verifier-critic
+ Strix report "owner-read grants cross-tenant access in multi-operator configs"
**structurally**, not just by documentation. A deployment with 2+ operator
emails gets the fail-closed behavior mechanically; no amount of misconfiguration
at the operator level can override it.

## The gate and serve layers: unchanged separation

The **retrieval gate** (`substrate/graph/retrieval_gate.py`) — the SQL deny-by-default
logic that admits a tag — is unchanged. The **serve gate**
(`substrate/books/serve.py`, `serve_full_text_guarded`) — the allowlist that
serves full-text body to the public — is unchanged. Retrieval-bypass ≠
serve-bypass: the owner can retrieve (search, chat) her own gated corpus, but
the public serve path still withholds the full-text body. Test at 77f1c71
proves this: `test_public_serve_path_still_excludes_gated_body_for_owner` —
authenticated owner can `ask_book` her `personal_reading` corpus (retrieval
privilege), but `GET /books/<id>/full-text` still returns `servable=False` and
null body (serve gate untouched).

## Fixes (commits 77f1c71, 883cf68, 58dcedd, 7c84165, merge 49b9a94)

### Commit 77f1c71 — owner-read path + owner-privilege invariant

| Component | Location |
|---|---|
| **Owner-read endpoints + policy-tag resolution** | `interfaces/research/api/books.py:48-121` — `_OWNER_READ_POLICY_TAG`, `_OWNER_AUTH_METHODS`, the `_owner_read_policy_tag(request)` helper (def at `:90`); `ask_book` + `corpus_search` wired to call it (lines `:766`, `:831`). |
| **Owner privilege threaded into retrieval** | `substrate/books/book_qa.py` — `answer_book_question()` gained a `policy_tag: str = "attribution_eligible"` param forwarded straight to `search()`. This is the mechanism by which `ask_book`'s owner privilege actually reaches retrieval; the deny-by-default gate logic itself (`substrate/graph/retrieval_gate.py`) is unchanged. |
| **Owner-privilege-tag invariant** | `substrate/invariants/owner-privilege-tag.toml` — a §9.0 guard (sibling of `owner_boundary_check`, `retrieval_gate_check`) forbidding a PRIVILEGED tag literal reaching retrieval outside the auth-checked allowlist. |
| **Lint scanner + CI wire** | `tools/lint/owner_privilege_check.py` — AST walk flagging `search(...) / answer_book_question(...)` calls with a static-literal privileged tag outside the allowlist; `.github/workflows/ci.yml:197-211` — `Owner-privilege boundary check` step. |
| **Tests: retrieval privilege** | `tests/test_owner_read_path.py` — 14 owner-read path tests: authenticated owner can read own gated/personal corpus (talk-to-book + search); non-owner / unauthenticated / multi-operator configs fail gated. |
| **Tests: lint scanner** | `tests/test_owner_privilege_check.py` — 9 tests exercising the lint: planted privileged literals are caught; resolved tags via helper are clean; the real tree passes. |

### Commit 7c84165 — single-operator enforcement

| Component | Location |
|---|---|
| **SINGLE-OPERATOR GATING LOGIC** | `interfaces/research/api/books.py:119` — `_owner_read_policy_tag` now gates the privilege on `len(operator_allowlist_from_env()) <= 1`; a 2+-email deployment returns the non-privileged tag. |
| **Structural enforcement test** | `tests/test_owner_read_path.py::test_multi_operator_config_fails_closed_to_non_privileged` — single operator ⇒ authenticated owner gets `operator_only`; 2+ operators ⇒ same auth methods return `attribution_eligible`; non-owner unaffected. |

### Commits 883cf68, 58dcedd — sharpen phase (type + lint cleanup)

| Commit | Change |
|---|---|
| **883cf68** | Ruff I001 import-order fix in new test file (pinned ruff 0.15.15, CI's declared-bar gate). |
| **58dcedd** | 7 pre-existing mypy --strict violations shifted by keystone; fixed at source: type casts, ServeResult annotation, ProviderError import. |

## Fail-before evidence

| Sprint | Proof |
|---|---|
| **Retrieval privilege** | Removing `_owner_read_policy_tag` call from `ask_book` / `corpus_search` ⇒ both endpoints stay on `attribution_eligible` ⇒ owner's gated/personal corpus is not found. |
| **Failure on unauthenticated** | Setting `request.state.auth_method = None` ⇒ `_owner_read_policy_tag` returns `attribution_eligible` ⇒ test fails (gate excludes personal_reading). |
| **Failure on multi-operator** | Setting `ANTIEK_OPERATOR_EMAIL=alice@ex.com,bob@ex.com` ⇒ `len(operator_allowlist_from_env()) > 1` ⇒ `_owner_read_policy_tag` returns non-privileged even for authenticated methods ⇒ test fails (owner cannot access gated corpus). |
| **Lint scanner on violation** | `test_lint_catches_a_planted_privileged_literal` plants a non-allowlisted call with `policy_tag="operator_only"` ⇒ lint flags it; `test_lint_is_green_when_tag_resolved_via_helper` same site but via `_owner_read_policy_tag(request)` call ⇒ lint passes. |
| **Serve path regression** | `test_public_serve_path_still_excludes_gated_body_for_owner` — authenticated owner `ask_book` succeeds (retrieval), `GET /full-text` still returns `servable=False` and null body (serve gate untouched). |

## Verification (PR #72, 2026-06-04)

```text
pytest tests/test_owner_read_path.py tests/test_owner_privilege_check.py -v
  14 owner-read + 15 meta-reading + 9 lint tests green

python tools/lint/owner_privilege_check.py
  OK: no privileged policy_tag literal passed to a retrieval callee outside the auth-checked allowlist.

Scoped mypy --strict (files changed + roots):
  interfaces/research/api/books.py ✓
  substrate/books/book_qa.py ✓

Ruff (pinned 0.15.15):
  tests/test_owner_privilege_check.py ✓ (I001 import order)
  Full tree ✓ (declared-bar CI gate)

Full CI subset: pytest tests/ -q -m "not integration" (unchanged from RG-06)
```

Invariant assertion: `substrate/invariants/owner-privilege-tag.toml` wired as CI
step. Non-vacuity: negative-control tests (`test_lint_catches_a_planted_privileged_literal`,
`test_lint_is_green_when_tag_resolved_via_helper`, `test_lint_passes_on_the_current_tree`)
prove the lint catches violations and passes on the real tree.

## SINGLE-OPERATOR DEPENDENCY (CLAUDE.md invariant #5)

This feature is LOCKED to single-operator configs. The privilege-resolution
helper (`_owner_read_policy_tag`) gates on `len(operator_allowlist_from_env()) <= 1`,
so multi-operator deployments FAIL CLOSED mechanically — an authenticated operator
on a 2+-email config gets the non-privileged tag and cannot read gated/personal
corpus. This is structural enforcement, not documentation:

- The helper keys on `auth_method` only, never on `request.state.user_id` or
  `user_email`.
- `search()` applies no `owner_user_id` filter (the column exists, schema.py:81).
- Retrieving with `operator_only` gives `BOTH` operators access to gated content —
  without per-operator scoping, that would leak each tenant's `personal_reading`
  corpus to the other.

**When Sprint-22 multi-user lands:** Restoring multi-operator owner-read requires
a deeper change — scope retrieval by `request.state.user_id` against `owner_user_id`
so each operator sees only their own gated corpus. The `operator_only` tag alone,
as designed today, is insufficient for multi-tenant safety. The helper at
commit 7c84165 bakes this gate in; multi-operator deployments cannot accidentally
sidestep it.

## Out of scope (unchanged)

- Serve path (public allowlist, no policy_tag consultation).
- Chunk retrieval gate (`retrieval_gate.py` SQL logic, RG-01..RG-06).
- Author attribution drop / corpus audit (unaffected by privilege).
- Deploy to prod (operator / PRcrouch).

## Operator follow-on

None at this sprint. The single-operator enforcement (commit 7c84165) ensures
safe defaults; no operator action needed beyond "continue deploying with one
`ANTIEK_OPERATOR_EMAIL`" (today's only mode). When transitioning to multi-operator
or when Sprint-22 lands, see the CLAUDE.md invariant #5 deferral in
`docs/engineering_deferrals.md`.
