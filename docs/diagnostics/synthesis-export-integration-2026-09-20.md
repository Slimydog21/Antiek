# Synthesis export integration evidence

## Failure Dossier

The prior UI tests mocked HTTP responses; backend tests mocked resolution and
mounted a bare FastAPI instance. They did not connect canonical persistence or
application authentication to the actual `/artifact?format=html` endpoint.
No live production failure or provider failure was observed. LLM contacted on
the application path: no. An independent GLM reviewer is used for code review.

### Signatures

Captured with `inspect.signature` using the worktree source:

```python
resolve_synthesis_export(synthesis_id: str, *, db_path: str | None = None) -> SynthesisExport | None
register_synthesis_artifact_routes(app: FastAPI) -> None
adapt_synthesis(export: SynthesisExport) -> dict[str, Any]
archive_synthesis_via_db(con: Any, inputs: ArchiveInputs, *, investigation_id: str, synthesis_id: str | None = None) -> str
```

### Numbered failure chain

1. MasterMdViewer supplies the synthesis API path to ArtifactExport.
2. ArtifactExport requests `/artifact?format=html` with session credentials.
3. Full application middleware authenticates before route resolution.
4. The resolver reads synthesis metadata and document rights from DuckDB.
5. The adapter filters rights; render output passes the script-free gate.

No broken-call exception was reproduced. The missing proof concerned steps
3–5. Scratch execution also confirms a separate provenance limitation: the
resolver constructs one thesis claim from document references, without
reconstructing the archived evidence's claim/chunk relationships.

### Old vs new call pattern

N/A. This change adds integration evidence without changing product calls.

### Repro gate

`PYTHONPATH="$PWD" /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest -q tests/api/test_synthesis_export_boundary.py tests/api/test_synthesis_export_database.py tests/api/test_synthesis_artifact.py`

Exit 0, 23 passed. Full output: `.audit/combined-tests.log`.

### What repro does NOT prove

Live deployment, browser downloads, validated claim/chunk provenance, or
persistent whole-synthesis restriction. The current schema has no such policy
field. Metadata refusal tests inject the adapter's transient restriction.

## Scope Map

| Entry point | Status | Evidence | Live LLM |
|---|---|---|---|
| Archive writer → resolver → query HTML route | tested | test_synthesis_export_database.py | no |
| Query route mixed rights and poisoned renderer | tested | test_synthesis_export_boundary.py | no |
| Query route restricted metadata, three formats | tested | test_synthesis_export_boundary.py | no |
| Full app bearer auth, both HTML routes | tested | test_synthesis_export_boundary.py | no |
| Full app signed-cookie auth and email allowlist | tested | test_synthesis_export_boundary.py | no |
| Full app signed cookie → real archived export | tested | test_synthesis_export_database.py | no |
| Browser download and rendered interaction | untested | no browser run | no |
| Real deployed schema and auth configuration | untested | no production read | no |

## Handoff

### Env Card

| Field | Value |
|---|---|
| Date | 2026-09-20 |
| Repo root | /Users/slimydog/Antiek/.worktrees/synthesis-export-integration-20260920 |
| Branch | test/synthesis-export-integration-20260920 |
| Base SHA | b96fa084e7a12b98a24b02f85200d82aeaa7bd2d |
| Python | /Users/slimydog/Antiek/platform/.venv/bin/python |
| Python version | 3.12.13 |
| Application LLM/network calls | none |

### Not proved

See the untested Scope Map rows and repro limitations above. Full-app bearer and cookie-negative tests use a missing synthesis to distinguish
rejected access from authenticated resolution. A fourth database test joins
real archive data, real signed-cookie authentication and successful HTML export
in the full application.

### Status

In progress. Tests and Ruff pass. Independent review pending. Provisional
export verification grade 78/100: substantially stronger backend evidence,
with browser and provenance obligations still open.

### Files touched

Two new export test modules and this diagnostic. No production implementation.

### Milestones

- [x] Real archive/resolver test with isolated database.
- [x] Exact query-route negative tests and full-app authentication.
- [ ] Independent review accepted.
- [ ] Browser download proof.

### Gate results

| Gate | Result | Evidence |
|---|---|---|
| Combined pytest command above | 23 passed, exit 0 | .audit/combined-tests.log |
| Ruff on both new test modules | exit 0 | root tool output |
| Strict mypy, follow-imports=silent, both new modules | exit 0 | .audit/mypy-tests.log |
| Gate-removal mutation | expected pytest exit 1 | .audit/gate-mutation.log |
| Independent GLM review | running | .audit/export-review.log |

### Decisions mid-flight

Preserve whole-synthesis restrictions as explicitly absent. No fictitious
database flag was added. Signed cookies use the actual signer and verifier.

### Assumptions surfaced

Document-level provenance completeness is weaker than the SPR-05 M4 requirement
to walk each claim/chunk/document chain. The observed metadata must not be
presented as proof of that stronger requirement.

### Steelman rejected alternative

Source inspection shows both routes share guards, but would not catch a later
query-route bypass or an application auth exception. The new tests exercise
those paths directly.

### Open questions

The independent reviewer is assessing whether a test pinning coarse provenance
would entrench a contract gap. Browser/download verification remains separate.

### Next sprint can start when

Ownership of the relevant resolver/adapter change is coordinated with the
existing federated-evidence claim, if a provenance correction is required.

### Out-of-scope temptations

No schema migration, auth-policy change, production mutation or deployment.
