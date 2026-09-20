"""The secrets template must declare the variables that decide whether the API
is authenticated.

`infrastructure/ansible/templates/secrets.env.j2` is the only artifact that
describes what belongs in `/etc/antiek/secrets.env`. The operator-auth
middleware takes a bypass branch when its three gate variables are all empty —
correct for a local checkout, catastrophic for a box brought up from this
template — and none of the three had a slot here.

The gate names are DERIVED from `app.py` rather than hand-listed, so renaming
the constant moves this test with it instead of silently un-covering the gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TEMPLATE = _ROOT / "infrastructure" / "ansible" / "templates" / "secrets.env.j2"
_APP = _ROOT / "interfaces" / "research" / "api" / "app.py"

# The constants in app.py that name the operator-auth gate env vars. If the
# bypass branch at `not expected_token and not operator_emails and not
# expected_st_client_id` is ever rewritten, update this list deliberately.
_GATE_CONSTANTS = (
    "_OPERATOR_TOKEN_ENV",
    "_OPERATOR_EMAIL_ENV",
    "_OPERATOR_SERVICE_TOKEN_CLIENT_ID_ENV",
)


def _declared_slots() -> set[str]:
    """Every `NAME=` slot declared in the template."""
    text = _TEMPLATE.read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, re.MULTILINE))


def _auth_gate_env_names() -> set[str]:
    """The env var names whose simultaneous absence disables enforcement."""
    src = _APP.read_text(encoding="utf-8")
    names: set[str] = set()
    for const in _GATE_CONSTANTS:
        match = re.search(rf'^\s*{const}\s*=\s*"([A-Z0-9_]+)"', src, re.MULTILINE)
        if match is None:
            pytest.fail(
                f"{const} no longer assigns a literal env var name in "
                f"{_APP.relative_to(_ROOT)}. This test derives the auth gate "
                "from that assignment; re-derive it rather than deleting this."
            )
        names.add(match.group(1))
    return names


def test_auth_gate_variables_have_declared_slots() -> None:
    gate = _auth_gate_env_names()
    missing = sorted(gate - _declared_slots())
    assert not missing, (
        "The operator-auth gate variables are absent from "
        f"{_TEMPLATE.relative_to(_ROOT)}: {missing}. app.py disables "
        "enforcement entirely when all of them are empty, so a production box "
        "provisioned from this template would serve every route to every "
        "caller with a fully-scoped operator identity. Declare them (empty is "
        "fine — the slot plus its comment is what carries the requirement)."
    )


def test_session_signing_key_has_a_declared_slot() -> None:
    """The cookie minted at /auth/callback is only as good as its key."""
    assert "ANTIEK_AUTH_SECRET" in _declared_slots(), (
        "ANTIEK_AUTH_SECRET signs the Antiek session cookie and must have a "
        f"slot in {_TEMPLATE.relative_to(_ROOT)}."
    )


def test_contract_is_not_vacuous() -> None:
    """Both sides must be non-trivially populated.

    If the template regex broke, `_declared_slots()` would return the empty
    set and every membership assertion above would fail loudly — but if the
    *derivation* broke and returned an empty gate, `gate - declared` would be
    empty and the first test would pass while checking nothing. Pin both.
    """
    assert len(_auth_gate_env_names()) == len(_GATE_CONSTANTS), (
        "the auth-gate derivation collapsed; it must resolve one env var name "
        "per constant"
    )
    assert len(_declared_slots()) >= 10, (
        "the template slot parse collapsed; secrets.env.j2 declares many more "
        "than 10 slots"
    )
