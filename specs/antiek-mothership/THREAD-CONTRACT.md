# THREAD-CONTRACT — the shared contract between lane A (UX) and lane B (data)

**Rule:** nobody builds against this file until both signatures at the bottom are filled in. After
signing, any change is a new dated revision that both lanes re-sign.

- **Part 1 (types and endpoints):** owned by lane B, Antiek Sweep v2 (a59f7aa2).
- **Part 2 (UI states and required fields):** owned by lane A, Antiek Nudge v2 (236c36bd).

Binding inputs: `DECISIONS.md` D1–D6 and `DESIGN-MODEL.md`. Lane B's guardrails, quoted from Sweep v2 on
2026-09-24:
- A thread *is* an investigation. It keeps the existing id, event log, `spawned_from` / start-payload
  lineage and `passage_research` anchor, plus whatever anchor and addressability fields grounding shows
  are missing.
- Companion documents derive from the research-artifact and html_projection projections, never a
  parallel document model.
- Fork and merge-into-document reuse the HTML-projection fork lineage and Write documents.
  **Corrected by lane B grounding (§1.1.2):** HTML projections have no fork lineage beyond the style parent; a document fork is a derived-asset revision, and source merge is retired.

---

## Part 1 — Types and endpoints (lane B drafts)

**Revision 8 (2026-09-26), audited to 8.10 and signed by lane B 2026-09-27; lane A's signature below.** This revision carries the operator's paragraph 2 as decision **C6**: prompt-driven reformulation of any information asset, with bite-level provenance and probe-to-core. The prompt is verbatim in `cockpit/OPERATOR-PROMPT-KIMI-2026-09-24.md`. It adds §1.11a and adopts four stores that other lanes built better than the contract described them (`cockpit/FORENSIC-SWEEP-V2…` §8.2 LB-1; sibling-stacks §3). It also lands the three seams rev 7 deferred: S5 (Write `informs`), S6 (reformat derivation) and S8 (attribution telemetry). The operator ruled T6 and T7 as recommended, and T9 as one tree per mode, on 2026-09-26 (`DECISIONS.md` "Operator rulings, 2026-09-26"). He also confirmed C1–C5, so the rev-7 caveat "as far as the operator's cockpit goal confirms them (T1)" is settled. Changes are marked "(rev 8)".

**Rev 8 audit (GLM-5.3-Flash via glmf-codex, different lineage, 2026-09-26).** It confirmed all four rev-6 findings resolved and every changed citation correct. It raised eight design majors, which **rev 8.1** closes and marks "(rev 8.1)":
- the §1.14 authority text;
- reformat under the cap;
- request idempotency and recovery;
- an estimator;
- rights for a reformulation of a reformulation;
- classes through a Write merge;
- span partition and support;
- probe routing to the core.

**Rev 8 audit, round 2 (GLM-5.3-Flash).** Five of the eight round-1 findings were confirmed fixed. Its remaining Part 1 items are closed in **rev 8.2**, marked "(rev 8.2)":
- GatedText `origin`;
- a fully specified `generated` member with the bite join;
- lineage storage;
- model selection;
- Write-mode placement;
- support that fails closed.

Its Part 2 items (§2.9, the §2.11 estimator and probe) had already been reconciled by lane A before the audited copy was superseded.

**Rev 8 audit, round 3 (GLM-5.3-Flash).** Every rev-8.1 and rev-8.2 Part 2 item it rechecked was already closed by lane A's 20:01Z reconciliation, which its copy predates. Its Part 1 items are closed in **rev 8.3**, marked "(rev 8.3)":
- the span endpoint;
- mode-aware wording;
- a distinct `unsupported` member;
- a multi-ref bite join;
- legacy generations;
- stable model binding;
- one failure vocabulary;
- the multi-window class rule.

**Rev 8 audit, round 4 (GLM-5.3-Flash, whole file current).** 12 of 18 prior items were confirmed fixed. Its blocker and majors are closed in **rev 8.4**, marked "(rev 8.4)":
- a serve-time rights gate for Write bodies;
- unsupported can no longer be cleared by attestation alone;
- a single join form for cited unsupported bites;
- a deterministic window tie-break;
- a support gate for `research_supplemented`;
- "lexical support", no longer described as entailment.

**Rev 8 audit, round 10 (GLM-5.3-Flash).** 12 of 13 round-9 items were confirmed fixed. **Rev 8.10** closes the rest, marked "(rev 8.10)":
- one stale backfill sentence;
- the class invariant now admits operator edits;
- hash drift is a read-time overlay;
- a citation path is corrected;
- the generation identity now follows the adopted plural storage;
- a fork has its own revise route.

**Rev 8 audit, round 9 (GLM-5.3-Flash).** 7 of 8 round-8 items were confirmed fixed, including all three LB-2 code items. **Rev 8.9** closes the rest, marked "(rev 8.9)":
- unresolved spans become a discriminated outcome, and unplaceable bites are listed apart;
- `declared_class` gets its column;
- a fork's bites are rows of the new revision;
- the "adopted code" now names the repaired lineage, #3527, which registers the view as `derived`;
- LB-2's restore compares the retired node (PR #3530, `ee6867a11`).

**Rev 8 audit, round 8 (GLM-5.3-Flash).** All six round-7 items were confirmed fixed, and **rev 8.8** closes its seven new ones, marked "(rev 8.8)":
- a sourceless unsupported span had no legal `origin`;
- an unplaceable backfill bite had no representable state;
- an operator could paste source words into the prompt and template them;
- `rights_basis` had two shapes;
- three LB-2 code items (tree bytes, depth, the last-page cursor), fixed in PR #3530 and stated in §1.6.

The same revision corrects §1.11's false claim about source merge.

**Rev-9 co-sign gate (2026-09-27, agreed by both lanes).**
- No lane-B build of LB-17 or later, and no lane-A build of A11 or later, until rev 9 carries both lanes' signatures and a different-lineage audit ACCEPT.
- Every citation added from rev 8.8 on is `path@<commit>` plus a quoted anchor phrase, never a bare line number, because line numbers drift.

**Rev 8 audit, round 7 (GLM-5.3-Flash).** All 14 round-6 items were confirmed fixed. It found six new ones in sections the earlier rounds had not reached, and **rev 8.7** closes them, marked "(rev 8.7)":
- a template slot could carry a source heading, so source text passed as sourceless `generated` text;
- the reading-version adoption had a table but no route;
- the Write informs editor had no revise operation;
- `bite_provenance` could not hold the origin and support columns its rules need;
- `research_supplemented` was not bound to research the generation was actually given;
- a reading-state citation claimed the 409 returns the current row.

**Rev 8 audit, round 6 (GLM-5.3-Flash).** 9 of 10 round-5 items were confirmed fixed. The one it still broke was the connective-text validator: lexical overlap cannot tell a framing sentence from an assertion that echoes the prompt. **Rev 8.6** closes the Part 1 findings, marked "(rev 8.6)":
- `generated` now comes only from a closed set of non-assertive templates, whose slots must be verbatim operator or source text;
- `validator_version` is on every span;
- a sentence longer than the span cap is its own span;
- the retirement table's write discipline is stated exactly.

The three Part 2 findings (§2.2, §2.4, §2.8) are lane A's.

**Rev 8 audit, round 5 (GLM-5.3-Flash).** 19 of 24 prior items were confirmed fixed. Its three blockers are closed in **rev 8.5**, marked "(rev 8.5)":
- `generated` must now be earned, so omitting a ref turns the text `unsupported`, never `generated`;
- support is scored per sentence, so a failing sentence cannot hide inside a supported span;
- the review carries a typed `acknowledgements[]`.

Its majors are also closed: an evidence-attachment operation, and one wire form for support.

**Revision 7 (2026-09-26).** This revision does two things. Changes are marked "(rev 7)".

First, it applies codex's audit of rev 6: 52 of 53 prior findings were resolved, and the open one was Part 2's, which lane A reconciled and re-signed at rev 6. It closes the three new Part 1 majors:
- legacy withholding now survives an ordinary revision (§1.11);
- the cap halt is durable across a crash (§1.13);
- retired tabs carry their complete node (§1.6).

Second, it absorbs the cockpit decisions C1–C5 and the seams S1–S8 that lane A signed on 2026-09-26 (`cockpit/FORENSIC-SWEEP-V2-KIMI-COCKPIT-2026-09-26.md` §8.3). C1–C5 stand as far as the operator's cockpit goal confirms them (T1). Their Part 1 consequences:
- the vocabulary (§1.0);
- thread kinds for agent tabs (§1.2; S2);
- document refs a client can open (§1.2; S1);
- tab sides and branch-origin kinds (§1.6; S1, S3);
- the Findings tab (§1.12; S7).

Three seams wait for rev 8, which carries the operator's paragraph 2 as C6: Write `informs` (S5), reformat derivation (S6) and attribution telemetry (S8).

**Rev 7 audit (MiMo, different lineage, 2026-09-26).** It confirmed all four rev-6 findings resolved and every rev-7 citation correct, including `events.py:358-371`. It raised six items against a copy taken before R7-1..R7-3 and lane A's Part 2 re-sign. Five were already closed by R7-1..R7-3 and that re-sign. The sixth, §1.11's `member_origin` and `unresolved_reason` enums missing `attested` and `legacy_unverified`, is fixed.

**Revision 6 (2026-09-24).** This revision applies codex's audit of rev 5 (43 of 49 resolved; 6 unresolved and 4 new, closed here) and lane A's R5-1 to R5-6. What changed:
- `GatedText` is one discriminated type with a mixed-source rule, and the rev-4 excerpt marker is its projection (§1.2; R5-1).
- Every item, entry, hunk and answer names its `GatedText` field (§1.8, §1.10, §1.11, §1.12; R5-2).
- The member table is rebuilt in full, and the export gate reads its members (§1.11).
- Overshoot is settled truthfully. A durable cap halt carries it, with its inbox kind and a `stop_reason` (§1.2, §1.13; R5-3, R5-4).
- Child counters are per parent, and allocation is idempotent and checked against an append-only register (§1.6; R5-5, R5-6).

Changes are marked "(rev 6)".

**Revision 5 (2026-09-24).** This revision applies codex's audit of rev 4 (37 of 41 resolved; 4 unresolved and 8 new, closed here). Lane A must reconcile §1.13's admission copy in Part 2. Changes are marked "(rev 5)".

**Revision 4 (2026-09-24).** This revision applies codex's audit of rev 3 (30 of 34 resolved; 4 unresolved and 7 new, all closed here) and lane A's R4-1 and R4-2. Changes are marked "(rev 4)".

**Revision 3 (2026-09-24).** This revision applies codex gpt-6-sol's re-audit of rev 2 (12 of 21 findings resolved, 13 new), lane A's R3-1 through R3-6, and lane A's citation note. Changes are marked "(rev 3)".

**Revision 2 (2026-09-24).** This revision applied codex gpt-6-sol's audit of rev 1. The audit checked all 94 citations and found 8 wrong citations and 13 design gaps; every one is corrected below. It also applies lane A's R2-1 (`selection`, not `island`, in payloads) and R2-2 (summarised/total thread counts). Both lanes re-sign rev 2.

Grounded against main `15e78e276`. The evidence is in `ground/lane-b.json`: 58 capabilities, each classed RUN or READ and cited `path:line`. Lane B's grades against the operator goal: B1 29, B2 24, B3 31, B4 21, B5 30. What exists is sound storage; what is missing is behaviour. Every Need in Part 2 is marked below as one of:
- **EXISTS**: main meets it; the entry cites where.
- **EXTEND**: a named module gains the stated delta.
- **NEW**: the entry defines it here.

