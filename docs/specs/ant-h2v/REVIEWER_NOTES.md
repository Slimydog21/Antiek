# Reviewer pass (htmlspec Phase 4)

Date: 2026-06-02. Persona: generalPurpose adversarial read.

## Wontfix (recorded)

- **Master spec five-value cards:** Glossary + sprint pages carry rigor; duplicating full cards on `index.html` would bloat the dashboard. Executors read per-sprint rigor blocks.

## Fixed from review

- **SPR-03 acceptance/rigor mismatch:** Milestone criteria now require kwargs spy on `dispatch` and `render_full_prompt`, not JSON shape alone.
- **Frontend auto-decompose UX contract:** `CascadeProposal.test.tsx` now
  asserts the Research door calls `createPlan` with exactly `{ problem }` and
  no own `sub_questions` key, including `[]`. This proves the UI exercises the
  backend auto-decompose branch instead of silently taking the manual branch.
- **Repo-only execution brief:** The ANT-H2V Grok brief and adjacent
  closure/failure dossiers now use `<repo-root>` / repo-relative paths instead
  of machine-specific absolute checkout paths, so they can be shared from the
  repo without leaking the executor's local checkout location.
- **CI milestone for repro + audit:** `.github/workflows/agent_execution_gates.yml`
  already runs `./scripts/canonical_verify.sh cascade`, which executes the
  repro script, production adapter test, light HTTP route test, and decomposer
  call-site audit (those scripts/tests shipped in the earlier ANT-H2V sprints).
  Its path filters now include the cascade repro/audit scripts and cascade test
  files, so changes to those gates trigger the fast hermetic ANT-H2V workflow
  instead of relying on manual invocation.

## Residual gaps (executor backlog)

None.
