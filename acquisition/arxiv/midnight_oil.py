"""Fixed-egress arXiv abstract connector for paid Midnight Oil research.

This is intentionally not a generic HTTP client.  It has one origin, one path,
one query shape, no redirects/proxies/subrequests, and resolves inside the TCP
connect boundary so a second hostname lookup cannot rebind the destination.
"""

from __future__ import annotations

import fcntl
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import time
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import certifi

from substrate.midnight_oil.publication_capability import (
    ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256,
    PublicationConnectorCapability,
)
from substrate.midnight_oil.publication_sources import (
    AcquiredPublicationExcerpt,
    ReviewedPublicationSource,
    acquired_excerpt,
)
from substrate.rights.arxiv_tiers import resolve_tier

from .client import DEFAULT_USER_AGENT, _parse_response
from .rate_governor import governed_request

_ARXIV_ID = re.compile(r"^[0-9]{4}\.[0-9]{4,5}$")
_MAX_DNS_ANSWERS = 16


class Resolver(Protocol):
    def __call__(self, host: str, port: int) -> Sequence[str]: ...


class Dialer(Protocol):
    def __call__(self, address: str, port: int, timeout_s: float) -> socket.socket: ...


@dataclass(frozen=True)
class DestinationAuditEvent:
    capability_sha256: str
    host: str
    port: int
    resolved_addresses: tuple[str, ...]
    selected_address: str | None
    result: str
    recorded_at_ms: int


class DestinationAuditSink(Protocol):
    def __call__(self, event: DestinationAuditEvent) -> None: ...


