> Reopened and corrected after the owner identified three explain leaks and the
> ordinary-export regression in 560e46267. Earlier ACCEPT/test records below are
> historical evidence, not acceptance of that revision. See the direct-reader
> correction and reader inventory for the current scope.

# Research-only purchases distinguish the agent from the owner

Decision: option B from `BLOCKER-research-only-principal-seam.md`, directed by the
operator on 2026-09-20. This implements the §9.0 principal decision and carries the
rights-state work from `88dbbf454` together with its missing access boundary.

## Contract

| Caller | Policy tag | Research-only chunks |
|---|---|---|
| Agent deriving research | `private_research` | Available |
| Authenticated paying owner | `operator_only` | Withheld |
| Public retrieval | `attribution_eligible` | Withheld |
| Unknown tag | Any unrecognized value | Withheld |

The canonical SQL predicate enforces this before `chunk_text` enters a result.
`/corpus/search` and `/books/{id}/ask` inherit the rule without checking each hit.
TurboPuffer's privileged paths use the same DuckDB predicate. The search result
shape stays compatible. Ownership still controls `personal_reading`; it cannot
allow an owner to retrieve a `research_only` body.

`ANTIEK_RESEARCH_POLICY_TAG` accepts `private_research` or
`attribution_eligible`. Unset or blank preserves the public default. The research
loop rejects `operator_only` and unknown values before retrieval. Enabling private
research remains an explicit server configuration choice.

The existing rights-state constants, serve refusals, citation metadata, quotation
policy, and corpus audit are retained. A work no longer than its quotation cap
returns no quotation, avoiding disclosure of an entire short work. The attribution
comment now names the actual exclusion union.

## Event transport also has two principals

Inspection found a second path after the retrieval split: Loop One persists
`EvidenceRetrieveRequestedPayload.chunks_block` and `subgraph_block`. Raw trajectory
and WebSocket serialization exposed those agent inputs to the owner.

The two trajectory endpoints and the WebSocket serializer now use one owner event
projection. Evidence-request payloads expose only an allowlist of progress and
request-identity fields, with empty context blocks. Unknown future context fields
are withheld. The rule applies to historical events without relying on producer
metadata. Internal replay and agent handlers keep the original event. Derived
result events retain their existing representation.

This is a separate event-transport boundary, not a per-search-hit redaction rule.
New outward event transports must use the owner projection. Raw event logs are
server-side agent data, not an owner export format.

The initial full-export refusal was too broad: every ordinary Phase 2 investigation
contains raw request context. The corrected owner export projects copied event
logs using the same owner projection, retaining derived output. The database
snapshot still returns 403 if it contains research-only documents. Agent replay
work in `note_taker_windows` is exported as an empty table because its stored
prompts can survive source deletion. The manifest calls this an owner projection,
not an operational backup. Source database rows and event files remain unchanged.

## Direct readers and buyer credentials

The retrieval gate does not govern SQL readers that resolve a chunk by ID. All
three explain routes now preserve citation identity while selecting NULL for
research-only text. MCP, wrestling, multimedia selection, and sidecar voice-note
references enforce an owner body predicate before using licensed source bodies.

Buyer BYOT credentials are an owner destination. A no-network capture proved that
private agent context reached that dispatch boundary. Retrieval now downscopes for
buyer-provider evidence calls. Dispatch also rebuilds the typed request from
canonical owner-readable chunk rows, checking ownership and takedown status.
Historical body and graph blocks never become buyer-provider inputs merely because
their headings name readable chunks. Unclassified, missing, and licensed sources
refuse before dispatch. Server-agent processing retains private research access.

The reader inventory and its regression check live in
`docs/diagnostics/research-only-principals/reader-inventory.json` and
`tools/lint/chunk_reader_census.py`. The accompanying `reader-audit.md` distinguishes
runtime probes from code inspection and trusted host maintenance. It supersedes
the earlier claim that citation projections had been checked comprehensively.

## Failure dossier

The rejected lane admitted `research_only` on both privileged tags. Actual
HTTP responses contained `PUBLISHERCONFIDENTIALPROBE` in search snippets and book
citations. The new regression tests reproduced both leaks before the fix, plus
the owner-tag chunk access. The two trajectory tests then reproduced raw context
disclosure before transport integration. Logs are under
`docs/diagnostics/research-only-principals/`.

## Handoff

