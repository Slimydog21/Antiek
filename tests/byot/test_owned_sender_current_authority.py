"""Current sender authority holds actual writers; all keys and routes are fixtures."""

from __future__ import annotations

import stat
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import settings_models_admin as models
from interfaces.research.api.settings_budget import register_settings_budget_routes
from runtime.byok.store import (
    CredentialIntegrityError,
    delete_credential,
    guard_current_credential,
    load_credential,
    prepare_current_master_key,
    store_credential_with_metadata,
)
from substrate.dispatch.providers.openai_compat import OpenAICompatProvider
from substrate.dispatch.router import (
    current_provider_registration,
    get_provider,
    register_provider,
    reset_provider_registry,
)

_KEY = b"k" * 32
_SECRET = "sk-fixture-current-owner-key-123456789"
_EMAIL = "current-owner@example.test"
_CREATE = {
    "provider_kind": "openai_compat",
    "provider_catalog_id": "deepseek",
    "model_id": "deepseek-flash",
    "display_name": "Current DeepSeek",
    "api_key": _SECRET,
}


@pytest.fixture
def private_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "master.key"))
    reset_provider_registry()
    app = FastAPI()

    @app.middleware("http")
    async def fixture_owner(request, call_next):
        request.state.user_id = "__operator__"
        request.state.user_email = _EMAIL
        request.state.auth_method = "antiek_session_cookie"
        return await call_next(request)

    register_settings_budget_routes(app)
    with TestClient(app) as client:
        yield client
    reset_provider_registry()


def test_guarded_credential_is_one_v3_record_and_blocks_delete(tmp_path: Path) -> None:
    artifact = str(tmp_path / "credentials.enc")
    saved = store_credential_with_metadata(
        "user-owner-model", _SECRET, pipeline_kind="model_provider",
        owner_user_id="owner-a", artifact_path=artifact, key_bytes=_KEY,
    )
    prepared = prepare_current_master_key(key_bytes=_KEY)
    assert load_credential(saved.cred_id, artifact_path=artifact,
                           key_bytes=_KEY).reveal() == _SECRET
    started = threading.Event()
    deleted = threading.Event()

    def writer() -> None:
        started.set()
        assert delete_credential(saved.cred_id, artifact_path=artifact)
        deleted.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with guard_current_credential(
            saved.cred_id, prepared_master_key=prepared, artifact_path=artifact,
        ) as current:
            assert current.metadata == saved
            assert current.metadata.binding_version == 3
            assert current.metadata.owner_user_id == "owner-a"
            assert current.secret.reveal() == _SECRET
            assert _SECRET.encode() not in Path(artifact).read_bytes()
            future = pool.submit(writer)
            assert started.wait(5)
            assert not deleted.wait(0.05)
        future.result(timeout=5)
    assert deleted.is_set()
    with pytest.raises(KeyError), guard_current_credential(
        saved.cred_id, prepared_master_key=prepared, artifact_path=artifact,
    ):
        pass


def test_master_preparation_reads_only_existing_private_key(tmp_path: Path) -> None:
    key_file = tmp_path / "master.key"
    with pytest.raises(FileNotFoundError):
        prepare_current_master_key(key_file=str(key_file))
    assert not key_file.exists()
    key_file.write_bytes(_KEY)
    key_file.chmod(0o600)
    assert prepare_current_master_key(key_file=str(key_file)) == _KEY
    key_file.chmod(0o640)
    with pytest.raises(CredentialIntegrityError):
        prepare_current_master_key(key_file=str(key_file))
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o640


def test_registration_snapshot_generation_and_writer_exclusion() -> None:
    reset_provider_registry()
    first = OpenAICompatProvider(name="owner-fixture", base_url="https://fixture.invalid", api_key=_SECRET)
    second = OpenAICompatProvider(name="owner-fixture", base_url="https://fixture.invalid", api_key=_SECRET)
    register_provider(first)
    entered = threading.Event()
    finished = threading.Event()

    def replace() -> None:
        entered.set()
        register_provider(second)
        finished.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with current_provider_registration("owner-fixture") as current:
            assert current.provider is first
            initial_generation = current.generation
            future = pool.submit(replace)
            assert entered.wait(5)
            assert not finished.wait(0.05)
        future.result(timeout=5)
    with current_provider_registration("owner-fixture") as changed:
        assert changed.provider is second
        assert changed.generation > initial_generation
        changed_generation = changed.generation
    assert get_provider("owner-fixture") is second
    reset_provider_registry()
    with pytest.raises(KeyError), current_provider_registration("owner-fixture"):
        pass
    register_provider(first)
    with current_provider_registration("owner-fixture") as after_reset:
        assert after_reset.provider is first
        assert after_reset.generation > changed_generation
    reset_provider_registry()


def test_reload_cannot_republish_deleted_record_or_seam(
    private_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = private_client.post("/settings/models/user", json=_CREATE)
    assert created.status_code == 201, created.text
    model_id = created.json()["id"]
    entered = threading.Event()
    release = threading.Event()
    delete_finished = threading.Event()
    real_make = models._make_provider

    def paused_real_adapter(record):
        if record.id == model_id:
            entered.set()
            assert release.wait(5)
        return real_make(record)

    def remove() -> int:
        response = private_client.delete(f"/settings/models/user/{model_id}")
        delete_finished.set()
        return response.status_code

    monkeypatch.setattr(models, "_make_provider", paused_real_adapter)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reload_future = pool.submit(models.reload_user_providers, private_client.app)
        try:
            assert entered.wait(5)
            delete_future = pool.submit(remove)
            assert not delete_finished.wait(0.05)
        finally:
            release.set()
        assert model_id in reload_future.result(timeout=5)
        assert delete_future.result(timeout=5) == 200
    assert models.reload_user_providers(private_client.app) == set()
    with models.current_user_model_record(model_id) as current:
        assert current is None
    assert model_id not in private_client.app.state.registered_providers
    assert model_id not in private_client.app.state.user_model_registration_fingerprints
    assert private_client.get("/settings/models/user").json()["models"] == []


def test_current_registry_guard_and_shared_builder_preserve_ordinary_route(
    private_client: TestClient,
) -> None:
    created = private_client.post("/settings/models/user", json=_CREATE)
    assert created.status_code == 201, created.text
    model_id = created.json()["id"]
    with models.current_user_model_record(model_id) as record:
        assert record is not None
        assert record.id == model_id
        assert record.cred_fingerprint is not None
        adapter = get_provider(model_id)
        assert isinstance(adapter, OpenAICompatProvider)
        built = adapter.build_request(
            model="deepseek-flash", prompt="fixture prompt", max_tokens=64,
            temperature=0.2, api_key=_SECRET,
        )
        assert built.url.endswith("/chat/completions")
        assert built.body["model"] == "deepseek-flash"
        assert built.body["thinking"] == {"type": "enabled"}
        assert built.body["messages"] == [{"role": "user", "content": "fixture prompt"}]
        assert built.headers["Authorization"] == f"Bearer {_SECRET}"
        no_thinking = adapter.build_request(
            model="deepseek-flash-nothink", prompt="fixture prompt", max_tokens=64,
            temperature=0.2, api_key=_SECRET,
        )
        assert no_thinking.model == "deepseek-flash"
        assert no_thinking.body["model"] == "deepseek-flash"
        assert no_thinking.body["thinking"] == {"type": "disabled"}
    assert private_client.delete(f"/settings/models/user/{model_id}").status_code == 200
