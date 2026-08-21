"""Strict transport models for the Herdr bridge."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal


def _record(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _string(value: object, *, label: str, maximum: int = 32768) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{label} must be a non-empty bounded string")
    return value


def _sha256(value: object, *, label: str) -> str:
    text = _string(value, label=label, maximum=64)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class LeaseEnvelope:
    work_id: str
    thread_id: str
    lease_id: str
    attempt_no: int
    logical_worker_id: str
    lease_expires_at: str
    artifact: dict[str, Any]
    anchor: dict[str, Any]
    comment_markdown: str
    context_sha256: str

    @classmethod
    def parse(cls, value: object) -> LeaseEnvelope:
        body = _record(value, label="lease")
        required = {
            "work_id",
            "thread_id",
            "lease_id",
            "attempt_no",
            "logical_worker_id",
            "lease_expires_at",
            "artifact",
            "anchor",
            "comment_markdown",
            "context_sha256",
        }
        if set(body) != required:
            raise ValueError("lease has unknown or missing fields")
        attempt_no = body["attempt_no"]
        if not isinstance(attempt_no, int) or isinstance(attempt_no, bool) or attempt_no < 1:
            raise ValueError("attempt_no must be a positive integer")
        expires_at = _string(body["lease_expires_at"], label="lease_expires_at", maximum=64)
        try:
            datetime.fromisoformat(expires_at)
        except ValueError as exc:
            raise ValueError("lease_expires_at must be ISO-8601") from exc
        artifact = _record(body["artifact"], label="artifact")
        anchor = _record(body["anchor"], label="anchor")
        if artifact.get("content_sha256") is None or artifact.get("source_sha256") is None:
            raise ValueError("artifact hashes are required")
        _sha256(artifact["content_sha256"], label="artifact.content_sha256")
        _sha256(artifact["source_sha256"], label="artifact.source_sha256")
        _sha256(anchor.get("node_text_sha256"), label="anchor.node_text_sha256")
        return cls(
            work_id=_string(body["work_id"], label="work_id", maximum=128),
            thread_id=_string(body["thread_id"], label="thread_id", maximum=128),
            lease_id=_string(body["lease_id"], label="lease_id", maximum=128),
            attempt_no=attempt_no,
            logical_worker_id=_string(
                body["logical_worker_id"], label="logical_worker_id", maximum=128
            ),
            lease_expires_at=expires_at,
            artifact=dict(artifact),
            anchor=dict(anchor),
            comment_markdown=_string(
                body["comment_markdown"], label="comment_markdown"
            ),
            context_sha256=_sha256(body["context_sha256"], label="context_sha256"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StructuredResult:
    work_id: str
    lease_id: str
    attempt_no: int
    context_sha256: str
    kind: Literal["reply", "decline", "approval_request", "failure"]
    reply_markdown: str | None = None
    message_markdown: str | None = None
    error_code: str | None = None
    retryable: bool | None = None

    @classmethod
    def parse(cls, value: object) -> StructuredResult:
        body = _record(value, label="result")
        common = {"work_id", "lease_id", "attempt_no", "context_sha256", "kind"}
        kind = body.get("kind")
        variants = {
            "reply": {"reply_markdown"},
            "decline": {"message_markdown"},
            "approval_request": {"message_markdown"},
            "failure": {"error_code", "retryable"},
        }
        if kind not in variants or set(body) != common | variants[kind]:
            raise ValueError("result has unknown, missing, or incompatible fields")
        attempt_no = body["attempt_no"]
        if not isinstance(attempt_no, int) or isinstance(attempt_no, bool) or attempt_no < 1:
            raise ValueError("attempt_no must be a positive integer")
        if kind == "failure":
            error_code = _string(body["error_code"], label="error_code", maximum=64)
            if not error_code.replace("_", "").isalnum() or not error_code.islower():
                raise ValueError("error_code must use lowercase letters, digits, or underscores")
            retryable = body["retryable"]
            if not isinstance(retryable, bool):
                raise ValueError("retryable must be a boolean")
            return cls(
                work_id=_string(body["work_id"], label="work_id", maximum=128),
                lease_id=_string(body["lease_id"], label="lease_id", maximum=128),
                attempt_no=attempt_no,
                context_sha256=_sha256(body["context_sha256"], label="context_sha256"),
                kind="failure",
                error_code=error_code,
                retryable=retryable,
            )
        message_field = "reply_markdown" if kind == "reply" else "message_markdown"
        message = _string(body[message_field], label=message_field)
        return cls(
            work_id=_string(body["work_id"], label="work_id", maximum=128),
            lease_id=_string(body["lease_id"], label="lease_id", maximum=128),
            attempt_no=attempt_no,
            context_sha256=_sha256(body["context_sha256"], label="context_sha256"),
            kind=kind,
            reply_markdown=message if kind == "reply" else None,
            message_markdown=message if kind != "reply" else None,
        )

    def to_dict(self) -> dict[str, Any]:
        body = asdict(self)
        return {key: value for key, value in body.items() if value is not None}

    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()
