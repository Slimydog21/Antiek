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

## Rejected alternatives

- One citation per step does not prove each claim.
- Embedding or string-similarity linking manufactures provenance.
- Defaulting legacy rows to v1 invents consent that was never recorded.
- Rejecting the entire operational deposit destroys useful partial work.

## Reverser

V2 requires a new explicit operator-visible policy version, migration posture, hash-sensitivity proofs, and graph-admission tests. Signed external receipts may become admissible only after their issuer, schema, integrity verification, revocation, and local attribution semantics are separately ratified. Existing v1 or legacy authority must never silently acquire v2 semantics.