No new store is introduced where an existing one can carry the concept. An unknown value is always `null` with a reason, never `0` (Part 2's rubric veto).

### 1.0 Vocabulary (binding on code, routes and event names)

| Word | Means | Never used for |
|---|---|---|
| cockpit (rev 7, C1) | the one shell. Research, writing and reading are its modes, and Speak and Home are doors outside the mode cycle (T11). | a second shell per mode. In code and routes the mode key stays `mothership` (`/projects/{id}/tabs/{mothership}`), which names a mode, never the platform. |
| left pane / right pane (rev 7, C2, C4) | the core material (document tabs) on the left, and the agents (agent tabs) on the right in research and reading. In writing the right pane is the block outline (C5). | "companion" as a name for the right pane |
| agent tab (rev 7, C4; S2) | a right-pane view of exactly one thread (§1.2 `kind`) | a store of its own: an agent tab holds a `thread_id`, never content |
| thread | exactly one investigation (`thread_id` = `investigation_id`) | the seams entity view and `ThreadBreadcrumb` (`substrate/seams/thread.py:1-31`, `interfaces/research/api/thread.py:164-188`), which lane A renames **trail**; `feedback_threads`, which stay "comment thread" |
| project | the data noun for a workstation | Speak `interview_projects` (`substrate/graph/schema.py:322-337`), which is never reused |
| workstation | the UI noun for a project | code names |
| branch | a durable parent → child **dependency** (§1.3) | a tab |
| island | a lane A presentation state of a thread | any backend or event name: it names the html_projection data island (`services/html_projection/island.py:1-55`). Payloads say `selection`. |
| companion document | the derived data: per project the **companion tab**, which the cockpit shows as the right pane's **Findings** tab (rev 7, C4; S7), and per evidence document the **companion rail** | the bare word "companion" in code, which already carries five meanings (Q-A3, §1.12) |
| document fork | a derived-asset revision (§1.11) | a style fork, a `documents` row, or source merge. The one exception (rev 8, §1.11a) is a reformulation's **reader view**: a `documents` row that only projects the current revision, is never written on its own, and always takes its source's live gate. |
| reformulation (rev 8, C6) | a derived asset made from a source asset by prompt (§1.11a) | a copy of the source, or a new work of the operator's |
| thread merge | an evidence pack plus a `merged_from` lineage (§1.10) | |
| flag | a question-family event with `intent` and `actor` (§1.13) | feature flags or `*.flagged` actions |

### 1.1 Corrections to Part 2 and to the header guardrail (these are facts on main)

1. **2.3, anchor.** `passage_research` does not anchor by text quote and position. It anchors by page: `passage:<doc>:p<page>` (`substrate/books/passage_research.py:44-56`). The anchor is defined in §1.4, and `passage_id` stays a legacy read path.
2. **Header guardrail and 2.6, fork lineage.** HTML projections have no fork lineage. The only lineage is the style parent (`interfaces/research/api/style_routes.py:133-200`). A document fork is a derived-asset revision (§1.11). `create_document_version` (`substrate/research_bridge/versioning.py:72`) is **not** reused: it inserts a `documents` row that inherits the source's content class, which the derived-asset boundary forbids.
3. **2.2, branch record.** Today the branch record is `investigation.spawned_from`, written into the **child's** log after its start. Its `parent_event_id` is never filled (`substrate/schemas/events.py:2456-2473`). §1.3 adds the parent-side record.
4. **2.4 and 2.8, `capped`.** On main, `capped` is a refusal **before** start: the ACU gate (`app.py:2696-2705`) or, per §1.13, the daily-cap reserve. Part 2 now names it `refused_capped`. It is a response and an inbox item, not a stored thread state. A run that a ledger halts mid-flight reads `stopped`.

### 1.2 Thread (= investigation)

**Type `ThreadSummary`.** EXTEND `InvestigationSummary` (`app.py:543-560`), which has 8 fields today, and the codegen in `apps/reading/src/generated/types.ts`.

| Field | Source |
|---|---|
| `thread_id` | the `investigation_id` |
| `title` | NEW optional start-payload field, plus a typed rename event; defaults to the start question |
| `kind` | NEW: `research \| cascade_session \| cascade_leaf \| reading \| dialogue \| reformat` (`dialogue` and `reformat` rev 7; S2). `read-spin`, `__sidecar__`, `__operator__` and `reformat:<generation_id>` are attribution buckets and are never listed as threads. |
| `state` | derived; see below |
| `owner_user_id` | NEW on every launch, from `request_owner_user_id` (`interfaces/research/api/settings_models_admin.py:229`); today it is set only for BYOT (`events.py:2425`) |
| `project_id?` | NEW start-payload field (= `workstation_id`) |
| `document_id?` | EXISTS on the event envelope (`events.py:4568-4580`) |
| `anchor?` | NEW (§1.4) |
| `parent_thread_id?` | EXISTS as `parent_investigation_id` (`app.py:457`) |
| `merged_from[]` | NEW (§1.10) |
| `model` | EXISTS as `model_choice` on `InvestigationStartRequest` (`app.py:441-488`) |
| `spend_cents \| null` | EXTEND (rev 3). The current cost source is `cost_usd_total` × 100 (`app.py:543-560`). Nullability while the trajectory is incomplete is new behaviour. |
| `last_activity_at` | NEW: derived from the newest event's `emitted_at` |
| `stop_reason \| null` | NEW (rev 6, R5-4): set only when `state` is `stopped`; see **State** |
| `excerpt` | NEW (rev 6): the thesis excerpt as a `GatedText` (below) |

**Counts (answers the audit's claim-count gap).** `claim_count` and `source_count` are NEW. They are derived from the thread's trajectory, not the research-artifact body, which carries no claims:
- `claim_count` is the number of `supporting_claims` across the thread's `evidence.retrieve.delivered` events that pass `evidence_payload_intact`.
- `source_count` is the number of distinct documents those claims' chunk and edge pointers resolve to.

Both are `null` when `trajectory_read` reports the log incomplete, and neither is ever `0` for an unknown.

**Gated content, one shape (rev 5; composed in rev 6).** Every piece of rights-bearing text any route returns is a `GatedText`:
- `text | null`
- `gate: served | cite_only | withheld`
- `reason | null`: `unresolved | not_servable | lineage_unreconciled`
- `source_refs[]`: every pointer the text came from (the event, chunk, edge or synthesis pin, plus the document it resolves to when it resolves), each carrying its own `gate` and `reason`
- `origin`: `source | operator | generated | unsourced` (rev 8.2; `unsourced` rev 8.8). It is `source` for text drawn from sources, `operator` for operator-authored text, and `generated` for model-written text that no source supports and the connective validator admits (§1.11a).
  - `unsourced` (rev 8.8) is model-written text with no source that the validator did **not** admit. It is always `unsupported`: served to its owner with that mark, and it holds export back (§1.11). It is never labelled "Generated".

The shape is discriminated (rev 6):
- `served`: `text` is set and `reason` is null.
- `cite_only`: `text` is null and `reason` is `unresolved` or `not_servable`. A citation stands in for the text: the pointers are shown, the words are not.
- `withheld`: `text` is null and `reason` is any of the three. Nothing stands in for the text.

**Which gate (rev 6).** It depends on what the text is:
- **Quotation.** A quotation of source items, such as a pack item from a retrieval's claim or a hunk built from such items, is `served` when every source is resolved and servable. Otherwise it is `cite_only`: `unresolved` if any source is unresolved, and `not_servable` if not.
- **Synthesis.** A synthesis over a thread is decided by the excerpt gate, `build_body._excerpt_cleared` (NEW on the wave-5 export branch, not on main): `served` when it clears, `withheld` otherwise. That covers the thesis excerpt, an archived synthesis and a companion entry drawn from an artifact body. A synthesis is never `cite_only`, because no single citation stands in for it.
- **No evidence.** Operator-authored text is `served` with no refs and `origin: operator`. Evidence-derived text whose refs cannot be recovered is `withheld · unresolved`.
- **Generated (rev 8.2, §1.11a).** A sourceless span of a reformulation is `served` with `origin: generated` and `source_refs: []`.
  - It may not state a claim. The invariant that every claim cites chunks holds, so generated text is connective or framing text only.
  - **`generated` is earned (rev 8.5; closed set rev 8.6).** The server's connective-text validator (§1.11a) decides it. From rev 8.6 that validator admits only a closed set of non-assertive templates. Leaving out a ref never earns it: any sourceless text the validator rejects is `unsupported`.
  - A span that states a claim and cannot cite is `unsupported` (§1.11a). It is never passed off as generated.

**Mixed sources (rev 6).** When one text draws on several sources or parts, the most restrictive gate wins: `withheld` over `cite_only` over `served`. The `reason` comes from the most restrictive part; when parts at that gate disagree, `lineage_unreconciled` wins over `unresolved`, which wins over `not_servable`. `source_refs[]` keeps every pointer with its own gate, so a reader can show which source held the text back.

**Where it is composed (rev 6, R5-2).** These field names are binding:
- `excerpt` on `ThreadSummary` and on the research-artifact body. That is EXTEND: the body's `synthesis_excerpt` string and `synthesis_withheld` boolean (`substrate/research_artifact/schema.py:36-37`) become projections of it.
- `answer` and `context[]` on an ask turn (§1.8)
- `content` on every `RightsGatedPack` item and merge-preview item (§1.10)
- `insert` on every merge-draft hunk (§1.11)
- `content` on every companion-document entry (§1.12)
- `content` on every span of a reformulation (`GET /derived-assets/{id}/revisions/{rev}/spans`, §1.11a; rev 8.2)

**Excerpt marker (rev 4, R4-2; a projection since rev 6, R5-1).** The rev-4 `excerpt: {state, reason?}` marker is no longer a separate field. Wherever a reader was built against it, it is computed from the excerpt's `GatedText`:
- `state` is `served` when `gate` is `served`, and `withheld` otherwise, with the same `reason`.
- The body's `synthesis_withheld` is `gate != served`.

The excerpt is a synthesis, so its gate is only ever `served` or `withheld`. The marker and the gate therefore never disagree.

**Agent tab kinds (rev 7; S2).** The right pane's registry shows five kinds, each a view of one thread of a §1.2 `kind`:
- **research:** a `research` or `cascade_session` thread.
- **dialogue:** a `dialogue` thread. It is NEW, created by `POST /investigations {kind: dialogue, question?}` with no research run. It holds only §1.8 conversation turns (`thread.turn`), so an agent conversation keeps its process like any thread.
- **reformat:** a `reformat` thread. Its log records the prompt, the generation id and, from rev 8 (§1.11a), the derived-asset revision. The derived text is the derived asset, and `reformat:<generation_id>` is never a thread id.
- **diligence:** a `research` thread whose start carries a diligence flag origin (§1.13).
- **island:** a `research` thread spawned from a selection. `island` is a UI registry name only, and payloads say `selection` (§1.0).

**Openable document refs (rev 7; S1).** A `source_ref` that resolves to a document carries `document_id`, and carries `anchor` (a §1.4 `BranchAnchor`) whenever the text names a passage. A client can then open it as a left tab whose `branch_origin` is that passage. This applies to every `GatedText` a thread returns, including §1.8 answers.

**State.** One server helper keyed by `kind` replaces the three independent derivations: `app.py:2902-2990`, `app.py:3001-3200` and `apps/reading/src/hooks/useInvestigation.ts:123-162`. Its outputs:
- `queued`: start requested, not yet running
- `running`
- `needs_you`: a pending cascade spend approval
- `done`: `investigation.completed` with no stop outcome
- `failed`
- `stopped`, with `stop_reason` (rev 6, R5-4) read from the terminal record:
  - `user`: `investigation.completed` with `outcome: stopped` (`app.py:3133`)
  - `cancel`: the same event with `outcome: cancelled`
  - `budget`: a research budget halt, `investigation.chase_halted` with `budget_exceeded` or the runner's `aggregate_budget` (`app.py:3141-3144`; `runtime/research_runner/host_local.py:247,320`)
  - `cap_reached` or `cap_overshoot`: NEW `investigation.cap_halted` (§1.13)
  - `null` when the terminal record carries no reason, as in older logs; lane A then shows a bare `stopped`

  A chase halt for `depth_reached`, `duration_reached`, `no_open_questions` or `chase_disabled` ends the chase, not the thread, so the helper reads the thread by its own completion. Main's list reader turns every chase halt into `stopped` (`app.py:3141-3144`); the helper corrects that.

A `reading` thread has no terminal event, so it reads `idle`, never "working". Today the rail shows "working" forever: see `ReadingCompanion.tsx:117-120` together with the status derivation in `useInvestigation.ts:123-162`, fed by the non-terminal reading events of `sourceRead.ts:44-90`. `merged_into(thread_id)` comes from the merge record (§1.10).

**Endpoints.**
- `GET /investigations`: EXTEND (`app.py:3001`) with filters `project_id`, `document_id` (envelope document plus passage links through `researches_for_passage`, `passage_research.py:158`), `kind`, `state` and `parent_thread_id`. It must also enumerate sealed `.parquet` logs; today it lists only `.jsonl` (`app.py:3068`).
- `GET /investigations/{id}`: EXISTS (`app.py:2902`).
- `GET /trajectory/{id}`: EXISTS (`app.py:2608-2620`). These are the process steps: `process_steps[]` is a projection of the trajectory, never a second store.
- `WS /ws/events?investigation_id=`: EXISTS (`app.py:4959-4985`).

**Integrity (shipped in B0 for parents; ids in W1).**
- `POST /investigations` refuses a parent that has no stored log, answering `422 parent_investigation_not_found`. This shipped with B0 at `6e395c0c8`.
- It must also refuse a client-supplied `investigation_id` that already has `investigation.start_requested`, except an exact replay (the `claim_owner_launch` pattern, `app.py:2760-2789`). House replays are handled on the wave-5 stack.
- Owner scoping of the parent is pre-multi-user work (§1.15).

### 1.3 Branch (lane B step B0; shipped at `6e395c0c8` on the wave-5 export branch)

**Event.** `investigation.branched` (`InvestigationBranchedPayload`, v41) is written into the **parent's** log, strictly, as the **last step before** the child's first event. If the write fails, the child does not start.

Payload:
- `child_investigation_id`
- `via`: `chase | cascade_leaf | sub_question | watch_for_later | passage_spin | reserved_launch | api`
- `origin?`: `{kind: footnote|reference|citation|selection|research|manual, document_id?, anchor?}`
- `spawn_context`
- `question_id?`

The child's `investigation.spawned_from` stays, with `parent_event_id` set to the branch event's id.

**What a branch means (rev 2 correction).** A branch is a durable **dependency**: from that point the parent depends on the child. It is not proof the child ran; whether the child ran, and how it ended, is the child's own log. The export gate therefore treats a branched child with no readable log as an unresolved dependency and withholds. Writing the branch last means only a crash or a failed child write can leave a branch without a child.

**Launch identity and abandonment (rev 3; shipped on the wave-5 export branch).** A launch is identified by `(child_investigation_id, branch_event_id)`. The order is:
1. validate the parent;
2. record the branch;
3. charge;
4. write the child's first event.

`investigation.branch_abandoned {child_investigation_id, branch_event_id, reason: capacity_refused}` is written **only** by the request that wrote that branch, and **only** after a refusal that precedes the child's first event in that same request. That request is the proof the child never started. It cancels exactly its own `branch_event_id`: a retry that branches again is a new, live dependency.

A branch orphaned by a crash between the branch and the child's first event is **never** abandoned automatically. The logs cannot tell it from a started child whose log was later lost, so it stays a live, unresolved dependency and fails closed. Clearing it is an operator reconciliation, recorded with the same event and an attesting `reason`, W1.

**Reservations (rev 3; shipped).** A reservation is written into the reserved id's **own** log as `investigation.reserved {parent_investigation_id, question_id}` (strict), before the parent's `question.escalated_to_research`.
- A reserved child that never runs still has a readable, evidence-free log, so it does not withhold.
- A reserved child whose log is missing was lost, not unlaunched, so it withholds.
- `POST /investigations` into a reserved id takes the reserving parent, or answers `409 reservation_parent_mismatch`, and branches with `via: reserved_launch`.
- Reserved-only logs are not listed as threads, and `GET /investigations/{id}` answers `not_found` for them.

**Spawn sites that write it (shipped):**
- `POST /investigations` with a parent (`interfaces/research/api/app.py`)
- the watch-for-later launch
- Loop One's autonomous chase (`orchestration/loop_one/orchestrator.py:2354-2386` on main), which halts with `branch_not_recorded`
- both research runners' `start()` for cascade leaves: `runtime/research_runner/host_local.py`, `runtime/remote_exec/runner.py`, launched from the cascade launch block around `orchestration/cascade_session.py:169`
- spin-research, which writes into `read-<documentId>` with origin `selection` and `page_index`

**Legacy lineage (rev 3).** The gate still reads the older records: forward child keys in parent events, and the backward `spawned_from` / start-payload `parent_investigation_id` scan. A branch is not the only authority.

For a parent whose trajectory predates B0, dependency completeness cannot be proven: "no such child" and "a child whose only record is gone" look alike. That is a fail-closed question, and it is recorded as **operator call #6** in `docs/decisions/audit-wave5-open-calls.md`.

The rule (rev 4; W1). **Withholding is mandatory** for every pre-B0 parent until it is reconciled; only the **excerpt** is withheld, not the notes or the artifact. Reconciliation takes two separate steps, and neither is sufficient alone:
1. **Backfill.** `tools/backfill_branches.py` writes `investigation.branched` into the parent from every lineage record still readable, then writes `investigation.lineage_backfilled {backfill_run_id}`. This does **not** clear the withhold. A scan of surviving records cannot prove that none was lost.
2. **Attestation.** The operator attests that no event log was deleted or truncated before the backfill. The evidence is an event-store audit: no log removal outside sealing, and every sealed Parquet still matching its source counts. The attestation is recorded per backfill run as `investigation.lineage_attested {backfill_run_id, attested_by, basis}`, and only the stamp plus its attestation clears the withhold.

Without an attestation, the legacy excerpts stay withheld. That is the honest state when completeness cannot be established.

**Tab mirror.** A tab spawned from research sets `parent_tab_id` to mirror the branch edge. Pruning or closing a tab never touches a branch.

### 1.4 Anchor (answers Q-A4)

**Store (rev 8; sibling-stacks §3.6).** The durable anchor is `anchored_highlights` (EXISTS on main since #3425, `substrate/books/highlights/schema.py`).
- The `anchor_id` (`ahl-…`) is the handle a `BranchAnchor` may carry.
- Its stored normalization, node hash and offsets map onto `source_locator`.
- Its servability CHECK already keeps a quote only when the document is servable at pin, which is the cite-only rule for anchors.
- **Status mapping:**
  - `active` → `resolved`
  - `drifted` → `ambiguous`, until a remap resolves it
  - `orphaned` → `unresolved`
- The remap route stays beside the shipped `/books/{id}/anchors*` routes.
- Every anchor route is document-scoped (LB-11, #3524).

**Type `BranchAnchor`** (shipped in v41; the same shape serves every anchor):
- `document_id`
- `source_locator?`: `{start, end, text_sha256}`, the `TextLocator` shape (EXISTS, `substrate/contracts/html_projection.py:71-88`)
- `region_id?`: a `RegionStore` region (EXISTS, `substrate/reading/regions.py:19-89`; it has no writer today)
- `quote?`, `prefix?`, `suffix?`: the `NodeTextAnchor` pattern (EXISTS, `substrate/feedback/domain.py:24-71`)
- `page_index?`: the legacy `passage_id` read path

`source_locator` is the durable key: `region_id` embeds the projection id, so it is per-projection.

**Remapping (rev 3: NEW; the `AnchorMapping` shape EXISTS at `substrate/contracts/html_projection.py:90-119`, the operation does not).** `POST /documents/{id}/anchors/remap {anchor, from_text_sha256}` returns `{status: resolved|ambiguous|unresolved, anchor?, candidates[{anchor, score}]}`. The procedure:
1. If the span hash still matches the current canonical text, the result is `resolved`.
2. Otherwise, find the exact `quote` with its `prefix` and `suffix` in the current text. One match is `resolved` at the new offsets; several are `ambiguous`, with those candidates.
3. Otherwise, find `quote` alone. One match is `ambiguous`, since the context changed; none is `unresolved`.

Choosing a candidate writes `anchor.resolved {anchor_ref, chosen_anchor}` on the owning thread, so the resolution persists. Part 2 designs all three states.

The anchor is carried on the start payload, on `investigation.branched.origin`, and on flags. `question.identified` already carries `anchor_region_id` (`events.py:1260-1264`).

### 1.5 Project and workstation registry (answers Q-A5)

**Storage.** EXTEND `write_folders` and `write_folder_members` (`substrate/write/folders.py:55-78`) into the project registry. There is no new projects table.
- **Folder fields:** `kind` (`project \| reading`), `title`, `order`, `pinned`, `archived_at`, `primary_document_id?` (for `kind: reading`), `created_at`, `updated_at`.
- **Owner:** `owner_user_id` becomes request-derived and enforced. Today it defaults to `__operator__`, and the routes take no identity (`interfaces/research/api/write_routes.py:315-330`).
- **Members:** gain `member_kind`: `node | investigation | document | deliverable`. The block-search base query stays node-only (`substrate/write/block_search.py:118-124`).
- **Events:** the `Folder*` payloads that `folders.py:47-52` notes were never registered become typed events.
- **Filing:** `documents.investigation_id` filing (`events.py:458-465`) and `topic_slug` (`app.py:454`) reconcile into membership.

**Standalone book (Q-A5).** A standalone book is `kind: reading` with a `primary_document_id`, promoted in place to `kind: project`. The id, members and threads are unchanged, and there is no separate book entity.

**Routes.** NEW `/projects`: `GET` (list), `POST` (create), `PATCH /{id}`, `POST /{id}/members`, `DELETE /{id}/members/{member}`, and `GET /{id}`. `/write/folders` stays as Write's alias over the same rows.

**Aggregates (rev 2).**
- `thread_counts` is `{running, needs_you, done_unseen}` over `GET /investigations?project_id=`.
- **Visibility has one authority (rev 3):** NEW `thread_seen` rows `(owner_user_id, thread_id, seen_through_position)` in the §1.6 per-account store. They are set by `POST /investigations/{id}/seen {through_event_id}`: the server validates that the event is in the thread's trajectory and stores its **position** there, since event ids are not ordered. The position is monotonic.
- `done_unseen` means the thread's terminal event sits after `seen_through_position`. Inbox `seen_at` (§1.13) is separate and never drives these counts.
- **Spend attribution (rev 3):** every ledger hold and every settlement (§1.13) records `thread_id` and `project_id` at the time of the charge.
- `spend_today` is `{cents, currency: "USD"} | null`. It sums today's settlements with that `project_id`, and is `null` when the ledger is unreachable, never `0`.

### 1.6 Tab tree (answers Q-A1: server-side per account)

**Storage.** NEW table `project_tabs`, one row per `(owner_user_id, project_id, mothership)`:
- `tree`: JSON, every node with the Part 2 §2.2 fields. Each node gains `side: left | right` (rev 7, C2/C4): left nodes are document tabs and right nodes are agent tabs (§1.2).
  - One tree per mode (`mothership`) holds both of that mode's panes, so a project switch swaps both panes of the current mode (T8; R7-3).
  - Research and reading keep separate trees: the operator ruled T9 as one tree per mode (2026-09-26).
  - The numbering registers below cover both sides.
- `active_tab_id`, now `active: {left, right}` (rev 7). Each is a `tab_id` on that side, or null.
- `next_child_index` (rev 6, R5-5): `{<parent tab_id, or "root">: n}`. Each counter is monotonic, and the server maintains it; it is never taken from the client.
- `retired`: superseded by the retirement table below (rev 7). Allocation never reads retirements.
- `version`
- `updated_at`

It is written through `connect_write` in the API process, so the single-writer invariant holds. Tabs are navigation state, not provenance, so they are a row, not events. `next_public_number` lives on a separate `(owner_user_id, project_id)` row, because public numbers are workstation-wide.

**Retirements (rev 7).** A tab that leaves the tree keeps its complete node in NEW `project_tab_retirements (owner_user_id, project_id, mothership, tab_id, closed_at, close_mode, node_json, restored_at)`, primary key `(owner_user_id, project_id, mothership, tab_id, closed_at)`:
- `node_json` is the whole Part 2 §2.2 node as it stood when it left the tree: `tab_id`, `public_number`, `hier_number`, `parent_tab_id`, `branch_origin`, `kind` and its ref, `title`, `mothership`, `pane`, `side`, `opened_by` (when the origin is `agent`), `child_order`, `last_visited_child_id` and `pruned_at` (`side` and `opened_by` rev 7, R7-2). Restoring from it needs nothing the client does not already hold, an agent-opened tab included.
- `close_mode` is `close`, `prune` or `lift_children`. A pruned subtree writes one row per node it removes.
- The PUT that drops a node writes its row in the same `connect_write` transaction as the snapshot. The server finds dropped nodes by comparing the accepted tree with the previous one. This diff records history; number ownership never reads it (the registers below do).
- A tab closed, restored and closed again has one row per close. The latest row with `restored_at` null is its restore descriptor. A PUT that brings the `tab_id` back sets `restored_at` on that row in the same transaction.
- **Write discipline (rev 8.6).** A row is inserted once per close, and rows are never compacted or deleted, so history and numbers stay consistent.
  - `closed_at`, `close_mode` and `node_json` never change after insert.
  - `restored_at` is the only mutable column. It moves exactly once, from null to the restoring PUT's time, and never back.
  - `closed_at` is unique and strictly increasing per `(owner_user_id, project_id, mothership)`, so the primary key cannot collide and `?before=<closed_at>` pages exactly.
    - The PUT gives its dropped nodes consecutive microseconds, in tree order, starting after the scope's latest `closed_at`.
    - When the clock has not moved past that time, the first close takes the latest `closed_at` plus one microsecond.

**Number register (rev 6, R5-6).** Every issued number is kept in NEW append-only tables. A row is written once, in the same transaction that issues its number, and is never updated or deleted:
- `tab_public_numbers (owner_user_id, project_id, public_number, tab_id, mothership, issued_at)`. The primary key is `(owner_user_id, project_id, public_number)`, with `UNIQUE (owner_user_id, project_id, tab_id)`.
- `tab_hier_numbers (owner_user_id, project_id, mothership, hier_number, tab_id, issued_at)`. The primary key is `(owner_user_id, project_id, mothership, hier_number)`, with `UNIQUE (owner_user_id, project_id, mothership, tab_id)`.

Every reuse check reads these registers, never a diff against the previous snapshot. A tab dropped from a snapshot therefore never frees its numbers.

**Branch-origin kinds (rev 7; S1).** A node's `branch_origin.kind` is `footnote | reference | citation | selection | research | manual | agent | derivation`.
- `agent` is a document an agent tab opened. It requires `opened_by: {thread_id, agent_kind}`, and the `anchor` of the passage the agent's reply named when it named one. That anchor is what lets `prefix+u` return there.
- `derivation` is a reformat result (C6, rev 8).
- Both are navigation state on the tab node. Neither writes `investigation.branched`, because no child investigation starts.
- The PUT refuses a node whose kind is outside the set, or an `agent` node without `opened_by`: `422 tab_origin_invalid`.
- The client allocator is `allocate(projectId, tabId)`, idempotent per `tab_id` (S3; the route below).

**Addressing (rev 2).**
- `public_number` is allocated **server-side, workstation-wide**, from `next_public_number` on a separate `(owner_user_id, project_id)` row, and registered to its `tab_id` in the same transaction (rev 6). It is monotonic and never reused, even after close, which is herdr semantics.
- `hier_number` (rev 3, R3-5; rev 6, R5-5) is computed client-side as `<parent's hier_number>.<k>`. Root tabs count under the key `root`.
  - `k` starts at the parent's `next_child_index` in the latest snapshot and rises by one for each further local spawn under that parent.
  - On the PUT, the server accepts a new hier number only if `k` is at least that counter and the number is unregistered. In the same transaction it registers the number to the tab and moves the counter past the largest accepted `k`.
  - The number is **final once accepted**.
- On a concurrent spawn under the same parent, the losing device gets a 409, rebases onto the new snapshot and recomputes its pending spawns' numbers **before** they are accepted. Every local spawn survives with a number unique under its parent.
- A closed or pruned node keeps its numbers: the registers still name its `tab_id`, and `retired` carries its restore descriptor (rev 6).
- **A pending spawn whose parent closed remotely (rev 5).** At rebase, the pending child re-attaches to its **nearest surviving ancestor**, or becomes a root if none survives. It keeps its `branch_origin`, its ref and its thread, and it takes a fresh `hier_number` under its new parent; numbers are final only once accepted. Restoring the closed parent from history later does **not** move the child back.
- **Restoring vs reusing (rev 3, R3-1).** Restoring the **same** `tab_id` from history reclaims its own retired numbers. A **different** `tab_id` may never take a retired number, which is what "reuse" means and why it is refused.
- `active: {left, right}` is persisted per mothership (rev 7).

**Routes.**
- `GET /projects/{id}/tabs/{mothership}` returns `{tree, active: {left, right}, version, next_child_index, retired: [{closed_at, close_mode, node}]}` (`active` rev 7, R7-1) (rev 4; `next_child_index` rev 6; complete nodes rev 7).
  - `retired` holds the 200 most recent unrestored retirements, read in the same transaction as the tree, so it is consistent with `version`.
  - Older retirements page through NEW `GET /projects/{id}/tabs/{mothership}/retired?before=<closed_at>&limit=`, which answers from the same table.
  - "Restore from history" PUTs the retired `node` back unchanged, with its own numbers. The number registers accept it because they name its `tab_id`.
  - The 409 on a stale PUT returns the same shape as `current`.
- `POST /projects/{id}/tabs/{mothership}/allocate {tab_id}` returns `{public_number}` (rev 6, R5-6). It is idempotent per `tab_id`: a repeat for a tab that already holds a number returns that number, so two devices retrying one unnumbered tab burn nothing.
- `PUT /projects/{id}/tabs/{mothership}` takes `{tree, active: {left, right}, expected_version}` (rev 7, R7-1). It answers a 409 in two cases, and both carry the GET shape as `current`, so the client rebases the same way (rev 6):
  - `409 {reason: version_stale, current}` on a stale version.
  - `409 {reason: number_conflict, tab_id, current}` when a node carries a number the register gives another tab, or a new hier number whose `k` is below its parent's counter.

The client rebases on a 409 (Part 2's rebasing flow): refetch, replay local ops, drop ops on tabs closed remotely. A restored tab keeps its own registered numbers, because the register names its `tab_id`.

**Wire precision (rev 8.7; built by LB-2, `substrate/projects/tabs.py`, `interfaces/research/api/project_routes.py`).**
- **`tree`** is exactly `{nodes: {<tab_id>: node}, root_order: [tab_id]}`. It holds no in-tree history, retired numbers or counters: `retired[]` and the top-level `next_child_index` carry those.
- **A node** carries only the Part 2 §2.2 fields:
  - `tab_id`, `parent_tab_id`, `side`, `kind`, `ref`, `title`, `mothership`, `pane?`, `public_number`, `hier_number`, `branch_origin?`, `opened_by?`, `child_order`, `last_visited_child_id?` and `pruned_at?`.
  - Any other field is refused, so navigation state cannot smuggle content.
  - `pruned_at` is set only on a retired node. A restore PUTs that node back unchanged, `pruned_at` included, and the server clears it as the tab reopens.
  - **Unchanged means (rev 8.9):** the restored node matches the retired one on `side`, `kind`, `ref`, `branch_origin` and `opened_by`, or it is `422 tab_tree_invalid` naming the changed fields.
    - It may differ in where it hangs (`parent_tab_id` and `child_order`, for the nearest-surviving-ancestor rule), in `last_visited_child_id`, and in a refreshed `title` or `pane`.
    - The registers already bind its numbers. `pruned_at` on a tab that is not being restored (one that is already open, or has no unrestored retirement) is `422 tab_tree_invalid` (rev 8.8).
- **Kinds by side:**
  - Left: `reader`, `document`, `research`.
  - Right: `research`, `dialogue`, `reformat`, `diligence`, `island`, `findings`, `flags`, `block`.
  - **`research` is on both sides (rev 8.8; lane A found it while building the adapter).** On the left it is a deep research spawned from a document, opened as core material. R3's own words list "deep researches spawned from a document" among the document-level tabs, and §2.2 has a child inherit its parent's side. On the right it is a research as an agent you talk to (R6, R18). `island` stays right.
- **Structural checks,** all `422 tab_tree_invalid`:
  - Each key equals its node's `tab_id`, which is 1 to 64 of `[A-Za-z0-9_-]`.
  - A parent is an open tab. `root_order` lists every root once, and `child_order` lists every child once. There is no cycle.
  - No number appears twice in one snapshot.
  - `active.left` and `active.right` are null or an open tab on that side.
  - A node's `mothership` is the route's.
  - At most 1,000 tabs and 1,000,000 bytes of the tree's canonical compact UTF-8 JSON (`ensure_ascii` off, no whitespace between tokens), so the bound does not depend on the client's formatting (rev 8.8).
  - Depth is unbounded, as Part 2 §2.2 says. The 1,000-tab bound limits it (rev 8.8).
- **Error bodies** are top-level JSON, so the client narrows on `reason`:
  - `409 {reason: "version_stale", current}` and `409 {reason: "number_conflict", tab_id, detail, current}`.
  - `422 {reason: "tab_origin_invalid" | "tab_tree_invalid", tab_id, detail}`. `tab_tree_invalid` is the reason for every structural refusal. Both 422s are lane-A bugs (Part 2 §2.2).
  - `404 project_not_found` covers a missing project and another owner's alike. `404 mothership_unknown` covers an unknown mode key.
- **A 200 on the PUT** answers the new snapshot in the GET shape.
- **Filled-in numbers.** A node sent with `public_number: null` whose `tab_id` allocate has registered is stored and returned with that number, so a numbering tab converges.
- **Invented or foreign numbers.** A `public_number` that allocate never issued is `422 tab_tree_invalid`. A number the register gives another tab is `409 number_conflict`. A tab whose number was allocated in another mode's tree is `422 tab_tree_invalid`.
- **Hier numbers.** A new tab's `hier_number` must be `<parent's hier>.<k>` (or `<k>` for a root). Each new `k` is checked against the counter of the **accepted** snapshot, never against one this PUT has already moved, because siblings arrive in `child_order`. An accepted tab's `hier_number` is final: changing it is `422`, even after a lift moves the tab under another parent.
- **`close_mode` is read off the diff:**
  - `lift_children` when any child of the dropped tab stays;
  - `prune` when it took children with it, or went with a pruned parent;
  - otherwise `close`.

  A pruned retirement's `node.pruned_at` is its `closed_at`.
- **`GET …/retired?before=&limit=`** (limit 1 to 200) answers `{retired: [...], next_before}`. `next_before` is null on the last page, including a page that is exactly full: the server reads one row past the page to know (rev 8.8).
- **One snapshot per GET (rev 8.8).** The GET reads the tree and its 200 retirements in one read transaction, so a PUT committing between them cannot pair version N with a retirement from N+1.
- **Push.** After an accepted PUT commits, the server broadcasts `project.tabs.version_bumped {project_id, mothership, version}` on `/ws/events`, with the envelope's `investigation_id` set to `project-<project_id>`. It is broadcast only and never appended to a trajectory, since tabs are rows (§1.7). A refused PUT broadcasts nothing.
- **`/write/folders` is owner-scoped too.** Create and list use the request's owner, and adding or removing a block on another owner's folder is `404 folder_not_found`. Write's node reads count only `member_kind = 'node'` members.

**Per-account store family.** `project_tabs`, `thread_seen`, inbox `seen_at` (§1.13) and reading-position projections (§1.14) are all per-account rows behind the API. None of them lives in `localStorage` or `sessionStorage`.

### 1.7 Push (answers Q-A2: WebSocket, not SSE)

The app streams over `WS /ws/events` with an optional `investigation_id` filter (EXISTS, `app.py:4959-4985`; `apps/reading/src/hooks/useEventStream.ts:72`). Cascade sessions additionally have SSE at `GET /research/sessions/{id}/stream` (`cascade_routes.py:1891`).

Only **broadcast** events reach the socket; `emit_typed` alone only appends (`books.py:2204-2208`). Every event Part 2 reacts to must be broadcast: thread state, branch, flag, consent, inbox, merge suggestion and tab-version bump. B0 broadcasts branches on the chase path. W1 wires the rest.

The socket is live-only: reconnect catch-up comes from the durable `GET /inbox?after=<cursor>` and `GET /investigations` (§1.13).

### 1.8 Ask this thread (C03: ABSENT on main)

**Tier 0 (W2): a conversational turn with the thread's context.** EXTEND `POST /thought-partner` (`app.py:6647-6733`), which today uses `investigation_id` only for attribution (`app.py:6704-6709`).
- It loads the addressed thread through the research-artifact context (`substrate/research_artifact/context.py`) and `distill_query`, rights-gated (§1.10).
- It persists each turn as a typed `thread.turn` event on that thread, following `read.book_answered` (`events.py:3965`; `books.py:2261-2473`).
- The route shape is `POST /investigations/{id}/ask {question, context_items[]}`, which returns the stream on `/ws/events`.
- **Answer (rev 6).** The turn's `answer` is a `GatedText` (§1.2).
  - The model receives only served text, so an answer is `served`, and its `source_refs` name the served items it was given.
  - `context[]` returns every item assembled for the turn as its own `GatedText`, including the cite-only and withheld ones, so the operator sees what the model was not shown.

**Tier 1 (W2/W3): a follow-up research run with the parent's context.**
- `POST /investigations` with `parent_investigation_id` and `continue_from_parent: true` writes the §1.3 branch.
- The Loop One handler, which today drops `spawn_context` and never reads the parent (`orchestrator.py:2082-2098`), loads the parent's rights-gated pack through `assemble_context_pack_with_reuse` (`substrate/context_pack/knowledge_reuse.py:752`).
- DRW's follow-up already stores into `st.follow_ups` and is never consumed (`host_local.py:457-466`). It becomes this path's first caller.

**Ownership note.** `/thought-partner` sits under PR #3278 (owner model) and codex-r15 (memory origin). Lane B edits it only after those land, or coordinates the hunks on the board.

### 1.9 Attached context and estimates

- **Context kinds.** EXTEND `ContextItem.kind` from `doc | insight` (`app.py:1318-1323`) to `doc | insight | thread | note`, and resolve the new kinds in `_compose_context` (`app.py:1348`) through the rights-gated pack of §1.10.
- **Launch payload.** EXTEND `InvestigationStartRequest` (`app.py:441-488`) with `context_items[]`. Unknown fields are silently ignored today, so the attach UI stays gated until this lands.

**Estimate (rev 2).** NEW `POST /investigations/estimate {question, model_choice, research_tier, context_items}` returns `{cents, basis, status: ok|unavailable, reason?}`. It computes from Midnight Oil's pricing (`substrate/midnight_oil/cost_estimate.py`, `TierPricing` at `:182`):
- the tier's role plan
- the chosen model's per-token rates
- the context items' token counts

`basis` names the model, the tier and the token assumptions. When a rate is missing or the model is BYOT with unknown pricing, `status` is `unavailable` with a reason; the answer is never `0`. Cascade spend-preview (`cascade_routes.py:810`) is a limit preview, not an estimator, and is not reused for this.

**Spin-research** gains `model_choice`. Today its body is page, text and export only (`books.py:2111-2258`).

### 1.10 Thread merge (2.5)

- **Merge.** A merge is an evidence pack over the member threads, plus lineage. It reuses `build_session_evidence_pack` (`orchestration/session_evidence_pack.py:195`), which accepts arbitrary `(investigation_id, sub_question)` pairs; every chunk carries `source_investigation_id`.

**Rights-gated pack (rev 3).** NEW adapter `RightsGatedPack`. `PackChunk` does not retain edge pointers, so items are built from the **source events** instead: each retrieval's `supporting_claims[]` with its `chunk_ids` and `edge_ids`, and each archived synthesis with its manifest pins. Every item carries all the pointers of the event it came from.

Each item passes the same resolver the excerpt gate uses:
- `resolve_pin_sources` and `resolve_synthesis_sources` in `services/html_projection/resolvers/substrate_refs.py`, which are **NEW on the wave-5 export branch**, not on main (lane A's citation note, rev 3);
- the gate itself, `build_body._excerpt_cleared`.

Every item carries `content: GatedText` (§1.2; rev 6, R5-2). It replaces R3-3's fields: the old `gate` is `content.gate`, and `cite_reason` is `content.reason`. The rules:
- A claim item whose sources are unresolved or not servable is `cite_only`: its pointers stand in for its text.
- An archived-synthesis item that fails the excerpt gate is `withheld`.
- Only gated output reaches the merge preview, model context (ask tiers and continuations), document drafts, exports and agent-facing trajectories.
- The same rule applies to trajectories served to agents.

**Preview.** NEW `POST /threads/merge/preview {thread_ids[]}` returns:
- `preview_digest` (rev 3): sha256 over each item's canonical `content` and the `content_class` of every document its pointers resolve to at preview time. The `content` is the `GatedText`, with `text` null unless served and its full pointer set (rev 6). Any change to content, provenance or rights re-keys the digest.
- `items[{item_id, content: GatedText, origin_thread_id}]` (rev 6)
- `conflicts[{claim_a, claim_b, reason}]`

Conflicts come from `supersession_candidates` (`schema.py:1186`; `supersession_routes.py:109,169`). The compose hash-conflict list is dead code (its hash includes the investigation id; RUN), and lane B removes it.

**Commit (rev 3).** `POST /threads/merge {thread_ids[], preview_digest, question, idempotency_key}` works as follows:
1. The server recomputes the rev-3 digest. On a mismatch it answers `409 preview_stale` and the client re-previews.
2. The merge operation is persisted **first** (rev 4): `thread.merge_started {merge_id, request_identity}` is written strictly into the new thread's own log.
   - `request_identity` = sha256(owner, sorted member ids, `preview_digest`, the reviewed conflict set, `question`), bound to the `idempotency_key`.
   - A reuse of the key with a different identity answers `409 idempotency_conflict`.
   - That record owns recovery.
   - The preview digest also binds the complete member set and the conflicts the user reviewed.
3. Every member must be owned by the caller.
4. Each member records `investigation.merged_into {thread_id, merge_id, preview_digest}` strictly, as a branch-family event. Then the merged thread's start event is written, carrying `merged_from[]`.
   - **Pending until committed (rev 4).** A member's `merged_into` is a **pending intent** until the merged thread's start event exists. Every projection (`GET /investigations/{id}`, the list, lane A's row state) shows `merge_pending(thread_id)`, or `merge_failed` after a refused commit, never `merged_into`, until then.
5. The merge **succeeds only when that start event exists**. If a member's record fails, the answer is 503 and nothing dispatches. A retry with the same `idempotency_key` resumes from `thread.merge_started`, writing only the missing member records. A partial merge never reports success.

Members are never mutated beyond that record.

**Suggestion.** NEW `thread.merge_suggested` is derived from continuous-research gap scoring (`GapEntry.investigation_ids`, `orchestration/continuous/scoring.py:58-119`, read-only because §7.4 freezes that file). It reaches you through the inbox and is never applied silently.

### 1.11 Merge into document and fork (2.6)

**Store.** `derived_asset_revisions` (EXISTS: `schema.py:1222-1357`, the CAS pointer `derived_asset_current_revisions`). Its **repository is NEW**.

**One canonical mapping (rev 2).** A Write deliverable is a derived asset, with `derived_asset_id = "write:<deliverable_id>"`. Every merge-into-document and fork goes through it. There is no second path to a Write document body.

**Initial revision and migration (rev 3).**
- **Initial revision.** The first operation on a deliverable writes revision 1 (`operation: create`): its current canonical HTML as bytes, its blocks mapped to evidence members as below, and the current pointer set.
- **Block → member mapping (rev 4; rev 6).** Each block contributes members:
  - **Evidence.** An evidence member pins one source: its projection, source asset, source document and their hashes. It records `use: quote` when the block shows the source's text, and `use: cite` when it shows only a citation marker (an accepted `cite_only` hunk). Members are deduplicated across blocks by `member_key` (below).
  - **Attribution.** `investigation_id` records the thread that found the source, and is null when the block names none, as for a document cited directly. Rights never read it, because the pin decides its own servability. A null shows as "no thread recorded" and is never filled with an invented id.
  - **User.** An operator-authored block with no evidence contributes a `user` member.
  - **Unresolved.** A block whose provenance is missing contributes an `unresolved` member, which withholds that revision's export.
- **Member table rebuild (rev 6, W3; replaces rev 5's partial list).** `derived_asset_revision_members` (`schema.py:1320-1337`) is rebuilt as a new table plus a copy, since DuckDB cannot alter constraints in place. Its columns:
  - Kept unchanged: `derived_asset_id`, `revision_id` and `member_index` (NOT NULL, ≥ 0), with the primary key `(derived_asset_id, revision_id, member_index)` and the foreign key to `derived_asset_revisions`.
  - NEW `source_kind`: `evidence | user | unresolved | generated | unsupported` (`generated` rev 8.2, `unsupported` rev 8.3), NOT NULL.
  - NEW `member_origin`: `recorded | legacy | attested` (`attested` rev 7, below), NOT NULL.
  - NEW `use`: `quote | cite`, set only for evidence.
  - NEW `block_id`: the html_projection block. It is set for `user` and `unresolved` members, and null for evidence, which is deduplicated across blocks.
  - NEW `unresolved_reason`: `no_provenance | projection_missing | source_missing | legacy_unverified` (`legacy_unverified` rev 7, below), set only for `unresolved`.
  - `projection_id`, `source_asset_id`, `source_document_id`, `source_sha256` and `hosted_html_sha256` become nullable. The existing 64-hex CHECKs still apply whenever a hash is set.
  - `investigation_id` stays nullable, as today.
  - NEW `member_key`, NOT NULL: sha256 of the canonical JSON of `[source_kind, use, projection_id, investigation_id]` for evidence, and of `[source_kind, block_id]` otherwise.
    - `UNIQUE (derived_asset_id, revision_id, member_key)` replaces `UNIQUE (derived_asset_id, revision_id, projection_id)`.
    - Two threads citing one projection, or one projection both quoted and cited, therefore stay distinct members.

  One CHECK per kind:
  - `evidence`: `use`, `projection_id`, `source_asset_id`, `source_document_id`, `source_sha256` and `hosted_html_sha256` are all set, and `block_id` and `unresolved_reason` are null.
  - `user`: `block_id` is set. `use`, every source column, `investigation_id` and `unresolved_reason` are null.
  - `unresolved`: `block_id` and `unresolved_reason` are set, and `use` is null. Each source column and `investigation_id` holds what is known, or null, never a guess.
  - `generated` (rev 8.2): `block_id` is set, and `use`, every source column, `investigation_id` and `unresolved_reason` are null. Its `member_key` is sha256 of the canonical JSON of `[source_kind, block_id, bite_id]`, which makes it one member per sourceless span.
  - `unsupported` (rev 8.3): the same columns as `generated`, with the same key form. It marks model text that states something its cited sources do not support.

  **Copy.** Main has no writer for these rows: only the DDL (`schema.py:1320-1337`) and `tests/test_derived_asset_schema.py` touch the table, so production is expected to hold none. The copy is lossless for any that exist:
  - Every column is copied as is, with `source_kind: evidence`, `use: quote` and `member_origin: legacy`.
  - `member_key` is computed from the copied values. The existing rows are unique per projection, so their keys are unique.
  - The revisions' `manifest_json` and `manifest_sha256` are immutable and are not rewritten.
- **Export gate over members (rev 6).** A revision exports only when every member passes:
  - A `quote` member's pinned source is servable.
  - A `cite` member's pin resolves. Citing a source that is not servable is allowed.
  - A `user` member passes.
  - A `generated` member passes. It carries no source, so it has no rights to check and gets no attribution share (rev 8.2).
  - An `unsupported` member **withholds** the revision's export, like `unresolved` (rev 8.3). A claim with no supporting source never leaves as if it were served. It clears only in one of two ways (rev 8.4):
    1. The operator deletes or rewrites the block.
    2. Evidence is attached whose **recomputed** support meets the threshold.

    Attestation establishes where text came from. It never establishes that a source supports a claim, so an attest call alone does not clear `unsupported`.

    **Attaching evidence (rev 8.5).** NEW `POST /derived-assets/{asset_id}/blocks/{block_id}/evidence {source: {document_id, anchor}, expected_revision_id, idempotency_key}`:
    - The source must be one the requester owns or may read, and it must be servable to them.
    - The call is bound to the block's current text hash.
    - It rescores each `unsupported` sentence of the block against the attached source's anchor span (per-sentence lexical support, above).
    - Sentences that now meet the threshold become evidence members, with their bite and join rows, through one `revise` with compare-and-set on `expected_revision_id`.
    - Sentences still below the threshold stay `unsupported`. The answer lists each sentence's score, so the operator sees exactly what still fails.
    - A key replayed with the same body returns the first result. `409 revision_moved` rebases.
  - An `unresolved` member withholds.
  - A `legacy` member withholds. A legacy manifest cannot show that it lists every source its blocks used, so this is the same fail-closed rule as §1.3's legacy lineage.
- **Legacy is cleared per block, never by an ordinary revision (rev 7).** Rebuilding members from the blocks would only restate whatever provenance those blocks carry, and that is exactly what a legacy revision cannot vouch for.
  - The first `revise` after a legacy revision carries one `unresolved` member with `unresolved_reason: legacy_unverified` for every Write block (by its stable Write block id) present in the last legacy revision. It carries the copied legacy evidence members forward unchanged.
  - A block's `legacy_unverified` member is removed only when one of three things happens:
    1. The block is deleted.
    2. The block's whole content is replaced by an accepted merge hunk (§1.11 flow), whose members are recorded.
    3. The operator attests the block's sources through NEW `POST /derived-assets/{asset_id}/blocks/{block_id}/attest {sources[], basis}`. This writes a typed `derived_asset.block_attested` event through `write_event_outbox` and replaces the member with recorded evidence members carrying `member_origin: attested`.
  - An edit to part of a legacy block keeps the member, because an edit cannot prove where the rest of the block came from.
  - The copied legacy evidence members leave the revision only when no `legacy_unverified` block remains.
  - `unresolved_reason` gains `legacy_unverified`, and `member_origin` gains `attested`.
- **Serve-time gate (rev 8.4).** Rights are rechecked every time body text is served, not only at export.
  - **Which responses.** Every response that carries deliverable body text is gated live: `GET /write/deliverables/{id}`, the html projection render, shared or public pages, and exports.
  - **The check.** Each evidence member is revalidated against its source projection or document's **current** gate at serve time.
  - **Composing each block.** Each block is composed by the §1.2 mixed-source rule:
    - A `quote` member whose source is no longer servable turns that block's quoted text into `cite_only`. The server builds the citation marker; the words are not served.
    - An `unresolved`, `legacy` or `unsupported` member withholds its block's text.
    - `generated` and `user` text is served.
  - **Two audiences.** The owner's editing view applies the owner-read gate, meaning what the owner may read (`serve_full_text_guarded(..., owner=True)`, `substrate/books/serve_guard.py:233`). Shared, public and export views apply the public gate.
  - **Caching.** A cached render is keyed by the fingerprint of its members' current gate states and is never served stale. A takedown or reclassification changes the fingerprint.
- **Migration.** From W3, **every** Write route that changes a deliverable body goes through the derived-asset repository as a `revise`. The existing Write mutation paths are migrated, not bypassed.
- **Atomicity.** One `connect_write` transaction writes the revision row, its evidence members, the CAS update of `derived_asset_current_revisions`, the idempotency record and the `write_event_outbox` row. All of them land or none does.

**Flow (rev 2).**
1. `POST /derived-assets/{asset_id}/merge-drafts {source: {thread_id} | {companion_entry_id}}` builds a draft from the source's rights-gated pack (§1.10) against the current revision. It returns:
   - `draft_id`
   - `base_revision_id`
   - `proposed_hunks[{hunk_id, hunk_digest, anchor, insert: GatedText}]` (rev 6, R5-2)
   - `evidence_manifest`
2. The hunks are a NEW block-level diff of canonical HTML against `base_revision_id`, keyed by html_projection blocks (rev 6 for the gating):
   - `insert.text` is the sanitized HTML, present only when `insert.gate` is `served`.
   - An accepted `cite_only` hunk becomes a citation marker that the server builds from `insert.source_refs`. It never becomes quoted text.
   - A `withheld` hunk can only be rejected. A review that accepts one answers `422 hunk_not_acceptable`.
   - `hunk_digest` is sha256 over the anchor and the canonical `insert`. After `revision_moved`, a decision carries over only to a hunk with the same digest.
3. `POST /merge-drafts/{draft_id}/review {accepted_hunk_ids[], rejected_hunk_ids[]}` returns a `review_id` bound to:
   - the owner
   - the accepted hunks
   - the sanitized bytes' hash, including any citation markers
   - the evidence manifest
   - the expected current revision and generation

   Each decision is a NEW typed accept/reject event, modelled on the supersession decisions (`supersession_routes.py:160-203`) and `AIActionApplied`/`Undone` (`events.py:3392-3452`), written through `write_event_outbox` (`schema.py:1361`) in the same transaction.
4. `POST /derived-assets/{asset_id}/revisions {review_id, acknowledgement, idempotency_key}` commits. This is the existing envelope (`substrate/write/derived_asset_boundary.py:21-23`); legacy fields answer 422.
   - `acknowledgement` is the literal `"new_revision"` (rev 3, R3-6).
   - A CAS refusal answers `409 revision_moved`, which lane A shows as `base_moved`. It atomically verifies that the current revision still equals the review's expected revision (CAS). On success it writes the new revision (`operation: revise`, `parent_revision_id`), which is the "forked" state; the original revision is untouched.
5. `GET /derived-assets/{asset_id}/revisions` returns the lineage.

**Targets and provenance.**
- **Deliverables.** Write deliverables are created from an investigation through `POST /write/deliverables/from-investigation` (`write_routes.py:590`); PR #3011 supplies the owner binding.
- **Blocks: EXTEND, correcting rev 1.** `POST /write/blocks` does **not** expose `investigation_id` or `parent_event_id` today (`write_routes.py:160-170`). W3 adds both as optional fields, each validated: the investigation must exist and be owned, and the event must belong to it.

**Source merge (corrected in rev 8.8).** The earlier text said that after #3432 its commit and restore are refused through `validate_commit_boundary`. That is false.
- **What is live today.** `validate_commit_boundary` (`substrate/write/derived_asset_boundary.py@d61e5256d`, "def validate_commit_boundary") has no production caller; only `tests/test_derived_asset_evidence_boundary.py` calls it.
- **Why that matters.** `POST /research/artifacts/source-merge/{preview,apply,commit,restore}` are live (`interfaces/research/api/artifact_routes.py@d61e5256d`, "@artifact_router.post(\"/artifacts/source-merge/"). Commit can rewrite a source body, against T6 ("merge never writes the source").
- **LB-33 retires them** (the lane-B forward fix, owner assigned 2026-09-27):
  - Preview, apply and commit answer `410 {reason: "retired", alternatives: ["adopt_reading_version", "merge_into_write"]}`, with no lock taken and no receipt written.
  - `restore` stays live as the undo for any merge already committed, until the operator confirms none remain. Then it retires the same way.
  - Lane A removes the client callers in the same change.

### 1.11a Reformat derivation (rev 8, C6: the operator's paragraph 2)

**What it is.** The operator reformulates any information asset by prompt, for a reading time or narrowed to themes, questions or insights. The reformulating agent stays with the operator and asks before opening the result on the left (S6). In research and reading it is a right-pane tab. In writing it runs in the AI sidecar, because C5 gives writing's right pane to the block outline (placement by mode, below). He can merge the result later or officially fork it (T6, ruled 2026-09-26). None of this may blur the line between what the author wrote, what an LLM compressed or expanded, and what merged research supplied. Every bite's contribution is traced defensibly, and any probe of a reformulation resolves to the unscrambled core artifact.

**Engagement = a `reformat` thread (rev 7 §1.2).**
- NEW `POST /reformats {source, prompt, params}` creates the thread and starts the generation.
  - `source` is `{document_id}`, or `{derived_asset_id, revision_id}` to reformulate a reformulation.
  - `params` is `{reading_minutes?, focus_items?[], mode?: condense|expand|reorder|explain, research_context?}`.
  - **`research_context` (rev 8.7)** is `{investigation_ids[]}`, at most 5. At admission the server checks that each id exists, is the requester's and has started. It then snapshots the refs that each investigation's retrieval events cite, as `{chunk_id, document_id, text_sha256}`, into `generation_records.research_context`, and gives the generator exactly those refs as context. `research_context` is part of the request identity.
- The thread's log records:
  - `reformat.requested {source, prompt, params}`;
  - `reformat.generated {generation_id, derived_asset_id, revision_id, model: {providers[], model, dispatch_event_ids[]}, cost_cents, reading_estimate?}` (plural rev 8.10, below);
  - `reformat.open_proposed {revision_id}`, the agent's ask (T3: anything agent-initiated is a proposal that one key accepts);
  - `reformat.failed {reason, detail?}` (the closed vocabulary below, rev 8.3).

**One failure vocabulary (rev 8.3).** Every reformat failure uses exactly one reason, and each has one place it is reported.
- **Refused before any thread exists**, as the HTTP answer to `POST /reformats` or `/estimate`, with nothing spent:
  - `too_large`, 422
  - `source_too_deep`, 422
  - `source_not_servable`, 403
  - `idempotency_conflict`, 409
  - `refused_capped`, 402. Admission failed against `remaining_cents`.
- **Failed after admission**, as `reformat.failed {reason}` on the thread, which reads `failed`:
  - `unavailable`: the model or provider is unavailable, answered with a 503 upstream.
  - `interrupted`: the recovery rule found an unfinished generation.
  - `failed`: any other generation error, with `detail`.
- **Stopped by the cap mid-generation**, as `investigation.cap_halted`. This is not a `reformat.failed`: the thread reads `stopped`, with `stop_reason` `cap_reached` or `cap_overshoot` (§1.13).
- `reformat:<generation_id>` is an attribution bucket and the derived asset's id. It is never a thread id.
- **Spend.** Generation runs under the §1.13 daily cap through `reserve_dispatch` / `settle_dispatch`. A request is bounded: the source is chunked, `max_tokens` is set, and extras are capped. A refused hold answers `refused_capped` and nothing is generated.

**Storage: adopted, not rebuilt.**
- **The adopted code is the repaired lineage (rev 8.9):** PR #3527, `fix/reformat-repair-20260926@c0845e327`, which supersedes #3522's `632cf592a`. Every "EXISTS on the reformat lineage" below means that head.
  - #3527 already registers the reader view with the new source kind `derived` (its item e, "honest registration"), so the older #3522 lineage's `SourceKind.USER_CONTENT` in `substrate/reformat/pipeline.py@632cf592a` ("register_source_document") is superseded, never adopted.
  - `substrate/rights/register.py@c0845e327` gains `SourceKind.DERIVED` in that PR (rev 8.10 corrects the path).
- `generation_records` (EXISTS on the reformat lineage, `substrate/provenance/schema.py`) is the asset's birth certificate. It records the model identity actually used, in place of the operator-default label, in the adopted storage (rev 8.10):
  - `model`: one model per generation, the one the binding resolved (§1.11a "Model selection").
  - `provider`: the provider or providers that answered, comma-joined in the adopted column. The wire splits it into `providers[]`.
  - `dispatch_event_ids`: every DispatchCall event id, one per generation window.
  - `cost_usd`, as adopted. The wire reports `cost_cents` = `round(cost_usd × 100)`. Money itself settles only in the §1.13 ledger, in cents; this figure is telemetry.
- The derived asset is `derived_asset_id = "reformat:<generation_id>"` in `derived_asset_revisions` (§1.11). Revision 1 is `operation: create`.
- The **reader view** (§1.0) is `documents.document_id = "drv-<generation_id>"`, rebuilt only from the current revision.
- **Source kind and rights.** The view's `source_kind` is `derived` (NEW), never `USER_CONTENT`. It carries the source's `ip_holder_id` and content class, and a `source_tier` no higher than the source's.
- **Serving.** At serve time the view applies the **source's live gate**, most restrictive first (§1.2 mixed sources), so a source takedown or reclassification withholds the reformulation at once. Its chunks are excluded from retrieval, and author text is found through the source.

**Bites at span grain (S8's input).** `bite_provenance` (EXISTS) keeps its database rules:
- `author_verbatim` requires `derived_text_sha256 = source_span_sha256`;
- `research_supplemented` holds exactly when an investigation is present;
- `contribution_class` keeps exactly its four values on a **placed** bite, with one exception: an operator edit in a fork (`origin: operator`, rev 8.9) has none. A sourceless span is `llm_expanded`: it carries words its (zero) cited sources do not. Only an `unresolved` bite (null class and null origin) and an operator edit (null class, `origin: operator`) have a null class (rev 8.10).

**Its columns for origin and support (rev 8.7).** They are added with `ADD COLUMN IF NOT EXISTS`, and each rule is a CHECK:
- `origin` is `source`, `generated`, `unsourced` (rev 8.8) or `operator` (rev 8.9, for operator edits in a fork). It is null only on rows written before rev 8.7 and on `unresolved` bites.
- `unsupported` is a boolean, default false.
- **`state` (rev 8.8)** is `placed` or `unresolved`, default `placed`. `unresolved` is a bite the backfill could not place in a span (§1.11a "Legacy generations"). It keeps its text hash and refs, has a null `contribution_class` and `origin`, reads `unresolved`, weighs 0 in attribution, holds export back, and is never given a guessed class.
- `support_score` is nullable; `support_method`, `support_tokenizer` and `support_reason` are nullable text.
- `validator_version`, `template_id` and `slot_source` are nullable.
- **CHECKs:**
  - `origin = 'generated'` requires empty `source_refs`, a non-null `validator_version`, `template_id` and `slot_source`, and `unsupported = false`.
  - `origin = 'unsourced'` requires empty `source_refs` and `unsupported = true` (rev 8.8).
  - `unsupported = true` requires `origin` to be `source`, `unsourced` or null.
  - `state = 'placed'` requires a non-null `contribution_class` unless `origin = 'operator'` (rev 8.9); `state = 'unresolved'` requires a null `contribution_class` and `origin` (rev 8.8).
  - `origin = 'operator'` requires a null `contribution_class` and `declared_class`, and `unsupported = false` (rev 8.9).
  - A sourced span that is not verbatim (`llm_*` or `research_supplemented` with refs) requires a non-null `support_method` and `support_tokenizer`.
- **A row written before rev 8.7** has a null `origin`. A sourceless one reads as `unsupported` (fail closed) until it is rescored, and rescoring writes `unsourced` or, when the validator admits it, `generated`.

It gains:
- `derived_asset_id`, `revision_id` and `span`: a TextLocator `{block_id, start, end, text_sha256}` into the revision. A span's hash is recomputed on read, so a span that drifted from its text is `unresolved`, never still labelled verified.
  - **A read-time overlay (rev 8.10).** Bite rows are immutable, so drift never rewrites a row. The span list reports a drifted span with `hash_ok: false` and `state: "unresolved"`. Its top-level `contribution_class` and `origin` are null and `unsupported` is false, exactly as a stored unresolved span reads.
  - The row's values stay visible for audit in `as_recorded: {contribution_class, declared_class, origin}`, which is present only on a drifted span.
  - A drifted span weighs 0 in attribution and holds export back, like any unresolved span. Rescoring the revision is the only way it becomes placed again. A paragraph may hold several spans of different classes.
- `source_refs[]` as §1.4 anchors into the core document(s), each with `{document_id, anchor, text_sha256}`, so a ref can be re-resolved, and stored under `chunk_ids` / `document_ids` so the pointer walkers see them.
- **Server-assigned class.** The model's claim is kept as `declared_class` and is never trusted.
  - **Its column (rev 8.9).** `declared_class` VARCHAR is added with `ADD COLUMN IF NOT EXISTS`. A CHECK keeps it in the four classes or null.
    - It is written in the same insert as the server-assigned `contribution_class`, never updated.
    - It is null only when the model declared nothing: a sourceless bite with no claim, or an operator edit (below).
    - **Migration.** A row written before rev 8.9 stored the model's claim *as* its `contribution_class`, because the unrepaired pipeline trusted it. The backfill therefore copies that value into `declared_class`, then recomputes `contribution_class` by the rules here, so a legacy false claim becomes a counted mismatch rather than a trusted class.
  - `author_verbatim` only when the hashes prove it.
  - `research_supplemented` only when the investigation exists, is the requester's, and its retrieval events cite the refs. A fabricated id is refused.
  - **Bound to what the generation was given (rev 8.7).** The investigation must be one the request named in `research_context`, and every ref of the span must be in the snapshot taken at admission. Retrieval that happens after admission never counts, so naming an investigation afterwards cannot earn the class.
  - Otherwise the class is `llm_compressed` or `llm_expanded` by the measured length against the cited source spans. `llm_expanded` is also used when the span carries content its sources do not.
  - A false verbatim claim is recorded as a **mismatch** (`declared_class` ≠ `contribution_class`) and counted in the revision's receipt. It is never silently relabelled.
- `support: {score, method}` on every sourced non-verbatim span (`llm_*` and `research_supplemented`; rev 8.4). It is **lexical** support (v1, below), and its threshold is policy. It is not entailment. Below the threshold, the span renders with a "weakly supported" mark and is `unsupported` downstream.
- **Completeness (rev 8.9: a discriminated outcome).** A revision's text is partitioned into spans, and every span is exactly one of two outcomes:
  - **`placed`:** it has a class (or is an operator edit, below), a locator, and `state: placed`.
  - **`unresolved`:** it has a locator into the revision's text, `state: unresolved`, and a null `contribution_class` and `origin`. This is text that no placed bite covers, which only a legacy backfill can produce.

  A revision is complete when every span is one of the two. Zero spans that are neither is a test.
  - **Unplaceable bites are not spans.** A legacy bite the backfill cannot place has no locator, because it matches no text of the revision. It is kept as a `bite_provenance` row with `state: unresolved`, a null `span`, and its `bite_id`, `derived_text_sha256`, `declared_class` and refs. The span list returns it in a separate `unplaced_bites[]`, never among the spans.
  - A CHECK allows a null `span` only when `state = 'unresolved'`.
  - **Effect.** An unresolved span or an unplaced bite weighs 0 in attribution, holds the revision's export back, and reads `unresolved`.

**Rendering (lane A A8).** Each span renders by class, and class never relies on colour alone.
- **Gate by class:**
  - `author_verbatim` follows the quotation rule (`served | cite_only`).
  - `llm_*` and `research_supplemented` follow the synthesis rule (`served | withheld`).
  - A generated span with no source is `served` with `origin: generated` and `source_refs: []` (the §1.2 GatedText rule for generated text, rev 8).

**The span list (rev 8.3).** `GET /derived-assets/{id}/revisions/{rev}/spans` is owner-scoped (§1.15).
- It answers `{revision_id, mostly_generated, spans[], unplaced_bites[]}` (`unplaced_bites` rev 8.9: `{bite_id, derived_text_sha256, declared_class, source_refs}`, empty for any revision not made by a legacy backfill). The spans come in document order and cover the revision's text exactly once.
- **Each span:**
  - `span_id`, and `locator`: a TextLocator `{block_id, start, end, text_sha256}`;
  - `hash_ok`, from the hash recomputed on read. When false, the span is `unresolved` and never still labelled verified;
  - `contribution_class`, `declared_class`, `support {score, method, tokenizer, reason?}` (rev 8.5), `origin`, `unsupported: bool` and `validator_version` (rev 8.6: the connective validator that judged a sourceless span, `connective-templates/v2`; null on a sourced span);
  - `content`: a `GatedText` gated by the class rule, with its `source_refs` given as core refs.
- **Errors:**
  - `404 not_found` for an unknown asset or revision, or one that is not the requester's;
  - `409 legacy_generation` for a legacy row that has not been backfilled;
  - `422 revision_not_committed` while generation is still running.

**Probe to the core.**
- NEW `POST /derived-assets/{id}/probe {span_ids[], question}` answers with a list of `GatedText`. Each resolves to a **core** document span, never the derived asset or its reader view, or it carries an explicit `unresolved`.
- The probe is a B0 branch (§1.3) from the source's reading thread `read-<document_id>`, with origin `selection` at the probed span's source anchor, so it is a thread with a process. It is not free text.
- A span with no source is probed through its generation record, which returns the prompt and model that produced it.
- Pulling core snippets on demand is `GET /derived-assets/{id}/spans/{span_id}/sources`, which returns GatedText.

**Answer provenance and presentation (T7, ruled 2026-09-26).** Every answer a thread returns writes NEW `answer.provenance {answer_event_id, retrieved_refs[], cited_refs[], presentation_mode}`. This covers §1.8 turns, probes and reformat summaries.
- `presentation_mode` is `quoted | cited_quietly | metadata_only`, and is the AI's choice per answer. Quote bombs are optional.
- The invariant still holds: every claim keeps a resolvable chunk citation, as a quiet marker or as a metadata-only record. `cited_refs ⊆ retrieved_refs`, and the record equals the retrieved set, so an answer with zero visible citations still carries its full evidence for the agent-facing base and for attribution.

**Fork and merge (T6, ruled 2026-09-26).**
- **Officially fork** is a §1.11 `revise` commit on the derived asset, and the original revision is untouched.
  - **The route (rev 8.10).** NEW `POST /derived-assets/{asset_id}/revisions {base_revision_id, blocks: [{block_id, text}], idempotency_key}`.
    - `blocks` holds the complete new text of every block the operator changed; unlisted blocks are unchanged. The operator never names a class.
    - It is owner-scoped: another owner's asset is 404.
    - It is `409 {reason: revision_moved, current_revision_id}` unless `base_revision_id` is current.
    - The same key and body replay; the same key with another body is `409 idempotency_conflict`.
    - It answers `{revision_id, carried, edited}`: the counts of carried and edited sentences.
  - **The server decides what is an edit, never the client.** Each new block's text is split into UAX #29 sentences.
    - A sentence whose NFC hash equals a sentence of the same block in the base revision is **carried forward**.
    - Every other sentence is an **operator edit** (`origin: operator`).
    - This route admits no model text: model text enters only through a reformulation, whose generation record binds it.
    - An edit that splits a carried sentence makes both halves operator edits. The classes it had are never stretched over changed words.
  - **Its bites (rev 8.9).** Bite rows belong to one revision and are never updated, so a revise writes the new revision's own rows in the same transaction as the commit:
    - **Carried forward.** A span of the new revision whose text hash equals a span of the parent revision gets a new `bite_id` with the parent's class, `declared_class`, origin, support and refs copied. It records `carried_from_bite_id`, and its locator points into the new revision.
    - **Operator edits.** Text the operator typed or changed gets `origin: operator`, a null `contribution_class` and `declared_class`, and `state: placed`. The CHECK allows a placed bite with a null class only when `origin = 'operator'`. It renders as "Your edit", weighs 0 in attribution, and is never unsupported: it is the operator's own words, not a claim the model made.
    - **Model text** added by a later reformulation of the revision is scored afresh by the rules above.
    - The parent revision's rows are untouched, so probing, attribution and export of any revision read that revision's rows alone.
- **Merge later** means one of two things:
  - **Adopt as the project's reading version.** NEW `project_reading_versions (owner_user_id, project_id, source_document_id, derived_asset_id, revision_id, adopted_at, version)` is a pointer, and it never writes into the source. The primary key is `(owner_user_id, project_id, source_document_id)`.
    - **Routes (rev 8.7).** All are owner-scoped, and another owner's project answers 404 like a missing one (§1.5).
      - `GET /projects/{project_id}/reading-versions/{source_document_id}` answers `{source_document_id, derived_asset_id, revision_id, adopted_at, version}`, or `404 no_reading_version`.
      - `PUT /projects/{project_id}/reading-versions/{source_document_id} {derived_asset_id, revision_id, expected_version}` adopts. `expected_version` is 0 when nothing is adopted yet, and the answer is the GET shape.
      - `DELETE /projects/{project_id}/reading-versions/{source_document_id}?expected_version=` reverts to the source.
    - **The PUT checks, in order:**
      1. The project is the requester's: else `404 project_not_found`.
      2. The source is a `document` member of the project: else `422 source_not_in_project`.
      3. The derived asset is the requester's, and its `rights_basis.core_documents` contains the source: else `422 not_a_reformulation_of_source`.
      4. The revision exists and has committed: else `422 revision_not_committed`.
      5. The reformulation is servable to the requester under the source's live gate: else `403 source_not_servable`.
      6. `expected_version` matches: else `409 {reason: version_stale, current}`, where `current` is the GET shape or null.
    - **Serving.** Opening that source in that project's reading tree shows the adopted revision, labelled as the project's reading version of the source, with one key to show the source itself. The serve-time gate still applies: a takedown withholds the reading version, and the pointer stays.
    - The PUT and the DELETE each write `project.reading_version_changed {project_id, source_document_id, derived_asset_id?, revision_id?}` on `read-<source_document_id>`.
  - **Merge into a Write deliverable** through §1.11 merge-drafts, where members keep their classes.
- The unit-5 `/books/{id}/forks` and `/forks/{id}/merge` client paths are retired.

**Reading parameters.**
- `reading_minutes` returns `reading_estimate {minutes, method, shortfall?}`. A request the source cannot honestly fit says so, and the reformulation is not padded or truncated silently.
- `focus_items[]` (themes, questions, insights, or an `anchored_highlight`) each map to span ids in the revision, so a focus can be checked.

**Attribution telemetry (S8, G4).**
- NEW `page.attribution.computed {subject: "drv:<asset>@<rev>", shares[{document_id, ip_holder_id, share, basis}]}`, emitted when a revision commits and when it is served.
- The shares split by source document and class: `author_verbatim` in full, `llm_*` weighted by support, and `research_supplemented` to that thread's cited sources.
- `substrate/attribution` reads it as **telemetry only** until the §9.0 gates G2/G3 open. No payout, escrow accrual or ledger movement is emitted, and a test asserts that.

**Write informs (S5).** NEW `derived_asset_block_informs (derived_asset_id, revision_id, block_id, ordinal, document_id, anchor?)`.
- It is an ordered list of the documents that inform each Write block.
- It is written only through a `revise` with compare-and-set on the current revision, never a `deliverables.metadata` PATCH.
- Lane A assigns by drop and by key, and reorders.
- **The operation (rev 8.7).** NEW `PUT /derived-assets/{asset_id}/blocks/{block_id}/informs {informs: [{document_id, anchor?}], expected_revision_id, idempotency_key}`.
  - It replaces the block's whole list. `ordinal` is the list order.
  - It commits one §1.11 `revise` (`operation: informs`). The block's text is unchanged; only its informs change.
  - It answers `{revision_id, block_id, informs: [{ordinal, document_id, anchor?}]}`.
  - **Checks:**
    - The asset is the requester's, and the block is in the current revision: else 404.
    - `expected_revision_id` is the current revision: else `409 {reason: revision_moved, current_revision_id}`, and lane A rebases.
    - The list has at most 50 entries and no repeated `document_id`, and each document exists and is readable by the requester: else `422 informs_invalid {index, detail}`.
    - An `anchor` must name the same `document_id`, in the §1.4 shape: else `422 informs_invalid`.
  - **Idempotency.** The same key and body replay the first answer; the same key with a different body answers `409 idempotency_conflict`.

**Model selection (rev 8.2).** `POST /reformats` and `POST /reformats/estimate` accept `params.model_choice?`.
- It is validated against the owner's lineup (`settings_lineup.py`). When it is absent, the model is the operator default for the `reformat` dispatch role.
- **Binding (rev 8.3).** An explicit `model_choice` is part of the request identity. Without one, the identity holds `model_choice: "default"`, and the model is resolved **once**, at admission, then recorded on the generation.
  - A retry under the same key replays that first generation even if the default has changed since.
  - A new Generate press is a new key, and it resolves the current default.
  - `assumptions.model` in `/estimate` echoes what a new press would use now. The estimate binds nothing.
- Generation uses exactly that model. If the default changes between the estimate and the generate press, the new identity yields a new estimate, never a silent swap.

**Placement by mode (rev 8.2, C5).** Placement is decided in Part 2, and the engagement is the same `reformat` thread in every mode.
- **Research and reading:** it is a right-pane reformat tab, and its result opens as a left `derivation` child of the source tab.
- **Writing:** the right pane is the block outline (C5), so the engagement runs in the AI sidecar. Its result opens as a left `derivation` child under the active section (T4).

**Lineage storage (rev 8.2).** `generation_records` gains:
- `source_kind`: `document | derived_revision`, NOT NULL;
- `source_document_id`, set only for `document`;
- `source_derived_asset_id` and `source_revision_id`, set only for `derived_revision`;
- `core_document_ids_json`: the resolved core set, sorted;
- `rights_basis_json` (one shape, rev 8.8): `{core_documents[], most_restrictive_class, least_trusted_tier, holder_set[], servable_at_commit}`.
  - **What is adopted, and what comes later (rev 8.10).** #3527's column is named `rights_basis` and holds `{core_documents, most_restrictive_class, holder_set}`.
  - LB-4b renames nothing. It adds `least_trusted_tier` and `servable_at_commit` to the same JSON, additively.
  - Until then a reader treats a missing key as **not established**, and fails closed: with no `servable_at_commit`, only the live serve-time gate decides. Its `core_documents` equals `core_document_ids_json`, and its `holder_set` equals `holder_set_json`. Those two columns stay as denormalised copies that a CHECK keeps equal, so readers of either agree;
- `holder_set_json`;
- `provider`, `model`, `dispatch_event_ids`, `cost_usd` (adopted from #3527, rev 8.10);
- `state`.

One CHECK allows exactly one source form. **Migration:** existing rows are all direct documents, so they copy with `source_kind: document`, `core_document_ids_json` holding their one source, and the basis recomputed from that document at migration time.

**Legacy generations fail closed (rev 8.3).** A pre-rev-8 generation has no derived-asset revision and no span partition, so it copies with `state: legacy`.
- It stays readable exactly as before, through its reader view under the live gate.
- It **cannot** be a `derived_revision` source, be probed through `/derived-assets/{id}/probe`, be merged into Write, or earn attribution until it is backfilled.
- NEW `tools/backfill_reformulations.py` writes revision 1 and the span partition from the stored text and bites, per the rules above. It never guesses a class (rev 8.10, matching "Completeness" above):
  - text that no placed bite covers becomes an `unresolved` **span**, with a locator and no class;
  - a bite it cannot place becomes an **unplaced bite** (`state: unresolved`, null `span`), returned in `unplaced_bites[]` and never among the spans.

  The row then moves to `committed`.

**Support that fails closed (rev 8.2).** This refines rev 8.1's partition and support.
- **Tokenizer.** Sentences and words follow Unicode UAX #29 (ICU BreakIterator, root locale). The pinned tokenizer is recorded in its own field: `support` is `{score, method: "rougeL-f1/v1", tokenizer: "uax29/icu-<version>", reason?}`. This is the one wire form, used everywhere (rev 8.5). Words are compared NFC and lowercased.
- **Matched window.** Support and class are computed against the **best-matching window** of each cited source span, where a window is a source substring of at most 1.5× the derived span's word count, taken at the highest ROUGE-L F1.
  - **Deterministic search (rev 8.4).** The unit space is the cited source span's UAX #29 word tokens, NFC and lowercased, indexed from 0.
  - A window is a contiguous token range whose length runs from 1 to ⌈1.5·n⌉, where n is the derived span's word count.
  - The chosen window has the highest F1. On a tie, the earliest start index wins, then the shortest length. Citing an overbroad source span earns no more than its best window. Compressed versus expanded compares the derived span's words with that window's words.
- **Several refs (rev 8.3).** A span that cites several source spans takes one best window per ref.
  - Its **support** is the maximum over those windows. On ties, the earlier ref in the span's ref order wins.
  - Its **class** compares the span's word count with the **sum** of the matched windows' word counts: at most the sum is `llm_compressed`, more is `llm_expanded`.
  - Windows are found per ref and never span two refs.
- **Unsupported.** A span with support below 0.35, or `not_computable`, is `unsupported` for every downstream use:
  - it gets no attribution share;
  - in a Write merge it becomes an `unsupported` member (rev 8.3). Honest connective text becomes a `generated` member. The two never share a kind;
  - a probe answers that the span has no supporting source.

  Its class stays recorded, but the class earns nothing without support.
- **Aggregate bound.** When sourceless plus unsupported words exceed 15% of the revision, `mostly_generated` is set. The revision is then excluded from attribution entirely. A merge of it into Write needs `"mostly_generated"` in the review's `acknowledgements` (rev 8.5):
  - `POST /merge-drafts/{draft_id}/review` gains a typed `acknowledgements: ["mostly_generated", ...]`, persisted with the review and bound into the `review_id`.
  - The commit refuses with `422 acknowledgement_required {missing: ["mostly_generated"]}` when the source revision is `mostly_generated` and the review lacks it.
  - The commit envelope's literal `acknowledgement: "new_revision"` (§1.11) is unchanged and separate.

**Estimate (rev 8.1).** NEW `POST /reformats/estimate {source, params}` returns:
- `estimate_cents | null` and `max_cents`;
- `reason?`: `unavailable | source_not_servable | too_large`;
- `assumptions`: `{input_tokens, max_tokens, extras_cap_cents, model}`.

`max_cents` is the conservative maximum the §1.13 admission compares against `remaining_cents`. When no figure can be given, Part 2 asks for an explicit confirm, and every dispatch hold still bounds the spend.

**Idempotency, state and recovery (rev 8.1).**
- **Idempotency.** `POST /reformats` takes an `idempotency_key`, and the request identity is sha256(owner, source, prompt, params).
  - The same key with the same identity replays: the same thread, the same generation, nothing new spent.
  - The same key with a different identity answers `409 idempotency_conflict`.
- **State.** `generation_records` gains `state`: `requested → admitted → generating → committed | failed`, and each transition is a `connect_write`.
  - `admitted` comes only after the §1.13 admission check.
  - Each dispatch holds through `reserve_dispatch` with `dispatch_id = <generation_id>:<chunk_index>`, so a retried chunk never double-holds or double-spends.
- **Commit.** The revision, its members, its bites and the reader view are written in **one** transaction. The view is deterministic from the revision: if it is ever missing, it is rebuilt on read and never regenerated.
- **Recovery.** At startup, a generation left in `requested`, `admitted` or `generating` past its lease settles its open holds at the held amount (the §1.13 unknown-outcome rule) and becomes `failed {reason: interrupted}`.
- **Terminal events.** `reformat.generated` and `reformat.failed` reach the thread through the same relay pattern as the cap halt (§1.13). Their event ids are deterministic from `(generation_id, state)`, so redelivery is idempotent.

**Reformulating a reformulation: rights (rev 8.1).**
- **Core set.** A `source` that is a derived asset resolves through `generation_records.source`, recursively, to its **core set**: the non-derived documents at the bottom.
  - A chain deeper than 8 is refused with `source_too_deep`.
  - Lineage only points to existing revisions, so there is no cycle.
- **Rights.** Rights come from the core set: the most restrictive content class and servability, the least-trusted `source_tier`, and a **holder set** of every core holder.
  - The view's `ip_holder_id` is that holder when there is exactly one. Otherwise it is null, and the set is recorded on the generation record.
  - These facts are bound to revision 1 as `rights_basis`, in the one shape of `generation_records.rights_basis_json` above (rev 8.8), and are **revalidated live at serve time** against each core document's current gate.

**Span partition and support (rev 8.1), so the classes cannot be gamed.**
- **Canonical text.** It is the revision's html_projection block text in NFC. Each block is partitioned into ordered, non-overlapping spans that cover every non-whitespace character exactly once.
- **Grain.** A span is at least one sentence, unless it is an `author_verbatim` substring, and at most one block.
  - **The partition never splits a sentence (rev 8.6).** A single sentence longer than a span's word cap (below) forms a span of its own. It is the one exception to the cap, and no text is dropped or truncated.
- **Class, deterministically.**
  - `author_verbatim` only by equal hashes.
  - `research_supplemented` only with a validated investigation, named in `research_context`, whose admission snapshot holds every ref of the span (rev 8.7).
  - Otherwise `llm_compressed` when the span's word count is at most the total words of its cited source spans, and `llm_expanded` when it is more.
- **Support.** `support.score` is v1 lexical support and deterministic: ROUGE-L F1 on NFC-lowercased word tokens, to two decimals, with `method: "rougeL-f1/v1"` and the `tokenizer` field. It is scored **per sentence** (rev 8.5, below). A span's reported score is the **minimum** over its sentences, never a maximum.
  - Below **0.35** the span renders "weakly supported".
  - A model-based entailment may be recorded as a second method. It never decides the class or the threshold, and v1 is named lexical support, never entailment (rev 8.4).
- **Research is gated too (rev 8.4).** `research_supplemented` spans are scored the same way, against the chunks that their investigation's retrieval events cite. Below the threshold they are `unsupported`. Naming a real, owned investigation is necessary, but not sufficient.
- **Per sentence (rev 8.5).** The unit of support is the UAX #29 sentence.
  - Each sentence of a sourced non-verbatim span is scored on its own, against the best window of each cited ref (the deterministic search above).
  - A sentence is supported when **some** cited ref's best window meets the threshold.
  - Before members or attribution are computed, every sentence that fails is **split into its own span** and marked `unsupported`. A supported span therefore contains only supported sentences, and a failing claim can never ride inside it.
- **Connective-text validator v2: a closed set (rev 8.6; replaces v1 of rev 8.5).** Lexical tests cannot tell framing from an assertion that echoes the prompt ("this supports the focus argument" passed v1), so v2 does not score prose. A sourceless sentence is `generated` only when it matches, after NFC and whitespace folding, one template of the pinned set `connective-templates/v2`:
  1. `This section covers {X}.`
  2. `The next section turns to {X}.`
  3. `The following summarizes {X}.`
  4. `Open questions on {X} follow.`
  5. `Sources on {X} follow.`
  6. `{X}` alone, as the whole text of a heading block.

  Each `{X}` must be a **verbatim** span of 1 to 8 words, matched case-insensitively, of **operator-authored text only** (rev 8.7): the prompt, or a focus item the operator typed (a theme, question or insight). The slot is therefore never model-authored text, and no template asserts anything about the world.
  - **Never source text (rev 8.7).** A slot may not come from a core source's heading or from a focus item that is an `anchored_highlight`, because either would pass source words off as sourceless text and skip their rights and attribution. A heading copied from a source is source text: it is `author_verbatim` by equal hashes and carries its ref.
  - **Recorded per sentence (rev 8.7).** A `generated` sentence records `template_id` (1 to 6) and `slot_source` (`prompt` or `focus_item:<index>`), so the operator words it quotes can be found again.
  - **Operator text that carries source words (rev 8.8).** An operator could paste a source's words into the prompt and template them. So a slot of **4 or more words** that occurs verbatim in the served text of any core source is treated as source text, not operator text. Matching is after NFC, case folding and whitespace folding. The sentence is then `unsourced` and `unsupported`, never `generated`.
    - A slot of 1 to 3 words is a topic label. It is admitted even when the source uses those words, because so short a phrase carries no expression to protect and no attribution weight, and a topic could not be named otherwise.
    - The check runs against the core set's served text at scoring time, and it is re-run whenever the span is rescored.
  - **Everything else is `unsupported`,** however short or plain. That includes any template whose slot is not verbatim.
  - Adding a template is a contract revision, never a code change alone.
  - A test pins the accept cases and these reject cases: "this supports the focus argument"; a template with a paraphrased slot; a template with a slot of 9 words; a heading that is not verbatim; a template followed by a second clause; (rev 8.7) a slot taken from a source heading or from a highlight focus item; and (rev 8.8) a prompt slot of 4 or more words that occurs verbatim in a core source. A 3-word topic label the source also uses is pinned as accepted.
  - **Recording.** `validator_version` is stored with each sourceless span on `bite_provenance` and in the export provenance manifest.
  - **Rows scored before rev 8.6** have `validator_version` null. Their sourceless sentences read as `unsupported` (fail closed, like legacy generations) until they are rescored under v2.
  - When a cited source span cannot be read (not servable to the scorer, or drifted), `score` is null with `reason: not_computable`. The span renders "support unknown" and weighs 0 in attribution.
- **Sourceless spans.** A span with no source refs has `source_refs: []`. Each of its sentences is `origin: generated` only if the connective-text validator passes it (rev 8.5; v2 rev 8.6). Otherwise it is `origin: unsourced` and `unsupported` (rev 8.8).
  - Each such span is at most 40 words, except a single sentence longer than that, which is its own span (rev 8.6, Grain above).
  - When sourceless words exceed 15% of the revision, `generation_records.mostly_generated` (EXISTS) is set and the view carries a banner.
  - Sourceless spans get no attribution share.

**Merging a reformulation into Write keeps its classes (rev 8.1; the join rev 8.2).** The class and support stay on `bite_provenance`. They are never copied onto a member.
- **The join (multi-ref, rev 8.3).** NEW `derived_asset_member_bites (derived_asset_id, revision_id, bite_id, ref_ordinal, member_key)`, with primary key `(derived_asset_id, revision_id, bite_id, ref_ordinal)`.
  - A bite with several core refs gets one row per ref, in the span's ref order. Each row points at the evidence member for that ref's source, and no ref is dropped.
  - A sourceless or unsupported bite gets one row with `ref_ordinal` 0, pointing at its `generated` or `unsupported` member. This holds even when the unsupported bite cites refs: its refs do not support it, so they are **not** routed to evidence members. Its complete ordered ref set stays on `bite_provenance.source_refs` and is listed in the export manifest (rev 8.4).
  - The join is written in the same transaction as the revision.
- **Per class:**
  - `author_verbatim` → an evidence member with `use: quote`. Its source columns are the core ref's document projection, asset and hashes.
  - `llm_compressed` and `llm_expanded` with support at or above the threshold → evidence members with `use: cite`, with the core ref's source columns.
  - `research_supplemented` → an evidence member with `use: cite`, its core ref's source columns and its `investigation_id`.
  - A sourceless span → a `generated` member. An `unsupported` span → an `unsupported` member, which withholds export until resolved (rev 8.3).

Evidence members stay deduplicated by `member_key` as before. The join is what lets an export recover every bite's class.
- **The manifest.** A Write export's manifest lists each member together with its joined bites' classes and supports, so the reformulation's provenance travels with it.

**Probe routing to the core (rev 8.1).**
- **Resolving refs.** A probed span's source refs resolve through the derivation lineage (the core set above) to core refs.
- **Branching.** The probe branches from `read-<core_document_id>` of the span's first core ref, in the span's ref order. Every core ref rides the branch's `origin.anchor` and `spawn_context`. When the refs name several core documents, the answer covers them all, and each ref resolves on its own.
- **Refusal.** A core the requester cannot read is refused with `probe_core_inaccessible`, never answered from the derived text.
- **Ownership.** Reading threads are single-operator today. Their owner-scoped ids come with §1.15.

**Future modalities (noted, not built).** Talking to or watching an asset reuses this contract. The engagement is a thread, the output is a derived asset, and bites and probes work the same way.

### 1.12 Companion document (2.7; Q-A3 naming)

**Agent-facing base (rev 8; sibling-stacks §3.2).** `evidence_index` (companion stack, rebuilt under LB-9) is the refs-only agent-facing evidence base alongside the MCP resources, with `entry_id = evidence_id`.
- It is admitted only with an owner-safe id: the owner is in the id material, or the key is `(owner_user_id, evidence_id)`.
- Its GET routes never write. A refresh is a POST plus the typed `companion_document.refreshed`.
- Its human-facing shape is the §1.12 entry list below, as GatedText.

**In the cockpit (rev 7, C4; S7).** The project companion document is the right pane's **Findings** tab, read from the routes below. The per-evidence rail stays in the reader. There is no second model: Findings is a view, and it renders each entry by `content.gate` (§2.10).

**Q-A3.** "Companion" already means five things:
- the `ReadingCompanion` rail component (`ReadingCompanion.tsx:26`)
- operator status docs (`docs/master-product-spec.md:39-84`)
- codex-primary's handoff-bundle "companion bytes" and receipts (board claims such as `codex-antiek-companion-integrity-receipt-20260924`)
- the `.antiek` sidecar writer (`services/antiek_format/sidecar_writer.py:3`)
- a thought-partner description

The mothership uses only the compound terms of §1.0.

**Routes.** NEW `GET /projects/{id}/companion-document` (the tab) and `GET /documents/{id}/companion-document` (the rail) both return:
- `entries[]`
- `content_hash`
- `covered: {thread_id: through_event_id}`
- `summarised_thread_count`, `total_thread_count` (R2-2)
- `state`

Each entry is `{entry_id, kind: claim|open_question|insight, content: GatedText, confidence?, thread_ids[], doc_ids[], updated_at, process_ref}`, where `process_ref` is the thread id plus event id. The rev-5 `text` and `source_refs[]` now live inside `content` (rev 6, R5-2).

**Sources.**
- The rail's per-document read path is EXISTS `GET /write/blocks/search?source_document_id=` (`write_routes.py:349-371`; RUN), extended with owner, servability and investigation provenance.
- Entries derive from each member thread's `ResearchArtifactBody` (`artifact_routes.py:254-616`) and `twin_note_taker`. Every text passes the rights-gated pack (§1.10).

**Refresh and staleness (rev 3).** `POST /projects/{id}/companion-document/refresh` (and its per-document twin) rebuilds the document and writes a receipt, **NEW** typed event `companion_document.refreshed {scope, id, content_hash, covered}`. It is its own action, not the `NOTE_COMPRESSED_DOC_WRITTEN` family, whose action and payload differ (`events.py:207,1248-1254`).

The document is `stale` when any of these holds:
- a member thread has an event newer than its `covered` entry, whether a completion, a `thread.turn` or a new retrieval;
- project membership changed since the receipt;
- a `reading.position` or `read.book_answered` event landed on the document since the receipt.

**Agent-facing evidence base.** The same entries plus the gated `SessionEvidencePack` and trajectories, served to agents through the MCP memory resources. Lane A renders only the link.

**Rights precondition.** Nothing here ships until the wave-5 export branch and `fix/w5-mcp-hardening-20260923` merge.

### 1.13 Flags, consent, daily cap and inbox (2.8), plus the to-read queue (2.9)

**Store for diligence flags (rev 8; sibling-stacks §3.4).** `diligence_queue` (EXISTS on main, refs-only, with CHECK backstops) is the store for `intent: diligence` flags.
- `flag_id` takes the form `dfl-…`.
- A `{concept: key}` target joins the target union.
- The shipped `/diligence/flags*` routes stand.
- `dismiss` is `decline`.
- D4 still governs: no launch without a consent event and a §1.13 hold. The daemon refuses to start with `ANTIEK_DAEMON_SPAWN_ENABLED` on until consent and the API-routed claim-then-spawn exist (LB-10).

**Flag identity and lifecycle (rev 3).** A flag is a `question.identified` event (`events.py:1260-1264`), and `flag_id` is its `question_id`. It gains:
- `intent: read | diligence`
- `actor: {kind: user|agent, id}`, **server-derived** from the request identity or the emitting agent's role, never client-supplied
- `target`: one of
  - `{anchor}`
  - `{question_id}`
  - `{insight_id}`, content-addressed by `insight_node_id` (`substrate/graph/insight_question.py:130`)
  - `{claim: {event_id, chunk_id?, edge_id?}}` (rev 3, R3-4): the retrieval event that stated the claim, plus its pointer
  - `{document: {document_id, anchor?}}` (rev 5): the to-read target for `intent: read`
  - **To-read projection.** `GET /flags?intent=read` returns every read flag. For a question, insight or claim target it resolves the document; when that fails, the item carries `document: null` and `reason: unresolved_document` rather than being dropped.
- `reason`

The lifecycle is typed events on the question family, all NEW:
- `question.diligence_consented {flag_id, consent_id, model_choice, estimate_cents}`
- `question.diligence_declined {flag_id}`
- `question.diligence_launched {consent_id, thread_id}`
- `question.diligence_refused {consent_id, reason: refused_capped|unavailable|failed}`

**Authenticated mutations (rev 3).** The actor always comes from the request identity:
- `POST /flags {intent, target, reason}` creates a flag.
- `POST /flags/{flag_id}/consent {model_choice, estimate_cents}` writes the consent, bound **immutably** to the flag's target and to a context version: the thread's head event and the anchor's `text_sha256`.
- `POST /flags/{flag_id}/decline` declines it.
- `POST /flags/{flag_id}/launch {consent_id}` launches.

**Consumption.** A consent is single-use, consumed idempotently by `consent_id` for exactly the consented model, target and version. A retry returns the same `thread_id`. If the target's version moved, the answer is `409 consent_stale` and consent is asked again. A refusal is recorded, never silent.

**No bypass.** The watch-for-later launch (`app.py:5011-5170`) stays a manual "read/run now" action. A **diligence** flag is never launched without consent. `GET /watch-for-later`, which drops `read-<doc>` parks today, is extended into `GET /flags?intent=&project_id=`.

**Unpriced estimates (R3-2, confirmed).** When the estimate is `unavailable`, consent is **not offered**. No reserve can be sized for an unknown price.

**Daily cap over actual spend (rev 4: a flat-hold design the cited ledger supports).** The authority is `BudgetLedger` (`substrate/midnight_oil/budget_ledger.py`), through a NEW `DiligenceBudget` adapter. There are no nested holds; the ledger has no parent-hold operation.
- **Daily authority.** The day's run `diligence:<owner>:<day>` is initialized once, at first use, with the user-set cap (`reserve`, `:369`). It stays open all day, and the adapter never calls the run-wide `release`.
- **Launch admission, no hold.** A launch is admitted only if the run's `remaining_cents` (`balance`, `:908`; defined as ceiling − spent − held, used directly without subtracting holds again) is at least the conservative maximum: the estimate × 1.5, or the tier's maximum when larger. Otherwise the answer is `refused_capped`.
  - Admission reserves nothing. Other work can consume the cap after admission, so a later dispatch may pause the run (`stopped`, reason `cap_reached`).
  - Lane A's consent copy must say so: "Starts if $X of today's cap is free; it pauses if the cap runs out" (rev 5), not "held".
- **Per dispatch, the only holds (rev 5: a declared ledger extension).** NEW `BudgetLedger.reserve_dispatch(run_id, dispatch_id, max_cents, thread_id, project_id)` works as follows:
  - It atomically creates one hold bound to a **unique** `dispatch_id` (the dispatch call id) and its attribution.
  - A replay with the same id and identical fields is idempotent. The same id with different fields answers `DispatchConflict`.
  - NEW `settle_dispatch(dispatch_id, actual_cents)` settles it, carrying `thread_id` and `project_id` onto the settlement row.

  `reserve_call` (`:605`) is not cited as providing any of this; it has no identity or attribution columns. The extension is tested against the ledger.
- **Per-call upper bound (rev 5).** Before dispatch, the hold is `max_cents` = input tokens × input rate + `max_tokens` × output rate + the tier's cap on billable extras (tool calls, search). `max_tokens` and the extras cap are enforced on the request. Each retry is its own dispatch with its own hold.
- **Enforcement and overshoot (rev 6; replaces rev 5's settlement bound).**
  - Admission and the dispatch holds bound **reserved exposure**. No hold is created that would take `remaining_cents` below zero, and a dispatch whose hold is refused does not run.
  - Settlement is truthful. `settle` records the actual charge even above its hold: it appends an `overshoot` ledger entry and marks the run exhausted when nothing remains (`budget_ledger.py:688-775`). `settle_dispatch` keeps that behaviour.
  - So spend passes the cap only by what providers bill beyond bounded requests already in flight, and every such cent is recorded.
- **The cap halt (rev 6, R5-3).** A refused hold or an overshoot halts the thread's further dispatch. It writes NEW `investigation.cap_halted {ledger_run_id, dispatch_id, reason, hold_cents, billed_cents?}` strictly into the thread's log, as its terminal record:
  - `cap_reached`: a dispatch's hold was refused. `hold_cents` is the refused hold, and nothing was billed for it.
  - `cap_overshoot`: a settlement exceeded its hold. `hold_cents` is the hold, and `billed_cents` is the true charge.

  Dispatches already in flight still settle truthfully and are not cancelled. The thread reads `stopped` with that `stop_reason` (§1.2), and the inbox gains a `run_stopped` item (below).
- **The halt is durable before it is announced (rev 7).** The halt obligation is part of the ledger's own write, so a crash cannot separate the charge from the stop:
  - `reserve_dispatch` refusing a hold, or `settle_dispatch` recording an overshoot, writes a row into NEW `midnight_oil_dispatch_halts (thread_id, dispatch_id, run_id, reason, hold_cents, billed_cents, created_at, delivered_event_id)`. The row is written in the same ledger transaction as the refusal or the settlement, in the same database as the `midnight_oil_*` tables. The primary key is `(thread_id, dispatch_id)`.
  - While any halt row exists for a thread, `reserve_dispatch` refuses every further hold for it with `ThreadHalted`, whether or not the event has been delivered yet.
  - A relay delivers each undelivered row as `investigation.cap_halted` into the thread's log. It uses `emit_typed(..., event_id=<deterministic from thread_id and dispatch_id>, idempotent=True, strict_write=True)` (`events.py:358-371`), then records `delivered_event_id` on the row.
  - The relay runs after each refusal or overshoot, and again at API and daemon startup. A crash between the ledger commit and the event write is therefore delivered on restart, and a repeated delivery finds the same event id.
  - The `run_stopped` inbox item's `item_id` is that event's id, so it is stable across redelivery.
- **Who can hit the cap (rev 6).** Only threads the `DiligenceBudget` admitted can stop with `cap_reached` or `cap_overshoot`. These are diligence launches, the daemon's spawns and **reformat engagements** (rev 8.1, §1.11a), whose generation is admitted and held through the same ledger. "Raise today's cap" therefore belongs only on those. An island or an operator launch is metered by the ACU gate before start and by its own research budget while running, and stops with `user`, `cancel` or `budget`.
- **Unknown outcome.** On restart, an unsettled dispatch hold settles at its full held amount, the conservative direction.
- **Cap change (rev 4).** NEW `PUT /settings/budget/daily-cap {cents}` amends today's run ceiling atomically, through a NEW ledger amendment operation under the ledger's own transaction.
  - Raising the cap takes effect for the next admission and hold.
  - Lowering it below `spent + held` blocks new holds; it neither cancels nor overspends outstanding ones.
  - An exhausted run is re-opened by a raise.
  - Concurrent launches see either the old or the new ceiling, never a mix.
  - There is no second run for the day.

`GET /settings/budget` (`settings_budget.py:817-961`) gains:
- `daily_cap_cents`
- `spent_today_cents | null`
- `held_today_cents | null` (rev 4, R4-1): the sum of open dispatch holds

The sheet can then say beforehand whether a launch's conservative maximum fits within cap − spent − held.
- The daemon's advisory `DaemonBudget` (`orchestration/continuous/budget.py:165-178`, frozen) stops being an independent spending gate. The same adapter carries the daemon's spawns. **NEW (rev 3):** entrypoint wiring gives both the one-shot and the continuous modes of `orchestration/continuous/__main__.py` the budget adapter and a `SpawnFn` that launches through the API as a branch-writing launch. Today no injection seam exists there, so the wiring is new code, not a cited one. `chase_mode` joins `InvestigationStartRequest`; the orchestrator already implements it on main.



**Inbox, durable (rev 2).** Items derive from **durable** events, never from the socket alone:

| Kind | Source event |
|---|---|
| `thread_done` | `investigation.completed` |
| `thread_needs_you` | a pending spend approval |
| `flag_consent` | a flag awaiting consent |
| `refused_capped` | `question.diligence_refused`, and the ACU gate's refusal recorded as a NEW `launch.refused` event |
| `merge_suggestion` | `thread.merge_suggested` |
| `run_stopped` | `investigation.cap_halted` (rev 6, R5-3) |

The rules:
- `item_id` is the source event id, so it is stable.
- The owner is the event's owner.
- `GET /inbox?after=<cursor>&limit=` returns `{items[{item_id, kind, ref, detail?, created_at, seen_at?}], next_cursor}` for reconnect catch-up.
- `ref` is the thread, flag or merge the item is about. `detail` depends on the kind; for `run_stopped` it is `{reason, hold_cents, billed_cents?}` (rev 6).
- `POST /inbox/{item_id}/seen` sets `seen_at` in the per-account store.
- The WebSocket only nudges a refetch.

**To-read queue.** `GET /flags?intent=read`, with `actor` covering you or an agent.

### 1.14 Reading position and reading threads (2.9)

**Authority (rev 8, replacing the event-log authority below; sibling-stacks §3.5).** The `reading_state` row per `(owner, document)`, with its `revision` compare-and-set (EXISTS on main via #3425), is the store of record.
- The #3454 blockers were lost updates, and the revision precondition closes them. An append-only log answered by "newest event per document" would stay last-writer-wins without a precondition of its own.
- `/books/{id}/reading-state` stands. `GET /reading/continue` reads the table.
- A `reading.position` event remains only as a derived emission where thread state needs one.

**The write and its precondition (rev 8.1).** `PUT /books/{id}/reading-state {page_index, anchor_ref?, revision}` (EXISTS, `reading_state_routes.py:36-44,149-159,178-185`) is the only writer.
- `revision` is the revision the client last saw, 0 for a first write.
- **Today (EXISTS)**, a mismatch answers `409` with only the string detail `reading_state_stale_revision: …`. The client refetches with `GET` and rebases on what it reads (rev 8.7 corrects the earlier claim).
- **Extension (NEW, rev 8.7).** The 409 body becomes `{reason: "reading_state_stale_revision", current}`, where `current` is the GET row, so the client can rebase without a second request. Until that ships, the refetch is the contract.

The rev-2 `/documents/{id}/position` routes and the rule that "the event log is authoritative" are **withdrawn**.

**Derived emission.** After the row commits, the server emits a typed `reading.position {owner_user_id, document_id, anchor_ref, page_index, revision}` on `read-<documentId>`, where thread state needs one, with `owner_user_id` server-derived. The emission is best effort. A failed emission is logged, never fails or retries the PUT, and never becomes a second writer. A reader of the event treats it as a hint that the row confirms.

It ships only together with the kind-aware state rule of §1.2, so reading threads read `idle`. Today position lives in `sessionStorage` per browser tab.

### 1.15 Rights and owner preconditions (pre-multi-user; single-operator today)

These routes take no owner filter today:
- `GET /research/{id}/artifact.html` and `twin-notes.html` (`artifact_routes.py:309-322,565-607`)
- `GET /trajectory/{id}`
- `GET /investigations`
- `/write/folders` and `/write/blocks/search`
- the `/twins` routes

Every route this contract adds is owner-scoped from day one. The existing ones are listed as pre-multi-user work (G7).

### 1.16 Schema sequencing

`EVENT_SCHEMA_VERSION` went 40 → 41 with B0: `investigation.branched`, `investigation.branch_abandoned`, `investigation.reserved`, `QuestionEscalatedToResearchPayload.launched` and the chase-halt reason `branch_not_recorded`, all unmerged on the wave-5 export branch. It carries a renumber-at-merge preflight; D2's 40 → 41 plan is superseded. Each later lane B wave takes **one** sequenced bump, with codegen in the same commit: W1 (rename, `thread_seen`, `branch_abandoned`, `reading.position`, `launch.refused`), W2 (flag lifecycle, `thread.turn`) and W3 (merge, revision decisions, companion receipt, `investigation.cap_halted`). Graph-schema changes ride with their wave (rev 6): the tab rows, counters and number registers in W1, and the member-table rebuild in W3. `source_merge.*` strings are retired, never typed.

### 1.17 Answers to Part 2's open questions

- **Q-A1:** server-side per account (§1.6).
- **Q-A2:** WebSocket push plus durable catch-up (§1.7, §1.13).
- **Q-A3:** the compound terms (§1.0, §1.12).
- **Q-A4:** `BranchAnchor` (§1.4).
- **Q-A5:** `kind: reading`, promoted in place (§1.5).

### 1.18 Lane B delivery order (matches ROSTER first use)

| Step | Delivers | Unblocks |
|---|---|---|
| **B0** (shipped at `6e395c0c8`, in codex review) | §1.3 branch at every spawn site, parent-exists integrity, schema v41 | the logic tree; the export-cluster lineage blockers |
| **W1** | §1.5 project registry with aggregates and `thread_seen`; §1.2 `ThreadSummary` (counts, kind-aware state, `.parquet` enumeration, id integrity); §1.6 tab rows and allocation; non-book documents served to the reader (lane A F8); §1.14 position; §1.3 `branch_abandoned` and the backfill; broadcast wiring (§1.7) | MS-03/04/05 |
| **W2** | §1.13 flags with actor and read intent plus the consent lifecycle; §1.8 ask tier 0, then tier 1; §1.9 context items and estimate; the rights-gated pack (§1.10) that the ask tiers need | MS-06/07 |
| **W3** | §1.2 threads by document and project; §1.10 merge; §1.12 companion document (after the rights branches land); §1.11 revision flow; §1.13 cap ledger, durable inbox and `SpawnFn` | MS-08/09/10 |

Every step ships the same way:
- red-first tests and mutation proofs;
- the declared ruff and mypy gates and the 8 required contexts;
- a codex gpt-6-sol ACCEPT;
- merging only through the Antiek Nudge train.

**Ownership to settle before mutation** (evidence in `ground/lane-b.json` `ownership_overlaps`):
1. The supersession of the closed PR #712 as owner of the spawn and merge seams is **recorded** on the board (portfolio `research-reading-vertical`, 2026-09-24).
2. Sequence behind the wave-5 export cluster on `build_body`, `context` and `cascade_session`.
3. Coordinate `/thought-partner` with PR #3278 and codex-r15.
4. Take the owner binding from PR #3011, and rebase spawn changes after codex-r24.
5. The D2 feedback/agent_work implementation has no owner. Ask-this-thread stays on the investigation trajectory and leaves `feedback_threads` to D2.

---

## Part 2 — UI states (lane A)

**Revision 8.10 (2026-09-27).** Part 2 is reconciled to Part 1 revs 8 to 8.10, one revision per GLM round, and signed with rev 8.10. What changed:
- **§2.11** is the rev-8 surface for C6. It covers:
  - the reformat flow, its estimate and binding, and the header with the plural model identity;
  - the five classes plus `generated` (connective templates only), `unsupported`, `unsourced`, unresolved spans, unplaced bites (listed below the document) and "Your edit";
  - lexical support below 0.35 per UAX #29 sentence;
  - hash drift as a read-time overlay with "was:";
  - probe to the core;
  - fork through the revisions route (full block text, `{carried, edited}`, rebase on `revision_moved`);
  - "Adopt as this project's reading version", with its route and refusal copy;
  - Write `informs` with its replace-all route and errors.
- **§2.10** adds `served · unsourced`, and a null origin renders the same way.
- **§2.9:** a reading-state 409 refetches and rebases (today it carries a string detail).
- **§2.2:** the restore PUT sends the retired node back unchanged (`pruned_at` included; equal on side, kind, ref, branch_origin and opened_by). `retired[]` is read in the tree's transaction, and paging stops on a null `next_before`. The body is bounded at 1,000,000 bytes, and depth is unbounded.

**Revision 7 (2026-09-26).** Part 2 is reconciled to Part 1 rev 7, which absorbed the cockpit decisions C1–C5 and the seams S1–S8 lane A signed. What changed:
- Every tab node has a `side` (left = document tabs, right = agent tabs). One tree per mode holds both panes, and the active tab is tracked per side.
- An agent-opened left tab records `opened_by` and the passage it came from.
- Retired tabs restore from their complete node.
- The right pane is named as such, never "companion". Its tabs are views of one thread each, plus the Findings tab.

The rev-7 requests are at the end; none blocks rev 7.

**Revision 6** reconciled Part 2 to Part 1 rev 6, which applied R5-1 to R5-6:
- Every item, entry, hunk and answer binds its named `GatedText` field (`content`, `insert`, `answer`, `excerpt`). §2.10 follows the rev-6 discriminated shape: `cite_only` is for quotations only, and each source carries its own gate.
- A carried-over hunk decision keys on `hunk_digest`.
- `stop_reason` drives every stopped state. Only threads the daily cap admitted (diligence, daemon and reformat threads, rev 8.1) can stop at the cap, so an island never offers "Raise today's cap".
- Tab numbers start from the server's `next_child_index`. A `409 number_conflict` is an ordinary rebase, not a bug.

**Revision 5** reconciled Part 2 to Part 1 revs 4 and 5, which applied R4-1 and R4-2:
- Every rights-bearing text renders from one `GatedText` rule (§2.10).
- Launch admission holds nothing, and the consent copy says so (§2.8).
- `stopped` carries its reason, including `cap_reached` and `cap_overshoot`.
- Merge members read `merge_pending` or `merge_failed` until the merge commits (§2.4).
- Restoring from history uses the server's `retired` descriptors (§2.2).
- To-read keeps flags whose document can't be resolved (§2.9).
- Changing the cap has its own route (§2.8).

The rev-5 requests are at the end. None blocks rev 5: each names the reading lane A builds against until it is answered.

**Revision 3** added these states:
- a thread tab's `no_record` and capacity-only `abandoned` (§2.2)
- anchor remap picks that persist (§2.3)
- a resumable merge (§2.5)
- revision 1 on first use (§2.6)
- `consent_stale`, the launch hold and `reserved` (§2.8)
- the withheld excerpt (§2.10)

**Revision 2** changes from rev 1:
- Counts, spend and estimates are nullable, and each null has a designed rendering.
- Tab numbers are allocated by the server and never reused.
- Merge and fork follow the rev-2 commit flows, including their stale and conflict states.
- A shared cite-only item state (§2.10) covers every rights-gated text.
- The inbox is durable, with cursor catch-up.

Each entry gives the surface, its states, its required fields (**Needs:**), and the events it reacts to.
Every surface designs every state. An unknown is never drawn as a zero or as empty: that rubric veto was
closed on five pages by W7.

**Nullable rendering rule.** A `null` count, spend or estimate renders as "—", with its reason on hover and on focus. The reasons are "Still counting", "Price unknown for this model" and "Ledger unreachable". It never renders as `0`, `$0.00` or a blank.

### 2.1 Workstation (shared by all three motherships, D1/D5)

- **States:**
  - `listed` (in the sidebar or switcher)
  - `active` (open in the current mothership)
  - `archived`
- **Needs** (§1.5):
  - `workstation_id`: the project id ("project" is the data noun, "workstation" the UI noun). It is the same in Research, Writing and Reading.
  - `title`, `order`, `pinned`, `archived_at?`
  - `created_at`, `updated_at`
  - `kind`: `project | reading`, with `primary_document_id?` (Q-A5). "Add to project…" promotes a `reading` project in place.
  - `active: {left, right}`, per mothership, from that mothership's tab row (§1.6, rev 7)
  - `thread_counts`: `{running, needs_you, done_unseen}`. `done_unseen` falls as threads are opened (§2.4 seen). Its one authority is `thread_seen` by trajectory position (§1.5); the inbox's `seen_at` never drives it.
  - `spend_today`: `{cents, currency} | null`, rendered by the nullable rule ("Ledger unreachable")
- **Reacts to** (broadcast on `WS /ws/events`, §1.7):
  - a thread changes state: refetch the counts
  - a typed Folder event from another tab or device (rename, reorder, pin, archive): last write wins, shown as a quiet toast

### 2.2 Tab (a node in the branch tree, D6)

- **Tree fields (Needs):**
  - `parent_tab_id?`: null for a root tab. Depth is unbounded.
  - `side`: `left | right` (§1.6, rev 7). Left nodes are document tabs (the core material); right nodes are agent tabs, each a view of exactly one thread, plus the Findings tab. A child inherits its parent's side, with two exceptions that are always left: an agent-opened document (`agent`), and a reformat result (`derivation`, rev 8). A derivation's parent is the source document's left tab, or in writing the active section.
  - `branch_origin?`: `{document_id, anchor, kind}`, where `anchor` is a `BranchAnchor` (§1.4). This is the exact passage the branch was opened from, and `prefix+u` returns there.
    `kind` in the UI is footnote, reference, citation, island, research, manual, agent or derivation (§1.6, rev 7). The backend value for "island" is `selection` (§1.0). `derivation` arrives with rev 8 (C6).
  - `opened_by?`: `{thread_id, agent_kind}`, required when `kind` is `agent` (S1). The node opens in the **current mode's** tree and never switches the mode; when the agent's reply named a passage, the node's `anchor` is that passage's.
  - `hier_number`: for example `3.2.1`. Lane A computes it as `<parent's hier_number>.<k>`. `k` starts at the parent's server-maintained `next_child_index` in the latest snapshot, and rises by one for each further local spawn under that parent (§1.6, rev 6). The server registers it on the PUT, and it is final once accepted. It is never reused, and a closed or pruned node keeps its numbers: the register still names its `tab_id`.
  - `child_order[]`
  - `last_visited_child_id?`
  - `pruned_at?`: prune is a soft close. A pruned subtree stays recoverable from history, and restoring the same `tab_id`s reclaims their own numbers (R3-1, applied in rev 3).
- **Addressing:**
  - `public_number` is allocated by `POST /projects/{id}/tabs/{mothership}/allocate {tab_id}` at spawn. It is workstation-wide and never reused, even after close. The call is idempotent per `tab_id`, so a retry from any device returns the same number (§1.6, rev 6).
  - **`numbering`**: the allocate call is in flight, or it failed.
    - The tab opens at once, with a dim placeholder in the number slot.
    - It is reachable by `prefix+n`/`p`, `prefix+w` and the mouse, but not by `prefix+<digit>`.
    - Lane A never invents a number locally, because a local guess could collide with another device's allocation.
    - A failed allocate retries with the next snapshot write, and the tab is never blocked.
  - **`numbered`**: the number is shown and addressable.
- **Operations:**
  - `spawn_child(parent, origin, kind, ref)`: allocate the number, then add the node. The hier number is computed from the snapshot, `retired_numbers` included. On a 409 it is recomputed before acceptance, so every local spawn survives with a number unique under its parent (R3-5).
  - `close(tab, mode: prune|lift_children)`, undoable for 10 s. The close is held locally through the undo window and written with the next snapshot only after the window lapses, so other devices never see a close that was undone. An undo after the write is also safe: the same `tab_id` reclaims its own numbers (R3-1).
  - `refocus_subtree(tab)`: view-only, no server write
  - `renumber`: never. Numbers are addresses.
- **Kinds:**
  - Left: `reader(doc_id)` and `document(write_doc_id)`.
  - Right: an agent tab of kind `research`, `dialogue`, `reformat`, `diligence` or `island`. Each holds a `thread_id` and never content (§1.2, rev 7; S2). Also on the right: `findings(project_id)`, the project companion document (§1.12; S7), and `flags(project_id)`.
  - Writing's right pane holds `block(block_id)` tabs (C5).
- **Mothership:** `mothership: research|writing|reading` (D5). A tree belongs to one mothership inside a
  workstation. Switching mothership shows that mothership's forest for the same workstation.
- **Tab ≠ branch (agreed with lane B, 2026-09-24).** The tab tree above is *navigation state*. It is server-side per account (Q-A1), written through the single-writer API, and never a parallel store.
  - A *research branch* is *provenance*: a durable dependency from a parent investigation to a child (§1.3), plus `origin {kind, document_id?, anchor?}`.
  - The branch is written into the PARENT's log as the last step before the child starts. It does not prove the child ran; the child's own log says that.
  - An island's parent is the document's reading thread, `read-<documentId>` (§1.3 spin-research). So the islands a reader tab spawns hang under that thread in the logic tree.
  - A tab of kind research, island or thread points at a `thread_id`. Its `parent_tab_id` mirrors the branch edge when it was spawned from research.
  - **Pruning or closing a tab never deletes a branch.** The companion document's "how I got here" reads the branch record, not the tab tree. The `agent` and `derivation` origins are navigation state only, and write no branch (§1.6, rev 7).
- **States:**
  - `open`
  - `focused`
  - `closed`, with undo for 10 s. On main, `LemonToast` has no undo slot (lifetimes 4/6/8 s), so MS-04 adds one with a 10 000 ms lifetime. Prune is the most destructive navigation act, so its undo outlives the longest existing toast.
- **Thread-backed tab states.** The tab shows its thread's state (§2.4). Three more states can only be reached from a tab:
  - `no_record`: `GET /investigations/{id}` finds no record. This is a branched child whose first event never landed, or whose log was lost. The logs cannot tell these apart, so the branch stays a live dependency and fails closed (§1.3).
    - The tab says "No record that this thread started. Its branch stays open until it is reconciled." It offers Close, which closes the tab and never the branch.
    - It is never shown as running, and never called "abandoned".
  - `abandoned`: the parent's log holds `investigation.branch_abandoned` for this exact launch. It is written only by the refusing request, with `reason: capacity_refused`, or by an operator reconciliation with an attesting reason (§1.3). The tab says "Didn't start: no capacity", or gives the reconciliation's reason, and offers Close.
  - `spawn_refused`: the spawn answered `422 parent_investigation_not_found` or `409 reservation_parent_mismatch` (§1.2, §1.3). The tab becomes a failed stub that keeps the origin passage, so nothing the operator selected is lost.

  A tab never points at a reserved-only id, which is not listed and answers `not_found`. Reservations surface on the question that holds them (§2.8).
- **Needs:**
  - `tab_id`
  - `public_number` (above)
  - `kind` plus a ref id
  - `title` (derived from the ref)
  - `mothership`
  - `pane`: `{docked_kind?, docked_ref?}`
- **Persistence** (§1.6):
  - `GET /projects/{id}/tabs/{mothership}` returns `{tree, active: {left, right}, version, next_child_index, retired: [{closed_at, close_mode, node}]}` (§1.6, rev 7; R7-1).
  - `PUT` takes `{tree, active: {left, right}, expected_version}`. Lane A applies operations locally and writes debounced whole-tree snapshots.
  - A `422 tab_origin_invalid` (a bad origin kind, or an `agent` node without `opened_by`) is a lane-A bug: log it and never show it to the operator.
  - **`409 {current}` state (`rebasing`):** another device wrote first. Take `current`, replay the pending local operations on top, and PUT again.
  - If a replayed operation targets a tab the other device closed, drop that operation and show one quiet toast ("A tab was closed on another device"). Never show a modal, and never lose a local spawn.
  - **A pending spawn whose parent closed remotely** re-attaches to its nearest surviving ancestor, or becomes a root (§1.6, rev 5). It keeps its origin, ref and thread and takes a fresh `hier_number`. The toast names where it went ("Moved under 3.2: its parent was closed on another device"). Restoring that parent later does not move it back.
  - **A replayed prune never closes a tab this device has not seen.** Children another device added under a tab this device pruned are lifted to the pruned tab's parent, with the same quiet toast. A prune closes only what the operator was looking at.
  - **Restore from history** reads the server's `retired[]` entries, `{closed_at, close_mode, node}`, where `node` is the complete tab node as it left the tree (§1.6, rev 7). It is never a local guess. The 200 most recent come with the tree, read in the same transaction as the tree (rev 8.8). Older ones page through `GET …/retired?before=`; paging stops when `next_before` is null, which includes an exactly full last page (rev 8.8). A restored tab reclaims its own numbers. If its parent is not open, it attaches to the nearest surviving ancestor, as above.
  - **The restore PUT** (rev 8.8, synced with LB-2 #3530; precision rev 8.9) sends the retired node back unchanged, `pruned_at` included, and the server clears it. "Unchanged" means equal on `side`, `kind`, `ref`, `branch_origin` and `opened_by`; a mismatch is `422 tab_tree_invalid` naming the fields, a lane-A bug. The node may differ only in `parent_tab_id` and `child_order` (the re-attach rule above), `last_visited_child_id`, and a refreshed `title` or `pane`. Lane A never strips `pruned_at` itself. It never sends `pruned_at` on a tab it is not restoring: a `422 tab_tree_invalid` for that is a lane-A bug, logged and never shown. The tree body is bounded at 1,000,000 bytes of canonical compact UTF-8 JSON, and depth is unbounded (§2.2). A tree that nears the bound is a lane-A bug to report (retired nodes live in `retired[]`, not in the body), never something the operator is asked to fix.
  - A tab-version bump broadcast from another device (§1.7): with no pending local operations, refetch and apply silently. With pending operations, rebase as above.
  - A 409 carries its reason (§1.6, rev 6), and both reasons rebase the same way, silently, with the toasts above:
    - `version_stale`: another device wrote first.
    - `number_conflict`: another device's accepted spawn moved a parent's counter past a pending local number. The pending spawn is renumbered from the new counter before it is accepted.
  - A `number_conflict` naming a tab this device restored from history would mean lane A sent a number the register gives another tab. That one is a lane-A bug: log it and rebase. It is never shown to the operator as their error.
  - A workstation survives a device change the way a herdr session survives a detach.

### 2.3 Island (A3)

- **States:**
  - `idle`: an affordance on the selection, nothing spent
  - `composing`
  - `estimating`: cost shown before spend, from `POST /investigations/estimate` (§1.9). It resolves one of two ways:
    - `estimate_ok` shows `{cents, basis}`.
    - `estimate_unavailable` shows the reason ("Price unknown for this model") and never a figure. Launch stays possible behind an explicit "Cost unknown" confirmation. An island is started by the operator, and the §1.13 cap reserves only diligence launches.
  - `running`: streaming process steps and a partial outcome
  - `answered`
  - `failed`: an honest reason, with Retry
  - `refused_capped`: the ACU gate refused the launch before start (`launch.refused`, §1.13). It is a response state, not a thread state, and it shows the gate's reason with a link to its setting.
  - `stopped`, shown with its `stop_reason` (§1.2, rev 6):
    - `user` reads "Stopped".
    - `cancel` reads "Cancelled".
    - `budget` reads "Its research budget ran out", and offers "Research further" (§2.4 tier 1) with its own estimate.
    - `null`, from an older log, reads a bare "Stopped".

    An island is metered by the ACU gate before start and by its own research budget while running. It never stops with `cap_reached` or `cap_overshoot`, which only the cap-admitted diligence, daemon and reformat threads can (§1.13, rev 8.1), so it never offers "Raise today's cap".
  - `kept`: collapsed to a margin mark
  - `promoted`: now a thread tab
- **Needs:**
  - `anchor`: a `BranchAnchor` (§1.4): `document_id`, `source_locator?`, `region_id?`, `quote?`, `prefix?`, `suffix?`, `page_index?`. **Anchor states are UI states too:**
    - `resolved`: the island sits on its passage
    - `ambiguous`: the quote matches more than one place after re-projection, or matches once but its context changed. `POST /documents/{id}/anchors/remap` returns the candidates with a `score` (§1.4).
      - Show them in score order and let the operator pick; never jump silently.
      - The pick writes `anchor.resolved` on the owning thread, so it is asked once, not on every open.
    - `unresolved`: the passage is gone. Keep the island, marked "passage changed", with the stored quote shown.
  - Remap runs when the document's current text no longer matches the anchor's `source_locator.text_sha256`. A matching hash is `resolved` with no call.
  - Correction (§1.1.1): `passage_research` anchors by page today. `page_index` is that legacy read path.
  - `workstation_id`
  - `attached_context[]`: `context_items[]` (§1.9: `doc | insight | thread | note`). **The attach UI does not ship until §1.9 lands,** because unknown fields are silently dropped today.
  - `model_choice`: the #3400 dropdown value
  - `estimate`: `{cents, basis, status: ok|unavailable, reason?}` (§1.9). It is re-requested, debounced, when the model or the attached context changes.
  - `thread_id`, once it has started. **An island is a thread**, created when its first question is asked, and branched from `read-<documentId>` with origin `selection` (§1.3). Agreed with lane B: `kept` and `promoted` are *presentation* states (margin mark vs tab), stored on the tab or anchor, not on the investigation. `merged_into` *is* investigation-level lineage (a merge record).
  - `process_steps[]`: `{ts, kind, text, source_refs[]}`, a projection of `GET /trajectory/{id}` (§1.2), never a second store. Code, routes and events never say "island" (§1.0); only lane A's components do.
  - `outcome`: `{text, claims[], source_refs[]}`, with `claim_count | null` and `source_count | null` (§1.2) under the nullable rule
- **Reacts to:**
  - stream events for its thread
  - cancel
  - model change before the question is sent

### 2.4 Thread list and "ask this thread" (A4)

- **States (list):**
  - `loading`
  - `empty`: "No threads on this document yet". Shown only after a real answer.
  - `error`: with Retry
  - `ready`
- **States (row):**
  - `queued`
  - `running`
  - `needs_you`
  - `done`, with an `unseen` marker until the thread is opened (`thread_seen`, §1.5)
  - `failed`
  - `stopped`, with its `stop_reason` (§1.2, rev 6): `user`, `cancel` and `budget` read as in §2.3. `cap_reached` and `cap_overshoot` read as in §2.8, and only those two offer "Raise today's cap". They can only occur on threads the daily cap admitted: diligence, daemon and reformat threads (§1.13, rev 8.1). `null` reads a bare "Stopped".
  - `idle`: a `reading` thread, which has no terminal event, so it never shows as working
  - `merge_pending(thread_id)`: the member recorded `merged_into` but the merged thread's start event does not exist yet (§1.10, rev 4). The row says "Merging into …", links the merged thread, and is not yet shown as merged.
  - `merge_failed`: the merge commit was refused. The member is exactly as it was and says "Merge didn't complete".
  - `merged_into(thread_id)`: only once the merged thread's start event exists

  `capped` is not a row state: it is a pre-start refusal, shown on the launch surface and in the inbox (§1.1.4). Agreed with lane B: the state is *derived* by the one server helper keyed by `kind` (§1.2), never from a second state column.
- **Row kinds** (§1.2): `research`, `cascade_session`, `cascade_leaf`, `reading`, `dialogue` and `reformat` (rev 7). A cascade leaf nests under its session. Attribution buckets are never rows.
  - A `dialogue` row shows the agent conversation's title and last turn time. Its states are `idle` between turns and `running` while a turn streams. It has no terminal state, like `reading`.
  - A `reformat` row shows the source title, the mode and the bound model. Its states follow §2.11's engagement: `running` while generating, `done` once committed, `failed` with the reason, and `stopped` with `cap_reached`/`cap_overshoot`.
  - Both open their right-pane agent tab (§2.2). A reformat row also offers its derivation's left tab once committed. The list and the tab read the same thread, so neither bypasses the other.
- **Seen:** opening a thread sends `POST /investigations/{id}/seen {through_event_id}`, carrying the newest event id the view rendered. The server stores that event's trajectory position and only ever moves it forward (§1.5), so a late or out-of-order send is harmless.
- **Needs** (§1.2 `ThreadSummary`):
  - `thread_id`, `title`, `kind`, `state`
  - `anchor?`
  - `scope`: `document(doc_id)` or `workstation(workstation_id)`, read through `GET /investigations?document_id=` or `?project_id=`
  - `model`
  - `spend_cents | null`
  - `last_activity_at`
  - `parent_thread_id?`
  - `merged_from[]`
  - `claim_count | null`, `source_count | null`. Both are null while the log is incomplete, and render by the nullable rule ("Still counting").
- **Ask this thread:**
  - composer states `idle`, `sending` and `continuing`, with the same stream as an island
  - **Needs:** §1.8.
    - Tier 0: `POST /investigations/{id}/ask {question, context_items[]}`, a turn persisted as `thread.turn`. The composer labels it a conversation turn. The turn's `answer`, and each of its `context[]` items, is a `GatedText`, rendered by §2.10 (§1.8, rev 6).
    - Tier 1: `POST /investigations` with `continue_from_parent: true`, a new research run, which writes a branch. The composer labels it "Research further" and shows its own estimate (§1.9).
    - The two tiers are distinct actions with distinct cost states, never merged into one ambiguous button.

### 2.5 Merge (A4, lane B B2)

- **States:**
  - `selecting`: two or more threads
  - `previewing`
  - `conflicts_shown`
  - `framing`: the operator writes the merged thread's question, which the commit requires
  - `merging`
  - `merged`
  - `preview_stale`: the commit answered `409 preview_stale`. The digest covers the gated text, its pointers and the `content_class` of every source (§1.10), so a changed thread, a changed source or a changed right all land here. Lane A re-previews at once, keeps the selection and the question, and says "Something in these threads or their sources changed since the preview". It never commits a preview the operator has not seen.
  - `failed`: a `503` means the merge started but a member's record failed, and nothing has run. The copy is "The merge didn't finish. Nothing has run yet." Retry uses the same idempotency key, which resumes from `thread.merge_started` rather than starting over (§1.10).
  - `merged` is shown only when the response confirms the merged thread's start event. A partial merge never reads as merged.
  - `suggestion`: an automatic merge offered through the inbox (`thread.merge_suggested`). It opens in `selecting` with the suggested members pre-selected, and it is never applied silently.
- **Needs** (§1.10):
  - `POST /threads/merge/preview {thread_ids[]}` returns:
    - `preview_digest`
    - `items[{item_id, content: GatedText, origin_thread_id}]` (§1.10, rev 6), each `content` rendered by §2.10
    - `conflicts[{claim_a, claim_b, reason}]`
  - The commit is `POST /threads/merge {thread_ids[], preview_digest, question, idempotency_key}`.
    - Lane A mints the `idempotency_key` when the operator presses Merge, and reuses it for every retry of that press.
    - A new preview mints a new key.
    - The key is bound to the request identity: the owner, the members, the digest, the reviewed conflicts and the question (§1.10, rev 4). So `409 idempotency_conflict` means lane A reused a key for a different merge. That is a lane-A bug: log it, mint a fresh key and re-preview. It is never shown as the operator's error.
  - The result is a `thread_id` with `merged_from[]`. Each member records `merged_into` and is never otherwise mutated.

### 2.6 Merge into document → fork (A4, lane B B4)

- **States:**
  - `choose_target`: a Write deliverable in this workstation.
    - `derived_asset_id = "write:<deliverable_id>"` is the only target (§1.11).
    - Write blocks are not a merge target; in W3 they gain thread provenance instead.
    - A workstation with no deliverable offers "Create a deliverable from this thread" (`POST /write/deliverables/from-investigation`).
  - `drafting`: `POST /derived-assets/{asset_id}/merge-drafts {source}`
  - `diff_review`: accept or reject, per hunk.
    - Every hunk starts undecided, and nothing is decided by default.
    - Commit stays disabled, with the reason shown, until every hunk is decided.
    - The decisions go to `POST /merge-drafts/{draft_id}/review`, which returns the `review_id`.
  - `committing`: `POST /derived-assets/{asset_id}/revisions {review_id, acknowledgement: "new_revision", idempotency_key}`. Only the explicit commit button sends the literal (R3-6).
  - `forked`: the new revision and its lineage (`GET /derived-assets/{asset_id}/revisions`). The original revision is untouched and one click away.
    - The first operation on a deliverable writes revision 1 from its current content (§1.11). The lineage labels it "Revision 1, as it was before the first merge", so the first fork always has an original to return to.
  - `base_moved`: the CAS refused the commit with `409 revision_moved` because the current revision moved after the review.
    - Say "The document changed while you reviewed", then re-draft against the new revision.
    - A decision carries over only to a hunk with the same `hunk_digest`: sha256 over its anchor and canonical `insert` (§1.11, rev 6). Every other hunk comes back undecided.
  - `failed`
- **Needs:**
  - `source`: `{thread_id} | {companion_entry_id}`
  - `target_asset_id`: `write:<deliverable_id>`
  - from the draft: `draft_id`, `base_revision_id`, `proposed_hunks[{hunk_id, hunk_digest, anchor, insert: GatedText}]` and `evidence_manifest` (§1.11, rev 6). Each hunk renders by `insert.gate` (§2.10), and `insert.text` is the sanitized HTML:
    - Each hunk shows the provenance classes it carries (§2.11's labels). `generated` is only validator-passed connective text; `unsupported` is its own class and holds the export back (rev 8.5). Classes survive the merge into Write (§1.11, rev 8.1).
- **Serve-time gate for Write bodies (rev 8.4).** Every view of a deliverable's body re-checks each member against its source's gate as it stands now: the editing view, the rendered projection, shared and public pages, and exports. Lane A renders two block states from it:
  - **Source withdrawn.** A quoted block whose source is no longer servable shows the server-built citation marker in place of the quoted words, labelled "Source withdrawn: shown as a citation". The rest of the block renders normally.
  - **Held back.** A block whose member is unresolved, legacy or unsupported shows no text, reading "Held back: <reason>". It keeps the §2.6 fixes, and the owner's editing view keeps the block visible so it can be fixed.
  - The owner's editing view uses the owner-read gate; shared, public and export views use the public gate. The same block can therefore read differently in the editor and on a shared page, and the editor labels it ("Shown to readers as a citation").
  - A changed source gate changes the render at once (renders are keyed by the members' gate fingerprint), so lane A never caches body text client-side past a gate change.
    - **An unsupported claim holds the export back** (rev 8.3). A merged `unsupported` member withholds the deliverable revision's export, like an unresolved one, until it is fixed. The revision reads "Held back: an unsupported claim in block N". Each block names its fixes: delete the block, rewrite the claim, or attach evidence. Attestation alone never clears it (rev 8.4). Generated connective text (member kind `generated`) passes.
      - **Attach evidence** (rev 8.5): `POST /derived-assets/{id}/blocks/{block_id}/evidence {source: {document_id, anchor}, expected_revision_id, idempotency_key}`. The block's unsupported sentences are re-scored one by one.
      - The answer's per-sentence scores drive the block view. Sentences that now pass lose their "Unsupported" mark and gain the evidence. Sentences that still fail stay marked, each with its score, so the operator sees exactly which sentence needs work.
      - A `409` on `expected_revision_id` rebases and re-asks.
    - When the source revision is `mostly_generated`, the review needs an explicit confirmation: "Most of this is generated or unsupported. Merge it anyway?" The confirmation is sent on the review, as typed `acknowledgements: ["mostly_generated"]` on `POST /merge-drafts/{id}/review`, and bound into its `review_id` (rev 8.5). The commit keeps its literal `acknowledgement: "new_revision"`. Without the confirmation, Commit stays disabled with that reason. A `422 acknowledgement_required {missing}` on commit is a lane-A bug.
    - `served`: the insertion, with its sources.
    - `cite_only`: the hunk offers the citation alone. Accepting it inserts a citation marker the server builds from `insert.source_refs`, never quoted text.
    - `withheld`: the hunk cannot be accepted. Its accept control is disabled with the reason shown, and it can only be rejected. A `422 hunk_not_acceptable` on review would mean lane A sent one; it is a lane-A bug, never the operator's error.
  - `review_id`
  - `fork_id` = the new revision id, and `parent_version_id` = `parent_revision_id` (§1.11). Correction §1.1.2: this is not an HTML-projection lineage and not `create_document_version`.
  - `lineage`: the revision chain
  - The commit envelope is exactly `{review_id, acknowledgement, idempotency_key}`. A 422 on legacy fields is a lane-A bug, not a user error.
  - Source merge is retired, so the UI never offers it.

### 2.7 Findings tab and companion rail (D3, C4; data noun: companion document, §1.0/§1.12)

In the cockpit, the project companion document is the right pane's **Findings** tab (§1.12, rev 7; S7). The per-evidence companion rail stays inside the reader. Both are views of one model.

- **States:**
  - `loading`
  - `empty`: "No findings yet". Shown only after a real answer.
  - `error`
  - `ready`
  - `stale`: the server's `state` says so. The causes are newer thread events, a membership change, or reading or answer events on the document (§1.12). The copy is "Newer activity since this was written", and it offers Refresh.
  - `refreshing`: `POST …/companion-document/refresh` is in flight. The current entries stay readable underneath. On success, the receipt's `content_hash` replaces the old one.
  - `partial`: "n of m threads summarised", from `summarised_thread_count` and `total_thread_count` (R2-2, in rev 2). The threads not yet covered are listed by name, one click each.
  - `unavailable_until_rights`: the rights branches have not landed (§1.12 precondition). This is an honest state, never an empty one.
- **Needs:** `GET /projects/{id}/companion-document` (tab) and `GET /documents/{id}/companion-document` (rail). Both return `{entries[], content_hash, covered: {thread_id: through_event_id}, summarised_thread_count, total_thread_count, state}`.
  - `entries[]`: `{entry_id, kind: claim|open_question|insight, content: GatedText, confidence?, thread_ids[], doc_ids[], updated_at, process_ref}` (§1.12, rev 6). The rev-5 `text` and `source_refs[]` live inside `content`. Each entry renders by `content.gate` (§2.10), never by whether a text field is empty.
  - the process link for each entry: `process_ref` (thread id plus event id), one click deep to that step of the trajectory
  - a per-document filter, for the rail
  - a link to the agent-facing evidence base (lane A renders only this link)

### 2.8 Flags, consent and the attention inbox (D4, lane B B5)

- **Flag states:**
  - `flagged`
  - `reserved`: a question escalated to research whose child id is reserved but has not launched (§1.3). It says "Research reserved, not started", and starting it goes through consent like any diligence launch.
  - `consent_pending`: shows the model, the estimate `{cents, basis}`, and whether the launch fits.
    - X is the conservative maximum: the estimate × 1.5, or the tier's maximum when larger (§1.13). The sheet compares it with `daily_cap_cents − spent_today_cents − held_today_cents`, which is the ledger's own `remaining` (R4-1, applied in rev 4).
    - The copy is exactly "Starts if $X of today's cap is free; it pauses if the cap runs out" (§1.13, rev 5). Admission reserves nothing, so nothing on the sheet says "held".
    - When X does not fit, the sheet says so before Accept ("$Y of today's cap is free") and offers "Raise today's cap". Accept stays available, because the server's admission is the authority and a refusal lands as `refused_capped`.
    - When `spent_today_cents` or `held_today_cents` is null, it shows "Free cap today: unknown", and Accept is disabled with that reason: admission cannot be checked against an unreachable ledger.
    - When the estimate's status is `unavailable`, consent is not offered. It shows the reason and "Choose a priced model" (R3-2).
  - `queued`
  - `running`
  - `done`
  - `failed`
  - `consent_stale`: the launch answered `409 consent_stale` because the target moved after consent: the thread's head event, or the anchor's text hash (§1.13). The copy is "This changed since you agreed", with the fresh estimate and one step to agree again.
  - `stopped`, with its reason (R5-4):
    - `cap_reached`: other work used today's cap after admission. It offers "Raise today's cap".
    - `cap_overshoot`: a provider billed past a bounded call. It shows the billed amount, because the overshoot is never hidden.
  - `refused`, with a reason from `question.diligence_refused`:
    - `refused_capped` offers "Raise today's cap"
    - `unavailable` offers "Choose another model"
    - `failed` offers Retry
  - `declined`

  A consent is single-use. A retry after any refusal is a fresh consent: one step, with a fresh estimate. A double press is safe, because the launch consumes the consent idempotently by `consent_id`.

  **Accept is two calls behind one press.** `POST /flags/{flag_id}/consent` returns the `consent_id`, then `POST /flags/{flag_id}/launch {consent_id}` runs it (§1.13).
  - If the launch call fails after the consent landed, Retry re-sends the launch with the same `consent_id`, so a retry never asks twice.
  - Decline is `POST /flags/{flag_id}/decline`, and flagging is `POST /flags`.
  - Run-now on a diligence flag always opens this consent sheet. Watch-for-later's run-now never bypasses it.
- **Inbox item kinds** (§1.13):
  - `thread_done`
  - `thread_needs_you`
  - `flag_consent`
  - `refused_capped` (rev 1's `cap_reached`, renamed to match Part 1)
  - `run_stopped`: a diligence, daemon or reformat run the cap halted mid-flight (reformat engagements are cap-admitted, §1.13 rev 8.1), sourced from `investigation.cap_halted`. Its `detail` is `{reason: cap_reached | cap_overshoot, hold_cents, billed_cents?}` (§1.13, rev 6). The row offers "Raise today's cap", and an overshoot shows `billed_cents` next to the hold.
  - `merge_suggestion`
- **Needs:**
  - `flag_id`: the `question_id`
  - `intent`: `read | diligence`
  - `actor {kind: user|agent, id}`, server-derived; lane A never sends it. The label is derived too: "You" for the operator's own id, otherwise the agent's role name.
  - `target`: `{anchor}`, `{question_id}`, `{insight_id}`, `{claim: {event_id, chunk_id?, edge_id?}}` (R3-4, applied in rev 3), or `{document: {document_id, anchor?}}` for a to-read flag (rev 5). Flag-a-claim sends the retrieval event that stated the claim, plus its pointer.
  - `reason`
  - the consent lifecycle: `question.diligence_consented`, `…_declined`, `…_launched` and `…_refused` (§1.13)
  - `daily_cap_cents`, `spent_today_cents | null` and `held_today_cents | null`, from `GET /settings/budget`
  - "Raise today's cap": `PUT /settings/budget/daily-cap {cents}` (§1.13, rev 4). It takes effect for the next admission and re-opens an exhausted day. Lowering the cap below spent + held blocks new work but never cancels running work. The settings copy says exactly that.
  - the flag list: `GET /flags?intent=&project_id=`
  - the inbox:
    - `GET /inbox?after=<cursor>&limit=` returns `{items[{item_id, kind, ref, created_at, seen_at?}], next_cursor}`, and `POST /inbox/{item_id}/seen` marks an item seen.
    - The socket only nudges a refetch. On reconnect, lane A fetches from its last cursor, so nothing is missed while offline.
    - `item_id` is the source event id, so a nudge and a catch-up never duplicate a row.
    - An item is unseen while it has no `seen_at`. That drives only the inbox's own badge, never the workstation's `done_unseen` (§1.5).

### 2.9 Reading home and the to-read queue (D5)

- **Doors:** `continue`, `to_read`, `new`.
- **Continue — Needs** (§1.14):
  - `GET /reading/continue` and `GET /books/{id}/reading-state` read the `reading_state` table, the store of record (§1.14, rev 8.1).
  - The position is synced per account. It replaces today's per-browser-tab `sessionStorage` value.
- **Writing the position.** `PUT /books/{id}/reading-state {page_index, anchor_ref?, revision}` is the only writer (§1.14, rev 8.1). `revision` is the one lane A last saw. On `409 reading_state_stale_revision` (today a string detail; rev 8.7), lane A refetches with GET, rebases on the fresh row and never loses the newer position. It does not depend on a `{reason, current}` body until that extension ships. Lane A still writes sparingly:
  - once scrolling has settled for 10 s
  - on leaving the document: a tab switch, `visibilitychange` to hidden, or `pagehide` with `keepalive`
  - never when the anchor is unchanged

  That is at most one write per 10 s of reading, and "continue" still lands on the last passage read.
- **To read — Needs:**
  - `GET /flags?intent=read`. Every read flag is returned. One whose document cannot be resolved carries `document: null` and `reason: unresolved_document` (rev 5). Its row says "Couldn't find the document for this", shows the flag's reason and target, and offers Dismiss. It is never dropped silently.
  - `actor {kind, id}`, with the label derived as in §2.8
  - `reason`
  - `workstation_id?`
  - `target: {document_id, anchor?}`
  - `created_at`
- **To read — states:**
  - `loading`
  - `empty`: "Nothing waiting". Shown only after a real answer.
  - `error`
  - `ready`
- **Standalone book (use case i):** a `kind: reading` project with `primary_document_id`, promoted in place by "Add to project…" (Q-A5, answered in §1.5).

### 2.10 Gated text (shared by 2.3, 2.5, 2.6, 2.7 and every excerpt)

Every rights-bearing text a route returns is a `GatedText` (§1.2, rev 6; `origin` rev 8.2): `{text | null, gate: served | cite_only | withheld, reason | null, origin: source | operator | generated | unsourced, source_refs[]}` (`unsourced` rev 8.8), where each source ref carries its own `gate` and `reason`. It binds as `excerpt`, `answer`, `context[]`, `content` and `insert`.

The shape is discriminated:
- `served`: text set, reason null.
- `cite_only`: a quotation whose sources are unresolved or not servable. A citation stands in for the words.
- `withheld`: nothing stands in. A synthesis (the thesis excerpt, an archived synthesis, a companion entry drawn from a body) is only ever `served` or `withheld`, never `cite_only`.

When sources mix, the most restrictive gate wins.

Lane A renders from `gate` and `reason`, never from whether `text` is empty, and never drops an item:
- `served`: the text, with its source refs. When `origin` is `generated` it carries the "Generated" label, and when it is `operator` it reads as the operator's own words (§1.2, rev 8.2).
- `served · unsourced` (rev 8.8): model text with no source that the connective validator did not admit. It is served to its owner and always reads "Unsupported: no source", with the same mark as §2.11's unsupported class. It is never labelled "Generated". A revision containing it holds its export back, and the export control says why ("Held back: unsupported text"). Before rev 8.8, such text arrived with a null origin; lane A renders a null origin the same way and never guesses a class.
- `cite_only · not_servable`: no text. It shows the source's title and locator and says "This source can be cited here but not quoted." The reference opens the source wherever the operator may read it.
- `cite_only · unresolved`: no text. It shows the stored pointers with the dangling treatment, which pairs colour with a text label and never relies on colour alone: "Source not found. The citation is kept; its text is not." It is never smoothed into a normal citation.
- `withheld · lineage_unreconciled`: an excerpt from a thread that predates branch records and has not been reconciled and attested (§1.3, rev 4, operator call #6). It shows no excerpt and says "Excerpt held back until this thread's history is reconciled. Its notes and artifact are unaffected."
- `withheld · unresolved`: evidence-derived text whose sources cannot be recovered. It reads "Held back: its sources can't be found".
- `withheld · not_servable`: a synthesis over sources that can't be served here. It reads "Held back: a source can't be shown here".
- **Which source held it back.** A non-served text lists its `source_refs` as small chips, each with its own gate and reason. The operator sees exactly which source withheld or reduced the text to a citation, and each chip opens that source where the operator may read it.
- Every list header counts each kind, for example "12 items, 3 cite-only, 1 held back", so a preview never implies it shows everything.

The rev-4 `excerpt: {state, reason?}` marker is a projection of the excerpt's `gate` (R5-1, applied in rev 6). The excerpt is a synthesis, so the marker and the gate never disagree.

### 2.11 Reformat, provenance and probe to the core (C6; rev 8 — T6/T7 ruled 2026-09-26, signed with rev 8)

The operator's paragraph 2, in the cockpit. The engagement lives in the right pane, the result opens on the left, and the line between the author's words and everything else is visible at every span (§1.11a).

**Where the engagement lives (C5, rev 8.2).**
- In research and reading, it is a right-pane agent tab of kind `reformat`.
- In writing, the right pane is the block outline, so the engagement runs in the AI sidecar. Its result opens as a left `derivation` child under the active section (T4).
- The states below are the same in both places.

**The reformat engagement (right-pane tab, or the Write sidecar).**
- `composing`: the prompt, plus the optional reading time (minutes), focus items (themes, questions, insights, or a highlight) and mode (condense, expand, reorder, explain).
  - A model picker offers the lineup's models (`params.model_choice`). When nothing is picked, a line names the resolved reformat default ("Uses <model>").
  - Changing the model, or a changed default, fetches a new estimate. The model is never swapped silently (§1.11a, rev 8.2).
  - **Binding (rev 8.3).** The estimate binds nothing. With no explicit choice, the model resolves once at admission.
    - A retry under the same idempotency key replays that first generation, even if the default has since changed.
    - A new Generate press is a new key, and uses the current default.
    - The tab names the bound model once admitted.
- `estimating`: `POST /reformats/estimate {source, params}` returns `{estimate_cents | null, max_cents, reason?, assumptions}` (§1.11a, rev 8.1).
  - The tab states "Starts if $<max_cents> of today's cap is free" (§2.8's admission copy), with the estimate beside it.
  - With no figure, it shows the reason and never a number, and generating needs an explicit "Cost unknown" confirmation.
  - `too_large` reads "This source is too large to reformulate in one pass". `source_not_servable` reads as in failed below.
- `generating`: the thread is running, and its process steps stream as in §2.3.
- **Requests are idempotent.** Lane A mints an `idempotency_key` per press of Generate and reuses it on every retry of that press. A `409 idempotency_conflict` is a lane-A bug, never shown to the operator. The generation's own states are `requested → admitted → generating → committed | failed`.
- `proposed`: the agent asks "Open it on the left?" (`reformat.open_proposed`). One key accepts: Enter while the tab is focused. The result opens as a `derivation` left child in the current mode. Declining keeps an "Open" control on the tab, so nothing opens without the operator.
- `opened`: the tab shows which left tab holds the result, one key away.
- **Honest reading time.** When `reading_estimate.shortfall` is set, the tab says so: "The source can't honestly fit 15 minutes; this reads in about 22." Nothing is padded or cut silently.
- **One failure vocabulary (rev 8.3).** Each reason has one state and one copy:
  - **Refused before any thread exists** (an HTTP answer to Generate; nothing was started):
    - `too_large` (422): "This source is too large to reformulate in one pass."
    - `source_too_deep` (422): "This is a reformulation too many times over. Reformulate an earlier version."
    - `source_not_servable` (403): "Its source is held back, so it can't be reformulated."
    - `refused_capped` (402): "Today's cap has no room for this." Offers "Raise today's cap".
    - `idempotency_conflict` (409): a lane-A bug, logged and never shown.
  - **Failed after admission** (`reformat.failed`; the thread exists and shows the reason):
    - `unavailable`: "The model isn't available." Offers "Choose another model".
    - `interrupted`: "It stopped before finishing. Nothing was saved." Retry reuses the same key.
    - `failed` with its detail: the detail in plain words. Offers Retry.
  - **Stopped by the cap mid-generation** (`investigation.cap_halted`): the thread reads `stopped` with `cap_reached` or `cap_overshoot` (§2.8), never "failed", and offers "Raise today's cap".
  - **Legacy** (`409 legacy_generation`, or a revision whose `state` is `legacy`): a reformulation made before provenance tracking. It stays readable, and its tab says "Made before provenance tracking. It can be read, but not probed, merged or reformulated until it's upgraded." The probe, merge and reformulate controls are disabled with that reason.

**The derivation left tab (reader view `drv-<generation_id>`).**
- **Header:** "Reformulated from <source title> · <mode> · <model actually used> · revision n", with the source one key away (it opens the core document as a sibling left tab). The model identity comes from `reformat.generated.model`, never an operator default. Since rev 8.10 that is `{providers[], model, dispatch_event_ids[]}`: there is one model, named once, and the providers are listed after it only when there is more than one ("<model> via A, B"). One dispatch event per generation window is reachable from the revision's receipt. `cost_cents` renders by the nullable rule.
- **Holders.** A reformulation of a reformulation resolves rights to its core sources (§1.11a, rev 8.1). When they have several holders, the header shows the holder set ("From 3 sources"), each opening its core, and never a single holder.
- **Mostly generated.** When sourceless plus unsupported words exceed 15% of the revision (`mostly_generated`, rev 8.2), a banner reads "Most of this is generated or unsupported text" above the first span. The revision earns no attribution.
- **Held back:** when the source's live gate withholds it (a takedown or reclassification), the whole view renders §2.10's withheld state: "This reformulation is held back because its source can no longer be shown."
- **Spans by class (A8).** Every span carries its class as a text label and a glyph, never colour alone. A persistent legend names all five classes.
  - `author_verbatim`: "Author". Upright text with a left rule, following the quotation gate (`served | cite_only`).
  - `llm_compressed`: "Condensed". `llm_expanded`: "Expanded".
  - `research_supplemented`: "Research", linking its thread.
  - Text whose `GatedText.origin` is `generated`: "Generated" (§1.2, rev 8.2). The server grants `generated` only to text matching one of its six non-assertive connective templates (`connective-templates/v2`, rev 8.6), such as "This section covers {X}.". Any other sourceless text is `unsupported`, and so is a span scored before rev 8.6 (`validator_version: null`, fail-closed). Lane A never labels model text "Generated" on its own inference. Generated text never states a claim.
  - A claim that cannot cite a source: "Unsupported", with the probe answer "No supporting source". It is never passed off as "Generated".
  - Text whose `GatedText.origin` is `unsourced` (rev 8.8): "Unsupported: no source". This includes a template sentence whose slot of 4 or more words appears verbatim in a core source's served text, because that slot is source text. Such a sentence is never "Generated" and never shows "from your prompt".
  - **Unresolved spans** (rev 8.9; every span is exactly `placed` or `unresolved`): an `unresolved` span has a locator and no class. It is text that no bite covers, which only a legacy backfill produces. It shows no class label and no glyph, only "Unresolved: this passage couldn't be placed", with the dangling treatment of §2.10. It is never given a guessed class. It weighs nothing in attribution and holds the export back, like `hash_ok: false`. The legend lists it after the five classes.
  - **Unplaced bites** (rev 8.9, `unplaced_bites[]`): bites from the original reformulation that have no locator. They cannot be drawn in the text, so they are listed below the document under "N passages from the original reformulation couldn't be placed". Each item shows its declared class as declared ("declared: Condensed"), its source chips, and the held-back mark. Each one holds the export back, and the export control counts them ("Held back: 2 passages couldn't be placed"). The list is never collapsed to nothing: zero unplaced bites shows no list.
  - **Your edits in a fork** (rev 8.9): an operator's edit in a new revision is an `origin: operator` bite with no class. It reads "Your edit" in the operator's own-words treatment (§2.10), weighs nothing in attribution, and is never marked unsupported. Carried-forward spans keep their class, and earlier revisions never change.
  - The provenance lens (a key-sheet toggle) shows the labels inline at every span boundary. Otherwise they show on hover and on focus. The spans are focusable in reading order, so the lens works from the keyboard.
- **Weakly supported.** An `llm_*` span whose `support.score` (`rougeL-f1/v1`, two decimals) is below 0.35 gets a dotted underline and the label "Weakly supported", with its lexical support score and method on focus (rev 8.4 names it lexical support; the UI never says "entails"). A null score with reason `not_computable` reads "Support unknown", never "supported". Both marks mean the span earns no attribution, and merges into Write as an `unsupported` member that holds the export back (rev 8.5); its focus text says so. Support is scored per sentence (UAX #29), so a failing sentence arrives as its own small span, and a span's score is the lowest of its sentences.
- **Where the spans come from (rev 8.3; `unplaced_bites` rev 8.9).** `GET /derived-assets/{id}/revisions/{rev}/spans` returns `{revision_id, mostly_generated, unplaced_bites[{bite_id, derived_text_sha256, declared_class, source_refs}], spans[{span_id, locator, hash_ok, contribution_class, declared_class, support{score, method: "rougeL-f1/v1", tokenizer: "uax29/icu-<ver>", reason?}, origin, unsupported, validator_version, content: GatedText}]}` (tokenizer rev 8.5; `validator_version` rev 8.6: `connective-templates/v2` on generated spans, null on sourced spans). A sentence longer than a span's word cap arrives as its own span, and a sentence is never split.
  - Each span renders from these fields: the label from `origin`, `contribution_class` and `unsupported`, and the gate from `content`.
  - A `404` reads "This reformulation no longer exists". A `409 legacy_generation` reads as Legacy above. A `422 revision_not_committed` shows the generating state, never an empty document.
- **Integrity.** A span with `hash_ok: false` reads "Passage changed" (unresolved), never "verified". The revision's receipt shows its mismatch count ("2 verbatim claims did not verify").
  - **Hash drift is read-time** (rev 8.10). A drifted span arrives as `state: "unresolved"`, with null top-level `contribution_class` and `origin`. Lane A draws no class for it: it renders as an unresolved span, weighing 0 and holding the export back.
  - **What it was.** Its focus detail shows the stored values from `as_recorded {contribution_class, declared_class, origin}` (present only on drifted spans) as "was: Condensed", so the operator sees what the passage was before it drifted. Lane A never renders the recorded class as current.

**Probe to the core.**
- Selecting span(s) offers "Probe the source" (the island key `prefix+a` / `ctrl+alt+a`). It creates a research thread branched from `read-<core document>` of the span's first core ref (§1.11a, rev 8.1), and that thread appears as a right-pane `island` tab. When the core can't be opened (`probe_core_inaccessible`), the offer reads "The source of this passage can't be opened, so it can't be probed" and starts nothing.
- Every answer is §2.10 `GatedText` that resolves to a **core** span, or reads "Unresolved" in words. Each resolved snippet opens the core document at that passage as a left tab (origin `agent`, `opened_by` the probe thread).
- "Show the core" on any span opens a peek card: `GET …/spans/{id}/sources`, rendered as GatedText, with "open on the left".
- A span with no source shows its generation record (the prompt and model that produced it) instead of a core snippet.

**How evidence is presented (T7, ruled 2026-09-26).**
- An answer follows its `presentation_mode`:
  - `quoted` shows inline quotes.
  - `cited_quietly` shows small citation markers.
  - `metadata_only` shows clean prose with an always-present "N sources behind this answer" disclosure that lists `cited_refs`, then the rest of `retrieved_refs`.
- An answer never looks unsupported when it was supported.

**Fork and merge (T6, ruled 2026-09-26).**
- "Fork" commits a new revision, and the original stays one click away in the lineage.
  - **The route** (rev 8.10): `POST /derived-assets/{asset_id}/revisions {base_revision_id, blocks: [{block_id, text}], idempotency_key}`.
    - Lane A sends the full new text of each changed block, never a class, never model text, and never unchanged blocks.
    - The server splits the sentences itself: an unchanged sentence carries forward with its class, and anything else becomes an operator edit ("Your edit").
  - **The answer** is `{revision_id, carried, edited}`. The fork's receipt reads "n sentences kept, m your edits", from those counts.
  - **Moved base.** `409 {reason: revision_moved, current_revision_id}` shows "This changed elsewhere". The edited blocks are kept locally, the view rebases on `current_revision_id`, and the operator re-applies with one key. An edit is never lost.
  - **One idempotency key** is minted per press of Fork and reused on retry.
- "Adopt as this project's reading version" sets the project pointer (rev 8.7):
  - The route is `PUT /projects/{project_id}/reading-versions/{source_document_id} {derived_asset_id, revision_id, expected_version}`, where 0 means none yet. "Stop using this version" is `DELETE …?expected_version=`. The answer carries the new `version`.
  - **Copy per refusal**, in the server's check order:
    - `404 project_not_found`: "This project no longer exists".
    - `422 source_not_in_project`: "Add the source to this project first", with an Add action.
    - `422 not_a_reformulation_of_source`: a lane-A bug; never offered for another source.
    - `422 revision_not_committed`: "Still generating".
    - `403 source_not_servable`: "Its source is held back".
    - `409 version_stale`: refetch and show "Changed elsewhere", then ask again.
  - **Opening that source in that project** shows the adopted revision, labelled "This project's reading version", with one key to show the original source. A takedown of the source still withholds it (§1.11a live gate). The source is never written.
- "Merge into a deliverable" is §2.6's merge-drafts flow, with members keeping their classes.
- There is no "merge into the book".

**Attribution (G4).** Nothing about money appears in the UI. Attribution is telemetry-only until the §9.0 gates open.

**Write informs (S5)** is part of §2.6's block tabs. A block tab's ordered document list is assigned by drop and by key, and reordered by key.
- **Saving (rev 8.7).** `PUT /derived-assets/{asset_id}/blocks/{block_id}/informs {informs: [{document_id, anchor?}], expected_revision_id, idempotency_key}` replaces the whole list, and the order is the ordinal.
- `409 revision_moved` rebases on `current_revision_id` and re-applies the operator's order.
- `422 informs_invalid {index, detail}` marks the offending row in place: more than 50 entries, a duplicate document, an unreadable or unknown document, or an anchor naming another document. The list is never silently trimmed.
- **Generated sentences** can show "from your prompt" or "from your focus" on hover, from their `slot_source` (rev 8.7). A template slot only ever comes from operator text. Only admitted `generated` sentences show it. A sentence whose slot of 4 or more words matches served source text is `unsourced` (rev 8.8) and shows "Unsupported: no source" instead. Topic labels of 1–3 words stay admitted.

---

## Open questions

- **Q-A1:** ~~is tab and workstation layout state server-side per account, or per browser?~~ Answered: server-side per account, via the single-writer API (lane B, 2026-09-24).
- **Q-A2:** answered in §1.7 and §1.13: `WS /ws/events` nudges, with durable cursor catch-up.
- **Q-A3:** answered in §1.12. The bare word has five meanings, so use the compound terms only.
- **Q-A4:** answered in §1.4: `BranchAnchor` with `TextLocator`, remapped as `resolved | ambiguous | unresolved`. Lane A designs all three states (2.3).
- **Q-A5:** answered in §1.5: `kind: reading` plus `primary_document_id`, promoted in place.

### Rev-2 requests from lane A (applied in rev 2)

- **R2-1:** `selection`, not `island`, in `origin.kind`. Applied in §1.3.
- **R2-2:** `summarised_thread_count` and `total_thread_count` on the companion document. Applied in §1.12.

### Rev-3 requests from lane A (applied in rev 3)

- **R3-1:** restoring the same `tab_id` reclaims its own numbers; a different `tab_id` never takes a retired one (§1.6).
- **R3-2:** an unpriced estimate means consent is not offered (§1.13).
- **R3-3:** `gate` and `cite_reason?` on every pack item (§1.10).
- **R3-4:** the claim target `{claim: {event_id, chunk_id?, edge_id?}}` (§1.13).
- **R3-5:** `hier_number` is client-computed, server-validated and final once accepted (§1.6).
- **R3-6:** `acknowledgement: "new_revision"` and `409 revision_moved` (§1.11).
- **Citation note:** the resolvers are marked NEW on the wave-5 export branch (§1.10).

### Rev-4 requests from lane A (applied in rev 4)

- **R4-1:** `held_today_cents` on `GET /settings/budget` (§1.13).
- **R4-2:** an explicit excerpt marker (§1.2). Rev 5 then generalised it to `GatedText`.

### Rev-5 requests from lane A (applied in rev 6)

- **R5-1:** the excerpt marker is a projection of `GatedText.gate` (§1.2).
- **R5-2:** `content`, `insert`, `answer`, `context[]` and `excerpt` are named, with the mixed-source rule (§1.2).
- **R5-3:** the `run_stopped` inbox kind, from `investigation.cap_halted` (§1.13).
- **R5-4:** `ThreadSummary.stop_reason` (§1.2).
- **R5-5:** a server-maintained `next_child_index` per parent (§1.6).
- **R5-6:** `allocate {tab_id}` is idempotent, over append-only number registers (§1.6).

### Rev-7 requests from lane A (applied in rev 7, per lane B's signature note)

- **R7-1, the GET shape still says `active_tab_id`.** §1.6's route line returns `{tree, active_tab_id, …}` while storage is now `active: {left, right}`. Lane A reads the route as returning `active: {left, right}`, per §1.6 storage.
- **R7-2, the retirement node omits the new fields.** `node_json`'s field list does not include `side` or `opened_by`, both rev-7 node fields. A restored agent-opened tab needs both. Lane A reads `node_json` as the whole node including them.
- **R7-3, one tree per mode, or one tree for both panes?** §1.6 says "one tree holds both panes, so a project switch swaps both (T8)", while T9 (whether research and reading share one forest) is open. Lane A reads it as one tree per mode holding both of that mode's panes: a project switch swaps both panes of the current mode. Please say so explicitly.

## Signatures

- **Lane B (types and endpoints):** signed rev 7, 2026-09-26, Antiek Sweep v2 (a59f7aa2), including lane A's alignment requests R7-1 to R7-3. Rev 7 applies codex's audit of rev 6 and absorbs C1–C5 with the seams S1–S8 lane A signed; S5, S6 and S8 land in rev 8 (C6).
- **Lane B (types and endpoints): signed rev 8.10, 2026-09-27, Antiek Sweep v2 (a59f7aa2).**
  - Rev 8 carries the operator's paragraph 2 as C6: reformulation with span-grain provenance, probe-to-core, fork and merge per T6, and presentation per T7.
  - **The audit.** GLM-5.3-Flash (via glmf-codex, a different lineage) audited it through eleven rounds; revs 8.1 to 8.10 closed each round's findings. Round 11 ACCEPTed rev 8.10 with zero new defects and every prior item confirmed resolved against the code: LB-2 at `ee6867a11` (PR #3530) and the repaired reformat lineage at `c0845e327` (PR #3527).
  - Lane A reconciled Part 2 to each revision, through 8.10.
  - **From here on:** any change to a type, route or state is a new dated revision that both lanes re-sign. Rev 9 is gated on both signatures plus a different-lineage audit ACCEPT (the rev-9 co-sign gate in Part 1's header).
- **Lane A (UI states):** signed rev 7, 2026-09-26, Antiek Nudge v2 (236c36bd). Part 2 is reconciled to Part 1 rev 7. Revs 1–6 were signed earlier.
  - Tab nodes gain `side` and `opened_by`, with the full branch-origin kind set, and agent opens stay in the current mode (S1, G3).
  - `active` is per side.
  - Retired entries carry the complete node.
  - The right pane's kinds follow S2, with Findings as S7.
  - R7-1 to R7-3 are non-blocking.
  - A citation-only change from the MiMo audit of rev 7 needs no re-sign; a change to a type, route or state does.
- **Lane A (UI states): signed rev 8.10, 2026-09-27, Antiek Nudge v2 (236c36bd).**
  - **What was reconciled.** Part 2 was reconciled to each of Part 1's revisions 8 to 8.10, as each round's findings closed; the Part 2 revision note above lists the result. GLM-5.3-Flash's round 11 ACCEPTed rev 8.10 with Part 2 in scope ("gaps that would make Part 2 … unbuildable"), and the Part 2 it read is byte-identical to this one.
  - **What lane A builds against rev 8 now:** §2.11's surfaces (A7 and A8 of the cockpit plan) over LB-4b and LB-5, and the tab adapter over LB-2 (#3530 at `ee6867a11`; A2a).
  - **Rev 9 opens** under the co-sign gate. Lane A's Part 2 inputs are `THREAD-CONTRACT-REV9-PART2-DRAFT.md` (§A deltas to §2.1–§2.5 and §2.9; §B new sections §2.12–§2.20; §C requests of Part 1) and the rulings recorded in `DECISIONS.md` on 2026-09-27: the delegated decisions D-P, D-A and D-M, the naming reconciliation and the lane-A defaults 1–8.
  - **Nothing builds against rev-9 seams** until both lanes sign rev 9 and a different-lineage audit ACCEPTs it.
