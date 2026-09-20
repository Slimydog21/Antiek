# Durable imported research notes

## Failure Dossier

**Reported symptom:** importing a note from an edited copy of a hashed research export emitted an event, but the next export contained no notes. **LLM contacted on failure path: no.**

### Signatures

Runtime signatures are retained in `.audit/notes-signatures.log`.

| Callable | Source | Contract |
|---|---|---|
| `export_research_artifact` | `substrate/research_artifact/export.py:30` | investigation id; optional keyword database/event paths, event flag, role and owner |
| `import_agent_notes` | `substrate/research_artifact/import_notes.py:131` | caller HTML `Path`; optional keyword investigation id, event directory and role; returns imported/skipped counts and accepted event ids |
| `load_persisted_agent_notes` | `substrate/research_artifact/import_notes.py:202` | investigation id and optional event directory; legacy `artifact_path` argument explicitly requires reimport |
| `build_body` | `substrate/research_artifact/build_body.py:12` | forwards the selected event directory to the note loader |

### Numbered failure chain

1. `export.py:51` writes `sources/<investigation>/<content-hash>.html`.
2. An operator edits a caller-selected copy and invokes `import_agent_notes`.
3. At base `f24981db2`, import wrote an `artifact.generated` event referring to that mutable caller file, with no durable note object.
4. The old loader read only `<investigation>.html`, independently of accepted events. Missing that unrelated filename returned an empty list.
5. Re-export silently dropped the imported note. The regression deletes the caller file after import and verifies the next actual export.

### Repro gate

Before source edits, `pytest tests/test_research_artifact_import.py -k hashed_export -q` failed with `[] != ['Keep this imported note']`: **1 failed, 2 deselected**, exit 1. Full output: `.audit/notes-roundtrip-red.log`.

Root additionally reproduced accumulated-note replay exceeding the old per-import bound in `.audit/root-reimport-cap-proof.json`. New-note limits now apply after durable deduplication; unchanged accepted notes do not consume the new-note allowance.

### What repro does NOT prove

It does not exercise browser note editing, the complete writing workstation, remote providers, deployment, or real operator data. All database, event and artifact storage used by tests is scratch storage.

## Scope Map

| Entry point | Status | Evidence | Live LLM |
|---|---|---|---|
| Actual hashed export → edited caller HTML → import → caller deletion → re-export | tested | `test_hashed_export_note_import_survives_caller_removal`; database bytes unchanged across import | no |
| CLI `--import-notes`, then separate-process export | tested | `test_cli_import_then_export_after_caller_removed` | no |
| Disabled events, strict append failure, partial batch retry | tested | import regression module; earlier accepted notes survive and unreferenced bytes stay invisible | no |
| Thread/process duplicate import and sealed event replay | tested | import regression module; one accepted event per full content hash | no |
| Legacy accepted-event migration | tested | legacy files alone ignored; accepted v1 hashes block export until every hash is explicitly reimported | no |
| Unsafe paths, symlinks, hardlinks, FIFO, corrupt/missing bytes | tested | note-store and import regression modules | no |
| Export/template/compose/hooks, artifact/feedback/style routes, twin note-taker consumers | tested | named consumer suite in Gate results | no |
| Browser editing and complete writing workflow | untested | no browser or workstation interaction in this lane | no |
| Future PR866 body-v2 parser and provenance changes | untested | narrow handoff preserves those separately owned files | no |

## Persistence contract

Each normalized note is an immutable UTF-8 object at `notes/<investigation>/<full-sha256>.txt`. Publication creates a private temporary file, writes and fsyncs it, links without replacing an existing name, removes the temporary name, then fsyncs the directory. Existing bytes must validate before reuse. The store rejects symlink components from the configured artifact root downward, nonregular files, additional hardlinks, foreign ownership, non-0600 permissions, size/hash mismatch and invalid UTF-8. Operator-configured ancestors of the artifact root remain a trusted filesystem boundary.

A separate investigation-directory flock serializes import before the emitter acquires its event lock. The directory descriptor closes on exit; there is no removable lockfile or database writer lock. Acquisition times out after ten seconds. The typed event uses a full-hash v2 note intent and deterministic UUID5 event id, `strict_write=True`, and the existing emitter's idempotent append. Note identity/version is independent of research body schema version.

