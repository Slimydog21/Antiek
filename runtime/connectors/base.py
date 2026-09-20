"""BYO-tools connector base + paste-a-key chassis (spec §5.0/§5.1, sprint S1).

The product story: a user connects their OWN data-vendor accounts to Antiek's
research workstation. Every v1 connector is one of three chassis kinds
(``ChassisKind``); this module ships the shared base + the **paste-a-key**
chassis, whose keyless form (``auth="none"`` — SEC EDGAR) is the degenerate
case: the same connector shape with no credential at all.

Posture, reused verbatim from the substrates the spec pins (do NOT rebuild):

  * SECRETS — ``runtime.byok.store``. A pasted key is shape-validated on input
    (length / prefix class only), then sealed via
    :func:`runtime.byok.store.store_credential` with
    ``pipeline_kind=f"connector_{vendor}"`` and held ONLY as its non-secret
    ``cred_id``. The plaintext is decrypted lazily AT CALL TIME via
    :func:`runtime.byok.store.load_credential` and surfaced as a redacting
    :class:`runtime.byok.secret_str.SecretStr` — the exact
    ``acquisition/twitter/api_client.py:81-106`` discipline. Nothing in this
    module ever logs, formats, or echoes key material; the one intentional
    plaintext egress is a greppable ``.reveal()`` at the subclass's send line.
  * SINGLE-WRITER — this module does NO DuckDB writes. Connector instance
    records (a JSON sidecar registry) and the settings API are the S1 settings
    vertical's job, not the chassis's.
  * FAIL CLOSED — a malformed key is rejected before it is stored; a connector
    whose descriptor declares no key shape (keyless) never touches the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from runtime.byok.secret_str import SecretStr
from runtime.byok.store import list_credentials, load_credential, store_credential

ChassisKind = Literal["paste_key", "oauth2_redirect", "gated_enterprise"]
AuthModel = Literal[
    "none",
    "api_key_query",
    "api_key_header",
    "bearer_token",
    "oauth2_code",
    "oauth2_pkce",
    "mcp",
]

# Hard upper bound on any pasted key, matching the settings vertical's input
# bound (interfaces/research/api/settings_models_admin.py — api_key <= 512).
KEY_MAX_LEN = 512


@dataclass(frozen=True)
class KeyShape:
    """The input-validation shape of a vendor's API key.

    Shape-only: checked on paste, never logged, never sufficient to
    reconstruct the key. ``prefix`` is the non-secret prefix CLASS a vendor's
    keys carry (e.g. a vendor whose keys all start one way); ``None`` when the
    vendor has no stable prefix (FMP per the spec census).
    """

    min_len: int
    max_len: int = KEY_MAX_LEN
    prefix: str | None = None


@dataclass(frozen=True)
class RateSpec:
    """A vendor's sliding-window rate budget — the governor's input.

    ``max_calls`` per ``window_s`` seconds, host-global across processes
    (``runtime/connectors/rate_governor.py``). EDGAR: ``(8, 1.0)`` — one notch
    under SEC's 10 req/s so bursts never trip the ~10-minute IP block.
    """

    max_calls: int
    window_s: float


@dataclass(frozen=True)
class ConnectorDescriptor:
    """The non-secret, code-resident description of one connector vendor.

    ``key_shape=None`` IS the keyless degenerate case (EDGAR): the chassis
    then stores nothing and :meth:`PasteKeyConnector.key_present` is always
    False. ``docs_url`` anchors the vendor's key-minting walkthrough.
    """

    vendor: str
    chassis: ChassisKind
    auth: AuthModel
    key_shape: KeyShape | None
    rate: RateSpec | None
    docs_url: str


class ConnectorError(RuntimeError):
    """Base for connector-chassis failures. Messages NEVER carry key material."""


class KeyShapeError(ConnectorError, ValueError):
    """A pasted key failed shape validation.

    The message describes the EXPECTED shape only (a length range, or that a
    prefix class was mismatched) — never the submitted value, so a surfaced
    error cannot leak the key (the settings_models_admin 422 bar).
    """


def validate_key_shape(descriptor: ConnectorDescriptor, api_key: str) -> None:
    """Validate one write-only key without storing or rendering its value."""
    shape = descriptor.key_shape
    if shape is None:
        raise KeyShapeError(
            f"connector {descriptor.vendor!r} is keyless (auth={descriptor.auth!r}); "
            "there is no key to attach"
        )
    if not isinstance(api_key, str) or not (shape.min_len <= len(api_key) <= shape.max_len):
        raise KeyShapeError(
            f"api_key for {descriptor.vendor!r} must be "
            f"{shape.min_len}-{shape.max_len} characters"
        )
    if shape.prefix is not None and not api_key.startswith(shape.prefix):
        raise KeyShapeError(
            f"api_key for {descriptor.vendor!r} does not match the expected prefix class"
        )


class Connector:
    """The small shared base every BYO-tools connector builds on.

    Carries the connector's :class:`ConnectorDescriptor` (a class attribute on
    the concrete connector) and nothing else — no I/O, no state. ``repr`` is
    deliberately descriptor-only so a stray log line can never carry
    credential material.
    """

    descriptor: ConnectorDescriptor  # set on the concrete subclass

    @property
    def vendor(self) -> str:
        return self.descriptor.vendor

    def __repr__(self) -> str:
        d = self.descriptor
        return f"{type(self).__name__}(vendor={d.vendor!r}, chassis={d.chassis!r}, auth={d.auth!r})"


class PasteKeyConnector(Connector):
    """The paste-a-key chassis: a connector that holds an OPTIONAL user key.

    The key is held ONLY as a non-secret ``cred_id`` into the encrypted byok
    store (see the module docstring). ``cred_id=None`` is the keyless
    degenerate case (EDGAR's ``auth="none"``): :meth:`key_present` is False
    and :meth:`_resolve_key` returns None — the subclass's send path then
    carries no credential at all.

    The ``artifact_path`` / ``key_bytes`` / ``key_file`` kwargs are the byok
    store's injection seams (tests inject a temp artifact + key bytes so no
    real key file or daemon is touched); production callers pass none.
    """

    def __init__(
        self,
        *,
        cred_id: str | None = None,
        artifact_path: str | None = None,
        key_bytes: bytes | None = None,
        key_file: str | None = None,
    ) -> None:
        self._cred_id = cred_id
        self._artifact_path = artifact_path
        self._key_bytes = key_bytes
        self._key_file = key_file

    @property
    def cred_id(self) -> str | None:
        """The non-secret store handle of the attached key (None if keyless)."""
        return self._cred_id

    def attach_key(self, api_key: str, *, account_handle: str | None = None) -> str:
        """Shape-validate ``api_key``, seal it in the byok store, return its cred_id.

        Raises :class:`KeyShapeError` (expected-shape message only, never the
        value) when the key fails the descriptor's :class:`KeyShape`. A
        connector whose descriptor is keyless (``key_shape=None``) refuses:
        attaching a key to EDGAR is a caller bug, not a stored credential.

        Stored with ``pipeline_kind=f"connector_{vendor}"`` — the byok store's
        ``pipeline_kind`` is an unconstrained ``str | None`` (verified at
        ``runtime/byok/store.py:289``), so connector kinds slot in without
        touching that module. The store is append-only: a replaced key leaves
        an honestly-orphaned ciphertext, the settings_models_admin posture.
        """
        validate_key_shape(self.descriptor, api_key)
        cred_id = store_credential(
            account_handle or f"connector-{self.vendor}",
            api_key,
            pipeline_kind=f"connector_{self.vendor}",
            artifact_path=self._artifact_path,
            key_bytes=self._key_bytes,
            key_file=self._key_file,
        )
        self._cred_id = cred_id
        return cred_id

    def key_present(self) -> bool:
        """Whether a credential for this connector exists — WITHOUT decrypting.

        Reads only :func:`runtime.byok.store.list_credentials` metadata (the
        non-secret listing); ``load_credential`` is never called here, so a
        settings/listing surface can show "key on file" with zero plaintext
        exposure. Always False for the keyless degenerate case.
        """
        if self._cred_id is None:
            return False
        return any(
            meta.cred_id == self._cred_id
            for meta in list_credentials(artifact_path=self._artifact_path)
        )

    def _resolve_key(self) -> SecretStr | None:
        """Decrypt the attached key AT CALL TIME, wrapped redacting. None if keyless.

        The ONLY caller is the subclass's send path, which reads ``.reveal()``
        scoped to the header/param line it builds — the greppable single
        egress of ``acquisition/twitter/api_client.py:104-106``. The wrapper
        (never the plaintext) is what may cross a function boundary.
        """
        if self._cred_id is None:
            return None
        return load_credential(
            self._cred_id,
            artifact_path=self._artifact_path,
            key_bytes=self._key_bytes,
            key_file=self._key_file,
        )


__all__ = [
    "AuthModel",
    "ChassisKind",
    "Connector",
    "ConnectorDescriptor",
    "ConnectorError",
    "KEY_MAX_LEN",
    "KeyShape",
    "KeyShapeError",
    "PasteKeyConnector",
    "RateSpec",
    "validate_key_shape",
]
