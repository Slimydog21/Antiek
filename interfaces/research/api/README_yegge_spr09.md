# SPR-09 — agent-loved API surface conventions

This file documents the conventions introduced by SPR-09 (Yegge-execute
spec). Read it before adding any new route to
`interfaces/research/api/`. **Existing routes are intentionally
unchanged in this sprint** — operator has in-flight parallel work on
`app.py` and the route modules; legacy migration is future-batch.

## Three additive primitives

| Module | Purpose |
|---|---|
| `envelope.py` | `ResponseEnvelope[T]`, `ErrorEnvelope`, closed `ERROR_CODES` set, `EnvelopedHTTPException`, `install_exception_handler(app)` |
| `idempotency.py` | `IdempotencyCache`, `require_idempotency_key(...)`, `record_completion(...)` |
| `discovery.py` | `router` exposing `/.well-known/mcp.json` + `/discovery` |

`/openapi.json` is free from FastAPI; no work required here.

## Activation (one-line each, when operator gets to it)

In `app.py` at app construction:

```python
from interfaces.research.api.envelope import install_exception_handler
from interfaces.research.api.discovery import router as discovery_router

install_exception_handler(app)
app.include_router(discovery_router)
```

These two lines are safe additions to `app.py`. They do not modify any
existing route's behavior.

## Convention for NEW routes

### Success path

```python
from interfaces.research.api.envelope import ResponseEnvelope

@router.get("/thing/{thing_id}", response_model=ResponseEnvelope[ThingData])
async def get_thing(thing_id: str) -> ResponseEnvelope[ThingData]:
    thing = await fetch(thing_id)
    return ResponseEnvelope.success(data=thing)
```

### Failure path — raise, don't return

```python
from interfaces.research.api.envelope import EnvelopedHTTPException

@router.get("/thing/{thing_id}", response_model=ResponseEnvelope[ThingData])
async def get_thing(thing_id: str) -> ResponseEnvelope[ThingData]:
    thing = await fetch(thing_id)
    if thing is None:
        raise EnvelopedHTTPException(
            code="NOT_FOUND",
            message=f"thing {thing_id!r} does not exist",
            status_code=404,
        )
    return ResponseEnvelope.success(data=thing)
```

The central handler (registered by `install_exception_handler`)
converts the exception into the canonical failure shape.

### Idempotency for POST/PUT

```python
from fastapi import Header
from interfaces.research.api.idempotency import (
    require_idempotency_key, record_completion,
)
from interfaces.research.api.envelope import ResponseEnvelope

@router.post("/thing")
async def create_thing(
    body: CreateThing,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ResponseEnvelope[ThingData]:
    key = await require_idempotency_key("POST /thing", idempotency_key)
    thing = await do_create(body)
    response = ResponseEnvelope.success(data=thing)
    await record_completion("POST /thing", key,
                            status_code=201, body=response.model_dump())
    return response
```

Replays return `error.code="IDEMPOTENCY_REPLAY"` with the prior response
in `details`. Missing header returns `error.code="IDEMPOTENCY_KEY_REQUIRED"`.

## Error codes (closed set)

See `envelope.py:ERROR_CODES`. Extending the set requires a code review
on that constant — the discoverability guarantee only works if codes
don't multiply silently.

## Why additive only?

The operator has in-flight changes to `app.py` and several route
modules (`feature/are/wave-1-substrate-additive` branch). Wrapping
existing routes in this sprint would create a guaranteed merge
conflict on every changed file. The convention applies to new routes
now; a future "batch 2" sprint owns the legacy migration once the
operator's wave-1 work lands.

## Reversal conditions

- If FastAPI ships a built-in envelope convention that matches Antiek's
  needs, this module gets a deprecation note and the convention shifts.
- If agent callers turn out to consistently fail on the legacy raw-FastAPI
  shape (measure via the substrate's existing logging), the legacy
  migration moves up the priority list.

Spec: `~/specs/antiek-yegge-execute/sprint-09-agent-loved-api.html`
