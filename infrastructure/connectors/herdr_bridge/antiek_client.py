"""Narrow HTTPS client for the authenticated Antiek bridge routes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

from .config import BridgeConfig
from .models import LeaseEnvelope, StructuredResult, canonical_json


class AntiekHttpError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: object


Transport = Callable[[str, str, dict[str, str], object], HttpResponse]


def _urllib_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: object,
) -> HttpResponse:
    encoded = canonical_json(body).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise AntiekHttpError(response.status, "Antiek response exceeded 1 MiB")
            return HttpResponse(response.status, json.loads(raw))
    except urllib.error.HTTPError as exc:
        raise AntiekHttpError(exc.code, f"Antiek returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AntiekHttpError(0, "Antiek request failed") from exc


class AntiekClient:
    def __init__(self, config: BridgeConfig, *, transport: Transport = _urllib_transport) -> None:
        self._config = config
        self._transport = transport

    def _post(
        self,
        path: str,
        body: object,
        *,
        idempotency_key: str,
    ) -> object:
        headers = {
            "Authorization": (
                f"AntiekBridge {self._config.credential_id}."
                f"{self._config.credential_secret}"
            ),
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
            "User-Agent": "AntiekHerdrBridge/0.1",
        }
        response = self._transport(
            "POST",
            f"{self._config.antiek_base_url}{path}",
            headers,
            body,
        )
        if response.status != 200:
            raise AntiekHttpError(response.status, f"Antiek returned HTTP {response.status}")
        return response.body

    @staticmethod
    def _key(action: str, *parts: object) -> str:
        import hashlib

        digest = hashlib.sha256(
            canonical_json([action, *parts]).encode("utf-8")
        ).hexdigest()
        return f"herdr-bridge-{action}-{digest}"

    @staticmethod
    def _attempt_path(lease: LeaseEnvelope, action: str) -> str:
        return (
            f"/internal/agent-work/{quote(lease.work_id, safe='')}/leases/"
            f"{quote(lease.lease_id, safe='')}/{action}"
        )

    def lease(self) -> LeaseEnvelope | None:
        body = self._post(
            "/internal/agent-work/lease",
            {
                "bridge_instance_id": self._config.bridge_instance_id,
                "lease_seconds": self._config.lease_seconds,
            },
            idempotency_key=f"herdr-bridge-lease-{uuid.uuid4().hex}",
        )
        return None if body is None else LeaseEnvelope.parse(body)

    def renew(self, lease: LeaseEnvelope) -> None:
        self._post(
            self._attempt_path(lease, "renew"),
            {
                "attempt_no": lease.attempt_no,
                "lease_seconds": self._config.lease_seconds,
            },
            idempotency_key=f"herdr-bridge-renew-{uuid.uuid4().hex}",
        )

    def submitted(self, lease: LeaseEnvelope, *, target: str) -> None:
        self._post(
            self._attempt_path(lease, "submitted"),
            {
                "attempt_no": lease.attempt_no,
                "adapter_version": "herdr-bridge/0.1",
                "herdr_target_observed": target,
            },
            idempotency_key=self._key(
                "submitted", lease.work_id, lease.attempt_no, lease.lease_id, target
            ),
        )

    def acknowledged(self, lease: LeaseEnvelope, *, receipt_sha256: str) -> None:
        self._post(
            self._attempt_path(lease, "acknowledged"),
            {
                "attempt_no": lease.attempt_no,
                "transport_receipt_sha256": receipt_sha256,
            },
            idempotency_key=self._key(
                "acknowledged",
                lease.work_id,
                lease.attempt_no,
                lease.lease_id,
                receipt_sha256,
            ),
        )

    def working(self, lease: LeaseEnvelope) -> None:
        self._post(
            self._attempt_path(lease, "working"),
            {"attempt_no": lease.attempt_no},
            idempotency_key=self._key(
                "working", lease.work_id, lease.attempt_no, lease.lease_id
            ),
        )

    def result(self, result: StructuredResult) -> None:
        path = (
            f"/internal/agent-work/{quote(result.work_id, safe='')}/leases/"
            f"{quote(result.lease_id, safe='')}/result"
        )
        body: dict[str, object] = {
            "attempt_no": result.attempt_no,
            "context_sha256": result.context_sha256,
            "kind": result.kind,
        }
        if result.kind == "reply":
            body["reply_markdown"] = result.reply_markdown
        elif result.kind in {"decline", "approval_request"}:
            body["message_markdown"] = result.message_markdown
        else:
            body["error_code"] = result.error_code
            body["retryable"] = result.retryable
        self._post(
            path,
            body,
            idempotency_key=self._key(
                "result",
                result.work_id,
                result.attempt_no,
                result.lease_id,
                result.digest(),
            ),
        )


__all__ = ["AntiekClient", "AntiekHttpError", "HttpResponse"]
