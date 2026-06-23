# ASR P1 write-home — register chokepoint vs `insert_document` default

**Date:** 2026-06-02  
**Branch:** `caffen/SR-04` (substrate reconciliation wave)  
**Status:** Decided — **dual path retained** (not folded)

## Decision

**Keep two complementary write-time homes; do not fold `substrate/graph/ops.py`
third-party `personal_reading` defaulting into `substrate/rights/register.py`.**

| Layer | Home | When it runs | What it guarantees |
|---|---|---|---|
| **Insert backstop** | `insert_document` in `substrate/graph/ops.py` | Every document row creation | Third-party `document_type` with `content_class=None` → `personal_reading` + `document.content_class_defaulted` event (SPR-01 M5). Applies to **all** adapters, including the seven P1b migration-pending ones that never call `register_source_document`. |
| **Rights chokepoint** | `register_source_document` in `substrate/rights/register.py` | After insert, when an adapter (or `register_book`) registers | Vocabulary validation (`VALID_CONTENT_CLASSES`, now including `personal_reading`), escrow rules by `SourceKind`, `ip_holder_id` threading, and **post-write `serve_full_text_guarded` in the same txn** (default `run_self_check=True`). |

## Why not a single home in `register`?

1. **Coverage.** Seven acquisition adapters still insert without registering (closed allowlist in `tools/lint/register_check.py`). Until P1b migrates each one, the only write-time deny-by-default for those paths is the `insert_document` guard. Moving the default into `register` would leave NULL-that-serves for every adapter that has not yet added a register call.

2. **Semantics of `content_class=None` at register.** `register_source_document` resolves omitted `content_class` to `GATED_DEFAULT_CONTENT_CLASS` (`restricted_pending_opt_in`) — correct for books and licensed sources that register explicitly, but **wrong** for third-party web captures that should land in the personal-reading lane. Folding the ops default into register without also teaching register about `document_type` would cause a migrated adapter that `insert`→`register(None)` to **clobber** `personal_reading` with gated — a rights regression.

3. **Layering.** Substrate graph ops own row admission; rights registration owns gate-column mutation on an existing row via `update_document_gate_columns`. The insert guard is admission policy; the registrar is rights establishment + serve-guard self-check. That split matches substrate→acquisition layering (acquisition inserts, then registers).

## What P1 *does* unify

- **Vocabulary:** `VALID_CONTENT_CLASSES` in `substrate/rights/register.py` is the one spelling home; `substrate/books/ingest._VALID_BOOK_CONTENT_CLASSES` aliases it (cannot drift).
- **Books path:** `register_book` delegates its rights core to `register_source_document` (`SourceKind.LICENSED_PUBLISHER`, `run_self_check=False` — behaviour-preserving).
- **Explicit personal_reading:** `PERSONAL_READING_CONTENT_CLASS` is a member of `VALID_CONTENT_CLASSES` so P1b adapters and re-register paths can stamp the lane through the chokepoint without a typo raise, and the txn serve-guard can run on that stamp.

## P1b migration contract

When an adapter migrates off the `register_check` allowlist:

1. Continue relying on `insert_document` for third-party NULL → `personal_reading` **or** pass `content_class=PERSONAL_READING_CONTENT_CLASS` explicitly on insert.
2. Call `register_source_document` with the **same** resolved class (never `None` alone for third-party web/user captures — that would re-stamp gated).
3. Keep `run_self_check=True` unless behaviour-preserving omission is documented (books: `False`).

## Verification

- `python tools/lint/register_check.py` — insert-without-register allowlist unchanged until P1b.
- `python tools/lint/serve_guard_check.py` — no regression.
- `pytest tests/test_register_source.py tests/test_personal_reading_lane.py` — personal_reading in vocabulary + lane invariants.

## Related

- Personal-Reading Lane: `docs/decisions/read-spr-01-servable-corpus-gate.md`
- SR-04 spec: `specs/antiek-substrate-reconciliation/sprint-sr-04-p1-register-reconcile.html`