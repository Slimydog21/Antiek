"""Owner-qualified authority and storage identity for the engagement spine."""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field

from substrate.research_artifact.authority import identity_digest

ENGAGEMENT_AUTHORITY_VERSION = 1
LOCAL_OPERATOR_ACCOUNT = "__operator__"


def _valid(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\x00" in value
        or len(value.encode("utf-8")) > 512
    ):
        raise ValueError(f"{field_name} is invalid")
    return value


@dataclass(frozen=True)
class EngagementAuthority:
    """One authenticated account's authority over engagement records."""

    account_id: str
    local_operator_compatibility: bool = field(default=False, repr=False)
    account_digest: str = field(init=False)
    key_id: str = field(init=False)

    def __post_init__(self) -> None:
        account_id = _valid(self.account_id, "account_id")
        if not isinstance(self.local_operator_compatibility, bool):
            raise ValueError("local operator compatibility is invalid")
        if self.local_operator_compatibility and account_id != LOCAL_OPERATOR_ACCOUNT:
            raise ValueError("local operator compatibility account is invalid")
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(
            self, "account_digest", identity_digest("engagement-account", account_id)
        )
        object.__setattr__(self, "key_id", identity_digest("engagement-key-generation", "v1"))

    def display_digest(self, kind: str, display_id: str) -> str:
        kind = _valid(kind, "engagement kind")
        display_id = _valid(display_id, f"{kind}_id")
        return identity_digest(f"engagement-{kind}", f"{self.account_digest}:{display_id}")

    def storage_id(self, kind: str, display_id: str) -> str:
        return f"e{ENGAGEMENT_AUTHORITY_VERSION}-{self.display_digest(kind, display_id)}"

    def owns_digest(self, candidate: object) -> bool:
        return isinstance(candidate, str) and hmac.compare_digest(candidate, self.account_digest)


def operator_engagement_authority() -> EngagementAuthority:
    return EngagementAuthority(LOCAL_OPERATOR_ACCOUNT, local_operator_compatibility=True)


def owner_qualified_id(authority: EngagementAuthority, kind: str, *identity_parts: str) -> str:
    cleaned = [_valid(part, f"{kind}_identity") for part in identity_parts]
    return f"{kind}_{authority.display_digest(kind, chr(0x1F).join(cleaned))[:24]}"


__all__ = [
    "ENGAGEMENT_AUTHORITY_VERSION",
    "EngagementAuthority",
    "LOCAL_OPERATOR_ACCOUNT",
    "operator_engagement_authority",
    "owner_qualified_id",
]
