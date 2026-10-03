# W3 Write revision writer: executable spec

Date: 2026-09-27. This spec was written read-only. I modified no file and opened no PR.

## 0. Provenance and what binds

**Code base.** `origin/main` is `b41f4ec9b95f90c97576674405ba3656766d65c4`, confirmed after `git fetch`.

**Signed rules.** The signed text is `/Users/slimydog/Antiek/specs/antiek-mothership/THREAD-CONTRACT.md` (TC). Its sha256 is `2395975c…090821d9`, which is rev 8.10, signed by both lanes.

**Unsigned rules.** `/Users/slimydog/Antiek/specs/antiek-mothership/THREAD-CONTRACT-REV8.11-NOTE-DRAFT.md` Part D (D1–D5, lines 195-228) is still marked "_pending_" at lines 242-246. D1–D5 therefore do not bind yet, and anything below that rests on them is marked (8.11).

**LB-8 code does not exist yet.**
- A local branch `feat/lb8-write-informs-20260927` now exists, but it points at `b41f4ec9b` with no commits.
- Its worktree `/Users/slimydog/Antiek/platform/.claude/worktrees/agent-a29fe416f72521b49` has no `substrate/derived_assets/` and no `derived_asset_routes.py`.
- So `create_revision` and `revise` are known only from `/Users/slimydog/Antiek/specs/antiek-mothership/cockpit/LB-8-SPEC-2026-09-27.md:164-201` (INFERRED from the spec). That means now is the moment to agree the interface in §6.

**What I re-read myself and what I took from the reports.** Any citation not tagged "(report)" or INFERRED I read at the stated ref. Partway through, the harness began refusing Bash in this worktree, so the last reads went through file reads of the lb2 working tree (HEAD `ee6867a11`).

---

## 1. The five decisions

### D-W1. W3 calls LB-8's primitive and does not fork it

- Every row W3 writes to `derived_assets`, `derived_asset_revisions`, members, revision_blocks, operations, the CAS pointer and the outbox goes through `substrate/derived_assets/repository.py`:
  - `create_revision()` for revision 1;
  - `revise()` for every later body change.
- W3's own modules contain no `INSERT`/`UPDATE`/`DELETE` on `derived_asset*` tables. A structural test enforces this (T3.S).
- Neither closed prior-art branch is revived: `goal/safe-derived-asset-merge-spr02` `80288d326` has a second create/revise writer with its own operations and outbox tables (report).
- LB-8's `revise()` as specified copies `canonical_html` from the parent. Its A2 says so (LB-8-SPEC:125), and its mutant M20 kills any re-render (LB-8-SPEC:417). A body edit needs new bytes. So W3 needs `revise(..., body=None)`: `None` keeps LB-8's copy, and a supplied `RevisionBody` means a body revise.
  - The preferred route is for LB-8 to ship that parameter before it merges.
  - Failing that, W3-3 adds it inside `repository.py`. That extends the primitive; it does not fork it.
  - The other items W3 needs from LB-8 are in §6.

### D-W2. When revision 1 is created

**Signed basis.**
- TC:577: "The first operation on a deliverable writes revision 1 (`operation: create`): its current canonical HTML as bytes, its blocks mapped to evidence members as below, and the current pointer set."
- TC:1496: "The first operation on a deliverable writes revision 1 from its current content (§1.11). … so the first fork always has an original to return to."

**The rule.**
1. **Eager, on the Write creation routes.** For a new deliverable, its creation is the first operation on it.
   - `POST /deliverables` (`origin/main:interfaces/research/api/app.py:3548-3577`), `POST /write/context/promote` (`write_routes.py:408-427`) and `POST /write/deliverables/from-investigation` (`write_routes.py:590-645`) each write revision 1 in the creation transaction.
   - Revision 1 holds the created body: empty, or the seeded blocks.
   - It is one `create`, not create plus revise, because nothing existed before.
2. **Lazy, for everything else.** This covers deliverables made before W3, and those made by the unmigrated Speak creators:
   - `POST /speak/biography` (`speak_routes.py:373-394` → `biography_composition.py:128-133`);
   - `POST /speak/projects/{id}/draft` (`speak_routes.py:844-850` → `biography.py:119-123`, which always makes a new deliverable).

   The first W3-migrated body operation writes revision 1 from the **pre-operation** state, then the operation's own `revise` (parent = revision 1). Both happen in one transaction.
3. **A refused operation writes neither revision.** This is required, not optional. Writing revision 1 in its own transaction before an operation that then 400s or 404s would write on a refusal.
4. **No backfill in W3.**
   - A bulk backfill is not "an operation on a deliverable" (TC:577).
   - It has no request subject.
   - It would stamp an acknowledgement nobody gave.
   - Consequence: an untouched pre-W3 deliverable keeps D5's honest 404 on the informs PUT and GET (8.11 note:219-222) until its first edit.
   - A backfill can come later behind co-sign W3-C1b.
5. **If 8.11 is signed without D5:** W3 exports `ensure_head()` (§3). LB-8's PUT can call it after its owner check, one line, instead of answering 404.

**Consequence for Part 2 copy.** Once every edit is a `revise` (TC:645), the first operation is almost never a merge. Revision 1 is then "as created" or "as it was before the first edit", so the lane-A label "Revision 1, as it was before the first merge" (TC:1496) becomes wrong. See co-sign W3-C10.

### D-W3. The member rebuild, kept minimal

**What the schema carries.** V24 is the full signed shape (TC:583-606); see PR W3-1.

**What the writer emits.** W3 v1 writes only `user` and `unresolved` members, one per block, all with `member_origin: recorded`. It writes no `evidence`, `generated`, `unsupported`, bite or member_bites rows. Reasons:
- **No evidence.** An evidence member needs a ready html_projection pin (TC:597). `html_projections` is created only lazily by `ProjectionStore.ensure_tables` (`origin/main:substrate/reading/projection/store.py:38-45`) and has no production writer (report). No signed rule picks one projection among several for a document.
- **No generated, unsupported or bites.** These need LB-5's bites (TC:600-601).

**Mapping.** For a block of each kind, W3 records this member (the full table is in PR W3-2):

