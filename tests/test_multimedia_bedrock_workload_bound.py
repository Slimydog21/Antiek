from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from substrate.multimedia.bedrock_batch_adapter import (
    BedrockBatchError,
    BedrockBatchRequest,
)
from substrate.multimedia.bedrock_workload_bound import (
    BedrockBatchModelProfile,
    BedrockBatchRateSnapshot,
    materialize_bedrock_batch_workload,
)
from tests.test_multimedia_bedrock_batch_adapter import (
    BedrockBatchRecoveryAdapter,
    StatefulBedrock,
    _authority,
)


def _profile(**changes: object) -> BedrockBatchModelProfile:
    values = {
        "provider_model_id": "anthropic.claude-v1",
        "antiek_model": "batch-model",
        "region": "us-east-1",
        "rate_tier": "standard",
        "context_tokens": 100_000,
        "maximum_records": 10,
        "maximum_output_tokens_per_record": 8_192,
        "output_cap_field": "max_tokens",
        "profile_version": "2026-07-15",
    }
    values.update(changes)
    return BedrockBatchModelProfile(**values)  # type: ignore[arg-type]


def _rates(**changes: object) -> BedrockBatchRateSnapshot:
    values = {
        "provider_model_id": "anthropic.claude-v1",
        "region": "us-east-1",
        "rate_tier": "standard",
        "input_usd_per_million_tokens": "3",
        "output_usd_per_million_tokens": "15",
        "fixed_request_usd": "0",
        "currency": "USD",
        "effective_at": "2026-07-15T00:00:00Z",
        "valid_until": "2026-07-16T00:00:00Z",
        "source_digest": "a" * 64,
        "rate_version": "v1",
        "paid": True,
    }
    values.update(changes)
    return BedrockBatchRateSnapshot(**values)  # type: ignore[arg-type]


def _records() -> list[dict[str, object]]:
    return [
        {"modelInput": {"prompt": "snowman \u2603", "max_tokens": 7}, "recordId": "b"},
        {"recordId": "a", "modelInput": {"max_tokens": 11, "prompt": "hello"}},
    ]


def test_materialization_is_exact_redacted_and_order_sensitive() -> None:
    raw, bound = materialize_bedrock_batch_workload(_records(), _profile(), _rates())
    assert raw == (
        b'{"modelInput":{"max_tokens":7,"prompt":"snowman \\u2603"},"recordId":"b"}\n'
        b'{"modelInput":{"max_tokens":11,"prompt":"hello"},"recordId":"a"}\n'
    )
    assert bound.workload_byte_length == len(raw)
    assert bound.workload_sha256 == hashlib.sha256(raw).hexdigest()
    assert bound.input_token_ceiling == 200_000
    assert bound.output_token_ceiling == 18
    assert bound.exact_unrounded_usd == "0.60027"
    assert bound.reservation_cents == 61
    assert "prompt" not in bound.canonical_json
    assert materialize_bedrock_batch_workload(_records(), _profile(), _rates()) == (raw, bound)
    reversed_bound = materialize_bedrock_batch_workload(
        list(reversed(_records())), _profile(), _rates()
    )[1]
    assert reversed_bound.workload_sha256 != bound.workload_sha256
    assert reversed_bound.ordered_record_ids_sha256 != bound.ordered_record_ids_sha256
    assert reversed_bound.reservation_cents == bound.reservation_cents


@pytest.mark.parametrize(
    ("input_rate", "output_rate", "fixed", "paid", "expected_usd", "expected_cents"),
    [
        ("0", "0", "0", False, "0", 0),
        ("0.000001", "0", "0", True, "0.0000001", 1),
        ("100", "0", "0", True, "10", 1_000),
        ("999999999999.999999999999", "0", "0", True, "99999999999.9999999999999", 10_000_000_000_000),
    ],
)
def test_exact_decimal_rounds_up_once(
    input_rate: str,
    output_rate: str,
    fixed: str,
    paid: bool,
    expected_usd: str,
    expected_cents: int,
) -> None:
    _, bound = materialize_bedrock_batch_workload(
        [{"recordId": "one", "modelInput": {"max_tokens": 1}}],
        _profile(context_tokens=100_000),
        _rates(
            input_usd_per_million_tokens=input_rate,
            output_usd_per_million_tokens=output_rate,
            fixed_request_usd=fixed,
            paid=paid,
        ),
    )
    assert bound.exact_unrounded_usd == expected_usd
    assert bound.reservation_cents == expected_cents


@pytest.mark.parametrize("bad", ["-1", "1e2", "1.230", "NaN", "Infinity", "0.1234567890123"])
def test_rates_reject_noncanonical_or_inexact_values(bad: str) -> None:
    with pytest.raises(ValueError, match="canonical non-negative decimal"):
        _rates(input_usd_per_million_tokens=bad)
    with pytest.raises((TypeError, ValueError)):
        _rates(input_usd_per_million_tokens=1.5)


