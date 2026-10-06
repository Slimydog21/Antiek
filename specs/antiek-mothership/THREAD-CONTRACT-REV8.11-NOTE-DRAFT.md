# THREAD-CONTRACT rev 8.11 — LB-3, LB-8 and LB-9 wire precision (draft v5, lane B, 2026-09-27)

**Status: draft, unsigned.** This note amends signed rev 8.10 (`THREAD-CONTRACT.md`, sha256 `2395975c…821d9`) only where LB-3 (agent threads as right-pane tabs), LB-8 (Write informs) and LB-9 (the companion document) found the signed text silent, ambiguous or contradicted by main.

**What it changes.** The item sections are the inventory. Every change to a type, route or state:
- ThreadSummary:
  - `state` may be `null` (A1);
  - new fields `failure_reason` and `failed_before_start` (A10);
  - the budget halt set is extended (A2).
- `GET /investigations`:
  - the `?project_id=` authority (A4);
  - the `?document_id=` sources, with a `503 passage_links_unreadable` (A5).
- `POST /investigations/{id}/seen`: signed §1.5 names it, and A6 fixes its body, answers and stored state.
- `thread_counts` and `spend_today` null rules (A7).
- `POST /investigations` request fields `project_id?`, `title?`, `document_id?` (A9).
- The companion document:
  - the Part 1 `state` enum (C1);
  - a fourth stale cause (C3);
  - the entry `origin` ruling (C5b);
  - wire details (C6).
- Write informs:
  - the `derived_asset.revised` event (D1);
  - a read route (D2);
  - block identity (D3);
  - carry-forward (D4);
  - no-revision 404 and the rev-9 exemption (D5).

**How it binds.**
- Both lanes sign it, after a different-lineage audit round.
- Lane B builds LB-3a/3b, LB-8 and LB-9b/c against it; none of those PRs merges before the signature.
- Each rule is chosen so that the rev-9 Part 1 draft need not reverse it. Where rev 9 must change something, the item says so.

**Evidence.** The executable specs carry the full evidence: `cockpit/LB-3-SPEC-2026-09-27.md`, `cockpit/LB-8-SPEC-2026-09-27.md` and `cockpit/LB-9-SPEC-2026-09-27.md`.

**Citations.** They are `path@commit ("anchor")`. Each anchor was checked to exist at that commit with a script (`cite_check.py`, lane B scratch).

**v5 (lane A):**
- A10's `failed_before_start` is derived only for `kind: research`, the one kind that writes `phase.enter`, and is `null` for every other kind.
- A7 records the null-reason codes that rev 9's `null_reasons` adds.
- MiMo round 3 on v4 produced no verdict: the run failed with "Session not found" during the host's disk-full window. Round 3 reruns on v5.

**v4 (MiMo round 2: REWORK, 5 majors, 3 minors):**
- A1 nulls an incomplete log with no terminal, and pins an unreadable leaf before the leaf aggregate.
- A6 defines the completion event for aggregate-done sessions.
- A2 supersedes LB-3 spec N2.
- A10 scopes the closed-set rule, and the fields are on LB-3's wire.
- C1 is corrected.
- The inventory is complete.
- The LB-3 spec carries an 8.11 supersession block.

**v3 (MiMo round 1: REWORK, 1 blocker, 6 majors, 3 minors, 3 wrong citations; all addressed):**
- Part B is withdrawn (the blocker; see below).
- A1 has a precedence order.
- A2 declares its extra derivations and the budget-set extension, and follows signed :269.
- A6 keys "done unseen" on a stable terminal event id.
- A7 nulls counts over any underivable member.
- A10 gains `failed_before_start`, and its closed set covers both owner-model codes.
- D4 drops a removed block's members.
- D5 discloses the rev-9 §1.15 conflict.
- C3 and C5 are marked as needing signature.
- The three wrong citations are fixed.

**Items marked "record"** need no re-sign. They state how signed text is read where main has no producer.

