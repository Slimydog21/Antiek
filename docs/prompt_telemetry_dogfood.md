# Prompt / question telemetry (research→notebook)

**SoT:** investigation event-log trajectory (`dispatch.call`, `investigation.start_requested`).
No parallel store. Full prompt bodies are **not** on `dispatch.call` (hash only);
the opening question is the start-event `question`.

## API

```bash
curl -sS "http://127.0.0.1:8000/investigations/<inv-id>/prompt-telemetry" | python -m json.tool
```

Fields: `question`, `calls[]` (`role`, `provider`, `model`, `finish_reason`,
`latency_ms`, `cost_usd`, `prompt_hash`, …), totals.

## UI

AutoNotebook (`/notebook/auto/<inv-id>`) shows a **Prompts & model calls**
section under the outline — citations stay in insights/questions; telemetry
is this panel.

## Mac Mini dogfood

```bash
# pick an inv with dispatch.call rows
INV=inv-df9521ebaea7   # example; substitute a live id
curl -sS "http://127.0.0.1:8000/investigations/$INV/prompt-telemetry" | head -c 2000
# open in reading app: /notebook/auto/$INV
```
