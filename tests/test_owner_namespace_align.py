"""Namespace Option A — two allowlisted operators cannot see each other's rows."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


def _req(email: str | None, user_id: str = "__operator__") -> Any:
    return SimpleNamespace(state=SimpleNamespace(user_id=user_id, user_email=email))


def test_two_allowlisted_emails_get_distinct_owners() -> None:
    a = request_owner_user_id(_req("alice@example.com"))
    b = request_owner_user_id(_req("bob@example.com"))
    assert a != b
    assert a == derive_owner_from_verified_email("alice@example.com")
    assert b == derive_owner_from_verified_email("bob@example.com")


def test_same_email_is_stable_across_calls() -> None:
    a1 = request_owner_user_id(_req("alice@example.com"))
    a2 = request_owner_user_id(_req("Alice@example.com"))
    assert a1 == a2


def test_legacy_user_id_does_not_leak_shared_owner() -> None:
    # The old path keyed on user_id="__operator__" for everyone.
    a = request_owner_user_id(_req("alice@example.com", user_id="__operator__"))
    b = request_owner_user_id(_req("bob@example.com", user_id="__operator__"))
    assert a != b, "shared sentinel must not collapse two people into one owner"


def test_fails_closed_without_verified_email() -> None:
    try:
        request_owner_user_id(_req(None))
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("missing e-mail must 401, not mint an owner")


def test_fails_closed_on_malformed_email() -> None:
    try:
        request_owner_user_id(_req("not-an-email"))
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("malformed e-mail must 401")


# The migration-tool tests that used to live here exercised the superseded
# 71-line draft (wrong registry shape — a silent no-op against real stores,
# proven in the PR review). Migration coverage now lives in
# tests/tools/test_migrate_owner_namespace.py, which drives the ported tool
# against real registry/BYOK/sqlite/DuckDB stores, including the multi-owner
# refusal and the operator-rows-only re-own these two tests asserted.
