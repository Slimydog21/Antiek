from __future__ import annotations

import ast
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from runtime.research_runner.cost_projection import (
    CostCatalogEntry,
    CostProjector,
    UnitRate,
    load_dispatch_inventory,
    project_cascade_cost,
)
from runtime.research_runner.protocol import (
    BillingUnit,
    BoundedUsage,
    CostProjectionRequest,
    ProjectionDisposition,
    ProjectionIneligibility,
    ProjectionRate,
)

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _entry(**overrides: object) -> CostCatalogEntry:
    values: dict[str, object] = {
        "seam_id": "test.llm",
        "provider": "provider-a",
        "model": "model-a",
        "operation": "generate",
        "rates": (
            UnitRate(BillingUnit.INPUT_TOKEN, Decimal("0.000001")),
            UnitRate(BillingUnit.OUTPUT_TOKEN, Decimal("0.000004")),
        ),
        "snapshot": "catalog-2026-07-13",
        "expires_at": NOW + timedelta(days=30),
        "durable_idempotency": True,
        "authoritative_reconciliation": True,
        "hidden_retries_disabled": True,
    }
    values.update(overrides)
    return CostCatalogEntry(**values)  # type: ignore[arg-type]


def _request(*, input_tokens: int = 1, output_tokens: int = 1) -> CostProjectionRequest:
    return CostProjectionRequest(
        seam_id="test.llm",
        provider="provider-a",
        model="model-a",
        operation="generate",
        bounded_usage=(
            BoundedUsage(BillingUnit.INPUT_TOKEN, input_tokens),
            BoundedUsage(BillingUnit.OUTPUT_TOKEN, output_tokens),
        ),
    )


def test_projection_rounds_up_to_integer_cents() -> None:
    result = CostProjector((_entry(),)).project(_request(), now=NOW)
    assert result.disposition is ProjectionDisposition.HOLD_ELIGIBLE
    assert result.maximum_cost_usd == Decimal("0.000005")
    assert result.reservation_cents == 1


def test_projection_does_not_round_away_sub_context_precision_cost() -> None:
    rates = (
        UnitRate(BillingUnit.INPUT_TOKEN, Decimal("0.01")),
        UnitRate(BillingUnit.OUTPUT_TOKEN, Decimal("1e-30")),
    )
    result = CostProjector((_entry(rates=rates),)).project(_request(), now=NOW)
    assert result.maximum_cost_usd == Decimal("0.010000000000000000000000000001")
    assert result.reservation_cents == 2


