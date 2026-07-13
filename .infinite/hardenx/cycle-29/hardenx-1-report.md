# Cycle 29 hardenx-1 report

- Path: `/Users/slimydog/Antiek/platform/worktrees/campaign-mo-swarm`
- Command: `hardenx . --strict --no-color`
- Verdict: LOW
- Real findings: 0
- Advisory findings: 14
- Filtered findings: 12
- Exit code: 0
- Waiver or bypass: none
- Corpus certification: unavailable because the repository has no configured `corpus.toml`

The adapter is isolated, in-memory, explicitly non-conferring, and absent from production composition. Installed dependencies named by the scan were OSV-reverified as patched. Unresolved manifest-floor advisories are unchanged and no dependency file changed in this cycle. No secret values or report previews are retained here.
