"""One key, many variants — SPR-03 Task 2.

One registration carrying ``model_ids`` [deepseek-v4-pro, deepseek-flash]
must produce exactly ONE ``UserModelRecord`` and exactly ONE stored
credential, with TWO selectable variants that both resolve under the same
record id (so usage and balance stay on one ledger key). All offline: the
registry and the byok artifact are redirected to tmp via env, the provider
registry is reset around each test, and no network is touched.

Mutation check (spec): revert ``_parse_create`` to a single ``model_id`` and
the first test goes red — the POST below sends no bare ``model_id``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_budget import register_settings_budget_routes
from interfaces.research.api.settings_models_admin import (
    UserModelChoice,
    UserModelChoiceUnavailable,
    UserModelRecord,
    _load_registry,
    resolve_owner_model_authority,
    resolve_user_model_choice,
)
from runtime.byok.store import list_credentials
from runtime.research_runner.byot_provider_catalog import (
    get_model_variant,
    get_provider_preset,
)
from substrate.dispatch.router import reset_provider_registry

_SECRET = "sk-BBBB-one-key-two-variants-secret-1234567890"

_TEST_EMAIL = "operator-under-test@example.com"


def _owner() -> str:
    """The Option A owner this suite's verified test operator derives to."""
    from interfaces.research.api.account_memory_identity import (
        derive_owner_from_verified_email,
    )

    return derive_owner_from_verified_email(_TEST_EMAIL)


def _pid(slug: str) -> str:
    """Owner-namespaced provider id for the suite's verified test operator
    (the same derivation tests/test_settings_models_admin.py uses)."""
    from interfaces.research.api.settings_models_admin import _owner_id_prefix

    return _owner_id_prefix(_owner()) + slug


_TWO_VARIANTS = {
    "provider_kind": "openai_compat",
    "provider_catalog_id": "deepseek",
    "model_ids": ["deepseek-v4-pro", "deepseek-flash"],
    "display_name": "My DeepSeek",
    "api_key": _SECRET,
}


def _fresh_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _test_identity(request, call_next):
        # One verified operator for this suite — the same seam
        # tests/test_settings_models_admin.py uses. Option A keys rows on
        # the derived owner from user_email; without an identity the route
        # correctly refuses with 401.
        request.state.user_id = "__operator__"
        request.state.user_email = _TEST_EMAIL
        request.state.auth_method = "antiek_session_cookie"
        return await call_next(request)

    register_settings_budget_routes(app)
    return app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_USER_MODELS_PATH", str(tmp_path / "settings" / "user_models.json"))
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "byok" / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "byok" / "master.key"))
    reset_provider_registry()
    return tmp_path


@pytest.fixture
def client(env: Path) -> Iterator[TestClient]:
    with TestClient(_fresh_app()) as c:
        yield c
    reset_provider_registry()


def _choice(model_id: str) -> dict[str, str]:
    return {"authority": "user_model", "provider_id": _pid("my-deepseek"), "model_id": model_id}


def test_one_registration_two_variants_one_record_one_credential(client: TestClient) -> None:
    created = client.post("/settings/models/user", json=_TWO_VARIANTS)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["id"] == _pid("my-deepseek")
    assert row["model_id"] == "deepseek-v4-pro"  # primary = first listed
    assert row["model_ids"] == ["deepseek-v4-pro", "deepseek-flash"]
    assert row["key_present"] is True
    assert row["registered"] is True
    assert "api_key" not in created.text
    assert _SECRET not in created.text

    # Exactly ONE durable record and exactly ONE encrypted credential.
    registry = _load_registry()
    assert list(registry) == [_pid("my-deepseek")]
    record: UserModelRecord = registry[_pid("my-deepseek")]
    assert record.model_ids == ["deepseek-v4-pro", "deepseek-flash"]
    credentials = list_credentials()
    assert len(credentials) == 1
    assert credentials[0].account_handle == _pid("my-deepseek")
    assert credentials[0].cred_id == record.cred_ref

    # The inventory shows ONE key row carrying TWO variants, not two rows.
    inventory = client.get("/settings/models/user").json()
    assert inventory["count"] == 1
    assert inventory["models"][0]["model_ids"] == ["deepseek-v4-pro", "deepseek-flash"]

    # Both variants are selectable under the SAME record id; each resolves
    # to the variant that was asked for, and an unlisted one is refused.
    for variant in ("deepseek-v4-pro", "deepseek-flash"):
        resolved = client.post("/settings/models/user/resolve", json=_choice(variant))
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["provider_id"] == _pid("my-deepseek")
        assert resolved.json()["model_id"] == variant
    assert client.post("/settings/models/user/resolve", json=_choice("deepseek-v3")).status_code == 409


