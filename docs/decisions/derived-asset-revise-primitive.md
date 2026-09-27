# The §1.11 revise primitive and Write informs (LB-8)

**Date:** 2026-09-27
**Source spec:** `specs/antiek-mothership/cockpit/LB-8-SPEC-2026-09-27.md`
**Contract:** THREAD-CONTRACT rev 8.10 §1.11 ("Store", "Atomicity") and §1.11a
"Write informs (S5)"; the event and the read are rev 8.11 Part D (unsigned).
**Binding record it implements:** `docs/decisions/safe-derived-asset-merge-boundary.md`
**Status:** built on `feat/lb8-write-informs-20260927`; merges only after the
rev 8.11 co-sign for the event and the read.

## Decision

`substrate/derived_assets/repository.py` is the sole writer of derived-asset
revisions. A caller holds `connect_write`, opens one transaction, and calls
`revise()`. In that transaction the primitive checks the caller's base against
the head, checks the parent manifest against its members, inserts the new
revision with the parent's bytes, carries every per-revision child row
forward, records the operation, advances the pointer with
`UPDATE … RETURNING`, and touches `derived_assets.updated_at`. A raise at any
step rolls all of it back. Nothing else inserts a revision, and nothing
updates or deletes one.

`PUT /derived-assets/{asset_id}/blocks/{block_id}/informs` is the first
caller. It replaces one Write block's ordered document list with one revise
whose patch replaces that block's rows; every other block's list is carried.
That makes the P13 lost update impossible on the server: a write to one block
cannot erase another's, and a writer holding a stale revision gets
`409 revision_moved` instead of overwriting.

## Internal choices (no wire change)

| # | Choice | Why |
|---|---|---|
| A1 | `operation_kind = 'revise'`; the label rides in `derived_asset_revisions.metadata_json = {"operation": "informs", "block_ids": [...]}` | The V16 CHECK refuses any other kind, and DuckDB cannot alter a CHECK in place |
| A2 | `review_id` = the operation receipt id (`dop-…`, a row in `derived_asset_operations`); `acknowledgement_version = 'operator_direct.v1'`; bytes, hashes, sanitizer identity and manifest are copied from the parent | The binding record calls `review_id` opaque and requires an operation/receipt. LB-4b's fork has the same no-review gap and adopts the same values |
| A3 | `derived_asset_operations` is the idempotency record, `UNIQUE (owner_user_id, idempotency_key)` | §1.11 "Atomicity" requires the idempotency record in the transaction |
| A4 | Request identity = sha256 of the canonical JSON of `{asset_id, block_id, body}` (sorted keys, no whitespace, UTF-8, no text normalization) | A retry resends the same bytes; another path or body under the same key is a conflict |
| A5 | Only a commit writes the operation row | A refusal writes nothing and never burns a key |
| A6 | Check order: body parse → owner 404 → replay or conflict → block 404 → CAS 409 → 422 | The signed list order. Replay precedes the CAS, or a retry after success would 409 against its own revision |
| A7 | `ordinal` and `index` are 0-based list positions; an over-long list reports `index: 50` | "ordinal is the list order" |
| A8 | `derived_asset_revision_blocks` is the per-revision block inventory | Deliverable HTML carries no block ids and V16 members have no `block_id`, so "the block is in the current revision" needs its own rows |
| A9 | The readability predicate below; the same `detail` for a missing and a foreign-private document | Amendment 1: foreign and missing are opaque |
| A10 | Cite-only anchors: `quote`, `prefix`, `suffix` are dropped unless the document is servable, and kept NFC-normalized when it is | §1.4: the cite-only rule for anchors; `book_anchor_routes.py` is the precedent |
| A11 | 422 `detail` is closed: `too_many_entries`, `duplicate_document`, `document_not_readable`, `anchor_other_document`, `anchor_invalid`, `entry_invalid` | Signed text gives `{index, detail}` only |
| A12 | Informs exist only for `write:<deliverable_id>` assets whose deliverable id is a safe event-storage id; any other asset answers the same 404 | §1.11a is "Write informs"; the event log `write-<deliverable_id>` must be a valid storage id |
| A13 | The compare-and-set is two checks. `check_expected` compares the caller's `expected_revision_id` with the loaded head; the pointer `UPDATE` binds that head's revision, content hash and generation and must return exactly one row | Either alone can be removed and a test goes red (M1 in both halves, M17). Under the single-writer lock the second never fires in production; it refuses a head that moved after it was loaded |
| A14 | `derived_assets.updated_at` is touched with a plain `UPDATE`, without `RETURNING` | DuckDB 1.5.4 plans `UPDATE … RETURNING` on a row other tables reference as a delete and insert and refuses it. The row is known to exist (the pointer references it); this is a timestamp, not a CAS |
| A15 | The manifest check reads the `members` array of a JSON object (the W3 Write manifest), or a bare JSON array (the SPR-00 shape), of `{member_index, projection_id?}`, and requires the member rows in the same count and order. It runs on the parent before a revise and on the new revision after its rows are carried | The binding record: "validate the canonical manifest's member count/order against its materialized member rows" |
| A16 | The §1.11 legacy rule (rev 7) is not built. If the member table gains `member_origin` (the W3 rebuild) and a parent holds a `legacy` member, a revise refuses with `RevisionIntegrityError` | Carrying legacy evidence without the rule would clear the export hold. It fails closed until the rule is built |
| A17 | `validate_commit_boundary` is not used | The informs body is not the commit envelope; the validator refuses it as unknown fields |

