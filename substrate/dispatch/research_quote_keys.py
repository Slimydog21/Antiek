"""Atomic environment-backed keyring loader shared by quote producers."""

from __future__ import annotations

import base64
import json
import os

from .research_quote import ResearchQuoteInvalid


def load_research_quote_keyring() -> tuple[str, bytes, dict[str, bytes]]:
    encoded = os.environ.get("ANTIEK_RESEARCH_QUOTE_KEYRING_JSON", "").strip()
    if not encoded:
        raise ResearchQuoteInvalid("research quote signing authority is unavailable")

    def decode_key(value: str) -> bytes:
        try:
            key = base64.b64decode(
                value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
            )
        except (ValueError, UnicodeEncodeError) as exc:
            raise ResearchQuoteInvalid("research quote keyring is malformed") from exc
        if len(key) < 32:
            raise ResearchQuoteInvalid(
                "research quote keys must contain at least 32 bytes"
            )
        return key

    try:
        document = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise ResearchQuoteInvalid("research quote keyring is malformed") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "active_key_id", "keys"}
        or document.get("schema_version") != 1
        or not isinstance(document.get("active_key_id"), str)
        or not isinstance(document.get("keys"), dict)
    ):
        raise ResearchQuoteInvalid("research quote keyring is malformed")
    active_key_id = document["active_key_id"]
    keyring: dict[str, bytes] = {}
    for key_id, value in document["keys"].items():
        if (
            not isinstance(key_id, str)
            or not key_id
            or len(key_id) > 128
            or not isinstance(value, str)
        ):
            raise ResearchQuoteInvalid("research quote keyring is malformed")
        keyring[key_id] = decode_key(value)
    signing_key = keyring.get(active_key_id)
    if signing_key is None:
        raise ResearchQuoteInvalid("active research quote key is inconsistent")
    return active_key_id, signing_key, keyring
