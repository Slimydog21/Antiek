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
    MidnightOilBudgetReservationReceipt,
    MidnightOilBudgetReservationRequest,
    MidnightOilDispatchReceipt,
    MidnightOilDispatchRequest,
    MidnightOilDryRunRequest,
    MidnightOilFinalArtifactReceipt,
    MidnightOilFinalArtifactRequest,
    MidnightOilGraphMutationReceipt,
    MidnightOilGraphMutationRequest,
    MidnightOilLiveRunActivationSettingsReceipt,
    MidnightOilLiveRunActivationSettingsRequest,
    MidnightOilPreflight,
    MidnightOilProviderRouteReceipt,
    MidnightOilProviderRouteRequest,
    MidnightOilRequest,
    MidnightOilRetrievalReceipt,
    MidnightOilRetrievalRequest,
    MidnightOilRunnerReadinessReceipt,
    MidnightOilRunnerReadinessRequest,
    activation_checklist_midnight_oil,
    budget_reservation_midnight_oil,
    dispatch_midnight_oil,
    dry_run_midnight_oil,
    final_artifact_midnight_oil,
    graph_mutation_midnight_oil,
    live_run_activation_settings_midnight_oil,
    preflight_midnight_oil,
    provider_route_midnight_oil,
    retrieval_midnight_oil,
    runner_readiness_midnight_oil,
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


def register_midnight_oil_routes(app: FastAPI) -> None:
    app.include_router(midnight_oil_router)


__all__ = [
    "midnight_oil_router",
    "post_midnight_oil_activation_checklist",
    "post_midnight_oil_budget_reservation",
    "post_midnight_oil_dispatch",
    "post_midnight_oil_dry_run",
    "post_midnight_oil_final_artifact",
    "post_midnight_oil_graph_mutation",
    "post_midnight_oil_live_run_activation_settings",
    "post_midnight_oil_preflight",
    "post_midnight_oil_provider_route",
    "post_midnight_oil_retrieval",
    "post_midnight_oil_runner_readiness",
    "register_midnight_oil_routes",
]
