"""Compact test-only composition for the quarantined source bundle store."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Never

from substrate.midnight_oil.private_source_authority import (
    OwnerPrivateEncryptedSourceBundleV1,
)
from substrate.midnight_oil.private_source_bundle_store import (
    OwnerPrivateEncryptedSourceBundleStoreV1,
)
from substrate.midnight_oil.private_source_head_store import (
    OwnerPrivateSourceAuthorityHeadV1,
)
from tests.support.owner_private_source_authority_v1 import (
    DATA_KEY_V1,
    encrypted_source_bundle,
    owner_private_source_authority_case,
)
from tests.support.owner_private_source_head_v1 import (
    OWNER_PATH_DISCRIMINATOR,
    REGISTRY_ID,
    empty_floor,
    head_verification_keys,
)
from tests.support.owner_private_v2 import (
    OwnerPrivateV2Case,
    owner_private_v2_case,
    owner_private_v2_planner_case,
)

KEY_VERSION = "opskv1_test-source-v1"
WRONG_DATA_KEY = bytes(value ^ 0x91 for value in range(32))


class OpaqueOwnerPathAuthority:
    """Identity-only stand-in for an already-authenticated owner path."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "OpaqueOwnerPathAuthority(redacted=True)"

    def __reduce__(self) -> Never:
        raise TypeError("owner path authority is process-local")

    def __copy__(self) -> Never:
        raise TypeError("owner path authority is process-local")

    def __deepcopy__(self, memo: object) -> Never:
        raise TypeError("owner path authority is process-local")


class _ClearingKeyContext(AbstractContextManager[bytearray]):
    def __init__(self, provider: ClearingTestSourceKeyProvider, key: bytes) -> None:
        self._provider = provider
        self._key = key
        self._opened: bytearray | None = None

    def __enter__(self) -> bytearray:
        opened = bytearray(self._key)
        self._opened = opened
        self._provider.opened_buffers.append(opened)
        return opened

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        opened = self._opened
        if opened is not None:
            opened[:] = b"\x00" * len(opened)
            self._provider.cleared_snapshots.append(bytes(opened))
        self._opened = None


@dataclass(slots=True)
class ClearingTestSourceKeyProvider:
    expected_authority: object
    owner_path_discriminator: str = OWNER_PATH_DISCRIMINATOR
    keys: dict[str, bytes] = field(default_factory=lambda: {KEY_VERSION: DATA_KEY_V1})
    calls: list[tuple[int, str, str]] = field(default_factory=list)
    opened_buffers: list[bytearray] = field(default_factory=list)
    cleared_snapshots: list[bytes] = field(default_factory=list)

    def open_aes256gcm_key(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        key_version: str,
    ) -> AbstractContextManager[bytearray]:
        self.calls.append((id(owner_path_authority), owner_path_discriminator, key_version))
        key = self.keys.get(key_version)
        if (
            owner_path_authority is not self.expected_authority
            or owner_path_discriminator != self.owner_path_discriminator
            or key is None
        ):
            raise ValueError("test source key is unavailable")
        return _ClearingKeyContext(self, key)

    def assert_all_opened_keys_cleared(self) -> None:
        assert self.opened_buffers
        assert all(buffer == bytearray(32) for buffer in self.opened_buffers)
        assert all(snapshot == b"\x00" * 32 for snapshot in self.cleared_snapshots)


@dataclass(frozen=True, slots=True)
class OwnerPrivateSourceBundleStoreCase:
    predecessor: OwnerPrivateV2Case
    bundle: OwnerPrivateEncryptedSourceBundleV1
    floor: OwnerPrivateSourceAuthorityHeadV1
    authority: OpaqueOwnerPathAuthority
    key_provider: ClearingTestSourceKeyProvider
    store: OwnerPrivateEncryptedSourceBundleStoreV1

    @property
    def receipt_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (receipt.receipt_id, receipt.receipt_sha256)
            for receipt in self.bundle.receipt_v5_roster
        )


def owner_private_source_bundle_store_case(
    root: Path,
    *,
    planner: bool = False,
) -> OwnerPrivateSourceBundleStoreCase:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    predecessor = owner_private_v2_planner_case() if planner else owner_private_v2_case()
    bundle = encrypted_source_bundle(predecessor)
    floor = empty_floor()
    authority = OpaqueOwnerPathAuthority()
    key_provider = ClearingTestSourceKeyProvider(authority)
    creation = owner_private_source_authority_case()
    store = OwnerPrivateEncryptedSourceBundleStoreV1(
        root / "source-authority.sqlite3",
        owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
        registry_id=REGISTRY_ID,
        trusted_floor_sha256=floor.head_sha256,
        creation_anchor_verification_keys=creation.anchor_verification_keys,
        source_head_verification_keys=head_verification_keys(),
        key_provider=key_provider,
    )
    return OwnerPrivateSourceBundleStoreCase(
        predecessor=predecessor,
        bundle=bundle,
        floor=floor,
        authority=authority,
        key_provider=key_provider,
        store=store,
    )


__all__ = [
    "KEY_VERSION",
    "WRONG_DATA_KEY",
    "ClearingTestSourceKeyProvider",
    "OpaqueOwnerPathAuthority",
    "OwnerPrivateSourceBundleStoreCase",
    "owner_private_source_bundle_store_case",
]
