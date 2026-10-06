"""A failed append on POST /events/typed must not report 201.

`emit_typed` defaults to `strict_write=False`, and in that mode a write error is **swallowed,
printed to stderr, and the call still returns an event id**. `app.py:2548` therefore passes
`strict_write=True`, which is the only thing that makes the route's own `except` clause
reachable:

    except Exception as exc:  # Pydantic ValidationError or write error
        raise HTTPException(status_code=422, detail=str(exc)) from exc

**Without that argument the comment above it describes a branch that cannot be taken**, and the
route answers 201 for an event that was never written.

An adversarial audit of this repository's record found that no test detects the argument's
removal: dropping it restores the false 201 and **all ~70 existing API and schema tests still
pass**, because they exercise the schema rather than the write.

The load-bearing assertion is therefore not only the status code. It is that the route passes
`strict_write=True` at all -- the flag is what the behaviour depends on, and asserting only the
422 would pass if a future emitter default changed to strict and this route stopped asking.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-strictwrite-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmp, "graph.duckdb"))
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    # The route is operator-authenticated (401 without this). Set before create_app, so the
    # middleware reads it at construction.
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "operator-test-secret")
    return {"tmpdir": tmp, "auth": {"Authorization": "Bearer operator-test-secret"}}


def _client(temp_substrate: dict) -> TestClient:
    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def _minimal_payload() -> dict:
    """A body the discriminated union accepts, discovered rather than hardcoded.

    Two earlier versions of this helper failed for reasons unrelated to what the file tests:
    a hardcoded action_type needs that variant's own required fields, and picking the
    alphabetically-first variant selected `agent.work.transitioned`, which requires `work_id`
    and returned a Pydantic 422 that looked exactly like the write failure this file is about.

    So: choose a variant with no required fields beyond `action_type`, found by inspecting the
    models. If none exists, say so -- a silently empty body would make both tests below pass
    for the wrong reason.
    """
    import pydantic

    import substrate.schemas as schemas

    candidates = []
    for name in sorted(schemas.TYPED_PAYLOAD_ACTION_TYPES):
        model_name = "".join(part.capitalize() for part in name.replace(".", "_").split("_"))
        model = getattr(schemas, model_name + "Payload", None) or getattr(
            schemas, model_name, None
        )
        if not (isinstance(model, type) and issubclass(model, pydantic.BaseModel)):
            continue
        fields = getattr(model, "model_fields", {})
        required = [k for k, f in fields.items() if f.is_required() and k != "action_type"]
        if "action_type" in fields:
            candidates.append((len(required), name))

    bare = [name for count, name in candidates if count == 0]
    assert bare, (
        "no TypedPayload variant is constructible from `action_type` alone, so this file cannot "
        "build a valid body without hardcoding one variant's fields. Fix the helper rather than "
        f"hardcoding. Candidates by required-field count: {sorted(candidates)[:5]}"
    )
    return {"investigation_id": "inv-strictwrite", "payload": {"action_type": sorted(bare)[0]}}


def test_the_route_asks_for_a_strict_write(temp_substrate, monkeypatch):
    """THE test. Without this argument the false 201 comes back.

    A fake emitter that records how it was called and fails when asked to be strict. If the
    route stops passing `strict_write=True`, `seen` records False and this fails -- which is
    exactly the mutation the audit found nothing could catch.
    """
    seen: list[bool] = []

    def fake_emit_typed(*_args, strict_write: bool = False, **_kwargs):
        seen.append(strict_write)
        if strict_write:
            raise RuntimeError("simulated append failure")
        return "evt-that-was-never-written"

    # `from interfaces.research.api import app` yields the FastAPI INSTANCE, not the module --
    # the package re-exports the instance under the same name. sys.modules gets the module,
    # which is where `emit_typed` actually lives.
    import sys

    import interfaces.research.api.app  # noqa: F401  (import for the side effect of registration)

    app_mod = sys.modules["interfaces.research.api.app"]
    monkeypatch.setattr(app_mod, "emit_typed", fake_emit_typed)
    resp = _client(temp_substrate).post(
        "/events/typed", json=_minimal_payload(), headers=temp_substrate["auth"]
    )

    assert seen == [True], (
        "POST /events/typed called emit_typed with strict_write="
        f"{seen!r}. The route depends on True to make its own except clause reachable; with "
        "the default (False) a write error is swallowed and the route answers 201 for an "
        "event that was never written."
    )
    assert resp.status_code == 422, (
        f"a failed append returned {resp.status_code}, not 422. 2xx here means the client was "
        f"told its event was recorded. Body: {resp.text[:200]}"
    )


def test_a_non_strict_emitter_would_have_returned_201(temp_substrate, monkeypatch):
    """Drive the failure the first test exists to prevent.

    With the emitter behaving as its DEFAULT (False) does -- swallowing the error and
    returning an id -- the route answers 201. That is the defect, reproduced, so the
    assertion above is known to be testing something.
    """
    def lenient_emit_typed(*_args, **_kwargs):  # ignores strict_write, like the default path
        return "evt-that-was-never-written"

    import sys

    import interfaces.research.api.app  # noqa: F401

    app_mod = sys.modules["interfaces.research.api.app"]
    monkeypatch.setattr(app_mod, "emit_typed", lenient_emit_typed)
    resp = _client(temp_substrate).post(
        "/events/typed", json=_minimal_payload(), headers=temp_substrate["auth"]
    )
    assert resp.status_code == 201, (
        "this test asserts the shape of the defect. If it no longer reproduces, the first "
        "test may have stopped testing anything and this file needs re-reading."
    )
