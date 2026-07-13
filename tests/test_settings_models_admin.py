"""Add-model vertical — user-added BYOK providers in Settings.

All offline + deterministic: byok artifact/key-file + user-model registry
redirected to tmp via env, zero real network (the credential-reflection test
uses ``httpx.MockTransport``), providers registered via the REAL dispatch seam
and reset around each test. The key-absent invariant mirrors ``test_byok_store.py``'s
byte-level absence assertion: responses, durable artifacts, and captured
logs/stdio must never contain the plaintext key.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_budget import register_settings_budget_routes
from substrate.dispatch.base import ProviderError
from substrate.dispatch.providers.openai_compat import OpenAICompatProvider
from substrate.dispatch.router import (
    get_provider,
    register_provider,
    reset_provider_registry,
)

_SECRET = "sk-AAAA-super-secret-user-model-key-1234567890"

_ADD_BODY = {
    "provider_kind": "openai_compat",
    "model_id": "deepseek-chat",
    "display_name": "My DeepSeek",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": _SECRET,
}


def _fresh_app() -> FastAPI:
    """Build an app through the REAL settings mount seam (the same
    ``register_settings_budget_routes`` create_app calls) without pulling
    the whole app.py surface into this suite."""
    app = FastAPI()
    register_settings_budget_routes(app)
    return app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv(
        "ANTIEK_USER_MODELS_PATH", str(tmp_path / "settings" / "user_models.json")
    )
    monkeypatch.setenv(
        "ANTIEK_BYOK_ARTIFACT", str(tmp_path / "byok" / "credentials.enc")
    )
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "byok" / "master.key"))
    reset_provider_registry()
    return tmp_path


@pytest.fixture
def client(env: Path) -> Iterator[TestClient]:
    with TestClient(_fresh_app()) as c:
        yield c
    reset_provider_registry()


def test_add_appears_with_key_present_and_registers(client: TestClient) -> None:
    r = client.post("/settings/models/user", json=_ADD_BODY)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "user-my-deepseek"
    assert body["key_present"] is True
    assert body["registered"] is True
    assert body["enabled"] is True
    assert "api_key" not in body

    inv = client.get("/settings/models/user")
    assert inv.status_code == 200
    rows = inv.json()["models"]
    assert [row["id"] for row in rows] == ["user-my-deepseek"]
    assert rows[0]["key_present"] is True

    # Registration proof through the SAME seam register_default_providers
    # populates: the existing inventory endpoint reads
    # app.state.registered_providers. The generic inventory must NOT call the
    # provider route-ready until an explicit dispatch tier binds it.
    models = client.get("/settings/models")
    assert models.status_code == 200
    row = next(
        m for m in models.json()["models"] if m["provider_id"] == "user-my-deepseek"
    )
    assert row["registered"] is True
    assert row["ready"] is False
    assert row["tier_bindings"] == []
    assert row["notes"] == "registered, but not bound to an active dispatch tier"

    # ... and the dispatch registry itself resolves the provider, with the
    # key decrypting from the byok store at call time (test-only private
    # access — this is the one place the plaintext round-trip is asserted,
    # mirroring test_byok_store's reveal() assertions).
    provider = get_provider("user-my-deepseek")
    assert provider._resolve_api_key() == _SECRET  # noqa: SLF001
    assert provider.base_url == "https://api.deepseek.com/v1"


def test_key_absent_from_responses_artifacts_and_logs(
    client: TestClient,
    env: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with caplog.at_level(logging.DEBUG):
        responses = [
            client.post("/settings/models/user", json=_ADD_BODY),
            client.get("/settings/models/user"),
            client.get("/settings/models"),
            client.delete("/settings/models/user/user-my-deepseek"),
        ]
    for r in responses:
        assert _SECRET not in r.text

    registry_bytes = (env / "settings" / "user_models.json").read_bytes()
    assert _SECRET.encode("utf-8") not in registry_bytes

    artifact_bytes = (env / "byok" / "credentials.enc").read_bytes()
    assert _SECRET.encode("utf-8") not in artifact_bytes
    assert b"ciphertext_hex" in artifact_bytes  # encrypted, not omitted

    assert _SECRET not in caplog.text
    captured = capsys.readouterr()
    assert _SECRET not in captured.out
    assert _SECRET not in captured.err


@pytest.mark.parametrize("provider_kind", ["openai_compat", "anthropic"])
def test_untrusted_endpoint_cannot_reflect_key_into_provider_error(
    client: TestClient, provider_kind: str
) -> None:
    body = {
        **_ADD_BODY,
        "provider_kind": provider_kind,
        "display_name": f"Hostile {provider_kind}",
    }
    if provider_kind == "anthropic":
        body["base_url"] = "https://attacker.invalid"
    created = client.post("/settings/models/user", json=body)
    assert created.status_code == 201

    provider = get_provider(created.json()["id"])

    def reflect_credential(request: httpx.Request) -> httpx.Response:
        reflected = request.headers.get("authorization") or request.headers.get("x-api-key")
        return httpx.Response(
            401,
            text=f"reflected credential: {reflected}",
            request=request,
        )

    provider._client = httpx.Client(transport=httpx.MockTransport(reflect_credential))  # noqa: SLF001
    provider._owns_client = True  # noqa: SLF001
    with pytest.raises(ProviderError) as raised:
        provider.call(model="test-model", prompt="test", max_tokens=1, temperature=0)

    message = str(raised.value)
    assert _SECRET not in message
    assert "reflected credential" not in message
    assert "HTTP 401" in message


@pytest.mark.parametrize("provider_kind", ["openai_compat", "anthropic"])
@pytest.mark.parametrize("error_type", [httpx.RemoteProtocolError, httpx.ReadTimeout])
def test_untrusted_transport_exception_cannot_reflect_key(
    client: TestClient,
    provider_kind: str,
    error_type: type[httpx.RequestError],
) -> None:
    body = {
        **_ADD_BODY,
        "provider_kind": provider_kind,
        "display_name": f"Transport reflector {provider_kind}",
    }
    if provider_kind == "anthropic":
        body["base_url"] = "https://attacker.invalid"
    created = client.post("/settings/models/user", json=body)
    assert created.status_code == 201
    provider = get_provider(created.json()["id"])

    def reflect_credential(request: httpx.Request) -> httpx.Response:
        raise error_type(f"malformed transport reflected {_SECRET}", request=request)

    provider._client = httpx.Client(  # noqa: SLF001
        transport=httpx.MockTransport(reflect_credential)
    )
    provider._owns_client = True  # noqa: SLF001
    with pytest.raises(ProviderError) as raised:
        provider.call(model="test-model", prompt="test", max_tokens=1, temperature=0)

    message = str(raised.value)
    assert _SECRET not in message
    assert "malformed transport" not in message
    assert raised.value.retryable is True


@pytest.mark.parametrize("provider_kind", ["openai_compat", "anthropic"])
def test_untrusted_endpoint_cannot_reflect_key_in_success_response(
    client: TestClient, provider_kind: str
) -> None:
    body = {
        **_ADD_BODY,
        "provider_kind": provider_kind,
        "display_name": f"Success reflector {provider_kind}",
    }
    if provider_kind == "anthropic":
        body["base_url"] = "https://attacker.invalid"
    created = client.post("/settings/models/user", json=body)
    assert created.status_code == 201
    provider = get_provider(created.json()["id"])

    def reflect_credential(request: httpx.Request) -> httpx.Response:
        reflected = request.headers.get("authorization") or request.headers.get("x-api-key")
        if provider_kind == "anthropic":
            payload = {
                "content": [{"type": "text", "text": f"answer {reflected}"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        else:
            payload = {
                "choices": [{
                    "message": {"content": f"answer {reflected}"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        # Preserve an encoded credential in the raw wire response.  A raw
        # substring scan must not be the security boundary: JSON decoding
        # reconstructs the plaintext before provider content is returned.
        serialized = json.dumps(payload).replace("AAAA", r"\u0041AAA", 1)
        assert _SECRET not in serialized
        return httpx.Response(200, text=serialized, request=request)

    provider._client = httpx.Client(transport=httpx.MockTransport(reflect_credential))  # noqa: SLF001
    provider._owns_client = True  # noqa: SLF001
    with pytest.raises(ProviderError) as raised:
        provider.call(model="test-model", prompt="test", max_tokens=1, temperature=0)

    message = str(raised.value)
    assert _SECRET not in message
    assert "credential material" in message


def test_untrusted_anthropic_endpoint_cannot_reassemble_split_key(
    client: TestClient,
) -> None:
    body = {
        **_ADD_BODY,
        "provider_kind": "anthropic",
        "display_name": "Split reflector",
        "base_url": "https://attacker.invalid",
    }
    created = client.post("/settings/models/user", json=body)
    assert created.status_code == 201
    provider = get_provider(created.json()["id"])

    def reflect_split_credential(request: httpx.Request) -> httpx.Response:
        reflected = request.headers["x-api-key"]
        midpoint = len(reflected) // 2
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": reflected[:midpoint]},
                    {"type": "text", "text": reflected[midpoint:]},
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
            request=request,
        )

    provider._client = httpx.Client(  # noqa: SLF001
        transport=httpx.MockTransport(reflect_split_credential)
    )
    provider._owns_client = True  # noqa: SLF001
    with pytest.raises(ProviderError) as raised:
        provider.call(model="test-model", prompt="test", max_tokens=1, temperature=0)

    message = str(raised.value)
    assert _SECRET not in message
    assert "credential material" in message


def test_remove_takes_effect_immediately(client: TestClient) -> None:
    assert client.post("/settings/models/user", json=_ADD_BODY).status_code == 201
    provider = get_provider("user-my-deepseek")

    r = client.delete("/settings/models/user/user-my-deepseek")
    assert r.status_code == 200
    assert r.json()["removed"] == "user-my-deepseek"

    assert client.get("/settings/models/user").json()["count"] == 0
    ids = {m["provider_id"] for m in client.get("/settings/models").json()["models"]}
    assert "user-my-deepseek" not in ids

    # The in-process dispatch-registry entry lingers (no public unregister)
    # but is INERT: key resolution re-checks the durable registry.
    with pytest.raises(ProviderError):
        provider._resolve_api_key()  # noqa: SLF001

    # Re-adding the same display name mints a new credential reference. A
    # retained reference to the deleted provider must stay inert rather than
    # decrypting its orphaned old ciphertext merely because the id exists again.
    replacement = {**_ADD_BODY, "api_key": "sk-replacement-secret-123456789"}
    assert client.post("/settings/models/user", json=replacement).status_code == 201
    with pytest.raises(ProviderError):
        provider._resolve_api_key()  # noqa: SLF001

    assert client.delete("/settings/models/user/user-my-deepseek").status_code == 200


@pytest.mark.parametrize(
    "mutation",
    [
        {"api_key": None},  # missing key
        {"api_key": ""},  # empty key
        {"api_key": "short"},  # truncated paste
        {"api_key": " padded-key-with-space "},  # whitespace
        {"provider_kind": "sorcery"},  # unknown kind
        {"model_id": None},  # missing model id
        {"model_id": "has whitespace"},
        {"display_name": None},
        {"display_name": "   "},
        {"base_url": None},  # required for openai_compat
        {"base_url": "ftp://api.example.com"},
    ],
)
def test_malformed_input_rejected_value_free(
    client: TestClient, mutation: dict[str, str | None]
) -> None:
    body = {**_ADD_BODY, **mutation}
    payload = {k: v for k, v in body.items() if v is not None}
    r = client.post("/settings/models/user", json=payload)
    assert r.status_code == 422
    # The load-bearing half: no rejection may echo the key back. This is
    # exactly the FastAPI whole-body-echo hazard the manual parser closes.
    assert _SECRET not in r.text
    assert client.get("/settings/models/user").json()["count"] == 0


def test_duplicate_display_name_conflicts(client: TestClient) -> None:
    assert client.post("/settings/models/user", json=_ADD_BODY).status_code == 201
    r = client.post("/settings/models/user", json=_ADD_BODY)
    assert r.status_code == 409
    assert _SECRET not in r.text


def test_anthropic_kind_without_base_url(client: TestClient) -> None:
    body = {
        "provider_kind": "anthropic",
        "model_id": "claude-opus-4-8",
        "display_name": "My Claude",
        "api_key": _SECRET,
    }
    r = client.post("/settings/models/user", json=body)
    assert r.status_code == 201
    provider = get_provider("user-my-claude")
    assert provider.name == "user-my-claude"
    assert provider._resolve_api_key() == _SECRET  # noqa: SLF001


def test_boot_time_reload_of_user_providers(env: Path) -> None:
    with TestClient(_fresh_app()) as first:
        assert first.post("/settings/models/user", json=_ADD_BODY).status_code == 201

    # Fresh process simulation: empty dispatch registry, new app, no POST.
    reset_provider_registry()
    with TestClient(_fresh_app()) as reborn:
        models = reborn.get("/settings/models").json()["models"]
        row = next(m for m in models if m["provider_id"] == "user-my-deepseek")
        assert row["ready"] is False
        assert get_provider("user-my-deepseek")._resolve_api_key() == _SECRET  # noqa: SLF001
    reset_provider_registry()


def test_boot_reload_cannot_shadow_default_provider_from_corrupt_registry(
    env: Path,
) -> None:
    with TestClient(_fresh_app()) as seeder:
        assert seeder.post("/settings/models/user", json=_ADD_BODY).status_code == 201

    registry_path = env / "settings" / "user_models.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    shadow = registry.pop("user-my-deepseek")
    shadow["id"] = "openrouter"
    registry["openrouter"] = shadow
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    reset_provider_registry()
    sentinel = OpenAICompatProvider(
        name="openrouter",
        base_url="https://trusted.example/v1",
        api_key="test-only-sentinel-key",
    )
    register_provider(sentinel)
    app = _fresh_app()
    app.state.registered_providers = {"openrouter"}

    with TestClient(app) as reborn:
        assert get_provider("openrouter") is sentinel
        assert reborn.get("/settings/models/user").json()["count"] == 0
        assert app.state.registered_providers == {"openrouter"}
    reset_provider_registry()


def test_boot_reload_rejects_credential_owned_by_another_pipeline(
    env: Path,
) -> None:
    with TestClient(_fresh_app()) as first:
        assert first.post("/settings/models/user", json=_ADD_BODY).status_code == 201
    registry_path = env / "settings" / "user_models.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    # Keep a real decryptable credential id but corrupt its non-secret owner
    # metadata to simulate a restored sidecar pointing at another BYOK lane.
    artifact_path = env / "byok" / "credentials.enc"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    cred_ref = registry["user-my-deepseek"]["cred_ref"]
    artifact[cred_ref]["pipeline_kind"] = "x_ingest"
    artifact[cred_ref]["account_handle"] = "unrelated-account"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    reset_provider_registry()
    with TestClient(_fresh_app()) as reborn:
        rows = reborn.get("/settings/models/user").json()["models"]
        assert rows[0]["key_present"] is False
        assert rows[0]["registered"] is False
        assert reborn.app.state.registered_providers == set()
    reset_provider_registry()


def test_credential_bearing_base_url_rejected_value_free(client: TestClient) -> None:
    # FINDING-1 regression: a credential smuggled into base_url (userinfo /
    # query / fragment) would land PLAINTEXT in the registry and echo in
    # every response carrying base_url. Must 422 and NEVER echo the URL.
    marker = "url-embedded-secret-marker-xyz"
    for url in (
        f"https://user:{marker}@api.example.com/v1",
        f"https://api.example.com/v1?key={marker}",
        f"https://api.example.com/v1#{marker}",
    ):
        r = client.post("/settings/models/user", json={**_ADD_BODY, "base_url": url})
        assert r.status_code == 422
        assert marker not in r.text
        assert _SECRET not in r.text
    assert client.get("/settings/models/user").json()["count"] == 0


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://[::1/v1",  # unclosed IPv6 bracket → urlsplit ValueError
        "https://host:notaport/v1",  # non-numeric port → .port ValueError
        "https://:443/v1",  # empty hostname (truthy netloc, no host)
    ],
)
def test_malformed_base_url_is_clean_422_not_500(
    client: TestClient, bad_url: str
) -> None:
    # FINDING-1 round-2 regression: a malformed authority must be a clean,
    # value-free 422 — never an uncaught ValueError surfacing as HTTP 500.
    r = client.post("/settings/models/user", json={**_ADD_BODY, "base_url": bad_url})
    assert r.status_code == 422
    assert bad_url not in r.text
    assert _SECRET not in r.text
    assert client.get("/settings/models/user").json()["count"] == 0


def test_well_formed_ipv6_base_url_accepted(client: TestClient) -> None:
    # FINDING-1 round-2 guard: the try/except must not over-reject a
    # WELL-FORMED bracketed IPv6 endpoint — a legitimate local provider.
    body = {**_ADD_BODY, "display_name": "Local V6", "base_url": "https://[::1]:8000/v1"}
    r = client.post("/settings/models/user", json=body)
    assert r.status_code == 201
    assert r.json()["base_url"] == "https://[::1]:8000/v1"
    assert get_provider("user-local-v6").base_url == "https://[::1]:8000/v1"


def test_over_length_inputs_rejected_value_free(client: TestClient, env: Path) -> None:
    # FINDING-2 regression: unbounded lengths let a 2MiB "key" balloon the
    # ciphertext artifact to 4MiB. Caps: api_key<=512, base_url<=2048;
    # rejections value-free, and nothing reaches the byok artifact.
    long_key = "k" * 600
    r = client.post("/settings/models/user", json={**_ADD_BODY, "api_key": long_key})
    assert r.status_code == 422
    assert long_key not in r.text

    long_url = "https://api.example.com/" + "a" * 2100
    r2 = client.post("/settings/models/user", json={**_ADD_BODY, "base_url": long_url})
    assert r2.status_code == 422
    assert long_url not in r2.text
    assert _SECRET not in r2.text

    assert client.get("/settings/models/user").json()["count"] == 0
    # Validation precedes encryption: no credential artifact was created.
    assert not (env / "byok" / "credentials.enc").exists()


def test_live_registry_corruption_surfaces_stale_registered(
    client: TestClient, env: Path
) -> None:
    # FINDING-3 regression (live half): registry corrupted while the process
    # is up -> inventory empties (lenient read must not crash) and the
    # still-registered seam name is SURFACED as stale, not hidden.
    assert client.post("/settings/models/user", json=_ADD_BODY).status_code == 201
    (env / "settings" / "user_models.json").write_text("{corrupt", encoding="utf-8")
    inv = client.get("/settings/models/user").json()
    assert inv["count"] == 0
    assert inv["stale_registered"] == ["user-my-deepseek"]


def test_boot_reconcile_discards_stale_user_names(env: Path) -> None:
    # FINDING-3 regression (boot half): a user-* seam name with no enabled
    # registry record is discarded at startup reconcile, so
    # GET /settings/models cannot claim ready:true for a provider whose key
    # resolution refuses. Non-user names are never touched (prefix guard).
    app = _fresh_app()
    app.state.registered_providers = {"user-ghost", "zai"}
    with TestClient(app) as c:
        assert app.state.registered_providers == {"zai"}
        ids = {m["provider_id"] for m in c.get("/settings/models").json()["models"]}
        assert "user-ghost" not in ids
    reset_provider_registry()


def test_boot_reload_lands_after_create_app_state_assignment(env: Path) -> None:
    # FINDING-5: pin the ordering claim against the REAL create_app.
    # create_app assigns app.state.registered_providers AFTER mounting the
    # settings routes; the startup reload must land ON that assignment (an
    # assignment-after-reload ordering would clobber the user name).
    with TestClient(_fresh_app()) as seeder:
        assert seeder.post("/settings/models/user", json=_ADD_BODY).status_code == 201
    reset_provider_registry()

    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False)
    # create_app has already run its assignment (empty set: no provider
    # keys); the reload is a lifespan-startup handler and has NOT run yet.
    assert app.state.registered_providers == set()
    with TestClient(app) as c:
        # Startup fired: reload landed after the assignment, not clobbered.
        assert app.state.registered_providers == {"user-my-deepseek"}
        row = next(
            m
            for m in c.get("/settings/models").json()["models"]
            if m["provider_id"] == "user-my-deepseek"
        )
        assert row["ready"] is False
    reset_provider_registry()


def test_disabled_record_is_not_registered_at_boot(env: Path) -> None:
    with TestClient(_fresh_app()) as first:
        assert first.post("/settings/models/user", json=_ADD_BODY).status_code == 201

    # The enabled field is honored read-side: flip it off in the durable
    # registry (operator escape hatch) and the provider must not register.
    registry_path = env / "settings" / "user_models.json"
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    data["user-my-deepseek"]["enabled"] = False
    registry_path.write_text(json.dumps(data), encoding="utf-8")

    reset_provider_registry()
    with TestClient(_fresh_app()) as reborn:
        ids = {
            m["provider_id"] for m in reborn.get("/settings/models").json()["models"]
        }
        assert "user-my-deepseek" not in ids
        rows = reborn.get("/settings/models/user").json()["models"]
        assert rows[0]["enabled"] is False
        assert rows[0]["registered"] is False
        with pytest.raises(KeyError):
            get_provider("user-my-deepseek")
    reset_provider_registry()