### The readability predicate (private to `informs.py`)

One SELECT over `documents(document_id, content_class, owner_user_id)` for
every id in the list. A document is readable when it exists, its
`content_class` is NULL (grandfathered) or in `VALID_CONTENT_CLASSES`, and an
owner-only class (`PERSONAL_ONLY_CONTENT_CLASSES`) belongs to the requester.
An unknown non-NULL class fails closed, `user_authored_private` included until
PA04. Legacy `user_owned` keeps its current behaviour (readable; OPEN until
PA06). A gated class is readable as a reference, because citing a source that
is not servable is allowed. This edits no rights or auth file; A06's planned
document-visibility module (not on main yet) replaces it, and informs become
a row in A06's saved-reference ledger.

## The `CHILD_TABLES` contract (LB-4b, LB-5)

`CHILD_TABLES` lists every table whose rows belong to one revision, in
insertion order: a table that references another child comes after it. On a
revise each is carried forward: its live columns are read from the catalog,
so a column added later is copied without a code change, and every parent row
is copied under the new revision id except the rows the caller's `ChildPatch`
replaces. A `ChildPatch` names the columns it matches on (only those in
`patchable_by`) and the rows it inserts, each of which must itself match.

- A table scoped by the block inventory (`scoped_by`) is carried only for
  blocks the new revision holds, so a block a revise removes loses its
  informs (R-LB8-4).
- A new per-revision table must be registered here, or named with a reason
  as not carried. `tests/test_derived_asset_repository.py` (T26) reads the
  live foreign keys and fails otherwise. `derived_asset_operations` is the
  one named exception: it is one operation's receipt.
- LB-4b's fork and merge and LB-5's span ledger call `revise()` and register
  their tables; they do not write revisions themselves.

## The W3 interface (L1-L5, W3 spec §6)

The W3 Write revision writer is the production caller of this primitive and
does not fork it (W3 spec D-W1). These are additive; informs behave as above.

- **L1, body revise.** `revise(..., body: RevisionBody | None = None)`.
  `None` copies the parent's bytes, hashes and manifest (informs; M20 still
  holds). A `RevisionBody` (`canonical_html`, `manifest_json`,
  `sanitizer_policy`, `sanitizer_version`) writes new bytes, and the pointer's
  content hash follows them. `revision_metadata` adds keys such as `route` to
  the revision's `metadata_json`; it may not set `operation` or `block_ids`.
- **L2, create.** `create_revision(con, *, asset_id, owner_user_id,
  asset_kind, title, body, blocks, members, idempotency_key, request_sha256,
  asset_metadata_json=None, revision_metadata=None, build_answer=None)`
  writes the asset, revision 1 (`create`, no parent), the block inventory,
  the members, the operation receipt (`operation: create`; the revision's
  `review_id`), and the pointer at generation 1, all in the caller's
  transaction. Members are written column for column into the live member
  table, so on main's V16 table only evidence rows fit; `user` and
  `unresolved` rows need the W3 rebuild. LB-8's tests are its only callers.
- **L3, manifest.** A15 above.
- **L4, removed blocks.** `CHILD_TABLES` copies the block inventory first.
  Informs, and members once the member table has a `block_id` column, are
  carried only for blocks the new revision holds; a member whose `block_id`
  is NULL (evidence) is carried. A `ChildPatch` with `match=None` rebuilds a
  whole table, as a body revise does for its inventory and members.
- **L5, transactions.** Callers open the caller's transaction with the
  re-entrant `con.transaction()`, never a bare-`BEGIN` `eventful_transaction`
  nested inside another, and dispatch outbox rows only after commit.
  `revise()` and `create_revision()` refuse to run outside an explicit
  transaction.

## Why the rev 8.11 Part D items exist (R-LB8)

1. **The event (R-LB8-1, D1).** §1.11 "Atomicity" requires a
   `write_event_outbox` row in the revise transaction, and no signed event
   names a revise. `derived_asset.revised {derived_asset_id, revision_id,
   parent_revision_id, operation, block_ids[]}` carries no document ids, so
   no saved reference reaches an event log. It lands on `write-<deliverable_id>`.
   `revise()` and `create_revision()` enqueue it keyed by the operation
   receipt, and the route delivers it after commit. `parent_revision_id` is
   null exactly when `operation` is `create`, and `operation` is one of
   `create | edit | informs` (W3's L6). The log has no investigation
   lifecycle marker, so `GET /investigations` never lists it.
2. **The read (R-LB8-2, D2).** Without a GET, a reload cannot show
   persistence and the only way to learn the current revision is a 409.
3. **Block identity (R-LB8-3, D3).** `block_id` is the stable Write block id.
4. **Carry-forward (R-LB8-4, D4).** Without it a fork or merge would empty
   every list, a second lost update.
5. **No revision yet (R-LB8-5, D5).** A deliverable with no revision answers
   404 to the PUT and the GET. LB-8 writes no revision 1: that belongs to the
   W3 Write revision writer, so in production every Write deliverable answers
   404 until W3 lands. Lane A keeps S5 persistence off until then.

The event and the GET are one separate commit on the branch, so they can be
dropped if the co-sign changes them.

## Reconsider if

- W3 rebuilds the member table: the manifest check (A15) and the legacy rule
  (A16) must follow the new columns.
- A06 ships its document-visibility module: the local predicate is replaced.
- DuckDB lifts the FK-parent `UPDATE … RETURNING` limitation: A14 can check
  the touched row.
