from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.multimedia_local_routes import (
    get_multimedia_local_runtime,
    get_multimedia_local_runtime_optional,
)
from interfaces.research.api.multimedia_reconciliation_routes import (
    authenticated_multimedia_operator,
)
from interfaces.research.api.multimedia_routes import multimedia_router
from substrate.multimedia.local_workstation import (
    LocalPreparedChapter,
    LocalPreparedSet,
    LocalWorkstationError,
)

SET_ID = "mmlocalset_" + "a" * 64


def _response(status: str = "review_required") -> LocalPreparedSet:
    return LocalPreparedSet(
        set_id=SET_ID,
        asset_id="asset-1",
        revision_id="revision-1",
        status=status,  # type: ignore[arg-type]
        recoverable=status in {"preparation_unknown", "production_unknown"},
        playback_ready=status == "registered",
        chapters=(LocalPreparedChapter(
            chapter_id="chapter-1", title="Flow", narration_ready=True,
            card_id="card-1", card_ready=True,
            attested=status in {"ready_to_produce", "registered"}, source_count=1,
        ),),
    )


class Runtime:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.fail = False

    def _return(self, name: str, *values):  # noqa: ANN002, ANN202
        self.calls.append((name, *values))
        if self.fail:
            raise LocalWorkstationError("local prepared set is unavailable")
        statuses = {
            "prepare": "review_required", "inspect": "review_required",
            "attest": "ready_to_produce", "produce": "registered",
            "recover": "review_required",
        }
        return _response(statuses[name])

    def prepare(self, asset_id, revision_id, *, owner_id):  # noqa: ANN001, ANN201
        return self._return("prepare", asset_id, revision_id, owner_id)

    def inspect(self, asset_id, revision_id, set_id, *, owner_id):  # noqa: ANN001, ANN201
        return self._return("inspect", asset_id, revision_id, set_id, owner_id)

    def attest(self, asset_id, revision_id, set_id, card_id, *, owner_id):  # noqa: ANN001, ANN201
        return self._return("attest", asset_id, revision_id, set_id, card_id, owner_id)

    def produce(self, asset_id, revision_id, set_id, *, owner_id):  # noqa: ANN001, ANN201
        return self._return("produce", asset_id, revision_id, set_id, owner_id)

    def recover(self, asset_id, revision_id, set_id, *, owner_id):  # noqa: ANN001, ANN201
        return self._return("recover", asset_id, revision_id, set_id, owner_id)

    def preview_card(self, asset_id, revision_id, set_id, card_id, *, owner_id):  # noqa: ANN001, ANN201
        self.calls.append(("preview", asset_id, revision_id, set_id, card_id, owner_id))
        return b"\x89PNG\r\n\x1a\nfixture"


def _client(runtime: Runtime | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(multimedia_router)
    app.dependency_overrides[authenticated_multimedia_operator] = lambda: "owner-1"
    app.dependency_overrides[get_multimedia_local_runtime_optional] = lambda: runtime
    if runtime is not None:
        app.dependency_overrides[get_multimedia_local_runtime] = lambda: runtime
    return TestClient(app)


def test_capability_is_opaque_for_ready_and_unavailable_runtime() -> None:
    assert _client(Runtime()).get("/multimedia/local/capability").json() == {
        "available": True, "reason": "ready", "route_policy": "cheapest", "cost_usd": 0.0,
    }
    assert _client().get("/multimedia/local/capability").json() == {
        "available": False, "reason": "unavailable", "route_policy": "cheapest", "cost_usd": 0.0,
    }


def test_authenticated_commands_pass_only_owner_revision_and_opaque_set() -> None:
    runtime = Runtime()
    client = _client(runtime)
    assert client.post(
        "/multimedia/assets/asset-1/local/prepare",
        json={"expected_revision_id": "revision-1"},
    ).status_code == 200
    preview = client.get(
        f"/multimedia/assets/asset-1/local/revision-1/{SET_ID}/cards/card-1/content"
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["cache-control"] == "private, no-store"
    assert client.get(
        f"/multimedia/assets/asset-1/local/revision-1/{SET_ID}"
    ).status_code == 200
    assert client.post(
        "/multimedia/assets/asset-1/local/cards/card-1/attest",
        json={"expected_revision_id": "revision-1", "set_id": SET_ID},
    ).json()["status"] == "ready_to_produce"
    assert client.post(
        "/multimedia/assets/asset-1/local/produce",
        json={"expected_revision_id": "revision-1", "set_id": SET_ID},
    ).json()["status"] == "registered"
    assert client.post(
        "/multimedia/assets/asset-1/local/recover",
        json={"expected_revision_id": "revision-1", "set_id": SET_ID},
    ).status_code == 200
    assert all(call[-1] == "owner-1" for call in runtime.calls)


def test_browser_cannot_supply_authority_fields_and_errors_are_opaque() -> None:
    runtime = Runtime()
    client = _client(runtime)
    body = {"expected_revision_id": "revision-1", "set_id": SET_ID}
    forbidden = client.post(
        "/multimedia/assets/asset-1/local/produce",
        json={**body, "output_path": "/tmp/forged", "input_digest": "0" * 64},
    )
    assert forbidden.status_code == 422
    runtime.fail = True
    missing = client.post(
        "/multimedia/assets/asset-1/local/produce", json=body
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "local multimedia authority is unavailable"}


def test_commands_fail_503_when_runtime_is_absent() -> None:
    response = _client().post(
        "/multimedia/assets/asset-1/local/prepare",
        json={"expected_revision_id": "revision-1"},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "local multimedia runtime is unavailable"}
