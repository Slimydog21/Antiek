from __future__ import annotations

import json
import ssl
from pathlib import Path
from typing import Any

import pytest

import acquisition.arxiv.midnight_oil as connector_module
from acquisition.arxiv.midnight_oil import (
    ArxivAbstractPublicationAcquirer,
    DestinationAuditEvent,
    _PinnedHTTPSConnection,
    _public_addresses,
    strict_ssl_context,
)
from substrate.engagement_spine.source_refs import parse_source_reference
from substrate.midnight_oil.publication_capability import (
    ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256,
    PUBLICATION_RIGHTS_POLICY_SHA256,
    PublicationCapabilityRegistry,
    load_publication_capability,
    require_pinned_publication_capability,
    signed_publication_capability,
)
from substrate.midnight_oil.publication_sources import build_reviewed_publication_manifest

_KEY = b"publication-capability-test-key!!"


def _capability(*, not_before_ms: int = 1_000, expires_at_ms: int = 5_000_000):
    return signed_publication_capability(
        {
            "schema_version": 1,
            "capability_id": "midnight-oil-arxiv-abstract-v1",
            "connector_id": "acquisition.arxiv.atom",
            "connector_version": "midnight-oil-arxiv-abstract-v1",
            "adapter_contract_sha256": ARXIV_ABSTRACT_ADAPTER_CONTRACT_SHA256,
            "source_kind": "arxiv",
            "acquisition_mode": "arxiv_abstract",
            "extraction_mode": "metadata_abstract",
            "rights_policy_id": "antiek-publication-research-v1",
            "rights_policy_sha256": PUBLICATION_RIGHTS_POLICY_SHA256,
            "allowed_rights_tiers": ("T1",),
            "scheme": "https",
            "host": "export.arxiv.org",
            "port": 443,
            "path": "/api/query",
            "request_mode": "id_list_single",
            "redirect_policy": "deny",
            "proxy_policy": "deny",
            "dns_policy": "resolve-on-connect-public-only-v1",
            "tls_policy": "system-ca-hostname-tls12-v1",
            "rate_governor_id": "arxiv-host-global-v1",
            "max_response_bytes": 256_000,
            "max_excerpt_bytes": 32_000,
            "timeout_ms": 15_000,
            "issued_at_ms": 0,
            "not_before_ms": not_before_ms,
            "expires_at_ms": expires_at_ms,
            "evidence_ref": "urn:test:arxiv-fixed-egress-review",
        },
        key_id="publication-key",
        signing_key=_KEY,
    )


def _manifest():
    return build_reviewed_publication_manifest(
        [parse_source_reference("arxiv:1706.03762").to_dict()]
    )


def _acquirer(**kwargs: Any) -> ArxivAbstractPublicationAcquirer:
    return ArxivAbstractPublicationAcquirer(
        _capability(), clock_ms=lambda: 2_000, **kwargs
    )