| Block | Member |
|---|---|
| Graph node that no longer exists | `unresolved/source_missing` |
| Graph node whose **own** metadata chunk names a document | `unresolved/projection_missing`, with `source_document_id` set |
| Graph node with no document found that way | `unresolved/no_provenance` |
| Operator-typed `user_authored` block or operator note | `user` |
| Migrated placeholder, `synthesized` or `brainstorm` block | `unresolved/no_provenance` |
| Section prose that was ever generated (`prose_provenance IS NOT NULL`) | `unresolved/no_provenance` |
| Section prose that was never generated | `user` |

- The "own metadata chunk" rule matters because main's resolver takes any edge in either direction, which can name a document the node only contradicts (`provenance.py:128-154`). W3 never uses that guess (TC:599: "never a guess").
- **Attribution.** `investigation_id` is null ("no thread recorded", TC:580) unless W3-4 recorded it at placement. It is never `__operator__` and never `deliverables.investigation_root_id`.
- **Carry-forward.** Every W3 body revise replaces the whole member set and block inventory with a fresh snapshot. LB-8's informs revise copies them verbatim. The copier needs no per-block evidence logic, because W3 writes no evidence.
- The block↔evidence join that the members report proposed is deferred to whichever package first writes evidence members (see co-sign W3-C5).

### D-W4. Legacy Write mutation routes: migrate them now

**Recommendation.** Migrate now; keeping them with the drift recorded would break informs, fork and merge, as follows.

**What goes wrong if the legacy routes keep writing without revisions** (the "keep" option):
- **Informs (LB-8):**
  - A block placed after the head is missing from the inventory, so PUT and GET answer 404 (LB-8 T20, LB-8-SPEC:384).
  - A deleted block stays in the inventory, so informs can be assigned to a block the editor no longer shows. The next revise that does change blocks then drops them silently under D4 ("A block that a revise removes loses its informs").
- **Fork (TC:802-819):**
  - `base_revision_id`'s block text is stale compared with the editor, so the sentence carry-forward (TC:810-812) compares against the wrong text.
  - Blocks the operator sees are not forkable.
  - A committed fork diverges from `outline_blocks`, so the editor never shows it. That breaks TC:574 ("There is no second path to a Write document body").
- **Merge (TC:648-670):** hunks are diffed against a stale base, and the accepted revision is invisible to the editor.

**Therefore:**
- LB-4b's fork and merge must not ship before W3-3.
- W3-3 migrates every route that changes the canonical body (defined in §2):
  - `POST /write/blocks`, `…/move` and `DELETE /write/blocks/{id}` (`write_routes.py:209-240`);
  - `POST /write/brainstorm/emit-blocks` (`:379-400`);
  - `POST /write/sections/{id}/generate`, its persist step (`:528-537`);
  - `PATCH /sections/{id}/prose` (`app.py:3876-3989`);
  - `POST /sections` (`app.py:3671-3704`);
  - the three creation routes.
- **Not migrated:** `POST /sections/attach-block` and `POST /sections/reorder-block` (`app.py:3706-3733`, `:3780+`).
  - They write legacy `section_blocks`, which `outline_blocks` supersedes (`substrate/write/outline_block.py:16-17`, report). They are outside the canonical body (W3-C4), so they cause no revision drift.
  - They do cause export drift: today's artifact and export read `section_blocks` plus prose (`deliverable_artifact.py:76-87`), and revisions do not. CreationStudio is still live at `/create` (`origin/main:apps/reading/src/App.tsx:175-176`).
  - That drift is recorded for the serve-gate/export package.

### D-W5. Owner stamping

**Grounding (this corrects the premise that sessions stamp a user id other than `__operator__`).** On `origin/main` every authenticated path stamps `__operator__`:
- Every session cookie is minted with `user_id="__operator__"`: `interfaces/research/api/auth.py:530-533`, plus `:633`, `:689` and `:768`.
- The bearer and service-token paths stamp `operator_claims().user_id` (`app.py:1824-1837,1882,1893`), which is `"__operator__"` (`substrate/multi_user/auth.py:72-78`).
- Local unauthenticated mode stamps the same (`app.py:1766-1770`).
- The A20 commit `b8bd3336947c0163f0a6d4849aca2291ed5c58ab` changes no `user_id` stamping: a grep of its +/- lines for `user_id` and `__operator__` found nothing.

So on main there is no skew between the subject and the `deliverables.owner_user_id` default (`ops.py:642`). LB-8's risk 4 (LB-8-SPEC:425) is a future hazard (G7, or a per-user identity), not a current one.

**Rules. They keep W3-made assets correct under any future subject.**
- **O1.** `derived_assets.owner_user_id` is always the deliverable's stored `owner_user_id`, for the eager and the lazy paths alike. An asset never has a second owner.
- **O2.** Every migrated creation route stamps `deliverables.owner_user_id` from the verified subject, in the same transaction as revision 1. `POST /deliverables` gains `request: Request` and passes `owner_user_id=subject`; today it omits the owner (`app.py:3557-3562`).
  - The subject helper is LB-8's: `_reader_owner_id` (`origin/main:interfaces/research/api/books.py:140-149`).
  - `promote` and `from-investigation` keep `_authenticated_owner_user_id` (`write_routes.py:71-88`). They are owned by the LB-15a lanes, and both helpers yield `request.state.user_id` when authenticated.
- **O3.** Every migrated route admits a request only when the subject equals `deliverables.owner_user_id`. Otherwise it returns that route's existing missing-entity 404, byte-identical, and writes nothing. No 403 (8.11 note:228; TC:806,856).
  - This is required because a revise on an asset is an owner-scoped write (TC:1183). Without it, a future subject could revise another owner's asset.
- **O4.** A test asserts that `derived_assets.owner_user_id` equals `deliverables.owner_user_id` for every `write:` asset.
- **Consequence (recorded, out of scope):** under a future non-`__operator__` subject, legacy `__operator__` rows 404 on every Write mutation, and on derived assets. That needs a G7 re-key migration.

---

## 2. Canonical body, snapshot, members and manifest (shared by all PRs)

**The canonical Write body (W3-C4).** It is the deliverable title, section headings, section prose (`deliverable_sections.prose_text`) and `outline_blocks`, in `build_outline_tree` order:
- sections: `ORDER BY section_index, section_id`, pre-order (`origin/main:substrate/write/outline.py:65-110`);
- blocks: `ORDER BY block_index, outline_block_id` (`outline_block.py:575-583`).

