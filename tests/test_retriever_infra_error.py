"""nygard SPR-02 M3/M5: the typed infra error + the expected-vs-infra helper.

RetrieverInfraError is the fail-loud carrier (I-LOUD): an unexpected infra fault
surfaces typed instead of being silently masked. is_expected_degradation draws
the one canonical line between expected (benign) degradations and infra faults.
"""

from __future__ import annotations

import errno

import pytest

from substrate.errors import RetrieverInfraError, is_expected_degradation
from substrate.results import Err, is_err


def test_construction_carries_seam_errno_and_cause():
    cause = OSError(errno.EROFS, "Read-only file system", "/scratch/vss_index.duckdb")
    err = RetrieverInfraError("vss index copy failed", seam="retrieval.vss_copy", cause=cause)
    assert err.seam == "retrieval.vss_copy"
    assert err.errno == errno.EROFS
    assert err.cause is cause
    assert "retrieval.vss_copy" in str(err)
    assert "errno=30" in str(err)  # EROFS is 30


def test_chaining_preserves_cause_via_raise_from():
    cause = OSError(errno.EROFS, "Read-only file system", "/x")
    with pytest.raises(RetrieverInfraError) as ei:
        raise RetrieverInfraError("copy failed", seam="s", cause=cause) from cause
    assert ei.value.__cause__ is cause
    assert ei.value.errno == errno.EROFS


def test_composes_with_result_as_err_payload():
    err = RetrieverInfraError("boom", seam="s")
    r = Err(error=err)
    assert is_err(r)
    assert r.error is err


def test_is_expected_degradation_infra_vs_expected():
    # Infra faults are NOT expected degradations.
    assert is_expected_degradation(OSError(errno.EROFS, "ro", "/x")) is False
    assert is_expected_degradation(RetrieverInfraError("x", seam="s")) is False
    # Named expected conditions ARE.
    from substrate.dispatch.base import ProviderError

    assert is_expected_degradation(
        ProviderError("no key", provider="p", model="m", latency_ms=0)
    ) is True
    assert is_expected_degradation(KeyError("unregistered provider")) is True

    from roles.evidence_retriever import EvidenceValidationError

    assert is_expected_degradation(EvidenceValidationError("bad shape")) is True