def test_each_variant_is_priced_as_itself_under_one_key(client: TestClient) -> None:
    assert client.post("/settings/models/user", json=_TWO_VARIANTS).status_code == 201
    preset = get_provider_preset("deepseek")
    snapshots = {}
    for variant in ("deepseek-v4-pro", "deepseek-flash"):
        choice = UserModelChoice(
            authority="user_model", provider_id=_pid("my-deepseek"), model_id=variant,
        )
        route = resolve_user_model_choice(client.app, choice, owner_user_id=_owner())
        authority = resolve_owner_model_authority(client.app, choice, owner_user_id=_owner())
        # Dispatch consumers read the CHOSEN variant off the authority, while
        # the record (and therefore the ledger key) is the same for both.
        assert authority.model_id == variant
        assert authority.record.id == _pid("my-deepseek")
        assert route.model_id == variant
        assert route.provider_id == _pid("my-deepseek")
        assert route.rate_snapshot == get_model_variant(preset, variant).snapshot
        snapshots[variant] = route.rate_snapshot
    # V4 Pro and V4 Flash carry different pinned pricing; one key, two prices.
    assert snapshots["deepseek-v4-pro"] != snapshots["deepseek-flash"]
    with pytest.raises(UserModelChoiceUnavailable):
        resolve_owner_model_authority(
            client.app,
            UserModelChoice(
                authority="user_model", provider_id=_pid("my-deepseek"), model_id="deepseek-v3",
            ),
            owner_user_id=_owner(),
        )


def test_explicit_model_id_becomes_primary_when_listed(client: TestClient) -> None:
    body = {**_TWO_VARIANTS, "model_id": "deepseek-flash"}
    created = client.post("/settings/models/user", json=body)
    assert created.status_code == 201, created.text
    assert created.json()["model_id"] == "deepseek-flash"
    assert created.json()["model_ids"] == ["deepseek-flash", "deepseek-v4-pro"]


def test_single_model_id_registration_is_a_one_variant_record(client: TestClient) -> None:
    body = {k: v for k, v in _TWO_VARIANTS.items() if k != "model_ids"}
    created = client.post("/settings/models/user", json={**body, "model_id": "deepseek-flash"})
    assert created.status_code == 201, created.text
    assert created.json()["model_id"] == "deepseek-flash"
    assert created.json()["model_ids"] == ["deepseek-flash"]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"model_ids": ["deepseek-flash", "gpt-5.6-sol"]}, "not in preset"),
        ({"model_ids": ["deepseek-flash", "deepseek-flash"]}, "repeated"),
        ({"model_ids": []}, "empty"),
        ({"model_ids": "deepseek-flash"}, "not a list"),
        ({"model_ids": ["deepseek-flash"], "model_id": "deepseek-v4-pro"}, "primary unlisted"),
        ({"model_ids": ["deep seek"]}, "whitespace"),
    ],
)
def test_malformed_variant_lists_are_refused_value_free(
    client: TestClient, mutation: dict[str, object], reason: str,
) -> None:
    del reason
    response = client.post("/settings/models/user", json={**_TWO_VARIANTS, **mutation})
    assert response.status_code == 422, response.text
    assert _SECRET not in response.text
    assert list_credentials() == []


def test_pre_variant_registry_row_loads_as_single_variant(client: TestClient, env: Path) -> None:
    """A row written before ``model_ids`` existed normalises on read."""
    body = {k: v for k, v in _TWO_VARIANTS.items() if k != "model_ids"}
    assert client.post("/settings/models/user", json={**body, "model_id": "deepseek-flash"}).status_code == 201
    path = env / "settings" / "user_models.json"
    raw = path.read_text()
    assert '"model_ids"' in raw
    import json

    registry = json.loads(raw)
    del registry[_pid("my-deepseek")]["model_ids"]
    path.write_text(json.dumps(registry))

    record = _load_registry()[_pid("my-deepseek")]
    assert record.model_ids == ["deepseek-flash"]