**Block identity (D3 and W3-C3).**
- An outline block's id is `outline_blocks.outline_block_id`.
- A section's prose is one block with id `sprose:<section_id>`, present only when the prose is non-empty.
- Headings and the title are structural text. They are not blocks, and carry no member and no informs.

**Why W3 needs its own renderer.** Main's only deliverable HTML path is unfit:
- it reads `section_blocks`, never `outline_blocks` (`deliverable_artifact.py:76-87`);
- it drops unresolvable refs (`:107-108`);
- it opens its own read connections (`:67,95`);
- it orders sections by `section_index` alone (`:78`);
- it bakes cite-only rights into the bytes at render time (`services/html_projection/adapters/deliverable.py:101-102`);
- it emits no block ids (`:33-45`).

W3 stores the owner's pre-gate bytes. The live gate applies at serve time (TC:636-644). This adds no exposure: the same text already sits in `nodes`, `outline_blocks` and `deliverable_sections`.

**Canonical HTML grammar** (sanitizer_policy `antiek-write-revision-escape`, sanitizer_version `1`):

```
article := '<article data-antiek-write="1" data-deliverable-id="'E(did)'">' LF '<h1>'E(title)'</h1>' LF section* '</article>' LF
section := '<section data-section-id="'E(sid)'" data-depth="'d'">' LF '<h'h'>'E(title or "")'</h'h'>' LF [prose] block* '</section>' LF   ; h=min(2+d,6)
prose   := '<div data-block-id="sprose:'E(sid)'" data-block-role="prose">' ('<p>'E(p)'</p>')+ '</div>' LF   ; p = paragraphs of NFC(prose) split on \n[ \t]*\n, stripped, empties dropped
block   := '<div data-block-id="'E(obid)'" data-block-kind="'k'" data-provenance-kind="'pk'">' ['<p>'E(text)'</p>'] '</div>' LF
```

- `E` is `html.escape(s, quote=True)`.
- A block's text:
  - a `graph_node` block uses `NFC(nodes.canonical_label)`, and renders empty when the node is dangling;
  - any other block uses `NFC(outline_blocks.content)`.
- Prose comes first in its section, matching today's artifact (`deliverable_artifact.py:100-105`).
- An allowlist verifier (`html.parser`) re-parses the output. It allows only these tags: `article`, `h1`–`h6`, `section`, `div`, `p`. It allows only the listed `data-*` attributes. It requires the `data-block-id` sequence to equal the inventory.
- Any change to this grammar is a new sanitizer_version. Stored revisions keep their stamp.
- This grounds the "canonical sanitizer identity" stop condition in `origin/main:docs/decisions/safe-derived-asset-merge-boundary.md:102-103` (W3-C9).

**Members.** Each block in the inventory contributes one row, in block order. `member_index` runs 0..n-1.
- `member_key` is the lowercase-hex sha256 of `json.dumps([source_kind, block_id], ensure_ascii=False, separators=(",",":"))` as UTF-8 (TC:592).
- The classification rules are in PR W3-2's table.

**Manifest.**
- It is the canonical JSON (sorted keys, `(",",":")`, `ensure_ascii=False`, UTF-8) of:
  - `{"schema":"antiek.write_revision.v1","deliverable_id":…,"blocks":[{block_id,section_id,role,block_kind,provenance_kind,text_sha256}],"members":[{member_index,member_key,source_kind,block_id,unresolved_reason,source_document_id,investigation_id}]}`
- `text_sha256` is the sha256 of the block's NFC text. That gives LB-4b and LB-5 per-block text identity without changing LB-8's `revision_blocks`.
- `manifest_sha256` must equal DuckDB's `sha256(manifest_json)` (`schema.py:1282-1287`).

**Fixed stored values** (internal; recorded in a decision record):

| Field | Value |
|---|---|
| `asset_kind` | `'document'` (the CHECK at `schema.py:1249-1251` has no Write value) |
| `derived_assets.title` | `deliverables.title` |
| `derived_assets.metadata_json` | `{"source":"write","deliverable_id","deliverable_kind"}` |
| `review_id` | the `dop-` receipt id (LB-8 A2) |
| `acknowledgement_version` | `'operator_direct.v1'` (LB-8 A2) |

- Revision `metadata_json`:
  - on create: `{"operation":"create","route":<label>,"pre_state":bool}`;
  - on an edit: `{"operation":"edit","route":<label>,"block_ids":[…]}`.
- "The current pointer set" (TC:577) is read as the CAS pointer row, inserted at generation 1 (W3-C8).

---

## 3. Transaction shape (TC:646)

```python
with connect_write(db, purpose=...) as con:
    with write_body_operation(con, subject=subject, locate=SectionRef(req.section_id), route="write.place_block") as op:
        # inside ONE con.transaction(): owner check -> ensure_head (lazy rev 1 from pre-state) -> legacy mutation
        obid = place_block(con, ...)          # now transaction-agnostic
        op.touched(obid)
        # on exit (still inside the txn): snapshot post-state -> repository.revise(body=snapshot, patches={revision_blocks, members}) -> outbox
    op.dispatch_after_commit()                # write-<did> plus the legacy mutators' logs; never inside the txn
```

**A hazard found in this pass (confirmed by reading; not executed).**
- On main, the mutators open a bare `BEGIN` (`origin/main:substrate/write/event_outbox.py:34-47`). So they cannot run inside a caller's transaction (INFERRED: DuckDB refuses a nested BEGIN).
- #3536 (`5a7fc533c`) makes `eventful_transaction` and `dispatch_pending`'s receipt re-entrant through `con.transaction()`. Its promotion then calls `place_block` inside `with con.transaction():` (`5a7fc533c:substrate/write/promote_context.py:320-357`).
- `place_block` then calls `dispatch_pending_best_effort` after its inner block, which is still inside the caller's transaction (`origin/main:substrate/write/outline_block.py:367-368`). That dispatch:
  - reads the uncommitted pending row;
  - appends it to `<investigation>.jsonl` (`event_outbox.py:218-251`);
  - marks it delivered inside the outer transaction.
