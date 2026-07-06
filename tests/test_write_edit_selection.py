"""CK-5 — POST /write/edit-selection (Cmd+K selection edit).

Exercises the write router in isolation with dispatch monkeypatched at
``substrate.dispatch.dispatch`` (local import inside the handler).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import substrate.dispatch as dispatch_mod
from interfaces.research.api.write_routes import write_router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(write_router)
    return TestClient(app)


_EDIT_BODY = {
    "deliverable_id": "d1",
    "section_id": "s1",
    "selection_text": "The quick brown fox.",
    "instruction": "make it punchier",
}


def test_edit_selection_returns_edited_text(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResult:
        text = "EDITED SPAN"

    def fake_dispatch(**kwargs):
        return _FakeResult()

    monkeypatch.setattr(dispatch_mod, "dispatch", fake_dispatch)
    resp = client.post("/write/edit-selection", json=_EDIT_BODY)
    assert resp.status_code == 200
    assert resp.json()["edited_text"] == "EDITED SPAN"


def test_edit_selection_503_on_keyerror(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kw):
        raise KeyError("no role")

    monkeypatch.setattr(dispatch_mod, "dispatch", boom)
    resp = client.post("/write/edit-selection", json=_EDIT_BODY)
    assert resp.status_code == 503


def test_edit_selection_503_on_provider_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(dispatch_mod, "dispatch", boom)
    resp = client.post("/write/edit-selection", json=_EDIT_BODY)
    assert resp.status_code == 503


def test_edit_selection_rejects_empty_selection(client: TestClient) -> None:
    body = {**_EDIT_BODY, "selection_text": ""}
    resp = client.post("/write/edit-selection", json=body)
    assert resp.status_code == 422