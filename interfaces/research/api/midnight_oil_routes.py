"""Midnight-oil autonomous research preflight API.

This route is intentionally a preflight only. It validates the operator's
approved time/price/route/source envelope and returns the role allocation that
a future runner must obey; it does not launch agents or reserve budget.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from substrate.midnight_oil import (
    MidnightOilActivationChecklistReceipt,
    MidnightOilActivationChecklistRequest,
    MidnightOilAppliedRunReceipt,
    MidnightOilBudgetProviderAdapterPlanReceipt,
    MidnightOilBudgetProviderAdapterPlanRequest,
    MidnightOilBudgetReservationReceipt,
    MidnightOilBudgetReservationRequest,
    MidnightOilControlLedgerAdapterPlanReceipt,
    MidnightOilControlLedgerAdapterPlanRequest,
    MidnightOilControlLedgerPersistenceApplyPlanReceipt,
    MidnightOilControlLedgerPersistenceApplyPlanRequest,
    MidnightOilControlLedgerPersistencePlanReceipt,
    MidnightOilControlLedgerPersistencePlanRequest,
    MidnightOilDispatchReceipt,
    MidnightOilDispatchRequest,
    MidnightOilDryRunRequest,
    MidnightOilFinalArtifactAdapterPlanReceipt,
    MidnightOilFinalArtifactAdapterPlanRequest,
    MidnightOilFinalArtifactCompletionFinalizationPlanReceipt,
    MidnightOilFinalArtifactCompletionFinalizationPlanRequest,
    MidnightOilFinalArtifactGraphCommitPlanReceipt,
    MidnightOilFinalArtifactGraphCommitPlanRequest,
    MidnightOilFinalArtifactPersistencePlanReceipt,
    MidnightOilFinalArtifactPersistencePlanRequest,
    MidnightOilFinalArtifactPublishPlanReceipt,
    MidnightOilFinalArtifactPublishPlanRequest,
    MidnightOilFinalArtifactReceipt,
    MidnightOilFinalArtifactRequest,
    MidnightOilFinalHtmlArtifactAssemblyPlanReceipt,
    MidnightOilFinalHtmlArtifactAssemblyPlanRequest,
    MidnightOilFinalRunClosurePlanReceipt,
    MidnightOilFinalRunClosurePlanRequest,
    MidnightOilFinalSynthesisDraftPlanReceipt,
    MidnightOilFinalSynthesisDraftPlanRequest,
    MidnightOilGraphAdapterPlanReceipt,
    MidnightOilGraphAdapterPlanRequest,
    MidnightOilGraphMutationReceipt,
    MidnightOilGraphMutationRequest,
    MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt,
    MidnightOilLiveDispatchFinalEnablementApplyPlanRequest,
    MidnightOilLiveDispatchFinalEnablementPlanReceipt,
    MidnightOilLiveDispatchFinalEnablementPlanRequest,
    MidnightOilLiveRunActivationSettingsReceipt,
    MidnightOilLiveRunActivationSettingsRequest,
    MidnightOilOperatorDispatchActivationReadinessPlanReceipt,
    MidnightOilOperatorDispatchActivationReadinessPlanRequest,
    MidnightOilOperatorDispatchAdapterPlanReceipt,
    MidnightOilOperatorDispatchAdapterPlanRequest,
    MidnightOilOperatorNotificationDeliveryApplyPlanReceipt,
    MidnightOilOperatorNotificationDeliveryApplyPlanRequest,
    MidnightOilOperatorNotificationDeliveryReadinessPlanReceipt,
    MidnightOilOperatorNotificationDeliveryReadinessPlanRequest,
    MidnightOilOperatorNotificationDeliveryResultReconciliationPlanReceipt,
    MidnightOilOperatorNotificationDeliveryResultReconciliationPlanRequest,
    MidnightOilPreflight,
    MidnightOilProviderExecutorAdapterPlanReceipt,
    MidnightOilProviderExecutorAdapterPlanRequest,
    MidnightOilProviderRouteReceipt,
    MidnightOilProviderRouteRequest,
    MidnightOilRepositoryCommitRollbackPlanReceipt,
    MidnightOilRepositoryCommitRollbackPlanRequest,
    MidnightOilRepositoryTransactionPlanReceipt,
    MidnightOilRepositoryTransactionPlanRequest,
    MidnightOilRequest,
    MidnightOilRetrievalAdapterPlanReceipt,
    MidnightOilRetrievalAdapterPlanRequest,
    MidnightOilRetrievalReceipt,
    MidnightOilRetrievalRequest,
    MidnightOilRunnerControlPlanReceipt,
    MidnightOilRunnerControlPlanRequest,
    MidnightOilRunnerDispatchSchedulerPlanReceipt,
    MidnightOilRunnerDispatchSchedulerPlanRequest,
    MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt,
    MidnightOilRunnerDispatchWorkerBootstrapPlanRequest,
    MidnightOilRunnerReadinessReceipt,
    MidnightOilRunnerReadinessRequest,
    MidnightOilSchedulerLeaseRetryPlanReceipt,
    MidnightOilSchedulerLeaseRetryPlanRequest,
    MidnightOilSynthesisBundleAssemblyPlanReceipt,
    MidnightOilSynthesisBundleAssemblyPlanRequest,
    MidnightOilWorkerCancellationAbandonPlanReceipt,
    MidnightOilWorkerCancellationAbandonPlanRequest,
    MidnightOilWorkerCompletionFinalizationPlanReceipt,
    MidnightOilWorkerCompletionFinalizationPlanRequest,
    MidnightOilWorkerDispatchLeaseHeartbeatPlanReceipt,
    MidnightOilWorkerDispatchLeaseHeartbeatPlanRequest,
    MidnightOilWorkerOutputAggregationPlanReceipt,
    MidnightOilWorkerOutputAggregationPlanRequest,
    MidnightOilWorkerQueueClaimPlanReceipt,
    MidnightOilWorkerQueueClaimPlanRequest,
    MidnightOilWorkerSynthesisHandoffPlanReceipt,
    MidnightOilWorkerSynthesisHandoffPlanRequest,
    activation_checklist_midnight_oil,
    budget_provider_adapter_plan_midnight_oil,
    budget_reservation_midnight_oil,
    control_ledger_adapter_plan_midnight_oil,
    control_ledger_persistence_apply_plan_midnight_oil,
    control_ledger_persistence_plan_midnight_oil,
    dispatch_midnight_oil,
    dry_run_midnight_oil,
    final_artifact_adapter_plan_midnight_oil,
    final_artifact_completion_finalization_plan_midnight_oil,
    final_artifact_graph_commit_plan_midnight_oil,
    final_artifact_midnight_oil,
    final_artifact_persistence_plan_midnight_oil,
    final_artifact_publish_plan_midnight_oil,
    final_html_artifact_assembly_plan_midnight_oil,
    final_run_closure_plan_midnight_oil,
    final_synthesis_draft_plan_midnight_oil,
    graph_adapter_plan_midnight_oil,
    graph_mutation_midnight_oil,
    live_dispatch_final_enablement_apply_plan_midnight_oil,
    live_dispatch_final_enablement_plan_midnight_oil,
    live_run_activation_settings_midnight_oil,
    operator_dispatch_activation_readiness_plan_midnight_oil,
    operator_dispatch_adapter_plan_midnight_oil,
    operator_notification_delivery_apply_plan_midnight_oil,
    operator_notification_delivery_readiness_plan_midnight_oil,
    operator_notification_delivery_result_reconciliation_plan_midnight_oil,
    preflight_midnight_oil,
    provider_executor_adapter_plan_midnight_oil,
    provider_route_midnight_oil,
    repository_commit_rollback_plan_midnight_oil,
    repository_transaction_plan_midnight_oil,
    retrieval_adapter_plan_midnight_oil,
    retrieval_midnight_oil,
    runner_control_plan_midnight_oil,
    runner_dispatch_scheduler_plan_midnight_oil,
    runner_dispatch_worker_bootstrap_plan_midnight_oil,
    runner_readiness_midnight_oil,
    scheduler_lease_retry_plan_midnight_oil,
    synthesis_bundle_assembly_plan_midnight_oil,
    worker_cancellation_abandon_plan_midnight_oil,
    worker_completion_finalization_plan_midnight_oil,
    worker_dispatch_lease_heartbeat_plan_midnight_oil,
    worker_output_aggregation_plan_midnight_oil,
    worker_queue_claim_plan_midnight_oil,
    worker_synthesis_handoff_plan_midnight_oil,
)

midnight_oil_router = APIRouter(prefix="/research/midnight-oil", tags=["deep-research"])


@midnight_oil_router.post("/preflight", response_model=MidnightOilPreflight)
def post_midnight_oil_preflight(req: MidnightOilRequest) -> MidnightOilPreflight:
    return preflight_midnight_oil(req)


@midnight_oil_router.post("/dry-run", response_model=MidnightOilAppliedRunReceipt)
def post_midnight_oil_dry_run(req: MidnightOilDryRunRequest) -> MidnightOilAppliedRunReceipt:
    return dry_run_midnight_oil(req)


@midnight_oil_router.post(
    "/live-run-activation-settings",
    response_model=MidnightOilLiveRunActivationSettingsReceipt,
)
def post_midnight_oil_live_run_activation_settings(
    req: MidnightOilLiveRunActivationSettingsRequest,
) -> MidnightOilLiveRunActivationSettingsReceipt:
    return live_run_activation_settings_midnight_oil(req)


@midnight_oil_router.post("/dispatch", response_model=MidnightOilDispatchReceipt)
def post_midnight_oil_dispatch(req: MidnightOilDispatchRequest) -> MidnightOilDispatchReceipt:
    return dispatch_midnight_oil(req)


@midnight_oil_router.post("/activation-checklist", response_model=MidnightOilActivationChecklistReceipt)
def post_midnight_oil_activation_checklist(
    req: MidnightOilActivationChecklistRequest,
) -> MidnightOilActivationChecklistReceipt:
    return activation_checklist_midnight_oil(req)


@midnight_oil_router.post("/budget-reservation", response_model=MidnightOilBudgetReservationReceipt)
def post_midnight_oil_budget_reservation(
    req: MidnightOilBudgetReservationRequest,
) -> MidnightOilBudgetReservationReceipt:
    return budget_reservation_midnight_oil(req)


@midnight_oil_router.post("/provider-route", response_model=MidnightOilProviderRouteReceipt)
def post_midnight_oil_provider_route(
    req: MidnightOilProviderRouteRequest,
) -> MidnightOilProviderRouteReceipt:
    return provider_route_midnight_oil(req)


@midnight_oil_router.post("/retrieval", response_model=MidnightOilRetrievalReceipt)
def post_midnight_oil_retrieval(
    req: MidnightOilRetrievalRequest,
) -> MidnightOilRetrievalReceipt:
    return retrieval_midnight_oil(req)


@midnight_oil_router.post("/graph-mutation", response_model=MidnightOilGraphMutationReceipt)
def post_midnight_oil_graph_mutation(
    req: MidnightOilGraphMutationRequest,
) -> MidnightOilGraphMutationReceipt:
    return graph_mutation_midnight_oil(req)


@midnight_oil_router.post("/final-artifact", response_model=MidnightOilFinalArtifactReceipt)
def post_midnight_oil_final_artifact(
    req: MidnightOilFinalArtifactRequest,
) -> MidnightOilFinalArtifactReceipt:
    return final_artifact_midnight_oil(req)


@midnight_oil_router.post("/runner-readiness", response_model=MidnightOilRunnerReadinessReceipt)
def post_midnight_oil_runner_readiness(
    req: MidnightOilRunnerReadinessRequest,
) -> MidnightOilRunnerReadinessReceipt:
    return runner_readiness_midnight_oil(req)


@midnight_oil_router.post("/runner-control-plan", response_model=MidnightOilRunnerControlPlanReceipt)
def post_midnight_oil_runner_control_plan(
    req: MidnightOilRunnerControlPlanRequest,
) -> MidnightOilRunnerControlPlanReceipt:
    return runner_control_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/budget-provider-adapter-plan",
    response_model=MidnightOilBudgetProviderAdapterPlanReceipt,
)
def post_midnight_oil_budget_provider_adapter_plan(
    req: MidnightOilBudgetProviderAdapterPlanRequest,
) -> MidnightOilBudgetProviderAdapterPlanReceipt:
    return budget_provider_adapter_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/provider-executor-adapter-plan",
    response_model=MidnightOilProviderExecutorAdapterPlanReceipt,
)
def post_midnight_oil_provider_executor_adapter_plan(
    req: MidnightOilProviderExecutorAdapterPlanRequest,
) -> MidnightOilProviderExecutorAdapterPlanReceipt:
    return provider_executor_adapter_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/retrieval-adapter-plan",
    response_model=MidnightOilRetrievalAdapterPlanReceipt,
)
def post_midnight_oil_retrieval_adapter_plan(
    req: MidnightOilRetrievalAdapterPlanRequest,
) -> MidnightOilRetrievalAdapterPlanReceipt:
    return retrieval_adapter_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/graph-adapter-plan",
    response_model=MidnightOilGraphAdapterPlanReceipt,
)
def post_midnight_oil_graph_adapter_plan(
    req: MidnightOilGraphAdapterPlanRequest,
) -> MidnightOilGraphAdapterPlanReceipt:
    return graph_adapter_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/final-artifact-adapter-plan",
    response_model=MidnightOilFinalArtifactAdapterPlanReceipt,
)
def post_midnight_oil_final_artifact_adapter_plan(
    req: MidnightOilFinalArtifactAdapterPlanRequest,
) -> MidnightOilFinalArtifactAdapterPlanReceipt:
    return final_artifact_adapter_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/operator-dispatch-adapter-plan",
    response_model=MidnightOilOperatorDispatchAdapterPlanReceipt,
)
def post_midnight_oil_operator_dispatch_adapter_plan(
    req: MidnightOilOperatorDispatchAdapterPlanRequest,
) -> MidnightOilOperatorDispatchAdapterPlanReceipt:
    return operator_dispatch_adapter_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/control-ledger-adapter-plan",
    response_model=MidnightOilControlLedgerAdapterPlanReceipt,
)
def post_midnight_oil_control_ledger_adapter_plan(
    req: MidnightOilControlLedgerAdapterPlanRequest,
) -> MidnightOilControlLedgerAdapterPlanReceipt:
    return control_ledger_adapter_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/control-ledger-persistence-plan",
    response_model=MidnightOilControlLedgerPersistencePlanReceipt,
)
def post_midnight_oil_control_ledger_persistence_plan(
    req: MidnightOilControlLedgerPersistencePlanRequest,
) -> MidnightOilControlLedgerPersistencePlanReceipt:
    return control_ledger_persistence_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/control-ledger-persistence-apply-plan",
    response_model=MidnightOilControlLedgerPersistenceApplyPlanReceipt,
)
def post_midnight_oil_control_ledger_persistence_apply_plan(
    req: MidnightOilControlLedgerPersistenceApplyPlanRequest,
) -> MidnightOilControlLedgerPersistenceApplyPlanReceipt:
    return control_ledger_persistence_apply_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/operator-dispatch-activation-readiness-plan",
    response_model=MidnightOilOperatorDispatchActivationReadinessPlanReceipt,
)
def post_midnight_oil_operator_dispatch_activation_readiness_plan(
    req: MidnightOilOperatorDispatchActivationReadinessPlanRequest,
) -> MidnightOilOperatorDispatchActivationReadinessPlanReceipt:
    return operator_dispatch_activation_readiness_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/live-dispatch-final-enablement-plan",
    response_model=MidnightOilLiveDispatchFinalEnablementPlanReceipt,
)
def post_midnight_oil_live_dispatch_final_enablement_plan(
    req: MidnightOilLiveDispatchFinalEnablementPlanRequest,
) -> MidnightOilLiveDispatchFinalEnablementPlanReceipt:
    return live_dispatch_final_enablement_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/live-dispatch-final-enablement-apply-plan",
    response_model=MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt,
)
def post_midnight_oil_live_dispatch_final_enablement_apply_plan(
    req: MidnightOilLiveDispatchFinalEnablementApplyPlanRequest,
) -> MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt:
    return live_dispatch_final_enablement_apply_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/runner-dispatch-scheduler-plan",
    response_model=MidnightOilRunnerDispatchSchedulerPlanReceipt,
)
def post_midnight_oil_runner_dispatch_scheduler_plan(
    req: MidnightOilRunnerDispatchSchedulerPlanRequest,
) -> MidnightOilRunnerDispatchSchedulerPlanReceipt:
    return runner_dispatch_scheduler_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/runner-dispatch-worker-bootstrap-plan",
    response_model=MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt,
)
def post_midnight_oil_runner_dispatch_worker_bootstrap_plan(
    req: MidnightOilRunnerDispatchWorkerBootstrapPlanRequest,
) -> MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt:
    return runner_dispatch_worker_bootstrap_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/scheduler-lease-retry-plan",
    response_model=MidnightOilSchedulerLeaseRetryPlanReceipt,
)
def post_midnight_oil_scheduler_lease_retry_plan(
    req: MidnightOilSchedulerLeaseRetryPlanRequest,
) -> MidnightOilSchedulerLeaseRetryPlanReceipt:
    return scheduler_lease_retry_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/worker-queue-claim-plan",
    response_model=MidnightOilWorkerQueueClaimPlanReceipt,
)
def post_midnight_oil_worker_queue_claim_plan(
    req: MidnightOilWorkerQueueClaimPlanRequest,
) -> MidnightOilWorkerQueueClaimPlanReceipt:
    return worker_queue_claim_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/repository-transaction-plan",
    response_model=MidnightOilRepositoryTransactionPlanReceipt,
)
def post_midnight_oil_repository_transaction_plan(
    req: MidnightOilRepositoryTransactionPlanRequest,
) -> MidnightOilRepositoryTransactionPlanReceipt:
    return repository_transaction_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/repository-commit-rollback-plan",
    response_model=MidnightOilRepositoryCommitRollbackPlanReceipt,
)
def post_midnight_oil_repository_commit_rollback_plan(
    req: MidnightOilRepositoryCommitRollbackPlanRequest,
) -> MidnightOilRepositoryCommitRollbackPlanReceipt:
    return repository_commit_rollback_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/worker-dispatch-lease-heartbeat-plan",
    response_model=MidnightOilWorkerDispatchLeaseHeartbeatPlanReceipt,
)
def post_midnight_oil_worker_dispatch_lease_heartbeat_plan(
    req: MidnightOilWorkerDispatchLeaseHeartbeatPlanRequest,
) -> MidnightOilWorkerDispatchLeaseHeartbeatPlanReceipt:
    return worker_dispatch_lease_heartbeat_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/worker-cancellation-abandon-plan",
    response_model=MidnightOilWorkerCancellationAbandonPlanReceipt,
)
def post_midnight_oil_worker_cancellation_abandon_plan(
    req: MidnightOilWorkerCancellationAbandonPlanRequest,
) -> MidnightOilWorkerCancellationAbandonPlanReceipt:
    return worker_cancellation_abandon_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/worker-completion-finalization-plan",
    response_model=MidnightOilWorkerCompletionFinalizationPlanReceipt,
)
def post_midnight_oil_worker_completion_finalization_plan(
    req: MidnightOilWorkerCompletionFinalizationPlanRequest,
) -> MidnightOilWorkerCompletionFinalizationPlanReceipt:
    return worker_completion_finalization_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/worker-output-aggregation-plan",
    response_model=MidnightOilWorkerOutputAggregationPlanReceipt,
)
def post_midnight_oil_worker_output_aggregation_plan(
    req: MidnightOilWorkerOutputAggregationPlanRequest,
) -> MidnightOilWorkerOutputAggregationPlanReceipt:
    return worker_output_aggregation_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/worker-synthesis-handoff-plan",
    response_model=MidnightOilWorkerSynthesisHandoffPlanReceipt,
)
def post_midnight_oil_worker_synthesis_handoff_plan(
    req: MidnightOilWorkerSynthesisHandoffPlanRequest,
) -> MidnightOilWorkerSynthesisHandoffPlanReceipt:
    return worker_synthesis_handoff_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/synthesis-bundle-assembly-plan",
    response_model=MidnightOilSynthesisBundleAssemblyPlanReceipt,
)
def post_midnight_oil_synthesis_bundle_assembly_plan(
    req: MidnightOilSynthesisBundleAssemblyPlanRequest,
) -> MidnightOilSynthesisBundleAssemblyPlanReceipt:
    return synthesis_bundle_assembly_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/final-synthesis-draft-plan",
    response_model=MidnightOilFinalSynthesisDraftPlanReceipt,
)
def post_midnight_oil_final_synthesis_draft_plan(
    req: MidnightOilFinalSynthesisDraftPlanRequest,
) -> MidnightOilFinalSynthesisDraftPlanReceipt:
    return final_synthesis_draft_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/final-html-artifact-assembly-plan",
    response_model=MidnightOilFinalHtmlArtifactAssemblyPlanReceipt,
)
def post_midnight_oil_final_html_artifact_assembly_plan(
    req: MidnightOilFinalHtmlArtifactAssemblyPlanRequest,
) -> MidnightOilFinalHtmlArtifactAssemblyPlanReceipt:
    return final_html_artifact_assembly_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/final-artifact-persistence-plan",
    response_model=MidnightOilFinalArtifactPersistencePlanReceipt,
)
def post_midnight_oil_final_artifact_persistence_plan(
    req: MidnightOilFinalArtifactPersistencePlanRequest,
) -> MidnightOilFinalArtifactPersistencePlanReceipt:
    return final_artifact_persistence_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/final-artifact-graph-commit-plan",
    response_model=MidnightOilFinalArtifactGraphCommitPlanReceipt,
)
def post_midnight_oil_final_artifact_graph_commit_plan(
    req: MidnightOilFinalArtifactGraphCommitPlanRequest,
) -> MidnightOilFinalArtifactGraphCommitPlanReceipt:
    return final_artifact_graph_commit_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/final-artifact-publish-plan",
    response_model=MidnightOilFinalArtifactPublishPlanReceipt,
)
def post_midnight_oil_final_artifact_publish_plan(
    req: MidnightOilFinalArtifactPublishPlanRequest,
) -> MidnightOilFinalArtifactPublishPlanReceipt:
    return final_artifact_publish_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/final-artifact-completion-finalization-plan",
    response_model=MidnightOilFinalArtifactCompletionFinalizationPlanReceipt,
)
def post_midnight_oil_final_artifact_completion_finalization_plan(
    req: MidnightOilFinalArtifactCompletionFinalizationPlanRequest,
) -> MidnightOilFinalArtifactCompletionFinalizationPlanReceipt:
    return final_artifact_completion_finalization_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/final-run-closure-plan",
    response_model=MidnightOilFinalRunClosurePlanReceipt,
)
def post_midnight_oil_final_run_closure_plan(
    req: MidnightOilFinalRunClosurePlanRequest,
) -> MidnightOilFinalRunClosurePlanReceipt:
    return final_run_closure_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/operator-notification-delivery-readiness-plan",
    response_model=MidnightOilOperatorNotificationDeliveryReadinessPlanReceipt,
)
def post_midnight_oil_operator_notification_delivery_readiness_plan(
    req: MidnightOilOperatorNotificationDeliveryReadinessPlanRequest,
) -> MidnightOilOperatorNotificationDeliveryReadinessPlanReceipt:
    return operator_notification_delivery_readiness_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/operator-notification-delivery-apply-plan",
    response_model=MidnightOilOperatorNotificationDeliveryApplyPlanReceipt,
)
def post_midnight_oil_operator_notification_delivery_apply_plan(
    req: MidnightOilOperatorNotificationDeliveryApplyPlanRequest,
) -> MidnightOilOperatorNotificationDeliveryApplyPlanReceipt:
    return operator_notification_delivery_apply_plan_midnight_oil(req)


@midnight_oil_router.post(
    "/operator-notification-delivery-result-reconciliation-plan",
    response_model=MidnightOilOperatorNotificationDeliveryResultReconciliationPlanReceipt,
)
def post_midnight_oil_operator_notification_delivery_result_reconciliation_plan(
    req: MidnightOilOperatorNotificationDeliveryResultReconciliationPlanRequest,
) -> MidnightOilOperatorNotificationDeliveryResultReconciliationPlanReceipt:
    return operator_notification_delivery_result_reconciliation_plan_midnight_oil(req)


def register_midnight_oil_routes(app: FastAPI) -> None:
    app.include_router(midnight_oil_router)


__all__ = [
    "midnight_oil_router",
    "post_midnight_oil_activation_checklist",
    "post_midnight_oil_budget_provider_adapter_plan",
    "post_midnight_oil_budget_reservation",
    "post_midnight_oil_control_ledger_adapter_plan",
    "post_midnight_oil_control_ledger_persistence_apply_plan",
    "post_midnight_oil_control_ledger_persistence_plan",
    "post_midnight_oil_dispatch",
    "post_midnight_oil_dry_run",
    "post_midnight_oil_final_artifact",
    "post_midnight_oil_final_artifact_adapter_plan",
    "post_midnight_oil_final_artifact_completion_finalization_plan",
    "post_midnight_oil_final_artifact_graph_commit_plan",
    "post_midnight_oil_final_artifact_persistence_plan",
    "post_midnight_oil_final_artifact_publish_plan",
    "post_midnight_oil_final_html_artifact_assembly_plan",
    "post_midnight_oil_final_run_closure_plan",
    "post_midnight_oil_final_synthesis_draft_plan",
    "post_midnight_oil_graph_adapter_plan",
    "post_midnight_oil_graph_mutation",
    "post_midnight_oil_live_dispatch_final_enablement_apply_plan",
    "post_midnight_oil_live_dispatch_final_enablement_plan",
    "post_midnight_oil_live_run_activation_settings",
    "post_midnight_oil_operator_dispatch_activation_readiness_plan",
    "post_midnight_oil_operator_dispatch_adapter_plan",
    "post_midnight_oil_operator_notification_delivery_apply_plan",
    "post_midnight_oil_operator_notification_delivery_readiness_plan",
    "post_midnight_oil_operator_notification_delivery_result_reconciliation_plan",
    "post_midnight_oil_preflight",
    "post_midnight_oil_provider_executor_adapter_plan",
    "post_midnight_oil_provider_route",
    "post_midnight_oil_repository_commit_rollback_plan",
    "post_midnight_oil_repository_transaction_plan",
    "post_midnight_oil_retrieval",
    "post_midnight_oil_retrieval_adapter_plan",
    "post_midnight_oil_runner_control_plan",
    "post_midnight_oil_runner_dispatch_scheduler_plan",
    "post_midnight_oil_runner_dispatch_worker_bootstrap_plan",
    "post_midnight_oil_runner_readiness",
    "post_midnight_oil_scheduler_lease_retry_plan",
    "post_midnight_oil_synthesis_bundle_assembly_plan",
    "post_midnight_oil_worker_cancellation_abandon_plan",
    "post_midnight_oil_worker_completion_finalization_plan",
    "post_midnight_oil_worker_dispatch_lease_heartbeat_plan",
    "post_midnight_oil_worker_output_aggregation_plan",
    "post_midnight_oil_worker_queue_claim_plan",
    "post_midnight_oil_worker_synthesis_handoff_plan",
    "register_midnight_oil_routes",
]