- If a later block or the receipt insert fails, the outer transaction rolls back, but the JSONL line survives: a durable event for a block that never existed.
- W3-0 closes this. Dispatch inside an open explicit transaction becomes a no-op, pending rows stay pending, and the transaction owner dispatches after commit.

---

## 4. PR plan

**Order.** W3-0 has no dependency and can go now. LB-8 merges next. Then W3-1 and W3-2 in parallel, then W3-3, then W3-4.

W3-3 is deploy-atomic: it may be reviewed as two commits, but it ships as one. A partial migration recreates the drift in D-W4.

### PR W3-0: event outbox transaction safety (prerequisite; small)

**Problem.** See §3: bare `BEGIN` at `event_outbox.py:41`; dispatch-in-transaction at `outline_block.py:289-291,367-368`; the #3536 re-entrant change at `5a7fc533c:substrate/write/event_outbox.py` (diff hunks at 38-46 and 251-262).

**Design.**
1. `eventful_transaction` uses `con.transaction()`. It is re-entrant (`origin/main:runtime/db_lock.py:642-669`). This is the same hunk as #3536; whichever lands second rebases.
2. `dispatch_pending_best_effort` returns `[]` when the connection is inside an explicit transaction.
3. `dispatch_pending` raises `EventOutboxError("dispatch inside an open transaction")` in the same case.

**Files.**
- EDIT `runtime/db_lock.py`: a read-only property `in_explicit_transaction` over `_in_explicit_transaction` (`:635-639`).
- EDIT `substrate/write/event_outbox.py`.
- NEW `tests/test_event_outbox_nested_transaction.py`.

**Wire.** None.

**Tests (red on main):**

| ID | Assertion | Expected on main |
|---|---|---|
| T0.1 | `with con.transaction(): place_block(...); raise` leaves no outbox row, no JSONL line, no `outline_blocks` row | `place_block` raises a transaction error from the nested `BEGIN` (INFERRED text). On #3536's head, the JSONL line persists after rollback (INFERRED, not executed) |
| T0.2 | `with con.transaction(): enqueue_event(...); dispatch_pending_best_effort(...)` returns `[]` with the JSONL empty; after commit, a dispatch delivers exactly 1 | the JSONL line is written, then the nested `BEGIN` raises and is swallowed |
| T0.3 | `dispatch_pending` inside a transaction raises `EventOutboxError` | fails (no such refusal) |

