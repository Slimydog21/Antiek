# Synthesis export provenance repair

## Failure Dossier

Production Loop One archives typed thesis components and chunk manifest pins,
but normally supplies no document manifest pins. The public export resolver
previously read only document pins and collapsed the summary into one claim.
It lost claim/source associations on production-shaped archives. When callers
supplied document pins, the adapter incorrectly counted those references as
complete claim/chunk/document provenance.

The first integration fixture supplied document pins explicitly. Its 23 passing
tests proved that narrower branch and authentication, but did not establish
production representativeness. Independent audit caught the mismatch. The
initial complete=True regression pin has been replaced, not ratified.

No live incident was observed. Application LLM calls: none. GLM performs
independent code review only.

### Signatures

Captured with inspect.signature from canonical code before repair:

```python
resolve_synthesis_export(synthesis_id: str, *, db_path: str | None = None) -> SynthesisExport | None
register_synthesis_artifact_routes(app: FastAPI) -> None
adapt_synthesis(export: SynthesisExport) -> dict[str, Any]
archive_synthesis_via_db(con: Any, inputs: ArchiveInputs, *, investigation_id: str, synthesis_id: str | None = None) -> str
```

These callable signatures remain unchanged.

### Numbered failure chain

1. Loop One's _deposit_synthesis_to_substrate archives thesis_components and
   chunk_ids, without document_ids.
2. archive_synthesis_via_db writes chunk pins, without deriving document pins.
3. The former export resolver queries only document pins and ignores thesis
   components, so valid chunk citations disappear from the export.
4. Its fallback attaches every document reference to one summary claim.
5. SourceRef.resolved formerly checked only document_id, allowing misleading
   complete=True metadata without a resolved chunk chain.

### Old vs new call pattern

The resolver now reads existing thesis JSON, preserves each component's exact
citation mapping, and queries chunks JOIN documents in parameterized batches.
It retains missing and malformed citations as unresolved records. Current
source rights still govern passage inclusion in the adapter. A resolved source
now needs both chunk and document identity.

Legacy or oversized/malformed component payloads export the authored summary
and document references with an explicit provenance note and incomplete count.
Analogy-only claims remain incomplete, with a note that analogy paths are not
resolved as chunk citations. No claim count is silently truncated.

### Repro gate

From the worktree root:

```bash
PYTHONPATH="$PWD" /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest -q services/html_projection/tests tests/api/test_synthesis_artifact.py tests/api/test_synthesis_export_boundary.py tests/api/test_synthesis_export_database.py
```

498 passed, exit 0. Full output: .audit/portable-links-full-tests.log.
The production-shaped fixture uses typed SynthesizeDeliveredPayload and
EvidenceRetrieveDeliveredPayload, pins chunks only, and asserts zero document
pins before checking exact claim/source resolution.

### What repro does NOT prove

Live production, the full workstation layout, or a stable multi-query archival snapshot.
Whole-synthesis restrictions still have no persisted policy field. Federated
span IDs remain unresolved in this local graph implementation.

## Scope Map

| Entry point | Status | Evidence |
|---|---|---|
| Typed archive, chunk-only pins, exact claim sources | tested | test_synthesis_export_database.py |
| Full app signed cookie to real archived HTML | tested | test_synthesis_export_database.py |
| Missing/malformed/legacy/analogy citations | tested | test_synthesis_export_database.py |
| Document-only and partially missing completeness | tested | test_provenance_gate.py |
| Query-route poison, rights, three-format refusal | tested | test_synthesis_export_boundary.py |
| Bearer/cookie/allowlist authentication | tested | test_synthesis_export_boundary.py |
| Shared component browser download/refusal, rendered file | tested | assets/synthesis-export-20260920 |
| Downloaded source link to actual reader body | tested | assets/synthesis-export-20260920/portable-reader.png |
| Deployed schema and other workstation flows | untested | no run |
| Archived external federation | untested | retained PR856, separate integration |

## Handoff

### Env Card

