"""Real encrypted account credentials stay guarded without authorizing audio dispatch."""

from __future__ import annotations

import json
import secrets
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from interfaces.research.api import settings_audio_models as audio
from interfaces.research.api.settings_audio_models import (
    AudioModelService,
    AudioModelUnavailable,
    AudioSelection,
)
from interfaces.research.api.settings_models_admin import UserModelChoice
from runtime.byok import store
from runtime.byok.secret_str import SecretStr

A = "acct_" + "a" * 32
B = "acct_" + "b" * 32
KEY = bytes(range(32))


def request(
    owner: str = A, *, method: str = "antiek_session_cookie", subject: str | None = None
) -> Request:
    result = Request({"type": "http", "method": "POST", "path": "/unit", "headers": []})
    result.state.user_id = owner
    result.state.account_subject = owner if subject is None else subject
    result.state.auth_method = method
    return result


@dataclass(frozen=True)
class Case:
    service: AudioModelService
    selection: AudioSelection
    secret: SecretStr

    @property
    def artifact(self) -> Path:
        return Path(self.service._artifact)

    @property
    def registry(self) -> Path:
        return self.service._root / "settings" / "user_audio_models.json"


@pytest.fixture(autouse=True)
def deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("private credential controls cannot open sockets")

    monkeypatch.setattr(socket, "socket", refuse)


@pytest.fixture
def case(tmp_path: Path) -> Case:
    assert Path(audio.__file__).resolve() == (
        Path(__file__).resolve().parents[1] / "interfaces/research/api/settings_audio_models.py"
    )
    private = tmp_path / "private-audio"
    private.mkdir(mode=0o700)
    secret = SecretStr(secrets.token_hex(32))
    service = AudioModelService(state_root=private, prepared_master_key=KEY)
    created = service.create(
        request(),
        {
            "catalog_id": "openai",
            "model_id": "whisper-1",
            "endpoint": "https://api.openai.com",
            "display_name": "Private UNIT microphone",
            "api_key": secret.reveal(),
        },
    )
    record_id = created["id"]
    assert isinstance(record_id, str)
    selected = service.capture(
        request(),
        UserModelChoice(authority="user_model", provider_id=record_id, model_id="whisper-1"),
    )
    return Case(service, selected, secret)


def mutate_artifact(case: Case, field: str, value: object) -> None:
    parsed: object = json.loads(case.artifact.read_text())
    assert isinstance(parsed, dict)
    row: object = parsed[case.selection.record.credential_id]
    assert isinstance(row, dict)
    row[field] = value
    case.artifact.write_text(json.dumps(parsed))


def test_real_current_credential_and_unbound_selection(case: Case) -> None:
    with case.service.guard_selected_credential(request(), case.selection) as guarded:
        assert isinstance(guarded, store.GuardedCredential)
        assert guarded.secret == case.secret
        assert guarded.metadata.cred_id == case.selection.record.credential_id
        assert guarded.metadata.owner_user_id == A
        assert guarded.metadata.binding_version == 3
        assert guarded.metadata.pipeline_kind == "audio_model_provider"
        assert guarded.metadata.account_handle == case.selection.record.id
        assert guarded.metadata.artifact_fingerprint == case.selection.record.credential_fingerprint
        assert case.selection.dispatch_authority == "unbound"