class FileDestinationAudit:
    """Bounded append-only JSONL destination audit; never records query/body."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def __call__(self, event: DestinationAuditEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(asdict(event), sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        if len(encoded) > 8_192:
            raise ValueError("publication destination audit event exceeds its bound")
        descriptor = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _normalize_address(value: str) -> str:
    address = ipaddress.ip_address(value.split("%", 1)[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.compressed


def _public_addresses(values: Sequence[str]) -> tuple[str, ...]:
    if not values or len(values) > _MAX_DNS_ANSWERS:
        raise ValueError("arXiv DNS answer count is outside the connector contract")
    normalized: list[str] = []
    for raw in values:
        try:
            address = ipaddress.ip_address(_normalize_address(raw))
        except ValueError as exc:
            raise ValueError("arXiv DNS returned an invalid address") from exc
        if (
            not address.is_global
            or address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            # Reject the entire answer set. Filtering a private member out of a
            # mixed response would hide a compromised/rebinding resolver signal.
            raise ValueError("arXiv DNS returned a non-public destination")
        normalized.append(address.compressed)
    return tuple(sorted(set(normalized), key=lambda item: (":" in item, item)))


def system_resolver(host: str, port: int) -> tuple[str, ...]:
    answers = socket.getaddrinfo(
        host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    return tuple(str(row[4][0]) for row in answers)


def system_dialer(address: str, port: int, timeout_s: float) -> socket.socket:
    return socket.create_connection((address, port), timeout=timeout_s)


def strict_ssl_context() -> ssl.SSLContext:
    # An explicit certifi bundle prevents SSL_CERT_FILE/SSL_CERT_DIR from
    # changing this connector's trust roots through ambient process state.
    context = ssl.create_default_context(cafile=certifi.where())
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        *,
        capability: PublicationConnectorCapability,
        resolver: Resolver,
        dialer: Dialer,
        on_destination: Callable[[tuple[str, ...], str], None],
    ) -> None:
        context = strict_ssl_context()
        timeout_s = capability.timeout_ms / 1000
        super().__init__(
            capability.host,
            capability.port,
            timeout=timeout_s,
            context=context,
        )
        self._capability = capability
        self._resolver = resolver
        self._dialer = dialer
        self._on_destination = on_destination
        self._strict_context = context
        self._timeout_s = timeout_s

    def connect(self) -> None:
        if (
            self.host != "export.arxiv.org"
            or self.port != 443
            or getattr(self, "_tunnel_host", None) is not None
        ):
            raise ValueError("arXiv connector origin escaped its fixed authority")
        addresses = _public_addresses(self._resolver(self.host, self.port))
        selected = addresses[0]
        self._on_destination(addresses, selected)
        raw = self._dialer(selected, self.port, self._timeout_s)
        try:
            peer = _normalize_address(str(raw.getpeername()[0]))
            if peer != selected:
                raise ValueError("arXiv connected peer conflicts with the vetted destination")
            # The socket is numeric-IP pinned, while TLS still authenticates and
            # sends SNI for the fixed hostname.
            self.sock = self._strict_context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class _GovernedResponse:
    def __init__(self, status_code: int, headers: Mapping[str, str], content: bytes) -> None:
        self.status_code = status_code
        self._headers = headers
        self.content = content

    @property
    def headers(self) -> Mapping[str, str]:
        return self._headers


class ArxivAbstractPublicationAcquirer:
    """Acquire exactly one reviewed arXiv Atom abstract under one capability."""

    def __init__(
        self,
        capability: PublicationConnectorCapability,
        *,
        resolver: Resolver = system_resolver,
        dialer: Dialer = system_dialer,
        audit: DestinationAuditSink | None = None,
        clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    ) -> None:
        if capability.adapter_contract_sha256 != ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256:
            raise ValueError("arXiv adapter contract conflicts with its capability")
        self._capability = capability
        self._resolver = resolver
        self._dialer = dialer
        self._audit = audit
        self._clock_ms = clock_ms

    def _record(
        self,
        *,
        addresses: tuple[str, ...],
        selected: str | None,
        result: str,
    ) -> None:
        if self._audit is None:
            return
        self._audit(
            DestinationAuditEvent(
                capability_sha256=self._capability.capability_sha256,
                host=self._capability.host,
                port=self._capability.port,
                resolved_addresses=addresses,
                selected_address=selected,
                result=result,
                recorded_at_ms=self._clock_ms(),
            )
        )

    def _fetch(
        self,
        source: ReviewedPublicationSource,
        *,
        before_transport: Callable[[], None] | None,
    ) -> bytes:
        destination: tuple[tuple[str, ...], str | None] = ((), None)

        def on_destination(addresses: tuple[str, ...], selected: str) -> None:
            nonlocal destination
            destination = (addresses, selected)
            self._record(addresses=addresses, selected=selected, result="tcp_attempted")

        params = urllib.parse.urlencode(
            {"id_list": source.external_id, "max_results": "1"}, quote_via=urllib.parse.quote
        )
        target = f"{self._capability.path}?{params}"

        def send() -> _GovernedResponse:
            connection = _PinnedHTTPSConnection(
                capability=self._capability,
                resolver=self._resolver,
                dialer=self._dialer,
                on_destination=on_destination,
            )
            try:
                now_ms = self._clock_ms()
                if not self._capability.not_before_ms <= now_ms < self._capability.expires_at_ms:
                    raise ValueError("arXiv connector capability is not currently valid")
                if before_transport is not None:
                    before_transport()
                connection.request(
                    "GET",
                    target,
                    headers={
                        "User-Agent": DEFAULT_USER_AGENT,
                        "Accept": "application/atom+xml, application/xml;q=0.9",
                        "Accept-Encoding": "identity",
                        "Connection": "close",
                    },
                )
                response = connection.getresponse()
                headers = {key.lower(): value for key, value in response.getheaders()}
                if headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                    raise ValueError("arXiv connector refuses encoded response bodies")
                content_type = headers.get("content-type", "").lower()
                if not content_type.startswith(("application/atom+xml", "application/xml", "text/xml")):
                    raise ValueError("arXiv connector received an unexpected content type")
                declared = headers.get("content-length")
                if declared is not None and int(declared) > self._capability.max_response_bytes:
                    raise ValueError("arXiv response exceeds the capability byte cap")
                body = response.read(self._capability.max_response_bytes + 1)
                if len(body) > self._capability.max_response_bytes:
                    raise ValueError("arXiv response exceeds the capability byte cap")
                return _GovernedResponse(response.status, headers, body)
            finally:
                connection.close()

        try:
            response = governed_request(send)
            if response.status_code != 200:
                # All 3xx are terminal. Location is deliberately never parsed.
                raise ValueError("arXiv connector received a non-success status")
        except BaseException:
            self._record(
                addresses=destination[0],
                selected=destination[1],
                result="failed",
            )
            raise
        self._record(
            addresses=destination[0],
            selected=destination[1],
            result="transport_succeeded",
        )
        return response.content

    def __call__(
        self,
        source: ReviewedPublicationSource,
        *,
        before_transport: Callable[[], None] | None = None,
    ) -> AcquiredPublicationExcerpt:
        capability = self._capability
        if (
            source.kind != "arxiv"
            or source.acquisition_mode != capability.acquisition_mode
            or source.rights_use != "metadata_abstract_research"
            or source.max_excerpt_bytes > capability.max_excerpt_bytes
            or _ARXIV_ID.fullmatch(source.external_id) is None
        ):
            raise ValueError("reviewed source is outside the arXiv adapter contract")
        papers = _parse_response(self._fetch(source, before_transport=before_transport))
        if len(papers) != 1:
            raise ValueError("arXiv connector did not return exactly one reviewed paper")
        paper = papers[0]
        if (
            paper.arxiv_id != source.external_id
            or paper.abs_url != source.canonical_url
            or not paper.abstract.strip()
        ):
            raise ValueError("arXiv connector response identity conflicts")
        tier = resolve_tier(paper.license_uri).value
        if tier not in capability.allowed_rights_tiers:
            raise ValueError("arXiv abstract rights tier is outside capability authority")
        if len(paper.abstract.encode("utf-8")) > source.max_excerpt_bytes:
            raise ValueError("arXiv abstract exceeds the reviewed excerpt cap")
        return acquired_excerpt(
            source,
            text=paper.abstract,
            connector="acquisition.arxiv",
            rights_tier="T1",
            truncated=False,
            connector_version=capability.connector_version,
            source_length=len(paper.abstract.encode("utf-8")),
            publication_capability_sha256=capability.capability_sha256,
        )


__all__ = [
    "ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256",
    "ArxivAbstractPublicationAcquirer",
    "DestinationAuditEvent",
    "FileDestinationAudit",
    "strict_ssl_context",
    "system_dialer",
    "system_resolver",
]
