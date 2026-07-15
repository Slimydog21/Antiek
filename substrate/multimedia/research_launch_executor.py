"""Durable, pull-driven multimedia research launch manifest."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from substrate.multimedia.research_plan import ResearchPlanLedger
from substrate.research_spend import (
    BindingConflict,
    LaunchExecutionIntent,
    LaunchExecutionSnapshot,
    LaunchOperationIntent,
    LaunchOperationState,
    ResearchSpendLedger,
    RunBinding,
    RunStatus,
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _identity(domain: str, prefix: str, *parts: object) -> str:
    return prefix + _digest([domain, *parts])[:48]


class EligibleResearchAdapter(Protocol):
    """Eligibility metadata only; dispatch remains a future gateway concern."""

    provider: str
    model: str
    durable_idempotency: bool
    hidden_retries_disabled: bool
    result_recovery: bool
    authoritative_reconciliation: bool


@dataclass(frozen=True)
class EligibleAdapterRegistry:
    adapters: Mapping[tuple[str, str], EligibleResearchAdapter]

    def eligible(self, provider: str, model: str) -> bool:
        adapter = self.adapters.get((provider, model))
        return bool(
            adapter is not None
            and adapter.provider == provider
            and adapter.model == model
            and adapter.durable_idempotency
            and adapter.hidden_retries_disabled
            and adapter.result_recovery
            and adapter.authoritative_reconciliation
        )


class MultimediaResearchLaunchExecutor:
    def __init__(
        self,
        plans: ResearchPlanLedger,
        spend: ResearchSpendLedger,
        registry: EligibleAdapterRegistry | None = None,
    ) -> None:
        self.plans = plans
        self.spend = spend
        self.spend.ensure_schema()
        self.registry = registry or EligibleAdapterRegistry({})

    def materialize(
        self, *, owner_id: str, investigation_id: str, launch_reservation_id: str, command_key: str
    ) -> tuple[LaunchExecutionSnapshot, bool]:
        reservation = self.plans.get_investigation_launch_reservation(
            owner_identity_digest=owner_id, investigation_id=investigation_id
        )
        if reservation.launch_reservation_id != launch_reservation_id:
            raise BindingConflict("launch reservation changed")
        prepared = self.plans.get_prepared_investigation(
            owner_identity_digest=owner_id, investigation_id=investigation_id
        )
        if (
            reservation.source_plan_integrity_digest != prepared.source_plan_integrity_digest
            or reservation.investigation_id != prepared.investigation_id
            or reservation.total_node_count != prepared.total_node_count
            or reservation.leaf_question_count != prepared.leaf_question_count
        ):
            raise BindingConflict("prepared investigation changed")
        binding = self._binding(owner_id, reservation)
        run = self.spend.balance(reservation.spend_run_id)
        if (
            run.binding != binding
            or run.ceiling_cents != reservation.reserved_cents
            or run.status is not RunStatus.ACTIVE
            or run.ceiling_breached
        ):
            raise BindingConflict("research spend run binding changed")
        leaves = self._ordered_leaves(prepared.tree)
        if len(leaves) != reservation.leaf_question_count:
            raise BindingConflict("prepared leaf count changed")
        execution_id = _identity(
            "research-launch-execution-v1",
            "mle_",
            reservation.launch_reservation_id,
            reservation.launch_manifest_digest,
        )
        eligible = self.registry.eligible(reservation.provider, reservation.model)
        operations = tuple(
            self._operation(reservation, node_id, question, ordinal, eligible)
            for ordinal, (node_id, question) in enumerate(leaves)
        )
        request_digest = _digest(
            {
                "launch_reservation_id": launch_reservation_id,
                "operations": [item.operation_id for item in operations],
            }
        )
        intent = LaunchExecutionIntent(
            execution_id=execution_id,
            authority_kind="multimedia_research_v1",
            launch_reservation_id=launch_reservation_id,
            launch_manifest_digest=reservation.launch_manifest_digest,
            prepared_integrity_digest=reservation.prepared_integrity_digest,
            provider=reservation.provider,
            model=reservation.model,
            route_digest=reservation.dispatch_config_digest,
            pricing_digest=reservation.pricing_digest,
            workload_digest=reservation.workload_digest,
            operation_count=len(operations),
            request_digest=request_digest,
        )
        return self.spend.materialize_launch_execution(command_key, binding, intent, operations)

    def get(self, *, owner_id: str, investigation_id: str) -> LaunchExecutionSnapshot:
        reservation = self.plans.get_investigation_launch_reservation(
            owner_identity_digest=owner_id, investigation_id=investigation_id
        )
        snapshot = self.spend.launch_execution_for_run(reservation.spend_run_id, owner_id)
        if (
            snapshot is None
            or snapshot.intent.launch_reservation_id != reservation.launch_reservation_id
        ):
            raise LookupError("launch execution unavailable")
        return snapshot

    def advance(
        self, *, owner_id: str, investigation_id: str, command_key: str
    ) -> LaunchExecutionSnapshot:
        snapshot = self.get(owner_id=owner_id, investigation_id=investigation_id)
        # Cycle 29 intentionally ships no production-eligible adapter. Blocked operations
        # are terminal for selection and replaying advance is a durable no-effect command.
        return self.spend.record_launch_advance(command_key, snapshot.intent.execution_id, owner_id)

    @staticmethod
    def _binding(owner_id: str, reservation) -> RunBinding:
        return RunBinding(
            run_id=reservation.spend_run_id,
            owner_id=owner_id,
            session_id=reservation.session_id,
            plan_digest=reservation.launch_manifest_digest,
            approval_revision=reservation.source_plan_version,
        )

    @staticmethod
    def _ordered_leaves(tree: dict[str, object]) -> tuple[tuple[str, str], ...]:
        root = tree.get("root")
        if not isinstance(root, dict):
            raise BindingConflict("prepared tree is malformed")
        leaves: list[tuple[str, str]] = []
        seen: set[str] = set()
        stack = [root]
        while stack:
            node = stack.pop()
            node_id, question, children = (
                node.get("node_id"),
                node.get("question"),
                node.get("children"),
            )
            if (
                not isinstance(node_id, str)
                or node_id in seen
                or not isinstance(question, str)
                or not question.strip()
                or len(question) > 2000
                or not isinstance(children, list)
            ):
                raise BindingConflict("prepared tree is malformed")
            seen.add(node_id)
            if not children:
                leaves.append((node_id, question))
            else:
                if any(not isinstance(child, dict) for child in children):
                    raise BindingConflict("prepared tree is malformed")
                stack.extend(reversed(children))
        return tuple(leaves)

    @staticmethod
    def _operation(
        reservation, node_id: str, question: str, ordinal: int, eligible: bool
    ) -> LaunchOperationIntent:
        operation_id = _identity(
            "multimedia-launch-operation-v1",
            "mlop_",
            reservation.launch_reservation_id,
            reservation.launch_manifest_digest,
            node_id,
            ordinal,
        )
        payload_digest = _digest({"question": question})
        logical_id = _identity(
            "research-provider-logical-operation-v1",
            "rplo_",
            operation_id,
            reservation.provider,
            reservation.model,
        )
        return LaunchOperationIntent(
            operation_id=operation_id,
            ordinal=ordinal,
            stable_source_id=node_id,
            question=question,
            payload_digest=payload_digest,
            provider=reservation.provider,
            model=reservation.model,
            logical_operation_id=logical_id,
            state=(
                LaunchOperationState.PENDING
                if eligible
                else LaunchOperationState.BLOCKED_PROVIDER_INELIGIBLE
            ),
            blocked_reason=None if eligible else "bound_provider_route_has_no_eligible_adapter",
        )


__all__ = ["EligibleAdapterRegistry", "EligibleResearchAdapter", "MultimediaResearchLaunchExecutor"]
