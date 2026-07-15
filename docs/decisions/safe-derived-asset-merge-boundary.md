# Safe derived-asset merge: immutable evidence boundary

Status: accepted for SPR-00 implementation

Date: 2026-07-15

Source: safe-derived-asset merge HTMLSpec at home commit `aefa27b`

## Decision

“Merge into the asset” never mutates a book, paper, source document, HTML
projection, or frozen compose snapshot. It creates or advances an
operator-owned derived asset. Each accepted state is an immutable canonical
HTML revision; restore creates another revision rather than rewinding history.

The canonical graph initializer owns four tables:

- `derived_assets`: stable owner, title, and kind.
- `derived_asset_revisions`: exact canonical HTML, hashes, sanitizer
  identity, canonical ordered-member manifest, review/acknowledgement binding,
  operation, and parent/restore lineage.
- `derived_asset_revision_members`: ordered copied provenance bindings for
  the exact source/projection evidence used by one revision.
- `derived_asset_current_revisions`: the sole mutable, generation-bearing
  pointer used by a future transactional compare-and-swap repository.

The pointer is deliberately separate from stable asset identity. Composite
foreign keys bind parent revisions, restored-from revisions, member manifests,
and current pointers to the same asset. Cross-asset lineage is invalid at the
database boundary, not merely discouraged in application code.

## Closed contracts

Revision operations are exactly `create`, `revise`, and `restore`:

- `create` has no parent or restore source.
- `revise` has a parent and no restore source.
- `restore` has both the current parent and the selected prior revision.

All SHA-256 values are lowercase hexadecimal. DuckDB checks that the content
hash and UTF-8 byte count match `canonical_html`, and that the manifest hash
matches `manifest_json`. A revision persists its
`canonical_html`, UTF-8 byte count, content and manifest hashes,
`sanitizer_policy`/`sanitizer_version`, opaque `review_id`, and fixed
acknowledgement-text version. Future SPR-01/02 code must recompute and compare
these values; hashes are integrity, never authorization.

## Evidence inputs are copied bindings

Member rows may name `projection_id`, `source_asset_id`,
`source_document_id`, source hash, hosted-HTML hash, and investigation ID.
They intentionally have no foreign key or write path to evidence tables.
Changing or deleting evidence is outside this subsystem; later commits must
re-load and verify the immutable bindings before mutation.

The rejected source-merge contract remains untrusted. The pure
`substrate/write/derived_asset_boundary.py` validator rejects unknown fields
before database or filesystem access and carries the stable HTTP-422 mapping
for its future route adapter. Browser-supplied
`draft_merge_path`, `compose_index_path`, owner/reviewer/commit authority,
and `acknowledge_body_rewrite` are not compatibility fields. No code in this
lane imports, migrates, or blesses legacy source-merge rows.

## Mutation ownership

SPR-00 installs schema and a pure compatibility-refusal boundary only. An
accepted current revision is protected from update/delete by DuckDB's
composite foreign-key relationship from the current pointer; historical
revisions remain protected by their descendants' parent/restore relationships.
SPR-02 must make revision insertion plus pointer installation one transaction,
so no committed unsealed revision can exist, and provide the sole repository
that:

1. opens the existing DuckDB write lock;
2. inserts revision, members, operation/receipt, and outbox in one transaction;
3. advances `derived_asset_current_revisions` with expected asset, revision,
   content hash, and generation using `UPDATE … RETURNING` (DuckDB
   `rowcount` is not a CAS signal);
4. exposes no generic revision update/delete API.

Routes never create tables. Source rows, projection rows, and filesystem
compose artifacts have no write method in this subsystem.

Known handoff gap: DuckDB has no trigger/permission primitive that can make an
unreferenced row physically append-only. The accepted-state invariant depends
on SPR-02 inserting a revision and its protecting current/parent references in
one transaction; no commit may expose an unsealed revision. SPR-01 may build
read-only drafts/reviews, but SPR-02 cannot be accepted without fault-injection
proof of that transaction. The repository must also validate the canonical
manifest's member count/order against its materialized member rows and maintain
`derived_assets.updated_at`.

## Verification and stop conditions

Focused schema tests prove fresh/reopen initialization, lowercase hash and
operation constraints, operation-shape requirements, ordered member identity,
one pointer per asset, CAS fields, and rejection of cross-asset parent,
restore, member, and pointer bindings. Static red proofs reject source-table,
projection-table, filesystem, and legacy source-merge write reachability in
the claimed runtime file.

Stop SPR-01 if authenticated operator scope, canonical sanitizer identity, or
server-owned projection loading cannot be grounded. Never revive source-body
mutation as a fallback.
