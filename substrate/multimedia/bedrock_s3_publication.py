"""Exact, immutable S3 object-version publication for Bedrock batch inputs."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from substrate.multimedia.bedrock_workload_bound import BedrockBatchWorkloadBound

_SHA256 = re.compile(r"[0-9a-f]{64}")
_BUCKET = re.compile(r"(?!\d+\.\d+\.\d+\.\d+$)(?!.*\.\.)[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")
_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+=,@-]{0,255}")


class S3PublicationClient(Protocol):
    def get_bucket_versioning(self, **request: object) -> Mapping[str, object]: ...
    def get_object_lock_configuration(self, **request: object) -> Mapping[str, object]: ...
    def put_object(self, **request: object) -> Mapping[str, object]: ...
    def head_object(self, **request: object) -> Mapping[str, object]: ...


class BedrockS3PublicationError(RuntimeError):
    """S3 publication evidence was absent, ambiguous, or contradictory."""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0) or value.microsecond:
        raise ValueError("timestamps must be whole-second UTC datetimes")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise ValueError("timestamp must be canonical whole-second UTC text")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if _timestamp(parsed) != value:
        raise ValueError("timestamp must be canonical whole-second UTC text")
    return parsed


@dataclass(frozen=True)
class BedrockS3PublicationProfile:
    bucket: str
    prefix: str
    expected_owner: str
    region: str
    retention_margin_hours: int
    profile_version: str
    namespace_policy_digest: str

    def __post_init__(self) -> None:
        if _BUCKET.fullmatch(self.bucket) is None or "--x-s3" in self.bucket:
            raise ValueError("bucket must be a general-purpose DNS bucket name")
        if (
            not isinstance(self.prefix, str)
            or not self.prefix
            or len(self.prefix.encode()) > 512
            or self.prefix.startswith("/")
            or not self.prefix.endswith("/")
            or any(part in {"", ".", ".."} for part in self.prefix.removesuffix("/").split("/"))
        ):
            raise ValueError("prefix must be a bounded server-owned key prefix ending in /")
        if re.fullmatch(r"\d{12}", self.expected_owner) is None:
            raise ValueError("expected_owner must be a 12-digit AWS account")
        if re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", self.region) is None:
            raise ValueError("region must be a canonical AWS region")
        if isinstance(self.retention_margin_hours, bool) or not 1 <= self.retention_margin_hours <= 24 * 365:
            raise ValueError("retention_margin_hours must be between 1 and 8760")
        if not isinstance(self.profile_version, str) or _TEXT.fullmatch(self.profile_version) is None:
            raise ValueError("profile_version must be bounded canonical text")
        if _SHA256.fullmatch(self.namespace_policy_digest) is None:
            raise ValueError("namespace_policy_digest must be a lowercase SHA-256")

    @property
    def owner_digest(self) -> str:
        return hashlib.sha256(self.expected_owner.encode("ascii")).hexdigest()

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class BedrockS3VersionPublicationReceipt:
    workload_bound_digest: str
    workload_sha256: str
    workload_byte_length: int
    profile_digest: str
    bucket: str
    key: str
    uri: str
    owner_digest: str
    checksum_sha256_base64: str
    version_id: str
    object_lock_mode: str
    retain_until: str
    namespace_policy_digest: str
    verified_at: str
    version_immutable: bool = True
    current_at_verification: bool = True
    bedrock_version_selected: bool = False

    def __post_init__(self) -> None:
        for name in ("workload_bound_digest", "workload_sha256", "profile_digest", "owner_digest", "namespace_policy_digest"):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"{name} must be a lowercase SHA-256")
        if isinstance(self.workload_byte_length, bool) or not 1 <= self.workload_byte_length <= 1_000_000_000:
            raise ValueError("workload_byte_length is outside the publication bound")
        if _BUCKET.fullmatch(self.bucket) is None or not self.key or len(self.key.encode()) > 1024:
            raise ValueError("receipt bucket/key is invalid")
        if self.uri != f"s3://{self.bucket}/{self.key}":
            raise ValueError("receipt URI must exactly bind bucket and key")
        try:
            checksum = base64.b64decode(self.checksum_sha256_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("checksum must be exact Base64 SHA-256") from exc
        if len(checksum) != 32 or base64.b64encode(checksum).decode("ascii") != self.checksum_sha256_base64:
            raise ValueError("checksum must be exact Base64 SHA-256")
        if not isinstance(self.version_id, str) or not self.version_id or len(self.version_id) > 1024:
            raise ValueError("version_id must be bounded non-null text")
        if self.object_lock_mode != "COMPLIANCE":
            raise ValueError("publication requires COMPLIANCE Object Lock")
        if _parse_timestamp(self.retain_until) <= _parse_timestamp(self.verified_at):
            raise ValueError("retention must extend beyond verification")
        if self.version_immutable is not True or self.current_at_verification is not True:
            raise ValueError("receipt must attest immutable and current-at-verification")
        if self.bedrock_version_selected is not False:
            raise ValueError("Bedrock version selection must remain explicitly unproven")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, raw: str) -> BedrockS3VersionPublicationReceipt:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("publication receipt must be canonical JSON") from exc
        if not isinstance(value, dict) or _canonical(value) != raw or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("publication receipt must be exact canonical JSON")
        return cls(**value)


class BedrockS3VersionPublisher:
    """Explicitly injected, single-part conditional S3 publisher."""

    def __init__(self, client: S3PublicationClient, profile: BedrockS3PublicationProfile) -> None:
        self.client = client
        self.profile = profile

    def publish(
        self, *, workload_bound: BedrockBatchWorkloadBound, workload_bytes: bytes,
        verified_at: datetime, bedrock_timeout_hours: int,
    ) -> BedrockS3VersionPublicationReceipt:
        workload_bound.verify_workload_bytes(workload_bytes)
        if not 1 <= len(workload_bytes) <= 1_000_000_000:
            raise ValueError("workload body is outside the single-part publication bound")
        if isinstance(bedrock_timeout_hours, bool) or not 24 <= bedrock_timeout_hours <= 168:
            raise ValueError("bedrock_timeout_hours must be between 24 and 168")
        verified = _timestamp(verified_at)
        retain_until_dt = verified_at + timedelta(
            hours=bedrock_timeout_hours + self.profile.retention_margin_hours
        )
        retain_until = _timestamp(retain_until_dt)
        self._verify_bucket()
        key = f"{self.profile.prefix}{workload_bound.workload_sha256}/manifest.jsonl"
        checksum = base64.b64encode(hashlib.sha256(workload_bytes).digest()).decode("ascii")
        request = {
            "Bucket": self.profile.bucket, "Key": key, "Body": workload_bytes,
            "ExpectedBucketOwner": self.profile.expected_owner,
            "ContentType": "application/json", "ChecksumAlgorithm": "SHA256",
            "ChecksumSHA256": checksum, "IfNoneMatch": "*",
            "ObjectLockMode": "COMPLIANCE", "ObjectLockRetainUntilDate": retain_until_dt,
        }
        response: Mapping[str, object] | None = None
        try:
            response = self.client.put_object(**request)
        except Exception as exc:
            status = self._status(exc)
            ambiguous_transport = isinstance(exc, (TimeoutError, ConnectionError, OSError))
            if status != 412 and not (
                isinstance(status, int) and status >= 500
            ) and not ambiguous_transport:
                raise BedrockS3PublicationError("conditional publication did not produce adoptable evidence") from exc
        if response is not None:
            if response.get("ChecksumSHA256") != checksum or not response.get("VersionId"):
                raise BedrockS3PublicationError("PUT response omitted exact checksum or version")
            version_id = str(response["VersionId"])
        else:
            current = self._head(key)
            version_id = self._validate_head(current, key, checksum, len(workload_bytes), retain_until)
        receipt = self._receipt(workload_bound, key, checksum, version_id, retain_until, verified)
        return self.verify(receipt)

    def verify(self, receipt: BedrockS3VersionPublicationReceipt) -> BedrockS3VersionPublicationReceipt:
        if receipt.profile_digest != self.profile.digest or receipt.owner_digest != self.profile.owner_digest:
            raise BedrockS3PublicationError("receipt conflicts with injected publication profile")
        if receipt.namespace_policy_digest != self.profile.namespace_policy_digest:
            raise BedrockS3PublicationError("receipt namespace policy conflicts")
        expected_key = f"{self.profile.prefix}{receipt.workload_sha256}/manifest.jsonl"
        if (
            receipt.bucket != self.profile.bucket
            or receipt.key != expected_key
            or receipt.uri != f"s3://{self.profile.bucket}/{expected_key}"
        ):
            raise BedrockS3PublicationError("receipt conflicts with server-owned publication route")
        self._verify_bucket()
        versioned = self._head(receipt.key, receipt.version_id)
        current = self._head(receipt.key)
        expected = (receipt.key, receipt.checksum_sha256_base64, receipt.workload_byte_length, receipt.retain_until)
        version = self._validate_head(versioned, *expected)
        current_version = self._validate_head(current, *expected)
        if version != receipt.version_id or current_version != receipt.version_id:
            raise BedrockS3PublicationError("exact immutable version is not the current version")
        return receipt

    def _verify_bucket(self) -> None:
        common = {"Bucket": self.profile.bucket, "ExpectedBucketOwner": self.profile.expected_owner}
        try:
            versioning = self.client.get_bucket_versioning(**common)
            lock = self.client.get_object_lock_configuration(**common)
        except Exception as exc:
            raise BedrockS3PublicationError("bucket authority could not be verified") from exc
        if versioning.get("Status") != "Enabled":
            raise BedrockS3PublicationError("bucket versioning must be enabled")
        configuration = lock.get("ObjectLockConfiguration")
        if not isinstance(configuration, Mapping) or configuration.get("ObjectLockEnabled") != "Enabled":
            raise BedrockS3PublicationError("bucket Object Lock must be enabled")

    def _head(self, key: str, version_id: str | None = None) -> Mapping[str, object]:
        request: dict[str, object] = {
            "Bucket": self.profile.bucket, "Key": key,
            "ExpectedBucketOwner": self.profile.expected_owner, "ChecksumMode": "ENABLED",
        }
        if version_id is not None:
            request["VersionId"] = version_id
        try:
            return self.client.head_object(**request)
        except Exception as exc:
            raise BedrockS3PublicationError("exact S3 HEAD evidence unavailable") from exc

    @staticmethod
    def _validate_head(head: Mapping[str, object], key: str, checksum: str, length: int, retain_until: str) -> str:
        version = head.get("VersionId")
        retain = head.get("ObjectLockRetainUntilDate")
        if isinstance(retain, datetime):
            try:
                retain = _timestamp(retain)
            except ValueError:
                retain = None
        valid = (
            isinstance(version, str) and bool(version)
            and head.get("ChecksumSHA256") == checksum
            and head.get("ChecksumType") == "FULL_OBJECT"
            and head.get("ContentLength") == length
            and head.get("ContentType") == "application/json"
            and head.get("ObjectLockMode") == "COMPLIANCE"
            and retain == retain_until
            and head.get("DeleteMarker", False) is False
        )
        if not valid:
            raise BedrockS3PublicationError(f"S3 HEAD did not exactly verify {key}")
        return version

    def _receipt(self, bound: BedrockBatchWorkloadBound, key: str, checksum: str,
                 version_id: str, retain_until: str, verified_at: str) -> BedrockS3VersionPublicationReceipt:
        return BedrockS3VersionPublicationReceipt(
            workload_bound_digest=bound.digest, workload_sha256=bound.workload_sha256,
            workload_byte_length=bound.workload_byte_length, profile_digest=self.profile.digest,
            bucket=self.profile.bucket, key=key, uri=f"s3://{self.profile.bucket}/{key}",
            owner_digest=self.profile.owner_digest, checksum_sha256_base64=checksum,
            version_id=version_id, object_lock_mode="COMPLIANCE", retain_until=retain_until,
            namespace_policy_digest=self.profile.namespace_policy_digest, verified_at=verified_at,
        )

    @staticmethod
    def _status(exc: Exception) -> int | None:
        response = getattr(exc, "response", None)
        if not isinstance(response, Mapping):
            return None
        metadata = response.get("ResponseMetadata")
        return metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None  # type: ignore[return-value]


__all__ = [
    "BedrockS3PublicationError", "BedrockS3PublicationProfile",
    "BedrockS3VersionPublicationReceipt", "BedrockS3VersionPublisher", "S3PublicationClient",
]