---

## Part A — thread states, listings, seen (LB-3a, LB-3b)

**A1. An underivable state is `null`, never a guess (§1.2).** The helper reads a thread's layers (sealed Parquet, then the JSONL tail) independently, and decides in this order:
1. **A terminal recovered from any readable layer decides the state** (A2), even if another layer failed to read.
2. **A `reading` thread reads `idle`** (signed §1.2), whatever its layers hold, including an empty `read-<doc>` log.
3. **Otherwise, if the read is incomplete, `state` is `null`.** A read is incomplete when:
   - any layer failed to read; or
   - the reader skipped any record it could not parse (`trajectory_read` reports this; plain `trajectory()` skips silently, which is why LB-3a uses `trajectory_read`).
4. **For a `cascade_session` with no terminal of its own**, the leaf aggregate (A2c) is consulted only when **every** leaf read is complete. If any leaf read is incomplete, the session's state is `null`. This rule is applied before the aggregate is computed.
5. **Otherwise the state is derived from a complete log.**
   - A research thread is `running` when a `phase.enter` exists, else `queued` when a start exists.
   - A cascade leaf is `running` when its `start_requested` exists, else `queued` when its `spawned_from` exists.
   - A log with no lifecycle record at all is `null`.

Basis: the Part 1 rule "An unknown value is always `null` with a reason, never `0`", and §1.2's count nullability. `needs_you` is not derived from a log (A3).

Today the list reader enumerates with `interfaces/research/api/app.py@b41f4ec9b` ("for filename in _os.listdir(events_dir):"), and one unreadable sealed log fails the whole list. Under A1 that row reads null and the rest answers 200.

Lane A renders null as unknown, never "working", "failed" or "needs attention". Lane A chose this over a 503 fallback, because a 503 would blank a whole list over one log.

**A2. Which terminal wins (§1.2 "State"), stated exactly.**

LB-3a's helper uses wave 5's `terminal_event` (`runtime/research_runner/protocol.py@2be3e0d1b` ("def terminal_event(")) for its core precedence:
- `investigation.completed` with `outcome` `stopped` or `cancelled` is stopped, and otherwise done;
- `investigation.failed` is failed;
- a chase halt counts only when the log has no completed or failed row.

On top of that it adds three derivations, declared here:
- **(a) The halt reason decides.** A chase halt with no completion of its own is terminal **only for a budget reason**, and then reads `stopped` with `stop_reason: budget`.
  - Signed §1.2 names `budget_exceeded` and `aggregate_budget`.
  - **8.11 extends that set** with the runner scopes `per_research` and `aggregate` (`runtime/research_runner/budget.py@b41f4ec9b` ("scope=\"per_research\"")).
  - Any other halt reason, including `depth_reached`, `duration_reached`, `no_open_questions` and `chase_disabled`, ends the chase and not the thread, as signed :269 says. The thread is then read by its own completion, and if it has none, by rule A1.5.
  - `terminal_event` itself classifies every such halt as budget-halted. The helper does not follow it there. No current writer produces that case: Loop One writes chase halts after its completion, and the runners write only budget reasons.
- **(b) Cascade session failure.** The session log's `cascade.synthesis_tail.failed` counts as `failed`.
- **(c) Cascade leaf aggregate.** A cascade session with no terminal of its own reads the aggregate of its leaves, as main's list does today: any leaf failed → `failed`; any done → `done`; otherwise `stopped` with `stop_reason: null`.

The legacy `status` is unchanged. `state` and `stop_reason` are added beside it.

**This supersedes LB-3 spec N2** where N2 made any chase halt with no completion terminal. The LB-3 spec now carries an 8.11 supersession block.

**A3. `needs_you` (record).**
- `needs_you` means a pending cascade spend approval bound to a thread.
- On main that approval is a pre-launch step, and the launch refuses with 409 before any session log exists (`interfaces/research/api/cascade_routes.py@b41f4ec9b` ("hard_ceiling_approval_required")).
- So the helper never emits `needs_you`, and `thread_counts.needs_you` is a counted `0` over complete reads. It becomes non-zero when a durable pending-approval record exists (W3).