Only successfully persisted events authorize loading. Event `artifact_path` is descriptive metadata and is never opened. The loader derives its path from validated investigation identity and content hash. A missing or corrupt accepted object raises explicitly. Events disabled or append failures fail the import; an orphan object remains invisible and can be verified/reused on retry. A failed multi-note batch retains earlier successful event commits. Reimport skips them and continues. This is append-only partial progress, not a transaction or rollback promise.

Legacy v1 accepted events do not provide trustworthy surviving note bytes. Export raises a migration-required error until their full hashes have corresponding durable accepted notes. Operators must explicitly reimport a surviving HTML copy containing those notes; no legacy event path or mutable `<iid>.html` is read automatically. Legacy files with no accepted event have no authority. Body v1 remains supported. Future body-version migration belongs in `parse_body_from_html`; the blocked PR866 owner retains schema/render/provenance changes, including its v1-to-v2 parser migration obligation. This repair does not claim body-v2 support on main.

### Resource and consumer bounds

Per note: 64 KiB. Per import: at most 256 unique **new** notes and 1 MiB new normalized bytes, subject to the stricter retained total. Per investigation: 4096 notes and 256 KiB normalized bytes. Input HTML: 10 MiB. Full replay is counted separately from new notes; aggregate overflow rejects before accepting any note in that batch.

Actual full-capacity exports of four distinct escaped notes measured:

| Repeated character | Raw accepted bytes | Export bytes |
|---|---:|---:|
| `<` | 262144 | 4724504 |
| `&` | 262144 | 4200224 |
| double quote | 262144 | 3151664 |
| U+0001 | 262144 | 4986644 |

All four reimported without new events. The regression reads the actual `style_routes._MAX_ARTIFACT_BYTES` consumer constant. Log: `.audit/notes-escaped-capacity.log`. This leaves several MiB for non-note content in the tested empty-investigation exports. Graph-derived content remains independently unbounded by this repair and can itself exceed the existing style-reader/input cap; this is not a proof that every combined artifact or the full style workflow fits. An intermediate test incorrectly required the measured `<` export to exceed 5 MiB; its failed log remains `.audit/notes-consumers.log`. The assertion now tests actual amplification and the downstream upper bound.

## Sprint research-note-persistence — Handoff

### Env Card

| Field | Value |
|---|---|
| Date | 2026-09-20 |
| Repo root | `/Users/slimydog/Antiek/.worktrees/research-note-persistence-20260920` |
| Branch | `fix/research-note-persistence-20260920` |
| Base SHA | `f24981db2bde8ce2fb88158fc54460cfd168c294` |
| Python | `/Users/slimydog/Antiek/platform/.venv/bin/python`, 3.12.13 |
| Runtime state | scratch `.audit/runtime` environment before imports; test fixtures use independent temporary paths |
| LLM contacted by product tests | no |
| Network required for gates | no |
| Ownership validation | `CONTROL_PLANE_OK agents=650 active_portfolio=9 owned_surfaces=1734 lease_tip=818a73788` before edits |

### Not proved

- Browser editing, live integrations, deployment, full writing workstation and body-v2 migration were not exercised.
- No abrupt power-loss test or Linux execution was performed locally. The store uses POSIX directory descriptors, flock, no-clobber hardlinks and fsync.
- This does not repair unrelated event-log corruption handling. A recognized durable-note event with invalid identity/object fails explicitly; underlying trajectory parsing/sealing remains the existing event-log contract.
- Same-user malicious mutation or replacement of the configured storage root is outside the immutable-object trust boundary. Object verification detects changed accepted bytes; this is not cryptographic event authentication.

### Status

Implementation and local gates complete; independent review pending. No push, PR, merge or deployment authorized in this lane yet.

### Files touched

Only `substrate/research_artifact/{import_notes,build_body,note_store}.py`, `tests/test_research_artifact_import.py`, `tests/test_research_artifact_note_store.py`, and this dossier. No schema, graph writer, `db_lock`, paths helper, renderer or event-log edits.

### Milestones (checkboxes)

- [x] Reproduce real hashed-export note loss before source edits.
- [x] Implement durable event-authoritative notes and explicit legacy migration.
- [x] Verify concurrency, corruption, failure recovery, bounds and downstream consumers.
- [ ] Independent critic and source security review by parent.