def test_rate_window_is_strict_and_expired_authority_is_not_held(tmp_path) -> None:
    with pytest.raises(ValueError, match="valid_until must be after effective_at"):
        _rates(valid_until="2026-07-15T00:00:00Z")
    with pytest.raises(ValueError, match="whole-second UTC timestamp"):
        _rates(valid_until="2026-07-16")

    workload_bytes, bound = materialize_bedrock_batch_workload(
        _records(),
        _profile(),
        _rates(
            effective_at="2020-01-01T00:00:00Z",
            valid_until="2020-01-02T00:00:00Z",
        ),
    )
    ledger, binding = _authority(tmp_path)
    request = BedrockBatchRequest.from_workload_bound(
        workload_bound=bound,
        job_name="job-name",
        model_id="anthropic.claude-v1",
        role_arn="arn:aws:iam::123456789012:role/AntiekBedrockBatch",
        input_s3_uri=f"s3://input-bucket/{bound.workload_sha256}/manifest.jsonl",
        output_s3_uri="s3://output-bucket/prefix/",
        timeout_hours=24,
        account_digest=hashlib.sha256(b"123456789012").hexdigest(),
        region="us-east-1",
    )
    adapter = BedrockBatchRecoveryAdapter(
        ledger, StatefulBedrock("123456789012", "us-east-1")
    )
    with pytest.raises(ValueError, match="rate snapshot is not current"):
        adapter.prepare(
            command_key="prepare",
            binding=binding,
            operation_id="operation-1",
            model="batch-model",
            request=request,
            workload_bytes=workload_bytes,
        )
    assert ledger.balance("run-1").held_cents == 0


def test_zero_cost_bound_is_pure_but_ineligible_for_paid_bedrock_hold(tmp_path) -> None:
    workload_bytes, bound = materialize_bedrock_batch_workload(
        _records(),
        _profile(),
        _rates(
            input_usd_per_million_tokens="0",
            output_usd_per_million_tokens="0",
            fixed_request_usd="0",
            paid=False,
        ),
    )
    assert bound.reservation_cents == 0
    request = BedrockBatchRequest.from_workload_bound(
        workload_bound=bound,
        job_name="job-name",
        model_id="anthropic.claude-v1",
        role_arn="arn:aws:iam::123456789012:role/AntiekBedrockBatch",
        input_s3_uri=f"s3://input-bucket/{bound.workload_sha256}/manifest.jsonl",
        output_s3_uri="s3://output-bucket/prefix/",
        timeout_hours=24,
        account_digest=hashlib.sha256(b"123456789012").hexdigest(),
        region="us-east-1",
    )
    ledger, binding = _authority(tmp_path)
    adapter = BedrockBatchRecoveryAdapter(
        ledger, StatefulBedrock("123456789012", "us-east-1")
    )
    with pytest.raises(BedrockBatchError, match="positive reservation"):
        adapter.prepare(
            command_key="prepare",
            binding=binding,
            operation_id="operation-1",
            model="batch-model",
            request=request,
            workload_bytes=workload_bytes,
        )
    assert ledger.balance("run-1").held_cents == 0


@pytest.mark.parametrize(
    "records",
    [
        [],
        [{"recordId": "x", "modelInput": {"max_tokens": True}}],
        [{"recordId": "x", "modelInput": {"max_tokens": 1.2}}],
        [{"recordId": "x", "modelInput": {}}],
        [{"recordId": "x", "modelInput": {"max_tokens": 9_000}}],
        [{"recordId": "x", "modelInput": {"max_tokens": 1}, "extra": 1}],
        [
            {"recordId": "x", "modelInput": {"max_tokens": 1}},
            {"recordId": "x", "modelInput": {"max_tokens": 2}},
        ],
    ],
)
def test_workload_shape_fails_closed(records: list[dict[str, object]]) -> None:
    with pytest.raises(ValueError):
        materialize_bedrock_batch_workload(records, _profile(), _rates())


def test_profile_rate_identity_and_zero_paid_route_fail_closed() -> None:
    with pytest.raises(ValueError, match="rate identity"):
        materialize_bedrock_batch_workload(_records(), _profile(), _rates(region="eu-west-1"))
    with pytest.raises(ValueError, match="explicitly non-paid"):
        materialize_bedrock_batch_workload(
            _records(),
            _profile(),
            _rates(
                input_usd_per_million_tokens="0",
                output_usd_per_million_tokens="0",
                paid=True,
            ),
        )


