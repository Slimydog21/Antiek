from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


def test_manifest_launch_rejects_forbidden_context_before_delivery() -> None:
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    response = client.post(
        "/research/derived-assets/evidence-manifests/dem_" + "a" * 32 + "/launch",
        json={"question": "Compare this evidence", "context": "client supplied"},
        headers={"If-Match": '"etag"', "Idempotency-Key": "launch-1"},
    )
    assert response.status_code == 422


def test_manifest_launch_requires_precondition_and_idempotency_headers() -> None:
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    response = client.post(
        "/research/derived-assets/evidence-manifests/dem_" + "a" * 32 + "/launch",
        json={"question": "Compare this evidence"},
    )
    assert response.status_code == 428