### Gate results

Run from the repo root above with `ANTIEK_HOME=$PWD/.audit/runtime`, `ANTIEK_DUCKDB_PATH=$PWD/.audit/runtime/graph.duckdb`, and `PYTHONPATH=$PWD` before pytest. Python is the absolute interpreter in the Env Card.

| Gate | Result | Log |
|---|---|---|
| Original red roundtrip | exit 1, 1 failed/2 deselected | `.audit/notes-roundtrip-red.log` |
| Final consumer suite | exit 0, 173 passed, no skips; one existing Starlette/httpx deprecation warning, 40.44 seconds | `.audit/notes-consumers-final.log` |
| Full-cap escaped exports and downstream cap | 4 passed | `.audit/notes-escaped-capacity.log` |
| Ruff, five Python files | exit 0, all checks passed | `.audit/notes-ruff.log` |
| Strict mypy, five Python files | exit 0, no issues | `.audit/notes-mypy.log` |
| Equivalent base mypy via shadow files | exit 1, 3 existing untyped test functions; current zero, zero new | `.audit/notes-mypy-baseline.log` |

Consumer command: `python -m pytest tests/test_research_artifact_import.py tests/test_research_artifact_note_store.py tests/test_research_artifact_export.py tests/test_research_artifact_template.py tests/test_research_artifact_blocks.py tests/test_research_artifact_compose.py tests/test_research_artifact_hooks.py tests/test_artifact_routes.py tests/test_feedback_routes.py tests/test_feedback_artifact_anchor.py tests/test_style_api.py tests/test_twin_note_taker_generate.py -q`.

Type command: `python -m mypy --strict --follow-imports=silent --explicit-package-bases` followed by the five owned Python files. Baseline uses the three preexisting files at the base SHA through `--shadow-file` in the same module context. No ignore comments or relaxed type flags were added.

### Decisions mid-flight

Per-import bounds were separated from retained replay after root reproduced the capacity mismatch. Retained bytes were reduced to 256 KiB to preserve useful headroom below the existing 10 MiB style reader; actual escaping was measured. Legacy accepted notes require explicit migration instead of disappearing silently.

### Assumptions surfaced

The local event stream and configured root are operator-owned. Existing trajectory ordering and sealed/live merging determine note order. Failed event writes can leave orphan bytes, which are never accepted without an event. Full content hashes make new note identity independent of the old truncated-intent collisions.

### Steelman rejected alternative

Copying the caller HTML to `<iid>.html` would make the immediate roundtrip work with less code. It would keep mutable files authoritative, overwrite concurrent changes and lose acceptance history after later edits. Automatically reading old event paths would also grant arbitrary paths read authority. Neither preserves the required durable append-only contract.

### Open questions

Parent owns independent review, source security scan, CI and any publish decision. The PR866 owner retains the future body-v2 integration. Lost legacy note bytes require operator recovery from a surviving copy; the event hash cannot reconstruct text.

### Next sprint can start when

Independent review accepts the immutable commit and parent records any remaining release constraints. A separate browser/writing-flow lane can then test real editing/import ergonomics.

### Out-of-scope temptations

No schema migration, graph mutation, event-log redesign, automatic legacy-path ingestion, background orphan deletion, renderer changes, broader ownership acquisition or deployment.

### Browser and source-scan follow-up

On source6e2c73d11, Chrome interacted with the actual private HTML Add-note
control. The edited DOM was serialized to a caller HTML file through DevTools;
the actual artifact_router import returned200/one accepted note/event. The caller
file was deleted, and actual re-export returned200 with the same note. Window
error and rejection capture remained empty. This is not native Save Page, full
application authentication, or the complete writing workflow. See
[verification JSON](assets/research-note-persistence-20260920/browser-verification.json)
and [screenshot](assets/research-note-persistence-20260920/add-note.png).

A second browser case containing literal closing-script-tag text produced
non-importable saved HTML, returning400 with an unterminated JSON string.
The existing renderer updates the JSON island without escaping less-than signs.
That separate renderer defect is assigned to the stacked serialization repair;
it is not hidden by the ordinary-note success above.