def test_bound_request_drives_hold_and_all_adapter_identities(tmp_path) -> None:
    workload_bytes, bound = materialize_bedrock_batch_workload(_records(), _profile(), _rates())
    request = BedrockBatchRequest.from_workload_bound(
        workload_bound=bound,
        job_name="job-name",
        model_id="anthropic.claude-v1",
        role_arn="arn:aws:iam::123456789012:role/AntiekBedrockBatch",
        input_s3_uri=f"s3://input/{bound.workload_sha256}/manifest.jsonl",
        output_s3_uri="s3://output/prefix/",
        timeout_hours=24,
        account_digest=hashlib.sha256(b"123456789012").hexdigest(),
        region="us-east-1",
    )
    ledger, binding = _authority(tmp_path)
    adapter = BedrockBatchRecoveryAdapter(
        ledger, StatefulBedrock("123456789012", "us-east-1")
    )
    submission = adapter.prepare(
        command_key="prepare",
        binding=binding,
        operation_id="operation-1",
        model="batch-model",
        request=request,
        workload_bytes=workload_bytes,
    )
    hold = ledger.hold(submission.hold_id)
    assert hold.projected_max_cents == bound.reservation_cents
    assert hold.intent.projection_digest == bound.digest
    assert hold.intent.rate_snapshot == bound.canonical_json
    assert submission.intent.adapter_contract.endswith("s3-version-publication-v2")
    assert "workload_bound" not in submission.intent.create_request_json

    _, changed = materialize_bedrock_batch_workload(
        _records(), _profile(), _rates(output_usd_per_million_tokens="16")
    )
    changed_request = BedrockBatchRequest.from_workload_bound(
        workload_bound=changed,
        **{
            key: value
            for key, value in request.__dict__.items()
            if key not in {"workload_bound_json", "workload_bound_digest"}
        },
    )
    assert changed_request.workload_bound_digest != request.workload_bound_digest


def test_bound_cannot_be_copied_with_lower_authority() -> None:
    _, bound = materialize_bedrock_batch_workload(_records(), _profile(), _rates())
    with pytest.raises(ValueError, match="do not reconcile"):
        replace(bound, reservation_cents=bound.reservation_cents - 1)
    with pytest.raises(ValueError, match="do not reconcile"):
        replace(bound, input_token_ceiling=bound.input_token_ceiling - 1)


def test_bound_path_rejects_uri_route_and_legacy_authority() -> None:
    _, bound = materialize_bedrock_batch_workload(_records(), _profile(), _rates())
    common = dict(
        job_name="job-name",
        model_id="anthropic.claude-v1",
        role_arn="arn:aws:iam::123456789012:role/AntiekBedrockBatch",
        output_s3_uri="s3://output/prefix/",
        timeout_hours=24,
        account_digest=hashlib.sha256(b"123456789012").hexdigest(),
        region="us-east-1",
    )
    with pytest.raises(ValueError, match="path segment"):
        BedrockBatchRequest.from_workload_bound(
            workload_bound=bound,
            input_s3_uri="s3://input/manifest.jsonl",
            **common,
        )
    for malformed_uri in (
        f"s3://{bound.workload_sha256}/manifest.jsonl",
        f"s3:///{bound.workload_sha256}/manifest.jsonl",
        f"s3://input/{bound.workload_sha256}/manifest.jsonl?version=1",
        f"s3://input/{bound.workload_sha256}/manifest.jsonl#fragment",
    ):
        with pytest.raises(ValueError, match="path segment"):
            BedrockBatchRequest.from_workload_bound(
                workload_bound=bound, input_s3_uri=malformed_uri, **common
            )
    unbound = BedrockBatchRequest(input_s3_uri="s3://input/manifest.jsonl", **common)
    adapter = BedrockBatchRecoveryAdapter(None, None)  # type: ignore[arg-type]
    with pytest.raises(BedrockBatchError, match="workload-bound"):
        adapter.prepare(
            command_key="x", binding=None, operation_id="x",  # type: ignore[arg-type]
            model="batch-model", request=unbound, workload_bytes=b"",
        )


def test_prepare_reopens_exact_workload_bytes_before_reserving(tmp_path) -> None:
    workload_bytes, bound = materialize_bedrock_batch_workload(_records(), _profile(), _rates())
    request = BedrockBatchRequest.from_workload_bound(
        workload_bound=bound,
        job_name="job-name",
        model_id="anthropic.claude-v1",
        role_arn="arn:aws:iam::123456789012:role/AntiekBedrockBatch",
        input_s3_uri=f"s3://input/{bound.workload_sha256}/manifest.jsonl",
        output_s3_uri="s3://output/prefix/",
        timeout_hours=24,
        account_digest=hashlib.sha256(b"123456789012").hexdigest(),
        region="us-east-1",
    )
    ledger, binding = _authority(tmp_path)
    adapter = BedrockBatchRecoveryAdapter(
        ledger, StatefulBedrock("123456789012", "us-east-1")
    )
    with pytest.raises(ValueError, match="workload bytes conflict"):
        adapter.prepare(
            command_key="prepare",
            binding=binding,
            operation_id="operation-1",
            model="batch-model",
            request=request,
            workload_bytes=workload_bytes.replace(b"hello", b"jello"),
        )
    assert ledger.balance("run-1").held_cents == 0
