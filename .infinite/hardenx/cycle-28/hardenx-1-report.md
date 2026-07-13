# Cycle 28 hardenx-1 report

- Path: `/Users/slimydog/Antiek/platform/worktrees/campaign-mo-swarm`
- Command: `hardenx . --strict`
- Verdict: LOW
- Real findings: 0
- Advisory findings: 14
- Filtered findings: 12
- Exit code: 0
- Waiver or bypass: none
- Corpus certification: unavailable because the repository has no configured `corpus.toml`

The only changed-path high-entropy advisory is the literal semantic module-source SHA-256 identity in `private_output_checker_v2.py`; it is not a credential. Installed dependencies named by the scan were OSV-reverified as patched. Unresolved manifest-floor advisories are unchanged and no dependency file changed in this cycle. No secret values or report previews are retained here.