def _atom(*, arxiv_id: str = "1706.03762", license_uri: str | None = None) -> bytes:
    license_xml = (
        ""
        if license_uri is None
        else f"<arxiv:license>{license_uri}</arxiv:license>"
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>https://arxiv.org/abs/{arxiv_id}v1</id>
    <updated>2024-01-01T00:00:00Z</updated><published>2024-01-01T00:00:00Z</published>
    <title>Reviewed paper</title><summary>Bounded reviewed abstract.</summary>
    <author><name>Researcher</name></author><category term="cs.AI" />
    {license_xml}
  </entry>
</feed>""".encode()


def test_signed_capability_loads_by_exact_hash_and_tamper_fails(tmp_path: Path) -> None:
    capability = _capability()
    path = tmp_path / "publication-capability.json"
    path.write_text(capability.model_dump_json(), encoding="utf-8")
    loaded = load_publication_capability(
        path, verification_keys={"publication-key": _KEY}
    )
    assert loaded == capability
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["timeout_ms"] = 14_000
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="hash conflicts"):
        load_publication_capability(path, verification_keys={"publication-key": _KEY})


def test_registry_rejects_not_yet_valid_expired_and_insufficient_horizon() -> None:
    manifest = _manifest()
    capability = _capability(not_before_ms=1_000, expires_at_ms=10_000)
    registry = PublicationCapabilityRegistry((capability,))
    assert registry.select(manifest, now_ms=999, required_until_ms=2_000) is None
    assert registry.select(manifest, now_ms=1_000, required_until_ms=10_000) is None
    assert registry.select(manifest, now_ms=1_000, required_until_ms=10_001) is None
    assert registry.select(manifest, now_ms=10_000, required_until_ms=10_000) is None
    assert registry.select(manifest, now_ms=1_000, required_until_ms=9_999) == capability
    with pytest.raises(ValueError, match="outside authority"):
        require_pinned_publication_capability(
            registry,
            capability_sha256=capability.capability_sha256,
            manifest=manifest,
            now_ms=10_000,
            required_until_ms=10_000,
        )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.1.1",
        "0.0.0.0",
        "224.0.0.1",
        "192.0.2.1",
        "::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_dns_non_public_and_mapped_private_answers_fail_closed(address: str) -> None:
    with pytest.raises(ValueError, match="non-public"):
        _public_addresses((address,))
    with pytest.raises(ValueError, match="non-public"):
        _public_addresses(("8.8.8.8", address))


def test_pinned_connection_resolves_once_dials_numeric_peer_and_preserves_sni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolutions = 0
    dials: list[str] = []
    sni: list[str] = []

    class FakeSocket:
        def getpeername(self):  # type: ignore[no-untyped-def]
            return ("8.8.8.8", 443)

        def close(self) -> None:
            pass

    class FakeContext:
        def wrap_socket(self, raw, *, server_hostname):  # type: ignore[no-untyped-def]
            sni.append(server_hostname)
            return raw

    def resolver(host: str, port: int) -> tuple[str, ...]:
        nonlocal resolutions
        assert (host, port) == ("export.arxiv.org", 443)
        resolutions += 1
        if resolutions > 1:
            return ("127.0.0.1",)
        return ("8.8.8.8",)

    def dialer(address: str, port: int, timeout_s: float):  # type: ignore[no-untyped-def]
        assert port == 443 and timeout_s == 15
        dials.append(address)
        return FakeSocket()

    monkeypatch.setattr(connector_module, "strict_ssl_context", lambda: FakeContext())
    connection = _PinnedHTTPSConnection(
        capability=_capability(),
        resolver=resolver,
        dialer=dialer,
        on_destination=lambda _addresses, _selected: None,
    )
    connection.connect()
    assert resolutions == 1
    assert dials == ["8.8.8.8"]
    assert sni == ["export.arxiv.org"]


def test_peer_mismatch_closes_before_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = False

    class FakeSocket:
        def getpeername(self):  # type: ignore[no-untyped-def]
            return ("1.1.1.1", 443)

        def close(self) -> None:
            nonlocal closed
            closed = True

    class FakeContext:
        def wrap_socket(self, raw, *, server_hostname):  # type: ignore[no-untyped-def]
            raise AssertionError("TLS must not start for a mismatched peer")

    monkeypatch.setattr(connector_module, "strict_ssl_context", lambda: FakeContext())
    connection = _PinnedHTTPSConnection(
        capability=_capability(),
        resolver=lambda _host, _port: ("8.8.8.8",),
        dialer=lambda _address, _port, _timeout: FakeSocket(),
        on_destination=lambda _addresses, _selected: None,
    )
    with pytest.raises(ValueError, match="peer conflicts"):
        connection.connect()
    assert closed is True


class _FakeResponse:
    def __init__(
        self,
        status: int,
        body: bytes,
        *,
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self._headers = headers or [("Content-Type", "application/atom+xml")]

    def getheaders(self) -> list[tuple[str, str]]:
        return self._headers

    def read(self, amount: int) -> bytes:
        return self._body[:amount]


def _install_fake_connection(
    monkeypatch: pytest.MonkeyPatch,
    response: _FakeResponse,
    requests: list[tuple[str, str]],
) -> None:
    class FakeConnection:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def request(
            self, method: str, target: str, *, headers: dict[str, str]
        ) -> None:
            assert headers["Accept-Encoding"] == "identity"
            requests.append((method, target))

        def getresponse(self) -> _FakeResponse:
            return response

        def close(self) -> None:
            pass

    monkeypatch.setattr(connector_module, "_PinnedHTTPSConnection", FakeConnection)
    monkeypatch.setattr(connector_module, "governed_request", lambda send: send())


def test_redirect_is_terminal_and_location_is_never_followed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, str]] = []
    response = _FakeResponse(
        302,
        b"",
        headers=[
            ("Content-Type", "application/atom+xml"),
            ("Location", "http://127.0.0.1/private"),
        ],
    )
    _install_fake_connection(monkeypatch, response, requests)
    acquirer = _acquirer()
    with pytest.raises(ValueError, match="non-success"):
        acquirer(_manifest().sources[0])
    assert len(requests) == 1


def test_fixed_connector_derives_t1_and_records_bounded_abstract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, str]] = []
    response = _FakeResponse(
        200,
        _atom(license_uri="https://creativecommons.org/licenses/by/4.0/"),
    )
    _install_fake_connection(monkeypatch, response, requests)
    audits: list[DestinationAuditEvent] = []
    acquirer = _acquirer(audit=audits.append)
    result = acquirer(_manifest().sources[0])
    assert result.rights_tier == "T1"
    assert result.text == "Bounded reviewed abstract."
    assert result.publication_capability_sha256 == _capability().capability_sha256
    assert requests == [("GET", "/api/query?id_list=1706.03762&max_results=1")]
    assert audits[-1].result == "transport_succeeded"
    assert not hasattr(audits[-1], "reviewed_ref_id")


def test_capability_is_rechecked_after_governor_wait_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, str]] = []
    _install_fake_connection(
        monkeypatch,
        _FakeResponse(
            200,
            _atom(license_uri="https://creativecommons.org/licenses/by/4.0/"),
        ),
        requests,
    )
    now = [2_000]

    def governor_wait(send):  # type: ignore[no-untyped-def]
        now[0] = 5_000_000
        return send()

    monkeypatch.setattr(connector_module, "governed_request", governor_wait)
    acquirer = ArxivAbstractPublicationAcquirer(
        _capability(), clock_ms=lambda: now[0]
    )
    with pytest.raises(ValueError, match="not currently valid"):
        acquirer(_manifest().sources[0])
    assert requests == []


def test_every_manifest_source_rechecks_capability_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, str]] = []
    _install_fake_connection(
        monkeypatch,
        _FakeResponse(
            200,
            _atom(license_uri="https://creativecommons.org/licenses/by/4.0/"),
        ),
        requests,
    )
    acquirer = _acquirer()
    checks = 0

    def expires_before_second_source() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise ValueError("capability expired between sources")

    source = _manifest().sources[0]
    acquirer(source, before_transport=expires_before_second_source)
    with pytest.raises(ValueError, match="expired between sources"):
        acquirer(source, before_transport=expires_before_second_source)
    assert checks == 2
    assert len(requests) == 1


def test_registry_allows_overlap_for_rotation_and_preserves_old_exact_hash() -> None:
    manifest = _manifest()
    old = _capability(expires_at_ms=10_000)
    new = _capability(expires_at_ms=20_000)
    registry = PublicationCapabilityRegistry((old, new))
    assert registry.get(old.capability_sha256) == old
    assert registry.get(new.capability_sha256) == new
    assert registry.select(manifest, now_ms=1_000, required_until_ms=9_000) == new


def test_wrong_identity_unknown_rights_and_oversize_fail_before_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _manifest().sources[0]
    for response, match in (
        (_FakeResponse(200, _atom(arxiv_id="2401.00001")), "identity conflicts"),
        (_FakeResponse(200, _atom()), "rights tier"),
        (
            _FakeResponse(
                200,
                b"x",
                headers=[
                    ("Content-Type", "application/atom+xml"),
                    ("Content-Length", "999999"),
                ],
            ),
            "byte cap",
        ),
    ):
        requests: list[tuple[str, str]] = []
        _install_fake_connection(monkeypatch, response, requests)
        with pytest.raises(ValueError, match=match):
            _acquirer()(source)
        assert len(requests) == 1


def test_ssl_context_is_strict_and_ignores_ambient_ca_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SSL_CERT_FILE", "/tmp/hostile-ca.pem")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    context = strict_ssl_context()
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