**Mutants.**
- M0.1: drop the in-transaction guard. T0.1 (on the #3536 shape) and T0.2 go red.
- M0.2: keep the bare `BEGIN`. T0.1 goes red.

**Risks.**
- The same file carries #3536 (GLM claim `glm53-deliverable-promote-owner-idempotency-20260927`) and the Codex claim `codex-lb15a-promote-owner-idempotency-20260927`.
- The guard should be folded into #3536 before it merges, because #3536 has the hazard today.

**Dependencies.** None.

### PR W3-1: V24 member-table rebuild (TC:583-606, §1.16 "the member-table rebuild in W3")

**Problem.** On main every source column is NOT NULL, and there is `UNIQUE(asset, rev, projection_id)`. There are no kind, origin, use, block, reason or key columns (`origin/main:substrate/graph/schema.py:1326-1343`). So `user` and `unresolved` rows cannot be stored. (TC's citation `1320-1337` has drifted.)

**Design.**
- NEW constant `ANTIEK_GRAPH_SCHEMA_V24_DERIVED_ASSET_MEMBERS_SQL` holding the new table shape:
  - kept: `derived_asset_id`, `revision_id`, `member_index>=0`, the PK and both FKs;
  - `source_kind` NOT NULL, with CHECK over the 5 kinds;
  - `member_origin` NOT NULL, with CHECK over the 3 origins;
  - `"use"` quoted (INFERRED whether needed), CHECK quote|cite;
  - `block_id` (1..256);
  - `unresolved_reason`, with CHECK over the 4 reasons;
  - the 5 source columns nullable, keeping the 64-hex CHECKs when set;
  - `investigation_id`;
  - `member_key` NOT NULL, 64-hex;
  - `UNIQUE(derived_asset_id, revision_id, member_key)`;
  - one CHECK per kind, exactly TC:597-601;
  - an internal extra CHECK: `member_origin IN ('legacy','attested') ⇒ source_kind='evidence'`. This follows TC:604 and :632.
- The same constant adds the attribution side table used by W3-4, in the same single bump: `outline_block_attribution(outline_block_id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL, parent_event_id TEXT, recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)`. It has no FK to `outline_blocks`, following the copied-binding pattern.
- `_rebuild_v24_members(con)`:
  - It returns if `member_key` is already a column (idempotent).
  - Otherwise, inside `con.transaction()`, it:
    1. selects every old row into Python (TC:603 expects none in production; the count is logged);
    2. drops the old table;
    3. creates the new one;
    4. re-inserts each old row with `source_kind='evidence'`, `"use"='quote'`, `member_origin='legacy'`, and `member_key=sha256(json.dumps(["evidence","quote",projection_id,investigation_id],…))`.
  - It never uses `RENAME`, whose DuckDB behaviour with FK tables is INFERRED.
  - It never touches `manifest_json` (TC:606).
- **Wiring:**
  - `init_database` runs the rebuild after V16 and after LB-8's V23 (`schema.py:2362`, after `:2459`).
  - `_v24_members_shape_is_valid` joins the warm probe's `present` conjunction (`:2556-2565`). Otherwise an existing database never rebuilds, because of the fast path (`:2468,2512`).
  - V16 stays byte-identical, because `tests/test_derived_asset_evidence_boundary.py:24-37` pins it.
- **Members copier in `repository.py` (edits the LB-8 entry, not a fork):**
  - It copies column-agnostically (`INSERT … SELECT * REPLACE (? AS revision_id)`; INFERRED DuckDB support, test-covered).
  - A revise that patches `revision_blocks` must also patch `members`; otherwise `RevisionIntegrityError`.
  - A revise of a `write:` asset whose parent holds any `legacy` member raises `RevisionIntegrityError` and writes nothing (W3-C6). This is unreachable in production, since no `write:` revision can predate the rebuild.

**Files.**
- EDIT `substrate/graph/schema.py`: V24 constant, rebuild function, init call, warm probe. `SCHEMA_TABLES` (`:375`) gains `outline_block_attribution`.
- EDIT `substrate/derived_assets/repository.py`: the members copier entry.
- EDIT `tests/test_derived_asset_schema.py`: the positional 9-value inserts at `:279-296` become named columns, and the projection-uniqueness test becomes a member-key test.
- NEW `tests/test_derived_asset_members_v24.py`.

**Wire.** None.

**Tests (red on main):**

| ID | Assertion | Expected on main |
|---|---|---|
| T1.1 | shape: new columns exist and source columns are nullable | assertion fails, columns absent |
| T1.2 | CHECK matrix: `user` with a source column; `unresolved` without a reason; `evidence` without `hosted_html_sha256`; `generated` with `use`; `legacy` + `user` → each ConstraintException. Valid rows of each kind insert | the valid `user` insert raises BinderException (paired with M1.2) |
| T1.3 | quote and cite of one projection coexist; the same `member_key` twice is refused | the second projection insert raises ConstraintException |
| T1.4 | lossless copy: a DB with V16 plus 2 evidence rows gets `evidence/quote/legacy`; the key equals sha256 of the literal JSON bytes; manifest bytes are unchanged | no rebuild, fails |
| T1.5 | re-init is idempotent (row count stable); a pre-V24 DB with `_INITIALIZED_PATHS` empty rebuilds through the warm probe | fails |
| T1.6 | copier: an informs revise copies members verbatim; blocks patched without members raises; a `write:` legacy parent raises and writes nothing | `ModuleNotFoundError` until LB-8 exists |

**Mutants.**

| Mutant | Killed by |
|---|---|
| M1.1 keep `UNIQUE(projection_id)` | T1.3 |
| M1.2 drop the `user` CHECK | T1.2 |
| M1.3 copy as `recorded` | T1.4 |
| M1.4 key with default `json.dumps` separators | T1.4 |
| M1.5 no shape detection | T1.5 |
| M1.6 no warm-probe predicate | T1.5 |
| M1.7 copier drops the `legacy` guard | T1.6 |

**Risks.**
- DuckDB transactional DROP/CREATE of an FK child table is INFERRED; T1.4 and T1.5 run on real DuckDB.
- `schema.py` collides with LB-8's V23 hunks and with stale #3056.
- LB-5's future `member_bites` FK to `member_key` must be created after V24.

**Dependencies.** LB-8 merged (V23 and `CHILD_TABLES`).

### PR W3-2: pure snapshot, the renderer and the classifier (no writes)

**Problem.** There is no canonical renderer over `outline_blocks` (see §2's list of what main's path does wrong). The member inputs are two resolvers that disagree:
- `provenance.py:128-154` takes any edge and uses `chunk_ids[0]`;
- `resolvers/substrate_refs.py:47-63` uses `LIMIT 1` with no ORDER BY (report).

**Design.** NEW `substrate/write/revision_snapshot.py`, SELECT-only on the caller's `con`:

```python
WRITE_SANITIZER_POLICY = "antiek-write-revision-escape"; WRITE_SANITIZER_VERSION = "1"
@dataclass(frozen=True) class SnapshotBlock: block_id: str; section_id: str; role: Literal["prose","outline"]; block_kind: str|None; provenance_kind: str|None; text: str
@dataclass(frozen=True) class MemberRow: member_index: int; member_key: str; source_kind: Literal["user","unresolved"]; block_id: str; unresolved_reason: str|None; source_document_id: str|None; investigation_id: str|None
@dataclass(frozen=True) class WriteSnapshot: deliverable_id: str; title: str; canonical_html: str; manifest_json: str; blocks: tuple[SnapshotBlock,...]; members: tuple[MemberRow,...]
def snapshot_deliverable(con, deliverable_id: str) -> WriteSnapshot
def member_key(parts: Sequence[str|None]) -> str
def verify_canonical_html(html: str, block_ids: Sequence[str]) -> None   # allowlist verifier
```

**Classification table.** Every row is `member_origin: recorded`, and `investigation_id` is taken only from `outline_block_attribution`:

| Block | Member |
|---|---|
| `graph_node`, node missing | `unresolved/source_missing`, no document |
| `graph_node`, node's own `metadata.chunk_id` → `chunks.document_id` | `unresolved/projection_missing`, `source_document_id` set |
| `graph_node`, otherwise (edges are never used) | `unresolved/no_provenance` |
| `user_authored` provenance with no `metadata.migrated_from` | `user` (`investigation_id` null) |
| migrated placeholder (`migrate_outline_block.py:61-63`, report) | `unresolved/no_provenance` |
| `synthesized`, `brainstorm` | `unresolved/no_provenance` |
| `sprose:`, `prose_provenance IS NOT NULL` (generation always stores a map, `draft_generation.py:360-366,396-399`; PATCH preserves it, `ops.py:719-745`) | `unresolved/no_provenance` |
| `sprose:`, `prose_provenance IS NULL` | `user` |

**Files.**
- NEW `substrate/write/revision_snapshot.py`.
- NEW `tests/test_write_revision_snapshot.py`.
- EDIT `tests/test_derived_asset_evidence_boundary.py`: add the module to `OWNED_RUNTIME` (`:23`).

**Wire.** None. The byte grammar is a stored format.

**Tests.** On main, all fail at import (`ModuleNotFoundError: substrate.write.revision_snapshot`). Each is paired with a mutant.

| ID | Assertion |
|---|---|
| T2.1 | outline blocks appear with `data-block-id=outline_block_id`; graph-node label text is present |
| T2.2 | equal `section_index` orders by `section_id`, and equal `block_index` by `outline_block_id`; bytes are identical across calls and across a fresh subprocess |
| T2.3 | a non-servable-sourced block keeps its text, with no cite-only notice |
| T2.4 | hostile `<script>`, `" onerror=` and `</div><div data-block-id="x">` in title, prose and content are escaped; the inventory is unchanged; the verifier passes |
| T2.5 | the classification matrix, one case per row, including a node whose only chunk comes from a `contradicts` edge → `no_provenance` with document NULL |
| T2.6 | `member_key(["user","oblk-1"])` equals sha256 of the literal bytes `["user","oblk-1"]` |
| T2.7 | manifest: sorted, compact; members count and order equal `members`; hash matches |
| T2.8 | a connection wrapper that raises on any non-SELECT → no raise (reads never write) |
| T2.9 | NFC: decomposed input yields composed bytes and `text_sha256` |
| T2.10 | empty prose → no `sprose:` block |

**Mutants.**

| Mutant | Killed by |
|---|---|
| M2.1 order by `section_index` only | T2.2 |
| M2.2 no NFC | T2.9 |
| M2.3 bake cite-only | T2.3 |
| M2.4 no escaping | T2.4 |
| M2.5 any-edge resolver | T2.5 |
| M2.6 `synthesized` → `user` | T2.5 |
| M2.7 generated prose → `user` | T2.5 |
| M2.8 `investigation_id='__operator__'` | T2.5 |
| M2.9 emit an empty prose block | T2.10 |

**Risks.**
- The judgment calls in W3-C5 (brainstorm and synthesized fail closed).
- Once the export gate lands, nearly every real deliverable withholds (every sourced block is `projection_missing`; generated prose is `unresolved`). That is honest, but lane A needs copy for it.

**Dependencies.** None for the code. The shapes are final only with co-signs W3-C3, W3-C5 and W3-C9.

### PR W3-3: the writer, creation routes and route migration (deploy-atomic)

**Problem.**
- No code writes a revision: grep finds no `INSERT INTO derived_asset*` outside `tests/` and `schema.py` (report; confirmed for the table names).
- The body routes bypass revisions.
- The creation routes stamp no owner (`app.py:3557-3562`).
- LB-8 is inert in production until this lands (LB-8-SPEC:13-16).

**Design.** NEW `substrate/write/revision_writer.py`:

```python
def write_asset_id(did: str) -> str             # "write:" + did   (TC:574)
def write_event_log_id(did: str) -> str         # "write-" + did   (8.11 D1; matches events.py:191 id regex, report)
class TargetNotFound(Exception): ...            # missing OR foreign; route maps to ITS existing 404 body
def resolve_owned_deliverable(con, *, subject: str, deliverable_id=None, section_id=None, outline_block_id=None) -> str
def create_on_creation(con, *, deliverable_id: str, subject: str, route: str) -> Head   # asserts deliverables.owner == subject; returns existing head on replay
def ensure_head(con, *, deliverable_id: str, route: str) -> Head   # lazy rev 1 from PRE-state; owner = deliverables.owner (O1)
@contextmanager
def write_body_operation(con, *, subject: str, locate: TargetRef, route: str) -> Iterator[BodyOp]
```

**`write_body_operation`.** It:
- opens `con.transaction()`;
- resolves ownership (O3);
- calls `ensure_head`;
- yields to the legacy mutation.

On exit, still inside the transaction, it:
- takes a snapshot;
- if the content and manifest sha256 equal the head's, mints no revise;
- otherwise calls `repository.revise(head=…, expected_revision_id=head.revision_id, owner_user_id=…, idempotency_key="srv:"+uuid4().hex, request_sha256=sha256(canonical JSON {asset_id, route, touched_block_ids, content_sha256}), operation="edit", body=RevisionBody(snapshot), patches={"revision_blocks": replace_all, "members": replace_all}, event_log_id=write_event_log_id(did), block_ids=touched)`.

The server-side head read is serialized by the single writer. A `RevisionMoved` here is a bug: the transaction rolls back and returns 500.

**Revision 1.** It is `repository.create_revision(...)`:
- idempotency key `srv:create:<asset_id>`, which with the `derived_assets` PK makes create once-only;
- event `derived_asset.revised {operation:"create", parent_revision_id:null, block_ids: full inventory}` (W3-C2).

**Owner and wiring** (subject is `_reader_owner_id(request)`; each migrated handler gains `request: Request`):

| Route | Change |
|---|---|
| `POST /deliverables` | stamps owner (O2); `create_on_creation` in the same transaction |
| `POST /write/context/promote`, `POST /write/deliverables/from-investigation` | `con.transaction()` around the promote call plus `create_on_creation`. On from-investigation `404 no_synthesis`, nothing is created |
| `POST /write/blocks`, `/move`, `DELETE`, `/brainstorm/emit-blocks`, `/generate` persist, `PATCH /sections/{id}/prose`, `POST /sections` | wrapped in `write_body_operation` |

- The generate route's model call stays outside the lock; only the persist is wrapped. Its 503 paths write nothing.
- A move across deliverables revises both (INFERRED whether `move_block` allows it; a test pins it).

**Files.**
- NEW `substrate/write/revision_writer.py`.
- EDIT `interfaces/research/api/write_routes.py`: 6 handlers. This collides with #3536, the Codex LB-15a claim, #3530 and the stale portfolio entry `write-authenticated-deliverable-owner-20260811`.
- EDIT `interfaces/research/api/app.py`: 3 handlers (a hot file).
- EDIT `substrate/derived_assets/repository.py`, only if LB-8 did not ship the §6 interface.
- EDIT `tests/test_derived_asset_informs_routes.py`: LB-8's T20 flips. A block placed through `POST /write/blocks` is now in the head, so the PUT returns 200.
- EDIT `tests/test_derived_asset_evidence_boundary.py`: `OWNED_RUNTIME` gains `revision_writer.py`.
- EDIT any existing test that pins outbox row counts after migrated routes (INFERRED names; W3-3 must run the full suite).
- NEW `tests/test_write_revision_writer.py` and `tests/test_write_revision_routes.py`.
- NEW `docs/decisions/write-revision-writer.md`, holding §2's fixed values, D-W2 and D-W5.

**Wire.**
- No request or response field changes. W3-C11 would add an optional `revision_id`.
- New state: foreign equals missing, a byte-identical 404 per route.
- Event: D1's payload with `operation ∈ {create, edit, informs}` (W3-C2).
- No new route prefix, so no Caddy change.

**Tests.** They are black-box (HTTP plus SQL), so the red on main is behavioural.

| ID | Assertion | Expected on main |
|---|---|---|
| T3.1 | `POST /deliverables` → one `write:<did>` asset, owner = the deliverable owner = the subject; 1 `create` revision; pointer at generation 1; one outbox create event on `write-<did>`; one operations row | fails, 0 rows |
| T3.2 | promote and from-investigation → revision 1 contains every seeded block, as a single `create` | fails |
| T3.3 | a legacy deliverable (seeded through ops, no asset) then `POST /write/blocks` → rev1 `create` whose inventory **excludes** the new block, rev2 `revise` with parent rev1 that includes it, generation 2, two events | fails |
| T3.4 | refusals write nothing: 400 composition (`graph_node` without `node_id`), 404 section, foreign owner → zero `derived_*`, outbox, JSONL and `outline_blocks` delta | green on main (guard); kills M3.1 |
| T3.5 | parametrized over every migrated route: afterwards the head's `content_sha256` equals `snapshot_deliverable(con).content_sha256`, and the inventory equals outline order | fails |
| T3.6 | seeded random 30-op sequence (place, move, delete, prose, sections): the invariant in T3.5 holds after every op | fails |
| T3.7 | informs carry-forward (LB-8 PUT on b1, b2): place b3 keeps both; delete b2 drops only b2's; move b1 keeps them (D4) | `ModuleNotFoundError` |
| T3.8 | end to end with D5: legacy informs PUT 404 → one place → D2 GET head → PUT 200 | fails |
| T3.9 | owner: a session cookie minted with `user_id='u-real'` → `POST /deliverables` stamps `'u-real'` on both rows. Subject `'u-other'` on that section → 404 byte-identical to a random missing section, nothing written | first half: `deliverables.owner_user_id=='__operator__'`; second half: 201 |
| T3.10 | no `investigation_id` is `'__operator__'` or `investigation_root_id` on any member | fails (no rows) |
| T3.11 | reads never write: `GET /write/deliverables/{id}/outline`, `/write/sections/{id}/blocks`, `GET /deliverables/{id}` and `artifact.html` with `connect_write` patched to raise → 200, and no asset is created | green (guard); kills M3.11 |
| T3.12 | fault injection after the mutation, after rev1, after the child copy, after the pointer and at enqueue → the whole transaction is absent and the JSONL is untouched | fails at import |
| T3.13 | moving a block to its own slot mints no revise | fails |
| T3.14 | after commit, `write-<did>.jsonl` and the legacy log hold the events | fails |
| T3.15 | O4 invariant sweep over all `write:` assets | fails |
| T3.16 | prose PATCH on a generated section keeps `unresolved`; on a never-generated section it is `user` | fails |
| T3.17 | attach-block and reorder-block leave the head unchanged (pins the declared W3-C4 drift) | green (pin) |
| T3.S | structural: outside `substrate/derived_assets/repository.py` and `schema.py`, no non-test module contains SQL that inserts into, updates or deletes from `derived_asset*` | green on main; kills M3.13 and a revived SPR-02 |

**Mutants.**

| Mutant | Killed by |
|---|---|
| M3.1 lazy rev1 in its own transaction | T3.4, T3.12 |
| M3.2 lazy owner from the subject rather than the deliverable (seed deliverable `'u-real'`, request as `'u-real'`, rows re-keyed) | T3.15 |
| M3.3 skip the owner check | T3.9 |
| M3.4 foreign 404 body differs | T3.9 |
| M3.5 rev1 from post-state | T3.3 |
| M3.6 collapse rev1 and revise | T3.3 |
| M3.7 dispatch before commit | T3.12 |
| M3.8 one route unwrapped | T3.5 |
| M3.9 promote writes create plus revise | T3.2 |
| M3.10 `body=None` on an edit | T3.5 |
| M3.11 `ensure_head` on a read path | T3.11 |
| M3.12 always revise on a no-op | T3.13 |
| M3.13 inline INSERT in the writer | T3.S |

**Risks.**
1. Autosave churn. The prose autosave is debounced (`PROSE_SAVE_DEBOUNCE_MS`, value unread, INFERRED) and every save becomes a revise with full `canonical_html`, N inventory rows, N member rows and copied informs. Storage and lock-hold time grow linearly (W3-C13). Measure it; don't gate CI on it.
2. The single-writer lock is held longer per operation (snapshot plus rows).
3. Clients still lose updates on prose (last writer wins), because the routes carry no expected revision. That needs a lane-A wire change, out of W3.
4. Legacy `__operator__` rows will 404 under a future subject (D-W5).
5. The event version bump is shared with LB-8 and D1, so it renumbers at merge (§1.16, TC:1187).
6. File collisions: `write_routes.py`, `app.py`, `promote_context.py`, `repository.py`.

**Dependencies.**
- W3-0 or #3536 plus the W3-0 guard.
- LB-8 merged, with the §6 interface.
- W3-1 and W3-2.
- 8.11 D1, D3, D4 and D5 signed.
- Co-signs W3-C1 through W3-C9.
- A board claim. None exists; the only mention is LB-8's non_goals (`.infinite/agent-board.json:29662`, report).

### PR W3-4: `POST /write/blocks` EXTEND (TC:674)

**Problem.** `PlaceBlockRequest` has neither `investigation_id` nor `parent_event_id` (`write_routes.py:160-170`). `place_block` records the investigation only in its event envelope, defaulting to `'__operator__'` (`outline_block.py:264,304-318`).

**Design.**
- Two optional fields: `investigation_id` (1..200, the event-id regex) and `parent_event_id`.
- Each is validated: the investigation exists and is the subject's, and the event belongs to it. If they pass, W3-4:
  - passes both to `place_block`;
  - inserts an `outline_block_attribution` row inside the same `write_body_operation`.
- from-investigation also writes attribution rows for its seeded blocks, since promotion already validates that investigation.
- Unresolved graph-node members then carry `investigation_id`. User members stay null (the TC:598 CHECK).

**Stop condition.** The "owned" and "event belongs to it" predicates are not grounded in this pass (INFERRED: an investigation owner column, and an event lookup). Build is blocked until they are cited.

**Files.**
- EDIT `write_routes.py` (the model and one handler) and `promote_context.py` (the attribution rows; that file is owned by the LB-15a lanes).
- EDIT `revision_snapshot.py` (reads attribution).
- NEW `tests/test_write_block_attribution.py`.

**Wire (W3-C12).**
```
POST /write/blocks {…, "investigation_id"?: str, "parent_event_id"?: str}
422 {"detail":"investigation_not_found"}   (missing and foreign identical)
422 {"detail":"parent_event_invalid"}
```

**Tests.**

| ID | Assertion | Expected on main |
|---|---|---|
| T4.1 | an owned investigation → the member's `investigation_id` is set | fields are ignored by pydantic's default, so no attribution |
| T4.2 | a foreign investigation and a missing one → identical 422, nothing written | 201 |
| T4.3 | an event from another investigation → 422 | fails |
| T4.4 | a `user` block with an investigation → member `investigation_id` NULL | CHECK guard |

**Mutants.** M4.1 skip the owner check (T4.2); M4.2 attribute `user` members (T4.4); M4.3 write attribution on a refusal (T4.2).

**Dependencies.** W3-3; co-sign W3-C12.

### Optional W3-5: backfill (only if W3-C1b is co-signed)

A one-shot operator command writes `create_on_creation`-equivalent revision 1 for every deliverable with no asset, with owner from the stored deliverable owner (O1). It is not wired to startup.

---

## 5. Contract items not in signed 8.10 or the 8.11 draft (need co-signing)

- **W3-C1.** Revision-1 trigger:
  - Write creation routes are the first operation (eager);
  - everything else is lazy from the pre-state;
  - revision 1 and the first revise share one transaction;
  - a refused operation writes neither.

  **W3-C1b (optional):** a backfill.
- **W3-C2.** D1 admits `operation:"create"` with `parent_revision_id:null` (null if and only if create) and `block_ids` = the full inventory. The operation vocabulary is `create | edit | informs`, with the route label only in revision `metadata_json`.
- **W3-C3.** A D3 extension: prose block id `sprose:<section_id>`. Headings and the title are structural (not blocks).
- **W3-C4.** The canonical Write body definition (§2). `section_blocks` is outside it, so attach-block and reorder-block do not revise. Their drift into today's artifact and export is recorded until the export package.
- **W3-C5.** Member mapping:
  - `synthesized`, `brainstorm` and migrated placeholders → `unresolved/no_provenance`;
  - generated prose stays `unresolved`, sticky across PATCH;
  - never-generated prose → `user`;
  - graph-node documents come only from the node's own chunk;
  - `projection_missing` means "no projection pinned in this revision";
  - W3 emits no evidence (the pin rule is unsigned).

  Open question: what clears `unresolved/no_provenance`? TC defines clearing only for `unsupported` (:612-624) and `legacy_unverified` (:629-632). The block↔evidence join also waits for the first evidence writer.
- **W3-C6.** A narrowing of TC:628: a `write:` asset with a legacy parent is refused, not carried. This is unreachable.
- **W3-C7.** The owner rule O1–O4, including owner-scoped 404s on the migrated legacy routes. Today's pre-multi-user list at TC:1176-1183 does not name them.
- **W3-C8.** "The current pointer set" (TC:577) means the CAS pointer row at generation 1.
- **W3-C9.** The Write sanitizer identity `antiek-write-revision-escape/1` and the byte grammar in §2. This is required by the SDAM stop condition at `safe-derived-asset-merge-boundary.md:102-103`.
- **W3-C10.** Part 2 copy: replace "Revision 1, as it was before the first merge" (TC:1496) with a label that holds when edits come first.
- **W3-C11 (optional).** An additive `revision_id` in migrated Write route answers, so lane A can avoid a 409 round trip.
- **W3-C12.** W3-4's 422 shapes.
- **W3-C13.** Autosave is a revise, so revision growth is accepted; the alternative is a checkpoint rule, which contradicts TC:645 as written.
- **W3-C14 (flagged; not W3's).** TC:667 and TC:804 give `POST /derived-assets/{asset_id}/revisions` two incompatible bodies, and `validate_commit_boundary` rejects the fork body (`substrate/write/derived_asset_boundary.py:61-74`). LB-4b needs a ruling. W3 mounts nothing under `/derived-assets`.

## 6. Coordination with LB-8 (internal; no wire)

- **L1.** `revise(..., body: RevisionBody | None = None)`. With `None`, the parent's bytes are copied; M20 still holds for informs.
- **L2.** `create_revision(con, *, asset_id, owner_user_id, asset_kind, title, asset_metadata_json, body: RevisionBody, blocks: Sequence[str], members: Sequence[MemberRow], idempotency_key, request_sha256, event_log_id) -> Head`. It writes the asset, revision, blocks, members, operations row, pointer (generation 1) and outbox create event, all in the caller's transaction.
- **L3.** The manifest is a JSON object whose `members` array is what LB-8's integrity check reads (`revise` step 2, LB-8-SPEC:193).
- **L4.** The informs copier drops rows whose `block_id` is missing from a patched inventory (D4). W3's T3.7 tests it.
- **L5.** Callers use `con.transaction()` (re-entrant) plus `enqueue_event`, not a bare-`BEGIN` `eventful_transaction`. Dispatch happens after commit.
- **L6.** D1's payload type: `parent_revision_id: str | None`, validated null if and only if the operation is `create`, in LB-8's single event bump.

## 7. Out of scope and recorded

- The serve-time and export gates, and moving `GET /deliverables/{id}`, artifact and export onto revisions (TC:636-644). `GET /write/deliverables/{id}` does not exist on main.
- Evidence pins and a projection producer.
- The attest and evidence routes.
- `restore`.
- LB-4b fork and merge. These are blocked on W3-3 and W3-C14.
- Retiring `section_blocks`.
- G7 owner re-keying.

## 8. Cross-lane findings for the caller

1. **The #3536 dispatch hazard in §3.** Confirmed by reading, not executed. It should be fixed inside #3536 (the W3-0 guard) before that PR merges.
2. **No board claim exists** for the W3 writer or the member rebuild. One must be recorded before W3-1 or W3-3 starts.
3. **The relayed Astra update** (A06 composition amendment; A20 `b8bd33369`) was not carried to a rev9 activation receipt, because this pass is read-only with no transport. Its effect on W3:
   - A20 changes no `user_id` stamping, so D-W5 stands.
   - W3 adds no registrar, book, PDF or converter writers, so the PA01–PA05 composition does not gate W3.
   - Any future evidence pin, and LB-8's local readability predicate, must defer to PA04 and PA05.