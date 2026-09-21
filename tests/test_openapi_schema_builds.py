"""``/openapi.json`` must actually build.

On 2026-09-20 it returned HTTP 500 on main. ``app.openapi()`` raised
``PydanticUserError``: ``PublisherClaimRequest`` was declared INSIDE
``create_app`` while ``interfaces/research/api/app.py`` sets
``from __future__ import annotations``, so the handler's ``req:
PublisherClaimRequest`` annotation is a *string* that Pydantic resolves
against module globals when it builds the request-body TypeAdapter. A class
in the factory's local scope is not in those globals.

One misplaced class took down the entire schema, not just that route.

The defect was invisible from outside: unauthenticated callers get 401 from
the auth middleware before routing, so the 500 only reaches a client that is
already logged in. That is also why no probe caught it -- the failing status
was masked by a healthier-looking one.

Thirty-two sibling models stay local and are fine: they are only passed as
``response_model=X``, which hands Pydantic the class OBJECT rather than a
name to resolve. Only a PARAMETER annotation goes through string lookup.
"""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app

_APP_SOURCE = Path(__file__).resolve().parents[1] / "interfaces" / "research" / "api" / "app.py"


def test_openapi_schema_builds() -> None:
    """The whole schema, not a sampled route."""
    spec = create_app().openapi()
    assert spec["paths"], "openapi built but declared no paths"


def test_openapi_json_route_returns_200() -> None:
    """End to end, the way a logged-in client hits it."""
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200, (
        f"GET /openapi.json returned {resp.status_code}; the schema failed to "
        "build. An unauthenticated probe cannot see this — auth answers 401 "
        "before routing."
    )


def test_no_route_parameter_is_annotated_with_a_factory_local_model() -> None:
    """Catch the CAUSE, so the next one fails here rather than at runtime.

    A ``BaseModel`` declared inside ``create_app`` and used as a route
    PARAMETER annotation cannot be resolved under postponed annotations.
    Using one as ``response_model=`` is fine and stays allowed.
    """
    tree = ast.parse(_APP_SOURCE.read_text(encoding="utf-8"))
    factories = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "create_app"
    ]
    assert factories, "create_app not found — this guard would be vacuous"
    offenders: list[str] = []
    for factory in factories:
        local = {
            n.name
            for n in ast.walk(factory)
            if isinstance(n, ast.ClassDef)
            and any(getattr(b, "id", "") == "BaseModel" for b in n.bases)
        }
        assert local, "no local BaseModel classes found — scanner is broken"
        for handler in ast.walk(factory):
            if not isinstance(handler, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any(
                "app." in ast.unparse(d) or "router." in ast.unparse(d)
                for d in handler.decorator_list
            ):
                continue
            args = list(handler.args.args) + list(handler.args.kwonlyargs)
            for arg in args:
                if arg.annotation is None:
                    continue
                annotation = ast.unparse(arg.annotation)
                for name in local:
                    if name in annotation:
                        offenders.append(
                            f"{handler.name}(... {arg.arg}: {name}) "
                            f"at line {handler.lineno}"
                        )
    assert not offenders, (
        "these route parameters are annotated with a BaseModel declared inside "
        "create_app; under `from __future__ import annotations` Pydantic cannot "
        "resolve them and app.openapi() raises, taking the WHOLE schema down:\n  "
        + "\n  ".join(offenders)
        + "\nMove the model to module level."
    )