**A4. `?project_id=P` (§1.5 members).**
- It lists the threads that hold an `investigation` member row in P, read through LB-2's registry. A start-payload filter could not honour the signed member DELETE.
- A member whose log is absent is omitted in rev 8.x (rev 9 lists it as `no_record`).

**A5. `?document_id=D` matches exactly three sources:**
1. the envelope `document_id` of the thread's first start-family event;
2. the reading thread `read-D`;
3. a child linked from `read-spin` by `question.escalated_to_research` whose passage id names D (`substrate/books/passage_research.py@b41f4ec9b` ("def parse_passage_id")).

Ingest events on other logs, `documents.investigation_id` filing and `anchored_highlights` do not match. When `read-spin` cannot be read, the route answers `503 {reason: "passage_links_unreadable"}`, so an incomplete list is never shown as empty.

**A6. `POST /investigations/{id}/seen` (§1.5 `thread_seen`).**
- Body exactly `{through_event_id}`.
- Answers:

  | Status | Body |
  |---|---|
  | 200 | `{thread_id, seen_through_position}` |
  | 404 | `{reason: "not_found"}` |
  | 422 | `{reason: "event_not_in_thread"}` |
  | 422 | `{reason: "seen_body_invalid"}` |
  | 503 | `{reason: "thread_log_unreadable"}` |

- The server stores two things per `(owner, thread)`:
  - **`seen_through_position`**: the event's 0-based index in `GET /trajectory/{id}` order, kept as the maximum ever sent. It is a reading cursor only, and it is advisory. `trajectory()` orders by `(emitted_at, event_id)` (`substrate/event_log/events.py@b41f4ec9b` ("merged.sort(")), so a backfilled event can shift what a position points at.
  - **`seen_terminal_event_id`**: the id of the thread's terminal event, recorded when the POSTed event is that terminal or sits after it. This is a stable id, not a position.
- **The completion event of a `done` thread** is:
  - its own terminal event, when it has one;
  - for a `cascade_session` that is done by its leaf aggregate (A2c) and has no terminal of its own, the latest leaf terminal event in trajectory order across its leaves;
  - `null` when neither exists.
- **`seen_terminal_event_id`** is recorded when the POSTed event is that completion event or sits after it in the same thread's order. For an aggregate-done session, POSTing the session's own latest event counts.
- **`done_unseen`** counts the threads whose `state` is `done` and whose completion event id is `null` or differs from `seen_terminal_event_id`. A null completion id always counts as unseen, so nothing done is ever hidden. A new or backfilled completion always reads unseen, and no cursor drift can hide it.

**A7. `thread_counts` and `spend_today` (§1.5).**
- `thread_counts` is `null` when any member's `state` is `null` (A1), or when the member or `thread_seen` read fails. It is never computed over a partial set, so `running: 0` is never served beside an unknown member.
- 8.11 has no `null_reasons` mechanism, so these nulls carry no reason code, and lane A reads a null with no entry as 8.11's copy.
- Rev 9's `null_reasons` (§1.5, "One entry per derived field that is null") adds two codes:
  - `thread_counts: member_state_unknown` (a member's state is null, or a member or `thread_seen` read failed);
  - `spend_today: not_attributed`.
- `spend_today` stays `null` until §1.13 attribution ships (record). The only spend ledger on main is keyed by run, not by thread or project (`substrate/midnight_oil/budget_ledger.py@b41f4ec9b` ("CREATE TABLE IF NOT EXISTS midnight_oil_spend_ledger")).

**A8. The per-thread GET (record).**
- `GET /investigations/{id}` carries the same ThreadSummary fields as a list row.
- It keeps `200 {status: "not_found"}` for an unknown id, as pinned by `tests/test_investigation_endpoints.py`. The 404 is rev 9's.

**A9. Launch scope (§1.2 `project_id?`, `title?`, `document_id?`).**
- `POST /investigations` gains all three as optional fields.
- Refusals come before any write:
  - `404 {"detail": "project_not_found"}` when the project is missing or another owner's (LB-2's shape);
  - `404 {reason: "document_not_found"}`;
  - a `title` outside 1..200 characters after strip → 422.
