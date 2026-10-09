"""Real private SecretBox controls; request stamps do not certify a production mount."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from pydantic import ValidationError

from interfaces.research.api.settings_audio_models import (
    AudioModelService,
    AudioModelUnavailable,
    AudioPublicationError,
    UserAudioModelRecord,
)
from interfaces.research.api.settings_models_admin import UserModelChoice
from runtime.byok import store
from runtime.research_runner.audio_provider_catalog import get_audio_model
from runtime.research_runner.byot_provider_catalog import BYOT_PROVIDER_PRESETS

A = "acct_" + "a" * 32
B = "acct_" + "b" * 32
SECRET = "UNIT-audio-key-not-a-provider-credential"
KEY = bytes(range(32))


def request(
    owner: str = A, *, method: str = "antiek_session_cookie", subject: str | None = None
) -> Request:
    result = Request({"type": "http", "method": "POST", "path": "/unit", "headers": []})
    result.state.user_id = owner
    result.state.account_subject = subject if subject is not None else owner
    result.state.auth_method = method
    return result


def payload() -> dict[str, object]:
    return {
        "catalog_id": "openai",
        "model_id": "whisper-1",
        "endpoint": "https://api.openai.com",
        "display_name": "Private microphone",
        "api_key": SECRET,
    }


@pytest.fixture
def service(tmp_path: Path) -> AudioModelService:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    return AudioModelService(state_root=root, prepared_master_key=KEY)


def choice(record_id: str, model_id: str = "whisper-1") -> UserModelChoice:
    return UserModelChoice(authority="user_model", provider_id=record_id, model_id=model_id)


def registry(service: AudioModelService) -> Path:
    return service._root / "settings" / "user_audio_models.json"


def artifact(service: AudioModelService) -> Path:
    return Path(service._artifact)


def test_create_authenticated_selection_nonsecret(
    service: AudioModelService, capsys: pytest.CaptureFixture[str]
) -> None:
    public = service.create(request(), payload())
    result = service.capture(request(), choice(str(public["id"])))
    assert result.dispatch_authority == "unbound"
    with service.guard_selection(request(), result) as current:
        assert current is result
        assert current.descriptor.request_path == "/v1/audio/transcriptions"
    assert public["registered"] is True
    assert service.list(request()) == [public]
    assert service.list(request(B)) == []
    assert SECRET not in artifact(service).read_text()
    assert SECRET not in registry(service).read_text()
    assert "ciphertext_hex" in artifact(service).read_text()
    assert not {"credential_id", "credential_fingerprint", "api_key", "ciphertext"} & public.keys()
    assert SECRET not in repr(result)
    assert SECRET not in str(capsys.readouterr())
    assert store.list_credentials(artifact_path=service._artifact)[0].binding_version == 3


@pytest.mark.parametrize(
    "owner,method,subject",
    [
        ("__operator__", "antiek_session_cookie", "__operator__"),
        ("email-owner", "antiek_session_cookie", "email-owner"),
        (A, "bearer_token", A),
        (A, "antiek_session_cookie", B),
        (A, "dev_login", A),
        (A, "cloudflare_service_token", A),
    ],
)
def test_canonical_request_required(
    service: AudioModelService, owner: str, method: str, subject: str
) -> None:
    with pytest.raises(HTTPException) as error:
        service.create(request(owner, method=method, subject=subject), payload())
    assert error.value.status_code == 401
    assert not artifact(service).exists()


def test_foreign_cannot_select_disable_or_delete(service: AudioModelService) -> None:
    public = service.create(request(), payload())
    record_id = str(public["id"])
    with pytest.raises(AudioModelUnavailable):
        service.capture(request(B), choice(record_id))
    with pytest.raises(AudioModelUnavailable):
        service.disable(request(B), record_id)
    with pytest.raises(AudioModelUnavailable):
        service.delete(request(B), record_id)
    assert service.list(request()) == [public]


@pytest.mark.parametrize(
    "field,value",
    [
        ("catalog_id", "deepseek"),
        ("model_id", "gpt-5.6-sol"),
        ("endpoint", "https://api.openai.com?key=UNIT-secret"),
        ("endpoint", "http://api.openai.com"),
        ("endpoint", "https://foreign.invalid"),
        ("api_key", ""),
        ("api_key", "x" * 513),
        ("display_name", "x" * 65),
    ],
)
def test_invalid_create_has_no_store_write(
    service: AudioModelService, field: str, value: str
) -> None:
    body = {**payload(), field: value}
    with pytest.raises(AudioModelUnavailable) as error:
        service.create(request(), body)
    assert str(error.value) == "invalid audio model request"
    assert SECRET not in str(error.value)
    assert not artifact(service).exists()


def test_text_selection_never_audio(service: AudioModelService) -> None:
    public = service.create(request(), payload())
    with pytest.raises(ValueError):
        service.capture(request(), choice(str(public["id"]), "gpt-5.6-sol"))
    assert all(
        model.model_id != "whisper-1" for preset in BYOT_PROVIDER_PRESETS for model in preset.models
    )
    assert get_audio_model("openai", "whisper-1").adapter_kind == "audio_transcription"


@pytest.mark.parametrize("action", ["disable", "delete"])
def test_retirement_revokes_captured_selection(service: AudioModelService, action: str) -> None:
    public = service.create(request(), payload())
    captured = service.capture(request(), choice(str(public["id"])))
    if action == "disable":
        service.disable(request(), captured.record.id)
    else:
        assert service.delete(request(), captured.record.id)
    with pytest.raises(AudioModelUnavailable), service.guard_selection(request(), captured):
        pytest.fail("retired selection admitted")


def test_registration_replacement_and_plain_copy_refused(service: AudioModelService) -> None:
    public = service.create(request(), payload())
    captured = service.capture(request(), choice(str(public["id"])))
    forged = replace(captured, registration=replace(captured.registration))
    with pytest.raises(AudioModelUnavailable), service.guard_selection(request(), forged):
        pytest.fail("copied registration admitted")
    service._registrations[captured.record.id] = replace(captured.registration)
    with pytest.raises(AudioModelUnavailable), service.guard_selection(request(), captured):
        pytest.fail("old registration admitted")


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_user_id", B),
        ("pipeline_kind", "model_provider"),
        ("account_handle", "another-record"),
        ("binding_version", 1),
        ("binding_version", 2),
        ("ciphertext_hex", "00" * 64),
    ],
)
def test_real_ciphertext_metadata_substitution_refused(
    service: AudioModelService, field: str, value: object
) -> None:
    public = service.create(request(), payload())
    captured = service.capture(request(), choice(str(public["id"])))
    path = artifact(service)
    data = json.loads(path.read_text())
    data[captured.record.credential_id][field] = value
    path.write_text(json.dumps(data))
    with (
        pytest.raises((ValueError, store.CredentialIntegrityError)),
        service.guard_selection(request(), captured),
    ):
        pytest.fail("substituted authenticated metadata admitted")


@pytest.mark.parametrize("raw", ["{}", "[", '[{"id":1,"id":2}]', "[]" + " " * 1_048_577])
def test_bounded_corrupt_registry_refuses(service: AudioModelService, raw: str) -> None:
    service.create(request(), payload())
    registry(service).write_text(raw)
    with pytest.raises(AudioModelUnavailable):
        service.list(request())


def test_duplicate_record_and_rebound_generation_refused(service: AudioModelService) -> None:
    public = service.create(request(), payload())
    captured = service.capture(request(), choice(str(public["id"])))
    path = registry(service)
    data = json.loads(path.read_text())
    path.write_text(json.dumps(data * 2))
    with pytest.raises(AudioModelUnavailable):
        service.list(request())
    data[0]["generation"] = "c" * 32
    path.write_text(json.dumps(data))
    with pytest.raises(AudioModelUnavailable), service.guard_selection(request(), captured):
        pytest.fail("rebound generation admitted")


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "mode"])
def test_unsafe_registry_refuses(service: AudioModelService, tmp_path: Path, kind: str) -> None:
    service.create(request(), payload())
    path = registry(service)
    if kind == "symlink":
        target = tmp_path / "foreign"
        path.rename(target)
        path.symlink_to(target)
    elif kind == "hardlink":
        os.link(path, tmp_path / "alias")
    else:
        path.chmod(0o644)
    with pytest.raises((OSError, AudioModelUnavailable)):
        service.list(request())


def test_publication_failure_never_registers(
    service: AudioModelService, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_write(directory: int, records: list[UserAudioModelRecord]) -> None:
        raise OSError("UNIT unavailable storage")

    monkeypatch.setattr(service, "_write", fail_write)
    with pytest.raises(AudioPublicationError) as error:
        service.create(request(), payload())
    assert error.value.cleanup_confirmed is False
    assert service._registrations == {}
    assert service.list(request()) == []
    assert SECRET not in str(error.value)


def test_restart_does_not_mint_registration(service: AudioModelService) -> None:
    public = service.create(request(), payload())
    restarted = AudioModelService(state_root=service._root, prepared_master_key=KEY)
    assert restarted.list(request())[0]["registered"] is False
    with pytest.raises(AudioModelUnavailable):
        restarted.capture(request(), choice(str(public["id"])))


def test_choice_strict_three_fields() -> None:
    with pytest.raises(ValidationError):
        UserModelChoice.model_validate(
            {"authority": "user_model", "provider_id": "id", "model_id": "whisper-1", "key": SECRET}
        )


def test_failed_publication_retires_durable_row_and_owned_credential(
    service: AudioModelService, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = service._write
    calls = 0

    def fail_after_durable_write(directory: int, records: list[UserAudioModelRecord]) -> None:
        nonlocal calls
        calls += 1
        original(directory, records)
        if calls == 1:
            raise OSError("UNIT closing failure")

    monkeypatch.setattr(service, "_write", fail_after_durable_write)
    with pytest.raises(AudioPublicationError) as error:
        service.create(request(), payload())
    assert error.value.cleanup_confirmed is True
    assert json.loads(registry(service).read_text()) == []
    assert store.list_credentials(artifact_path=service._artifact) == []
    assert service._registrations == {}


def test_credential_removed_refuses_captured_selection(service: AudioModelService) -> None:
    public = service.create(request(), payload())
    captured = service.capture(request(), choice(str(public["id"])))
    assert store.delete_credential(captured.record.credential_id, artifact_path=service._artifact)
    with pytest.raises((KeyError, ValueError)), service.guard_selection(request(), captured):
        pytest.fail("deleted credential admitted")
    assert service.list(request()) == []


def test_foreign_valid_encrypted_artifact_cannot_replace_current(
    service: AudioModelService,
) -> None:
    public = service.create(request(), payload())
    captured = service.capture(request(), choice(str(public["id"])))
    replacement = store.store_credential_with_metadata(
        captured.record.id,
        "UNIT-different-key-material",
        owner_user_id=B,
        pipeline_kind="audio_model_provider",
        artifact_path=service._artifact,
        key_bytes=KEY,
    )
    path = artifact(service)
    data = json.loads(path.read_text())
    foreign = data[replacement.cred_id]
    foreign["cred_id"] = captured.record.credential_id
    data[captured.record.credential_id] = foreign
    path.write_text(json.dumps(data))
    with (
        pytest.raises((ValueError, store.CredentialIntegrityError)),
        service.guard_selection(request(), captured),
    ):
        pytest.fail("foreign authenticated ciphertext admitted")


def test_constructed_non_user_choice_refused(service: AudioModelService) -> None:
    public = service.create(request(), payload())
    forged = UserModelChoice.model_construct(
        authority="operator", provider_id=public["id"], model_id="whisper-1"
    )
    with pytest.raises(AudioModelUnavailable):
        service.capture(request(), forged)


def test_registration_construction_failure_has_no_live_row(
    service: AudioModelService, monkeypatch: pytest.MonkeyPatch
) -> None:
    import interfaces.research.api.settings_audio_models as audio

    def refuse_registration(record: UserAudioModelRecord, generation: str) -> object:
        raise ValueError("UNIT registration refusal")

    monkeypatch.setattr(audio, "_Registration", refuse_registration)
    with pytest.raises(AudioPublicationError) as error:
        service.create(request(), payload())
    assert error.value.cleanup_confirmed is True
    assert service._registrations == {}
    assert json.loads(registry(service).read_text()) == []
    assert store.list_credentials(artifact_path=service._artifact) == []


def test_secret_cannot_be_reflected_through_display(service: AudioModelService) -> None:
    with pytest.raises(AudioModelUnavailable) as error:
        service.create(request(), {**payload(), "display_name": SECRET})
    assert SECRET not in str(error.value)
    assert not artifact(service).exists()
    assert not registry(service).exists()


def test_registry_fingerprint_substitution_is_not_current_authority(
    service: AudioModelService,
) -> None:
    public = service.create(request(), payload())
    captured = service.capture(request(), choice(str(public["id"])))
    data = json.loads(registry(service).read_text())
    data[0]["credential_fingerprint"] = "f" * 64
    registry(service).write_text(json.dumps(data))
    with pytest.raises(AudioModelUnavailable), service.guard_selection(request(), captured):
        pytest.fail("substituted registry fingerprint admitted")
    assert service.list(request()) == []


def _stat_observation(info: os.stat_result, field: str, value: int) -> os.stat_result:
    values: list[int | float] = [
        info.st_mode,
        info.st_ino,
        info.st_dev,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_atime,
        info.st_mtime,
        info.st_ctime,
    ]
    extras = {
        "st_atime_ns": info.st_atime_ns,
        "st_mtime_ns": info.st_mtime_ns,
        "st_ctime_ns": info.st_ctime_ns,
    }
    indices = {
        "st_mode": 0,
        "st_ino": 1,
        "st_dev": 2,
        "st_nlink": 3,
        "st_uid": 4,
        "st_gid": 5,
        "st_size": 6,
    }
    if field in indices:
        values[indices[field]] = value
    else:
        extras[field] = value
        values[{"st_atime_ns": 7, "st_mtime_ns": 8, "st_ctime_ns": 9}[field]] = value / 1e9
    return os.stat_result(values, extras)


def test_atime_only_fd_observations_preserve_real_current_selection(
    service: AudioModelService, monkeypatch: pytest.MonkeyPatch
) -> None:
    public = service.create(request(), payload())
    paths = [registry(service), service._root / "settings" / "audio-models.lock"]
    identities = {(p.stat().st_dev, p.stat().st_ino) for p in paths}
    native_fstat = os.fstat
    observations = 0

    def observed_fstat(fd: int) -> os.stat_result:
        nonlocal observations
        info = native_fstat(fd)
        if (info.st_dev, info.st_ino) in identities:
            observations += 1
            return _stat_observation(info, "st_atime_ns", info.st_atime_ns + 1_000_000_000)
        return info

    monkeypatch.setattr(os, "fstat", observed_fstat)
    captured = service.capture(request(), choice(str(public["id"])))
    with service.guard_selection(request(), captured) as current:
        assert current is captured
    assert service.list(request()) == [public]
    assert observations >= 6


@pytest.mark.parametrize("chunk_size", [7, 64])
def test_short_native_registry_chunks_consume_declared_body_and_one_eof(
    service: AudioModelService, monkeypatch: pytest.MonkeyPatch, chunk_size: int
) -> None:
    public = service.create(request(), payload())
    info = registry(service).stat()
    native_read = os.read
    reads: list[tuple[int, int]] = []

    def short_read(fd: int, size: int) -> bytes:
        current = os.fstat(fd)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            return native_read(fd, size)
        result = native_read(fd, min(size, chunk_size))
        reads.append((size, len(result)))
        return result

    monkeypatch.setattr(os, "read", short_read)
    assert service.list(request()) == [public]
    assert sum(length for _, length in reads) == info.st_size
    assert all(0 < length <= size for size, length in reads[:-1])
    assert reads[-1] == (1, 0)
    assert len(reads) > 2


@pytest.mark.parametrize("failure", ["premature_eof", "growth"])
def test_incomplete_or_growing_native_registry_refuses(
    service: AudioModelService, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    service.create(request(), payload())
    path = registry(service)
    info = path.stat()
    native_read = os.read
    calls = 0
    consumed = 0

    def changing_read(fd: int, size: int) -> bytes:
        nonlocal calls, consumed
        current = os.fstat(fd)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            return native_read(fd, size)
        calls += 1
        if failure == "premature_eof" and calls == 2:
            return b""
        if failure == "growth" and consumed == info.st_size:
            with path.open("ab") as stream:
                stream.write(b" ")
        result = native_read(fd, min(size, 7))
        consumed += len(result)
        return result

    monkeypatch.setattr(os, "read", changing_read)
    with pytest.raises(AudioModelUnavailable):
        service.list(request())
    if failure == "premature_eof":
        assert calls == 2
        assert consumed == 7
        assert path.stat().st_size == info.st_size
    else:
        assert consumed == info.st_size + 1
        assert path.stat().st_size == info.st_size + 1


@pytest.mark.parametrize(
    "field",
    [
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_gid",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    ],
)
def test_each_content_security_fd_identity_change_refuses(
    service: AudioModelService, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    service.create(request(), payload())
    info = registry(service).stat()
    native_fstat = os.fstat
    calls = 0

    def changed_fstat(fd: int) -> os.stat_result:
        nonlocal calls
        current = native_fstat(fd)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            return current
        calls += 1
        if calls == 2:
            value = {
                "st_dev": current.st_dev,
                "st_ino": current.st_ino,
                "st_mode": current.st_mode,
                "st_uid": current.st_uid,
                "st_gid": current.st_gid,
                "st_nlink": current.st_nlink,
                "st_size": current.st_size,
                "st_mtime_ns": current.st_mtime_ns,
                "st_ctime_ns": current.st_ctime_ns,
            }[field]
            return _stat_observation(current, field, value + 1)
        return current

    monkeypatch.setattr(os, "fstat", changed_fstat)
    with pytest.raises(AudioModelUnavailable):
        service.list(request())
    assert calls == 2


def test_registry_path_replacement_during_native_read_refuses(
    service: AudioModelService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.create(request(), payload())
    path = registry(service)
    info = path.stat()
    native_read = os.read
    replaced = False
    body = path.read_bytes()

    def replacing_read(fd: int, size: int) -> bytes:
        nonlocal replaced
        current = os.fstat(fd)
        result = native_read(fd, size)
        if (current.st_dev, current.st_ino) == (info.st_dev, info.st_ino) and not replaced:
            replaced = True
            path.rename(path.with_name("retired-registry.json"))
            path.write_bytes(body)
            path.chmod(0o600)
        return result

    monkeypatch.setattr(os, "read", replacing_read)
    with pytest.raises(AudioModelUnavailable):
        service.list(request())
    assert replaced
    assert path.stat().st_ino != info.st_ino
    assert path.read_bytes() == body