@pytest.mark.parametrize("invalid", [True, 1.5, Decimal("NaN"), 10**20])
def test_bounded_usage_rejects_non_integer_or_unreasonable_maximum(
    invalid: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        BoundedUsage(BillingUnit.CALL, invalid)  # type: ignore[arg-type]


def test_raw_enum_strings_cannot_bypass_projection_invariants() -> None:
    with pytest.raises(TypeError, match="disposition"):
        type(CostProjector((_entry(),)).project(_request(), now=NOW))(
            **{
                **CostProjector((_entry(),)).project(_request(), now=NOW).__dict__,
                "disposition": "hold_eligible",
            }
        )


def test_eligible_projection_cannot_be_constructed_with_under_reserved_cents() -> None:
    valid = CostProjector((_entry(),)).project(_request(), now=NOW)
    with pytest.raises(ValueError, match="exact upward hold"):
        type(valid)(**{**valid.__dict__, "reservation_cents": 2})


def test_eligible_projection_carries_exact_rates() -> None:
    result = CostProjector((_entry(),)).project(_request(), now=NOW)
    assert result.rates == (
        ProjectionRate(BillingUnit.INPUT_TOKEN, Decimal("0.000001")),
        ProjectionRate(BillingUnit.OUTPUT_TOKEN, Decimal("0.000004")),
    )


@pytest.mark.parametrize("larger_input,larger_output", [(2, 1), (1, 2), (5000, 9000)])
def test_projection_is_monotonic(larger_input: int, larger_output: int) -> None:
    projector = CostProjector((_entry(),))
    base = projector.project(_request(), now=NOW)
    larger = projector.project(
        _request(input_tokens=larger_input, output_tokens=larger_output), now=NOW
    )
    assert larger.maximum_cost_usd >= base.maximum_cost_usd
    assert larger.reservation_cents >= base.reservation_cents


@pytest.mark.parametrize(
    ("entry_overrides", "reason"),
    [
        ({"rates": ()}, ProjectionIneligibility.UNKNOWN_PRICING),
        (
            {"rates": (UnitRate(BillingUnit.INPUT_TOKEN, Decimal("0")),)},
            ProjectionIneligibility.UNKNOWN_PRICING,
        ),
        ({"currency": "EUR"}, ProjectionIneligibility.NON_USD_BILLING),
        (
            {"expires_at": NOW - timedelta(seconds=1)},
            ProjectionIneligibility.STALE_RATE_SNAPSHOT,
        ),
        (
            {"durable_idempotency": False},
            ProjectionIneligibility.PROVIDER_IDEMPOTENCY_UNAVAILABLE,
        ),
        (
            {"authoritative_reconciliation": False},
            ProjectionIneligibility.PROVIDER_RECONCILIATION_UNAVAILABLE,
        ),
        (
            {"hidden_retries_disabled": False},
            ProjectionIneligibility.HIDDEN_RETRIES_ENABLED,
        ),
    ],
)
def test_paid_projection_fails_closed(
    entry_overrides: dict[str, object], reason: ProjectionIneligibility
) -> None:
    result = CostProjector((_entry(**entry_overrides),)).project(_request(), now=NOW)
    assert result.disposition is ProjectionDisposition.INELIGIBLE
    assert result.ineligibility is reason
    assert result.reservation_cents == 0


def test_snapshot_is_stale_at_exact_expiration() -> None:
    result = CostProjector((_entry(expires_at=NOW),)).project(_request(), now=NOW)
    assert result.ineligibility is ProjectionIneligibility.STALE_RATE_SNAPSHOT


def test_paid_zero_price_is_not_treated_as_free() -> None:
    zero_rates = (
        UnitRate(BillingUnit.INPUT_TOKEN, Decimal("0")),
        UnitRate(BillingUnit.OUTPUT_TOKEN, Decimal("0")),
    )
    result = CostProjector((_entry(rates=zero_rates),)).project(_request(), now=NOW)
    assert result.ineligibility is ProjectionIneligibility.ZERO_PRICE_FOR_PAID_SERVICE


def test_missing_bound_for_priced_unit_fails_closed() -> None:
    request = CostProjectionRequest(
        seam_id="test.llm",
        provider="provider-a",
        model="model-a",
        operation="generate",
        bounded_usage=(BoundedUsage(BillingUnit.INPUT_TOKEN, 100),),
    )
    result = CostProjector((_entry(),)).project(request, now=NOW)
    assert result.ineligibility is ProjectionIneligibility.UNBOUNDED_USAGE


def test_catalog_rejects_duplicate_billing_units() -> None:
    duplicate_rates = (
        UnitRate(BillingUnit.INPUT_TOKEN, Decimal("0.1")),
        UnitRate(BillingUnit.INPUT_TOKEN, Decimal("0.2")),
    )
    with pytest.raises(ValueError, match="repeats a billing unit"):
        CostProjector((_entry(rates=duplicate_rates),))


def test_zero_cost_local_path_returns_receipt_without_hold() -> None:
    entry = _entry(
        provider="antiek",
        model="contract-stub",
        operation="gather",
        paid_service=False,
        rates=(UnitRate(BillingUnit.LOCAL_OPERATION, Decimal(0)),),
    )
    request = CostProjectionRequest(
        seam_id="test.llm",
        provider="antiek",
        model="contract-stub",
        operation="gather",
        bounded_usage=(BoundedUsage(BillingUnit.LOCAL_OPERATION, 2),),
    )
    result = CostProjector((entry,)).project(request, now=NOW)
    assert result.disposition is ProjectionDisposition.ZERO_COST_RECEIPT
    assert result.reservation_cents == 0


def test_zero_cost_route_with_wrong_billing_unit_refuses() -> None:
    entry = _entry(
        paid_service=False,
        rates=(UnitRate(BillingUnit.LOCAL_OPERATION, Decimal(0)),),
    )
    result = CostProjector((entry,)).project(_request(), now=NOW)
    assert result.ineligibility is ProjectionIneligibility.UNBOUNDED_USAGE


def test_extreme_rate_coefficient_returns_typed_overflow() -> None:
    huge_rate = Decimal("1" * 1_001)
    result = CostProjector(
        (
            _entry(
                rates=(
                    UnitRate(BillingUnit.INPUT_TOKEN, huge_rate),
                    UnitRate(BillingUnit.OUTPUT_TOKEN, Decimal(1)),
                )
            ),
        )
    ).project(_request(), now=NOW)
    assert result.ineligibility is ProjectionIneligibility.PROJECTION_OVERFLOW


def test_checked_in_catalog_refuses_current_paid_routes() -> None:
    llm = CostProjectionRequest(
        seam_id="cascade.tail.synthesizer",
        provider="zai_reasoning",
        model="glm-5.2",
        operation="generate",
        bounded_usage=(
            BoundedUsage(BillingUnit.INPUT_TOKEN, 1000),
            BoundedUsage(BillingUnit.OUTPUT_TOKEN, 16384),
        ),
    )
    llm_result = project_cascade_cost(llm, now=NOW)
    assert llm_result.ineligibility is ProjectionIneligibility.ZERO_PRICE_FOR_PAID_SERVICE

    exa = CostProjectionRequest(
        seam_id="cascade.gather.exa.search",
        provider="exa",
        model="search",
        operation="search",
        bounded_usage=(BoundedUsage(BillingUnit.CALL, 1),),
    )
    exa_result = project_cascade_cost(exa, now=NOW)
    assert exa_result.ineligibility is ProjectionIneligibility.STALE_RATE_SNAPSHOT


def test_checked_in_catalog_emits_local_receipt() -> None:
    request = CostProjectionRequest(
        seam_id="cascade.gather.contract_stub",
        provider="antiek",
        model="contract-stub",
        operation="gather",
        bounded_usage=(BoundedUsage(BillingUnit.LOCAL_OPERATION, 2),),
    )
    assert (
        project_cascade_cost(request, now=NOW).disposition
        is ProjectionDisposition.ZERO_COST_RECEIPT
    )


def test_snapshot_or_route_change_invalidates_projection() -> None:
    projector = CostProjector((_entry(),))
    stale_request = CostProjectionRequest(
        **{
            **_request().__dict__,
            "expected_rate_snapshot": "catalog-before-route-change",
        }
    )
    assert (
        projector.project(stale_request, now=NOW).ineligibility
        is ProjectionIneligibility.ROUTE_MISMATCH
    )
    changed_model = CostProjectionRequest(**{**_request().__dict__, "model": "model-b"})
    assert (
        projector.project(changed_model, now=NOW).ineligibility
        is ProjectionIneligibility.ROUTE_MISMATCH
    )


def _call_symbol(node: ast.Call) -> str:
    parts: list[str] = []
    value: ast.expr = node.func
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


class _ScopedCalls(ast.NodeVisitor):
    def __init__(self) -> None:
        self._scope: list[str] = []
        self.calls: list[tuple[str, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scope(node, node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scope(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scope(node, node.name)

    def _visit_scope(self, node: ast.AST, name: str) -> None:
        self._scope.append(name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append((".".join(self._scope), _call_symbol(node)))
        self.generic_visit(node)


def test_all_cascade_dispatchers_classified() -> None:
    inventory = load_dispatch_inventory()
    declared: Counter[tuple[str, str, str]] = Counter()
    seam_ids = [str(item["seam_id"]) for item in inventory]
    assert len(seam_ids) == len(set(seam_ids))
    for item in inventory:
        source = str(item["source"])
        function = str(item["function"])
        symbols = item.get("call_symbols", [item.get("call_symbol")])
        assert isinstance(symbols, list)
        declared.update((source, function, str(symbol)) for symbol in symbols)
        tree = ast.parse((ROOT / source).read_text(encoding="utf-8"), filename=source)
        scoped = _ScopedCalls()
        scoped.visit(tree)
        assert all((function, str(symbol)) in scoped.calls for symbol in symbols)

    outbound_symbols = {
        "dispatch",
        "dispatch_loop_one",
        "client.post",
        "client.get",
        "c.get",
        "SentenceTransformerEmbedding",
    }
    reachable: Counter[tuple[str, str, str]] = Counter()
    for source in {str(item["source"]) for item in inventory}:
        tree = ast.parse((ROOT / source).read_text(encoding="utf-8"), filename=source)
        scoped = _ScopedCalls()
        scoped.visit(tree)
        reachable.update(
            (source, scope, symbol) for scope, symbol in scoped.calls if symbol in outbound_symbols
        )
    non_dispatch_marker = Counter(
        {
            (
                "runtime/research_runner/host_local.py",
                "make_contract_gather_stub._loop",
                "ctx.step",
            ): 1,
            (
                "interfaces/research/api/cascade_routes.py",
                "_hard_ceiling_launch_receipt",
                "gateway.prepare_zero_cost",
            ): 1,
            (
                "interfaces/research/api/cascade_routes.py",
                "_hard_ceiling_approval_receipt",
                "gateway.prepare_zero_cost",
            ): 1,
        }
    )
    assert declared - non_dispatch_marker == reachable

    classifications = {str(item["classification"]) for item in inventory}
    assert classifications <= {"paid_ineligible", "zero_cost_local", "zero_cost_external"}
    assert not any(item.get("classification") == "hold_eligible" for item in inventory)


def test_browserbase_is_not_reachable_from_cascade_promotion() -> None:
    host_local = (ROOT / "runtime/research_runner/host_local.py").read_text(encoding="utf-8")
    tree = ast.parse(host_local)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_symbol(node) == "promote_discovery"
    ]
    assert calls
    assert all(
        not any(keyword.arg == "fallback_to_browserbase" for keyword in call.keywords)
        for call in calls
    )