- After every existing refusal, and immediately before the start event, the launch writes the `investigation` member row. It is idempotent.
- The start event carries `project_id` and `title`, and its envelope carries `document_id`.
- Rev 9's scope union supersedes these flat fields additively. The fields stay readable.

**A10. `failure_reason` and `failed_before_start` (NEW ThreadSummary fields).**
- **`failure_reason: "owner_model_unavailable" | "owner_model_outcome_unknown" | null`.**
  - It is non-null only when `state` is `failed` and the failed terminal's `reason` is one of those codes.
  - Loop One writes both codes, before phase 1 and mid-run (`orchestration/loop_one/orchestrator.py@b41f4ec9b` ("owner_model_unavailable")).
  - Free-text diagnostic reasons never enter these fields. The set grows only by a signed revision.
- **`failed_before_start: bool | null`.** It is derived **only for `kind: research`**, because only a research log writes `phase.enter`. For a failed research thread it is `true` when no `phase.enter` precedes the failed terminal, and `false` when one does.
  - It is `null` for every other kind, because none of them can prove whether it started:
    - `cascade_leaf` runs on `start_requested`;
    - a `cascade_session` can fail in its synthesis tail after its leaves ran;
    - `reformat` and `reading` have no `phase.enter`.
  - It is also `null` when `state` is not `failed`.
  - Lane A's rule "never assert a start we can't prove" gives `null` the copy "Didn't finish", with no start claim.
- Lane A shows "Didn't start" only when `failed_before_start` is `true`. The owner-model sentence keys on `failure_reason`. The UI never names a phase.
- **Scope of the closed-set rule.** It covers the ThreadSummary fields, on the list and on the per-thread GET alike. It does **not** cover the per-thread GET's legacy `terminal_payload` (`interfaces/research/api/app.py@b41f4ec9b` ("terminal_payload=")), which returns the raw terminal payload, a free-text `reason` included.
  - That field is the owner's own run, and single-operator today (G7). 8.11 leaves it unchanged, because lane A may read it.
  - Lane A renders failure copy only from `failure_reason` and `failed_before_start`, never from `terminal_payload.reason`.
  - Rev 9 gates `terminal_payload` with the per-thread GET's owner scoping.
