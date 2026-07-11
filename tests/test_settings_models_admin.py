"""Add-model vertical — user-added BYOK providers in Settings.

All offline + deterministic: byok artifact/key-file + user-model registry
redirected to tmp via env, zero network (no provider ``call()`` is ever
made), providers registered via the REAL dispatch seam and reset around
each test. The key-absent invariant mirrors ``test_byok_store.py``'s
byte-level absence assertion: responses, durable artifacts, and captured
logs/stdio must never contain the plaintext key.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_budget import register_settings_budget_routes
from substrate.dispatch.base import ProviderError
from substrate.dispatch.router import get_provider, reset_provider_registry

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
    # app.state.registered_providers and must show the user provider ready.
    models = client.get("/settings/models")
    assert models.status_code == 200
    row = next(
        m for m in models.json()["models"] if m["provider_id"] == "user-my-deepseek"
    )
    assert row["ready"] is True

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

    assert client.delete("/settings/models/user/user-my-deepseek").status_code == 404


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
        assert row["ready"] is True
        assert get_provider("user-my-deepseek")._resolve_api_key() == _SECRET  # noqa: SLF001
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
        assert row["ready"] is True
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
