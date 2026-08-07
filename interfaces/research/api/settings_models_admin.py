"""Operator Settings — user-added model providers (add-model vertical).

Settings SPR-01 shipped the read-only model inventory and deferred "add
model" to a later sprint. This module is that vertical: the operator
registers their own provider endpoint + model (BYOK — bring your own key)
from Settings through the same low-level seam ``register_default_providers``
populates: ``register_provider`` plus the
``app.state.registered_providers`` name set. Registration is deliberately
distinct from route authority: this vertical does not silently bind a new
provider to an active tier. ``GET /settings/models`` therefore reports it as
registered but not route-ready until the model-selection vertical explicitly
chooses where it may drive a prompt.

SECRET HANDLING — reuses the house BYOK mechanism, decision (a)
────────────────────────────────────────────────────────────────
The API key is stored ENCRYPTED AT REST via ``runtime.byok.store``
directly (libsodium SecretBox, master key in a 0600 key file, plaintext
returned only as a redacting ``SecretStr``). ``CredentialMetadata``
generalizes cleanly: the key lands with ``pipeline_kind="model_provider"``
and the record id as its non-secret handle, so ``list_credentials`` can
answer ``key_present`` without ever touching key material. The only
X-flavored residue is the opaque ``cred-x-`` id prefix — cosmetic, not
semantic — so building a parallel store on the raw primitives (option (b))
would have duplicated artifact/key-file plumbing for zero security gain.

The plaintext key is NEVER in any response, log, repr, or exception
message. Three load-bearing consequences in the code:

* ``POST /settings/models/user`` parses its body BY HAND. FastAPI's
  ``RequestValidationError`` echoes the offending input back in the 422
  body — and for a missing-field error the echoed input is the WHOLE
  body, api_key included. Manual parsing keeps every 4xx value-free.
* Keys travel ONLY in ``api_key``. ``base_url`` is structurally prevented
  from carrying credentials: it must be scheme + host + optional path,
  and any userinfo (``user:secret@host``), query string (``?key=...``),
  or fragment is rejected value-free — otherwise a key-bearing URL would
  land PLAINTEXT in the registry file and echo in every response that
  carries base_url. Lengths are bounded too (api_key ≤ 512, base_url
  ≤ 2048) so a paste accident cannot balloon the ciphertext artifact.
* Registered providers resolve their key AT CALL TIME (decrypt-on-use via
  ``_ByokResolvedKeyMixin``), never holding plaintext in instance state.
  Resolution re-checks the durable registry first, so a DELETE is
  effective immediately even though the in-process dispatch registry has
  no public unregister: a removed/disabled record can no longer resolve a
  key, making any lingering registry entry inert until the next boot.

DELETE removes both the registry row and its SecretBox ciphertext through
``runtime.byok.store.delete_credential``. Registry removal is written first:
a crash or artifact-integrity failure can therefore leave unreachable
ciphertext, but can never leave a live registry row pointing at a credential
that was already deleted.

PERSISTENCE — non-secret registry
─────────────────────────────────
``(ANTIEK_HOME|~/.antiek)/settings/user_models.json`` (override:
``ANTIEK_USER_MODELS_PATH``), mirroring the DaemonBudget JSON-sidecar
precedent. No DuckDB, so the single-writer/db_lock rule is untouched; the
API process is the only writer (``--workers 1`` house invariant). Reads
are lenient like ``store._read_artifact`` (corrupt file → empty registry),
writes are ``indent=2, sort_keys=True`` like ``store._write_artifact``.

Mount: ``register_settings_budget_routes`` (settings_budget.py) calls
``register_settings_models_admin_routes`` — the settings-local pattern;
app.py is untouched. Boot-time reload of user providers runs as a startup
event handler because ``create_app`` assigns
``app.state.registered_providers`` AFTER the settings routes are mounted;
startup events fire later still, so the union lands on the real set.

Non-goals honored: no implicit dispatch-tier mutation, no per-key usage ledger,
no budget writes, no live provider validation calls. Named presets receive an
exact server-owned price row; custom endpoints remain unknown-priced, and no
preset is presented as hard-ceiling executable without provider reconciliation.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from runtime.byok.store import (
    CredentialIntegrityError,
    CredentialMetadata,
    delete_credential,
    list_credentials,
    load_credential,
    store_credential,
)
from runtime.research_runner.byot_provider_catalog import (
    ProviderCatalogId,
    canonical_catalog_id,
    get_model_variant,
    get_provider_preset,
    route_authority_catalog_entries,
)
from runtime.research_runner.provider_route_authority import (
    EMPTY_PROVIDER_ROUTE_AUTHORITY,
    ProviderRouteAuthority,
    ProviderRouteAuthorityResolver,
    ProviderRouteIdentity,
    RouteExecutionStatus,
    canonical_provider_endpoint,
)
from substrate.dispatch.base import Provider, ProviderError
from substrate.dispatch.providers.anthropic import AnthropicProvider
from substrate.dispatch.providers.openai_compat import OpenAICompatProvider
from substrate.dispatch.router import get_provider, register_provider

_ENV_REGISTRY_PATH = "ANTIEK_USER_MODELS_PATH"
_ENV_HOME = "ANTIEK_HOME"

_PIPELINE_KIND = "model_provider"
_ID_PREFIX = "user-"
_LEGACY_OWNER_USER_ID = "__operator__"
_REGISTRY_LOCK = threading.RLock()
_PRIVATE_FILE_MODE = 0o600

ProviderKind = Literal["openai_compat", "anthropic"]
_PROVIDER_KINDS: tuple[str, ...] = ("openai_compat", "anthropic")


class UserModelRegistryIntegrityError(RuntimeError):
    """Durable model authority is corrupt and must not be overwritten."""


# Shortest real provider keys are far longer; this catches truncated pastes
# without rejecting any legitimate key format.
_MIN_KEY_LEN = 8
# Longest real provider keys are well under this (OpenAI project keys ~164
# chars, Anthropic ~108, GCP service tokens in the low hundreds); the cap
# bounds the SecretBox ciphertext artifact against multi-megabyte paste
# accidents (a 2MiB "key" would otherwise land as a 4MiB hex ciphertext).
_MAX_KEY_LEN = 512
_MAX_BASE_URL_LEN = 2048
_MAX_DISPLAY_NAME_LEN = 64
_MAX_MODEL_ID_LEN = 200


# ---------------------------------------------------------------------------
# Durable non-secret registry
# ---------------------------------------------------------------------------


class UserModelRecord(BaseModel):
    """One durable registry entry. Non-secret by construction: the key
    lives ONLY as SecretBox ciphertext in the byok artifact, referenced
    here by its opaque ``cred_ref``."""

    id: str
    owner_user_id: str = Field(default=_LEGACY_OWNER_USER_ID, min_length=1, max_length=256)
    provider_kind: ProviderKind
    provider_catalog_id: ProviderCatalogId | None = None
    model_id: str
    display_name: str
    base_url: str | None = None
    cred_ref: str
    cred_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    enabled: bool = True


def _owner_hash(owner_user_id: str) -> str:
    return hashlib.blake2b(owner_user_id.encode("utf-8")).hexdigest()[:8]


def _owner_id_prefix(owner_user_id: str) -> str:
    return f"{_ID_PREFIX}{_owner_hash(owner_user_id)}-"


def _looks_namespaced(record_id: str) -> bool:
    tail = record_id.removeprefix(_ID_PREFIX)
    return len(tail) > 9 and tail[8] == "-" and all(c in "0123456789abcdef" for c in tail[:8])


def _record_identity_matches_owner(record: UserModelRecord) -> bool:
    if record.id.startswith(_owner_id_prefix(record.owner_user_id)):
        return True
    return (
        record.owner_user_id == _LEGACY_OWNER_USER_ID
        and record.id.startswith(_ID_PREFIX)
        and not _looks_namespaced(record.id)
    )


def _registered_name_belongs_to(name: str, owner_user_id: str) -> bool:
    if name.startswith(_owner_id_prefix(owner_user_id)):
        return True
    return (
        owner_user_id == _LEGACY_OWNER_USER_ID
        and name.startswith(_ID_PREFIX)
        and not _looks_namespaced(name)
    )


def request_owner_user_id(request: Request) -> str:
    value = getattr(request.state, "user_id", _LEGACY_OWNER_USER_ID)
    if not isinstance(value, str) or not value or len(value) > 256:
        raise HTTPException(status_code=401, detail="authenticated user identity required")
    return value


def _registry_path() -> Path:
    env = os.environ.get(_ENV_REGISTRY_PATH)
    if env:
        return Path(os.path.expanduser(env))
    home = os.environ.get(_ENV_HOME)
    base = Path(home) if home else Path.home() / ".antiek"
    return base / "settings" / "user_models.json"


def _fsync_directory(directory: Path) -> None:
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_directory(directory: Path) -> None:
    missing: list[Path] = []
    current = directory
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for item in reversed(missing):
        item.mkdir(exist_ok=True)
        _fsync_directory(item)
        _fsync_directory(item.parent)


def _secure_registry_file(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError("user-model registry must be a regular file")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise PermissionError("user-model registry must be owned by this user")
    if stat.S_IMODE(info.st_mode) != _PRIVATE_FILE_MODE:
        os.chmod(path, _PRIVATE_FILE_MODE)


@contextmanager
def _registry_guard(*, exclusive: bool) -> Iterator[None]:
    path = _registry_path()
    lock_path = Path(f"{path}.lock")
    _ensure_directory(lock_path.parent)
    with _REGISTRY_LOCK:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(lock_path), flags, _PRIVATE_FILE_MODE)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _load_registry_unlocked() -> dict[str, UserModelRecord]:
    """Read durable authority, preserving corrupt bytes for operator recovery."""
    path = _registry_path()
    if not path.exists():
        if path.is_symlink():
            raise RuntimeError("user-model registry must be a regular file")
        return {}
    _secure_registry_file(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise UserModelRegistryIntegrityError(
            "user-model registry is unreadable; refusing mutation"
        ) from exc
    if not isinstance(raw, dict):
        raise UserModelRegistryIntegrityError(
            "user-model registry root must be an object; refusing mutation"
        )
    out: dict[str, UserModelRecord] = {}
    for rid, entry in raw.items():
        try:
            record = UserModelRecord.model_validate(entry)
        except ValidationError as exc:
            raise UserModelRegistryIntegrityError(
                f"user-model registry entry {rid!r} is invalid; refusing mutation"
            ) from exc
        record_id = str(rid)
        # CREATE is the only authority that mints registry identities.  Apply
        # its namespace and key/id invariants again on every read so a restored
        # or externally corrupted sidecar cannot smuggle a default provider
        # name into the live dispatch registry at boot.
        if record_id != record.id or not _record_identity_matches_owner(record):
            raise UserModelRegistryIntegrityError(
                f"user-model registry entry {record_id!r} violates identity invariants"
            )
        out[record_id] = record
    return out


def _load_registry() -> dict[str, UserModelRecord]:
    with _registry_guard(exclusive=False):
        return _load_registry_unlocked()


def _write_registry_unlocked(registry: dict[str, UserModelRecord]) -> None:
    path = _registry_path()
    _ensure_directory(path.parent)
    data = {rid: rec.model_dump() for rid, rec in registry.items()}
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    fd = os.open(
        str(temporary),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        _PRIVATE_FILE_MODE,
    )
    try:
        payload = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, _PRIVATE_FILE_MODE)
        _fsync_directory(path.parent)
    finally:
        os.close(fd)
        with suppress(FileNotFoundError):
            temporary.unlink()


def _record_fingerprint(record: UserModelRecord) -> str:
    canonical = json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _registration_fingerprints(app: FastAPI) -> dict[str, str]:
    raw = getattr(app.state, "user_model_registration_fingerprints", None)
    if not isinstance(raw, dict):
        raw = {}
        app.state.user_model_registration_fingerprints = raw
    return raw


def _live_adapter_matches(app: FastAPI, provider_id: str) -> bool:
    try:
        adapter = get_provider(provider_id)
    except KeyError:
        return False
    return getattr(adapter, "_user_model_authority_fingerprint", None) == (
        _registration_fingerprints(app).get(provider_id)
    )


# ---------------------------------------------------------------------------
# Dispatch registration — the same seam register_default_providers uses
# ---------------------------------------------------------------------------


class _ByokResolvedKeyMixin:
    """Resolve the API key at CALL time from the byok store.

    Overrides the adapters' ``_resolve_api_key`` seam (the same method the
    env-var path uses) so plaintext never sits in provider instance state,
    and so a record deleted/disabled in Settings refuses key resolution
    IMMEDIATELY — the dispatch registry has no public unregister, and this
    check is what makes a lingering entry inert. Every failure message
    here is value-free by construction.
    """

    name: str
    _user_model_id: str
    _cred_ref: str
    _user_model_authority_fingerprint: str

    def _resolve_api_key(self) -> str:
        record = _load_registry().get(self._user_model_id)
        if (
            record is None
            or not record.enabled
            or record.cred_ref != self._cred_ref
            or not _credential_matches_record(record, _credential_metadata())
        ):
            raise ProviderError(
                f"{self.name}: user-added provider was removed, disabled, or "
                "its credential binding changed; refusing credential resolution.",
                provider=self.name,
                model="<unknown>",
                latency_ms=0,
            )
        try:
            secret = load_credential(self._cred_ref)
        except (KeyError, CredentialIntegrityError) as exc:
            raise ProviderError(
                f"{self.name}: stored credential is missing from the BYOK artifact.",
                provider=self.name,
                model="<unknown>",
                latency_ms=0,
            ) from exc
        return secret.reveal()


def _credential_metadata() -> dict[str, CredentialMetadata]:
    """Index only non-secret BYOK metadata; this never decrypts a key."""
    return {item.cred_id: item for item in list_credentials()}


def _credential_matches_record(
    record: UserModelRecord,
    metadata: dict[str, CredentialMetadata],
) -> bool:
    """Bind a registry row to the credential CREATE minted for that row.

    A restored or hand-edited sidecar must not be able to point an arbitrary
    model endpoint at an unrelated X or other BYOK credential.
    """
    item = metadata.get(record.cred_ref)
    if item is None:
        return False
    owner_bound = (item.binding_version == 3 and item.owner_user_id == record.owner_user_id) or (
        item.binding_version == 2
        and item.owner_user_id is None
        and record.owner_user_id == _LEGACY_OWNER_USER_ID
    )
    return bool(
        owner_bound
        and item.pipeline_kind == _PIPELINE_KIND
        and item.account_handle == record.id
        and item.artifact_fingerprint == record.cred_fingerprint
    )


def _migrate_legacy_registry_unlocked(
    registry: dict[str, UserModelRecord],
    metadata: dict[str, CredentialMetadata],
) -> tuple[dict[str, UserModelRecord], bool]:
    """Re-seal legacy user-model credentials under v3 owner binding."""
    changed = False
    migrated = dict(registry)
    for record_id, record in registry.items():
        if record.cred_fingerprint is not None:
            continue
        legacy = metadata.get(record.cred_ref)
        if (
            legacy is None
            or legacy.binding_version != 1
            or legacy.pipeline_kind != _PIPELINE_KIND
            or legacy.account_handle != record.id
        ):
            continue
        plaintext: str | None = None
        try:
            plaintext = load_credential(record.cred_ref).reveal()
            new_ref = store_credential(
                record.id,
                plaintext,
                pipeline_kind=_PIPELINE_KIND,
                owner_user_id=record.owner_user_id,
            )
        except (KeyError, CredentialIntegrityError, OSError, ValueError):
            continue
        finally:
            plaintext = None
        new_metadata = _credential_metadata().get(new_ref)
        if new_metadata is None or new_metadata.binding_version != 3:
            continue
        migrated[record_id] = record.model_copy(
            update={
                "cred_ref": new_ref,
                "cred_fingerprint": new_metadata.artifact_fingerprint,
            }
        )
        changed = True
    return migrated, changed


class _UserOpenAICompatProvider(_ByokResolvedKeyMixin, OpenAICompatProvider):
    """User-added OpenAI-shaped endpoint. The operator supplies the FULL
    base URL including any version prefix (e.g. ``https://api.openai.com/v1``)
    and the adapter appends ``/chat/completions`` — the dominant house
    pattern (openrouter/hermes/xiaomi/zai) that avoids the double-``/v1``
    404 class documented in bootstrap.py."""

    def __init__(self, record: UserModelRecord) -> None:
        super().__init__(
            name=record.id,
            base_url=record.base_url or "",
            chat_completions_path="/chat/completions",
            # This endpoint is operator-supplied and therefore untrusted. It
            # can reflect Authorization in a response; upstream body text must
            # never enter ProviderError, which callers may expose or persist.
            expose_error_body=False,
        )
        self._user_model_id = record.id
        self._cred_ref = record.cred_ref
        self._user_model_authority_fingerprint = _record_fingerprint(record)


class _UserAnthropicProvider(_ByokResolvedKeyMixin, AnthropicProvider):
    def __init__(self, record: UserModelRecord) -> None:
        if record.base_url:
            super().__init__(base_url=record.base_url, expose_error_body=False)
        else:
            super().__init__(expose_error_body=False)
        # Registry entries are name-keyed; shadow the class-level
        # ``name = "anthropic"`` so a user entry never collides with the
        # default adapter.
        self.name = record.id
        self._user_model_id = record.id
        self._cred_ref = record.cred_ref
        self._user_model_authority_fingerprint = _record_fingerprint(record)


def _make_provider(record: UserModelRecord) -> Provider:
    if record.provider_kind == "anthropic":
        return _UserAnthropicProvider(record)
    return _UserOpenAICompatProvider(record)


def _seam_names(app: FastAPI) -> set[str]:
    """The live registered-provider name set, coerced to a real set on
    ``app.state`` so unions/discards are visible to ``GET /settings/models``
    and ``/health`` (which read the same attribute)."""
    raw = getattr(app.state, "registered_providers", None)
    if isinstance(raw, set):
        return raw
    coerced: set[str] = (
        {str(p) for p in raw} if isinstance(raw, (list, tuple, frozenset)) else set()
    )
    app.state.registered_providers = coerced
    return coerced


def reload_user_providers(app: FastAPI) -> set[str]:
    """Register every enabled user model whose credential is present.

    Mirrors ``register_default_providers``' degraded posture: a record
    without a stored credential (or disabled) is skipped, not an error.
    Returns the set of registered names, same contract as the bootstrap.

    Also RECONCILES the seam set: a ``user-``-prefixed name in
    ``app.state.registered_providers`` without an enabled registry record
    (a corrupt/lost registry file is the realistic path here) is stale —
    its key resolution would refuse anyway — and is discarded so
    ``GET /settings/models`` cannot report ``ready: true`` for a provider
    that cannot resolve credentials. Default provider names are never
    touched (prefix-guarded).
    """
    with _registry_guard(exclusive=True):
        registry = _load_registry_unlocked()
        metadata = _credential_metadata()
        registry, migrated = _migrate_legacy_registry_unlocked(registry, metadata)
        if migrated:
            _write_registry_unlocked(registry)
            metadata = _credential_metadata()
    registered: set[str] = set()
    fingerprints: dict[str, str] = {}
    for record_id, record in registry.items():
        # Defense in depth at the authority boundary: even if a future registry
        # reader becomes more permissive, boot reload may only register names
        # that CREATE could have minted.
        if record_id != record.id or not _record_identity_matches_owner(record):
            continue
        if not record.enabled or not _credential_matches_record(record, metadata):
            continue
        adapter = _make_provider(record)
        register_provider(adapter)
        registered.add(record.id)
        fingerprints[record.id] = _record_fingerprint(record)
    seam = _seam_names(app)
    stale = {
        name
        for name in seam
        if name.startswith(_ID_PREFIX) and not (name in registry and registry[name].enabled)
    }
    seam.difference_update(stale)
    seam.update(registered)
    app.state.user_model_registration_fingerprints = fingerprints
    return registered


# ---------------------------------------------------------------------------
# API models (responses never carry key material — there is no key field)
# ---------------------------------------------------------------------------


class UserModelRow(BaseModel):
    id: str
    provider_kind: ProviderKind
    provider_catalog_id: ProviderCatalogId | None = None
    model_id: str
    display_name: str
    base_url: str | None
    enabled: bool
    key_present: bool
    registered: bool
    route_eligible: bool
    pricing_status: Literal["known", "unknown"] = "unknown"
    hard_ceiling_eligible: bool = False
    execution_status: RouteExecutionStatus = RouteExecutionStatus.BLOCKED_UNKNOWN_PRICING
    rate_snapshot: str | None = None


class UserModelsResponse(BaseModel):
    models: list[UserModelRow]
    count: int
    # Surfacing, not hiding: user-* names still in the live registered set
    # whose registry record is gone (corrupt/lost file while the process is
    # up). They cannot resolve keys and clear at the next boot reconcile.
    stale_registered: list[str] = Field(default_factory=list)
    source: str = "settings user-model registry + byok credential store"


class UserModelDeleteResponse(BaseModel):
    removed: str
    notes: list[str]


class UserModelChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    authority: Literal["user_model"]
    provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=200)


@dataclass(frozen=True, slots=True)
class ResolvedUserModelRoute:
    authority: Literal["user_model"]
    provider_id: str
    model_id: str
    credential_ref: str
    pricing_status: Literal["known", "unknown"]
    hard_ceiling_eligible: bool
    execution_status: RouteExecutionStatus
    rate_snapshot: str | None


class UserModelChoiceUnavailable(ValueError):
    """The requested route has no current exact server authority."""


@dataclass(frozen=True, slots=True)
class UserModelAuthoritySnapshot:
    model_id: str
    route_eligible: bool
    pricing_status: Literal["known", "unknown"]
    hard_ceiling_eligible: bool
    execution_status: RouteExecutionStatus
    rate_snapshot: str | None


def _route_execution_authority(app: FastAPI, record: UserModelRecord) -> ProviderRouteAuthority:
    endpoint = record.base_url or "https://api.anthropic.com"
    identity = ProviderRouteIdentity(
        provider_kind=record.provider_kind,
        model_id=record.model_id,
        endpoint=endpoint,
        seam_id="user.prompt.generate",
        operation="generate",
    )
    resolver: ProviderRouteAuthorityResolver = EMPTY_PROVIDER_ROUTE_AUTHORITY
    if record.provider_catalog_id is not None:
        try:
            preset = get_provider_preset(record.provider_catalog_id)
            get_model_variant(preset, record.model_id)
            preset_matches = (
                record.provider_kind == preset.adapter_kind
                and canonical_provider_endpoint(endpoint)
                == canonical_provider_endpoint(preset.default_base_url)
            )
        except (KeyError, ValueError):
            preset_matches = False
        if preset_matches:
            raw = getattr(app.state, "provider_route_authority", None)
            if isinstance(raw, ProviderRouteAuthorityResolver):
                resolver = raw
    return resolver.resolve(identity, provider_id=record.id)


def user_model_authority_snapshot(
    app: FastAPI,
    *,
    owner_user_id: str = _LEGACY_OWNER_USER_ID,
) -> dict[str, UserModelAuthoritySnapshot]:
    """Return one owner's non-secret current authority facts for shared inventory."""
    registry = _load_registry()
    metadata = _credential_metadata()
    seam = _seam_names(app)
    fingerprints = _registration_fingerprints(app)
    snapshots: dict[str, UserModelAuthoritySnapshot] = {}
    for record in registry.values():
        if record.owner_user_id != owner_user_id:
            continue
        route_eligible = (
            record.enabled
            and _credential_matches_record(record, metadata)
            and record.id in seam
            and fingerprints.get(record.id) == _record_fingerprint(record)
            and _live_adapter_matches(app, record.id)
        )
        authority = _route_execution_authority(app, record)
        snapshots[record.id] = UserModelAuthoritySnapshot(
            model_id=record.model_id,
            route_eligible=route_eligible,
            pricing_status=authority.pricing_status,
            hard_ceiling_eligible=route_eligible and authority.hard_ceiling_eligible,
            execution_status=(
                authority.execution_status
                if route_eligible
                else RouteExecutionStatus.BLOCKED_SELECTION_AUTHORITY
            ),
            rate_snapshot=authority.rate_snapshot,
        )
    return snapshots


def resolve_user_model_choice(
    app: FastAPI,
    choice: UserModelChoice,
    *,
    owner_user_id: str = _LEGACY_OWNER_USER_ID,
) -> ResolvedUserModelRoute:
    """Resolve one owner's prompt route without decrypting credentials or trusting cache."""
    validated = UserModelChoice.model_validate(choice.model_dump(mode="json"))
    record = _load_registry().get(validated.provider_id)
    metadata = _credential_metadata()
    fingerprints = _registration_fingerprints(app)
    if (
        record is None
        or record.owner_user_id != owner_user_id
        or not record.enabled
        or record.id != validated.provider_id
        or record.model_id != validated.model_id
        or not _credential_matches_record(record, metadata)
        or record.id not in _seam_names(app)
        or fingerprints.get(record.id) != _record_fingerprint(record)
        or not _live_adapter_matches(app, record.id)
    ):
        raise UserModelChoiceUnavailable("user model route is unavailable")
    authority = _route_execution_authority(app, record)
    return ResolvedUserModelRoute(
        authority="user_model",
        provider_id=record.id,
        model_id=record.model_id,
        credential_ref=record.cred_ref,
        pricing_status=authority.pricing_status,
        hard_ceiling_eligible=authority.hard_ceiling_eligible,
        execution_status=authority.execution_status,
        rate_snapshot=authority.rate_snapshot,
    )


class UserModelRouteResponse(BaseModel):
    authority: Literal["user_model"]
    provider_id: str
    model_id: str
    pricing_status: Literal["known", "unknown"]
    hard_ceiling_eligible: bool
    execution_status: RouteExecutionStatus
    rate_snapshot: str | None


@dataclass(frozen=True)
class _ValidatedCreate:
    provider_kind: ProviderKind
    provider_catalog_id: ProviderCatalogId | None
    model_id: str
    display_name: str
    base_url: str | None
    api_key: str


def _reject(detail: str) -> HTTPException:
    # All validation failures route through here: 422 with a message that
    # names the field but NEVER interpolates its value.
    return HTTPException(status_code=422, detail=detail)


def _parse_create(payload: object) -> _ValidatedCreate:
    if not isinstance(payload, dict):
        raise _reject("body must be a JSON object")

    provider_kind = payload.get("provider_kind")
    if provider_kind not in _PROVIDER_KINDS:
        raise _reject("provider_kind must be one of: " + ", ".join(_PROVIDER_KINDS))

    raw_catalog_id = payload.get("provider_catalog_id")
    provider_catalog_id: ProviderCatalogId | None
    if raw_catalog_id in (None, "custom"):
        provider_catalog_id = None
        preset = None
    elif isinstance(raw_catalog_id, str):
        try:
            provider_catalog_id = canonical_catalog_id(raw_catalog_id)
            preset = get_provider_preset(provider_catalog_id)
        except KeyError as exc:
            raise _reject("provider_catalog_id is not a supported preset") from exc
        if provider_kind != preset.adapter_kind:
            raise _reject("provider_kind does not match the selected provider preset")
    else:
        raise _reject("provider_catalog_id must be a string when provided")

    model_id = payload.get("model_id")
    if (
        not isinstance(model_id, str)
        or not model_id
        or len(model_id) > _MAX_MODEL_ID_LEN
        or any(c.isspace() for c in model_id)
    ):
        raise _reject("model_id must be a non-empty string without whitespace")
    if preset is not None:
        try:
            get_model_variant(preset, model_id)
        except KeyError as exc:
            raise _reject("model_id is not available for the selected provider preset") from exc

    display_name = payload.get("display_name")
    if (
        not isinstance(display_name, str)
        or not display_name.strip()
        or len(display_name) > _MAX_DISPLAY_NAME_LEN
    ):
        raise _reject("display_name must be a non-empty string (max 64 chars)")

    api_key = payload.get("api_key")
    if (
        not isinstance(api_key, str)
        or len(api_key) < _MIN_KEY_LEN
        or len(api_key) > _MAX_KEY_LEN
        or any(c.isspace() for c in api_key)
    ):
        raise _reject(
            "api_key must be a string of 8-512 characters with no "
            "whitespace (value withheld from this error by design)"
        )

    base_url = payload.get("base_url")
    if base_url is None and preset is not None:
        base_url = preset.default_base_url
    if base_url is not None:
        if (
            not isinstance(base_url, str)
            or len(base_url) > _MAX_BASE_URL_LEN
            or any(c.isspace() for c in base_url)
        ):
            raise _reject(
                "base_url must be an http(s) URL of at most 2048 characters without whitespace"
            )
        # urlsplit raises ValueError on a malformed authority (unclosed IPv6
        # bracket), and .port raises ValueError on a non-numeric port —
        # accessing both inside one try/except turns every malformed URL into
        # a clean value-free 422, never an uncaught 500.
        try:
            parts = urlsplit(base_url)
            host = parts.hostname
            _ = parts.port  # access validates a present port is numeric
        except ValueError as exc:
            raise _reject("base_url is not a well-formed URL") from exc
        # Require a real host: ``https://:443/v1`` has a truthy netloc but an
        # empty hostname, so netloc alone is not enough.
        if parts.scheme not in ("http", "https") or not host:
            raise _reject("base_url must be an http(s) URL with a host")
        # Structural credential exclusion: keys travel ONLY in api_key. A
        # userinfo / query / fragment-bearing URL could smuggle a credential
        # into the PLAINTEXT registry and into every response that echoes
        # base_url — rejected outright, value-free (the URL itself may carry
        # the secret, so it is never interpolated into the error).
        if "@" in parts.netloc or parts.query or parts.fragment:
            raise _reject(
                "base_url must be scheme + host + optional path only — no "
                "userinfo, query, or fragment (credentials go in api_key)"
            )
        if preset is not None and canonical_provider_endpoint(base_url) != (
            canonical_provider_endpoint(preset.default_base_url)
        ):
            raise _reject(
                "base_url must match the selected provider preset; use custom for another endpoint"
            )
    if provider_kind == "openai_compat" and base_url is None:
        raise _reject(
            "base_url is required for openai_compat (the provider's full "
            "base URL including any version prefix, e.g. "
            "https://api.openai.com/v1)"
        )

    return _ValidatedCreate(
        provider_kind=cast(ProviderKind, provider_kind),
        provider_catalog_id=provider_catalog_id,
        model_id=model_id,
        display_name=display_name.strip(),
        base_url=base_url,
        api_key=api_key,
    )


def _slug_id(display_name: str, owner_user_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
    if not slug:
        raise _reject("display_name must contain at least one letter or digit")
    if owner_user_id == _LEGACY_OWNER_USER_ID:
        return _ID_PREFIX + slug
    return _owner_id_prefix(owner_user_id) + slug


def _row(
    record: UserModelRecord,
    *,
    app: FastAPI,
    present: set[str],
    seam: set[str],
    fingerprints: dict[str, str],
) -> UserModelRow:
    route_eligible = (
        record.enabled
        and record.cred_ref in present
        and record.id in seam
        and fingerprints.get(record.id) == _record_fingerprint(record)
        and _live_adapter_matches(app, record.id)
    )
    authority = _route_execution_authority(app, record)
    execution_status = (
        authority.execution_status
        if route_eligible
        else RouteExecutionStatus.BLOCKED_SELECTION_AUTHORITY
    )
    return UserModelRow(
        id=record.id,
        provider_kind=record.provider_kind,
        provider_catalog_id=record.provider_catalog_id,
        model_id=record.model_id,
        display_name=record.display_name,
        base_url=record.base_url,
        enabled=record.enabled,
        key_present=record.cred_ref in present,
        registered=record.id in seam,
        route_eligible=route_eligible,
        pricing_status=authority.pricing_status,
        hard_ceiling_eligible=route_eligible and authority.hard_ceiling_eligible,
        execution_status=execution_status,
        rate_snapshot=authority.rate_snapshot,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

user_models_router = APIRouter(prefix="/settings/models/user", tags=["settings"])


@user_models_router.get("", response_model=UserModelsResponse)
def get_user_models(request: Request) -> UserModelsResponse:
    owner_user_id = request_owner_user_id(request)
    registry = _load_registry()
    owned_records = [
        record for record in registry.values() if record.owner_user_id == owner_user_id
    ]
    metadata = _credential_metadata()
    present = {
        record.cred_ref for record in owned_records if _credential_matches_record(record, metadata)
    }
    seam = _seam_names(request.app)
    fingerprints = _registration_fingerprints(request.app)
    rows = [
        _row(rec, app=request.app, present=present, seam=seam, fingerprints=fingerprints)
        for rec in sorted(owned_records, key=lambda r: r.id)
    ]
    stale = sorted(
        name
        for name in seam
        if _registered_name_belongs_to(name, owner_user_id) and name not in registry
    )
    return UserModelsResponse(models=rows, count=len(rows), stale_registered=stale)


@user_models_router.post("", response_model=UserModelRow, status_code=201)
async def post_user_model(request: Request) -> UserModelRow:
    # Manual body parse — see module docstring: FastAPI's automatic 422
    # echoes request input (the whole body on a missing-field error),
    # which would leak the api_key. Every rejection below is value-free.
    try:
        payload = await request.json()
    except ValueError as exc:
        raise _reject("body must be valid JSON") from exc
    spec = _parse_create(payload)
    owner_user_id = request_owner_user_id(request)

    record_id = _slug_id(spec.display_name, owner_user_id)
    with _registry_guard(exclusive=True):
        registry = _load_registry_unlocked()
        if record_id in registry:
            raise HTTPException(
                status_code=409,
                detail=f"user model {record_id!r} already exists; "
                "delete it first or pick another display name",
            )

        # Encrypt-at-rest FIRST, then persist the non-secret record in the
        # same registry transaction. A crash between the two orphans only
        # unreachable ciphertext, never a record with a dangling key.
        cred_ref = store_credential(
            record_id,
            spec.api_key,
            pipeline_kind=_PIPELINE_KIND,
            owner_user_id=owner_user_id,
        )
        credential = _credential_metadata().get(cred_ref)
        if credential is None:
            raise HTTPException(status_code=500, detail="credential persistence failed")
        record = UserModelRecord(
            id=record_id,
            owner_user_id=owner_user_id,
            provider_kind=spec.provider_kind,
            provider_catalog_id=spec.provider_catalog_id,
            model_id=spec.model_id,
            display_name=spec.display_name,
            base_url=spec.base_url,
            cred_ref=cred_ref,
            cred_fingerprint=credential.artifact_fingerprint,
            enabled=True,
        )
        registry[record_id] = record
        _write_registry_unlocked(registry)

        # Registration and app-local authority update remain inside the same
        # transaction, so a concurrent delete cannot resurrect a stale seam.
        adapter = _make_provider(record)
        register_provider(adapter)
        seam = _seam_names(request.app)
        seam.add(record_id)
        fingerprints = _registration_fingerprints(request.app)
        fingerprints[record_id] = _record_fingerprint(record)

        metadata = _credential_metadata()
        present = {record.cred_ref} if _credential_matches_record(record, metadata) else set()
        return _row(
            record,
            app=request.app,
            present=present,
            seam=seam,
            fingerprints=fingerprints,
        )


@user_models_router.post("/resolve", response_model=UserModelRouteResponse)
async def resolve_user_model_route(request: Request) -> UserModelRouteResponse:
    try:
        choice = UserModelChoice.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail="model choice is invalid") from None
    try:
        route = resolve_user_model_choice(
            request.app,
            choice,
            owner_user_id=request_owner_user_id(request),
        )
    except UserModelChoiceUnavailable:
        raise HTTPException(status_code=409, detail="user model route is unavailable") from None
    return UserModelRouteResponse(
        authority=route.authority,
        provider_id=route.provider_id,
        model_id=route.model_id,
        pricing_status=route.pricing_status,
        hard_ceiling_eligible=route.hard_ceiling_eligible,
        execution_status=route.execution_status,
        rate_snapshot=route.rate_snapshot,
    )


@user_models_router.delete("/{user_model_id}", response_model=UserModelDeleteResponse)
def delete_user_model(user_model_id: str, request: Request) -> UserModelDeleteResponse:
    owner_user_id = request_owner_user_id(request)
    with _registry_guard(exclusive=True):
        registry = _load_registry_unlocked()
        record = registry.get(user_model_id)
        if record is None or record.owner_user_id != owner_user_id:
            raise HTTPException(status_code=404, detail="unknown user model id")
        del registry[user_model_id]
        _write_registry_unlocked(registry)
        credential_removed = delete_credential(record.cred_ref)
        _seam_names(request.app).discard(user_model_id)
        _registration_fingerprints(request.app).pop(user_model_id, None)
    notes = [
        "credential resolution for this id now refuses and its encrypted BYOK record was removed"
    ]
    if not credential_removed:
        notes.append("the referenced encrypted credential was already absent")
    return UserModelDeleteResponse(removed=user_model_id, notes=notes)


def register_settings_models_admin_routes(app: FastAPI) -> None:
    """Mount the add-model admin routes + boot-time reload of user
    providers. Called from ``register_settings_budget_routes`` — the
    settings-local mount seam; app.py stays untouched. The reload runs as
    a startup handler because ``create_app`` assigns
    ``app.state.registered_providers`` after route registration."""
    app.include_router(user_models_router)
    from .certified_provider_credentials import (
        register_certified_provider_credential_routes,
    )

    register_certified_provider_credential_routes(app)
    # Production begins with no qualified paid route. Future provider-specific
    # bootstrap code must install exact catalog and adapter authorities here;
    # generic BYOK registration never mutates this execution authority.
    if not isinstance(
        getattr(app.state, "provider_route_authority", None),
        ProviderRouteAuthorityResolver,
    ):
        app.state.provider_route_authority = ProviderRouteAuthorityResolver(
            route_authority_catalog_entries()
        )

    def _reload_at_startup() -> None:
        reload_user_providers(app)

    # Starlette 1.x removed ``add_event_handler``/``on_event``; the router's
    # ``on_startup`` list still drains through the default lifespan, and
    # create_app passes no custom lifespan, so this is the one seam that
    # runs after ``app.state.registered_providers`` is assigned.
    app.router.on_startup.append(_reload_at_startup)


__all__ = [
    "UserModelDeleteResponse",
    "ResolvedUserModelRoute",
    "UserModelChoice",
    "UserModelChoiceUnavailable",
    "UserModelAuthoritySnapshot",
    "UserModelRecord",
    "UserModelRegistryIntegrityError",
    "UserModelRow",
    "UserModelsResponse",
    "register_settings_models_admin_routes",
    "request_owner_user_id",
    "resolve_user_model_choice",
    "user_model_authority_snapshot",
    "reload_user_providers",
    "user_models_router",
]
