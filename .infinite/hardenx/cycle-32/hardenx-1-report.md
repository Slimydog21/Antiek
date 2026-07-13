# Cycle 32 hardenx report

- Command: `hardenx --strict --json .`
- Verdict: **LOW**
- Real findings: **0**
- Advisory findings: **17**
- Filtered findings: **12**
- OSV verification: enabled; installed flagged dependencies resolved cleanly.
- Changed-surface review: frozen semantic hashes/domain constants are identifiers, not credentials. No waiver or bypass was used.
- Residual advisories: unchanged high-entropy identifiers and unresolved manifest-floor packages not installed in this environment.

The strict command exited zero. The generated `.harden/` material was scrubbed by hardenx; this categorical report contains no secret fragments.
