# ResearchArtifact activation readiness — Cycle 6

Date: 2026-07-15  
Decision: **READY-EXCEPT-BROWSER — no activation authorized or performed**

The disposable account-hosting implementation is ready for its required in-app visual canary. It is not ready for configured-root or production activation until that canary produces a stored terminal-green evidence artifact and a root-bound activation receipt is built from the complete evidence set.

## Passed evidence

- Real Uvicorn TCP/process canary: authenticated Alice and Bob retain disjoint same-display HTML and notes across process kill/restart and full-root backup/restore; Mallory's foreign and nonexistent probes are byte/status indistinguishable and do not mutate durable state.
- Durable event recovery: exact append-once envelopes survive partial failure; retries converge on deterministic event identity; stale export envelopes are quarantined after artifact supersession.
- Storage crash recovery: both replacement and first-write interruption recover a validated HTML/sidecar pair.
- Frontend private-session boundary: identity changes destroy the prior iframe; stale refreshes cannot overwrite newer identity; logout invalidates immediately and suppresses refresh while pending.
- Activation guard: all seven named evidence JSON artifacts must be regular, identify the matching gate, report `status=pass` and `exit_code=0`, match their recorded SHA-256 digest, match the target root and mode, and preserve receipt integrity.
- Regression gate: 140 affected Python tests passed; 5 frontend tests passed; TypeScript typecheck, Ruff, and Python 3.11 syntax compilation passed.
- Independent review: Codex final verdict PASS after four initial findings and two follow-up findings were fixed and retested.
- Security: hardenx strict exit 0, LOW band, 0 REAL, 12 advisory. Corpus certification was not established; the corpus-check CLI expects a corpus file and none was supplied.

## Evidence not run

- In-app browser visual canary: **NOT RUN**. Browser discovery returned no available in-app browser sessions. The browser-control contract prohibited substituting an unrelated browser surface.

## Operational boundary

No configured artifact/event/graph root, production service, deployment, commit, push, or rollout mode was mutated. No terminal-green activation receipt was written. Activation remains fail-closed in SHADOW until the missing browser evidence is produced and separately approved.