### Env Card

- Worktree: `/Users/slimydog/Antiek/worktrees/research-only-principal-split`
- Branch: `fix/research-only-principal-split`
- Base: `f24981db2bde8ce2fb88158fc54460cfd168c294`
- Python: worktree `.venv/bin/python`, shared platform environment, Python 3.12.13.
- No successful live LLM, publisher, payment, or remote retrieval call. The
  broader legacy evidence-bridge tests attempted a provider connection and failed
  DNS resolution; the same four failures reproduce on the original lane.

### Not proved

- Deployment and production data migration were not run.
- This does not prove that arbitrary model-generated prose obeys negotiated
  quotation terms. The checked boundaries are source retrieval, direct serving,
  citation projections, raw event context delivery, owner-provider evidence input,
  and owner export projection. The inventory identifies evidence per reader.
- This does not authorize publisher activation, payouts, or purchase checkout.
- New owner event transports need the same projection contract.

### Status

Implemented locally; verification results below. Not merged or deployed.

### Files touched

The rights-state files from `88dbbf454`, canonical retrieval gate, research-loop
configuration boundary, owner event projection and its three API integration
points, full owner export refusal, regression tests, §9.0 and this decision record. The lane's unrelated
`HANDOFF.md` replacement was not carried over.

### Milestones

- [x] Reproduce owner search and Q&A leaks with actual response bodies.
- [x] Split agent retrieval from owner retrieval in the SQL gate.
- [x] Validate research configuration and retain agent-positive controls.
- [x] Reproduce and close raw-context trajectory/WebSocket disclosure.
- [x] Refuse full owner exports containing source bodies or agent context.
- [x] Preserve the rights-state and derived citation behavior.


### Scope map

| Entry point | Verified behavior | Test in `tests/test_research_only_principals.py` |
|---|---|---|
| Owner corpus search | Sentinel absent from HTTP response | `test_owner_response_withholds_research_body[search]` |
| Owner book Q&A | Sentinel absent from response and provider prompt | `test_owner_response_withholds_research_body[ask]` |
| Canonical SQL retrieval | Agent succeeds; owner/public/unknown denied | `test_principal_gate_reads_real_chunks` |
| TurboPuffer privileged adapter | Same canonical gate; no remote index | `test_turbopuffer_owner_and_agent_use_canonical_gate` |
| Loop One configuration | Invalid principal fails before retrieval | `test_loop_rejects_invalid_principal_before_retrieval` |
| Both trajectory routes | Context withheld; internal replay retains it | `test_owner_trajectory_withholds_agent_inputs` |
| WebSocket | Owner frame withheld; internal handler receives body | `test_owner_websocket_withholds_context_but_agent_handler_receives_it` |
| Full owner export | Source snapshot denied | `test_owner_full_export_refuses_research_source` |
| Historical JSONL/Parquet export | Context snapshot denied | `test_owner_full_export_refuses_historical_agent_context` |
| Quotation policy | Short work never returned whole | `test_quotation_never_returns_short_work_whole` |

### Gate results

Recorded in `verification.txt` beside the diagnostic logs. The test command clears
inherited operator-auth configuration for legacy unauthenticated tests; owner-path
fixtures explicitly enable real bearer authentication. Initial legacy tests failed
with 401 under the inherited environment, including on the rejected lane.

### Decisions mid-flight

Owner event projection was required because fixing retrieval alone still let agent
inputs travel to the owner through the event feed. A short source receives no quote
when a cap would permit its entire body.

### Assumptions surfaced

`private_research` is a server-selected principal, not an owner-supplied access token.
Owner reading endpoints select `operator_only` from authenticated request state.
Derived graph notes remain readable under the existing provenance rules.

### Steelman rejected alternative

Returning `content_class` and redacting each snippet would preserve every current
result shape and offer fine-grained rendering. It would leave future renderers able
to disclose raw chunks by omission. The SQL gate prevents those chunks from reaching
owner retrieval in the first place.

### Open questions

Negotiated quotation enforcement over generated prose belongs to the artifact policy
boundary. It is not proved by source-body gating or by a model prompt.

### Next sprint can start when

The complete branch, including the rights state and principal split, passes integration
review. Do not land the rejected rights-state commit alone.

### Out-of-scope temptations

No payment routing, publisher activation, provider selection, graph schema migration,
or deployment changes.
