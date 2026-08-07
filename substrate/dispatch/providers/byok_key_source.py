"""``byok_key_source`` — resolve a dispatch provider's API key from the operator's
BYOK store first, the process environment second.

This is the load-bearing join that makes Antiek **actually** bring-your-own-token
for the certified provider set: instead of every provider reading its key straight
from ``os.environ`` at boot (``bootstrap.py``), each provider asks this module for
its key. The resolver prefers a key the operator (or, later, the signed-in user)
has stored in the encrypted BYOK store (``runtime.byok.store``) under the
provider-scoped handle ``provider:<name>``; if none is stored it falls back to the
environment variable, exactly as before. So:

* **No BYOK key stored** → identical to today (env var). Zero behaviour change.
* **BYOK key stored** → the stored key is used; the env var need not be set.
* **``ANTIEK_BYOT_ONLY=1``** → the env fallback is disabled. A provider registers
  ONLY if the operator has stored its key in BYOK. This is the honest mechanism
  behind "remove my keys": you onboard your key into the store and flip the flag —
  you never ``rm .env`` and you are never silently spending on an env key you meant
  to retire.

Scope note (deliberate): this covers the **certified provider set** already wired in
``bootstrap.py`` (DeepSeek / Anthropic / OpenRouter / MiMo / xAI-bridge / Z.ai) —
providers whose adapters + pricing are already qualified and reach
``RouteExecutionStatus.EXECUTABLE``. It does NOT open a path for arbitrary user-
supplied *custom* endpoints; that requires the preset-catalog + route-authority
qualification seam (spec ``byot-onboarding.md`` §5.C) and is intentionally out of
scope here so the spend-safety invariant is never weakened.

The plaintext key is handled as a redacting ``SecretStr`` right up to the moment it
is handed to the provider constructor; it is never logged.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("substrate.dispatch.providers.byok_key_source")

# BYOK credentials for the dispatch provider set are stored under this
# ``pipeline_kind`` namespace so provider-dispatch keys never collide with
# ingest/tool credentials in the same store.
_PROVIDER_PIPELINE_PREFIX = "provider:"

_TRUE = frozenset({"1", "true", "yes", "on"})


def byot_only_enabled() -> bool:
    """True when ``ANTIEK_BYOT_ONLY`` disables the environment-variable fallback.

    Default (unset/empty) is False — env providers stay available, so this whole
    module is a pure superset of the pre-existing behaviour until the operator
    opts in.
    """
    return os.environ.get("ANTIEK_BYOT_ONLY", "").strip().lower() in _TRUE


def _lookup_byok_key(provider_handle: str) -> str | None:
    """Return the plaintext key stored in the BYOK store for
    ``provider:<provider_handle>``, or ``None`` if there is none / the store is
    unreadable. Never raises — a broken or absent store degrades to env fallback.
    """
    try:
        # Imported lazily so importing this module (and therefore the provider
        # bootstrap) never hard-depends on the BYOK store being initialised.
        from runtime.byok import store as byok_store
    except Exception:  # pragma: no cover - byok package always importable in-tree
        return None

    want = f"{_PROVIDER_PIPELINE_PREFIX}{provider_handle}"
    configured_owner = os.environ.get("ANTIEK_OPERATOR_USER_ID")
    try:
        matches = [
            meta
            for meta in byok_store.list_credentials()
            if meta.pipeline_kind == want
            and (configured_owner is None or meta.owner_user_id == configured_owner)
        ]
    except Exception:
        # No artifact yet, unreadable store, permission error → env fallback.
        return None
    if not matches:
        return None
    # Credential metadata is ordered by opaque random id, not creation time.
    # Picking first/last would therefore make authority random after a duplicate
    # write. Fail closed until the operator-scoped Settings replacement route
    # establishes exactly one record.
    if len(matches) != 1:
        logger.warning(
            "provider %s has ambiguous BYOK credentials; refusing stored-key authority",
            provider_handle,
        )
        return None
    chosen = matches[0]
    try:
        secret = byok_store.load_credential(chosen.cred_id)
    except Exception:
        # Ciphertext present but master key missing/rotated → do NOT crash boot;
        # fall back to env. Surface once, without the secret.
        logger.warning(
            "byok key for %s present but could not be decrypted; using env fallback",
            provider_handle,
        )
        return None
    revealed = secret.reveal()
    return revealed or None


def resolve_provider_key(provider_handle: str, env_var: str) -> str | None:
    """Resolve the API key for a dispatch provider.

    Order: BYOK store (``provider:<provider_handle>``) → environment ``env_var``.
    When ``ANTIEK_BYOT_ONLY`` is set, the env fallback is skipped: the provider
    registers only if its key is in the BYOK store.

    Returns the plaintext key, or ``None`` when no key is available (the caller —
    ``bootstrap.py`` — treats ``None`` as "do not register this provider", the
    same degraded-posture contract it already honours for a missing env var).
    """
    byok_key = _lookup_byok_key(provider_handle)
    if byok_key:
        logger.info("provider %s: key sourced from BYOK store", provider_handle)
        return byok_key
    if byot_only_enabled():
        # Operator opted into BYOT-only and has not onboarded this provider's
        # key: refuse honestly rather than silently spending on the env key.
        return None
    return os.environ.get(env_var)
