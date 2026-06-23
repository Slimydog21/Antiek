# Research artifact transport (ANT-AHT / SPR-AHT-03)

Agents should prefer **exported ResearchArtifact HTML** over raw MASTER.md for cross-session handoff.

## Export

```bash
python -m substrate.research_artifact <investigation_id>
# or POST /research/{id}/artifact/export
```

## Append discipline

- Only **`agent_notes[]`** in the JSON block may be imported (v0).
- CLI: `python -m substrate.research_artifact --import-notes ~/.antiek/research-artifacts/<id>.html`
- API: `POST /research/{id}/artifact/import-notes` with `{"path": "..."}`.
- Each new note emits `artifact.generated` with intent `research_artifact_agent_note_v1:{id}:{hash}` (deduped).
- Findings and gaps must come from graph distill — never fabricate insight text in HTML.

## Handoff paste

Use **Copy as agent handoff** in the artifact, or paste the JSON block from `#antiek-artifact-v1`.

## Verification

```bash
./.venv/bin/python -m pytest tests/test_research_artifact_export.py -q
```