@pytest.mark.parametrize(
    "owner,method,subject",
    [
        ("__operator__", "antiek_session_cookie", "__operator__"),
        ("machine", "antiek_session_cookie", "machine"),
        (A, "bearer_token", A),
        (A, "dev_login", A),
        (A, "cloudflare_service_token", A),
        (A, "antiek_session_cookie", B),
    ],
)
def test_noncanonical_request_denied_before_credential_access(
    case: Case, monkeypatch: pytest.MonkeyPatch, owner: str, method: str, subject: str
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("credential access preceded account admission")

    monkeypatch.setattr(store, "guard_current_credential", forbidden)
    with (
        pytest.raises(HTTPException) as failure,
        case.service.guard_selected_credential(
            request(owner, method=method, subject=subject), case.selection
        ),
    ):
        pytest.fail("noncanonical request admitted")
    assert failure.value.status_code == 401


def test_foreign_account_denied_before_store_access(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("foreign account reached credentials")

    monkeypatch.setattr(store, "guard_current_credential", forbidden)
    with (
        pytest.raises(AudioModelUnavailable),
        case.service.guard_selected_credential(request(B), case.selection),
    ):
        pytest.fail("foreign account admitted")


@pytest.mark.parametrize("action", ["disable", "delete", "credential_delete"])
def test_real_retirement_before_fresh_guard_refuses(case: Case, action: str) -> None:
    if action == "disable":
        case.service.disable(request(), case.selection.record.id)
    elif action == "delete":
        assert case.service.delete(request(), case.selection.record.id)
    else:
        assert store.delete_credential(
            case.selection.record.credential_id, artifact_path=case.service._artifact
        )
    with (
        pytest.raises((AudioModelUnavailable, KeyError, ValueError)),
        case.service.guard_selected_credential(request(), case.selection),
    ):
        pytest.fail("retired credential admitted")


@pytest.mark.parametrize(
    "change", ["copied_capture", "replaced_registration", "rebound_generation"]
)
def test_registration_identity_and_generation_are_still_required(case: Case, change: str) -> None:
    selection = case.selection
    if change == "copied_capture":
        selection = replace(selection, registration=replace(selection.registration))
    elif change == "replaced_registration":
        case.service._registrations[selection.record.id] = replace(selection.registration)
    else:
        rows: object = json.loads(case.registry.read_text())
        assert isinstance(rows, list) and isinstance(rows[0], dict)
        rows[0]["generation"] = "e" * 32
        case.registry.write_text(json.dumps(rows))
    with (
        pytest.raises(AudioModelUnavailable),
        case.service.guard_selected_credential(request(), selection),
    ):
        pytest.fail("stale registration admitted")


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_user_id", B),
        ("credential_id", "cred-x-foreign"),
        ("credential_fingerprint", "f" * 64),
        ("generation", "e" * 32),
        ("enabled", False),
    ],
)
def test_captured_record_substitution_refused(case: Case, field: str, value: object) -> None:
    record = case.selection.record.model_copy(update={field: value})
    forged = replace(case.selection, record=record)
    with (
        pytest.raises(AudioModelUnavailable),
        case.service.guard_selected_credential(request(), forged),
    ):
        pytest.fail("substituted capture admitted")


def test_descriptor_and_dispatch_grant_substitution_refused(case: Case) -> None:
    descriptor = replace(case.selection.descriptor)
    object.__setattr__(descriptor, "endpoint", "https://foreign.invalid")
    forged = replace(case.selection, descriptor=descriptor)
    with (
        pytest.raises(AudioModelUnavailable),
        case.service.guard_selected_credential(request(), forged),
    ):
        pytest.fail("foreign descriptor admitted")
    granted = replace(case.selection)
    object.__setattr__(granted, "dispatch_authority", "granted")
    with (
        pytest.raises(AudioModelUnavailable),
        case.service.guard_selected_credential(request(), granted),
    ):
        pytest.fail("invented dispatch permission admitted")


@pytest.mark.parametrize(
    "field,value",
    [
        ("cred_id", "cred-x-foreign"),
        ("owner_user_id", B),
        ("pipeline_kind", "model_provider"),
        ("account_handle", "another-record"),
        ("binding_version", 1),
        ("binding_version", 2),
        ("binding_version", True),
        ("ciphertext_hex", "00" * 64),
    ],
)
def test_real_ciphertext_or_authenticated_binding_substitution_refuses(
    case: Case, field: str, value: object
) -> None:
    mutate_artifact(case, field, value)
    with (
        pytest.raises((ValueError, KeyError, AudioModelUnavailable)),
        case.service.guard_selected_credential(request(), case.selection),
    ):
        pytest.fail("changed ciphertext authority admitted")


def test_registry_fingerprint_substitution_refuses(case: Case) -> None:
    rows: object = json.loads(case.registry.read_text())
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    rows[0]["credential_fingerprint"] = "f" * 64
    case.registry.write_text(json.dumps(rows))
    with (
        pytest.raises(AudioModelUnavailable),
        case.service.guard_selected_credential(request(), case.selection),
    ):
        pytest.fail("changed registry fingerprint admitted")


def test_wrong_prepared_master_key_refuses(case: Case) -> None:
    case.service._key = bytes(reversed(range(32)))
    with (
        pytest.raises(store.CredentialIntegrityError),
        case.service.guard_selected_credential(request(), case.selection),
    ):
        pytest.fail("wrong master key admitted")