| Field | Value |
|---|---|
| Date | 2026-09-20 |
| Repo | /Users/slimydog/Antiek/.worktrees/synthesis-export-integration-20260920 |
| Branch | test/synthesis-export-integration-20260920 |
| Base | b96fa084e7a12b98a24b02f85200d82aeaa7bd2d |
| First evidence commit | 502cb2238c5c3111b3835c943f7e0ea4fd58bb8a |
| Interpreter | /Users/slimydog/Antiek/platform/.venv/bin/python, Python3.12.13 |
| Application provider/network calls | none |

### Not proved

See untested scope rows above. Synthetic tests do not establish live output
quality. Public export rights and citation completeness are separate checks.

### Status

In progress. Current tests and types pass; implementation review at c9b5c81b1 accepted91; followup review of copy and coverage changes pending. Initial M4 compliance was assessed at35/100, provisional repaired
local-graph compliance at88/100 pending independent review. Broad export
readiness remains below completion due to full-workstation/live/federated gaps.

### Files touched

The public resolver and adapter; provenance and database integration tests;
boundary tests from the first evidence commit; this diagnostic.

### Milestones

- [x] Production-shaped archive and full-app authenticated export proof.
- [x] Exact claim/chunk resolution and honest incomplete fallbacks.
- [ ] Independent implementation acceptance and current CI.
- [x] Local shared component download/refusal and rendered artifact.
- [ ] Full workstation and deployed verification.

### Gate results

| Gate | Result | Local evidence |
|---|---|---|
| Full export suite above | 498 passed, exit0 | .audit/portable-links-full-tests.log |
| Strict mypy, explicit-package-bases, follow-imports=silent | 4 files clean | .audit/portable-links-mypy.log |
| Ruff on changed Python | passed | command output |
| Gate-removal mutation | expected pytest exit1 | .audit/gate-mutation.log |
| Initial evidence-only GLM | ACCEPT84, entrenchment concern | .audit/export-review.log |
| Implementation GLM at c9b5c81b1 | ACCEPT91, terminal0 | .audit/provenance-review.log |
| Source-only security | LOW, 0 REAL, 7 advisory, exit0 | .audit/export-source-security-summary.json |

### Decisions mid-flight

The resolver design reuses PR856's archived-component and graph-join approach,
while retaining unresolved IDs and correcting document-only completeness.
The control-plane owner explicitly transferred the public export files from
that blocked claim. PR856 exact9652d314a remains untouched; its external span
registry still needs deliberate reintegration. No schema, writer, db_lock,
Parquet or serving-rights policy change.

### Assumptions surfaced

Legacy summaries have no verified claim mapping. They remain useful readable
exports, but do not receive fabricated provenance. Malformed payloads fall back
visibly. Query batching bounds parameters; parser limits bound expansion.

### Steelman rejected alternative

Merely renaming complete=True as document-level completeness preserves the
missing claim citations. This repair resolves the archived graph references
and keeps genuine gaps visible instead.

### Open questions

Independent critique, browser proof, production parity and federated rebase.

### Next sprint can start when

The implementation review is terminal and its findings are handled. Browser
verification can proceed independently on synthetic local data.

### Out-of-scope temptations

No provider execution, schema/writer migration, production mutation or deploy.


## Browser evidence and review followup

At c9b5c81b1, an isolated headless Chrome profile used browser-harness to click
the actual shared ArtifactExport component mounted in a local fixture page.
The local full app used scratch typed archives and ephemeral bearer auth.
HTML download produced 9,942 bytes, SHA256
b17b3f8a0ac0e35cc69e570e77ddb9969f2bca67c6506f69440a880d125cc5a9.
Its actual bytes passed the script-free gate, retained the public passage,
excluded the private passage, and reported 2/2 fully sourced claims. A synthetic
restricted metadata fixture exercised the real refusal route; its specific
reason appeared visibly in the shared component. This is not proof that a
persisted restriction field exists.

