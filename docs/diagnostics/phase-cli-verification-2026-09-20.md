# Phase CLI checker configuration must fail closed

## Failure Dossier

A misspelled `--postcondition-module` made `verify` return success and record
`(no postcondition registered)` as verification evidence. `status` likewise
reported successful live checks. This was reproduced locally in the production
CLI module, with no LLM contacted and no production data accessed.

### Signatures

Source inspection at base `b96fa084e7a12b98a24b02f85200d82aeaa7bd2d`:

- `_load_postcondition_check(module_path: str | None)` returned `None` for empty,
  unimportable, or checker-free modules.
- `verify_phase(investigation_id: str, phase: int, *, postcondition_check:
  PostconditionCheck | None = None, log_dir: str | None = None) -> VerifyOutcome`.
- `phase_status(investigation_id: str, *, postcondition_check:
  PostconditionCheck | None = None, log_dir: str | None = None) -> dict[str, Any]`.

### Numbered failure chain

1. CLI loader at `orchestration/phase_runner/cli.py:44` resolved a configured
   checker to `None` on import failure, including a missing nested dependency.
2. `_cmd_verify` passed that value to `runner.verify_phase`.
3. `orchestration/phase_runner/runner.py:227` selected its structural default.
4. `orchestration/phase_log/log.py:220` recorded verification and emitted a typed
   `phase.verify` event. No exception alerted the operator.

The fix requires a callable checker before entering either CLI runner operation.
Configuration failures print a diagnostic and return 2. A wrapper preserves
callable objects with false boolean values, which would otherwise select the
library's optional default. Library defaults and Loop1 callers remain unchanged.

## Scope Map

| Entry point | Status | Evidence | Live LLM |
|---|---|---|---|
| CLI `verify`, invalid checker | Tested | New subprocess tests compare every phase/event file byte before and after | No |
| CLI `status`, invalid checker | Tested | Same parameterized tests require exit 2 and no success JSON | No |
| CLI `verify`, valid pass/fail | Tested | Real JSON evidence, typed event count/type, subsequent CLI `assert` | No |
| CLI `status`, valid pass/fail | Tested | Live results match checker and files remain unchanged | No |
| CLI default checker | Tested | Missing orientation fails; valid local artifact passes | No |
| Library and phase-log API | Tested | Existing runner, postconditions and phase-log suites | No |
| Loop1 and production research | Untested in this lane | No changed call sites; end-to-end runs require separate scope | Not run |

## Handoff Packet

### Env Card

| Field | Value |
|---|---|
| Date | 2026-09-20 |
| Repo root | `/Users/slimydog/Antiek/.worktrees/phase-cli-verification-20260920` |
| Branch | `fix/phase-cli-verification-20260920` |
| Base SHA | `b96fa084e7a12b98a24b02f85200d82aeaa7bd2d` |
| Python | `/Users/slimydog/Antiek/platform/.venv/bin/python`, 3.12.13 |
| Test imports | Worktree cwd with `PYTHONPATH=.`; subprocesses explicitly use worktree plus temporary checker modules |
| LLM / paid calls | None |
| Network for gates | None; Git fetch only for base reconciliation |

### Not proved

Independent review, PR CI, integration and deployment remain pending. This change
does not establish the sufficiency of every phase's domain predicate or revoke
historical false verification records. Arbitrary operator-selected checker modules
execute Python on import; this loader is not a sandbox and cannot prevent their
own side effects. No production incident was observed, so the production-incident
YAML catalog was not expanded.

### Status

Implementation ready for independent review. Provisional evidence grade 92/100:
5 points reserved for independent review and 3 for integration CI. This is a
bounded readiness assessment, not an independent acceptance score or a product
completion claim.

### Files touched

- `orchestration/phase_runner/cli.py`
- `tests/test_phase_cli_verification.py`
- This diagnostic.

### Milestones (checkboxes)

- [x] Reproduce false success before changing the CLI.
- [x] Require a callable checker and preserve real pass/fail behavior.
- [x] Exercise phase JSON and typed events through actual subprocess commands.
- [ ] Obtain different-lineage acceptance and PR CI.

### Gate results

Commands run at the worktree root. `PY` below denotes the absolute interpreter
in the Env Card. Full logs are retained locally under `.audit/`.

| Gate | Command | Result | Log |
|---|---|---|---|
| Before fix | `PYTHONPATH=. $PY -m pytest tests/test_phase_cli_verification.py -q --tb=short` | 13 failed, 1 passed: 12 intended configuration failures plus one test event-label typo, corrected to canonical `phase.verify` | `.audit/before.log` |
| Related suite | `PYTHONPATH=. $PY -m pytest tests/test_phase_cli_verification.py tests/test_orchestration_phase_runner.py tests/test_phase_runner_postconditions.py tests/test_orchestration_phase_log.py -q --tb=short` | Exit 0, 106 passed in 15.66s | `.audit/final-root-tests.log` |
| Lint | `$PY -m ruff check orchestration/phase_runner/cli.py tests/test_phase_cli_verification.py` | Exit 0 | `.audit/ruff.log` |
| Scoped strict types | `$PY -m mypy --follow-imports=silent orchestration/phase_runner/cli.py` | Raw exit 1: seven existing findings, zero NEW and zero scoped STALE using the repository baseline matcher; no baseline changes | `.audit/cli-mypy-final.log`, `.audit/cli-mypy-final-comparison.log` |
| Whitespace | `git diff --check` | Exit 0 | Inline output empty |

### Decisions mid-flight

Fast-forwarded the branch from `ebc5996ad` to current main `b96fa084e` before the
production edit. Only lint baselines changed in that update. Import-time ordinary
exceptions become explicit configuration failures; process-control exceptions
are not swallowed. Runtime checker failures retain existing nonzero behavior. Scoped strict typing found a new `no-any-return` in the wrapper; a cast after callable validation fixes that dynamic-import typing boundary. The seven remaining findings already exist in the declared baseline. No baseline was expanded or edited in this claim.

### Assumptions surfaced

A callable is the CLI configuration contract. Checker correctness remains the
checker's responsibility. The default artifact checker is exercised with an
isolated local orientation document; no provider access is needed.

### Steelman rejected alternative

Removing only the `ImportError` catch would stop one false-success path but leave
empty module names and missing `run_check` attributes selecting the no-op default.
It would also leave status diagnostics inconsistent.

### Open questions

Historical false-verification remediation requires evidence of affected records
and separate ownership. This lane has not inspected or changed live records.

### Next sprint can start when

The parent orchestrator has reviewed the focused diff and obtained the required
different-lineage assessment.

### Out-of-scope temptations

Changing library default behavior, changing normal Loop1 checks, and tightening
all domain predicates would exceed this claim and require separate compatibility
analysis.


### Type baseline ownership

The loader keeps its existing unannotated signature. Its returned closure is
annotated and casts the validated callable to the existing PostconditionCheck
contract. This fixes the new dynamic-return finding without editing the type
baseline concurrently owned by dependency-security PR #3247. Existing typing
debt remains visible; no ignore or baseline entry was added.


### Scoped security evidence

Hardenx strict source-only scan exited0: LOW, zero REAL and seven advisory
findings. Scope was exactly the two changed Python files copied to a temporary
directory outside Git, not a repository, dependency or production audit. An
initial scan of an audit subdirectory inside the worktree reported a missing
.gitignore for that artificial directory; the actual repository has its policy.
No allowlist or scanner finding was suppressed. Sanitized summaries are retained
in .audit/cli-security-source-summary.json and .audit/cli-security-summary.json.
Independent GLM review is running; this PR remains draft pending its verdict and CI.
