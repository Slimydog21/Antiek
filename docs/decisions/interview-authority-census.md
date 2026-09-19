# Interview authority census — Cycle 44

Status: parent authority and durable margin active; legacy derived Speak substrate local-only; canonical derivation pending.

## Canonical account-qualified authority

- `interview_projects_authority`: project content keyed by `(account_digest, project_id)` with explicit owner corruption check.
- `interviews_authority`: interview PII, lifecycle, and transcript keyed by `(account_digest, interview_id)` and owner-qualified project membership.
- `interview_invite_capabilities`: hashed, revocable, expirable exact-interview credentials. Raw tokens are returned once.
- `interview_consent_events`: immutable per-scope evidence with account, interview, invite, actor kind, policy version, decision, and time. `consent_recorded` is compatibility projection only.
- `interview_margins` and receipts: conditional revisioned plain text with exact retry semantics.
- Authenticated core routes `/interview-projects`, `/interviews`, `/interview-invites` derive account authority only from middleware claims. Foreign and missing resources both return 404.
- Public `/speak/invite/{token}` canonical branches derive one exact interview authority from the token. They cannot list projects, read margins, access other interviews, or survive revocation. Transcript reads require record consent.

## Legacy local-operator compatibility substrate

The following families remain globally keyed. The router dependency denies every non-invite `/speak/*` request for authenticated non-local accounts; missing middleware also fails closed. They remain available only through explicit `__operator__` local compatibility until migrated.

- Parent adapters: `interview_projects`, `interviews`, `substrate/speak/project.py`, `substrate/speak/async_interview.py`.
- Invitations and consent: `speak_invites`, `speak_consent`, `substrate/speak/invitations.py`, `substrate/speak/consent.py`.
- Claims and corroboration: `speak_claims`, corroboration groups/votes, third-party review and subject-consent state.
- Contribution/economics: contributor claims, payout decisions, grades, escrow/disbursement verification, physical-book acknowledgements.
- Composition: biography facts, chapter outlines, Write/Read handoffs, public feed and deliverable links.
- Operator API surface: legacy `/speak/projects/*`, `/speak/interviews/*`, claims, grades, publishing, economics, and composition routes.

## Migration behavior

- Legacy rows migrate only from explicit project owners. Missing or conflicting ownership is quarantined and unavailable; it is never claimed by the current operator.
- Canonical conflicts are compared, not silently ignored. Interviews resolve through the exact validated migration map rather than a display-ID search.
- The manifest records schema version, source count, migrated count, quarantine count, and `complete` versus `complete_with_quarantine`.
- Warm initialization requires the versioned manifest and every authority sentinel. A partially applied schema cannot pass the warm probe.
- DuckDB foreign keys are intentionally avoided because they block legitimate parent updates. Every product mutation checks account, owner, and parent membership transactionally; integrity auditing remains required before deletion/reconciliation work.

## Browser authority

- `InterviewNotes` no longer reads or writes `antiek.interview-notes.<id>` values. It enumerates key names only to disclose legacy presence.
- Canonical empty content always replaces rendered state. Hydration failure leaves editing disabled.
- Recovery uses an opaque server-derived scope and an account/interview/revision/hash envelope. Only transport failure writes it; HTTP conflicts and denials remain explicit. Recovery loads review-only and never auto-uploads.
- Hydration and save completion are fenced by interview identity and auth session generation. Autosaves serialize and advance only from acknowledged revisions.

## Deliberately open work

- Canonical invite answers are durable transcript turns with question-level exact retry, but document/claim derivation returns `canonical_derivation_pending`. It must not call the legacy global investigation/document bridge.
- Canonical follow-up generation currently returns an empty set rather than invoking the legacy global async-interview engine.
- Account-qualify claim, corroboration, contributor, payout, composition, and deliverable sidecars before lifting the local-only router ratchet.
- Add a canonical integrity audit/reconciliation command for orphaned parents, invites, consent evidence, margins, and receipts.
- Run a live multi-tab/auth-switch/browser canary when the in-app browser is available. No provider, spend, deployment, commit, or push was authorized in this cycle.
