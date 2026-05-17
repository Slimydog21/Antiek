# interfaces/research/

Research workflow CLI and API.

## CLI surface (planned)

```
antiek research ingest <source-uri>           # one-off source ingestion
antiek research investigate <kanban-task-id>  # run an investigation end-to-end
antiek research synth show <synthesis-id>     # display an archived synthesis
antiek research audit                         # run the audit reports on demand
```

## API surface (planned)

A FastAPI app exposing:

- `POST /ingest` — accept a source URI, kick the acquisition path
- `POST /investigate` — kick a full investigation
- `GET /synthesis/{id}` — return an archived synthesis with all stamps

## Discipline

The interface layer is a thin wrapper over the substrate. It does not
contain business logic — it translates HTTP/CLI into typed events and
returns event-derived state.
