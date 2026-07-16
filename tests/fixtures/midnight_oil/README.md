# Midnight Oil compatibility vectors

`34e_copied_epoch0.bundle.b64` was generated from detached commit `ddfc996c1`
before any Cycle 34F/V2 implementation was present. It contains gzip-compressed,
base64-encoded JSON holding the copied SQLite bytes, complete frozen corpus,
`CopyAuditV1`, signed `copied_epoch0` lifecycle state, and its verification key.

The current test suite treats the bundle as immutable input: it does not rebuild,
rewrite, or relabel the database. It verifies the historical signature and
recomputes the complete observed-target audit with current code.

Fixture SHA-256:
`5143bd753ab7457f9f4e32660af7c3ddd29d568616eee296d6b6c3c64b83caf2`
