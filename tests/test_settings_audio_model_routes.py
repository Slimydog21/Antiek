"""Actual private account middleware and encrypted audio settings, without sends."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Never

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.auth import reset_auth_throttles
from interfaces.research.api.settings_audio_model_routes import (
    _AppAudioBinding,
    register_settings_audio_model_routes,
)
from interfaces.research.api.settings_audio_models import AudioModelService, AudioModelUnavailable
from interfaces.research.api.settings_models_admin import UserModelChoice
from runtime.byok import store
from substrate.auth import MockEmailProvider

SECRET = "UNIT-audio-http-secret-not-a-provider-key"
ALICE = "audio-alice@example.test"
BOB = "audio-bob@example.test"
OPERATOR = "audio-original@example.test"
PREFIX = "/settings/audio-models"


@dataclass
class PrivateAPI:
    app: FastAPI
    sender: MockEmailProvider
    root: Path
    artifact: Path
    key: Path


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PrivateAPI:
    root = tmp_path / "state"
    vault = tmp_path / "existing-vault"
    root.mkdir(mode=0o700)
    vault.mkdir(mode=0o700)
    artifact, key = vault / "credentials.enc", vault / "master.key"
    artifact.write_text("{}")
    key.write_bytes(bytes(range(32)))
    artifact.chmod(0o600)
    key.chmod(0o600)
    configured = {
        "ANTIEK_HOME": str(root),
        "ANTIEK_STATE_DIR": str(root),
        "ANTIEK_BYOK_ARTIFACT": str(artifact),
        "ANTIEK_BYOK_KEY_FILE": str(key),
        "ANTIEK_AUTH_SECRET": "UNIT-audio-http-auth-" + "x" * 48,
        "ANTIEK_OPERATOR_EMAIL": OPERATOR,
        "ANTIEK_LEGACY_OPERATOR_EMAIL": OPERATOR,
        "ANTIEK_OPEN_SIGNUP": "1",
        "ANTIEK_COOKIE_INSECURE": "1",
        "ANTIEK_ACCOUNT_STORE": str(tmp_path / "accounts.json"),
        "ANTIEK_PASSKEY_STORE": str(tmp_path / "passkeys.json"),
        "ANTIEK_USER_MODELS_PATH": str(tmp_path / "text-models.json"),
    }
    for name, value in configured.items():
        monkeypatch.setenv(name, value)
    for name in (
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    sender = MockEmailProvider(log_to_stdout=False)
    monkeypatch.setattr("interfaces.research.api.auth.get_email_provider", lambda: sender)
    reset_auth_throttles()
    app = create_app(register_wrestling=False, register_providers=False)
    return PrivateAPI(app, sender, root, artifact, key)


def sign_in(api: PrivateAPI, email: str = ALICE) -> TestClient:
    client = TestClient(api.app)
    requested = client.post("/auth/request", json={"email": email})
    assert requested.status_code == 200
    code = api.sender.sent[-1].email.subject.rsplit("·", 1)[-1].strip()
    payload = requested.json()
    claimed = client.post(
        "/auth/claim",
        json={
            "attempt_id": payload["attempt_id"],
            "claim_secret": payload["claim_secret"],
            "code": code,
        },
    )
    assert claimed.status_code == 200 and claimed.json()["authenticated"] is True
    return client


def payload() -> dict[str, object]:
    return {
        "catalog_id": "openai",
        "model_id": "whisper-1",
        "endpoint": "https://api.openai.com",
        "display_name": "Private microphone",
        "api_key": SECRET,
    }


def create(client: TestClient) -> str:
    response = client.post(PREFIX + "/user", json=payload())
    assert response.status_code == 201
    assert response.json()["registered"] is True
    assert response.json()["dispatch_authority"] == "unbound"
    assert response.headers["Cache-Control"] == "private, no-store"
    return str(response.json()["id"])


def binding(api: PrivateAPI) -> _AppAudioBinding:
    value = api.app.state.audio_model_binding
    assert isinstance(value, _AppAudioBinding)
    return value


def test_real_account_create_list_disable_delete_and_existing_vault(
    api: PrivateAPI,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    alice, bob = sign_in(api), sign_in(api, BOB)
    record = create(alice)
    listed = alice.get(PREFIX + "/user")
    assert listed.status_code == 200 and listed.json()["models"][0]["id"] == record
    assert bob.get(PREFIX + "/user").json() == {"models": []}
    metadata = store.list_credentials(artifact_path=str(api.artifact))
    assert len(metadata) == 1 and metadata[0].binding_version == 3
    assert metadata[0].owner_user_id == alice.get("/auth/me").json()["user_id"]
    assert (
        store.load_credential(
            metadata[0].cred_id, artifact_path=str(api.artifact), key_file=str(api.key)
        ).reveal()
        == SECRET
    )
    assert not (api.root / "byok" / "credentials.enc").exists()
    assert SECRET not in api.artifact.read_text()
    assert SECRET not in (api.root / "settings" / "user_audio_models.json").read_text()
    assert SECRET not in listed.text + caplog.text + str(capsys.readouterr())
    assert (
        not {"credential_id", "credential_fingerprint", "api_key", "ciphertext"}
        & listed.json()["models"][0].keys()
    )
    disabled = alice.patch(PREFIX + "/user/" + record, json={"enabled": False})
    assert disabled.status_code == 204 and disabled.content == b""
    assert alice.get(PREFIX + "/user").json()["models"][0]["enabled"] is False
    deleted = alice.delete(PREFIX + "/user/" + record)
    assert deleted.status_code == 200 and deleted.json() == {"credential_removed": True}
    assert alice.get(PREFIX + "/user").json() == {"models": []}
    assert store.list_credentials(artifact_path=str(api.artifact)) == []


def test_foreign_and_missing_ids_indistinguishable_without_retiring_owner(api: PrivateAPI) -> None:
    alice, bob = sign_in(api), sign_in(api, BOB)
    record = create(alice)
    for method in ("PATCH", "DELETE"):
        body = {"enabled": False} if method == "PATCH" else None
        foreign = bob.request(method, PREFIX + "/user/" + record, json=body)
        missing = bob.request(method, PREFIX + "/user/missing", json=body)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
        assert foreign.headers["Cache-Control"] == "private, no-store"
    assert alice.get(PREFIX + "/user").json()["models"][0]["registered"] is True


def test_same_app_registration_and_restart_are_distinct(api: PrivateAPI) -> None:
    alice = sign_in(api)
    record = create(alice)
    assert alice.get(PREFIX + "/user").json()["models"][0]["registered"] is True
    other_app = create_app(register_wrestling=False, register_providers=False)
    restarted = TestClient(other_app)
    restarted.cookies.update(alice.cookies)
    row = restarted.get(PREFIX + "/user").json()["models"][0]
    assert row["id"] == record and row["registered"] is False
    assert row["dispatch_authority"] == "unbound"
    assert alice.get(PREFIX + "/user").json()["models"][0]["registered"] is True
    assert other_app.state.audio_model_binding is not binding(api)


def test_catalogue_needs_account_but_no_private_binding(
    api: PrivateAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = sign_in(api)
    api.key.unlink()

    def forbidden(**_kwargs: object) -> bytes:
        raise AssertionError("catalogue cannot prepare private key")

    monkeypatch.setattr(store, "prepare_current_master_key", forbidden)
    response = alice.get(PREFIX + "/catalog")
    assert response.status_code == 200
    assert response.json() == {
        "models": [
            {
                "catalog_id": "openai",
                "model_id": "whisper-1",
                "adapter_kind": "audio_transcription",
                "operation": "transcribe",
                "endpoint": "https://api.openai.com",
                "request_path": "/v1/audio/transcriptions",
            }
        ]
    }
    assert response.headers["Cache-Control"] == "private, no-store"
    assert binding(api)._service is None


@pytest.mark.parametrize("actor", ["anonymous", "operator", "bearer", "legacy", "forged-subject"])
def test_refusal_precedes_private_binding_and_body_decoder(
    api: PrivateAPI,
    monkeypatch: pytest.MonkeyPatch,
    actor: str,
) -> None:
    import interfaces.research.api.settings_audio_model_routes as routes
    from substrate.auth import mint_session_cookie

    client = sign_in(api, OPERATOR) if actor == "operator" else TestClient(api.app)
    if actor == "bearer":
        monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", "UNIT-machine-token")
        client = TestClient(create_app(register_wrestling=False, register_providers=False))
        client.headers["Authorization"] = "Bearer UNIT-machine-token"
    elif actor in {"legacy", "forged-subject"}:
        user_id = "__operator__" if actor == "legacy" else "acct_" + "f" * 32
        client.cookies.set("ANTIEK_SESSION", mint_session_cookie(user_id=user_id, email=ALICE))

    def forbidden(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("refused actor cannot prepare key")

    async def forbidden_body(_request: Request) -> dict[str, object]:
        raise AssertionError("refused actor cannot parse body")

    monkeypatch.setattr(store, "prepare_current_master_key", forbidden)
    monkeypatch.setattr(routes, "_body", forbidden_body)
    before = api.artifact.read_bytes()
    response = client.post(PREFIX + "/user", content=SECRET)
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "private, no-store"
    assert SECRET not in response.text
    assert api.artifact.read_bytes() == before and binding(api)._service is None


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"[]",
        b"null",
        b'{"api_key":NaN}',
        b'{"api_key":Infinity}',
        b'{"enabled":false,"enabled":false}',
        b'"UNIT-audio-http-secret-not-a-provider-key"',
    ],
)
def test_malformed_body_is_value_free_before_private_work(api: PrivateAPI, body: bytes) -> None:
    alice = sign_in(api)
    response = alice.post(PREFIX + "/user", content=body)
    assert response.status_code == 422 and SECRET not in response.text
    assert response.headers["Cache-Control"] == "private, no-store"
    assert binding(api)._service is None


@pytest.mark.parametrize(
    "changed",
    [
        {"extra": SECRET},
        {"endpoint": "https://attacker.example"},
        {"model_id": "text-default"},
        {"api_key": 32},
        {"api_key": "short"},
        {"display_name": SECRET},
        {"catalog_id": "other"},
    ],
)
def test_create_payload_preserves_exact_service_contract(
    api: PrivateAPI, changed: dict[str, object]
) -> None:
    alice = sign_in(api)
    response = alice.post(PREFIX + "/user", json={**payload(), **changed})
    assert response.status_code == 422 and SECRET not in response.text
    assert binding(api)._service is None and api.artifact.read_text() == "{}"


@pytest.mark.parametrize("size,status", [(8192, 201), (8193, 413)])
def test_body_byte_limit_is_inclusive(api: PrivateAPI, size: int, status: int) -> None:
    alice = sign_in(api)
    body = json.dumps(payload()).encode()
    body += b" " * (size - len(body))
    response = alice.post(PREFIX + "/user", content=body)
    assert response.status_code == status
    assert response.headers["Cache-Control"] == "private, no-store"
    assert SECRET not in response.text
    if status == 413:
        assert binding(api)._service is None and api.artifact.read_text() == "{}"


@pytest.mark.parametrize(
    "body", [{"enabled": True}, {"enabled": 0}, {"enabled": False, "extra": SECRET}, {}]
)
def test_patch_is_disable_only(api: PrivateAPI, body: dict[str, object]) -> None:
    alice = sign_in(api)
    record = create(alice)
    response = alice.patch(PREFIX + "/user/" + record, json=body)
    assert response.status_code == 422 and SECRET not in response.text
    assert alice.get(PREFIX + "/user").json()["models"][0]["enabled"] is True


@pytest.mark.parametrize(
    "damage",
    [
        "key-missing",
        "artifact-missing",
        "root-missing",
        "key-symlink",
        "artifact-symlink",
        "key-mode",
        "artifact-mode",
        "root-mode",
        "key-short",
        "artifact-corrupt",
        "artifact-row-corrupt",
        "key-hardlink",
        "artifact-hardlink",
        "artifact-lock-mode",
        "key-lock-symlink",
    ],
)
def test_unsafe_or_missing_binding_is_unavailable_without_repair(
    api: PrivateAPI, damage: str
) -> None:
    alice = sign_in(api)
    if damage.endswith("missing"):
        path = {"key-missing": api.key, "artifact-missing": api.artifact, "root-missing": api.root}[
            damage
        ]
        if path.is_dir():
            import shutil

            shutil.rmtree(path)
        else:
            path.unlink()
    elif damage.endswith("symlink"):
        target = api.key if damage == "key-symlink" else api.artifact
        if damage == "key-lock-symlink":
            target = api.key.with_name(api.key.name + ".lock")
            target.symlink_to(api.key)
        else:
            moved = target.with_suffix(".retained")
            target.rename(moved)
            target.symlink_to(moved)
    elif damage.endswith("mode"):
        mode_target = {
            "key-mode": api.key,
            "artifact-mode": api.artifact,
            "root-mode": api.root,
        }.get(damage)
        if mode_target is None:
            mode_target = api.artifact.with_name(api.artifact.name + ".lock")
            mode_target.write_bytes(b"")
        mode_target.chmod(0o755 if mode_target == api.root else 0o644)
    elif damage.endswith("hardlink"):
        target = api.key if damage == "key-hardlink" else api.artifact
        os.link(target, target.with_suffix(".hardlinked"))
    elif damage == "key-short":
        api.key.write_bytes(b"UNIT")
    else:
        api.artifact.write_text(
            "not-json" if damage == "artifact-corrupt" else '{"bad":{"ciphertext_hex":"bad"}}'
        )
    names = set(api.artifact.parent.iterdir())
    modes = {p: p.lstat().st_mode for p in names}
    response = alice.get(PREFIX + "/user")
    assert response.status_code == 503
    assert response.json() in (
        {"detail": "audio model unavailable"},
        {"detail": "audio models unavailable"},
    )
    assert response.headers["Cache-Control"] == "private, no-store"
    assert SECRET not in response.text and str(api.root) not in response.text
    assert set(api.artifact.parent.iterdir()) == names
    assert {p: p.lstat().st_mode for p in names} == modes
    assert binding(api)._service is None


@pytest.mark.parametrize("changed", ["key", "artifact", "root"])
def test_replaced_binding_retires_old_selection_and_cannot_rearm_same_app(
    api: PrivateAPI,
    changed: str,
) -> None:
    alice = sign_in(api)
    record = create(alice)
    service = binding(api)._service
    assert service is not None
    request = Request({"type": "http", "method": "GET", "path": "/unit", "headers": []})
    request.state.user_id = alice.get("/auth/me").json()["user_id"]
    request.state.account_subject = request.state.user_id
    request.state.auth_method = "antiek_session_cookie"
    selection = service.capture(
        request, UserModelChoice(authority="user_model", provider_id=record, model_id="whisper-1")
    )
    if changed == "root":
        api.root.rename(api.root.with_name("retained-state"))
        api.root.mkdir(mode=0o700)
    else:
        target = api.key if changed == "key" else api.artifact
        replacement = target.with_suffix(".new")
        replacement.write_bytes(
            bytes(reversed(range(32))) if changed == "key" else target.read_bytes()
        )
        replacement.chmod(0o600)
        replacement.replace(target)
    assert alice.get(PREFIX + "/user").status_code == 503
    assert alice.get(PREFIX + "/user").status_code == 503
    assert binding(api)._service is None
    with pytest.raises(AudioModelUnavailable), service.guard_selection(request, selection):
        pytest.fail("retired selection admitted")


def test_delete_reports_actual_missing_credential_outcome(api: PrivateAPI) -> None:
    alice = sign_in(api)
    record = create(alice)
    credential = store.list_credentials(artifact_path=str(api.artifact))[0]
    assert store.delete_credential(credential.cred_id, artifact_path=str(api.artifact)) is True
    receiving = TestClient(create_app(register_wrestling=False, register_providers=False))
    receiving.cookies.update(alice.cookies)
    response = receiving.delete(PREFIX + "/user/" + record)
    assert response.status_code == 200 and response.json() == {"credential_removed": False}


def test_external_credential_removal_quarantines_already_live_binding(api: PrivateAPI) -> None:
    alice = sign_in(api)
    record = create(alice)
    live_service = binding(api)._service
    assert live_service is not None and live_service._registrations
    credential = store.list_credentials(artifact_path=str(api.artifact))[0]
    assert store.delete_credential(credential.cred_id, artifact_path=str(api.artifact)) is True
    assert alice.get(PREFIX + "/user").status_code == 503
    assert binding(api)._service is None and live_service._registrations == {}
    assert alice.get(PREFIX + "/user").status_code == 503
    refused = alice.delete(PREFIX + "/user/" + record)
    assert refused.status_code == 503 and "credential_removed" not in refused.json()
    assert binding(api)._service is None and api.artifact.read_text() == "{}"


def test_publication_failure_reports_unconfirmed_cleanup_without_echo(
    api: PrivateAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = sign_in(api)

    def failed_write(*_args: object, **_kwargs: object) -> None:
        raise OSError(SECRET)

    monkeypatch.setattr(AudioModelService, "_write", failed_write)
    response = alice.post(PREFIX + "/user", json=payload())
    assert response.status_code == 409
    assert response.json() == {
        "detail": "audio publication unconfirmed",
        "credential_cleanup_confirmed": False,
    }
    assert SECRET not in response.text


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/catalog"),
        ("PUT", "/user"),
        ("GET", "/user/arbitrary"),
        ("POST", "/user/arbitrary"),
        ("POST", "/user/arbitrary/resolve"),
        ("POST", "/send"),
    ],
)
def test_only_five_exact_method_path_pairs_are_admitted(
    api: PrivateAPI, method: str, path: str
) -> None:
    alice = sign_in(api)
    response = alice.request(method, PREFIX + path, json=payload())
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"
    assert binding(api)._service is None


def test_registration_performs_no_private_IO(monkeypatch: pytest.MonkeyPatch) -> None:
    import interfaces.research.api.settings_audio_model_routes as routes

    def forbidden(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError("private binding used during registration")

    monkeypatch.setattr(routes, "_server_paths", forbidden)
    monkeypatch.setattr(store, "prepare_current_master_key", forbidden)
    app = FastAPI()
    register_settings_audio_model_routes(app)
    assert isinstance(app.state.audio_model_binding, _AppAudioBinding)
    assert app.state.audio_model_binding._service is None
    assert len([r for r in app.routes if getattr(r, "path", "").startswith(PREFIX)]) == 5


def test_constructor_injection_is_absolute_and_keeps_direct_default(tmp_path: Path) -> None:
    direct = AudioModelService(state_root=tmp_path, prepared_master_key=bytes(32))
    assert direct._artifact == str(tmp_path / "byok" / "credentials.enc")
    for bad in (Path("relative"), tmp_path / ".." / "other.enc"):
        with pytest.raises(AudioModelUnavailable):
            AudioModelService(state_root=tmp_path, prepared_master_key=bytes(32), artifact_path=bad)


def test_key_work_is_off_loop_while_same_loop_catalogue_remains_available(
    api: PrivateAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = sign_in(api)
    entered, release = threading.Event(), threading.Event()
    original = store.prepare_current_master_key
    worker_ids: list[int] = []

    def blocked(*, key_bytes: bytes | None = None, key_file: str | None = None) -> bytes:
        worker_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(3)
        return original(key_bytes=key_bytes, key_file=key_file)

    monkeypatch.setattr(store, "prepare_current_master_key", blocked)

    async def exercise() -> None:
        loop_thread = threading.get_ident()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api.app),
            base_url=str(alice.base_url),
            cookies=alice.cookies,
        ) as client:
            pending = asyncio.create_task(client.get(PREFIX + "/user"))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                catalog = await asyncio.wait_for(client.get(PREFIX + "/catalog"), 1)
                assert catalog.status_code == 200
                assert worker_ids and all(value != loop_thread for value in worker_ids)
            finally:
                release.set()
            assert (await pending).status_code == 200

    asyncio.run(exercise())