def test_restart_cannot_manufacture_current_registration(case: Case) -> None:
    restarted = AudioModelService(state_root=case.service._root, prepared_master_key=KEY)
    with (
        pytest.raises(AudioModelUnavailable),
        restarted.guard_selected_credential(request(), case.selection),
    ):
        pytest.fail("durable row manufactured registration")


def test_guard_never_uses_ambient_or_public_key_accessor(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("ambient/public credential accessor used")

    for name in (
        "_default_artifact_path",
        "_default_key_file",
        "_load_master_key",
        "load_credential",
    ):
        monkeypatch.setattr(store, name, forbidden)
    with case.service.guard_selected_credential(request(), case.selection) as guarded:
        assert guarded.secret == case.secret


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_user_id", B),
        ("pipeline_kind", "model_provider"),
        ("account_handle", "another-record"),
        ("cred_id", "cred-x-foreign"),
        ("binding_version", 2),
        ("artifact_fingerprint", "f" * 64),
    ],
)
def test_second_real_credential_guard_rechecks_returned_metadata(
    case: Case, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    original = store.guard_current_credential
    calls = 0

    @contextmanager
    def substituted(
        cred_id: str, *, prepared_master_key: bytes, artifact_path: str | None = None
    ) -> Iterator[store.GuardedCredential]:
        nonlocal calls
        calls += 1
        with original(
            cred_id, prepared_master_key=prepared_master_key, artifact_path=artifact_path
        ) as guarded:
            if calls == 2:
                if field == "binding_version":
                    assert type(value) is int
                    metadata = replace(guarded.metadata, binding_version=value)
                else:
                    assert isinstance(value, str)
                    if field == "owner_user_id":
                        metadata = replace(guarded.metadata, owner_user_id=value)
                    elif field == "pipeline_kind":
                        metadata = replace(guarded.metadata, pipeline_kind=value)
                    elif field == "account_handle":
                        metadata = replace(guarded.metadata, account_handle=value)
                    elif field == "cred_id":
                        metadata = replace(guarded.metadata, cred_id=value)
                    elif field == "artifact_fingerprint":
                        metadata = replace(guarded.metadata, artifact_fingerprint=value)
                    else:
                        raise AssertionError("unknown allocated metadata fault field")
                yield replace(guarded, metadata=metadata)
            else:
                yield guarded

    monkeypatch.setattr(store, "guard_current_credential", substituted)
    with (
        pytest.raises(AudioModelUnavailable),
        case.service.guard_selected_credential(request(), case.selection),
    ):
        pytest.fail("second credential guard returned unqualified metadata")
    assert calls == 2


def test_consumer_exception_releases_guards_for_later_legitimate_claim(case: Case) -> None:
    with (
        pytest.raises(RuntimeError, match="UNIT consumer stopped"),
        case.service.guard_selected_credential(request(), case.selection) as guarded,
    ):
        assert guarded.secret == case.secret
        raise RuntimeError("UNIT consumer stopped")
    with case.service.guard_selected_credential(request(), case.selection) as current:
        assert current.secret == case.secret


def test_real_writer_waits_for_guard_exit_then_revocation_is_effective(case: Case) -> None:
    started = threading.Event()
    finished = threading.Event()
    results: list[bool] = []
    failures: list[BaseException] = []

    def retire() -> None:
        started.set()
        try:
            results.append(
                store.delete_credential(
                    case.selection.record.credential_id, artifact_path=case.service._artifact
                )
            )
        except BaseException as error:
            failures.append(error)
        finally:
            finished.set()

    writer = threading.Thread(target=retire, daemon=True)
    try:
        with case.service.guard_selected_credential(request(), case.selection) as guarded:
            assert guarded.secret == case.secret
            writer.start()
            assert started.wait(1)
            assert not finished.wait(0.1)
            assert guarded.metadata.cred_id == case.selection.record.credential_id
    finally:
        if writer.ident is not None:
            writer.join(2)
    assert not writer.is_alive()
    assert finished.is_set() and results == [True]
    assert not failures
    with (
        pytest.raises(KeyError),
        case.service.guard_selected_credential(request(), case.selection),
    ):
        pytest.fail("retired credential admitted after writer release")
