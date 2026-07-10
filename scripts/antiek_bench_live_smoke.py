#!/usr/bin/env python3
"""Operator-gated one-item, two-model Antiek-bench live smoke."""

from __future__ import annotations

import json
import multiprocessing
import os
import secrets
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol, TextIO, TypedDict

LIVE_ENV = "ANTIEK_BENCH_LIVE_SMOKE"
CANDIDATES_ENV = "ANTIEK_BENCH_SMOKE_MODELS_JSON"
CAP_ENV = "ANTIEK_BENCH_SMOKE_CAP_USD"
TIMEOUT_ENV = "ANTIEK_BENCH_SMOKE_TIMEOUT_S"
JOURNAL_ENV = "ANTIEK_BENCH_SMOKE_JOURNAL"
MAX_CAP = Decimal("0.10")
MAX_TIMEOUT_S = 30.0
SMOKE_PROMPT = "Return exactly: Antiek live smoke acknowledged."


@dataclass(frozen=True)
class SmokeCandidate:
    provider_id: str
    model_id: str
    input_usd_per_1m: Decimal
    output_usd_per_1m: Decimal


@dataclass(frozen=True)
class SmokeSettings:
    candidates: tuple[SmokeCandidate, SmokeCandidate]
    cap_usd: Decimal
    timeout_s: float
    journal_path: Path
    run_id: str
    max_output_tokens: int = 128


@dataclass(frozen=True)
class SmokeResult:
    provider_id: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int
    receipt_id: str
    response_text: str


class SmokeCaller(Protocol):
    def __call__(
        self, candidate: SmokeCandidate, settings: SmokeSettings
    ) -> SmokeResult: ...


ProviderFactory = Callable[[], SmokeCaller]


class SmokeSummary(TypedDict):
    models: list[str]
    statuses: list[str]
    receipt_ids: list[str]
    aggregate_actual_spend_usd: str
    cap_usd: str


def _invoke_in_child(fn: Callable[[], object], queue: object) -> None:
    try:
        queue.put((True, fn()))  # type: ignore[attr-defined]
    except BaseException:
        queue.put((False, None))  # type: ignore[attr-defined]


def _settings(environ: Mapping[str, str]) -> SmokeSettings:
    if environ.get(LIVE_ENV) != "1":
        raise ValueError(f"{LIVE_ENV}=1 is required")
    if (environ.get("CI") or "").strip().lower() in {"1", "true", "yes"}:
        raise ValueError("live smoke is forbidden under CI")
    cap = Decimal(environ.get(CAP_ENV, "0"))
    if cap <= 0 or cap > MAX_CAP:
        raise ValueError(f"{CAP_ENV} must be >0 and <=0.10")
    timeout = float(environ.get(TIMEOUT_ENV, "0"))
    if timeout <= 0 or timeout > MAX_TIMEOUT_S:
        raise ValueError(f"{TIMEOUT_ENV} must be >0 and <=30")
    raw = json.loads(environ.get(CANDIDATES_ENV, "[]"))
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError(f"{CANDIDATES_ENV} must contain exactly two models")
    candidates: list[SmokeCandidate] = []
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("smoke model entries must be objects")
        candidate = SmokeCandidate(
            provider_id=str(row.get("provider_id") or "").strip(),
            model_id=str(row.get("model_id") or "").strip(),
            input_usd_per_1m=Decimal(str(row.get("input_usd_per_1m") or "0")),
            output_usd_per_1m=Decimal(str(row.get("output_usd_per_1m") or "0")),
        )
        if not candidate.provider_id or not candidate.model_id:
            raise ValueError("smoke candidates require provider_id and model_id")
        if candidate.input_usd_per_1m <= 0 or candidate.output_usd_per_1m <= 0:
            raise ValueError("smoke candidates require verified positive pricing")
        candidates.append(candidate)
    if len({(row.provider_id, row.model_id) for row in candidates}) != 2:
        raise ValueError("smoke candidates must be distinct")
    journal = Path(
        environ.get(JOURNAL_ENV, "~/.antiek/bench-live-smoke/calls.jsonl")
    ).expanduser()
    settings = SmokeSettings(
        candidates=(candidates[0], candidates[1]),
        cap_usd=cap,
        timeout_s=timeout,
        journal_path=journal,
        run_id=secrets.token_hex(8),
    )
    if sum((_reservation(row, settings) for row in settings.candidates), Decimal("0")) > cap:
        raise ValueError("two-call worst-case reservation exceeds approved cap")
    return settings


def _reservation(candidate: SmokeCandidate, settings: SmokeSettings) -> Decimal:
    input_tokens = len(SMOKE_PROMPT.encode("utf-8"))
    return (
        Decimal(input_tokens) * candidate.input_usd_per_1m
        + Decimal(settings.max_output_tokens) * candidate.output_usd_per_1m
    ) / Decimal(1_000_000)


