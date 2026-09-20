# Finding: book-acquisition replay fixture changed the signed EPUB bytes

**Date:** 2026-08-07 · **Context:** the 21-PR consolidation ship (Aug 6–7 swarm).

## Symptom
`tests/test_book_acquisition_routes.py::test_authenticated_intent_authorization_and_port_round_trip`
fails on CI shard 3/4 (py3.14) with `assert 409 == 200` — the `/port` call returns
`AcquisitionConflictError` (409) instead of 200.

## It is NOT a product regression (proven)
- The book-acquisition product code was byte-identical to `origin/main`.
- The 409 response detail was `authorization already has a different or tampered port receipt`.
- Replaying the exact original EPUB bytes returns 200 and the existing receipt.
- Regenerating the fixture after 2.1 seconds produces different bytes and returns 409.

## Root cause (diagnosed)
The test called `_epub()` separately for the initial port and its replay. `_epub()` creates a ZIP,
whose entry metadata includes the current local timestamp with ZIP's two-second resolution. When the
two calls crossed that timestamp boundary, the resulting EPUB byte sequences—and therefore their
SHA-256 digests—differed. The endpoint correctly binds the authorization receipt to the raw EPUB
digest and rejected the second, byte-different body as a tampered or different replay.

The failure depended on suite timing, which made sharding expose it, but there was no leaked database,
environment variable, or signing key.

## Disposition
- The product endpoint is correct and unchanged → the deploy ships identical book-acquisition code to
  what is already live in prod. Deploying is safe.
- The test generates the EPUB once and reuses that exact byte sequence for the replay assertion.
- The raw-byte tamper binding remains unchanged; no skip, retry, or weakened assertion was added.

## Verification
- Five repeated focused runs passed.
- The full `tests/test_book_acquisition_routes.py` suite passed.
- All four Python 3.14 CI shards passed with the exact-byte fixture fix.

## Reconsider-if
Investigate product code only if an exact replay of the same captured byte sequence produces a 409,
or if a byte-different replay is accepted. Either result would violate the intended receipt contract.