Source-only strict Hardenx scan exited0, LOW, zero REAL and six advisory findings
on the frozen changed Python files with the repository ignore rules preserved.
Evidence: .audit/notes-hardenx.json. No dependency or production clearance follows.
Independent GLM review26146 returned ACCEPT, 88/100, on source6e2c73d11.
Follow-up work addresses managed-directory permissions and explicit restoration
of accepted note objects. The original acceptance does not cover that follow-up.


### Independent-review implementation follow-up

GLM review 26146 accepted source `6e2c73d11` at 88/100. Its acceptance does not cover this subsequent change. Board validation before follow-up edits passed with 653 agents, 9 active portfolio entries and 1763 owned surfaces.

**L1:** every managed `notes` and investigation directory is now checked by descriptor for current-user ownership and exact 0700 mode. Existing permissive or foreign-owned directories fail closed; no automatic chmod/chown is attempted. The configured artifact root's existing trust policy is unchanged. The mode regressions alter real directory permissions. Owner regressions inject foreign UID metadata through `fstat`, without requiring privileged chown.

**M1:** explicit import can restore missing or damaged accepted bytes only when the supplied normalized text matches both the accepted full SHA-256 and byte size. Recovery occurs under the existing import lock. It reuses the original event and reports the restored note as a skipped duplicate, with zero new event ids. Ordinary loading/export still fails until recovery succeeds. An unrelated new import cannot bypass an unavailable accepted note. Earlier restored or accepted notes remain intact if a later note in the batch fails.

For damaged bytes, only an owned, regular, singly linked, 0600 object within the note-size bound qualifies. Recovery prepares and fsyncs replacement bytes first, revalidates the damaged object through its descriptor and matching directory entry, fsyncs the old bytes, reserves a fresh private quarantine sibling, then atomically renames the damaged object there. After directory fsync, it links the prepared replacement without clobbering an existing name, unlinks its temporary name and fsyncs the directory again. Quarantined bytes are retained. A failure after quarantine leaves a missing accepted path that exact reimport can restore. Concurrent exports can fail explicitly during this recovery window; the operation does not promise uninterrupted reads.

Symlinks, foreign-owned, multiply linked, permissive or oversized objects are never moved or overwritten. Healthy accepted objects keep their inode and produce no quarantine. The tests preserve damaged bytes, refuse wrong replacement text, and inject publication failure after quarantine before successfully retrying. This injection demonstrates retry semantics, not real power-loss behavior.

**L2:** inspection confirmed the existing `_directory` context manager already wraps `OSError` thrown by leaf open or operations in its yielded body. No redundant catch was added. Specific missing-object and corrupt-byte subclasses distinguish authorized recovery candidates from unsafe storage.

**L3:** caller-selected HTML can be outside artifact storage, but its final path component must be a regular file, not a symlink. The importer opens with `O_NOFOLLOW`; a symlink is rejected before notes or events are written. Callers must explicitly choose the regular target path. Event paths remain non-authoritative regardless of caller-path policy.

Review regressions were run before production edits: **5 failed, 45 deselected**, covering missing-object restoration and both managed directory levels under wrong mode/UID. Log: `.audit/notes-review-red.log`. The additional corrupt-byte restoration regression also failed before its implementation: **1 failed, 37 deselected**, `.audit/notes-corrupt-recovery-red.log`. The final consumer suite includes these cases, unsafe-object refusal, caller-symlink rejection and failure after quarantine.

| Follow-up gate | Result | Evidence |
|---|---|---|
| Consumer suite | exit 0, 186 passed, no skips; one existing Starlette warning, 36.46 seconds | `.audit/notes-review-consumers-final.log` |
| Ruff | exit 0, all checks passed | `.audit/notes-review-ruff.log` |
| Strict mypy | exit 0, no issues in five files; zero new versus recorded baseline | `.audit/notes-review-mypy.log` |

After conservative rename-error cleanup was removed to avoid deleting potentially moved bytes, the affected recovery cases were rerun: **9 passed, 30 deselected**, `.audit/notes-review-recovery-final.log`. A failed rename can leave an empty reserved quarantine placeholder; it cannot authorize a note or trigger automatic cleanup of damaged bytes.

The previous browser proof and source scan remain tied to `6e2c73d11`. Updated independent review remains the parent's responsibility. This lane added no production-incident fixture: both observed failures were local reproductions, not claims of incidents seen in production.
