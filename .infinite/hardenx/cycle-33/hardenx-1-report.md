# Cycle 33 hardenx report

- Command: `hardenx --strict --json .`
- Verdict: **LOW**
- Real findings: **0**
- Advisory findings: **18**
- Filtered findings: **12**
- OSV verification: enabled; installed flagged dependencies resolved cleanly.
- Changed-surface review: the admission-module advisory identifies a frozen regex/domain-style constant, not a credential. No waiver or bypass was used.
- Residual advisories: unchanged high-entropy identifiers and unresolved manifest-floor packages not installed in this environment.

The strict command exited zero. Generated scanner material was scrubbed by hardenx; this categorical report retains no secret fragments.
