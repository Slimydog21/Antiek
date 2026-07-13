from __future__ import annotations

import pytest

from tests.support.owner_private_dispatch import (
    PrivateTransportResponseFixture,
    invoke_test_transport_once,
)
from tests.test_midnight_oil_private_dispatch_boundary import _prepare
from tests.test_midnight_oil_private_provider_authority import _registry


@pytest.mark.xfail(
    strict=True,
    reason="11B-F must add a linearizable admitted-before-revocation protocol",
)
def test_provider_revocation_after_validation_must_prevent_future_transport() -> None:
    prepared, composition = _prepare()
    capability_sha256 = prepared.source_receipts[0].provider_capability_sha256
    composition.registry = _registry(revoked=(capability_sha256,))
    calls: list[bytes] = []

    def spy(request: bytes) -> PrivateTransportResponseFixture:
        calls.append(request)
        return PrivateTransportResponseFixture(
            provider_id=prepared.descriptor.provider_id,
            model_id=prepared.descriptor.model_id,
            route_key=prepared.descriptor.route_key,
            output_text="must not cross after revocation",
        )

    invoke_test_transport_once(prepared, spy)
    assert calls == []
