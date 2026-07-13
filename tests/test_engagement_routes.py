from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.engagement_routes import (
    register_engagement_routes,
    reset_engagement_stores,
)


def client() -> TestClient:
    app = FastAPI()
    register_engagement_routes(app)
    return TestClient(app)


def test_trimmed_surface_and_linked_session() -> None:
    reset_engagement_stores()
    api = client()
    response = api.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "book-1",
            "selection_text": "A guarded passage.",
            "region_id": "region-2",
            "view_mode": "floating",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["parent_asset_id"] == "book-1"
    assert body["selection_text"] == "A guarded passage."
    assert body["region_id"] == "region-2"
    assert body["session_id"].startswith("fsess_")
    assert body["spawn_id"].startswith("spn_")
    assert body["investigation_id"].startswith("inv_")
    assert body["view_format"] == "html"

    # Starlette 1.x nests included routers behind _IncludedRouter wrappers
    # (no .path); descend into original_router to collect registered paths.
    paths = set()
    for route in api.app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        for sub in getattr(getattr(route, "original_router", None), "routes", []):
            if hasattr(sub, "path"):
                paths.add(sub.path)
    paths = {p for p in paths if p.startswith("/engagement")}
    assert paths == {
        "/engagement/sessions/open",
        "/engagement/twins/{asset_id}",
        "/engagement/twins",
        "/engagement/merge",
    }


def test_durable_session_and_twins_reconstruct(tmp_path) -> None:
    root = tmp_path / "engagement"
    reset_engagement_stores(root=root)
    api = client()
    opened = api.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "durable-book",
            "selection_text": "Persistence is product behavior.",
            "region_id": "stable-region",
        },
    )
    assert opened.status_code == 200
    first = opened.json()
    note = api.post(
        "/engagement/twins",
        json={
            "asset_id": "durable-book",
            "kind": "insight",
            "text": "Stored beside the asset.",
            "source_spawn_id": first["spawn_id"],
        },
    )
    assert note.status_code == 200

    reset_engagement_stores(root=root)
    rebuilt = client()
    reopened = rebuilt.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "durable-book",
            "selection_text": "Persistence is product behavior.",
            "region_id": "stable-region",
        },
    )
    twins = rebuilt.get("/engagement/twins/durable-book")
    assert reopened.json()["session_id"] == first["session_id"]
    assert reopened.json()["spawn_id"] == first["spawn_id"]
    assert twins.json()["notes"][0]["text"] == "Stored beside the asset."


def test_blank_selection_is_rejected_without_store_write() -> None:
    reset_engagement_stores()
    response = client().post(
        "/engagement/sessions/open",
        json={"asset_id": "book-1", "selection_text": "   "},
    )
    assert response.status_code == 400
