"""Hypothesis strategies for substrate.results / substrate.errors.

Skips entire module if hypothesis is not installed. ARE-07 of the
Antiek Rust-Execution Spec; opt-in dep, not in pyproject direct deps.
"""

from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis not installed")
from hypothesis import strategies as st  # noqa: E402

from substrate.errors import (  # noqa: E402
    BudgetExceeded,
    SchemaMismatch,
    SubstrateError,
    UpstreamUnavailable,
    VerifierTimeout,
    WriterContended,
)
from substrate.results import Err, Ok, Result  # noqa: E402


def _budget_exceeded() -> st.SearchStrategy[BudgetExceeded]:
    return st.builds(
        BudgetExceeded,
        cap=st.integers(min_value=0, max_value=10**9),
        attempted=st.integers(min_value=0, max_value=10**9),
        units=st.sampled_from(["tokens", "usd_cents", "calls", "bytes"]),
    )


def _schema_mismatch() -> st.SearchStrategy[SchemaMismatch]:
    return st.builds(
        SchemaMismatch,
        field=st.text(min_size=1, max_size=64).filter(lambda s: s.strip()),
        expected_type=st.sampled_from(["int", "str", "float", "bool", "list", "dict"]),
        actual_repr=st.text(max_size=200),
        schema_version=st.integers(min_value=0, max_value=99),
    )


def _upstream_unavailable() -> st.SearchStrategy[UpstreamUnavailable]:
    return st.builds(
        UpstreamUnavailable,
        upstream=st.sampled_from(["openai", "anthropic", "exa", "browserbase"]),
        status_code=st.one_of(st.none(), st.integers(min_value=400, max_value=599)),
        reason=st.one_of(st.none(), st.text(max_size=120)),
    )


def _verifier_timeout() -> st.SearchStrategy[VerifierTimeout]:
    return st.builds(
        VerifierTimeout,
        verifier=st.text(min_size=1, max_size=48).filter(lambda s: s.strip()),
        elapsed_s=st.floats(min_value=0.0, max_value=600.0,
                            allow_nan=False, allow_infinity=False),
        timeout_s=st.floats(min_value=0.0, max_value=600.0,
                            allow_nan=False, allow_infinity=False),
    )


def _writer_contended() -> st.SearchStrategy[WriterContended]:
    return st.builds(
        WriterContended,
        resource=st.text(min_size=1, max_size=48).filter(lambda s: s.strip()),
        holder_pid=st.one_of(st.none(),
                             st.integers(min_value=1, max_value=2**31 - 1)),
        timeout_s=st.floats(min_value=0.0, max_value=600.0,
                            allow_nan=False, allow_infinity=False),
    )


def substrate_error() -> st.SearchStrategy[SubstrateError]:
    return st.one_of(
        _budget_exceeded(),
        _schema_mismatch(),
        _upstream_unavailable(),
        _verifier_timeout(),
        _writer_contended(),
    )


def ok_int() -> st.SearchStrategy[Ok[int]]:
    return st.integers(min_value=-(10**9), max_value=10**9).map(lambda v: Ok(value=v))


def err_substrate() -> st.SearchStrategy[Err[SubstrateError]]:
    return substrate_error().map(lambda e: Err(error=e))


def result_int() -> st.SearchStrategy[Result[int, SubstrateError]]:
    return st.one_of(ok_int(), err_substrate())