- **Wire.** Both fields are on the ThreadSummary wire shape in LB-3a, beside `state` and `stop_reason` (the LB-3 spec's 8.11 supersession block).
- **The producer fix these fields rely on (LB-3a0, building).** Today a run refused before phase 1 writes no terminal at all, because `phase=0` fails validation. After LB-3a0 it writes `investigation.failed {phase: 1, reason, last_completed_phase: null}`, and with no `phase.enter` it reads `failed_before_start: true`.

## Part B — dialogues and ask: WITHDRAWN from 8.11 (MiMo blocker)

MiMo showed that Part B was not a strict subset of rev 9 §1.8. Rev 9 would have had to reverse:
- the optional idempotency key, which rev 9 makes required;
- the request identity;
- "provider error writes nothing", which rev 9 replaces with `thread.turn_failed`;
- the create and replay answers;
- the flat scope fields, which rev 9 replaces with the scope union;
- stored-answer gating, which rev 9 does at read time.

Conforming Part B fully would copy rev 9's whole turn model (turn ids, attempts, recovery and `GET …/turns`) into 8.11. So LB-3c, persisted dialogues with ask, builds on rev 9 §1.8 once rev 9 is signed. It is rev 9's tier-2 package (T2). Nothing of Part B ships under 8.11.

## Part C — the companion document (LB-9b, LB-9c)

**C1. `state` is `ready | stale | unavailable_until_rights`.**
- Part 2 already names all three (signed Part 2 §2.7: `ready`, `stale`, `unavailable_until_rights`). 8.11 closes the Part 1 wire enum to exactly these three.
- A scope never refreshed reads `stale`, with `content_hash: null` and `entries: []`.
- While unavailable, the body is `{entries: [], content_hash: null, covered: {}, summarised_thread_count: null, total_thread_count: null, state: "unavailable_until_rights"}`.
- `partial` and `empty` stay lane A's derivations.

**C2. The rights precondition is both branches (record).** Signed §1.12 says "Nothing here ships until the wave-5 export branch and `fix/w5-mcp-hardening-20260923` merge".
- While off, every GET answers 200 with the unavailable body, and every refresh POST answers `409 {reason: "unavailable_until_rights"}`.
- The 404 for a missing or foreign scope comes before either, so the switch is never an existence oracle.
- One reviewed PR (LB-9d) flips it.

**C3. A fourth staleness cause: drift (extends signed §1.12's closed list; needs signature and a Part 2 addendum).**
- The document also reads `stale` when the served projection's hash differs from the receipt's `content_hash`. That catches a refinement logged outside the member threads, and a takedown between refresh and read.
- Part 2's stale copy, "Newer activity since this was written", is false for this cause. So lane A adds copy for drift. Lane B proposes: "The sources behind this changed since it was written."

**C4. Gating an entry drawn from a thread's body (§1.2 "Synthesis"; record).**
- The excerpt gate decides per member thread. Under the literal signed rule, one non-servable source in a thread withholds every entry drawn from that thread. The entry's `source_refs` name the source that held it back.
- The operator's own `personal_reading` documents read as withheld under 8.10, which has no owner path. Rev 9's A06 owner allowlist is where that changes.

**C5. Kinds and origin (C5a is record; C5b is a ruling needing signature).**
- **C5a.** Rev 8.x entries are `insight` and `open_question` only. `claim` entries come from the §1.10 pack over `supporting_claims` (W2 / LB-24a). twin_note_taker contributes nothing until its ids carry an owner.
- **C5b.** An entry's `origin` is `source` when it has at least one own pin, and `unsourced` otherwise. It is never `operator` or `generated`.
  - This is lane B's ruling. Wave 5's resolver treats a question with no source as the operator's own words, and LB-9 does not.

**C6. Wire details for lane A.**
- `process_ref` is the object `{thread_id, event_id}`.
- A missing or foreign document answers `404 {"detail": "document_not_found"}`, and a project answers `404 {"detail": "project_not_found"}`, identically for missing and foreign.
- A refresh whose receipt could not be written answers `503 {reason: "receipt_not_written"}`, and its rows are never served until a retry succeeds.

## Part D — Write informs (LB-8; §1.11 revise)

Signed rev 8.10 defines the informs PUT (§1.11a "Write informs (S5)"). LB-8 builds it on a shared §1.11 revise primitive, which LB-4b's fork and merge and LB-5's span ledger then reuse.

**D1. `derived_asset.revised` (NEW event).**
- Payload: `{derived_asset_id, revision_id, parent_revision_id, operation, block_ids[]}`.
- It is written through `write_event_outbox` inside the revise transaction (§1.11: one `connect_write` transaction writes the revision, members, pointer, idempotency record and outbox row).
- It carries **no document ids**, so no saved reference leaks into an event log.
- The log is `write-<deliverable_id>`, which is never listed as a thread: §1.2's attribution-bucket rule extends to `write-*`.
- It rides the next sequenced schema bump, with codegen in the same commit.

**D2. A read of one block's informs (NEW route).**
- `GET /derived-assets/{asset_id}/blocks/{block_id}/informs` answers the PUT's 200 shape at the current revision.
- It answers 404 exactly as the PUT does, and writes nothing.

**D3. Block identity.** `block_id` is the stable Write block id (`outline_blocks.outline_block_id`). A Write revision records its blocks under those ids.

**D4. Carry-forward.**
- Every revise copies unchanged each per-revision row it does not replace, **for the blocks the new revision keeps**: members, the block inventory and informs.
- A block the revise removes loses its informs **and its members**. So an unresolved member on a deleted block can never withhold the new revision's export (signed §1.11 rule 1 on withholding).
- Bites follow LB-5's carried-bite rule.

**D5. No revision yet, and one disclosed rev-9 conflict.**
- A deliverable with no revision answers 404 to the PUT and the GET.
- LB-8 writes no revision 1. §1.11's `create` ("the first operation on a deliverable writes revision 1") belongs to the W3 Write revision writer.
  - Lane B has grounded it (spec to follow); it is still unclaimed.
  - So under 8.11 an informs PUT is **not** a first operation that may create revision 1. This is a narrowing of the signed trigger, declared here.
- Until W3 lands, lane A keeps S5 persistence off, with its copy "Evidence links aren't saved yet for this piece."
- **Rev-9 conflict.** The rev-9 Part 1 draft's §1.15 rule 4 answers a missing document named in a body with `404 source_not_found`. The signed informs route answers `422 informs_invalid {index, detail: document_not_readable}`. Rev 9 must exempt the informs route from rule 4, or amend informs. Lane B proposes the exemption, so the list is marked in place, **on lane A's condition**:
  - The 422 answer is byte-identical for a missing document and another owner's private document: `detail: document_not_readable`, at the same `index`.
  - So the in-place row marking is never an existence oracle for another owner's private document, which is what rule 4 prevents.

**Also recorded for lane A.**
- `422 informs_invalid {index, detail}` uses a closed `detail` set: `too_many_entries` (at index 50), `duplicate_document` (at the second occurrence), `document_not_readable`, `anchor_other_document`, `anchor_invalid`, `entry_invalid`.
- A missing document and a foreign private one get the same `detail`.
- No 403 is ever returned. A missing or foreign asset is `404 {"detail": "not_found"}`.

---

## Lane A's choices (answered 2026-09-27; v3 re-confirmed by lane A, pending MiMo round 2)

1. **A1 as written:** unchanged in intent. v3 adds the precedence order.
2. **Part B:** withdrawn, which lane A re-confirmed. LB-3c follows rev 9's T2 package. Lane A's persisted-dialogue work (A16) was already gated on rev 9.
3. **Copy** (lane A's 8.11 Part 2 addendum):
   - a null state is a neutral dot with "State unknown", and on focus "Its record couldn't be read.";
   - a null `spend_today` is "—" with "Spend by project isn't recorded yet";
   - when `failed_before_start` is true, "Didn't start", followed by the sentence for its `failure_reason`:
     - `owner_model_unavailable`: "The model you chose isn't available. Pick another and try again."
     - `owner_model_outcome_unknown`: "We couldn't confirm the model's answer, so nothing started. Try again."
   - when `failed_before_start` is false, "Didn't finish", followed by:
     - `owner_model_unavailable`: "The model you chose stopped being available. Pick another and try again."
     - `owner_model_outcome_unknown`: "The model's answer didn't come back, so the run stopped. Try again."
   - when `failed_before_start` is null, "Didn't finish" without any claim that it started;
   - when `failure_reason` is null, the failure renders by state alone;
   - a null `thread_counts` reads "—" with "Still counting";
   - drift has its own stale copy (C3);
   - the informs 404 reads "Evidence links aren't saved yet for this piece.";
   - the per-code informs lines are as sent.

## Signatures

- Lane B (types and endpoints): _pending audit round 2_
- Lane A (UI states): _pending_
- Different-lineage audit:
  - round 1: MiMo, REWORK (1 blocker, 6 majors, 3 minors, 3 wrong citations; all addressed in v3);
  - round 2: _pending_.