[Rendered download](assets/synthesis-export-20260920/download-render.png),
[visible refusal](assets/synthesis-export-20260920/refusal.png),
[downloaded HTML](assets/synthesis-export-20260920/browser-export-proof.html),
and [verification record](assets/synthesis-export-20260920/download-verification.json)
are retained. The fixture uses simple surrounding CSS, not the full workstation.
The API, Vite and isolated Chrome processes were stopped after verification;
ephemeral session credentials were removed. An unrelated missing p5 package
appeared during Vite's initial app dependency scan, but the fixture and real
export component loaded and completed both interactions. No dependency change
was made.

A concrete portability gap remains: downloaded source links resolve to
file:///read/doc-public and file:///read/doc-private. The browser DOM confirms
these targets. This proof does not claim useful offline source navigation.

The accepted review's stale docstring and fallback-copy findings are corrected.
Unresolved citation IDs now remain visible; an unavailable permitted passage
gets an explicit marker. Both parser limits omitted by the earlier tests now
have coverage. The resulting suite passes471 tests. Signed-format filename
quoting, metadata JSON bounds, read-route initialization, and portable source
links remain separate followups. No full-goal completion claim.


## Portable source links

The file-relative link defect observed above is repaired. The resolver uses the
established ANTIEK_FRONTEND_BASE_URL then ANTIEK_PUBLIC_BASE_URL configuration,
accepting an absolute HTTP(S) origin. It rejects credentials, invalid host/port,
controls, queries/fragments and path prefixes. Request Host, Origin and forwarded
headers never choose exported targets. Document IDs are percent-encoded as one
path segment. With no usable origin or document path, citations stay visible
with the document ID and "reader link unavailable", without a broken anchor.
Both HTML routes and direct resolver calls share this behavior.

The 498-test suite covers precedence, malformed/unset configuration, header
spoofing, localhost/IPv6, encoded IDs, both endpoints and machine-island links.
Strict mypy is clean on the four implementation/integration files.
The earlier followup review is terminal ACCEPT95 at8c6e8da5b. Independent
review of this portable-link delta completed ACCEPT94 at380d1407f in
.audit/portable-links-review.log. Its small followups reject noncanonical
numeric hosts and add backslash, port, percent-host, empty-ID and invalid
PUBLIC fallback tests. Canonical IPv4 and alphabetic hex-shaped DNS labels
remain accepted. The [WHATWG host parser](https://url.spec.whatwg.org/#concept-host-parser)
selects IPv4 parsing from numeric final labels, including hex notation; merely
rejecting digits-and-dots missed that case. Followup verification passes511tests,
strict mypy on4files and Ruff. Historical browser source hashes still identify
the earlier380d1407f implementation, not this validation-only followup.

Browser verification used an isolated Chrome profile with a real signed session
cookie, the real shared export component, and the local full app. A canonical
book asset was added to the synthetic public document. Clicking the public
source link from the downloaded file navigated to the actual Antiek reader at
http://127.0.0.1:18883/read/doc-public, where PUBLIC_SOURCE_PASSAGE was visibly
rendered. This closes the local file-to-reader navigation case, not reader-asset
availability for every graph document or deployed configuration.

[Portable downloaded HTML](assets/synthesis-export-20260920/portable-export.html),
[rendered file](assets/synthesis-export-20260920/portable-download-render.png),
[actual reader](assets/synthesis-export-20260920/portable-reader.png), and
[hashes, source digests and scope](assets/synthesis-export-20260920/portable-verification.json)
retain the evidence. The new file is10,118bytes, SHA256
c79cdd07be1ee74b0c5e6812f34a5b4c3c5fe830586c79ae0810dfd8288e2b19.
API, Vite and Chrome were stopped; ephemeral session credentials were removed.
The previous c9b5c81b1 artifacts remain as historical before-fix evidence.

A clean isolated npm ci resolved the missing p5 dependency without changing
package manifests. Its audit revealed50 affected package entries, including
2critical and10high; runtime-only audit reported1high and30moderate. Those
counts describe package entries, not distinct advisories or proven application
exploits. Read-only triage found the runtime high in Tiptap and critical dev
findings in form-data/Lost Pixel's dependency chain. Evidence is retained under
.audit/npm-*-20260920.json. Frontend dependency remediation is a separate lane;
source-only Hardenx results must not be presented as dependency clearance.
