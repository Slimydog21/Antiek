# Midnight Oil claim admission v1

Date: 2026-07-13
Status: accepted for staged implementation
Program: `ANT-MOCA`

## Decision

Every newly issued Midnight Oil spend consent carries `ResearchAcceptancePolicy` v1 inside `JobConsentConfig` and therefore inside the existing canonical config hash. V1 is a closed safety floor, not a set of operator-tunable booleans:

- every insight and every non-empty normalized `output_text` paragraph requires exact local evidence before graph admission;
- exploratory questions remain explicitly unverified and operational-only;
- public-web receipts without a locally canonical document/chunk/hash chain remain operational-only;
- unsupported output is retained as honest HTML rather than discarded;
- policy-absent legacy rows remain `legacy_unverified` and are never auto-upgraded.

The complete v1 policy is:

| Field | Required literal value |
| --- | --- |
| `policy_version` | `1` |
| `required_coverage` | `insights_and_output_paragraphs` |
| `exploratory_questions` | `operational_only` |
| `external_receipts` | `local_canonical_chunk_required` |
| `unsupported_output` | `retain_operational_only` |
| `legacy_rows` | `legacy_unverified` |

New consent issuance rejects a policy-absent config. Policy-absent configs retain the pre-policy canonical hash shape only so an already-issued legacy receipt can be reconstructed and audited without fabricating a new binding. This compatibility is reconstructive, not admission authority.

## Durable authority

The complete six-field policy is flattened into the closed owner payload. It is never rehydrated from a version number plus runtime defaults. Once consent is issued, the immutable queue options carry the same six fields together with `consent_receipt_id` and `consent_config_hash`. The worker reconstructs one `JobConsentConfig` and requires exact policy equality plus matching owner and queue receipt/config identities before the owner can enter `RUNNING` or the queue can expose a dispatchable lease.

The API deliberately retains its crash-repair ordering: signed consent is claimed, owner authority moves to `QUEUED`, and then the queue row is inserted idempotently. Requiring a queue row before that transition would make the existing claim-to-CAS and CAS-to-enqueue repair protocol impossible without a transactional outbox redesign. Here, “before lease” means before a dispatchable or paid lease. A worker may still acquire a quarantine lease solely to remove an invalid row from the queue and prevent starvation; quarantine cannot create a budget hold, retrieval, or provider dispatch.

Policy-absent legacy owner or queue authority is non-dispatchable. Receipt reconstruction remains available for audit, but legacy absence never becomes v1 authority.

## Canonical identity

All identity payloads use UTF-8 JSON with sorted keys, compact separators, `ensure_ascii=False`, and `schema_version = 1`.

Claim IDs use the exact domain string `antiek.midnight_oil.claim` and hash `domain`, `schema_version`, `job_id`, `step_key`, `claim_class`, zero-based `ordinal`, and `normalized_text`. Paragraph normalization converts CRLF/CR to LF, trims outer whitespace, splits on one or more blank lines, preserves order, and retains normalized paragraph text.

Source-receipt IDs use the exact domain string `antiek.midnight_oil.source_receipt` and hash `domain`, `schema_version`, `document_id`, `chunk_id`, `hash_scope`, `content_hash`, and `canonical_url`. Titles and all other display metadata are excluded from authority.

## Claim evidence v1

Every new returned step persists `claim_evidence_schema_version = 1` and a complete ordered census of its non-empty normalized output paragraphs, non-empty insights, and non-empty exploratory questions. Each record carries the canonical claim ID, class, zero-based class ordinal, normalized text, one of the closed states `supported`, `unverified`, or `exploratory`, and an ordered tuple of canonical source-receipt IDs.

`supported` is valid only for an insight or output paragraph with at least one unique reference to a receipt attached to that exact step. An omitted mapping becomes `unverified`; it is never linked to the first or nearest receipt. Exploratory questions carry no receipt references and remain `exploratory`. Duplicate claim IDs, duplicate source-receipt IDs, duplicate mappings, unknown claim ordinals, unknown receipt references, forged stored receipt IDs, and partial or oversized versioned records reject.

The live synthesizer returns a closed JSON envelope containing output text, insights, questions, and explicit support mappings by claim class and ordinal. Receipt IDs are included in the untrusted evidence envelope so the synthesizer can cite exact identifiers. Malformed output cannot create a returned-content checkpoint. Provider dispatch may already have occurred, so this failure follows the existing unknown-paid-outcome reconciliation path rather than pretending the call was free.

Rows without `claim_evidence_schema_version` remain reconstructable legacy evidence with an empty claim census. They are not upgraded from step-level receipts. The graph evidence hash includes the version and complete claim census; graph admission semantics remain the responsibility of SPR-04.

## Rejected alternatives

- One citation per step does not prove each claim.
- Embedding or string-similarity linking manufactures provenance.
- Defaulting legacy rows to v1 invents consent that was never recorded.
- Rejecting the entire operational deposit destroys useful partial work.

## Operator-visible launch and admission contract

The launch surface displays the complete v1 acceptance summary beside the price ceiling before spend approval. The browser enables approval only after validating the exact closed six-field object, then sends `acceptance_policy_version = 1` as an explicit acknowledgement. Omission is rejected; the server never supplies a default acknowledgement. The canonical `JobConsentConfig` hash is exposed as `research_brief_hash`; after approval, `approved_research_brief_hash` must match it and the policy panel becomes read-only.

Operational retention and graph admission remain two separate lanes in the interface:

| Machine state | Operator copy | Verified knowledge? |
| --- | --- | --- |
| `pending` + pre-terminal job state | Research has not finished | No |
| `pending` + terminal `none` | No research result returned | No |
| `pending` + `receipt_only` | Operational receipts retained; no research result returned | No |
| `pending` + returned output | Operational output retained; graph admission pending | No |
| `complete` | Admitted to the knowledge graph | Yes |
| `refused` | Operational HTML retained; graph admission refused | No |
| `failed_reconcile`, policy drift, or deterministic conflict | Reconciliation required | No |
| Unknown policy, state, reason, or contradictory `complete` combination | Admission status unavailable; do not treat as verified | No |

Refusal never removes the deposited HTML or its reopen path. Retryable reasons tell the operator to retry admission without redispatching research. Permanent evidence failures keep the artifact operational-only. Unknown backend values deliberately render an unverified fallback instead of inheriting success styling or copy.

The browser validates state/reason pairs as a closed relationship: `pending` accepts only no reason or a retryable reason, `refused` requires a permanent refusal reason, and `complete` requires no reason plus an approved brief with matching canonical and approved SHA-256 hashes. Graph navigation uses that verified presentation instead of the raw state literal. Create, consent/recovery, run, status, and deposit responses all carry the same launch and graph-admission projection.

## Reverser

V2 requires a new explicit operator-visible policy version, migration posture, hash-sensitivity proofs, and graph-admission tests. Signed external receipts may become admissible only after their issuer, schema, integrity verification, revocation, and local attribution semantics are separately ratified. Existing v1 or legacy authority must never silently acquire v2 semantics.