def default_provider_factory() -> SmokeCaller:
    """Construct the real single-router caller only after all refusal gates pass."""
    from substrate.dispatch.router import DispatchConfig, TierConfig, TierPricing, dispatch

    def call(candidate: SmokeCandidate, settings: SmokeSettings) -> SmokeResult:
        from substrate.dispatch.providers.bootstrap import register_default_providers

        registered = register_default_providers(quiet=True, only=[candidate.provider_id])
        if candidate.provider_id not in registered:
            raise RuntimeError("requested smoke provider is unavailable")
        tier = TierConfig(
            name="antiek_bench_smoke",
            provider=candidate.provider_id,
            model=candidate.model_id,
            max_tokens=settings.max_output_tokens,
            temperature=0,
            context_budget_tokens=1_000,
            pricing=TierPricing(
                input_per_mtok=float(candidate.input_usd_per_1m),
                output_per_mtok=float(candidate.output_usd_per_1m),
            ),
            fallback=None,
        )
        result = dispatch(
            SMOKE_PROMPT,
            "synthesizer",
            investigation_id="antiek-bench-live-smoke",
            max_tokens=settings.max_output_tokens,
            config=DispatchConfig(
                role_tiers={"synthesizer": tier.name}, tiers={tier.name: tier}
            ),
        )
        return SmokeResult(
            provider_id=result.provider,
            model_id=result.model,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cost_usd=Decimal(str(result.cost_usd)),
            latency_ms=result.latency_ms,
            receipt_id=result.event_id or "",
            response_text=result.text,
        )

    return call


def run_smoke(settings: SmokeSettings, caller: SmokeCaller) -> SmokeSummary:
    from substrate.antiek_bench.live import HardBudget, Journal, LiveCallRunner, ProviderResult

    class ProcessTimeout:
        def run(self, fn, timeout_s: float):  # type: ignore[no-untyped-def]
            if "fork" not in multiprocessing.get_all_start_methods():
                raise RuntimeError("live smoke requires killable fork isolation")
            context = multiprocessing.get_context("fork")
            queue = context.Queue(maxsize=1)
            process = context.Process(target=_invoke_in_child, args=(fn, queue))
            process.start()
            process.join(timeout_s)
            if process.is_alive():
                process.terminate()
                process.join(2)
                if process.is_alive():
                    process.kill()
                    process.join()
                raise TimeoutError
            if process.exitcode != 0:
                raise RuntimeError("isolated provider process failed")
            ok, value = queue.get(timeout=1)
            if not ok:
                raise RuntimeError("isolated provider call failed")
            return value

    journal = Journal(settings.journal_path)
    runner = LiveCallRunner(journal, HardBudget(settings.cap_usd, journal), ProcessTimeout())
    rows = []
    for candidate in settings.candidates:
        def invoke(current: SmokeCandidate = candidate) -> ProviderResult:
            result = caller(current, settings)
            return ProviderResult(
                model_id=result.model_id,
                prompt_tokens=result.input_tokens,
                completion_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                response_text=result.response_text,
                provider_id=result.provider_id,
                route_receipt_id=result.receipt_id,
            )

        rows.append(
            runner.execute(
                wedge_id=f"manual-live-smoke-v1-{settings.run_id}",
                week_id="smoke-W01",
                suite_version="smoke-v1",
                requested_provider=candidate.provider_id,
                requested_model=candidate.model_id,
                task_class="distill",
                item_id="smoke-item",
                prompt_hash="sha256:fixed-smoke-v1",
                provider_fn=invoke,
                timeout_s=settings.timeout_s,
                maximum_cost=_reservation(candidate, settings),
            )
        )
    return {
        "models": [row.requested_model for row in rows],
        "statuses": [row.status for row in rows],
        "receipt_ids": [row.route_receipt_id for row in rows],
        "aggregate_actual_spend_usd": str(
            sum((row.cost_usd for row in rows), Decimal("0"))
        ),
        "cap_usd": str(settings.cap_usd),
    }


def main(
    *,
    environ: Mapping[str, str] | None = None,
    provider_factory: ProviderFactory = default_provider_factory,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    env = os.environ if environ is None else environ
    try:
        settings = _settings(env)
    except (ValueError, TypeError, json.JSONDecodeError, ArithmeticError) as exc:
        print(f"REFUSED: {exc}", file=stderr)
        return 2
    try:
        caller = provider_factory()
        result = run_smoke(settings, caller)
    except Exception:
        print("SMOKE_FAILED: provider_or_journal_boundary", file=stderr)
        return 1
    print(json.dumps(result, sort_keys=True), file=stdout)
    return 0 if all(status == "ok" for status in result["statuses"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
