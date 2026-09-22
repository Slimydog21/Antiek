"""Namespace Option A — two allowlisted operators cannot see each other's rows."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from fastapi import HTTPException  # noqa: E402

from interfaces.research.api.account_memory_identity import (  # noqa: E402
    derive_owner_from_verified_email,
)
from interfaces.research.api.settings_models_admin import (  # noqa: E402
    request_owner_user_id,
)


def _req(email: str | None, user_id: str = "__operator__") -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(user_id=user_id, user_email=email))


def test_two_allowlisted_emails_get_distinct_owners():
    a = request_owner_user_id(_req("alice@example.com"))
    b = request_owner_user_id(_req("bob@example.com"))
    assert a != b
    assert a == derive_owner_from_verified_email("alice@example.com")
    assert b == derive_owner_from_verified_email("bob@example.com")


def test_same_email_is_stable_across_calls():
    a1 = request_owner_user_id(_req("alice@example.com"))
    a2 = request_owner_user_id(_req("Alice@example.com"))
    assert a1 == a2


def test_legacy_user_id_does_not_leak_shared_owner():
    # The old path keyed on user_id="__operator__" for everyone.
    a = request_owner_user_id(_req("alice@example.com", user_id="__operator__"))
    b = request_owner_user_id(_req("bob@example.com", user_id="__operator__"))
    assert a != b, "shared sentinel must not collapse two people into one owner"


def test_fails_closed_without_verified_email():
    try:
        request_owner_user_id(_req(None))
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("missing e-mail must 401, not mint an owner")


def test_fails_closed_on_malformed_email():
    try:
        request_owner_user_id(_req("not-an-email"))
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("malformed e-mail must 401")


def test_migration_refuses_multi_owner_registry(tmp_path):
    from tools.migrate_owner_namespace import migrate_registry

    reg = tmp_path / "user_models.json"
    reg.write_text(
        '{"models": ['
        '{"id": "m1", "owner_user_id": "__operator__"},'
        '{"id": "m2", "owner_user_id": "derived:other"}'
        "]}"
    )
    rc = migrate_registry(reg, "alice@example.com", apply=True)
    assert rc == 3, "must refuse when more than one legacy owner is present"


def test_migration_reowns_only_operator_rows(tmp_path):
    from tools.migrate_owner_namespace import migrate_registry

    reg = tmp_path / "user_models.json"
    reg.write_text(
        '{"models": ['
        '{"id": "m1", "owner_user_id": "__operator__"},'
        '{"id": "m2", "owner_user_id": "__operator__"}'
        "]}"
    )
    rc = migrate_registry(reg, "alice@example.com", apply=True)
    assert rc == 0
    body = reg.read_text()
    assert '"owner_user_id": "__operator__"' not in body and '"owner_user_id":"__operator__"' not in body
    assert derive_owner_from_verified_email("alice@example.com") in body
    assert "migrated_from_owner" in body
