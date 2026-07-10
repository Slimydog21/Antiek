from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path

from scripts.antiek_bench_live_smoke import SmokeResult, main


def valid_env(tmp_path: Path) -> dict[str, str]:
    return {
        "ANTIEK_BENCH_LIVE_SMOKE": "1",
        "ANTIEK_BENCH_SMOKE_CAP_USD": "0.10",
        "ANTIEK_BENCH_SMOKE_TIMEOUT_S": "30",
        "ANTIEK_BENCH_SMOKE_JOURNAL": str(tmp_path / "smoke.jsonl"),
        "ANTIEK_BENCH_SMOKE_MODELS_JSON": json.dumps(
            [
                {"provider_id": "p-a", "model_id": "m-a", "input_usd_per_1m": 1, "output_usd_per_1m": 1},
                {"provider_id": "p-b", "model_id": "m-b", "input_usd_per_1m": 1, "output_usd_per_1m": 1},
            ]
        ),
    }


def test_absent_gate_and_ci_refuse_before_provider_construction(tmp_path: Path) -> None:
    for env in ({}, {**valid_env(tmp_path), "CI": "true"}):
        constructed = False

        def factory():  # type: ignore[no-untyped-def]
            nonlocal constructed
            constructed = True
            raise AssertionError("provider must not be constructed")

        assert main(environ=env, provider_factory=factory) == 2
        assert constructed is False


def test_cap_timeout_and_pricing_are_hard_refusals(tmp_path: Path) -> None:
    mutations = (
        {"ANTIEK_BENCH_SMOKE_CAP_USD": "0.101"},
        {"ANTIEK_BENCH_SMOKE_TIMEOUT_S": "31"},
        {"ANTIEK_BENCH_SMOKE_MODELS_JSON": "[]"},
        {
            "ANTIEK_BENCH_SMOKE_MODELS_JSON": json.dumps(
                [
                    {"provider_id": "a", "model_id": "a", "input_usd_per_1m": 1_000_000, "output_usd_per_1m": 1_000_000},
                    {"provider_id": "b", "model_id": "b", "input_usd_per_1m": 1_000_000, "output_usd_per_1m": 1_000_000},
                ]
            )
        },
    )
    for mutation in mutations:
        env = {**valid_env(tmp_path), **mutation}
        assert main(environ=env, provider_factory=lambda: None) == 2  # type: ignore[arg-type,return-value]


def test_injected_smoke_is_capped_receipted_and_redacted(tmp_path: Path) -> None:
    output, errors = io.StringIO(), io.StringIO()
    def factory():  # type: ignore[no-untyped-def]
        def call(candidate, settings):  # type: ignore[no-untyped-def]
            return SmokeResult(
                provider_id=candidate.provider_id,
                model_id=candidate.model_id,
                input_tokens=4,
                output_tokens=4,
                cost_usd=Decimal("0.000001"),
                latency_ms=2,
                receipt_id=f"evt-{candidate.model_id}",
                response_text="private-sentinel sk-ABC123",
            )

        return call

    assert main(
        environ=valid_env(tmp_path),
        provider_factory=factory,
        stdout=output,
        stderr=errors,
    ) == 0
    payload = json.loads(output.getvalue())
    assert payload["models"] == ["m-a", "m-b"]
    assert payload["aggregate_actual_spend_usd"] == "0.000002"
    assert payload["cap_usd"] == "0.10"
    assert payload["statuses"] == ["ok", "ok"]
    assert "private-sentinel" not in output.getvalue()
    assert "sk-ABC123" not in output.getvalue()
    persisted = (tmp_path / "smoke.jsonl").read_text()
    assert "private-sentinel" not in persisted


def test_repeated_smoke_creates_fresh_measurements(tmp_path: Path) -> None:
    def factory():  # type: ignore[no-untyped-def]
        def call(candidate, settings):  # type: ignore[no-untyped-def]
            return SmokeResult(
                candidate.provider_id,
                candidate.model_id,
                1,
                1,
                Decimal("0.000001"),
                1,
                f"evt-{candidate.model_id}",
                "ok",
            )

        return call

    env = valid_env(tmp_path)
    assert main(environ=env, provider_factory=factory) == 0
    assert main(environ=env, provider_factory=factory) == 0
    lines = (tmp_path / "smoke.jsonl").read_text().splitlines()
    assert len(lines) == 8
    assert len({json.loads(line)["call_id"] for line in lines}) == 4


def test_timeout_is_bounded_redacted_and_returns_failure(tmp_path: Path) -> None:
    import time

    env = valid_env(tmp_path)
    env["ANTIEK_BENCH_SMOKE_TIMEOUT_S"] = "0.01"
    output, errors = io.StringIO(), io.StringIO()

    def factory():  # type: ignore[no-untyped-def]
        def call(candidate, settings):  # type: ignore[no-untyped-def]
            time.sleep(0.05)
            return SmokeResult(
                candidate.provider_id,
                candidate.model_id,
                1,
                1,
                Decimal("0.000001"),
                50,
                "evt-secret",
                "private-sentinel",
            )

        return call

    assert main(
        environ=env,
        provider_factory=factory,
        stdout=output,
        stderr=errors,
    ) == 1
    payload = json.loads(output.getvalue())
    assert payload["statuses"] == ["timeout", "timeout"]
    assert "private-sentinel" not in output.getvalue() + errors.getvalue()
