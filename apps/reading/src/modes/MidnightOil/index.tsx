import { useState } from "react";

import {
  activationChecklistMidnightOil,
  budgetProviderAdapterPlanMidnightOil,
  budgetReservationMidnightOil,
  controlLedgerAdapterPlanMidnightOil,
  controlLedgerPersistenceApplyPlanMidnightOil,
  controlLedgerPersistencePlanMidnightOil,
  deliveryNotificationReconciliationPlanMidnightOil,
  dispatchMidnightOil,
  dryRunMidnightOil,
  finalArtifactAdapterPlanMidnightOil,
  finalArtifactCompletionFinalizationPlanMidnightOil,
  finalArtifactGraphCommitPlanMidnightOil,
  finalArtifactMidnightOil,
  finalArtifactPersistencePlanMidnightOil,
  finalArtifactPublishPlanMidnightOil,
  finalCloseoutArchiveReconciliationPlanMidnightOil,
  finalRunClosurePlanMidnightOil,
  finalHtmlArtifactAssemblyPlanMidnightOil,
  finalSynthesisDraftPlanMidnightOil,
  graphAdapterPlanMidnightOil,
  graphMutationMidnightOil,
  liveDispatchFinalEnablementApplyPlanMidnightOil,
  liveDispatchFinalEnablementPlanMidnightOil,
  liveRunActivationSettingsMidnightOil,
  operatorArchiveHandoffPackageDeliveryAuditPlanMidnightOil,
  operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanMidnightOil,
  operatorArchiveHandoffPackagePlanMidnightOil,
  operatorArchiveHandoffPackageResultReconciliationPlanMidnightOil,
  operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanMidnightOil,
  operatorArchivePackageDeliveryReportDeliveryConfirmationPlanMidnightOil,
  operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanMidnightOil,
  operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanMidnightOil,
  operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanMidnightOil,
  operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanMidnightOil,
  operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanMidnightOil,
  operatorArchivePackageDeliveryReportPlanMidnightOil,
  operatorArchivePackageDeliveryReportNotificationReadinessPlanMidnightOil,
  operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanMidnightOil,
  operatorArchivePackageDeliveryReportResultReconciliationPlanMidnightOil,
  operatorDeliveryLedgerReconciliationPlanMidnightOil,
  operatorDispatchActivationReadinessPlanMidnightOil,
  operatorDispatchAdapterPlanMidnightOil,
  operatorNotificationDeliveryApplyPlanMidnightOil,
  operatorNotificationDeliveryReadinessPlanMidnightOil,
  operatorNotificationDeliveryResultReconciliationPlanMidnightOil,
  preflightMidnightOil,
  providerExecutorAdapterPlanMidnightOil,
  providerRouteMidnightOil,
  repositoryCommitRollbackPlanMidnightOil,
  repositoryTransactionPlanMidnightOil,
  retentionBillingReconciliationPlanMidnightOil,
  retrievalAdapterPlanMidnightOil,
  retrievalMidnightOil,
  runnerControlPlanMidnightOil,
  runnerDispatchSchedulerPlanMidnightOil,
  runnerDispatchWorkerBootstrapPlanMidnightOil,
  runnerReadinessMidnightOil,
  schedulerLeaseRetryPlanMidnightOil,
  synthesisBundleAssemblyPlanMidnightOil,
  workerCancellationAbandonPlanMidnightOil,
  workerCompletionFinalizationPlanMidnightOil,
  workerDispatchLeaseHeartbeatPlanMidnightOil,
  workerOutputAggregationPlanMidnightOil,
  workerQueueClaimPlanMidnightOil,
  workerSynthesisHandoffPlanMidnightOil,
  workspaceDeliveryCardReconciliationPlanMidnightOil,
  type MidnightOilActivationChecklistReceipt,
  type MidnightOilAppliedRunReceipt,
  type MidnightOilBudgetProviderAdapterPlanReceipt,
  type MidnightOilBudgetReservationReceipt,
  type MidnightOilControlLedgerAdapterPlanReceipt,
  type MidnightOilControlLedgerPersistenceApplyPlanReceipt,
  type MidnightOilControlLedgerPersistencePlanReceipt,
  type MidnightOilDeliveryNotificationReconciliationPlanReceipt,
  type MidnightOilDispatchReceipt,
  type MidnightOilFinalArtifactAdapterPlanReceipt,
  type MidnightOilFinalArtifactCompletionFinalizationPlanReceipt,
  type MidnightOilFinalArtifactGraphCommitPlanReceipt,
  type MidnightOilFinalArtifactReceipt,
  type MidnightOilFinalArtifactPersistencePlanReceipt,
  type MidnightOilFinalArtifactPublishPlanReceipt,
  type MidnightOilFinalCloseoutArchiveReconciliationPlanReceipt,
  type MidnightOilFinalRunClosurePlanReceipt,
  type MidnightOilFinalHtmlArtifactAssemblyPlanReceipt,
  type MidnightOilFinalSynthesisDraftPlanReceipt,
  type MidnightOilGraphAdapterPlanReceipt,
  type MidnightOilGraphMutationReceipt,
  type MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt,
  type MidnightOilLiveDispatchFinalEnablementPlanReceipt,
  type MidnightOilLiveRunActivationSettingsReceipt,
  type MidnightOilOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
  type MidnightOilOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
  type MidnightOilOperatorArchiveHandoffPackagePlanReceipt,
  type MidnightOilOperatorArchiveHandoffPackageResultReconciliationPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
  type MidnightOilOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
  type MidnightOilOperatorDeliveryLedgerReconciliationPlanReceipt,
  type MidnightOilOperatorDispatchActivationReadinessPlanReceipt,
  type MidnightOilOperatorDispatchAdapterPlanReceipt,
  type MidnightOilOperatorNotificationDeliveryApplyPlanReceipt,
  type MidnightOilOperatorNotificationDeliveryReadinessPlanReceipt,
  type MidnightOilOperatorNotificationDeliveryResultReconciliationPlanReceipt,
  type MidnightOilPreflight,
  type MidnightOilProviderExecutorAdapterPlanReceipt,
  type MidnightOilProviderRouteReceipt,
  type MidnightOilRepositoryCommitRollbackPlanReceipt,
  type MidnightOilRepositoryTransactionPlanReceipt,
  type MidnightOilRetentionBillingReconciliationPlanReceipt,
  type MidnightOilRetrievalAdapterPlanReceipt,
  type MidnightOilRetrievalReceipt,
  type MidnightOilRunnerControlPlanReceipt,
  type MidnightOilRunnerDispatchSchedulerPlanReceipt,
  type MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt,
  type MidnightOilRunnerReadinessReceipt,
  type MidnightOilRouteMode,
  type MidnightOilSchedulerLeaseRetryPlanReceipt,
  type MidnightOilSourcePolicy,
  type MidnightOilSynthesisBundleAssemblyPlanReceipt,
  type MidnightOilWorkerCancellationAbandonPlanReceipt,
  type MidnightOilWorkerCompletionFinalizationPlanReceipt,
  type MidnightOilWorkerDispatchLeaseHeartbeatPlanReceipt,
  type MidnightOilWorkerOutputAggregationPlanReceipt,
  type MidnightOilWorkerQueueClaimPlanReceipt,
  type MidnightOilWorkerSynthesisHandoffPlanReceipt,
  type MidnightOilWorkspaceDeliveryCardReconciliationPlanReceipt,
} from "../../api/midnightOil";
import LemonCard from "../../components/lemon/LemonCard";

const ROUTE_MODES: Array<{ value: MidnightOilRouteMode; label: string }> = [
  { value: "auto_balanced", label: "Balanced" },
  { value: "auto_quality", label: "Quality" },
  { value: "auto_cost", label: "Cost" },
  { value: "auto_latency", label: "Latency" },
];

const SOURCES: Array<{ value: MidnightOilSourcePolicy; label: string }> = [
  { value: "arxiv", label: "arXiv" },
  { value: "substack", label: "Substack" },
  { value: "web", label: "Web" },
  { value: "operator_corpus", label: "My corpus" },
];

export default function MidnightOil() {
  const [goal, setGoal] = useState("");
  const [workMinutes, setWorkMinutes] = useState(120);
  const [priceCeiling, setPriceCeiling] = useState(25);
  const [routeMode, setRouteMode] = useState<MidnightOilRouteMode>("auto_balanced");
  const [sourcePolicy, setSourcePolicy] = useState<MidnightOilSourcePolicy[]>([
    "arxiv",
    "substack",
    "operator_corpus",
  ]);
  const [ack, setAck] = useState(false);
  const [preflight, setPreflight] = useState<MidnightOilPreflight | null>(null);
  const [dryRunReceipt, setDryRunReceipt] = useState<MidnightOilAppliedRunReceipt | null>(null);
  const [liveSettingsReceipt, setLiveSettingsReceipt] =
    useState<MidnightOilLiveRunActivationSettingsReceipt | null>(null);
  const [dispatchReceipt, setDispatchReceipt] = useState<MidnightOilDispatchReceipt | null>(null);
  const [activationReceipt, setActivationReceipt] =
    useState<MidnightOilActivationChecklistReceipt | null>(null);
  const [budgetReservationReceipt, setBudgetReservationReceipt] =
    useState<MidnightOilBudgetReservationReceipt | null>(null);
  const [providerRouteReceipt, setProviderRouteReceipt] =
    useState<MidnightOilProviderRouteReceipt | null>(null);
  const [retrievalReceipt, setRetrievalReceipt] = useState<MidnightOilRetrievalReceipt | null>(null);
  const [graphMutationReceipt, setGraphMutationReceipt] =
    useState<MidnightOilGraphMutationReceipt | null>(null);
  const [finalArtifactReceipt, setFinalArtifactReceipt] =
    useState<MidnightOilFinalArtifactReceipt | null>(null);
  const [runnerReadinessReceipt, setRunnerReadinessReceipt] =
    useState<MidnightOilRunnerReadinessReceipt | null>(null);
  const [runnerControlPlanReceipt, setRunnerControlPlanReceipt] =
    useState<MidnightOilRunnerControlPlanReceipt | null>(null);
  const [budgetProviderAdapterPlanReceipt, setBudgetProviderAdapterPlanReceipt] =
    useState<MidnightOilBudgetProviderAdapterPlanReceipt | null>(null);
  const [providerExecutorAdapterPlanReceipt, setProviderExecutorAdapterPlanReceipt] =
    useState<MidnightOilProviderExecutorAdapterPlanReceipt | null>(null);
  const [retrievalAdapterPlanReceipt, setRetrievalAdapterPlanReceipt] =
    useState<MidnightOilRetrievalAdapterPlanReceipt | null>(null);
  const [graphAdapterPlanReceipt, setGraphAdapterPlanReceipt] =
    useState<MidnightOilGraphAdapterPlanReceipt | null>(null);
  const [finalArtifactAdapterPlanReceipt, setFinalArtifactAdapterPlanReceipt] =
    useState<MidnightOilFinalArtifactAdapterPlanReceipt | null>(null);
  const [operatorDispatchAdapterPlanReceipt, setOperatorDispatchAdapterPlanReceipt] =
    useState<MidnightOilOperatorDispatchAdapterPlanReceipt | null>(null);
  const [controlLedgerAdapterPlanReceipt, setControlLedgerAdapterPlanReceipt] =
    useState<MidnightOilControlLedgerAdapterPlanReceipt | null>(null);
  const [controlLedgerPersistencePlanReceipt, setControlLedgerPersistencePlanReceipt] =
    useState<MidnightOilControlLedgerPersistencePlanReceipt | null>(null);
  const [controlLedgerPersistenceApplyPlanReceipt, setControlLedgerPersistenceApplyPlanReceipt] =
    useState<MidnightOilControlLedgerPersistenceApplyPlanReceipt | null>(null);
  const [
    operatorDispatchActivationReadinessPlanReceipt,
    setOperatorDispatchActivationReadinessPlanReceipt,
  ] = useState<MidnightOilOperatorDispatchActivationReadinessPlanReceipt | null>(null);
  const [liveDispatchFinalEnablementPlanReceipt, setLiveDispatchFinalEnablementPlanReceipt] =
    useState<MidnightOilLiveDispatchFinalEnablementPlanReceipt | null>(null);
  const [
    liveDispatchFinalEnablementApplyPlanReceipt,
    setLiveDispatchFinalEnablementApplyPlanReceipt,
  ] = useState<MidnightOilLiveDispatchFinalEnablementApplyPlanReceipt | null>(null);
  const [runnerDispatchSchedulerPlanReceipt, setRunnerDispatchSchedulerPlanReceipt] =
    useState<MidnightOilRunnerDispatchSchedulerPlanReceipt | null>(null);
  const [
    runnerDispatchWorkerBootstrapPlanReceipt,
    setRunnerDispatchWorkerBootstrapPlanReceipt,
  ] = useState<MidnightOilRunnerDispatchWorkerBootstrapPlanReceipt | null>(null);
  const [schedulerLeaseRetryPlanReceipt, setSchedulerLeaseRetryPlanReceipt] =
    useState<MidnightOilSchedulerLeaseRetryPlanReceipt | null>(null);
  const [workerQueueClaimPlanReceipt, setWorkerQueueClaimPlanReceipt] =
    useState<MidnightOilWorkerQueueClaimPlanReceipt | null>(null);
  const [repositoryTransactionPlanReceipt, setRepositoryTransactionPlanReceipt] =
    useState<MidnightOilRepositoryTransactionPlanReceipt | null>(null);
  const [repositoryCommitRollbackPlanReceipt, setRepositoryCommitRollbackPlanReceipt] =
    useState<MidnightOilRepositoryCommitRollbackPlanReceipt | null>(null);
  const [workerDispatchLeaseHeartbeatPlanReceipt, setWorkerDispatchLeaseHeartbeatPlanReceipt] =
    useState<MidnightOilWorkerDispatchLeaseHeartbeatPlanReceipt | null>(null);
  const [workerCancellationAbandonPlanReceipt, setWorkerCancellationAbandonPlanReceipt] =
    useState<MidnightOilWorkerCancellationAbandonPlanReceipt | null>(null);
  const [workerCompletionFinalizationPlanReceipt, setWorkerCompletionFinalizationPlanReceipt] =
    useState<MidnightOilWorkerCompletionFinalizationPlanReceipt | null>(null);
  const [workerOutputAggregationPlanReceipt, setWorkerOutputAggregationPlanReceipt] =
    useState<MidnightOilWorkerOutputAggregationPlanReceipt | null>(null);
  const [workerSynthesisHandoffPlanReceipt, setWorkerSynthesisHandoffPlanReceipt] =
    useState<MidnightOilWorkerSynthesisHandoffPlanReceipt | null>(null);
  const [synthesisBundleAssemblyPlanReceipt, setSynthesisBundleAssemblyPlanReceipt] =
    useState<MidnightOilSynthesisBundleAssemblyPlanReceipt | null>(null);
  const [finalSynthesisDraftPlanReceipt, setFinalSynthesisDraftPlanReceipt] =
    useState<MidnightOilFinalSynthesisDraftPlanReceipt | null>(null);
  const [finalHtmlArtifactAssemblyPlanReceipt, setFinalHtmlArtifactAssemblyPlanReceipt] =
    useState<MidnightOilFinalHtmlArtifactAssemblyPlanReceipt | null>(null);
  const [finalArtifactPersistencePlanReceipt, setFinalArtifactPersistencePlanReceipt] =
    useState<MidnightOilFinalArtifactPersistencePlanReceipt | null>(null);
  const [finalArtifactGraphCommitPlanReceipt, setFinalArtifactGraphCommitPlanReceipt] =
    useState<MidnightOilFinalArtifactGraphCommitPlanReceipt | null>(null);
  const [finalArtifactPublishPlanReceipt, setFinalArtifactPublishPlanReceipt] =
    useState<MidnightOilFinalArtifactPublishPlanReceipt | null>(null);
  const [
    finalArtifactCompletionFinalizationPlanReceipt,
    setFinalArtifactCompletionFinalizationPlanReceipt,
  ] = useState<MidnightOilFinalArtifactCompletionFinalizationPlanReceipt | null>(null);
  const [finalRunClosurePlanReceipt, setFinalRunClosurePlanReceipt] =
    useState<MidnightOilFinalRunClosurePlanReceipt | null>(null);
  const [
    operatorNotificationDeliveryReadinessPlanReceipt,
    setOperatorNotificationDeliveryReadinessPlanReceipt,
  ] = useState<MidnightOilOperatorNotificationDeliveryReadinessPlanReceipt | null>(null);
  const [
    operatorNotificationDeliveryApplyPlanReceipt,
    setOperatorNotificationDeliveryApplyPlanReceipt,
  ] = useState<MidnightOilOperatorNotificationDeliveryApplyPlanReceipt | null>(null);
  const [
    operatorNotificationDeliveryResultReconciliationPlanReceipt,
    setOperatorNotificationDeliveryResultReconciliationPlanReceipt,
  ] = useState<MidnightOilOperatorNotificationDeliveryResultReconciliationPlanReceipt | null>(
    null,
  );
  const [
    operatorDeliveryLedgerReconciliationPlanReceipt,
    setOperatorDeliveryLedgerReconciliationPlanReceipt,
  ] = useState<MidnightOilOperatorDeliveryLedgerReconciliationPlanReceipt | null>(null);
  const [
    workspaceDeliveryCardReconciliationPlanReceipt,
    setWorkspaceDeliveryCardReconciliationPlanReceipt,
  ] = useState<MidnightOilWorkspaceDeliveryCardReconciliationPlanReceipt | null>(null);
  const [
    deliveryNotificationReconciliationPlanReceipt,
    setDeliveryNotificationReconciliationPlanReceipt,
  ] = useState<MidnightOilDeliveryNotificationReconciliationPlanReceipt | null>(null);
  const [
    retentionBillingReconciliationPlanReceipt,
    setRetentionBillingReconciliationPlanReceipt,
  ] = useState<MidnightOilRetentionBillingReconciliationPlanReceipt | null>(null);
  const [
    finalCloseoutArchiveReconciliationPlanReceipt,
    setFinalCloseoutArchiveReconciliationPlanReceipt,
  ] = useState<MidnightOilFinalCloseoutArchiveReconciliationPlanReceipt | null>(null);
  const [
    operatorArchiveHandoffPackagePlanReceipt,
    setOperatorArchiveHandoffPackagePlanReceipt,
  ] = useState<MidnightOilOperatorArchiveHandoffPackagePlanReceipt | null>(null);
  const [
    operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
    setOperatorArchiveHandoffPackageResultReconciliationPlanReceipt,
  ] = useState<MidnightOilOperatorArchiveHandoffPackageResultReconciliationPlanReceipt | null>(
    null,
  );
  const [
    operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
    setOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
  ] = useState<MidnightOilOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt | null>(
    null,
  );
  const [
    operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
    setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
  ] = useState<MidnightOilOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt | null>(
    null,
  );
  const [
    operatorArchivePackageDeliveryReportPlanReceipt,
    setOperatorArchivePackageDeliveryReportPlanReceipt,
  ] = useState<MidnightOilOperatorArchivePackageDeliveryReportPlanReceipt | null>(
    null,
  );
  const [
    operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
    setOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
  ] =
    useState<MidnightOilOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt | null>(
      null,
    );
  const [
    operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
    setOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
  ] =
    useState<MidnightOilOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt | null>(
      null,
    );
  const [
    operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
    setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
  ] =
    useState<MidnightOilOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt | null>(
      null,
    );
  const [
    operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt,
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt,
  ] =
    useState<MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt | null>(
      null,
    );
  const [
    operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt,
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt,
  ] =
    useState<MidnightOilOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt | null>(
      null,
    );
  const [
    operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt,
    setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt,
  ] =
    useState<MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt | null>(
      null,
    );
  const [
    operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt,
    setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt,
  ] =
    useState<MidnightOilOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt | null>(
      null,
    );
  const [
    operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt,
    setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt,
  ] =
    useState<MidnightOilOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt | null>(
      null,
    );
  const [
    operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt,
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt,
  ] =
    useState<MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt | null>(
      null,
    );
  const [
    operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt,
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt,
  ] =
    useState<MidnightOilOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt | null>(
      null,
    );
  const [busy, setBusy] = useState(false);
  const [dryRunBusy, setDryRunBusy] = useState(false);
  const [liveSettingsBusy, setLiveSettingsBusy] = useState(false);
  const [dispatchBusy, setDispatchBusy] = useState(false);
  const [activationBusy, setActivationBusy] = useState(false);
  const [budgetReservationBusy, setBudgetReservationBusy] = useState(false);
  const [providerRouteBusy, setProviderRouteBusy] = useState(false);
  const [retrievalBusy, setRetrievalBusy] = useState(false);
  const [graphMutationBusy, setGraphMutationBusy] = useState(false);
  const [finalArtifactBusy, setFinalArtifactBusy] = useState(false);
  const [runnerReadinessBusy, setRunnerReadinessBusy] = useState(false);
  const [runnerControlPlanBusy, setRunnerControlPlanBusy] = useState(false);
  const [budgetProviderAdapterPlanBusy, setBudgetProviderAdapterPlanBusy] = useState(false);
  const [providerExecutorAdapterPlanBusy, setProviderExecutorAdapterPlanBusy] = useState(false);
  const [retrievalAdapterPlanBusy, setRetrievalAdapterPlanBusy] = useState(false);
  const [graphAdapterPlanBusy, setGraphAdapterPlanBusy] = useState(false);
  const [finalArtifactAdapterPlanBusy, setFinalArtifactAdapterPlanBusy] = useState(false);
  const [operatorDispatchAdapterPlanBusy, setOperatorDispatchAdapterPlanBusy] = useState(false);
  const [controlLedgerAdapterPlanBusy, setControlLedgerAdapterPlanBusy] = useState(false);
  const [controlLedgerPersistencePlanBusy, setControlLedgerPersistencePlanBusy] = useState(false);
  const [controlLedgerPersistenceApplyPlanBusy, setControlLedgerPersistenceApplyPlanBusy] =
    useState(false);
  const [
    operatorDispatchActivationReadinessPlanBusy,
    setOperatorDispatchActivationReadinessPlanBusy,
  ] = useState(false);
  const [liveDispatchFinalEnablementPlanBusy, setLiveDispatchFinalEnablementPlanBusy] =
    useState(false);
  const [
    liveDispatchFinalEnablementApplyPlanBusy,
    setLiveDispatchFinalEnablementApplyPlanBusy,
  ] = useState(false);
  const [runnerDispatchSchedulerPlanBusy, setRunnerDispatchSchedulerPlanBusy] = useState(false);
  const [runnerDispatchWorkerBootstrapPlanBusy, setRunnerDispatchWorkerBootstrapPlanBusy] =
    useState(false);
  const [schedulerLeaseRetryPlanBusy, setSchedulerLeaseRetryPlanBusy] = useState(false);
  const [workerQueueClaimPlanBusy, setWorkerQueueClaimPlanBusy] = useState(false);
  const [repositoryTransactionPlanBusy, setRepositoryTransactionPlanBusy] = useState(false);
  const [repositoryCommitRollbackPlanBusy, setRepositoryCommitRollbackPlanBusy] = useState(false);
  const [workerDispatchLeaseHeartbeatPlanBusy, setWorkerDispatchLeaseHeartbeatPlanBusy] =
    useState(false);
  const [workerCancellationAbandonPlanBusy, setWorkerCancellationAbandonPlanBusy] =
    useState(false);
  const [workerCompletionFinalizationPlanBusy, setWorkerCompletionFinalizationPlanBusy] =
    useState(false);
  const [workerOutputAggregationPlanBusy, setWorkerOutputAggregationPlanBusy] = useState(false);
  const [workerSynthesisHandoffPlanBusy, setWorkerSynthesisHandoffPlanBusy] = useState(false);
  const [synthesisBundleAssemblyPlanBusy, setSynthesisBundleAssemblyPlanBusy] = useState(false);
  const [finalSynthesisDraftPlanBusy, setFinalSynthesisDraftPlanBusy] = useState(false);
  const [finalHtmlArtifactAssemblyPlanBusy, setFinalHtmlArtifactAssemblyPlanBusy] =
    useState(false);
  const [finalArtifactPersistencePlanBusy, setFinalArtifactPersistencePlanBusy] =
    useState(false);
  const [finalArtifactGraphCommitPlanBusy, setFinalArtifactGraphCommitPlanBusy] =
    useState(false);
  const [finalArtifactPublishPlanBusy, setFinalArtifactPublishPlanBusy] = useState(false);
  const [
    finalArtifactCompletionFinalizationPlanBusy,
    setFinalArtifactCompletionFinalizationPlanBusy,
  ] = useState(false);
  const [finalRunClosurePlanBusy, setFinalRunClosurePlanBusy] = useState(false);
  const [
    operatorNotificationDeliveryReadinessPlanBusy,
    setOperatorNotificationDeliveryReadinessPlanBusy,
  ] = useState(false);
  const [
    operatorNotificationDeliveryApplyPlanBusy,
    setOperatorNotificationDeliveryApplyPlanBusy,
  ] = useState(false);
  const [
    operatorNotificationDeliveryResultReconciliationPlanBusy,
    setOperatorNotificationDeliveryResultReconciliationPlanBusy,
  ] = useState(false);
  const [
    operatorDeliveryLedgerReconciliationPlanBusy,
    setOperatorDeliveryLedgerReconciliationPlanBusy,
  ] = useState(false);
  const [
    workspaceDeliveryCardReconciliationPlanBusy,
    setWorkspaceDeliveryCardReconciliationPlanBusy,
  ] = useState(false);
  const [
    deliveryNotificationReconciliationPlanBusy,
    setDeliveryNotificationReconciliationPlanBusy,
  ] = useState(false);
  const [
    retentionBillingReconciliationPlanBusy,
    setRetentionBillingReconciliationPlanBusy,
  ] = useState(false);
  const [
    finalCloseoutArchiveReconciliationPlanBusy,
    setFinalCloseoutArchiveReconciliationPlanBusy,
  ] = useState(false);
  const [
    operatorArchiveHandoffPackagePlanBusy,
    setOperatorArchiveHandoffPackagePlanBusy,
  ] = useState(false);
  const [
    operatorArchiveHandoffPackageResultReconciliationPlanBusy,
    setOperatorArchiveHandoffPackageResultReconciliationPlanBusy,
  ] = useState(false);
  const [
    operatorArchiveHandoffPackageDeliveryAuditPlanBusy,
    setOperatorArchiveHandoffPackageDeliveryAuditPlanBusy,
  ] = useState(false);
  const [
    operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanBusy,
    setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportPlanBusy,
    setOperatorArchivePackageDeliveryReportPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportResultReconciliationPlanBusy,
    setOperatorArchivePackageDeliveryReportResultReconciliationPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportNotificationReadinessPlanBusy,
    setOperatorArchivePackageDeliveryReportNotificationReadinessPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanBusy,
    setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportDeliveryConfirmationPlanBusy,
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanBusy,
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanBusy,
    setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanBusy,
    setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanBusy,
    setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanBusy,
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanBusy,
  ] = useState(false);
  const [
    operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanBusy,
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanBusy,
  ] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dryRunError, setDryRunError] = useState<string | null>(null);
  const [liveSettingsError, setLiveSettingsError] = useState<string | null>(null);
  const [dispatchError, setDispatchError] = useState<string | null>(null);
  const [activationError, setActivationError] = useState<string | null>(null);
  const [budgetReservationError, setBudgetReservationError] = useState<string | null>(null);
  const [providerRouteError, setProviderRouteError] = useState<string | null>(null);
  const [retrievalError, setRetrievalError] = useState<string | null>(null);
  const [graphMutationError, setGraphMutationError] = useState<string | null>(null);
  const [finalArtifactError, setFinalArtifactError] = useState<string | null>(null);
  const [runnerReadinessError, setRunnerReadinessError] = useState<string | null>(null);
  const [runnerControlPlanError, setRunnerControlPlanError] = useState<string | null>(null);
  const [budgetProviderAdapterPlanError, setBudgetProviderAdapterPlanError] =
    useState<string | null>(null);
  const [providerExecutorAdapterPlanError, setProviderExecutorAdapterPlanError] =
    useState<string | null>(null);
  const [retrievalAdapterPlanError, setRetrievalAdapterPlanError] = useState<string | null>(null);
  const [graphAdapterPlanError, setGraphAdapterPlanError] = useState<string | null>(null);
  const [finalArtifactAdapterPlanError, setFinalArtifactAdapterPlanError] =
    useState<string | null>(null);
  const [operatorDispatchAdapterPlanError, setOperatorDispatchAdapterPlanError] =
    useState<string | null>(null);
  const [controlLedgerAdapterPlanError, setControlLedgerAdapterPlanError] =
    useState<string | null>(null);
  const [controlLedgerPersistencePlanError, setControlLedgerPersistencePlanError] =
    useState<string | null>(null);
  const [controlLedgerPersistenceApplyPlanError, setControlLedgerPersistenceApplyPlanError] =
    useState<string | null>(null);
  const [
    operatorDispatchActivationReadinessPlanError,
    setOperatorDispatchActivationReadinessPlanError,
  ] = useState<string | null>(null);
  const [liveDispatchFinalEnablementPlanError, setLiveDispatchFinalEnablementPlanError] =
    useState<string | null>(null);
  const [
    liveDispatchFinalEnablementApplyPlanError,
    setLiveDispatchFinalEnablementApplyPlanError,
  ] = useState<string | null>(null);
  const [runnerDispatchSchedulerPlanError, setRunnerDispatchSchedulerPlanError] =
    useState<string | null>(null);
  const [
    runnerDispatchWorkerBootstrapPlanError,
    setRunnerDispatchWorkerBootstrapPlanError,
  ] = useState<string | null>(null);
  const [schedulerLeaseRetryPlanError, setSchedulerLeaseRetryPlanError] =
    useState<string | null>(null);
  const [workerQueueClaimPlanError, setWorkerQueueClaimPlanError] = useState<string | null>(null);
  const [repositoryTransactionPlanError, setRepositoryTransactionPlanError] =
    useState<string | null>(null);
  const [repositoryCommitRollbackPlanError, setRepositoryCommitRollbackPlanError] =
    useState<string | null>(null);
  const [workerDispatchLeaseHeartbeatPlanError, setWorkerDispatchLeaseHeartbeatPlanError] =
    useState<string | null>(null);
  const [workerCancellationAbandonPlanError, setWorkerCancellationAbandonPlanError] =
    useState<string | null>(null);
  const [workerCompletionFinalizationPlanError, setWorkerCompletionFinalizationPlanError] =
    useState<string | null>(null);
  const [workerOutputAggregationPlanError, setWorkerOutputAggregationPlanError] =
    useState<string | null>(null);
  const [workerSynthesisHandoffPlanError, setWorkerSynthesisHandoffPlanError] =
    useState<string | null>(null);
  const [synthesisBundleAssemblyPlanError, setSynthesisBundleAssemblyPlanError] =
    useState<string | null>(null);
  const [finalSynthesisDraftPlanError, setFinalSynthesisDraftPlanError] =
    useState<string | null>(null);
  const [finalHtmlArtifactAssemblyPlanError, setFinalHtmlArtifactAssemblyPlanError] =
    useState<string | null>(null);
  const [finalArtifactPersistencePlanError, setFinalArtifactPersistencePlanError] =
    useState<string | null>(null);
  const [finalArtifactGraphCommitPlanError, setFinalArtifactGraphCommitPlanError] =
    useState<string | null>(null);
  const [finalArtifactPublishPlanError, setFinalArtifactPublishPlanError] =
    useState<string | null>(null);
  const [
    finalArtifactCompletionFinalizationPlanError,
    setFinalArtifactCompletionFinalizationPlanError,
  ] = useState<string | null>(null);
  const [finalRunClosurePlanError, setFinalRunClosurePlanError] = useState<string | null>(null);
  const [
    operatorNotificationDeliveryReadinessPlanError,
    setOperatorNotificationDeliveryReadinessPlanError,
  ] = useState<string | null>(null);
  const [
    operatorNotificationDeliveryApplyPlanError,
    setOperatorNotificationDeliveryApplyPlanError,
  ] = useState<string | null>(null);
  const [
    operatorNotificationDeliveryResultReconciliationPlanError,
    setOperatorNotificationDeliveryResultReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    operatorDeliveryLedgerReconciliationPlanError,
    setOperatorDeliveryLedgerReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    workspaceDeliveryCardReconciliationPlanError,
    setWorkspaceDeliveryCardReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    deliveryNotificationReconciliationPlanError,
    setDeliveryNotificationReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    retentionBillingReconciliationPlanError,
    setRetentionBillingReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    finalCloseoutArchiveReconciliationPlanError,
    setFinalCloseoutArchiveReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchiveHandoffPackagePlanError,
    setOperatorArchiveHandoffPackagePlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchiveHandoffPackageResultReconciliationPlanError,
    setOperatorArchiveHandoffPackageResultReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchiveHandoffPackageDeliveryAuditPlanError,
    setOperatorArchiveHandoffPackageDeliveryAuditPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanError,
    setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportPlanError,
    setOperatorArchivePackageDeliveryReportPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportResultReconciliationPlanError,
    setOperatorArchivePackageDeliveryReportResultReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportNotificationReadinessPlanError,
    setOperatorArchivePackageDeliveryReportNotificationReadinessPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanError,
    setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportDeliveryConfirmationPlanError,
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanError,
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanError,
    setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanError,
    setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanError,
    setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanError,
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanError,
  ] = useState<string | null>(null);
  const [
    operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanError,
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanError,
  ] = useState<string | null>(null);

  function clearOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlan() {
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt(
      null,
    );
  }

  function clearOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlan() {
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanError(null);
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt(
      null,
    );
    clearOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlan();
  }

  function clearOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlan() {
    setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt(
      null,
    );
    clearOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlan();
  }

  function clearOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlan() {
    setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt(
      null,
    );
    clearOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlan();
  }

  function clearOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlan() {
    setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanError(null);
    setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt(
      null,
    );
    clearOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlan();
  }

  function clearOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlan() {
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt(
      null,
    );
    clearOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlan();
  }

  function clearOperatorArchivePackageDeliveryReportDeliveryConfirmationPlan() {
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanError(null);
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt(null);
    clearOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlan();
  }

  function clearOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlan() {
    setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanError(null);
    setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt(
      null,
    );
    clearOperatorArchivePackageDeliveryReportDeliveryConfirmationPlan();
  }

  function clearOperatorArchivePackageDeliveryReportNotificationReadinessPlan() {
    setOperatorArchivePackageDeliveryReportNotificationReadinessPlanError(null);
    setOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt(null);
    clearOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlan();
  }

  function clearOperatorArchivePackageDeliveryReportResultReconciliationPlan() {
    setOperatorArchivePackageDeliveryReportResultReconciliationPlanError(null);
    setOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt(null);
    clearOperatorArchivePackageDeliveryReportNotificationReadinessPlan();
  }

  function clearOperatorArchivePackageDeliveryReportPlan() {
    setOperatorArchivePackageDeliveryReportPlanError(null);
    setOperatorArchivePackageDeliveryReportPlanReceipt(null);
    clearOperatorArchivePackageDeliveryReportResultReconciliationPlan();
  }

  function clearOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlan() {
    setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanError(null);
    setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt(null);
    clearOperatorArchivePackageDeliveryReportPlan();
  }

  function clearOperatorArchiveHandoffPackageDeliveryAuditPlan() {
    setOperatorArchiveHandoffPackageDeliveryAuditPlanError(null);
    setOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt(null);
    clearOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlan();
  }

  function clearOperatorArchiveHandoffPackageResultReconciliationPlan() {
    setOperatorArchiveHandoffPackageResultReconciliationPlanError(null);
    setOperatorArchiveHandoffPackageResultReconciliationPlanReceipt(null);
    clearOperatorArchiveHandoffPackageDeliveryAuditPlan();
  }

  function clearOperatorArchiveHandoffPackagePlan() {
    setOperatorArchiveHandoffPackagePlanError(null);
    setOperatorArchiveHandoffPackagePlanReceipt(null);
    clearOperatorArchiveHandoffPackageResultReconciliationPlan();
  }

  function clearFinalCloseoutArchiveReconciliationPlan() {
    setFinalCloseoutArchiveReconciliationPlanError(null);
    setFinalCloseoutArchiveReconciliationPlanReceipt(null);
    clearOperatorArchiveHandoffPackagePlan();
  }

  function clearRetentionBillingReconciliationPlan() {
    setRetentionBillingReconciliationPlanError(null);
    setRetentionBillingReconciliationPlanReceipt(null);
    clearFinalCloseoutArchiveReconciliationPlan();
  }

  function clearDeliveryNotificationReconciliationPlan() {
    setDeliveryNotificationReconciliationPlanError(null);
    setDeliveryNotificationReconciliationPlanReceipt(null);
    clearRetentionBillingReconciliationPlan();
  }

  function clearWorkspaceDeliveryCardReconciliationPlan() {
    setWorkspaceDeliveryCardReconciliationPlanError(null);
    setWorkspaceDeliveryCardReconciliationPlanReceipt(null);
    clearDeliveryNotificationReconciliationPlan();
  }

  function clearOperatorDeliveryLedgerReconciliationPlan() {
    setOperatorDeliveryLedgerReconciliationPlanError(null);
    setOperatorDeliveryLedgerReconciliationPlanReceipt(null);
    clearWorkspaceDeliveryCardReconciliationPlan();
  }

  function clearOperatorNotificationDeliveryResultReconciliationPlan() {
    setOperatorNotificationDeliveryResultReconciliationPlanError(null);
    setOperatorNotificationDeliveryResultReconciliationPlanReceipt(null);
    clearOperatorDeliveryLedgerReconciliationPlan();
  }

  function clearOperatorNotificationDeliveryApplyPlan() {
    setOperatorNotificationDeliveryApplyPlanError(null);
    setOperatorNotificationDeliveryApplyPlanReceipt(null);
    clearOperatorNotificationDeliveryResultReconciliationPlan();
  }

  function clearOperatorNotificationDeliveryReadinessPlan() {
    setOperatorNotificationDeliveryReadinessPlanError(null);
    setOperatorNotificationDeliveryReadinessPlanReceipt(null);
    clearOperatorNotificationDeliveryApplyPlan();
  }

  function clearFinalRunClosurePlan() {
    setFinalRunClosurePlanError(null);
    setFinalRunClosurePlanReceipt(null);
    clearOperatorNotificationDeliveryReadinessPlan();
  }

  function clearFinalArtifactCompletionFinalizationPlan() {
    setFinalArtifactCompletionFinalizationPlanError(null);
    setFinalArtifactCompletionFinalizationPlanReceipt(null);
    clearFinalRunClosurePlan();
  }

  function clearFinalArtifactPublishPlan() {
    setFinalArtifactPublishPlanError(null);
    setFinalArtifactPublishPlanReceipt(null);
    clearFinalArtifactCompletionFinalizationPlan();
  }

  function clearFinalArtifactGraphCommitPlan() {
    setFinalArtifactGraphCommitPlanError(null);
    setFinalArtifactGraphCommitPlanReceipt(null);
    clearFinalArtifactPublishPlan();
  }

  function clearFinalArtifactPersistencePlan() {
    setFinalArtifactPersistencePlanError(null);
    setFinalArtifactPersistencePlanReceipt(null);
    clearFinalArtifactGraphCommitPlan();
  }

  function clearFinalHtmlArtifactAssemblyPlan() {
    setFinalHtmlArtifactAssemblyPlanError(null);
    setFinalHtmlArtifactAssemblyPlanReceipt(null);
    clearFinalArtifactPersistencePlan();
  }

  function clearFinalSynthesisDraftPlan() {
    setFinalSynthesisDraftPlanError(null);
    setFinalSynthesisDraftPlanReceipt(null);
    clearFinalHtmlArtifactAssemblyPlan();
  }

  function clearSynthesisBundleAssemblyPlan() {
    setSynthesisBundleAssemblyPlanError(null);
    setSynthesisBundleAssemblyPlanReceipt(null);
    clearFinalSynthesisDraftPlan();
  }

  function clearWorkerOutputAggregationPlan() {
    setWorkerOutputAggregationPlanError(null);
    setWorkerOutputAggregationPlanReceipt(null);
    setWorkerSynthesisHandoffPlanError(null);
    setWorkerSynthesisHandoffPlanReceipt(null);
    clearSynthesisBundleAssemblyPlan();
  }

  function clearWorkerCompletionFinalizationPlan() {
    setWorkerCompletionFinalizationPlanError(null);
    setWorkerCompletionFinalizationPlanReceipt(null);
    clearWorkerOutputAggregationPlan();
  }

  function clearWorkerCancellationAbandonPlan() {
    setWorkerCancellationAbandonPlanError(null);
    setWorkerCancellationAbandonPlanReceipt(null);
    clearWorkerCompletionFinalizationPlan();
  }

  function clearWorkerDispatchLeaseHeartbeatPlan() {
    setWorkerDispatchLeaseHeartbeatPlanError(null);
    setWorkerDispatchLeaseHeartbeatPlanReceipt(null);
    clearWorkerCancellationAbandonPlan();
  }

  function clearRepositoryCommitRollbackPlan() {
    setRepositoryCommitRollbackPlanError(null);
    setRepositoryCommitRollbackPlanReceipt(null);
    clearWorkerDispatchLeaseHeartbeatPlan();
  }

  function clearRepositoryTransactionPlan() {
    setRepositoryTransactionPlanError(null);
    setRepositoryTransactionPlanReceipt(null);
    clearRepositoryCommitRollbackPlan();
  }

  function clearWorkerQueueClaimPlan() {
    setWorkerQueueClaimPlanError(null);
    setWorkerQueueClaimPlanReceipt(null);
    clearRepositoryTransactionPlan();
  }

  function clearSchedulerLeaseRetryPlan() {
    setSchedulerLeaseRetryPlanError(null);
    setSchedulerLeaseRetryPlanReceipt(null);
    clearWorkerQueueClaimPlan();
  }

  function clearRunnerDispatchWorkerBootstrapPlan() {
    setRunnerDispatchWorkerBootstrapPlanError(null);
    setRunnerDispatchWorkerBootstrapPlanReceipt(null);
    clearSchedulerLeaseRetryPlan();
  }

  function clearRunnerDispatchSchedulerPlan() {
    setRunnerDispatchSchedulerPlanError(null);
    setRunnerDispatchSchedulerPlanReceipt(null);
    clearRunnerDispatchWorkerBootstrapPlan();
  }

  function clearLiveDispatchFinalEnablementApplyPlan() {
    setLiveDispatchFinalEnablementApplyPlanError(null);
    setLiveDispatchFinalEnablementApplyPlanReceipt(null);
    clearRunnerDispatchSchedulerPlan();
  }

  function clearLiveDispatchFinalEnablementPlan() {
    setLiveDispatchFinalEnablementPlanError(null);
    setLiveDispatchFinalEnablementPlanReceipt(null);
    clearLiveDispatchFinalEnablementApplyPlan();
  }

  function clearOperatorDispatchActivationReadinessPlan() {
    setOperatorDispatchActivationReadinessPlanError(null);
    setOperatorDispatchActivationReadinessPlanReceipt(null);
    clearLiveDispatchFinalEnablementPlan();
  }

  function clearControlLedgerPersistenceApplyPlan() {
    setControlLedgerPersistenceApplyPlanError(null);
    setControlLedgerPersistenceApplyPlanReceipt(null);
    clearOperatorDispatchActivationReadinessPlan();
  }

  function clearControlLedgerPersistencePlan() {
    setControlLedgerPersistencePlanError(null);
    setControlLedgerPersistencePlanReceipt(null);
    clearControlLedgerPersistenceApplyPlan();
  }

  function clearControlLedgerAdapterPlan() {
    setControlLedgerAdapterPlanError(null);
    setControlLedgerAdapterPlanReceipt(null);
    clearControlLedgerPersistencePlan();
  }

  function clearOperatorDispatchAdapterPlan() {
    setOperatorDispatchAdapterPlanError(null);
    setOperatorDispatchAdapterPlanReceipt(null);
    clearControlLedgerAdapterPlan();
  }

  function clearFinalArtifactAdapterPlan() {
    setFinalArtifactAdapterPlanError(null);
    setFinalArtifactAdapterPlanReceipt(null);
    clearOperatorDispatchAdapterPlan();
  }

  function clearGraphAdapterPlan() {
    setGraphAdapterPlanError(null);
    setGraphAdapterPlanReceipt(null);
    clearFinalArtifactAdapterPlan();
  }

  function clearRetrievalAdapterPlan() {
    setRetrievalAdapterPlanError(null);
    setRetrievalAdapterPlanReceipt(null);
    clearGraphAdapterPlan();
  }

  function clearProviderExecutorAdapterPlan() {
    setProviderExecutorAdapterPlanError(null);
    setProviderExecutorAdapterPlanReceipt(null);
    clearRetrievalAdapterPlan();
  }

  function clearBudgetProviderAdapterPlan() {
    setBudgetProviderAdapterPlanError(null);
    setBudgetProviderAdapterPlanReceipt(null);
    clearProviderExecutorAdapterPlan();
  }

  function clearRunnerControlPlan() {
    setRunnerControlPlanError(null);
    setRunnerControlPlanReceipt(null);
    clearBudgetProviderAdapterPlan();
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDryRunError(null);
    setLiveSettingsError(null);
    setDispatchError(null);
    setActivationError(null);
    setBudgetReservationError(null);
    setProviderRouteError(null);
    setRetrievalError(null);
    setGraphMutationError(null);
    setFinalArtifactError(null);
    setRunnerControlPlanError(null);
    setBudgetProviderAdapterPlanError(null);
    setProviderExecutorAdapterPlanError(null);
    setRetrievalAdapterPlanError(null);
    setGraphAdapterPlanError(null);
    setFinalArtifactAdapterPlanError(null);
    setOperatorDispatchAdapterPlanError(null);
    setControlLedgerAdapterPlanError(null);
    setControlLedgerPersistencePlanError(null);
    setControlLedgerPersistenceApplyPlanError(null);
    setOperatorDispatchActivationReadinessPlanError(null);
    setLiveDispatchFinalEnablementPlanError(null);
    setLiveDispatchFinalEnablementApplyPlanError(null);
    setRunnerDispatchSchedulerPlanError(null);
    setRunnerDispatchWorkerBootstrapPlanError(null);
    setSchedulerLeaseRetryPlanError(null);
    setWorkerQueueClaimPlanError(null);
    setWorkerDispatchLeaseHeartbeatPlanError(null);
    setWorkerCancellationAbandonPlanError(null);
    setWorkerCompletionFinalizationPlanError(null);
    setWorkerOutputAggregationPlanError(null);
    setWorkerSynthesisHandoffPlanError(null);
    setSynthesisBundleAssemblyPlanError(null);
    setFinalSynthesisDraftPlanError(null);
    setFinalHtmlArtifactAssemblyPlanError(null);
    setFinalArtifactPersistencePlanError(null);
    setFinalArtifactGraphCommitPlanError(null);
    setFinalArtifactPublishPlanError(null);
    setFinalArtifactCompletionFinalizationPlanError(null);
    setFinalRunClosurePlanError(null);
    setOperatorNotificationDeliveryReadinessPlanError(null);
    setOperatorNotificationDeliveryApplyPlanError(null);
    setOperatorNotificationDeliveryResultReconciliationPlanError(null);
    setOperatorDeliveryLedgerReconciliationPlanError(null);
    setWorkspaceDeliveryCardReconciliationPlanError(null);
    setDeliveryNotificationReconciliationPlanError(null);
    setRetentionBillingReconciliationPlanError(null);
    setFinalCloseoutArchiveReconciliationPlanError(null);
    setOperatorArchiveHandoffPackagePlanError(null);
    setOperatorArchiveHandoffPackageResultReconciliationPlanError(null);
    setOperatorArchiveHandoffPackageDeliveryAuditPlanError(null);
    setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanError(null);
    setPreflight(null);
    setDryRunReceipt(null);
    setLiveSettingsReceipt(null);
    setDispatchReceipt(null);
    setActivationReceipt(null);
    setBudgetReservationReceipt(null);
    setProviderRouteReceipt(null);
    setRetrievalReceipt(null);
    setGraphMutationReceipt(null);
    setFinalArtifactReceipt(null);
    setRunnerReadinessError(null);
    setRunnerReadinessReceipt(null);
    setRunnerControlPlanReceipt(null);
    setBudgetProviderAdapterPlanReceipt(null);
    setProviderExecutorAdapterPlanReceipt(null);
    setRetrievalAdapterPlanReceipt(null);
    setGraphAdapterPlanReceipt(null);
    setFinalArtifactAdapterPlanReceipt(null);
    setOperatorDispatchAdapterPlanReceipt(null);
    setControlLedgerAdapterPlanReceipt(null);
    setControlLedgerPersistencePlanReceipt(null);
    setControlLedgerPersistenceApplyPlanReceipt(null);
    setOperatorDispatchActivationReadinessPlanReceipt(null);
    setLiveDispatchFinalEnablementPlanReceipt(null);
    setLiveDispatchFinalEnablementApplyPlanReceipt(null);
    setRunnerDispatchSchedulerPlanReceipt(null);
    setRunnerDispatchWorkerBootstrapPlanReceipt(null);
    setSchedulerLeaseRetryPlanReceipt(null);
    setWorkerQueueClaimPlanReceipt(null);
    setRepositoryTransactionPlanReceipt(null);
    setRepositoryCommitRollbackPlanReceipt(null);
    setWorkerDispatchLeaseHeartbeatPlanReceipt(null);
    setWorkerCancellationAbandonPlanReceipt(null);
    setWorkerCompletionFinalizationPlanReceipt(null);
    setWorkerOutputAggregationPlanReceipt(null);
    setWorkerSynthesisHandoffPlanReceipt(null);
    setSynthesisBundleAssemblyPlanReceipt(null);
    setFinalSynthesisDraftPlanReceipt(null);
    setFinalHtmlArtifactAssemblyPlanReceipt(null);
    setFinalArtifactPersistencePlanReceipt(null);
    setFinalArtifactGraphCommitPlanReceipt(null);
    setFinalArtifactPublishPlanReceipt(null);
    setFinalArtifactCompletionFinalizationPlanReceipt(null);
    setFinalRunClosurePlanReceipt(null);
    setOperatorNotificationDeliveryReadinessPlanReceipt(null);
    setOperatorNotificationDeliveryApplyPlanReceipt(null);
    setOperatorNotificationDeliveryResultReconciliationPlanReceipt(null);
    setOperatorDeliveryLedgerReconciliationPlanReceipt(null);
    setWorkspaceDeliveryCardReconciliationPlanReceipt(null);
    setDeliveryNotificationReconciliationPlanReceipt(null);
    setRetentionBillingReconciliationPlanReceipt(null);
    setFinalCloseoutArchiveReconciliationPlanReceipt(null);
    setOperatorArchiveHandoffPackagePlanReceipt(null);
    setOperatorArchiveHandoffPackageResultReconciliationPlanReceipt(null);
    setOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt(null);
    setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt(null);
    try {
      const result = await preflightMidnightOil({
        goal,
        work_minutes: workMinutes,
        price_ceiling_usd: priceCeiling,
        route_mode: routeMode,
        source_policy: sourcePolicy,
        deliverable: "html_research_asset",
        operator_acknowledged_spend: ack,
      });
      setPreflight(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDryRun() {
    if (!preflight?.launch_packet || !preflight.approval_receipt || !preflight.runner_handoff) {
      setDryRunError("Dry run requires launch packet, approval receipt, and runner handoff.");
      return;
    }

    setDryRunBusy(true);
    setDryRunError(null);
    setDryRunReceipt(null);
    try {
      const result = await dryRunMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
      });
      setDryRunReceipt(result);
    } catch (e) {
      setDryRunError(e instanceof Error ? e.message : String(e));
    } finally {
      setDryRunBusy(false);
    }
  }

  async function onLiveRunSettings() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !preflight.applied_run_receipt
    ) {
      setLiveSettingsError(
        "Live settings require launch packet, approval receipt, runner handoff, and applied run receipt.",
      );
      return;
    }

    setLiveSettingsBusy(true);
    setLiveSettingsError(null);
    setLiveSettingsReceipt(null);
    setDispatchError(null);
    setDispatchReceipt(null);
    setActivationError(null);
    setActivationReceipt(null);
    setBudgetReservationError(null);
    setBudgetReservationReceipt(null);
    setProviderRouteError(null);
    setProviderRouteReceipt(null);
    setRetrievalError(null);
    setRetrievalReceipt(null);
    setGraphMutationError(null);
    setGraphMutationReceipt(null);
    setFinalArtifactError(null);
    setFinalArtifactReceipt(null);
    setRunnerReadinessError(null);
    setRunnerReadinessReceipt(null);
    clearRunnerControlPlan();
    try {
      const result = await liveRunActivationSettingsMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        applied_run_receipt: preflight.applied_run_receipt,
        requested_live_run_enabled: true,
        requested_price_ceiling_usd: preflight.approval_receipt.approved_price_ceiling_usd,
        requested_work_minutes: preflight.approval_receipt.approved_work_minutes,
      });
      setLiveSettingsReceipt(result);
    } catch (e) {
      setLiveSettingsError(e instanceof Error ? e.message : String(e));
    } finally {
      setLiveSettingsBusy(false);
    }
  }

  async function onDispatchGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !preflight.applied_run_receipt
    ) {
      setDispatchError(
        "Dispatch gate requires launch packet, approval receipt, runner handoff, and applied run receipt.",
      );
      return;
    }

    setDispatchBusy(true);
    setDispatchError(null);
    setDispatchReceipt(null);
    setActivationError(null);
    setActivationReceipt(null);
    setBudgetReservationError(null);
    setBudgetReservationReceipt(null);
    setProviderRouteError(null);
    setProviderRouteReceipt(null);
    setRetrievalError(null);
    setRetrievalReceipt(null);
    setGraphMutationError(null);
    setGraphMutationReceipt(null);
    setFinalArtifactError(null);
    setFinalArtifactReceipt(null);
    setRunnerReadinessError(null);
    setRunnerReadinessReceipt(null);
    clearRunnerControlPlan();
    try {
      const result = await dispatchMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        applied_run_receipt: preflight.applied_run_receipt,
        live_dispatch_requested: true,
      });
      setDispatchReceipt(result);
    } catch (e) {
      setDispatchError(e instanceof Error ? e.message : String(e));
    } finally {
      setDispatchBusy(false);
    }
  }

  async function onActivationChecklist() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !preflight.applied_run_receipt ||
      !liveSettingsReceipt ||
      !dispatchReceipt
    ) {
      setActivationError(
        "Activation checklist requires launch packet, approval receipt, runner handoff, applied run receipt, live settings receipt, and dispatch receipt.",
      );
      return;
    }

    setActivationBusy(true);
    setActivationError(null);
    setActivationReceipt(null);
    setBudgetReservationError(null);
    setBudgetReservationReceipt(null);
    setProviderRouteError(null);
    setProviderRouteReceipt(null);
    setRetrievalError(null);
    setRetrievalReceipt(null);
    setGraphMutationError(null);
    setGraphMutationReceipt(null);
    setFinalArtifactError(null);
    setFinalArtifactReceipt(null);
    setRunnerReadinessError(null);
    setRunnerReadinessReceipt(null);
    clearRunnerControlPlan();
    try {
      const result = await activationChecklistMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        applied_run_receipt: preflight.applied_run_receipt,
        live_run_activation_settings_receipt: liveSettingsReceipt,
        dispatch_receipt: dispatchReceipt,
      });
      setActivationReceipt(result);
    } catch (e) {
      setActivationError(e instanceof Error ? e.message : String(e));
    } finally {
      setActivationBusy(false);
    }
  }

  async function onBudgetReservationGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !preflight.applied_run_receipt ||
      !dispatchReceipt ||
      !activationReceipt
    ) {
      setBudgetReservationError(
        "Budget reservation requires launch packet, approval receipt, runner handoff, applied run receipt, dispatch receipt, and activation receipt.",
      );
      return;
    }

    setBudgetReservationBusy(true);
    setBudgetReservationError(null);
    setBudgetReservationReceipt(null);
    setProviderRouteError(null);
    setProviderRouteReceipt(null);
    setRetrievalError(null);
    setRetrievalReceipt(null);
    setGraphMutationError(null);
    setGraphMutationReceipt(null);
    setFinalArtifactError(null);
    setFinalArtifactReceipt(null);
    setRunnerReadinessError(null);
    setRunnerReadinessReceipt(null);
    clearRunnerControlPlan();
    try {
      const result = await budgetReservationMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        applied_run_receipt: preflight.applied_run_receipt,
        dispatch_receipt: dispatchReceipt,
        activation_checklist_receipt: activationReceipt,
      });
      setBudgetReservationReceipt(result);
    } catch (e) {
      setBudgetReservationError(e instanceof Error ? e.message : String(e));
    } finally {
      setBudgetReservationBusy(false);
    }
  }

  async function onProviderRouteGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !preflight.applied_run_receipt ||
      !dispatchReceipt ||
      !activationReceipt ||
      !budgetReservationReceipt
    ) {
      setProviderRouteError(
        "Provider route requires launch packet, approval receipt, runner handoff, applied run receipt, dispatch receipt, activation receipt, and budget reservation receipt.",
      );
      return;
    }

    setProviderRouteBusy(true);
    setProviderRouteError(null);
    setProviderRouteReceipt(null);
    setRetrievalError(null);
    setRetrievalReceipt(null);
    setGraphMutationError(null);
    setGraphMutationReceipt(null);
    setFinalArtifactError(null);
    setFinalArtifactReceipt(null);
    setRunnerReadinessError(null);
    setRunnerReadinessReceipt(null);
    clearRunnerControlPlan();
    try {
      const result = await providerRouteMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        applied_run_receipt: preflight.applied_run_receipt,
        dispatch_receipt: dispatchReceipt,
        activation_checklist_receipt: activationReceipt,
        budget_reservation_receipt: budgetReservationReceipt,
      });
      setProviderRouteReceipt(result);
    } catch (e) {
      setProviderRouteError(e instanceof Error ? e.message : String(e));
    } finally {
      setProviderRouteBusy(false);
    }
  }

  async function onRetrievalGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !preflight.applied_run_receipt ||
      !dispatchReceipt ||
      !activationReceipt ||
      !budgetReservationReceipt ||
      !providerRouteReceipt
    ) {
      setRetrievalError(
        "Retrieval requires launch packet, approval receipt, runner handoff, applied run receipt, dispatch receipt, activation receipt, budget reservation receipt, and provider route receipt.",
      );
      return;
    }

    setRetrievalBusy(true);
    setRetrievalError(null);
    setRetrievalReceipt(null);
    setGraphMutationError(null);
    setGraphMutationReceipt(null);
    setFinalArtifactError(null);
    setFinalArtifactReceipt(null);
    setRunnerReadinessError(null);
    setRunnerReadinessReceipt(null);
    clearRunnerControlPlan();
    try {
      const result = await retrievalMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        applied_run_receipt: preflight.applied_run_receipt,
        dispatch_receipt: dispatchReceipt,
        activation_checklist_receipt: activationReceipt,
        budget_reservation_receipt: budgetReservationReceipt,
        provider_route_receipt: providerRouteReceipt,
      });
      setRetrievalReceipt(result);
    } catch (e) {
      setRetrievalError(e instanceof Error ? e.message : String(e));
    } finally {
      setRetrievalBusy(false);
    }
  }

  async function onGraphMutationGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !preflight.applied_run_receipt ||
      !dispatchReceipt ||
      !activationReceipt ||
      !budgetReservationReceipt ||
      !providerRouteReceipt ||
      !retrievalReceipt
    ) {
      setGraphMutationError(
        "Graph mutation requires launch packet, approval receipt, runner handoff, applied run receipt, dispatch receipt, activation receipt, budget reservation receipt, provider route receipt, and retrieval receipt.",
      );
      return;
    }

    setGraphMutationBusy(true);
    setGraphMutationError(null);
    setGraphMutationReceipt(null);
    setFinalArtifactError(null);
    setFinalArtifactReceipt(null);
    setRunnerReadinessError(null);
    setRunnerReadinessReceipt(null);
    clearRunnerControlPlan();
    try {
      const result = await graphMutationMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        applied_run_receipt: preflight.applied_run_receipt,
        dispatch_receipt: dispatchReceipt,
        activation_checklist_receipt: activationReceipt,
        budget_reservation_receipt: budgetReservationReceipt,
        provider_route_receipt: providerRouteReceipt,
        retrieval_receipt: retrievalReceipt,
      });
      setGraphMutationReceipt(result);
    } catch (e) {
      setGraphMutationError(e instanceof Error ? e.message : String(e));
    } finally {
      setGraphMutationBusy(false);
    }
  }

  async function onFinalArtifactGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !preflight.applied_run_receipt ||
      !dispatchReceipt ||
      !activationReceipt ||
      !budgetReservationReceipt ||
      !providerRouteReceipt ||
      !retrievalReceipt ||
      !graphMutationReceipt
    ) {
      setFinalArtifactError(
        "Final artifact requires launch packet, approval receipt, runner handoff, applied run receipt, dispatch receipt, activation receipt, budget reservation receipt, provider route receipt, retrieval receipt, and graph mutation receipt.",
      );
      return;
    }

    setFinalArtifactBusy(true);
    setFinalArtifactError(null);
    setFinalArtifactReceipt(null);
    setRunnerReadinessError(null);
    setRunnerReadinessReceipt(null);
    clearRunnerControlPlan();
    try {
      const result = await finalArtifactMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        applied_run_receipt: preflight.applied_run_receipt,
        dispatch_receipt: dispatchReceipt,
        activation_checklist_receipt: activationReceipt,
        budget_reservation_receipt: budgetReservationReceipt,
        provider_route_receipt: providerRouteReceipt,
        retrieval_receipt: retrievalReceipt,
        graph_mutation_receipt: graphMutationReceipt,
      });
      setFinalArtifactReceipt(result);
    } catch (e) {
      setFinalArtifactError(e instanceof Error ? e.message : String(e));
    } finally {
      setFinalArtifactBusy(false);
    }
  }

  async function onRunnerReadinessGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !preflight.applied_run_receipt ||
      !liveSettingsReceipt ||
      !dispatchReceipt ||
      !activationReceipt ||
      !budgetReservationReceipt ||
      !providerRouteReceipt ||
      !retrievalReceipt ||
      !graphMutationReceipt ||
      !finalArtifactReceipt
    ) {
      setRunnerReadinessError(
        "Runner readiness requires launch packet, approval receipt, runner handoff, applied run receipt, live settings receipt, dispatch receipt, activation receipt, budget reservation receipt, provider route receipt, retrieval receipt, graph mutation receipt, and final artifact receipt.",
      );
      return;
    }

    setRunnerReadinessBusy(true);
    setRunnerReadinessError(null);
    setRunnerReadinessReceipt(null);
    clearRunnerControlPlan();
    try {
      const result = await runnerReadinessMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        applied_run_receipt: preflight.applied_run_receipt,
        live_run_activation_settings_receipt: liveSettingsReceipt,
        dispatch_receipt: dispatchReceipt,
        activation_checklist_receipt: activationReceipt,
        budget_reservation_receipt: budgetReservationReceipt,
        provider_route_receipt: providerRouteReceipt,
        retrieval_receipt: retrievalReceipt,
        graph_mutation_receipt: graphMutationReceipt,
        final_artifact_receipt: finalArtifactReceipt,
      });
      setRunnerReadinessReceipt(result);
    } catch (e) {
      setRunnerReadinessError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunnerReadinessBusy(false);
    }
  }

  async function onRunnerControlPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerReadinessReceipt
    ) {
      setRunnerControlPlanError(
        "Runner control plan requires launch packet, approval receipt, runner handoff, and runner readiness receipt.",
      );
      return;
    }

    setRunnerControlPlanBusy(true);
    setRunnerControlPlanError(null);
    setRunnerControlPlanReceipt(null);
    clearBudgetProviderAdapterPlan();
    try {
      const result = await runnerControlPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_readiness_receipt: runnerReadinessReceipt,
      });
      setRunnerControlPlanReceipt(result);
    } catch (e) {
      setRunnerControlPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunnerControlPlanBusy(false);
    }
  }

  async function onBudgetProviderAdapterPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt
    ) {
      setBudgetProviderAdapterPlanError(
        "Budget provider adapter plan requires launch packet, approval receipt, runner handoff, and runner control plan receipt.",
      );
      return;
    }

    setBudgetProviderAdapterPlanBusy(true);
    setBudgetProviderAdapterPlanError(null);
    setBudgetProviderAdapterPlanReceipt(null);
    clearProviderExecutorAdapterPlan();
    try {
      const result = await budgetProviderAdapterPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
      });
      setBudgetProviderAdapterPlanReceipt(result);
    } catch (e) {
      setBudgetProviderAdapterPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setBudgetProviderAdapterPlanBusy(false);
    }
  }

  async function onProviderExecutorAdapterPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt
    ) {
      setProviderExecutorAdapterPlanError(
        "Provider executor adapter plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, and budget provider adapter plan receipt.",
      );
      return;
    }

    setProviderExecutorAdapterPlanBusy(true);
    setProviderExecutorAdapterPlanError(null);
    setProviderExecutorAdapterPlanReceipt(null);
    clearRetrievalAdapterPlan();
    try {
      const result = await providerExecutorAdapterPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
      });
      setProviderExecutorAdapterPlanReceipt(result);
    } catch (e) {
      setProviderExecutorAdapterPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setProviderExecutorAdapterPlanBusy(false);
    }
  }

  async function onRetrievalAdapterPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt
    ) {
      setRetrievalAdapterPlanError(
        "Retrieval adapter plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, and provider executor adapter plan receipt.",
      );
      return;
    }

    setRetrievalAdapterPlanBusy(true);
    setRetrievalAdapterPlanError(null);
    setRetrievalAdapterPlanReceipt(null);
    clearGraphAdapterPlan();
    try {
      const result = await retrievalAdapterPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
      });
      setRetrievalAdapterPlanReceipt(result);
    } catch (e) {
      setRetrievalAdapterPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setRetrievalAdapterPlanBusy(false);
    }
  }

  async function onGraphAdapterPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt
    ) {
      setGraphAdapterPlanError(
        "Graph adapter plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, and retrieval adapter plan receipt.",
      );
      return;
    }

    setGraphAdapterPlanBusy(true);
    setGraphAdapterPlanError(null);
    setGraphAdapterPlanReceipt(null);
    clearFinalArtifactAdapterPlan();
    try {
      const result = await graphAdapterPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
      });
      setGraphAdapterPlanReceipt(result);
    } catch (e) {
      setGraphAdapterPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setGraphAdapterPlanBusy(false);
    }
  }

  async function onFinalArtifactAdapterPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt
    ) {
      setFinalArtifactAdapterPlanError(
        "Final artifact adapter plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, and graph adapter plan receipt.",
      );
      return;
    }

    setFinalArtifactAdapterPlanBusy(true);
    setFinalArtifactAdapterPlanError(null);
    setFinalArtifactAdapterPlanReceipt(null);
    clearOperatorDispatchAdapterPlan();
    try {
      const result = await finalArtifactAdapterPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
      });
      setFinalArtifactAdapterPlanReceipt(result);
    } catch (e) {
      setFinalArtifactAdapterPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setFinalArtifactAdapterPlanBusy(false);
    }
  }

  async function onOperatorDispatchAdapterPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt
    ) {
      setOperatorDispatchAdapterPlanError(
        "Operator dispatch adapter plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, and final artifact adapter plan receipt.",
      );
      return;
    }

    setOperatorDispatchAdapterPlanBusy(true);
    setOperatorDispatchAdapterPlanError(null);
    setOperatorDispatchAdapterPlanReceipt(null);
    clearControlLedgerAdapterPlan();
    try {
      const result = await operatorDispatchAdapterPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
      });
      setOperatorDispatchAdapterPlanReceipt(result);
    } catch (e) {
      setOperatorDispatchAdapterPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setOperatorDispatchAdapterPlanBusy(false);
    }
  }

  async function onControlLedgerAdapterPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt
    ) {
      setControlLedgerAdapterPlanError(
        "Control ledger adapter plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, and operator dispatch adapter plan receipt.",
      );
      return;
    }

    setControlLedgerAdapterPlanBusy(true);
    setControlLedgerAdapterPlanError(null);
    setControlLedgerAdapterPlanReceipt(null);
    clearControlLedgerPersistencePlan();
    try {
      const result = await controlLedgerAdapterPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
      });
      setControlLedgerAdapterPlanReceipt(result);
    } catch (e) {
      setControlLedgerAdapterPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setControlLedgerAdapterPlanBusy(false);
    }
  }

  async function onControlLedgerPersistencePlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt
    ) {
      setControlLedgerPersistencePlanError(
        "Control ledger persistence requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, and control ledger adapter plan receipt.",
      );
      return;
    }

    setControlLedgerPersistencePlanBusy(true);
    setControlLedgerPersistencePlanError(null);
    setControlLedgerPersistencePlanReceipt(null);
    clearControlLedgerPersistenceApplyPlan();
    try {
      const result = await controlLedgerPersistencePlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
      });
      setControlLedgerPersistencePlanReceipt(result);
    } catch (e) {
      setControlLedgerPersistencePlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setControlLedgerPersistencePlanBusy(false);
    }
  }

  async function onControlLedgerPersistenceApplyPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt
    ) {
      setControlLedgerPersistenceApplyPlanError(
        "Control ledger persistence apply requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, and control ledger persistence plan receipt.",
      );
      return;
    }

    setControlLedgerPersistenceApplyPlanBusy(true);
    setControlLedgerPersistenceApplyPlanError(null);
    setControlLedgerPersistenceApplyPlanReceipt(null);
    clearOperatorDispatchActivationReadinessPlan();
    try {
      const result = await controlLedgerPersistenceApplyPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
      });
      setControlLedgerPersistenceApplyPlanReceipt(result);
    } catch (e) {
      setControlLedgerPersistenceApplyPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setControlLedgerPersistenceApplyPlanBusy(false);
    }
  }

  async function onOperatorDispatchActivationReadinessPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt
    ) {
      setOperatorDispatchActivationReadinessPlanError(
        "Operator dispatch activation readiness requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, and control ledger persistence apply plan receipt.",
      );
      return;
    }

    setOperatorDispatchActivationReadinessPlanBusy(true);
    setOperatorDispatchActivationReadinessPlanError(null);
    setOperatorDispatchActivationReadinessPlanReceipt(null);
    clearLiveDispatchFinalEnablementPlan();
    try {
      const result = await operatorDispatchActivationReadinessPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
      });
      setOperatorDispatchActivationReadinessPlanReceipt(result);
    } catch (e) {
      setOperatorDispatchActivationReadinessPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorDispatchActivationReadinessPlanBusy(false);
    }
  }

  async function onLiveDispatchFinalEnablementPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt
    ) {
      setLiveDispatchFinalEnablementPlanError(
        "Live dispatch final enablement requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, and operator dispatch activation readiness plan receipt.",
      );
      return;
    }

    setLiveDispatchFinalEnablementPlanBusy(true);
    setLiveDispatchFinalEnablementPlanError(null);
    setLiveDispatchFinalEnablementPlanReceipt(null);
    clearLiveDispatchFinalEnablementApplyPlan();
    try {
      const result = await liveDispatchFinalEnablementPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
      });
      setLiveDispatchFinalEnablementPlanReceipt(result);
    } catch (e) {
      setLiveDispatchFinalEnablementPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setLiveDispatchFinalEnablementPlanBusy(false);
    }
  }

  async function onLiveDispatchFinalEnablementApplyPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt
    ) {
      setLiveDispatchFinalEnablementApplyPlanError(
        "Live dispatch final enablement apply requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, and live dispatch final enablement plan receipt.",
      );
      return;
    }

    setLiveDispatchFinalEnablementApplyPlanBusy(true);
    setLiveDispatchFinalEnablementApplyPlanError(null);
    setLiveDispatchFinalEnablementApplyPlanReceipt(null);
    clearRunnerDispatchSchedulerPlan();
    try {
      const result = await liveDispatchFinalEnablementApplyPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
      });
      setLiveDispatchFinalEnablementApplyPlanReceipt(result);
    } catch (e) {
      setLiveDispatchFinalEnablementApplyPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setLiveDispatchFinalEnablementApplyPlanBusy(false);
    }
  }

  async function onRunnerDispatchSchedulerPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt
    ) {
      setRunnerDispatchSchedulerPlanError(
        "Runner dispatch scheduler requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, and live dispatch final enablement apply plan receipt.",
      );
      return;
    }

    setRunnerDispatchSchedulerPlanBusy(true);
    setRunnerDispatchSchedulerPlanError(null);
    setRunnerDispatchSchedulerPlanReceipt(null);
    clearRunnerDispatchWorkerBootstrapPlan();
    try {
      const result = await runnerDispatchSchedulerPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
      });
      setRunnerDispatchSchedulerPlanReceipt(result);
    } catch (e) {
      setRunnerDispatchSchedulerPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunnerDispatchSchedulerPlanBusy(false);
    }
  }

  async function onRunnerDispatchWorkerBootstrapPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt
    ) {
      setRunnerDispatchWorkerBootstrapPlanError(
        "Runner dispatch worker bootstrap requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, and runner dispatch scheduler plan receipt.",
      );
      return;
    }

    setRunnerDispatchWorkerBootstrapPlanBusy(true);
    setRunnerDispatchWorkerBootstrapPlanError(null);
    setRunnerDispatchWorkerBootstrapPlanReceipt(null);
    clearSchedulerLeaseRetryPlan();
    try {
      const result = await runnerDispatchWorkerBootstrapPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
      });
      setRunnerDispatchWorkerBootstrapPlanReceipt(result);
    } catch (e) {
      setRunnerDispatchWorkerBootstrapPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunnerDispatchWorkerBootstrapPlanBusy(false);
    }
  }

  async function onSchedulerLeaseRetryPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt
    ) {
      setSchedulerLeaseRetryPlanError(
        "Scheduler lease retry plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, and runner dispatch worker bootstrap plan receipt.",
      );
      return;
    }

    setSchedulerLeaseRetryPlanBusy(true);
    setSchedulerLeaseRetryPlanError(null);
    setSchedulerLeaseRetryPlanReceipt(null);
    clearWorkerQueueClaimPlan();
    try {
      const result = await schedulerLeaseRetryPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
      });
      setSchedulerLeaseRetryPlanReceipt(result);
    } catch (e) {
      setSchedulerLeaseRetryPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setSchedulerLeaseRetryPlanBusy(false);
    }
  }

  async function onWorkerQueueClaimPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt
    ) {
      setWorkerQueueClaimPlanError(
        "Worker queue claim plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, and scheduler lease retry plan receipt.",
      );
      return;
    }

    setWorkerQueueClaimPlanBusy(true);
    setWorkerQueueClaimPlanError(null);
    setWorkerQueueClaimPlanReceipt(null);
    clearRepositoryTransactionPlan();
    try {
      const result = await workerQueueClaimPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
      });
      setWorkerQueueClaimPlanReceipt(result);
    } catch (e) {
      setWorkerQueueClaimPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorkerQueueClaimPlanBusy(false);
    }
  }

  async function onRepositoryTransactionPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt
    ) {
      setRepositoryTransactionPlanError(
        "Repository transaction plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, and worker queue claim plan receipt.",
      );
      return;
    }

    setRepositoryTransactionPlanBusy(true);
    setRepositoryTransactionPlanError(null);
    setRepositoryTransactionPlanReceipt(null);
    clearRepositoryCommitRollbackPlan();
    try {
      const result = await repositoryTransactionPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
      });
      setRepositoryTransactionPlanReceipt(result);
    } catch (e) {
      setRepositoryTransactionPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setRepositoryTransactionPlanBusy(false);
    }
  }

  async function onRepositoryCommitRollbackPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt
    ) {
      setRepositoryCommitRollbackPlanError(
        "Repository commit rollback plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, and repository transaction plan receipt.",
      );
      return;
    }

    setRepositoryCommitRollbackPlanBusy(true);
    setRepositoryCommitRollbackPlanError(null);
    setRepositoryCommitRollbackPlanReceipt(null);
    clearWorkerDispatchLeaseHeartbeatPlan();
    try {
      const result = await repositoryCommitRollbackPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
      });
      setRepositoryCommitRollbackPlanReceipt(result);
    } catch (e) {
      setRepositoryCommitRollbackPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setRepositoryCommitRollbackPlanBusy(false);
    }
  }

  async function onWorkerDispatchLeaseHeartbeatPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt
    ) {
      setWorkerDispatchLeaseHeartbeatPlanError(
        "Worker lease heartbeat plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, and repository commit rollback plan receipt.",
      );
      return;
    }

    setWorkerDispatchLeaseHeartbeatPlanBusy(true);
    setWorkerDispatchLeaseHeartbeatPlanError(null);
    setWorkerDispatchLeaseHeartbeatPlanReceipt(null);
    clearWorkerCancellationAbandonPlan();
    try {
      const result = await workerDispatchLeaseHeartbeatPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
      });
      setWorkerDispatchLeaseHeartbeatPlanReceipt(result);
    } catch (e) {
      setWorkerDispatchLeaseHeartbeatPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorkerDispatchLeaseHeartbeatPlanBusy(false);
    }
  }

  async function onWorkerCancellationAbandonPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt
    ) {
      setWorkerCancellationAbandonPlanError(
        "Worker cancellation abandon plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, and worker lease heartbeat plan receipt.",
      );
      return;
    }

    setWorkerCancellationAbandonPlanBusy(true);
    setWorkerCancellationAbandonPlanError(null);
    setWorkerCancellationAbandonPlanReceipt(null);
    clearWorkerCompletionFinalizationPlan();
    try {
      const result = await workerCancellationAbandonPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
      });
      setWorkerCancellationAbandonPlanReceipt(result);
    } catch (e) {
      setWorkerCancellationAbandonPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorkerCancellationAbandonPlanBusy(false);
    }
  }

  async function onWorkerCompletionFinalizationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt
    ) {
      setWorkerCompletionFinalizationPlanError(
        "Worker completion finalization plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, and worker cancellation abandon plan receipt.",
      );
      return;
    }

    setWorkerCompletionFinalizationPlanBusy(true);
    setWorkerCompletionFinalizationPlanError(null);
    setWorkerCompletionFinalizationPlanReceipt(null);
    clearWorkerOutputAggregationPlan();
    try {
      const result = await workerCompletionFinalizationPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
      });
      setWorkerCompletionFinalizationPlanReceipt(result);
    } catch (e) {
      setWorkerCompletionFinalizationPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorkerCompletionFinalizationPlanBusy(false);
    }
  }

  async function onWorkerOutputAggregationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt
    ) {
      setWorkerOutputAggregationPlanError(
        "Worker output aggregation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, and worker completion finalization plan receipt.",
      );
      return;
    }

    setWorkerOutputAggregationPlanBusy(true);
    setWorkerOutputAggregationPlanError(null);
    setWorkerOutputAggregationPlanReceipt(null);
    try {
      const result = await workerOutputAggregationPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
      });
      setWorkerOutputAggregationPlanReceipt(result);
    } catch (e) {
      setWorkerOutputAggregationPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorkerOutputAggregationPlanBusy(false);
    }
  }

  async function onWorkerSynthesisHandoffPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt
    ) {
      setWorkerSynthesisHandoffPlanError(
        "Worker synthesis handoff plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, and worker output aggregation plan receipt.",
      );
      return;
    }

    setWorkerSynthesisHandoffPlanBusy(true);
    setWorkerSynthesisHandoffPlanError(null);
    setWorkerSynthesisHandoffPlanReceipt(null);
    clearSynthesisBundleAssemblyPlan();
    try {
      const result = await workerSynthesisHandoffPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
      });
      setWorkerSynthesisHandoffPlanReceipt(result);
    } catch (e) {
      setWorkerSynthesisHandoffPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorkerSynthesisHandoffPlanBusy(false);
    }
  }

  async function onSynthesisBundleAssemblyPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt
    ) {
      setSynthesisBundleAssemblyPlanError(
        "Synthesis bundle assembly plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, and worker synthesis handoff plan receipt.",
      );
      return;
    }

    setSynthesisBundleAssemblyPlanBusy(true);
    setSynthesisBundleAssemblyPlanError(null);
    setSynthesisBundleAssemblyPlanReceipt(null);
    try {
      const result = await synthesisBundleAssemblyPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
      });
      setSynthesisBundleAssemblyPlanReceipt(result);
    } catch (e) {
      setSynthesisBundleAssemblyPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setSynthesisBundleAssemblyPlanBusy(false);
    }
  }

  async function onFinalSynthesisDraftPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt
    ) {
      setFinalSynthesisDraftPlanError(
        "Final synthesis draft plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, and synthesis bundle assembly plan receipt.",
      );
      return;
    }

    setFinalSynthesisDraftPlanBusy(true);
    setFinalSynthesisDraftPlanError(null);
    setFinalSynthesisDraftPlanReceipt(null);
    clearFinalHtmlArtifactAssemblyPlan();
    try {
      const result = await finalSynthesisDraftPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
      });
      setFinalSynthesisDraftPlanReceipt(result);
    } catch (e) {
      setFinalSynthesisDraftPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setFinalSynthesisDraftPlanBusy(false);
    }
  }

  async function onFinalHtmlArtifactAssemblyPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt
    ) {
      setFinalHtmlArtifactAssemblyPlanError(
        "Final HTML artifact assembly plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, and final synthesis draft plan receipt.",
      );
      return;
    }

    setFinalHtmlArtifactAssemblyPlanBusy(true);
    setFinalHtmlArtifactAssemblyPlanError(null);
    setFinalHtmlArtifactAssemblyPlanReceipt(null);
    clearFinalArtifactPersistencePlan();
    try {
      const result = await finalHtmlArtifactAssemblyPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
      });
      setFinalHtmlArtifactAssemblyPlanReceipt(result);
    } catch (e) {
      setFinalHtmlArtifactAssemblyPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setFinalHtmlArtifactAssemblyPlanBusy(false);
    }
  }

  async function onFinalArtifactPersistencePlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt
    ) {
      setFinalArtifactPersistencePlanError(
        "Final artifact persistence plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, and final HTML artifact assembly plan receipt.",
      );
      return;
    }

    setFinalArtifactPersistencePlanBusy(true);
    setFinalArtifactPersistencePlanError(null);
    setFinalArtifactPersistencePlanReceipt(null);
    clearFinalArtifactGraphCommitPlan();
    try {
      const result = await finalArtifactPersistencePlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
      });
      setFinalArtifactPersistencePlanReceipt(result);
    } catch (e) {
      setFinalArtifactPersistencePlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setFinalArtifactPersistencePlanBusy(false);
    }
  }

  async function onFinalArtifactGraphCommitPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt
    ) {
      setFinalArtifactGraphCommitPlanError(
        "Final artifact graph commit plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, and final artifact persistence plan receipt.",
      );
      return;
    }

    setFinalArtifactGraphCommitPlanBusy(true);
    setFinalArtifactGraphCommitPlanError(null);
    setFinalArtifactGraphCommitPlanReceipt(null);
    clearFinalArtifactPublishPlan();
    try {
      const result = await finalArtifactGraphCommitPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
      });
      setFinalArtifactGraphCommitPlanReceipt(result);
    } catch (e) {
      setFinalArtifactGraphCommitPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setFinalArtifactGraphCommitPlanBusy(false);
    }
  }

  async function onFinalArtifactPublishPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt
    ) {
      setFinalArtifactPublishPlanError(
        "Final artifact publish plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, and final artifact graph commit plan receipt.",
      );
      return;
    }

    setFinalArtifactPublishPlanBusy(true);
    setFinalArtifactPublishPlanError(null);
    setFinalArtifactPublishPlanReceipt(null);
    clearFinalArtifactCompletionFinalizationPlan();
    try {
      const result = await finalArtifactPublishPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
      });
      setFinalArtifactPublishPlanReceipt(result);
    } catch (e) {
      setFinalArtifactPublishPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setFinalArtifactPublishPlanBusy(false);
    }
  }

  async function onFinalArtifactCompletionFinalizationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt
    ) {
      setFinalArtifactCompletionFinalizationPlanError(
        "Final artifact completion finalization plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, and final artifact publish plan receipt.",
      );
      return;
    }

    setFinalArtifactCompletionFinalizationPlanBusy(true);
    setFinalArtifactCompletionFinalizationPlanError(null);
    setFinalArtifactCompletionFinalizationPlanReceipt(null);
    clearFinalRunClosurePlan();
    try {
      const result = await finalArtifactCompletionFinalizationPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
      });
      setFinalArtifactCompletionFinalizationPlanReceipt(result);
    } catch (e) {
      setFinalArtifactCompletionFinalizationPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setFinalArtifactCompletionFinalizationPlanBusy(false);
    }
  }

  async function onFinalRunClosurePlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt
    ) {
      setFinalRunClosurePlanError(
        "Final run closure plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, and final artifact completion finalization plan receipt.",
      );
      return;
    }

    setFinalRunClosurePlanBusy(true);
    setFinalRunClosurePlanError(null);
    setFinalRunClosurePlanReceipt(null);
    clearOperatorNotificationDeliveryReadinessPlan();
    try {
      const result = await finalRunClosurePlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
      });
      setFinalRunClosurePlanReceipt(result);
    } catch (e) {
      setFinalRunClosurePlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setFinalRunClosurePlanBusy(false);
    }
  }

  async function onOperatorNotificationDeliveryReadinessPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt
    ) {
      setOperatorNotificationDeliveryReadinessPlanError(
        "Operator notification delivery readiness plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, and final run closure plan receipt.",
      );
      return;
    }

    setOperatorNotificationDeliveryReadinessPlanBusy(true);
    setOperatorNotificationDeliveryReadinessPlanError(null);
    setOperatorNotificationDeliveryReadinessPlanReceipt(null);
    clearOperatorNotificationDeliveryApplyPlan();
    try {
      const result = await operatorNotificationDeliveryReadinessPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
      });
      setOperatorNotificationDeliveryReadinessPlanReceipt(result);
    } catch (e) {
      setOperatorNotificationDeliveryReadinessPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setOperatorNotificationDeliveryReadinessPlanBusy(false);
    }
  }

  async function onOperatorNotificationDeliveryApplyPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt
    ) {
      setOperatorNotificationDeliveryApplyPlanError(
        "Operator notification delivery apply plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, and operator notification delivery readiness plan receipt.",
      );
      return;
    }

    setOperatorNotificationDeliveryApplyPlanBusy(true);
    setOperatorNotificationDeliveryApplyPlanError(null);
    setOperatorNotificationDeliveryApplyPlanReceipt(null);
    clearOperatorNotificationDeliveryResultReconciliationPlan();
    try {
      const result = await operatorNotificationDeliveryApplyPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
      });
      setOperatorNotificationDeliveryApplyPlanReceipt(result);
    } catch (e) {
      setOperatorNotificationDeliveryApplyPlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setOperatorNotificationDeliveryApplyPlanBusy(false);
    }
  }

  async function onOperatorNotificationDeliveryResultReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt
    ) {
      setOperatorNotificationDeliveryResultReconciliationPlanError(
        "Operator notification delivery result reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, and operator notification delivery apply plan receipt.",
      );
      return;
    }

    setOperatorNotificationDeliveryResultReconciliationPlanBusy(true);
    setOperatorNotificationDeliveryResultReconciliationPlanError(null);
    setOperatorNotificationDeliveryResultReconciliationPlanReceipt(null);
    clearOperatorDeliveryLedgerReconciliationPlan();
    try {
      const result = await operatorNotificationDeliveryResultReconciliationPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
        operator_notification_delivery_apply_plan_receipt:
          operatorNotificationDeliveryApplyPlanReceipt,
      });
      setOperatorNotificationDeliveryResultReconciliationPlanReceipt(result);
    } catch (e) {
      setOperatorNotificationDeliveryResultReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorNotificationDeliveryResultReconciliationPlanBusy(false);
    }
  }

  async function onOperatorDeliveryLedgerReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt
    ) {
      setOperatorDeliveryLedgerReconciliationPlanError(
        "Operator delivery ledger reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, and operator notification delivery result reconciliation plan receipt.",
      );
      return;
    }

    setOperatorDeliveryLedgerReconciliationPlanBusy(true);
    setOperatorDeliveryLedgerReconciliationPlanError(null);
    setOperatorDeliveryLedgerReconciliationPlanReceipt(null);
    clearWorkspaceDeliveryCardReconciliationPlan();
    try {
      const result = await operatorDeliveryLedgerReconciliationPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
        operator_notification_delivery_apply_plan_receipt:
          operatorNotificationDeliveryApplyPlanReceipt,
        operator_notification_delivery_result_reconciliation_plan_receipt:
          operatorNotificationDeliveryResultReconciliationPlanReceipt,
      });
      setOperatorDeliveryLedgerReconciliationPlanReceipt(result);
    } catch (e) {
      setOperatorDeliveryLedgerReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorDeliveryLedgerReconciliationPlanBusy(false);
    }
  }

  async function onWorkspaceDeliveryCardReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt
    ) {
      setWorkspaceDeliveryCardReconciliationPlanError(
        "Workspace delivery card reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, and operator delivery ledger reconciliation plan receipt.",
      );
      return;
    }

    setWorkspaceDeliveryCardReconciliationPlanBusy(true);
    setWorkspaceDeliveryCardReconciliationPlanError(null);
    setWorkspaceDeliveryCardReconciliationPlanReceipt(null);
    clearDeliveryNotificationReconciliationPlan();
    try {
      const result = await workspaceDeliveryCardReconciliationPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
        operator_notification_delivery_apply_plan_receipt:
          operatorNotificationDeliveryApplyPlanReceipt,
        operator_notification_delivery_result_reconciliation_plan_receipt:
          operatorNotificationDeliveryResultReconciliationPlanReceipt,
        operator_delivery_ledger_reconciliation_plan_receipt:
          operatorDeliveryLedgerReconciliationPlanReceipt,
      });
      setWorkspaceDeliveryCardReconciliationPlanReceipt(result);
    } catch (e) {
      setWorkspaceDeliveryCardReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setWorkspaceDeliveryCardReconciliationPlanBusy(false);
    }
  }

  async function onDeliveryNotificationReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt
    ) {
      setDeliveryNotificationReconciliationPlanError(
        "Delivery notification reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, and workspace delivery card reconciliation plan receipt.",
      );
      return;
    }

    setDeliveryNotificationReconciliationPlanBusy(true);
    setDeliveryNotificationReconciliationPlanError(null);
    setDeliveryNotificationReconciliationPlanReceipt(null);
    clearRetentionBillingReconciliationPlan();
    try {
      const result = await deliveryNotificationReconciliationPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
        operator_notification_delivery_apply_plan_receipt:
          operatorNotificationDeliveryApplyPlanReceipt,
        operator_notification_delivery_result_reconciliation_plan_receipt:
          operatorNotificationDeliveryResultReconciliationPlanReceipt,
        operator_delivery_ledger_reconciliation_plan_receipt:
          operatorDeliveryLedgerReconciliationPlanReceipt,
        workspace_delivery_card_reconciliation_plan_receipt:
          workspaceDeliveryCardReconciliationPlanReceipt,
      });
      setDeliveryNotificationReconciliationPlanReceipt(result);
    } catch (e) {
      setDeliveryNotificationReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setDeliveryNotificationReconciliationPlanBusy(false);
    }
  }

  async function onRetentionBillingReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt
    ) {
      setRetentionBillingReconciliationPlanError(
        "Retention billing reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, and delivery notification reconciliation plan receipt.",
      );
      return;
    }

    setRetentionBillingReconciliationPlanBusy(true);
    setRetentionBillingReconciliationPlanError(null);
    setRetentionBillingReconciliationPlanReceipt(null);
    clearFinalCloseoutArchiveReconciliationPlan();
    try {
      const result = await retentionBillingReconciliationPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
        operator_notification_delivery_apply_plan_receipt:
          operatorNotificationDeliveryApplyPlanReceipt,
        operator_notification_delivery_result_reconciliation_plan_receipt:
          operatorNotificationDeliveryResultReconciliationPlanReceipt,
        operator_delivery_ledger_reconciliation_plan_receipt:
          operatorDeliveryLedgerReconciliationPlanReceipt,
        workspace_delivery_card_reconciliation_plan_receipt:
          workspaceDeliveryCardReconciliationPlanReceipt,
        delivery_notification_reconciliation_plan_receipt:
          deliveryNotificationReconciliationPlanReceipt,
      });
      setRetentionBillingReconciliationPlanReceipt(result);
    } catch (e) {
      setRetentionBillingReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setRetentionBillingReconciliationPlanBusy(false);
    }
  }

  async function onFinalCloseoutArchiveReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt
    ) {
      setFinalCloseoutArchiveReconciliationPlanError(
        "Final closeout archive reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, and retention billing reconciliation plan receipt.",
      );
      return;
    }

    setFinalCloseoutArchiveReconciliationPlanBusy(true);
    setFinalCloseoutArchiveReconciliationPlanError(null);
    setFinalCloseoutArchiveReconciliationPlanReceipt(null);
    try {
      const result = await finalCloseoutArchiveReconciliationPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
        operator_notification_delivery_apply_plan_receipt:
          operatorNotificationDeliveryApplyPlanReceipt,
        operator_notification_delivery_result_reconciliation_plan_receipt:
          operatorNotificationDeliveryResultReconciliationPlanReceipt,
        operator_delivery_ledger_reconciliation_plan_receipt:
          operatorDeliveryLedgerReconciliationPlanReceipt,
        workspace_delivery_card_reconciliation_plan_receipt:
          workspaceDeliveryCardReconciliationPlanReceipt,
        delivery_notification_reconciliation_plan_receipt:
          deliveryNotificationReconciliationPlanReceipt,
        retention_billing_reconciliation_plan_receipt:
          retentionBillingReconciliationPlanReceipt,
      });
      setFinalCloseoutArchiveReconciliationPlanReceipt(result);
    } catch (e) {
      setFinalCloseoutArchiveReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setFinalCloseoutArchiveReconciliationPlanBusy(false);
    }
  }

  async function onOperatorArchiveHandoffPackagePlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt
    ) {
      setOperatorArchiveHandoffPackagePlanError(
        "Operator archive handoff package plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, and final closeout archive reconciliation plan receipt.",
      );
      return;
    }

    setOperatorArchiveHandoffPackagePlanBusy(true);
    setOperatorArchiveHandoffPackagePlanError(null);
    setOperatorArchiveHandoffPackagePlanReceipt(null);
    try {
      const result = await operatorArchiveHandoffPackagePlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
        operator_notification_delivery_apply_plan_receipt:
          operatorNotificationDeliveryApplyPlanReceipt,
        operator_notification_delivery_result_reconciliation_plan_receipt:
          operatorNotificationDeliveryResultReconciliationPlanReceipt,
        operator_delivery_ledger_reconciliation_plan_receipt:
          operatorDeliveryLedgerReconciliationPlanReceipt,
        workspace_delivery_card_reconciliation_plan_receipt:
          workspaceDeliveryCardReconciliationPlanReceipt,
        delivery_notification_reconciliation_plan_receipt:
          deliveryNotificationReconciliationPlanReceipt,
        retention_billing_reconciliation_plan_receipt:
          retentionBillingReconciliationPlanReceipt,
        final_closeout_archive_reconciliation_plan_receipt:
          finalCloseoutArchiveReconciliationPlanReceipt,
      });
      setOperatorArchiveHandoffPackagePlanReceipt(result);
    } catch (e) {
      setOperatorArchiveHandoffPackagePlanError(e instanceof Error ? e.message : String(e));
    } finally {
      setOperatorArchiveHandoffPackagePlanBusy(false);
    }
  }

  async function onOperatorArchiveHandoffPackageResultReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt
    ) {
      setOperatorArchiveHandoffPackageResultReconciliationPlanError(
        "Operator archive handoff package result reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, and operator archive handoff package plan receipt.",
      );
      return;
    }

    setOperatorArchiveHandoffPackageResultReconciliationPlanBusy(true);
    setOperatorArchiveHandoffPackageResultReconciliationPlanError(null);
    setOperatorArchiveHandoffPackageResultReconciliationPlanReceipt(null);
    try {
      const result = await operatorArchiveHandoffPackageResultReconciliationPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
        operator_notification_delivery_apply_plan_receipt:
          operatorNotificationDeliveryApplyPlanReceipt,
        operator_notification_delivery_result_reconciliation_plan_receipt:
          operatorNotificationDeliveryResultReconciliationPlanReceipt,
        operator_delivery_ledger_reconciliation_plan_receipt:
          operatorDeliveryLedgerReconciliationPlanReceipt,
        workspace_delivery_card_reconciliation_plan_receipt:
          workspaceDeliveryCardReconciliationPlanReceipt,
        delivery_notification_reconciliation_plan_receipt:
          deliveryNotificationReconciliationPlanReceipt,
        retention_billing_reconciliation_plan_receipt:
          retentionBillingReconciliationPlanReceipt,
        final_closeout_archive_reconciliation_plan_receipt:
          finalCloseoutArchiveReconciliationPlanReceipt,
        operator_archive_handoff_package_plan_receipt:
          operatorArchiveHandoffPackagePlanReceipt,
      });
      setOperatorArchiveHandoffPackageResultReconciliationPlanReceipt(result);
    } catch (e) {
      setOperatorArchiveHandoffPackageResultReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchiveHandoffPackageResultReconciliationPlanBusy(false);
    }
  }

  async function onOperatorArchiveHandoffPackageDeliveryAuditPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt
    ) {
      setOperatorArchiveHandoffPackageDeliveryAuditPlanError(
        "Operator archive handoff package delivery audit plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, and operator archive handoff package result reconciliation plan receipt.",
      );
      return;
    }

    setOperatorArchiveHandoffPackageDeliveryAuditPlanBusy(true);
    setOperatorArchiveHandoffPackageDeliveryAuditPlanError(null);
    setOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt(null);
    try {
      const result = await operatorArchiveHandoffPackageDeliveryAuditPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt: controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt: liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt: runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt: workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt: workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
        operator_notification_delivery_apply_plan_receipt:
          operatorNotificationDeliveryApplyPlanReceipt,
        operator_notification_delivery_result_reconciliation_plan_receipt:
          operatorNotificationDeliveryResultReconciliationPlanReceipt,
        operator_delivery_ledger_reconciliation_plan_receipt:
          operatorDeliveryLedgerReconciliationPlanReceipt,
        workspace_delivery_card_reconciliation_plan_receipt:
          workspaceDeliveryCardReconciliationPlanReceipt,
        delivery_notification_reconciliation_plan_receipt:
          deliveryNotificationReconciliationPlanReceipt,
        retention_billing_reconciliation_plan_receipt:
          retentionBillingReconciliationPlanReceipt,
        final_closeout_archive_reconciliation_plan_receipt:
          finalCloseoutArchiveReconciliationPlanReceipt,
        operator_archive_handoff_package_plan_receipt:
          operatorArchiveHandoffPackagePlanReceipt,
        operator_archive_handoff_package_result_reconciliation_plan_receipt:
          operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
      });
      setOperatorArchiveHandoffPackageDeliveryAuditPlanReceipt(result);
    } catch (e) {
      setOperatorArchiveHandoffPackageDeliveryAuditPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchiveHandoffPackageDeliveryAuditPlanBusy(false);
    }
  }

  async function onOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt
    ) {
      setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanError(
        "Operator archive handoff package delivery audit result reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, and operator archive handoff package delivery audit plan receipt.",
      );
      return;
    }

    setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanBusy(true);
    setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanError(null);
    setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt(null);
    try {
      const result =
        await operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
          },
        );
      setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanBusy(false);
    }
  }

  async function onOperatorArchivePackageDeliveryReportPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportPlanError(
        "Operator archive package delivery report plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, and operator archive handoff package delivery audit result reconciliation plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportPlanBusy(true);
    setOperatorArchivePackageDeliveryReportPlanError(null);
    setOperatorArchivePackageDeliveryReportPlanReceipt(null);
    try {
      const result = await operatorArchivePackageDeliveryReportPlanMidnightOil({
        launch_packet: preflight.launch_packet,
        approval_receipt: preflight.approval_receipt,
        runner_handoff: preflight.runner_handoff,
        runner_control_plan_receipt: runnerControlPlanReceipt,
        budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
        provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
        retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
        graph_adapter_plan_receipt: graphAdapterPlanReceipt,
        final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
        operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
        control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
        control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
        control_ledger_persistence_apply_plan_receipt:
          controlLedgerPersistenceApplyPlanReceipt,
        operator_dispatch_activation_readiness_plan_receipt:
          operatorDispatchActivationReadinessPlanReceipt,
        live_dispatch_final_enablement_plan_receipt:
          liveDispatchFinalEnablementPlanReceipt,
        live_dispatch_final_enablement_apply_plan_receipt:
          liveDispatchFinalEnablementApplyPlanReceipt,
        runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
        runner_dispatch_worker_bootstrap_plan_receipt:
          runnerDispatchWorkerBootstrapPlanReceipt,
        scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
        worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
        repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
        repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
        worker_dispatch_lease_heartbeat_plan_receipt:
          workerDispatchLeaseHeartbeatPlanReceipt,
        worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
        worker_completion_finalization_plan_receipt:
          workerCompletionFinalizationPlanReceipt,
        worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
        worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
        synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
        final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
        final_html_artifact_assembly_plan_receipt: finalHtmlArtifactAssemblyPlanReceipt,
        final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
        final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
        final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
        final_artifact_completion_finalization_plan_receipt:
          finalArtifactCompletionFinalizationPlanReceipt,
        final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
        operator_notification_delivery_readiness_plan_receipt:
          operatorNotificationDeliveryReadinessPlanReceipt,
        operator_notification_delivery_apply_plan_receipt:
          operatorNotificationDeliveryApplyPlanReceipt,
        operator_notification_delivery_result_reconciliation_plan_receipt:
          operatorNotificationDeliveryResultReconciliationPlanReceipt,
        operator_delivery_ledger_reconciliation_plan_receipt:
          operatorDeliveryLedgerReconciliationPlanReceipt,
        workspace_delivery_card_reconciliation_plan_receipt:
          workspaceDeliveryCardReconciliationPlanReceipt,
        delivery_notification_reconciliation_plan_receipt:
          deliveryNotificationReconciliationPlanReceipt,
        retention_billing_reconciliation_plan_receipt:
          retentionBillingReconciliationPlanReceipt,
        final_closeout_archive_reconciliation_plan_receipt:
          finalCloseoutArchiveReconciliationPlanReceipt,
        operator_archive_handoff_package_plan_receipt:
          operatorArchiveHandoffPackagePlanReceipt,
        operator_archive_handoff_package_result_reconciliation_plan_receipt:
          operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
        operator_archive_handoff_package_delivery_audit_plan_receipt:
          operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
        operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
          operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
      });
      setOperatorArchivePackageDeliveryReportPlanReceipt(result);
    } catch (e) {
      setOperatorArchivePackageDeliveryReportPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportPlanBusy(false);
    }
  }

  async function onOperatorArchivePackageDeliveryReportResultReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportResultReconciliationPlanError(
        "Operator archive package delivery report result reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, operator archive handoff package delivery audit result reconciliation plan receipt, and operator archive package delivery report plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportResultReconciliationPlanBusy(true);
    setOperatorArchivePackageDeliveryReportResultReconciliationPlanError(null);
    setOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt(null);
    try {
      const result =
        await operatorArchivePackageDeliveryReportResultReconciliationPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt:
              finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
            operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_plan_receipt:
              operatorArchivePackageDeliveryReportPlanReceipt,
          },
        );
      setOperatorArchivePackageDeliveryReportResultReconciliationPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchivePackageDeliveryReportResultReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportResultReconciliationPlanBusy(false);
    }
  }

  async function onOperatorArchivePackageDeliveryReportNotificationReadinessPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportPlanReceipt ||
      !operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportNotificationReadinessPlanError(
        "Operator archive package delivery report notification readiness plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, operator archive handoff package delivery audit result reconciliation plan receipt, operator archive package delivery report plan receipt, and operator archive package delivery report result reconciliation plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportNotificationReadinessPlanBusy(true);
    setOperatorArchivePackageDeliveryReportNotificationReadinessPlanError(null);
    setOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt(null);
    try {
      const result =
        await operatorArchivePackageDeliveryReportNotificationReadinessPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt:
              finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
            operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_plan_receipt:
              operatorArchivePackageDeliveryReportPlanReceipt,
            operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
          },
        );
      setOperatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchivePackageDeliveryReportNotificationReadinessPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportNotificationReadinessPlanBusy(false);
    }
  }

  async function onOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportPlanReceipt ||
      !operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanError(
        "Operator archive package delivery report notification result reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, operator archive handoff package delivery audit result reconciliation plan receipt, operator archive package delivery report plan receipt, operator archive package delivery report result reconciliation plan receipt, and operator archive package delivery report notification readiness plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanBusy(
      true,
    );
    setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt(
      null,
    );
    try {
      const result =
        await operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt:
              finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
            operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_plan_receipt:
              operatorArchivePackageDeliveryReportPlanReceipt,
            operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_notification_readiness_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
          },
        );
      setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanBusy(
        false,
      );
    }
  }

  async function onOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportPlanReceipt ||
      !operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanError(
        "Operator archive package delivery report delivery confirmation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, operator archive handoff package delivery audit result reconciliation plan receipt, operator archive package delivery report plan receipt, operator archive package delivery report result reconciliation plan receipt, operator archive package delivery report notification readiness plan receipt, and operator archive package delivery report notification result reconciliation plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanBusy(true);
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanError(null);
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt(null);
    try {
      const result =
        await operatorArchivePackageDeliveryReportDeliveryConfirmationPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt:
              finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
            operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_plan_receipt:
              operatorArchivePackageDeliveryReportPlanReceipt,
            operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_notification_readiness_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
            operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
          },
        );
      setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanBusy(false);
    }
  }

  async function onOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportPlanReceipt ||
      !operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanError(
        "Operator archive package delivery report delivery confirmation result reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, operator archive handoff package delivery audit result reconciliation plan receipt, operator archive package delivery report plan receipt, operator archive package delivery report result reconciliation plan receipt, operator archive package delivery report notification readiness plan receipt, operator archive package delivery report notification result reconciliation plan receipt, and operator archive package delivery report delivery confirmation plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanBusy(
      true,
    );
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt(
      null,
    );
    try {
      const result =
        await operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt:
              finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
            operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_plan_receipt:
              operatorArchivePackageDeliveryReportPlanReceipt,
            operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_notification_readiness_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
            operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt,
          },
        );
      setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanBusy(
        false,
      );
    }
  }

  async function onOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportPlanReceipt ||
      !operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanError(
        "Operator archive package delivery report final operator acknowledgement plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, operator archive handoff package delivery audit result reconciliation plan receipt, operator archive package delivery report plan receipt, operator archive package delivery report result reconciliation plan receipt, operator archive package delivery report notification readiness plan receipt, operator archive package delivery report notification result reconciliation plan receipt, operator archive package delivery report delivery confirmation plan receipt, and operator archive package delivery report delivery confirmation result reconciliation plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanBusy(
      true,
    );
    setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt(
      null,
    );
    try {
      const result =
        await operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt:
              finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
            operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_plan_receipt:
              operatorArchivePackageDeliveryReportPlanReceipt,
            operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_notification_readiness_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
            operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt,
          },
        );
      setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanBusy(
        false,
      );
    }
  }

  async function onOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportPlanReceipt ||
      !operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanError(
        "Operator archive package delivery report acknowledgement result reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, operator archive handoff package delivery audit result reconciliation plan receipt, operator archive package delivery report plan receipt, operator archive package delivery report result reconciliation plan receipt, operator archive package delivery report notification readiness plan receipt, operator archive package delivery report notification result reconciliation plan receipt, operator archive package delivery report delivery confirmation plan receipt, operator archive package delivery report delivery confirmation result reconciliation plan receipt, and operator archive package delivery report final operator acknowledgement plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanBusy(
      true,
    );
    setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt(
      null,
    );
    try {
      const result =
        await operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt:
              finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
            operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_plan_receipt:
              operatorArchivePackageDeliveryReportPlanReceipt,
            operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_notification_readiness_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
            operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt:
              operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt,
          },
        );
      setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanBusy(
        false,
      );
    }
  }

  async function onOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportPlanReceipt ||
      !operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt ||
      !operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanError(
        "Operator archive package delivery report final closeout acknowledgement plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, operator archive handoff package delivery audit result reconciliation plan receipt, operator archive package delivery report plan receipt, operator archive package delivery report result reconciliation plan receipt, operator archive package delivery report notification readiness plan receipt, operator archive package delivery report notification result reconciliation plan receipt, operator archive package delivery report delivery confirmation plan receipt, operator archive package delivery report delivery confirmation result reconciliation plan receipt, operator archive package delivery report final operator acknowledgement plan receipt, and operator archive package delivery report acknowledgement result reconciliation plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanBusy(
      true,
    );
    setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt(
      null,
    );
    try {
      const result =
        await operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt:
              finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
            operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_plan_receipt:
              operatorArchivePackageDeliveryReportPlanReceipt,
            operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_notification_readiness_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
            operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt:
              operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt,
            operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt,
          },
        );
      setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanBusy(
        false,
      );
    }
  }

  async function onOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportPlanReceipt ||
      !operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt ||
      !operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanError(
        "Operator archive package delivery report final operator delivery closeout plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, operator archive handoff package delivery audit result reconciliation plan receipt, operator archive package delivery report plan receipt, operator archive package delivery report result reconciliation plan receipt, operator archive package delivery report notification readiness plan receipt, operator archive package delivery report notification result reconciliation plan receipt, operator archive package delivery report delivery confirmation plan receipt, operator archive package delivery report delivery confirmation result reconciliation plan receipt, operator archive package delivery report final operator acknowledgement plan receipt, operator archive package delivery report acknowledgement result reconciliation plan receipt, and operator archive package delivery report final closeout acknowledgement plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanBusy(
      true,
    );
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt(
      null,
    );
    try {
      const result =
        await operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt:
              finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
            operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_plan_receipt:
              operatorArchivePackageDeliveryReportPlanReceipt,
            operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_notification_readiness_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
            operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt:
              operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt,
            operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_final_closeout_acknowledgement_plan_receipt:
              operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt,
          },
        );
      setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanBusy(
        false,
      );
    }
  }

  async function onOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanGate() {
    if (
      !preflight?.launch_packet ||
      !preflight.approval_receipt ||
      !preflight.runner_handoff ||
      !runnerControlPlanReceipt ||
      !budgetProviderAdapterPlanReceipt ||
      !providerExecutorAdapterPlanReceipt ||
      !retrievalAdapterPlanReceipt ||
      !graphAdapterPlanReceipt ||
      !finalArtifactAdapterPlanReceipt ||
      !operatorDispatchAdapterPlanReceipt ||
      !controlLedgerAdapterPlanReceipt ||
      !controlLedgerPersistencePlanReceipt ||
      !controlLedgerPersistenceApplyPlanReceipt ||
      !operatorDispatchActivationReadinessPlanReceipt ||
      !liveDispatchFinalEnablementPlanReceipt ||
      !liveDispatchFinalEnablementApplyPlanReceipt ||
      !runnerDispatchSchedulerPlanReceipt ||
      !runnerDispatchWorkerBootstrapPlanReceipt ||
      !schedulerLeaseRetryPlanReceipt ||
      !workerQueueClaimPlanReceipt ||
      !repositoryTransactionPlanReceipt ||
      !repositoryCommitRollbackPlanReceipt ||
      !workerDispatchLeaseHeartbeatPlanReceipt ||
      !workerCancellationAbandonPlanReceipt ||
      !workerCompletionFinalizationPlanReceipt ||
      !workerOutputAggregationPlanReceipt ||
      !workerSynthesisHandoffPlanReceipt ||
      !synthesisBundleAssemblyPlanReceipt ||
      !finalSynthesisDraftPlanReceipt ||
      !finalHtmlArtifactAssemblyPlanReceipt ||
      !finalArtifactPersistencePlanReceipt ||
      !finalArtifactGraphCommitPlanReceipt ||
      !finalArtifactPublishPlanReceipt ||
      !finalArtifactCompletionFinalizationPlanReceipt ||
      !finalRunClosurePlanReceipt ||
      !operatorNotificationDeliveryReadinessPlanReceipt ||
      !operatorNotificationDeliveryApplyPlanReceipt ||
      !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
      !operatorDeliveryLedgerReconciliationPlanReceipt ||
      !workspaceDeliveryCardReconciliationPlanReceipt ||
      !deliveryNotificationReconciliationPlanReceipt ||
      !retentionBillingReconciliationPlanReceipt ||
      !finalCloseoutArchiveReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackagePlanReceipt ||
      !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
      !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportPlanReceipt ||
      !operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt ||
      !operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt ||
      !operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt ||
      !operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt ||
      !operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt ||
      !operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt
    ) {
      setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanError(
        "Operator archive package delivery report final operator delivery closeout result reconciliation plan requires launch packet, approval receipt, runner handoff, runner control plan receipt, budget provider adapter plan receipt, provider executor adapter plan receipt, retrieval adapter plan receipt, graph adapter plan receipt, final artifact adapter plan receipt, operator dispatch adapter plan receipt, control ledger adapter plan receipt, control ledger persistence plan receipt, control ledger persistence apply plan receipt, operator dispatch activation readiness plan receipt, live dispatch final enablement plan receipt, live dispatch final enablement apply plan receipt, runner dispatch scheduler plan receipt, runner dispatch worker bootstrap plan receipt, scheduler lease retry plan receipt, worker queue claim plan receipt, repository transaction plan receipt, repository commit rollback plan receipt, worker lease heartbeat plan receipt, worker cancellation abandon plan receipt, worker completion finalization plan receipt, worker output aggregation plan receipt, worker synthesis handoff plan receipt, synthesis bundle assembly plan receipt, final synthesis draft plan receipt, final HTML artifact assembly plan receipt, final artifact persistence plan receipt, final artifact graph commit plan receipt, final artifact publish plan receipt, final artifact completion finalization plan receipt, final run closure plan receipt, operator notification delivery readiness plan receipt, operator notification delivery apply plan receipt, operator notification delivery result reconciliation plan receipt, operator delivery ledger reconciliation plan receipt, workspace delivery card reconciliation plan receipt, delivery notification reconciliation plan receipt, retention billing reconciliation plan receipt, final closeout archive reconciliation plan receipt, operator archive handoff package plan receipt, operator archive handoff package result reconciliation plan receipt, operator archive handoff package delivery audit plan receipt, operator archive handoff package delivery audit result reconciliation plan receipt, operator archive package delivery report plan receipt, operator archive package delivery report result reconciliation plan receipt, operator archive package delivery report notification readiness plan receipt, operator archive package delivery report notification result reconciliation plan receipt, operator archive package delivery report delivery confirmation plan receipt, operator archive package delivery report delivery confirmation result reconciliation plan receipt, operator archive package delivery report final operator acknowledgement plan receipt, operator archive package delivery report acknowledgement result reconciliation plan receipt, operator archive package delivery report final closeout acknowledgement plan receipt, and operator archive package delivery report final operator delivery closeout plan receipt.",
      );
      return;
    }

    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanBusy(
      true,
    );
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanError(
      null,
    );
    setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt(
      null,
    );
    try {
      const result =
        await operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanMidnightOil(
          {
            launch_packet: preflight.launch_packet,
            approval_receipt: preflight.approval_receipt,
            runner_handoff: preflight.runner_handoff,
            runner_control_plan_receipt: runnerControlPlanReceipt,
            budget_provider_adapter_plan_receipt: budgetProviderAdapterPlanReceipt,
            provider_executor_adapter_plan_receipt: providerExecutorAdapterPlanReceipt,
            retrieval_adapter_plan_receipt: retrievalAdapterPlanReceipt,
            graph_adapter_plan_receipt: graphAdapterPlanReceipt,
            final_artifact_adapter_plan_receipt: finalArtifactAdapterPlanReceipt,
            operator_dispatch_adapter_plan_receipt: operatorDispatchAdapterPlanReceipt,
            control_ledger_adapter_plan_receipt: controlLedgerAdapterPlanReceipt,
            control_ledger_persistence_plan_receipt: controlLedgerPersistencePlanReceipt,
            control_ledger_persistence_apply_plan_receipt:
              controlLedgerPersistenceApplyPlanReceipt,
            operator_dispatch_activation_readiness_plan_receipt:
              operatorDispatchActivationReadinessPlanReceipt,
            live_dispatch_final_enablement_plan_receipt:
              liveDispatchFinalEnablementPlanReceipt,
            live_dispatch_final_enablement_apply_plan_receipt:
              liveDispatchFinalEnablementApplyPlanReceipt,
            runner_dispatch_scheduler_plan_receipt: runnerDispatchSchedulerPlanReceipt,
            runner_dispatch_worker_bootstrap_plan_receipt:
              runnerDispatchWorkerBootstrapPlanReceipt,
            scheduler_lease_retry_plan_receipt: schedulerLeaseRetryPlanReceipt,
            worker_queue_claim_plan_receipt: workerQueueClaimPlanReceipt,
            repository_transaction_plan_receipt: repositoryTransactionPlanReceipt,
            repository_commit_rollback_plan_receipt: repositoryCommitRollbackPlanReceipt,
            worker_dispatch_lease_heartbeat_plan_receipt:
              workerDispatchLeaseHeartbeatPlanReceipt,
            worker_cancellation_abandon_plan_receipt: workerCancellationAbandonPlanReceipt,
            worker_completion_finalization_plan_receipt:
              workerCompletionFinalizationPlanReceipt,
            worker_output_aggregation_plan_receipt: workerOutputAggregationPlanReceipt,
            worker_synthesis_handoff_plan_receipt: workerSynthesisHandoffPlanReceipt,
            synthesis_bundle_assembly_plan_receipt: synthesisBundleAssemblyPlanReceipt,
            final_synthesis_draft_plan_receipt: finalSynthesisDraftPlanReceipt,
            final_html_artifact_assembly_plan_receipt:
              finalHtmlArtifactAssemblyPlanReceipt,
            final_artifact_persistence_plan_receipt: finalArtifactPersistencePlanReceipt,
            final_artifact_graph_commit_plan_receipt: finalArtifactGraphCommitPlanReceipt,
            final_artifact_publish_plan_receipt: finalArtifactPublishPlanReceipt,
            final_artifact_completion_finalization_plan_receipt:
              finalArtifactCompletionFinalizationPlanReceipt,
            final_run_closure_plan_receipt: finalRunClosurePlanReceipt,
            operator_notification_delivery_readiness_plan_receipt:
              operatorNotificationDeliveryReadinessPlanReceipt,
            operator_notification_delivery_apply_plan_receipt:
              operatorNotificationDeliveryApplyPlanReceipt,
            operator_notification_delivery_result_reconciliation_plan_receipt:
              operatorNotificationDeliveryResultReconciliationPlanReceipt,
            operator_delivery_ledger_reconciliation_plan_receipt:
              operatorDeliveryLedgerReconciliationPlanReceipt,
            workspace_delivery_card_reconciliation_plan_receipt:
              workspaceDeliveryCardReconciliationPlanReceipt,
            delivery_notification_reconciliation_plan_receipt:
              deliveryNotificationReconciliationPlanReceipt,
            retention_billing_reconciliation_plan_receipt:
              retentionBillingReconciliationPlanReceipt,
            final_closeout_archive_reconciliation_plan_receipt:
              finalCloseoutArchiveReconciliationPlanReceipt,
            operator_archive_handoff_package_plan_receipt:
              operatorArchiveHandoffPackagePlanReceipt,
            operator_archive_handoff_package_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageResultReconciliationPlanReceipt,
            operator_archive_handoff_package_delivery_audit_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditPlanReceipt,
            operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt:
              operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_plan_receipt:
              operatorArchivePackageDeliveryReportPlanReceipt,
            operator_archive_package_delivery_report_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_notification_readiness_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt,
            operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt,
            operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt:
              operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt,
            operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt:
              operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt,
            operator_archive_package_delivery_report_final_closeout_acknowledgement_plan_receipt:
              operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt,
            operator_archive_package_delivery_report_final_operator_delivery_closeout_plan_receipt:
              operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt,
          },
        );
      setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt(
        result,
      );
    } catch (e) {
      setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanError(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanBusy(
        false,
      );
    }
  }

  function toggleSource(source: MidnightOilSourcePolicy) {
    setSourcePolicy((current) => {
      if (current.includes(source)) {
        return current.length === 1 ? current : current.filter((s) => s !== source);
      }
      return [...current, source];
    });
  }

  return (
    <div className="h-full overflow-y-auto bg-ice-2 dark:bg-space-2">
      <div className="mx-auto max-w-4xl px-6 py-8 space-y-6">
        <header className="space-y-2">
          <h1 className="text-2xl font-serif text-ink dark:text-bright">Midnight oil</h1>
          <p className="text-sm font-serif text-ink-soft dark:text-starlight leading-relaxed">
            Preflight an autonomous research swarm with an approved time box, price ceiling,
            route policy, source policy, and HTML asset contract.
          </p>
        </header>

        <LemonCard title="Preflight" elevation="z1">
          <form className="p-4 space-y-4" onSubmit={onSubmit}>
            <label className="block space-y-1">
              <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Goal
              </span>
              <textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                rows={5}
                required
                className="w-full rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-3 py-2 text-sm font-serif text-ink dark:text-bright"
                placeholder="Research the bottlenecks in widebody engine supply chains."
              />
            </label>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <label className="space-y-1">
                <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Work minutes
                </span>
                <input
                  type="number"
                  min={15}
                  max={720}
                  value={workMinutes}
                  onChange={(event) => setWorkMinutes(Number(event.target.value) || 15)}
                  className="w-full rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-3 py-1.5 text-sm font-mono text-ink dark:text-bright"
                />
              </label>
              <label className="space-y-1">
                <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Price ceiling USD
                </span>
                <input
                  type="number"
                  min={0.01}
                  step={0.01}
                  value={priceCeiling}
                  onChange={(event) => setPriceCeiling(Number(event.target.value) || 0.01)}
                  className="w-full rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-3 py-1.5 text-sm font-mono text-ink dark:text-bright"
                />
              </label>
              <label className="space-y-1">
                <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Route mode
                </span>
                <select
                  value={routeMode}
                  onChange={(event) => setRouteMode(event.target.value as MidnightOilRouteMode)}
                  className="w-full rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-3 py-1.5 text-sm font-mono text-ink dark:text-bright"
                >
                  {ROUTE_MODES.map((mode) => (
                    <option key={mode.value} value={mode.value}>
                      {mode.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <fieldset className="space-y-2">
              <legend className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Source policy
              </legend>
              <div className="flex flex-wrap gap-2">
                {SOURCES.map((source) => {
                  const active = sourcePolicy.includes(source.value);
                  return (
                    <button
                      key={source.value}
                      type="button"
                      role="checkbox"
                      aria-checked={active}
                      onClick={() => toggleSource(source.value)}
                      className={
                        "rounded-md border px-3 py-1.5 text-xs font-mono " +
                        (active
                          ? "border-ink bg-ink text-white dark:border-bright dark:bg-bright dark:text-space"
                          : "border-rule dark:border-charcoal-1 text-ink dark:text-bright")
                      }
                    >
                      {source.label}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                <input
                  type="checkbox"
                  checked={ack}
                  onChange={(event) => setAck(event.target.checked)}
                  className="mt-0.5"
                />
                <span>I approve this ceiling for a future run; this preflight still launches nothing.</span>
              </label>
              <button
                type="submit"
                disabled={busy || goal.trim().length === 0}
                className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
              >
                {busy ? "Checking..." : "Preflight"}
              </button>
            </div>
          </form>
        </LemonCard>

        {error && (
          <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
            {error}
          </p>
        )}

        {preflight && (
          <LemonCard title="Run contract" elevation="z1">
            <div className="p-4 space-y-4" aria-live="polite">
              <div className="grid grid-cols-1 md:grid-cols-5 gap-3 font-mono text-[13px]">
                <Metric label="Accepted" value={preflight.accepted ? "yes" : "no"} />
                <Metric label="Run id" value={preflight.run_id ?? "not issued"} />
                <Metric
                  label="Planned budget"
                  value={`$${preflight.planned_budget_usd.toFixed(2)}`}
                />
                <Metric
                  label="Unallocated"
                  value={`$${preflight.unallocated_budget_usd.toFixed(2)}`}
                />
                <Metric label="Final format" value={preflight.artifact_contract.final_format} />
              </div>

              {!preflight.accepted && preflight.denial_reason && (
                <p className="text-sm font-mono text-emperor">{preflight.denial_reason}</p>
              )}

              {preflight.role_plans.length > 0 && (
                <div>
                  <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                    Role allocation
                  </p>
                  <ul className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                    {preflight.role_plans.map((plan) => (
                      <li
                        key={plan.role}
                        className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2 font-mono text-[12px]"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-ink dark:text-bright">{plan.role}</span>
                          <span className="text-shadow-1 dark:text-moonlight">
                            ${plan.budget_usd.toFixed(2)} / {plan.max_minutes}m
                          </span>
                        </div>
                        <p className="mt-1 truncate text-shadow-1 dark:text-moonlight">
                          {plan.planned_route_receipt_id}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                <Metric
                  label="Twin notes"
                  value={preflight.artifact_contract.twin_note_document_required ? "required" : "not required"}
                />
                <Metric
                  label="Route receipts"
                  value={preflight.artifact_contract.route_receipt_links_required ? "required" : "not required"}
                />
                <Metric
                  label="Source receipts"
                  value={preflight.artifact_contract.source_receipt_links_required ? "required" : "not required"}
                />
              </div>

              {preflight.launch_packet && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Launch packet
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {preflight.launch_packet.packet_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Dispatch"
                      value={preflight.launch_packet.dispatch_allowed ? "enabled" : "disabled"}
                    />
                    <Metric
                      label="Budget reserve"
                      value={preflight.launch_packet.budget_reserved ? "reserved" : "not reserved"}
                    />
                    <Metric
                      label="Provider calls"
                      value={preflight.launch_packet.provider_calls_made ? "made" : "none"}
                    />
                  </div>
                  <p className="mt-2 text-[11px] text-ink-soft dark:text-starlight">
                    {preflight.launch_packet.role_count} roles inherit this packet and must attach route
                    and source receipts before the final HTML asset.
                  </p>
                </div>
              )}

              {preflight.approval_receipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Approval receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {preflight.approval_receipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Scope"
                      value={preflight.approval_receipt.approval_scope.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Runner apply"
                      value={preflight.approval_receipt.runner_apply_required ? "required" : "not required"}
                    />
                    <Metric
                      label="Approved ceiling"
                      value={`$${preflight.approval_receipt.approved_price_ceiling_usd.toFixed(2)}`}
                    />
                  </div>
                  <p className="mt-2 text-[11px] text-ink-soft dark:text-starlight">
                    Bound to {preflight.approval_receipt.launch_packet_id}; no dispatch, budget
                    reservation, provider calls, or graph mutation happens in this receipt.
                  </p>
                </div>
              )}

              {preflight.runner_handoff && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Runner handoff
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {preflight.runner_handoff.handoff_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={preflight.runner_handoff.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Dispatch"
                      value={preflight.runner_handoff.dispatch_performed ? "dispatched" : "not dispatched"}
                    />
                    <Metric
                      label="Graph"
                      value={preflight.runner_handoff.graph_mutated ? "mutated" : "unchanged"}
                    />
                  </div>
                  <p className="mt-2 text-[11px] text-ink-soft dark:text-starlight">
                    Requires {preflight.runner_handoff.prerequisite_receipt_ids.length} prior receipts;
                    no budget reservation or provider call has happened.
                  </p>
                </div>
              )}

              {preflight.applied_run_receipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Applied run
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {preflight.applied_run_receipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={preflight.applied_run_receipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Retrieval"
                      value={preflight.applied_run_receipt.retrieval_performed ? "performed" : "not performed"}
                    />
                    <Metric
                      label="Artifact"
                      value={preflight.applied_run_receipt.final_artifact_created ? "created" : "not created"}
                    />
                  </div>
                  <p className="mt-2 text-[11px] text-ink-soft dark:text-starlight">
                    {preflight.applied_run_receipt.planned_role_count} planned roles; dry receipt only,
                    with no dispatch, budget reservation, provider call, retrieval, or graph mutation.
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Dry-run endpoint
                </p>
                <button
                  type="button"
                  onClick={onDryRun}
                  disabled={
                    dryRunBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {dryRunBusy ? "Dry running..." : "Dry run endpoint"}
                </button>
              </div>

              {dryRunError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {dryRunError}
                </p>
              )}

              {dryRunReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Dry-run receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {dryRunReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric label="Status" value={dryRunReceipt.status.replaceAll("_", " ")} />
                    <Metric
                      label="Dispatch"
                      value={dryRunReceipt.dispatch_performed ? "dispatched" : "not dispatched"}
                    />
                    <Metric
                      label="Retrieval"
                      value={dryRunReceipt.retrieval_performed ? "performed" : "not performed"}
                    />
                    <Metric
                      label="Artifact"
                      value={dryRunReceipt.final_artifact_created ? "created" : "not created"}
                    />
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Live settings
                </p>
                <button
                  type="button"
                  onClick={onLiveRunSettings}
                  disabled={
                    liveSettingsBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !preflight.applied_run_receipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {liveSettingsBusy ? "Checking settings..." : "Live settings"}
                </button>
              </div>

              {liveSettingsError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {liveSettingsError}
                </p>
              )}

              {liveSettingsReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Settings receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {liveSettingsReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={liveSettingsReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Ceiling"
                      value={`$${liveSettingsReceipt.requested_price_ceiling_usd.toFixed(2)}`}
                    />
                    <Metric
                      label="Work"
                      value={`${liveSettingsReceipt.requested_work_minutes}m`}
                    />
                    <Metric
                      label="Live"
                      value={liveSettingsReceipt.live_run_activation_allowed ? "allowed" : "blocked"}
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Blocker"
                      value={liveSettingsReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Missing"
                      value={`${liveSettingsReceipt.missing_controls.length} controls`}
                    />
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Dispatch gate
                </p>
                <button
                  type="button"
                  onClick={onDispatchGate}
                  disabled={
                    dispatchBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !preflight.applied_run_receipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {dispatchBusy ? "Checking gate..." : "Dispatch gate"}
                </button>
              </div>

              {dispatchError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {dispatchError}
                </p>
              )}

              {dispatchReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Dispatch receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {dispatchReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric label="Status" value={dispatchReceipt.status.replaceAll("_", " ")} />
                    <Metric
                      label="Blocker"
                      value={dispatchReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Dispatch"
                      value={dispatchReceipt.dispatch_performed ? "dispatched" : "not dispatched"}
                    />
                    <Metric
                      label="Provider calls"
                      value={dispatchReceipt.provider_calls_made ? "made" : "none"}
                    />
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Activation checklist
                </p>
                <button
                  type="button"
                  onClick={onActivationChecklist}
                  disabled={
                    activationBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !preflight.applied_run_receipt ||
                    !liveSettingsReceipt ||
                    !dispatchReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {activationBusy ? "Checking controls..." : "Activation checklist"}
                </button>
              </div>

              {activationError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {activationError}
                </p>
              )}

              {activationReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Activation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {activationReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric label="Status" value={activationReceipt.status.replaceAll("_", " ")} />
                    <Metric
                      label="Missing"
                      value={`${activationReceipt.missing_items.length} controls`}
                    />
                    <Metric
                      label="Budget reserve"
                      value={activationReceipt.budget_reservation_allowed ? "allowed" : "blocked"}
                    />
                    <Metric
                      label="Provider execution"
                      value={activationReceipt.provider_execution_allowed ? "allowed" : "blocked"}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {activationReceipt.missing_items.slice(0, 4).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Budget reservation
                </p>
                <button
                  type="button"
                  onClick={onBudgetReservationGate}
                  disabled={
                    budgetReservationBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !preflight.applied_run_receipt ||
                    !dispatchReceipt ||
                    !activationReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {budgetReservationBusy ? "Checking budget..." : "Budget reservation"}
                </button>
              </div>

              {budgetReservationError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {budgetReservationError}
                </p>
              )}

              {budgetReservationReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Budget receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {budgetReservationReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={budgetReservationReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Requested"
                      value={`$${budgetReservationReceipt.requested_reservation_usd.toFixed(2)}`}
                    />
                    <Metric
                      label="Blocker"
                      value={budgetReservationReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Reserved"
                      value={budgetReservationReceipt.budget_reserved ? "yes" : "no"}
                    />
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Provider route
                </p>
                <button
                  type="button"
                  onClick={onProviderRouteGate}
                  disabled={
                    providerRouteBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !preflight.applied_run_receipt ||
                    !dispatchReceipt ||
                    !activationReceipt ||
                    !budgetReservationReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {providerRouteBusy ? "Checking route..." : "Provider route"}
                </button>
              </div>

              {providerRouteError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {providerRouteError}
                </p>
              )}

              {providerRouteReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Provider receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {providerRouteReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={providerRouteReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric label="Routes" value={`${providerRouteReceipt.requested_route_count}`} />
                    <Metric
                      label="Blocker"
                      value={providerRouteReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Provider calls"
                      value={providerRouteReceipt.provider_calls_made ? "made" : "none"}
                    />
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Retrieval
                </p>
                <button
                  type="button"
                  onClick={onRetrievalGate}
                  disabled={
                    retrievalBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !preflight.applied_run_receipt ||
                    !dispatchReceipt ||
                    !activationReceipt ||
                    !budgetReservationReceipt ||
                    !providerRouteReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {retrievalBusy ? "Checking retrieval..." : "Retrieval"}
                </button>
              </div>

              {retrievalError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {retrievalError}
                </p>
              )}

              {retrievalReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Retrieval receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {retrievalReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric label="Status" value={retrievalReceipt.status.replaceAll("_", " ")} />
                    <Metric
                      label="Sources"
                      value={`${retrievalReceipt.planned_source_policy.length}`}
                    />
                    <Metric
                      label="Blocker"
                      value={retrievalReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Source receipts"
                      value={retrievalReceipt.source_receipts_created ? "created" : "none"}
                    />
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Graph mutation
                </p>
                <button
                  type="button"
                  onClick={onGraphMutationGate}
                  disabled={
                    graphMutationBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !preflight.applied_run_receipt ||
                    !dispatchReceipt ||
                    !activationReceipt ||
                    !budgetReservationReceipt ||
                    !providerRouteReceipt ||
                    !retrievalReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {graphMutationBusy ? "Checking graph..." : "Graph mutation"}
                </button>
              </div>

              {graphMutationError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {graphMutationError}
                </p>
              )}

              {graphMutationReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Graph receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {graphMutationReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={graphMutationReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Nodes"
                      value={`${graphMutationReceipt.planned_graph_node_ids.length}`}
                    />
                    <Metric
                      label="Blocker"
                      value={graphMutationReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Graph"
                      value={graphMutationReceipt.graph_mutated ? "mutated" : "not mutated"}
                    />
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Final artifact
                </p>
                <button
                  type="button"
                  onClick={onFinalArtifactGate}
                  disabled={
                    finalArtifactBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !preflight.applied_run_receipt ||
                    !dispatchReceipt ||
                    !activationReceipt ||
                    !budgetReservationReceipt ||
                    !providerRouteReceipt ||
                    !retrievalReceipt ||
                    !graphMutationReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {finalArtifactBusy ? "Checking artifact..." : "Final artifact"}
                </button>
              </div>

              {finalArtifactError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {finalArtifactError}
                </p>
              )}

              {finalArtifactReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Artifact receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {finalArtifactReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={finalArtifactReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric label="Format" value={finalArtifactReceipt.final_format} />
                    <Metric
                      label="Blocker"
                      value={finalArtifactReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Artifact"
                      value={finalArtifactReceipt.final_artifact_created ? "created" : "not created"}
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric label="HTML asset" value={finalArtifactReceipt.planned_artifact_id} />
                    <Metric
                      label="Twin note"
                      value={finalArtifactReceipt.planned_twin_note_document_id}
                    />
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Runner readiness
                </p>
                <button
                  type="button"
                  onClick={onRunnerReadinessGate}
                  disabled={
                    runnerReadinessBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !preflight.applied_run_receipt ||
                    !liveSettingsReceipt ||
                    !dispatchReceipt ||
                    !activationReceipt ||
                    !budgetReservationReceipt ||
                    !providerRouteReceipt ||
                    !retrievalReceipt ||
                    !graphMutationReceipt ||
                    !finalArtifactReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {runnerReadinessBusy ? "Checking readiness..." : "Runner readiness"}
                </button>
              </div>

              {runnerReadinessError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {runnerReadinessError}
                </p>
              )}

              {runnerReadinessReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Readiness receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {runnerReadinessReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={runnerReadinessReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Receipts"
                      value={`${runnerReadinessReceipt.completed_receipt_ids.length}`}
                    />
                    <Metric
                      label="Blockers"
                      value={`${runnerReadinessReceipt.remaining_blockers.length}`}
                    />
                    <Metric
                      label="Live run"
                      value={runnerReadinessReceipt.live_run_allowed ? "allowed" : "blocked"}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {runnerReadinessReceipt.remaining_blockers.slice(0, 6).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Runner control plan
                </p>
                <button
                  type="button"
                  onClick={onRunnerControlPlanGate}
                  disabled={
                    runnerControlPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerReadinessReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {runnerControlPlanBusy ? "Planning controls..." : "Runner control plan"}
                </button>
              </div>

              {runnerControlPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {runnerControlPlanError}
                </p>
              )}

              {runnerControlPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Control plan receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {runnerControlPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={runnerControlPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Scope"
                      value={`${runnerControlPlanReceipt.requested_control_scope.length}`}
                    />
                    <Metric
                      label="Requirements"
                      value={`${runnerControlPlanReceipt.implementation_requirements.length}`}
                    />
                    <Metric
                      label="Live run"
                      value={runnerControlPlanReceipt.live_run_allowed ? "allowed" : "blocked"}
                    />
                  </div>
                  <ol className="mt-2 grid grid-cols-1 gap-2 text-[11px] text-ink-soft dark:text-starlight">
                    {runnerControlPlanReceipt.implementation_requirements.map((requirement) => (
                      <li
                        key={requirement.control_key}
                        className="rounded-md border border-rule px-3 py-2 dark:border-charcoal-1"
                      >
                        <p className="font-mono text-ink dark:text-bright">
                          {requirement.control_key.replaceAll("_", " ")}
                        </p>
                        <p className="mt-1">{requirement.blocker}</p>
                        <p className="mt-1 font-mono">{requirement.required_artifact}</p>
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Budget provider adapter
                </p>
                <button
                  type="button"
                  onClick={onBudgetProviderAdapterPlanGate}
                  disabled={
                    budgetProviderAdapterPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {budgetProviderAdapterPlanBusy
                    ? "Planning adapter..."
                    : "Budget provider adapter"}
                </button>
              </div>

              {budgetProviderAdapterPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {budgetProviderAdapterPlanError}
                </p>
              )}

              {budgetProviderAdapterPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Adapter plan receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {budgetProviderAdapterPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={budgetProviderAdapterPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Ceiling"
                      value={`$${budgetProviderAdapterPlanReceipt.approved_price_ceiling_usd.toFixed(2)}`}
                    />
                    <Metric
                      label="Planned"
                      value={`$${budgetProviderAdapterPlanReceipt.planned_budget_usd.toFixed(2)}`}
                    />
                    <Metric
                      label="Reserved"
                      value={budgetProviderAdapterPlanReceipt.budget_reserved ? "yes" : "no"}
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Adapter"
                      value={budgetProviderAdapterPlanReceipt.planned_adapter_id}
                    />
                    <Metric
                      label="Ledger"
                      value={budgetProviderAdapterPlanReceipt.planned_ledger_id}
                    />
                  </div>
                  <p className="mt-2 break-all font-mono text-[11px] text-ink-soft dark:text-starlight">
                    {budgetProviderAdapterPlanReceipt.idempotency_key}
                  </p>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {budgetProviderAdapterPlanReceipt.required_invariants.slice(0, 5).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Ledger fields: {budgetProviderAdapterPlanReceipt.required_ledger_fields.join(", ")}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Provider executor adapter
                </p>
                <button
                  type="button"
                  onClick={onProviderExecutorAdapterPlanGate}
                  disabled={
                    providerExecutorAdapterPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {providerExecutorAdapterPlanBusy
                    ? "Planning executor..."
                    : "Provider executor adapter"}
                </button>
              </div>

              {providerExecutorAdapterPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {providerExecutorAdapterPlanError}
                </p>
              )}

              {providerExecutorAdapterPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Provider executor adapter receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {providerExecutorAdapterPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={providerExecutorAdapterPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Routes"
                      value={`${providerExecutorAdapterPlanReceipt.requested_route_count}`}
                    />
                    <Metric
                      label="Calls"
                      value={providerExecutorAdapterPlanReceipt.provider_calls_made ? "yes" : "no"}
                    />
                    <Metric
                      label="Live run"
                      value={providerExecutorAdapterPlanReceipt.live_run_allowed ? "allowed" : "blocked"}
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Executor"
                      value={providerExecutorAdapterPlanReceipt.planned_executor_id}
                    />
                    <Metric
                      label="Route ledger"
                      value={providerExecutorAdapterPlanReceipt.planned_route_ledger_id}
                    />
                  </div>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Route policy: {providerExecutorAdapterPlanReceipt.provider_policy.replaceAll("_", " ")}
                  </p>
                  <p className="mt-1 break-all font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Role route receipts:{" "}
                    {providerExecutorAdapterPlanReceipt.planned_role_route_receipt_ids.join(", ")}
                  </p>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {providerExecutorAdapterPlanReceipt.required_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Route receipt fields:{" "}
                    {providerExecutorAdapterPlanReceipt.required_route_receipt_fields.join(", ")}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Retrieval adapter
                </p>
                <button
                  type="button"
                  onClick={onRetrievalAdapterPlanGate}
                  disabled={
                    retrievalAdapterPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {retrievalAdapterPlanBusy ? "Planning retrieval..." : "Retrieval adapter"}
                </button>
              </div>

              {retrievalAdapterPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {retrievalAdapterPlanError}
                </p>
              )}

              {retrievalAdapterPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Retrieval adapter receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {retrievalAdapterPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={retrievalAdapterPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Sources"
                      value={`${retrievalAdapterPlanReceipt.requested_source_count}`}
                    />
                    <Metric
                      label="Retrieved"
                      value={retrievalAdapterPlanReceipt.retrieval_performed ? "yes" : "no"}
                    />
                    <Metric
                      label="Source receipts"
                      value={retrievalAdapterPlanReceipt.source_receipts_created ? "yes" : "no"}
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Executor"
                      value={retrievalAdapterPlanReceipt.planned_executor_id}
                    />
                    <Metric
                      label="Source ledger"
                      value={retrievalAdapterPlanReceipt.planned_source_ledger_id}
                    />
                  </div>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Source policy: {retrievalAdapterPlanReceipt.planned_source_policy.join(", ")}
                  </p>
                  <p className="mt-1 break-all font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Source receipts: {retrievalAdapterPlanReceipt.planned_source_receipt_ids.join(", ")}
                  </p>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {retrievalAdapterPlanReceipt.required_invariants.slice(0, 5).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Source receipt fields:{" "}
                    {retrievalAdapterPlanReceipt.required_source_receipt_fields.join(", ")}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Graph adapter
                </p>
                <button
                  type="button"
                  onClick={onGraphAdapterPlanGate}
                  disabled={
                    graphAdapterPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {graphAdapterPlanBusy ? "Planning graph..." : "Graph adapter"}
                </button>
              </div>

              {graphAdapterPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {graphAdapterPlanError}
                </p>
              )}

              {graphAdapterPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Graph adapter receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {graphAdapterPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={graphAdapterPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Nodes"
                      value={`${graphAdapterPlanReceipt.planned_graph_node_ids.length}`}
                    />
                    <Metric
                      label="Edges"
                      value={`${graphAdapterPlanReceipt.planned_graph_edge_ids.length}`}
                    />
                    <Metric
                      label="Mutated"
                      value={graphAdapterPlanReceipt.graph_mutated ? "yes" : "no"}
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric label="Writer" value={graphAdapterPlanReceipt.planned_writer_id} />
                    <Metric
                      label="Graph ledger"
                      value={graphAdapterPlanReceipt.planned_graph_ledger_id}
                    />
                  </div>
                  <p className="mt-2 break-all font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Graph nodes: {graphAdapterPlanReceipt.planned_graph_node_ids.join(", ")}
                  </p>
                  <p className="mt-1 break-all font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Graph edges: {graphAdapterPlanReceipt.planned_graph_edge_ids.join(", ")}
                  </p>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {graphAdapterPlanReceipt.required_invariants.slice(0, 5).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Graph receipt fields:{" "}
                    {graphAdapterPlanReceipt.required_graph_receipt_fields.join(", ")}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Final artifact adapter
                </p>
                <button
                  type="button"
                  onClick={onFinalArtifactAdapterPlanGate}
                  disabled={
                    finalArtifactAdapterPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {finalArtifactAdapterPlanBusy
                    ? "Planning artifact..."
                    : "Final artifact adapter"}
                </button>
              </div>

              {finalArtifactAdapterPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {finalArtifactAdapterPlanError}
                </p>
              )}

              {finalArtifactAdapterPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Final artifact adapter receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {finalArtifactAdapterPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={finalArtifactAdapterPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric label="Format" value={finalArtifactAdapterPlanReceipt.final_format} />
                    <Metric
                      label="PDF"
                      value={finalArtifactAdapterPlanReceipt.pdf_allowed ? "allowed" : "blocked"}
                    />
                    <Metric
                      label="Created"
                      value={finalArtifactAdapterPlanReceipt.final_artifact_created ? "yes" : "no"}
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Writer"
                      value={finalArtifactAdapterPlanReceipt.planned_writer_id}
                    />
                    <Metric
                      label="Artifact ledger"
                      value={finalArtifactAdapterPlanReceipt.planned_artifact_ledger_id}
                    />
                    <Metric
                      label="HTML asset"
                      value={finalArtifactAdapterPlanReceipt.planned_artifact_id}
                    />
                    <Metric
                      label="Twin note"
                      value={finalArtifactAdapterPlanReceipt.planned_twin_note_document_id}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {finalArtifactAdapterPlanReceipt.required_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Artifact receipt fields:{" "}
                    {finalArtifactAdapterPlanReceipt.required_artifact_receipt_fields.join(", ")}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator dispatch adapter
                </p>
                <button
                  type="button"
                  onClick={onOperatorDispatchAdapterPlanGate}
                  disabled={
                    operatorDispatchAdapterPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorDispatchAdapterPlanBusy
                    ? "Planning dispatch..."
                    : "Operator dispatch adapter"}
                </button>
              </div>

              {operatorDispatchAdapterPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorDispatchAdapterPlanError}
                </p>
              )}

              {operatorDispatchAdapterPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator dispatch adapter receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {operatorDispatchAdapterPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorDispatchAdapterPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Dispatch"
                      value={
                        operatorDispatchAdapterPlanReceipt.operator_dispatch_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Live toggle"
                      value={
                        operatorDispatchAdapterPlanReceipt.operator_live_dispatch_enabled
                          ? "enabled"
                          : "disabled"
                      }
                    />
                    <Metric
                      label="Artifact"
                      value={
                        operatorDispatchAdapterPlanReceipt.final_artifact_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Setting"
                      value={operatorDispatchAdapterPlanReceipt.planned_setting_id}
                    />
                    <Metric
                      label="Control ledger"
                      value={operatorDispatchAdapterPlanReceipt.planned_control_ledger_id}
                    />
                    <Metric
                      label="Adapter"
                      value={operatorDispatchAdapterPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorDispatchAdapterPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorDispatchAdapterPlanReceipt.required_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Dispatch enablement fields:{" "}
                    {operatorDispatchAdapterPlanReceipt.required_dispatch_enablement_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Control ledger adapter
                </p>
                <button
                  type="button"
                  onClick={onControlLedgerAdapterPlanGate}
                  disabled={
                    controlLedgerAdapterPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {controlLedgerAdapterPlanBusy
                    ? "Planning ledger..."
                    : "Control ledger adapter"}
                </button>
              </div>

              {controlLedgerAdapterPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {controlLedgerAdapterPlanError}
                </p>
              )}

              {controlLedgerAdapterPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Control ledger adapter receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {controlLedgerAdapterPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={controlLedgerAdapterPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Persistence"
                      value={
                        controlLedgerAdapterPlanReceipt.control_ledger_persistence_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Ledger"
                      value={
                        controlLedgerAdapterPlanReceipt.control_ledger_written
                          ? "written"
                          : "not written"
                      }
                    />
                    <Metric
                      label="Rollback"
                      value={
                        controlLedgerAdapterPlanReceipt.rollback_receipt_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Setting"
                      value={controlLedgerAdapterPlanReceipt.planned_setting_id}
                    />
                    <Metric
                      label="Control ledger"
                      value={controlLedgerAdapterPlanReceipt.planned_control_ledger_id}
                    />
                    <Metric
                      label="Audit log"
                      value={controlLedgerAdapterPlanReceipt.planned_audit_log_id}
                    />
                    <Metric
                      label="Rollback receipt"
                      value={controlLedgerAdapterPlanReceipt.planned_rollback_receipt_id}
                    />
                    <Metric
                      label="Adapter"
                      value={controlLedgerAdapterPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={controlLedgerAdapterPlanReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {controlLedgerAdapterPlanReceipt.required_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Control ledger fields:{" "}
                    {controlLedgerAdapterPlanReceipt.required_control_ledger_fields.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Rollback receipt fields:{" "}
                    {controlLedgerAdapterPlanReceipt.required_rollback_receipt_fields.join(", ")}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Control ledger persistence
                </p>
                <button
                  type="button"
                  onClick={onControlLedgerPersistencePlanGate}
                  disabled={
                    controlLedgerPersistencePlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {controlLedgerPersistencePlanBusy
                    ? "Planning persistence..."
                    : "Control ledger persistence"}
                </button>
              </div>

              {controlLedgerPersistencePlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {controlLedgerPersistencePlanError}
                </p>
              )}

              {controlLedgerPersistencePlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Control ledger persistence receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {controlLedgerPersistencePlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={controlLedgerPersistencePlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Persistence"
                      value={
                        controlLedgerPersistencePlanReceipt.persistence_adapter_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Ledger"
                      value={
                        controlLedgerPersistencePlanReceipt.control_ledger_written
                          ? "written"
                          : "not written"
                      }
                    />
                    <Metric
                      label="Audit"
                      value={
                        controlLedgerPersistencePlanReceipt.audit_log_written
                          ? "written"
                          : "not written"
                      }
                    />
                    <Metric
                      label="Rollback"
                      value={
                        controlLedgerPersistencePlanReceipt.rollback_receipt_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Repository"
                      value={controlLedgerPersistencePlanReceipt.planned_repository_id}
                    />
                    <Metric
                      label="Transaction"
                      value={controlLedgerPersistencePlanReceipt.planned_transaction_id}
                    />
                    <Metric
                      label="Setting"
                      value={controlLedgerPersistencePlanReceipt.planned_setting_id}
                    />
                    <Metric
                      label="Control ledger"
                      value={controlLedgerPersistencePlanReceipt.planned_control_ledger_id}
                    />
                    <Metric
                      label="Audit log"
                      value={controlLedgerPersistencePlanReceipt.planned_audit_log_id}
                    />
                    <Metric
                      label="Rollback receipt"
                      value={controlLedgerPersistencePlanReceipt.planned_rollback_receipt_id}
                    />
                    <Metric
                      label="Adapter"
                      value={controlLedgerPersistencePlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={controlLedgerPersistencePlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {controlLedgerPersistencePlanReceipt.required_transaction_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Storage tables:{" "}
                    {controlLedgerPersistencePlanReceipt.required_storage_tables.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Apply fields:{" "}
                    {controlLedgerPersistencePlanReceipt.required_apply_fields.join(", ")}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Control ledger persistence apply
                </p>
                <button
                  type="button"
                  onClick={onControlLedgerPersistenceApplyPlanGate}
                  disabled={
                    controlLedgerPersistenceApplyPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {controlLedgerPersistenceApplyPlanBusy
                    ? "Planning commit..."
                    : "Control ledger persistence apply"}
                </button>
              </div>

              {controlLedgerPersistenceApplyPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {controlLedgerPersistenceApplyPlanError}
                </p>
              )}

              {controlLedgerPersistenceApplyPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Control ledger persistence apply receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {controlLedgerPersistenceApplyPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={controlLedgerPersistenceApplyPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Opened"
                      value={
                        controlLedgerPersistenceApplyPlanReceipt.transaction_opened
                          ? "opened"
                          : "not opened"
                      }
                    />
                    <Metric
                      label="Committed"
                      value={
                        controlLedgerPersistenceApplyPlanReceipt.transaction_committed
                          ? "committed"
                          : "not committed"
                      }
                    />
                    <Metric
                      label="Setting"
                      value={
                        controlLedgerPersistenceApplyPlanReceipt.setting_persisted
                          ? "persisted"
                          : "not persisted"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Repository"
                      value={controlLedgerPersistenceApplyPlanReceipt.planned_repository_id}
                    />
                    <Metric
                      label="Transaction"
                      value={controlLedgerPersistenceApplyPlanReceipt.planned_transaction_id}
                    />
                    <Metric
                      label="Commit receipt"
                      value={controlLedgerPersistenceApplyPlanReceipt.planned_commit_receipt_id}
                    />
                    <Metric
                      label="Content digest"
                      value={controlLedgerPersistenceApplyPlanReceipt.planned_content_digest}
                    />
                    <Metric
                      label="Control ledger"
                      value={controlLedgerPersistenceApplyPlanReceipt.planned_control_ledger_id}
                    />
                    <Metric
                      label="Rollback receipt"
                      value={controlLedgerPersistenceApplyPlanReceipt.planned_rollback_receipt_id}
                    />
                    <Metric
                      label="Adapter"
                      value={controlLedgerPersistenceApplyPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={controlLedgerPersistenceApplyPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {controlLedgerPersistenceApplyPlanReceipt.required_commit_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Commit receipt fields:{" "}
                    {controlLedgerPersistenceApplyPlanReceipt.required_commit_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator dispatch activation readiness
                </p>
                <button
                  type="button"
                  onClick={onOperatorDispatchActivationReadinessPlanGate}
                  disabled={
                    operatorDispatchActivationReadinessPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorDispatchActivationReadinessPlanBusy
                    ? "Planning readiness..."
                    : "Operator dispatch activation readiness"}
                </button>
              </div>

              {operatorDispatchActivationReadinessPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorDispatchActivationReadinessPlanError}
                </p>
              )}

              {operatorDispatchActivationReadinessPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator dispatch activation readiness receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {operatorDispatchActivationReadinessPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorDispatchActivationReadinessPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Allowed"
                      value={
                        operatorDispatchActivationReadinessPlanReceipt
                          .activation_readiness_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Ready"
                      value={
                        operatorDispatchActivationReadinessPlanReceipt.activation_ready
                          ? "ready"
                          : "not ready"
                      }
                    />
                    <Metric
                      label="Live dispatch"
                      value={
                        operatorDispatchActivationReadinessPlanReceipt
                          .operator_live_dispatch_enabled
                          ? "enabled"
                          : "disabled"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Commit receipt"
                      value={
                        operatorDispatchActivationReadinessPlanReceipt.planned_commit_receipt_id
                      }
                    />
                    <Metric
                      label="Readiness receipt"
                      value={
                        operatorDispatchActivationReadinessPlanReceipt
                          .planned_activation_readiness_receipt_id
                      }
                    />
                    <Metric
                      label="Dispatch enablement"
                      value={
                        operatorDispatchActivationReadinessPlanReceipt
                          .planned_dispatch_enablement_id
                      }
                    />
                    <Metric
                      label="Repository"
                      value={operatorDispatchActivationReadinessPlanReceipt.planned_repository_id}
                    />
                    <Metric
                      label="Transaction"
                      value={operatorDispatchActivationReadinessPlanReceipt.planned_transaction_id}
                    />
                    <Metric
                      label="Adapter"
                      value={operatorDispatchActivationReadinessPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorDispatchActivationReadinessPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorDispatchActivationReadinessPlanReceipt.required_activation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Readiness blockers:{" "}
                    {operatorDispatchActivationReadinessPlanReceipt.readiness_blockers.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Activation receipt fields:{" "}
                    {operatorDispatchActivationReadinessPlanReceipt.required_activation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Live dispatch final enablement
                </p>
                <button
                  type="button"
                  onClick={onLiveDispatchFinalEnablementPlanGate}
                  disabled={
                    liveDispatchFinalEnablementPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {liveDispatchFinalEnablementPlanBusy
                    ? "Planning final enablement..."
                    : "Live dispatch final enablement"}
                </button>
              </div>

              {liveDispatchFinalEnablementPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {liveDispatchFinalEnablementPlanError}
                </p>
              )}

              {liveDispatchFinalEnablementPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Live dispatch final enablement receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {liveDispatchFinalEnablementPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={liveDispatchFinalEnablementPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Allowed"
                      value={
                        liveDispatchFinalEnablementPlanReceipt.final_enablement_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Ready"
                      value={
                        liveDispatchFinalEnablementPlanReceipt.live_dispatch_ready
                          ? "ready"
                          : "not ready"
                      }
                    />
                    <Metric
                      label="Live dispatch"
                      value={
                        liveDispatchFinalEnablementPlanReceipt.live_dispatch_enabled
                          ? "enabled"
                          : "disabled"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Readiness plan"
                      value={
                        liveDispatchFinalEnablementPlanReceipt
                          .operator_dispatch_activation_readiness_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Readiness receipt"
                      value={
                        liveDispatchFinalEnablementPlanReceipt
                          .planned_activation_readiness_receipt_id
                      }
                    />
                    <Metric
                      label="Dispatch enablement"
                      value={liveDispatchFinalEnablementPlanReceipt.planned_dispatch_enablement_id}
                    />
                    <Metric
                      label="Live dispatch receipt"
                      value={
                        liveDispatchFinalEnablementPlanReceipt.planned_live_dispatch_receipt_id
                      }
                    />
                    <Metric
                      label="Runner dispatch"
                      value={liveDispatchFinalEnablementPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Adapter"
                      value={liveDispatchFinalEnablementPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={liveDispatchFinalEnablementPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {liveDispatchFinalEnablementPlanReceipt.required_enablement_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final blockers:{" "}
                    {liveDispatchFinalEnablementPlanReceipt.readiness_blockers.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Enablement receipt fields:{" "}
                    {liveDispatchFinalEnablementPlanReceipt.required_enablement_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Live dispatch final enablement apply
                </p>
                <button
                  type="button"
                  onClick={onLiveDispatchFinalEnablementApplyPlanGate}
                  disabled={
                    liveDispatchFinalEnablementApplyPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {liveDispatchFinalEnablementApplyPlanBusy
                    ? "Planning final apply..."
                    : "Live dispatch final enablement apply"}
                </button>
              </div>

              {liveDispatchFinalEnablementApplyPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {liveDispatchFinalEnablementApplyPlanError}
                </p>
              )}

              {liveDispatchFinalEnablementApplyPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Live dispatch final enablement apply receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {liveDispatchFinalEnablementApplyPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={liveDispatchFinalEnablementApplyPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Allowed"
                      value={
                        liveDispatchFinalEnablementApplyPlanReceipt
                          .final_enablement_apply_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Transaction"
                      value={
                        liveDispatchFinalEnablementApplyPlanReceipt.transaction_opened
                          ? "opened"
                          : "closed"
                      }
                    />
                    <Metric
                      label="Dispatch"
                      value={
                        liveDispatchFinalEnablementApplyPlanReceipt.dispatch_performed
                          ? "performed"
                          : "not performed"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Final plan"
                      value={
                        liveDispatchFinalEnablementApplyPlanReceipt
                          .live_dispatch_final_enablement_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Apply receipt"
                      value={liveDispatchFinalEnablementApplyPlanReceipt.planned_apply_receipt_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={liveDispatchFinalEnablementApplyPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Repository"
                      value={liveDispatchFinalEnablementApplyPlanReceipt.planned_repository_id}
                    />
                    <Metric
                      label="Transaction"
                      value={liveDispatchFinalEnablementApplyPlanReceipt.planned_transaction_id}
                    />
                    <Metric
                      label="Live dispatch receipt"
                      value={
                        liveDispatchFinalEnablementApplyPlanReceipt
                          .planned_live_dispatch_receipt_id
                      }
                    />
                    <Metric
                      label="Runner dispatch"
                      value={liveDispatchFinalEnablementApplyPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Adapter"
                      value={liveDispatchFinalEnablementApplyPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={liveDispatchFinalEnablementApplyPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {liveDispatchFinalEnablementApplyPlanReceipt.required_apply_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Apply blockers:{" "}
                    {liveDispatchFinalEnablementApplyPlanReceipt.apply_blockers.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Apply receipt fields:{" "}
                    {liveDispatchFinalEnablementApplyPlanReceipt.required_apply_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Runner dispatch scheduler
                </p>
                <button
                  type="button"
                  onClick={onRunnerDispatchSchedulerPlanGate}
                  disabled={
                    runnerDispatchSchedulerPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {runnerDispatchSchedulerPlanBusy
                    ? "Planning scheduler..."
                    : "Runner dispatch scheduler"}
                </button>
              </div>

              {runnerDispatchSchedulerPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {runnerDispatchSchedulerPlanError}
                </p>
              )}

              {runnerDispatchSchedulerPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Runner dispatch scheduler receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {runnerDispatchSchedulerPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={runnerDispatchSchedulerPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Scheduler allowed"
                      value={
                        runnerDispatchSchedulerPlanReceipt.scheduler_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Job"
                      value={
                        runnerDispatchSchedulerPlanReceipt.scheduler_job_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Enqueued"
                      value={
                        runnerDispatchSchedulerPlanReceipt.runner_dispatch_enqueued
                          ? "enqueued"
                          : "not enqueued"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Apply plan"
                      value={
                        runnerDispatchSchedulerPlanReceipt
                          .live_dispatch_final_enablement_apply_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Scheduler job"
                      value={runnerDispatchSchedulerPlanReceipt.planned_scheduler_job_id}
                    />
                    <Metric
                      label="Queue"
                      value={runnerDispatchSchedulerPlanReceipt.planned_queue_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={runnerDispatchSchedulerPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Live dispatch receipt"
                      value={runnerDispatchSchedulerPlanReceipt.planned_live_dispatch_receipt_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={runnerDispatchSchedulerPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={runnerDispatchSchedulerPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={runnerDispatchSchedulerPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {runnerDispatchSchedulerPlanReceipt.required_scheduler_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Scheduler blockers:{" "}
                    {runnerDispatchSchedulerPlanReceipt.scheduler_blockers.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Scheduler receipt fields:{" "}
                    {runnerDispatchSchedulerPlanReceipt.required_scheduler_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Runner dispatch worker bootstrap
                </p>
                <button
                  type="button"
                  onClick={onRunnerDispatchWorkerBootstrapPlanGate}
                  disabled={
                    runnerDispatchWorkerBootstrapPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {runnerDispatchWorkerBootstrapPlanBusy
                    ? "Planning worker..."
                    : "Runner dispatch worker bootstrap"}
                </button>
              </div>

              {runnerDispatchWorkerBootstrapPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {runnerDispatchWorkerBootstrapPlanError}
                </p>
              )}

              {runnerDispatchWorkerBootstrapPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Runner dispatch worker bootstrap receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {runnerDispatchWorkerBootstrapPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={runnerDispatchWorkerBootstrapPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Bootstrap"
                      value={
                        runnerDispatchWorkerBootstrapPlanReceipt.worker_bootstrap_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Worker"
                      value={
                        runnerDispatchWorkerBootstrapPlanReceipt.worker_started
                          ? "started"
                          : "not started"
                      }
                    />
                    <Metric
                      label="Enqueued"
                      value={
                        runnerDispatchWorkerBootstrapPlanReceipt.runner_dispatch_enqueued
                          ? "enqueued"
                          : "not enqueued"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Scheduler plan"
                      value={
                        runnerDispatchWorkerBootstrapPlanReceipt
                          .runner_dispatch_scheduler_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Worker bootstrap"
                      value={
                        runnerDispatchWorkerBootstrapPlanReceipt.planned_worker_bootstrap_id
                      }
                    />
                    <Metric
                      label="Worker"
                      value={runnerDispatchWorkerBootstrapPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={runnerDispatchWorkerBootstrapPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Retry policy"
                      value={runnerDispatchWorkerBootstrapPlanReceipt.planned_retry_policy_id}
                    />
                    <Metric
                      label="Dead letter queue"
                      value={
                        runnerDispatchWorkerBootstrapPlanReceipt.planned_dead_letter_queue_id
                      }
                    />
                    <Metric
                      label="Scheduler job"
                      value={runnerDispatchWorkerBootstrapPlanReceipt.planned_scheduler_job_id}
                    />
                    <Metric
                      label="Queue"
                      value={runnerDispatchWorkerBootstrapPlanReceipt.planned_queue_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={runnerDispatchWorkerBootstrapPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Live dispatch receipt"
                      value={
                        runnerDispatchWorkerBootstrapPlanReceipt
                          .planned_live_dispatch_receipt_id
                      }
                    />
                    <Metric
                      label="Idempotency key"
                      value={runnerDispatchWorkerBootstrapPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={runnerDispatchWorkerBootstrapPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={runnerDispatchWorkerBootstrapPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {runnerDispatchWorkerBootstrapPlanReceipt.required_worker_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker blockers:{" "}
                    {runnerDispatchWorkerBootstrapPlanReceipt.worker_bootstrap_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker receipt fields:{" "}
                    {runnerDispatchWorkerBootstrapPlanReceipt.required_worker_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Scheduler lease retry plan
                </p>
                <button
                  type="button"
                  onClick={onSchedulerLeaseRetryPlanGate}
                  disabled={
                    schedulerLeaseRetryPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {schedulerLeaseRetryPlanBusy
                    ? "Planning leases..."
                    : "Scheduler lease retry plan"}
                </button>
              </div>

              {schedulerLeaseRetryPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {schedulerLeaseRetryPlanError}
                </p>
              )}

              {schedulerLeaseRetryPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Scheduler lease retry receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {schedulerLeaseRetryPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={schedulerLeaseRetryPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Lease retry"
                      value={
                        schedulerLeaseRetryPlanReceipt.lease_retry_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Lease policy"
                      value={
                        schedulerLeaseRetryPlanReceipt.lease_policy_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Retry policy"
                      value={
                        schedulerLeaseRetryPlanReceipt.retry_policy_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Worker bootstrap"
                      value={
                        schedulerLeaseRetryPlanReceipt
                          .runner_dispatch_worker_bootstrap_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Scheduler plan"
                      value={
                        schedulerLeaseRetryPlanReceipt.runner_dispatch_scheduler_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Lease policy"
                      value={schedulerLeaseRetryPlanReceipt.planned_lease_policy_id}
                    />
                    <Metric
                      label="Retry policy"
                      value={schedulerLeaseRetryPlanReceipt.planned_retry_policy_id}
                    />
                    <Metric
                      label="Dead letter queue"
                      value={schedulerLeaseRetryPlanReceipt.planned_dead_letter_queue_id}
                    />
                    <Metric
                      label="Visibility timeout"
                      value={`${schedulerLeaseRetryPlanReceipt.planned_visibility_timeout_seconds}s`}
                    />
                    <Metric
                      label="Lease TTL"
                      value={`${schedulerLeaseRetryPlanReceipt.planned_lease_ttl_seconds}s`}
                    />
                    <Metric
                      label="Heartbeat"
                      value={`${schedulerLeaseRetryPlanReceipt.planned_heartbeat_interval_seconds}s`}
                    />
                    <Metric
                      label="Max attempts"
                      value={String(schedulerLeaseRetryPlanReceipt.planned_max_attempts)}
                    />
                    <Metric
                      label="Backoff"
                      value={schedulerLeaseRetryPlanReceipt.planned_backoff_policy.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Worker lease"
                      value={schedulerLeaseRetryPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={schedulerLeaseRetryPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Live dispatch receipt"
                      value={schedulerLeaseRetryPlanReceipt.planned_live_dispatch_receipt_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={schedulerLeaseRetryPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={schedulerLeaseRetryPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={schedulerLeaseRetryPlanReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {schedulerLeaseRetryPlanReceipt.required_lease_retry_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Lease retry blockers:{" "}
                    {schedulerLeaseRetryPlanReceipt.lease_retry_blockers.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Lease retry receipt fields:{" "}
                    {schedulerLeaseRetryPlanReceipt.required_lease_retry_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Worker queue claim plan
                </p>
                <button
                  type="button"
                  onClick={onWorkerQueueClaimPlanGate}
                  disabled={
                    workerQueueClaimPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {workerQueueClaimPlanBusy
                    ? "Planning queue claim..."
                    : "Worker queue claim plan"}
                </button>
              </div>

              {workerQueueClaimPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {workerQueueClaimPlanError}
                </p>
              )}

              {workerQueueClaimPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Worker queue claim receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {workerQueueClaimPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={workerQueueClaimPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Queue claim"
                      value={
                        workerQueueClaimPlanReceipt.queue_claim_allowed ? "allowed" : "blocked"
                      }
                    />
                    <Metric
                      label="Claim"
                      value={
                        workerQueueClaimPlanReceipt.queue_claim_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Transaction"
                      value={
                        workerQueueClaimPlanReceipt.claim_transaction_committed
                          ? "committed"
                          : "not committed"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Lease retry plan"
                      value={workerQueueClaimPlanReceipt.scheduler_lease_retry_plan_receipt_id}
                    />
                    <Metric
                      label="Worker bootstrap"
                      value={
                        workerQueueClaimPlanReceipt
                          .runner_dispatch_worker_bootstrap_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Queue claim"
                      value={workerQueueClaimPlanReceipt.planned_queue_claim_id}
                    />
                    <Metric
                      label="Claim transaction"
                      value={workerQueueClaimPlanReceipt.planned_claim_transaction_id}
                    />
                    <Metric
                      label="Lease token"
                      value={workerQueueClaimPlanReceipt.planned_claim_lease_token_id}
                    />
                    <Metric
                      label="Claim cursor"
                      value={workerQueueClaimPlanReceipt.planned_claim_cursor_id}
                    />
                    <Metric label="Queue" value={workerQueueClaimPlanReceipt.planned_queue_id} />
                    <Metric
                      label="Worker"
                      value={workerQueueClaimPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={workerQueueClaimPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Visibility timeout"
                      value={`${workerQueueClaimPlanReceipt.planned_visibility_timeout_seconds}s`}
                    />
                    <Metric
                      label="Lease TTL"
                      value={`${workerQueueClaimPlanReceipt.planned_lease_ttl_seconds}s`}
                    />
                    <Metric
                      label="Heartbeat"
                      value={`${workerQueueClaimPlanReceipt.planned_heartbeat_interval_seconds}s`}
                    />
                    <Metric
                      label="Max attempts"
                      value={String(workerQueueClaimPlanReceipt.planned_max_attempts)}
                    />
                    <Metric
                      label="Backoff"
                      value={workerQueueClaimPlanReceipt.planned_backoff_policy.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Idempotency key"
                      value={workerQueueClaimPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Blocker"
                      value={workerQueueClaimPlanReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {workerQueueClaimPlanReceipt.required_queue_claim_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Queue claim blockers:{" "}
                    {workerQueueClaimPlanReceipt.queue_claim_blockers.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Queue claim receipt fields:{" "}
                    {workerQueueClaimPlanReceipt.required_queue_claim_receipt_fields.join(", ")}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Repository transaction plan
                </p>
                <button
                  type="button"
                  onClick={onRepositoryTransactionPlanGate}
                  disabled={
                    repositoryTransactionPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {repositoryTransactionPlanBusy
                    ? "Planning transaction..."
                    : "Repository transaction plan"}
                </button>
              </div>

              {repositoryTransactionPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {repositoryTransactionPlanError}
                </p>
              )}

              {repositoryTransactionPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Repository transaction receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {repositoryTransactionPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={repositoryTransactionPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Repository tx"
                      value={
                        repositoryTransactionPlanReceipt.repository_transaction_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Opened"
                      value={
                        repositoryTransactionPlanReceipt.repository_transaction_opened
                          ? "opened"
                          : "not opened"
                      }
                    />
                    <Metric
                      label="Committed"
                      value={
                        repositoryTransactionPlanReceipt.repository_transaction_committed
                          ? "committed"
                          : "not committed"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Queue claim plan"
                      value={repositoryTransactionPlanReceipt.worker_queue_claim_plan_receipt_id}
                    />
                    <Metric
                      label="Lease retry plan"
                      value={repositoryTransactionPlanReceipt.scheduler_lease_retry_plan_receipt_id}
                    />
                    <Metric
                      label="Repository tx"
                      value={repositoryTransactionPlanReceipt.planned_repository_transaction_id}
                    />
                    <Metric
                      label="Scope"
                      value={repositoryTransactionPlanReceipt.planned_transaction_scope.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Write set"
                      value={repositoryTransactionPlanReceipt.planned_write_set_id}
                    />
                    <Metric label="Lock" value={repositoryTransactionPlanReceipt.planned_lock_id} />
                    <Metric
                      label="Commit receipt"
                      value={repositoryTransactionPlanReceipt.planned_commit_receipt_id}
                    />
                    <Metric
                      label="Rollback receipt"
                      value={repositoryTransactionPlanReceipt.planned_rollback_receipt_id}
                    />
                    <Metric
                      label="Queue claim"
                      value={repositoryTransactionPlanReceipt.planned_queue_claim_id}
                    />
                    <Metric
                      label="Claim transaction"
                      value={repositoryTransactionPlanReceipt.planned_claim_transaction_id}
                    />
                    <Metric
                      label="Lease token"
                      value={repositoryTransactionPlanReceipt.planned_claim_lease_token_id}
                    />
                    <Metric
                      label="Claim cursor"
                      value={repositoryTransactionPlanReceipt.planned_claim_cursor_id}
                    />
                    <Metric
                      label="Queue"
                      value={repositoryTransactionPlanReceipt.planned_queue_id}
                    />
                    <Metric
                      label="Worker"
                      value={repositoryTransactionPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={repositoryTransactionPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={repositoryTransactionPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={repositoryTransactionPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={repositoryTransactionPlanReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {repositoryTransactionPlanReceipt.required_repository_transaction_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Repository transaction blockers:{" "}
                    {repositoryTransactionPlanReceipt.repository_transaction_blockers.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Repository transaction receipt fields:{" "}
                    {repositoryTransactionPlanReceipt.required_repository_transaction_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Repository commit rollback plan
                </p>
                <button
                  type="button"
                  onClick={onRepositoryCommitRollbackPlanGate}
                  disabled={
                    repositoryCommitRollbackPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {repositoryCommitRollbackPlanBusy
                    ? "Planning commit rollback..."
                    : "Repository commit rollback plan"}
                </button>
              </div>

              {repositoryCommitRollbackPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {repositoryCommitRollbackPlanError}
                </p>
              )}

              {repositoryCommitRollbackPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Repository commit rollback receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {repositoryCommitRollbackPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={repositoryCommitRollbackPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Commit"
                      value={
                        repositoryCommitRollbackPlanReceipt.repository_commit_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Rollback"
                      value={
                        repositoryCommitRollbackPlanReceipt.repository_rollback_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Receipt write"
                      value={
                        repositoryCommitRollbackPlanReceipt.commit_receipt_created ||
                        repositoryCommitRollbackPlanReceipt.rollback_receipt_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Transaction plan"
                      value={
                        repositoryCommitRollbackPlanReceipt.repository_transaction_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Queue claim plan"
                      value={repositoryCommitRollbackPlanReceipt.worker_queue_claim_plan_receipt_id}
                    />
                    <Metric
                      label="Repository tx"
                      value={repositoryCommitRollbackPlanReceipt.planned_repository_transaction_id}
                    />
                    <Metric
                      label="Scope"
                      value={repositoryCommitRollbackPlanReceipt.planned_transaction_scope.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Write set"
                      value={repositoryCommitRollbackPlanReceipt.planned_write_set_id}
                    />
                    <Metric
                      label="Lock"
                      value={repositoryCommitRollbackPlanReceipt.planned_lock_id}
                    />
                    <Metric
                      label="Commit receipt"
                      value={repositoryCommitRollbackPlanReceipt.planned_commit_receipt_id}
                    />
                    <Metric
                      label="Rollback receipt"
                      value={repositoryCommitRollbackPlanReceipt.planned_rollback_receipt_id}
                    />
                    <Metric
                      label="Commit ledger"
                      value={repositoryCommitRollbackPlanReceipt.planned_commit_ledger_entry_id}
                    />
                    <Metric
                      label="Rollback ledger"
                      value={repositoryCommitRollbackPlanReceipt.planned_rollback_ledger_entry_id}
                    />
                    <Metric
                      label="Queue claim"
                      value={repositoryCommitRollbackPlanReceipt.planned_queue_claim_id}
                    />
                    <Metric
                      label="Claim transaction"
                      value={repositoryCommitRollbackPlanReceipt.planned_claim_transaction_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={repositoryCommitRollbackPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={repositoryCommitRollbackPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={repositoryCommitRollbackPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={repositoryCommitRollbackPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {repositoryCommitRollbackPlanReceipt.required_repository_commit_rollback_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Commit rollback blockers:{" "}
                    {repositoryCommitRollbackPlanReceipt.repository_commit_rollback_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Commit rollback receipt fields:{" "}
                    {repositoryCommitRollbackPlanReceipt.required_repository_commit_rollback_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Worker lease heartbeat plan
                </p>
                <button
                  type="button"
                  onClick={onWorkerDispatchLeaseHeartbeatPlanGate}
                  disabled={
                    workerDispatchLeaseHeartbeatPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {workerDispatchLeaseHeartbeatPlanBusy
                    ? "Planning heartbeat..."
                    : "Worker lease heartbeat plan"}
                </button>
              </div>

              {workerDispatchLeaseHeartbeatPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {workerDispatchLeaseHeartbeatPlanError}
                </p>
              )}

              {workerDispatchLeaseHeartbeatPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Worker lease heartbeat receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {workerDispatchLeaseHeartbeatPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Heartbeat"
                      value={
                        workerDispatchLeaseHeartbeatPlanReceipt.worker_lease_heartbeat_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Renewal"
                      value={
                        workerDispatchLeaseHeartbeatPlanReceipt.worker_lease_renewal_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Expiry"
                      value={
                        workerDispatchLeaseHeartbeatPlanReceipt.worker_lease_expiry_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Receipt write"
                      value={
                        workerDispatchLeaseHeartbeatPlanReceipt.worker_lease_heartbeat_recorded ||
                        workerDispatchLeaseHeartbeatPlanReceipt.worker_lease_renewed ||
                        workerDispatchLeaseHeartbeatPlanReceipt.worker_lease_expired
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Commit rollback plan"
                      value={
                        workerDispatchLeaseHeartbeatPlanReceipt.repository_commit_rollback_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Transaction plan"
                      value={
                        workerDispatchLeaseHeartbeatPlanReceipt.repository_transaction_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Queue claim plan"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.worker_queue_claim_plan_receipt_id}
                    />
                    <Metric
                      label="Heartbeat receipt"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_heartbeat_receipt_id}
                    />
                    <Metric
                      label="Renewal receipt"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_lease_renewal_receipt_id}
                    />
                    <Metric
                      label="Expiry receipt"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_lease_expiry_receipt_id}
                    />
                    <Metric
                      label="Heartbeat ledger"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_heartbeat_ledger_entry_id}
                    />
                    <Metric
                      label="Queue claim"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_queue_claim_id}
                    />
                    <Metric
                      label="Claim lease token"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_claim_lease_token_id}
                    />
                    <Metric
                      label="Queue"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_queue_id}
                    />
                    <Metric
                      label="Worker"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Visibility timeout"
                      value={`${workerDispatchLeaseHeartbeatPlanReceipt.planned_visibility_timeout_seconds}s`}
                    />
                    <Metric
                      label="Lease ttl"
                      value={`${workerDispatchLeaseHeartbeatPlanReceipt.planned_lease_ttl_seconds}s`}
                    />
                    <Metric
                      label="Heartbeat interval"
                      value={`${workerDispatchLeaseHeartbeatPlanReceipt.planned_heartbeat_interval_seconds}s`}
                    />
                    <Metric
                      label="Max missed"
                      value={String(
                        workerDispatchLeaseHeartbeatPlanReceipt.planned_max_missed_heartbeats,
                      )}
                    />
                    <Metric
                      label="Idempotency key"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={workerDispatchLeaseHeartbeatPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {workerDispatchLeaseHeartbeatPlanReceipt.required_worker_dispatch_lease_heartbeat_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker lease heartbeat blockers:{" "}
                    {workerDispatchLeaseHeartbeatPlanReceipt.worker_dispatch_lease_heartbeat_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker lease heartbeat receipt fields:{" "}
                    {workerDispatchLeaseHeartbeatPlanReceipt.required_worker_dispatch_lease_heartbeat_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Worker cancellation abandon plan
                </p>
                <button
                  type="button"
                  onClick={onWorkerCancellationAbandonPlanGate}
                  disabled={
                    workerCancellationAbandonPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {workerCancellationAbandonPlanBusy
                    ? "Planning shutdown..."
                    : "Worker cancellation abandon plan"}
                </button>
              </div>

              {workerCancellationAbandonPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {workerCancellationAbandonPlanError}
                </p>
              )}

              {workerCancellationAbandonPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Worker cancellation abandon receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {workerCancellationAbandonPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={workerCancellationAbandonPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Cancellation"
                      value={
                        workerCancellationAbandonPlanReceipt.worker_cancellation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Abandon"
                      value={
                        workerCancellationAbandonPlanReceipt.worker_abandon_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Receipt write"
                      value={
                        workerCancellationAbandonPlanReceipt.worker_cancelled ||
                        workerCancellationAbandonPlanReceipt.worker_abandoned
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Heartbeat plan"
                      value={
                        workerCancellationAbandonPlanReceipt.worker_dispatch_lease_heartbeat_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Commit rollback plan"
                      value={
                        workerCancellationAbandonPlanReceipt.repository_commit_rollback_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Transaction plan"
                      value={
                        workerCancellationAbandonPlanReceipt.repository_transaction_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Queue claim plan"
                      value={workerCancellationAbandonPlanReceipt.worker_queue_claim_plan_receipt_id}
                    />
                    <Metric
                      label="Cancellation receipt"
                      value={workerCancellationAbandonPlanReceipt.planned_cancellation_receipt_id}
                    />
                    <Metric
                      label="Abandon receipt"
                      value={workerCancellationAbandonPlanReceipt.planned_abandon_receipt_id}
                    />
                    <Metric
                      label="Cancellation ledger"
                      value={
                        workerCancellationAbandonPlanReceipt.planned_cancellation_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Abandon ledger"
                      value={workerCancellationAbandonPlanReceipt.planned_abandon_ledger_entry_id}
                    />
                    <Metric
                      label="Queue claim"
                      value={workerCancellationAbandonPlanReceipt.planned_queue_claim_id}
                    />
                    <Metric
                      label="Claim lease token"
                      value={workerCancellationAbandonPlanReceipt.planned_claim_lease_token_id}
                    />
                    <Metric
                      label="Queue"
                      value={workerCancellationAbandonPlanReceipt.planned_queue_id}
                    />
                    <Metric
                      label="Worker"
                      value={workerCancellationAbandonPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={workerCancellationAbandonPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={workerCancellationAbandonPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Visibility timeout"
                      value={`${workerCancellationAbandonPlanReceipt.planned_visibility_timeout_seconds}s`}
                    />
                    <Metric
                      label="Lease ttl"
                      value={`${workerCancellationAbandonPlanReceipt.planned_lease_ttl_seconds}s`}
                    />
                    <Metric
                      label="Abandon after missed"
                      value={String(
                        workerCancellationAbandonPlanReceipt.planned_abandon_after_missed_heartbeats,
                      )}
                    />
                    <Metric
                      label="Idempotency key"
                      value={workerCancellationAbandonPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={workerCancellationAbandonPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={workerCancellationAbandonPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {workerCancellationAbandonPlanReceipt.required_worker_cancellation_abandon_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker cancellation abandon blockers:{" "}
                    {workerCancellationAbandonPlanReceipt.worker_cancellation_abandon_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker cancellation abandon receipt fields:{" "}
                    {workerCancellationAbandonPlanReceipt.required_worker_cancellation_abandon_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Worker completion finalization plan
                </p>
                <button
                  type="button"
                  onClick={onWorkerCompletionFinalizationPlanGate}
                  disabled={
                    workerCompletionFinalizationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {workerCompletionFinalizationPlanBusy
                    ? "Planning finalization..."
                    : "Worker completion finalization plan"}
                </button>
              </div>

              {workerCompletionFinalizationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {workerCompletionFinalizationPlanError}
                </p>
              )}

              {workerCompletionFinalizationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Worker completion finalization receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {workerCompletionFinalizationPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={workerCompletionFinalizationPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Completion"
                      value={
                        workerCompletionFinalizationPlanReceipt.worker_completion_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Finalization"
                      value={
                        workerCompletionFinalizationPlanReceipt.worker_finalization_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Result manifest"
                      value={
                        workerCompletionFinalizationPlanReceipt.worker_result_manifest_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Output bundle"
                      value={
                        workerCompletionFinalizationPlanReceipt.worker_output_bundle_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Receipt write"
                      value={
                        workerCompletionFinalizationPlanReceipt.worker_completed ||
                        workerCompletionFinalizationPlanReceipt.worker_finalized
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Cancellation abandon plan"
                      value={
                        workerCompletionFinalizationPlanReceipt.worker_cancellation_abandon_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Heartbeat plan"
                      value={
                        workerCompletionFinalizationPlanReceipt.worker_dispatch_lease_heartbeat_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Commit rollback plan"
                      value={
                        workerCompletionFinalizationPlanReceipt.repository_commit_rollback_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Transaction plan"
                      value={
                        workerCompletionFinalizationPlanReceipt.repository_transaction_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Queue claim plan"
                      value={workerCompletionFinalizationPlanReceipt.worker_queue_claim_plan_receipt_id}
                    />
                    <Metric
                      label="Completion receipt"
                      value={workerCompletionFinalizationPlanReceipt.planned_completion_receipt_id}
                    />
                    <Metric
                      label="Finalization receipt"
                      value={workerCompletionFinalizationPlanReceipt.planned_finalization_receipt_id}
                    />
                    <Metric
                      label="Worker result manifest"
                      value={
                        workerCompletionFinalizationPlanReceipt.planned_worker_result_manifest_id
                      }
                    />
                    <Metric
                      label="Worker output bundle"
                      value={workerCompletionFinalizationPlanReceipt.planned_worker_output_bundle_id}
                    />
                    <Metric
                      label="Completion ledger"
                      value={
                        workerCompletionFinalizationPlanReceipt.planned_completion_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Finalization ledger"
                      value={
                        workerCompletionFinalizationPlanReceipt.planned_finalization_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Queue claim"
                      value={workerCompletionFinalizationPlanReceipt.planned_queue_claim_id}
                    />
                    <Metric
                      label="Claim lease token"
                      value={workerCompletionFinalizationPlanReceipt.planned_claim_lease_token_id}
                    />
                    <Metric
                      label="Queue"
                      value={workerCompletionFinalizationPlanReceipt.planned_queue_id}
                    />
                    <Metric
                      label="Worker"
                      value={workerCompletionFinalizationPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={workerCompletionFinalizationPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={workerCompletionFinalizationPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={workerCompletionFinalizationPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={workerCompletionFinalizationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={workerCompletionFinalizationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {workerCompletionFinalizationPlanReceipt.required_worker_completion_finalization_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker completion finalization blockers:{" "}
                    {workerCompletionFinalizationPlanReceipt.worker_completion_finalization_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker completion finalization receipt fields:{" "}
                    {workerCompletionFinalizationPlanReceipt.required_worker_completion_finalization_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Worker output aggregation plan
                </p>
                <button
                  type="button"
                  onClick={onWorkerOutputAggregationPlanGate}
                  disabled={
                    workerOutputAggregationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {workerOutputAggregationPlanBusy
                    ? "Planning aggregation..."
                    : "Worker output aggregation plan"}
                </button>
              </div>

              {workerOutputAggregationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {workerOutputAggregationPlanError}
                </p>
              )}

              {workerOutputAggregationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Worker output aggregation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {workerOutputAggregationPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={workerOutputAggregationPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Aggregation"
                      value={
                        workerOutputAggregationPlanReceipt.worker_output_aggregation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Output index"
                      value={
                        workerOutputAggregationPlanReceipt.worker_output_index_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Output manifest"
                      value={
                        workerOutputAggregationPlanReceipt.worker_output_manifest_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Output summary"
                      value={
                        workerOutputAggregationPlanReceipt.worker_output_summary_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Receipt write"
                      value={
                        workerOutputAggregationPlanReceipt.worker_output_aggregated
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Completion finalization plan"
                      value={
                        workerOutputAggregationPlanReceipt.worker_completion_finalization_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Cancellation abandon plan"
                      value={
                        workerOutputAggregationPlanReceipt.worker_cancellation_abandon_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Heartbeat plan"
                      value={
                        workerOutputAggregationPlanReceipt.worker_dispatch_lease_heartbeat_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Commit rollback plan"
                      value={
                        workerOutputAggregationPlanReceipt.repository_commit_rollback_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Transaction plan"
                      value={
                        workerOutputAggregationPlanReceipt.repository_transaction_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Queue claim plan"
                      value={workerOutputAggregationPlanReceipt.worker_queue_claim_plan_receipt_id}
                    />
                    <Metric
                      label="Aggregation receipt"
                      value={
                        workerOutputAggregationPlanReceipt.planned_worker_output_aggregation_receipt_id
                      }
                    />
                    <Metric
                      label="Output index"
                      value={workerOutputAggregationPlanReceipt.planned_worker_output_index_id}
                    />
                    <Metric
                      label="Output manifest"
                      value={workerOutputAggregationPlanReceipt.planned_worker_output_manifest_id}
                    />
                    <Metric
                      label="Output summary"
                      value={workerOutputAggregationPlanReceipt.planned_worker_output_summary_id}
                    />
                    <Metric
                      label="Worker result manifest"
                      value={workerOutputAggregationPlanReceipt.planned_worker_result_manifest_id}
                    />
                    <Metric
                      label="Worker output bundle"
                      value={workerOutputAggregationPlanReceipt.planned_worker_output_bundle_id}
                    />
                    <Metric
                      label="Aggregation ledger"
                      value={
                        workerOutputAggregationPlanReceipt.planned_output_aggregation_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Queue claim"
                      value={workerOutputAggregationPlanReceipt.planned_queue_claim_id}
                    />
                    <Metric
                      label="Claim lease token"
                      value={workerOutputAggregationPlanReceipt.planned_claim_lease_token_id}
                    />
                    <Metric
                      label="Queue"
                      value={workerOutputAggregationPlanReceipt.planned_queue_id}
                    />
                    <Metric
                      label="Worker"
                      value={workerOutputAggregationPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={workerOutputAggregationPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={workerOutputAggregationPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={workerOutputAggregationPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={workerOutputAggregationPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={workerOutputAggregationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {workerOutputAggregationPlanReceipt.required_worker_output_aggregation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker output aggregation blockers:{" "}
                    {workerOutputAggregationPlanReceipt.worker_output_aggregation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker output aggregation receipt fields:{" "}
                    {workerOutputAggregationPlanReceipt.required_worker_output_aggregation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Worker synthesis handoff plan
                </p>
                <button
                  type="button"
                  onClick={onWorkerSynthesisHandoffPlanGate}
                  disabled={
                    workerSynthesisHandoffPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {workerSynthesisHandoffPlanBusy
                    ? "Planning handoff..."
                    : "Worker synthesis handoff plan"}
                </button>
              </div>

              {workerSynthesisHandoffPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {workerSynthesisHandoffPlanError}
                </p>
              )}

              {workerSynthesisHandoffPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Worker synthesis handoff receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {workerSynthesisHandoffPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={workerSynthesisHandoffPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Handoff"
                      value={
                        workerSynthesisHandoffPlanReceipt.worker_synthesis_handoff_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Handoff receipt"
                      value={
                        workerSynthesisHandoffPlanReceipt.worker_synthesis_handoff_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Input bundle"
                      value={
                        workerSynthesisHandoffPlanReceipt.synthesis_input_bundle_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Context manifest"
                      value={
                        workerSynthesisHandoffPlanReceipt.synthesis_context_manifest_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Outline"
                      value={
                        workerSynthesisHandoffPlanReceipt.synthesis_outline_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Output aggregation plan"
                      value={
                        workerSynthesisHandoffPlanReceipt.worker_output_aggregation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Completion finalization plan"
                      value={
                        workerSynthesisHandoffPlanReceipt.worker_completion_finalization_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Cancellation abandon plan"
                      value={
                        workerSynthesisHandoffPlanReceipt.worker_cancellation_abandon_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Heartbeat plan"
                      value={
                        workerSynthesisHandoffPlanReceipt.worker_dispatch_lease_heartbeat_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Commit rollback plan"
                      value={
                        workerSynthesisHandoffPlanReceipt.repository_commit_rollback_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Transaction plan"
                      value={
                        workerSynthesisHandoffPlanReceipt.repository_transaction_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Queue claim plan"
                      value={workerSynthesisHandoffPlanReceipt.worker_queue_claim_plan_receipt_id}
                    />
                    <Metric
                      label="Synthesis handoff"
                      value={
                        workerSynthesisHandoffPlanReceipt.planned_synthesis_handoff_receipt_id
                      }
                    />
                    <Metric
                      label="Input bundle"
                      value={workerSynthesisHandoffPlanReceipt.planned_synthesis_input_bundle_id}
                    />
                    <Metric
                      label="Context manifest"
                      value={
                        workerSynthesisHandoffPlanReceipt.planned_synthesis_context_manifest_id
                      }
                    />
                    <Metric
                      label="Outline"
                      value={workerSynthesisHandoffPlanReceipt.planned_synthesis_outline_id}
                    />
                    <Metric
                      label="Handoff ledger"
                      value={
                        workerSynthesisHandoffPlanReceipt.planned_synthesis_handoff_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Aggregation receipt"
                      value={
                        workerSynthesisHandoffPlanReceipt.planned_worker_output_aggregation_receipt_id
                      }
                    />
                    <Metric
                      label="Output index"
                      value={workerSynthesisHandoffPlanReceipt.planned_worker_output_index_id}
                    />
                    <Metric
                      label="Output manifest"
                      value={workerSynthesisHandoffPlanReceipt.planned_worker_output_manifest_id}
                    />
                    <Metric
                      label="Output summary"
                      value={workerSynthesisHandoffPlanReceipt.planned_worker_output_summary_id}
                    />
                    <Metric
                      label="Worker result manifest"
                      value={workerSynthesisHandoffPlanReceipt.planned_worker_result_manifest_id}
                    />
                    <Metric
                      label="Worker output bundle"
                      value={workerSynthesisHandoffPlanReceipt.planned_worker_output_bundle_id}
                    />
                    <Metric
                      label="Queue claim"
                      value={workerSynthesisHandoffPlanReceipt.planned_queue_claim_id}
                    />
                    <Metric
                      label="Claim lease token"
                      value={workerSynthesisHandoffPlanReceipt.planned_claim_lease_token_id}
                    />
                    <Metric
                      label="Queue"
                      value={workerSynthesisHandoffPlanReceipt.planned_queue_id}
                    />
                    <Metric
                      label="Worker"
                      value={workerSynthesisHandoffPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={workerSynthesisHandoffPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={workerSynthesisHandoffPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={workerSynthesisHandoffPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={workerSynthesisHandoffPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={workerSynthesisHandoffPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {workerSynthesisHandoffPlanReceipt.required_worker_synthesis_handoff_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker synthesis handoff blockers:{" "}
                    {workerSynthesisHandoffPlanReceipt.worker_synthesis_handoff_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Worker synthesis handoff receipt fields:{" "}
                    {workerSynthesisHandoffPlanReceipt.required_worker_synthesis_handoff_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Synthesis bundle assembly plan
                </p>
                <button
                  type="button"
                  onClick={onSynthesisBundleAssemblyPlanGate}
                  disabled={
                    synthesisBundleAssemblyPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {synthesisBundleAssemblyPlanBusy
                    ? "Planning bundle..."
                    : "Synthesis bundle assembly plan"}
                </button>
              </div>

              {synthesisBundleAssemblyPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {synthesisBundleAssemblyPlanError}
                </p>
              )}

              {synthesisBundleAssemblyPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Synthesis bundle assembly receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {synthesisBundleAssemblyPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={synthesisBundleAssemblyPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Assembly"
                      value={
                        synthesisBundleAssemblyPlanReceipt.synthesis_bundle_assembly_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Bundle"
                      value={
                        synthesisBundleAssemblyPlanReceipt.synthesis_bundle_assembled
                          ? "assembled"
                          : "not assembled"
                      }
                    />
                    <Metric
                      label="Source packet"
                      value={
                        synthesisBundleAssemblyPlanReceipt.synthesis_source_packet_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Evidence map"
                      value={
                        synthesisBundleAssemblyPlanReceipt.synthesis_evidence_map_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Quality gate"
                      value={
                        synthesisBundleAssemblyPlanReceipt.synthesis_quality_gate_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Synthesis handoff plan"
                      value={
                        synthesisBundleAssemblyPlanReceipt.worker_synthesis_handoff_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Output aggregation plan"
                      value={
                        synthesisBundleAssemblyPlanReceipt.worker_output_aggregation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Completion finalization plan"
                      value={
                        synthesisBundleAssemblyPlanReceipt.worker_completion_finalization_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Cancellation abandon plan"
                      value={
                        synthesisBundleAssemblyPlanReceipt.worker_cancellation_abandon_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Heartbeat plan"
                      value={
                        synthesisBundleAssemblyPlanReceipt.worker_dispatch_lease_heartbeat_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Queue claim plan"
                      value={synthesisBundleAssemblyPlanReceipt.worker_queue_claim_plan_receipt_id}
                    />
                    <Metric
                      label="Assembly receipt"
                      value={
                        synthesisBundleAssemblyPlanReceipt.planned_synthesis_bundle_assembly_receipt_id
                      }
                    />
                    <Metric
                      label="Synthesis bundle"
                      value={synthesisBundleAssemblyPlanReceipt.planned_synthesis_bundle_id}
                    />
                    <Metric
                      label="Source packet"
                      value={
                        synthesisBundleAssemblyPlanReceipt.planned_synthesis_source_packet_id
                      }
                    />
                    <Metric
                      label="Evidence map"
                      value={synthesisBundleAssemblyPlanReceipt.planned_synthesis_evidence_map_id}
                    />
                    <Metric
                      label="Composition plan"
                      value={
                        synthesisBundleAssemblyPlanReceipt.planned_synthesis_composition_plan_id
                      }
                    />
                    <Metric
                      label="Quality gate"
                      value={synthesisBundleAssemblyPlanReceipt.planned_synthesis_quality_gate_id}
                    />
                    <Metric
                      label="Synthesis handoff"
                      value={
                        synthesisBundleAssemblyPlanReceipt.planned_synthesis_handoff_receipt_id
                      }
                    />
                    <Metric
                      label="Input bundle"
                      value={synthesisBundleAssemblyPlanReceipt.planned_synthesis_input_bundle_id}
                    />
                    <Metric
                      label="Context manifest"
                      value={
                        synthesisBundleAssemblyPlanReceipt.planned_synthesis_context_manifest_id
                      }
                    />
                    <Metric
                      label="Outline"
                      value={synthesisBundleAssemblyPlanReceipt.planned_synthesis_outline_id}
                    />
                    <Metric
                      label="Output index"
                      value={synthesisBundleAssemblyPlanReceipt.planned_worker_output_index_id}
                    />
                    <Metric
                      label="Output manifest"
                      value={synthesisBundleAssemblyPlanReceipt.planned_worker_output_manifest_id}
                    />
                    <Metric
                      label="Output summary"
                      value={synthesisBundleAssemblyPlanReceipt.planned_worker_output_summary_id}
                    />
                    <Metric
                      label="Worker result manifest"
                      value={synthesisBundleAssemblyPlanReceipt.planned_worker_result_manifest_id}
                    />
                    <Metric
                      label="Worker output bundle"
                      value={synthesisBundleAssemblyPlanReceipt.planned_worker_output_bundle_id}
                    />
                    <Metric
                      label="Claim lease token"
                      value={synthesisBundleAssemblyPlanReceipt.planned_claim_lease_token_id}
                    />
                    <Metric
                      label="Worker"
                      value={synthesisBundleAssemblyPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={synthesisBundleAssemblyPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={synthesisBundleAssemblyPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={synthesisBundleAssemblyPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={synthesisBundleAssemblyPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={synthesisBundleAssemblyPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {synthesisBundleAssemblyPlanReceipt.required_synthesis_bundle_assembly_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Synthesis bundle assembly blockers:{" "}
                    {synthesisBundleAssemblyPlanReceipt.synthesis_bundle_assembly_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Synthesis bundle assembly receipt fields:{" "}
                    {synthesisBundleAssemblyPlanReceipt.required_synthesis_bundle_assembly_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Final synthesis draft plan
                </p>
                <button
                  type="button"
                  onClick={onFinalSynthesisDraftPlanGate}
                  disabled={
                    finalSynthesisDraftPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {finalSynthesisDraftPlanBusy ? "Planning draft..." : "Final synthesis draft plan"}
                </button>
              </div>

              {finalSynthesisDraftPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {finalSynthesisDraftPlanError}
                </p>
              )}

              {finalSynthesisDraftPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Final synthesis draft receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {finalSynthesisDraftPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={finalSynthesisDraftPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Draft"
                      value={
                        finalSynthesisDraftPlanReceipt.final_synthesis_draft_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Draft artifact"
                      value={
                        finalSynthesisDraftPlanReceipt.final_synthesis_draft_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Outline"
                      value={
                        finalSynthesisDraftPlanReceipt.final_synthesis_outline_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Claim map"
                      value={
                        finalSynthesisDraftPlanReceipt.final_synthesis_claim_map_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Citation map"
                      value={
                        finalSynthesisDraftPlanReceipt.final_synthesis_citation_map_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Quality report"
                      value={
                        finalSynthesisDraftPlanReceipt.final_synthesis_quality_report_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Synthesis bundle assembly plan"
                      value={finalSynthesisDraftPlanReceipt.synthesis_bundle_assembly_plan_receipt_id}
                    />
                    <Metric
                      label="Worker synthesis handoff plan"
                      value={finalSynthesisDraftPlanReceipt.worker_synthesis_handoff_plan_receipt_id}
                    />
                    <Metric
                      label="Output aggregation plan"
                      value={finalSynthesisDraftPlanReceipt.worker_output_aggregation_plan_receipt_id}
                    />
                    <Metric
                      label="Final draft receipt"
                      value={
                        finalSynthesisDraftPlanReceipt.planned_final_synthesis_draft_receipt_id
                      }
                    />
                    <Metric
                      label="Final draft"
                      value={finalSynthesisDraftPlanReceipt.planned_final_synthesis_draft_id}
                    />
                    <Metric
                      label="Final outline"
                      value={finalSynthesisDraftPlanReceipt.planned_final_synthesis_outline_id}
                    />
                    <Metric
                      label="Claim map"
                      value={finalSynthesisDraftPlanReceipt.planned_final_synthesis_claim_map_id}
                    />
                    <Metric
                      label="Citation map"
                      value={finalSynthesisDraftPlanReceipt.planned_final_synthesis_citation_map_id}
                    />
                    <Metric
                      label="Gap list"
                      value={finalSynthesisDraftPlanReceipt.planned_final_synthesis_gap_list_id}
                    />
                    <Metric
                      label="Quality report"
                      value={finalSynthesisDraftPlanReceipt.planned_final_synthesis_quality_report_id}
                    />
                    <Metric
                      label="Synthesis assembly receipt"
                      value={
                        finalSynthesisDraftPlanReceipt.planned_synthesis_bundle_assembly_receipt_id
                      }
                    />
                    <Metric
                      label="Synthesis bundle"
                      value={finalSynthesisDraftPlanReceipt.planned_synthesis_bundle_id}
                    />
                    <Metric
                      label="Source packet"
                      value={finalSynthesisDraftPlanReceipt.planned_synthesis_source_packet_id}
                    />
                    <Metric
                      label="Evidence map"
                      value={finalSynthesisDraftPlanReceipt.planned_synthesis_evidence_map_id}
                    />
                    <Metric
                      label="Composition plan"
                      value={finalSynthesisDraftPlanReceipt.planned_synthesis_composition_plan_id}
                    />
                    <Metric
                      label="Quality gate"
                      value={finalSynthesisDraftPlanReceipt.planned_synthesis_quality_gate_id}
                    />
                    <Metric
                      label="Input bundle"
                      value={finalSynthesisDraftPlanReceipt.planned_synthesis_input_bundle_id}
                    />
                    <Metric
                      label="Context manifest"
                      value={finalSynthesisDraftPlanReceipt.planned_synthesis_context_manifest_id}
                    />
                    <Metric
                      label="Outline"
                      value={finalSynthesisDraftPlanReceipt.planned_synthesis_outline_id}
                    />
                    <Metric
                      label="Output index"
                      value={finalSynthesisDraftPlanReceipt.planned_worker_output_index_id}
                    />
                    <Metric
                      label="Output manifest"
                      value={finalSynthesisDraftPlanReceipt.planned_worker_output_manifest_id}
                    />
                    <Metric
                      label="Output summary"
                      value={finalSynthesisDraftPlanReceipt.planned_worker_output_summary_id}
                    />
                    <Metric
                      label="Worker result manifest"
                      value={finalSynthesisDraftPlanReceipt.planned_worker_result_manifest_id}
                    />
                    <Metric
                      label="Worker output bundle"
                      value={finalSynthesisDraftPlanReceipt.planned_worker_output_bundle_id}
                    />
                    <Metric
                      label="Worker"
                      value={finalSynthesisDraftPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={finalSynthesisDraftPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={finalSynthesisDraftPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={finalSynthesisDraftPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={finalSynthesisDraftPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={finalSynthesisDraftPlanReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {finalSynthesisDraftPlanReceipt.required_final_synthesis_draft_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final synthesis draft blockers:{" "}
                    {finalSynthesisDraftPlanReceipt.final_synthesis_draft_blockers.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final synthesis draft receipt fields:{" "}
                    {finalSynthesisDraftPlanReceipt.required_final_synthesis_draft_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Final HTML artifact assembly plan
                </p>
                <button
                  type="button"
                  onClick={onFinalHtmlArtifactAssemblyPlanGate}
                  disabled={
                    finalHtmlArtifactAssemblyPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {finalHtmlArtifactAssemblyPlanBusy
                    ? "Planning HTML..."
                    : "Final HTML artifact assembly plan"}
                </button>
              </div>

              {finalHtmlArtifactAssemblyPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {finalHtmlArtifactAssemblyPlanError}
                </p>
              )}

              {finalHtmlArtifactAssemblyPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Final HTML artifact assembly receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {finalHtmlArtifactAssemblyPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={finalHtmlArtifactAssemblyPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Assembly"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.final_html_artifact_assembly_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="HTML artifact"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.final_html_artifact_assembled
                          ? "assembled"
                          : "not assembled"
                      }
                    />
                    <Metric
                      label="HTML asset"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.final_html_asset_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="HTML document"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.final_html_document_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Twin notes"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.final_html_twin_notes_document_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Citation index"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.final_html_citation_index_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Export manifest"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.final_html_export_manifest_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Final synthesis draft plan"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.final_synthesis_draft_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Synthesis bundle assembly plan"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.synthesis_bundle_assembly_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Worker synthesis handoff plan"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.worker_synthesis_handoff_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Output aggregation plan"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.worker_output_aggregation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="HTML assembly receipt"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_final_html_artifact_assembly_receipt_id
                      }
                    />
                    <Metric
                      label="HTML artifact"
                      value={finalHtmlArtifactAssemblyPlanReceipt.planned_final_html_artifact_id}
                    />
                    <Metric
                      label="HTML asset"
                      value={finalHtmlArtifactAssemblyPlanReceipt.planned_final_html_asset_id}
                    />
                    <Metric
                      label="HTML document"
                      value={finalHtmlArtifactAssemblyPlanReceipt.planned_final_html_document_id}
                    />
                    <Metric
                      label="Twin notes document"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_final_html_twin_notes_document_id
                      }
                    />
                    <Metric
                      label="Citation index"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_final_html_citation_index_id
                      }
                    />
                    <Metric
                      label="Export manifest"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_final_html_export_manifest_id
                      }
                    />
                    <Metric
                      label="Final draft receipt"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_final_synthesis_draft_receipt_id
                      }
                    />
                    <Metric
                      label="Final draft"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_final_synthesis_draft_id
                      }
                    />
                    <Metric
                      label="Claim map"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_final_synthesis_claim_map_id
                      }
                    />
                    <Metric
                      label="Citation map"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_final_synthesis_citation_map_id
                      }
                    />
                    <Metric
                      label="Quality report"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_final_synthesis_quality_report_id
                      }
                    />
                    <Metric
                      label="Synthesis bundle"
                      value={finalHtmlArtifactAssemblyPlanReceipt.planned_synthesis_bundle_id}
                    />
                    <Metric
                      label="Source packet"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_synthesis_source_packet_id
                      }
                    />
                    <Metric
                      label="Evidence map"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_synthesis_evidence_map_id
                      }
                    />
                    <Metric
                      label="Composition plan"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_synthesis_composition_plan_id
                      }
                    />
                    <Metric
                      label="Quality gate"
                      value={
                        finalHtmlArtifactAssemblyPlanReceipt.planned_synthesis_quality_gate_id
                      }
                    />
                    <Metric
                      label="Worker"
                      value={finalHtmlArtifactAssemblyPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Worker lease"
                      value={finalHtmlArtifactAssemblyPlanReceipt.planned_worker_lease_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={finalHtmlArtifactAssemblyPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={finalHtmlArtifactAssemblyPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={finalHtmlArtifactAssemblyPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={finalHtmlArtifactAssemblyPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {finalHtmlArtifactAssemblyPlanReceipt.required_final_html_artifact_assembly_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final HTML artifact assembly blockers:{" "}
                    {finalHtmlArtifactAssemblyPlanReceipt.final_html_artifact_assembly_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final HTML artifact assembly receipt fields:{" "}
                    {finalHtmlArtifactAssemblyPlanReceipt.required_final_html_artifact_assembly_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Final artifact persistence plan
                </p>
                <button
                  type="button"
                  onClick={onFinalArtifactPersistencePlanGate}
                  disabled={
                    finalArtifactPersistencePlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {finalArtifactPersistencePlanBusy
                    ? "Planning persistence..."
                    : "Final artifact persistence plan"}
                </button>
              </div>

              {finalArtifactPersistencePlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {finalArtifactPersistencePlanError}
                </p>
              )}

              {finalArtifactPersistencePlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Final artifact persistence receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {finalArtifactPersistencePlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={finalArtifactPersistencePlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Persistence"
                      value={
                        finalArtifactPersistencePlanReceipt.final_artifact_persistence_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Final artifact"
                      value={
                        finalArtifactPersistencePlanReceipt.final_artifact_persisted
                          ? "persisted"
                          : "not persisted"
                      }
                    />
                    <Metric
                      label="Information asset"
                      value={
                        finalArtifactPersistencePlanReceipt.information_asset_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Hosted HTML"
                      value={
                        finalArtifactPersistencePlanReceipt.hosted_html_asset_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Graph node"
                      value={
                        finalArtifactPersistencePlanReceipt.graph_node_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Graph edges"
                      value={
                        finalArtifactPersistencePlanReceipt.graph_edge_set_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Ledger entry"
                      value={
                        finalArtifactPersistencePlanReceipt.artifact_ledger_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="HTML assembly plan"
                      value={
                        finalArtifactPersistencePlanReceipt.final_html_artifact_assembly_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Final synthesis draft plan"
                      value={
                        finalArtifactPersistencePlanReceipt.final_synthesis_draft_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Synthesis bundle assembly plan"
                      value={
                        finalArtifactPersistencePlanReceipt.synthesis_bundle_assembly_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Persistence receipt"
                      value={
                        finalArtifactPersistencePlanReceipt.planned_final_artifact_persistence_receipt_id
                      }
                    />
                    <Metric
                      label="Persisted final artifact"
                      value={finalArtifactPersistencePlanReceipt.planned_persisted_final_artifact_id}
                    />
                    <Metric
                      label="Information asset"
                      value={finalArtifactPersistencePlanReceipt.planned_information_asset_id}
                    />
                    <Metric
                      label="Hosted HTML asset"
                      value={finalArtifactPersistencePlanReceipt.planned_hosted_html_asset_id}
                    />
                    <Metric
                      label="Account binding"
                      value={finalArtifactPersistencePlanReceipt.planned_account_asset_binding_id}
                    />
                    <Metric
                      label="Twin notes binding"
                      value={finalArtifactPersistencePlanReceipt.planned_twin_notes_binding_id}
                    />
                    <Metric
                      label="Citation binding"
                      value={finalArtifactPersistencePlanReceipt.planned_citation_index_binding_id}
                    />
                    <Metric
                      label="Graph node"
                      value={finalArtifactPersistencePlanReceipt.planned_graph_node_id}
                    />
                    <Metric
                      label="Graph edge set"
                      value={finalArtifactPersistencePlanReceipt.planned_graph_edge_set_id}
                    />
                    <Metric
                      label="Artifact ledger entry"
                      value={finalArtifactPersistencePlanReceipt.planned_artifact_ledger_entry_id}
                    />
                    <Metric
                      label="HTML artifact"
                      value={finalArtifactPersistencePlanReceipt.planned_final_html_artifact_id}
                    />
                    <Metric
                      label="HTML document"
                      value={finalArtifactPersistencePlanReceipt.planned_final_html_document_id}
                    />
                    <Metric
                      label="Twin notes document"
                      value={
                        finalArtifactPersistencePlanReceipt.planned_final_html_twin_notes_document_id
                      }
                    />
                    <Metric
                      label="Citation index"
                      value={
                        finalArtifactPersistencePlanReceipt.planned_final_html_citation_index_id
                      }
                    />
                    <Metric
                      label="Export manifest"
                      value={
                        finalArtifactPersistencePlanReceipt.planned_final_html_export_manifest_id
                      }
                    />
                    <Metric
                      label="Final draft"
                      value={finalArtifactPersistencePlanReceipt.planned_final_synthesis_draft_id}
                    />
                    <Metric
                      label="Synthesis bundle"
                      value={finalArtifactPersistencePlanReceipt.planned_synthesis_bundle_id}
                    />
                    <Metric
                      label="Source packet"
                      value={finalArtifactPersistencePlanReceipt.planned_synthesis_source_packet_id}
                    />
                    <Metric
                      label="Evidence map"
                      value={finalArtifactPersistencePlanReceipt.planned_synthesis_evidence_map_id}
                    />
                    <Metric
                      label="Worker"
                      value={finalArtifactPersistencePlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={finalArtifactPersistencePlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={finalArtifactPersistencePlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={finalArtifactPersistencePlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={finalArtifactPersistencePlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {finalArtifactPersistencePlanReceipt.required_final_artifact_persistence_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final artifact persistence blockers:{" "}
                    {finalArtifactPersistencePlanReceipt.final_artifact_persistence_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final artifact persistence receipt fields:{" "}
                    {finalArtifactPersistencePlanReceipt.required_final_artifact_persistence_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Final artifact graph commit plan
                </p>
                <button
                  type="button"
                  onClick={onFinalArtifactGraphCommitPlanGate}
                  disabled={
                    finalArtifactGraphCommitPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {finalArtifactGraphCommitPlanBusy
                    ? "Planning graph commit..."
                    : "Final artifact graph commit plan"}
                </button>
              </div>

              {finalArtifactGraphCommitPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {finalArtifactGraphCommitPlanError}
                </p>
              )}

              {finalArtifactGraphCommitPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Final artifact graph commit receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {finalArtifactGraphCommitPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={finalArtifactGraphCommitPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Graph commit"
                      value={
                        finalArtifactGraphCommitPlanReceipt.final_artifact_graph_commit_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Commit"
                      value={
                        finalArtifactGraphCommitPlanReceipt.graph_commit_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Transaction"
                      value={
                        finalArtifactGraphCommitPlanReceipt.graph_transaction_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Node commit"
                      value={
                        finalArtifactGraphCommitPlanReceipt.graph_node_committed
                          ? "committed"
                          : "not committed"
                      }
                    />
                    <Metric
                      label="Edge commit"
                      value={
                        finalArtifactGraphCommitPlanReceipt.graph_edge_set_committed
                          ? "committed"
                          : "not committed"
                      }
                    />
                    <Metric
                      label="Snapshot"
                      value={
                        finalArtifactGraphCommitPlanReceipt.graph_snapshot_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Lineage index"
                      value={
                        finalArtifactGraphCommitPlanReceipt.graph_lineage_index_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Persistence plan"
                      value={
                        finalArtifactGraphCommitPlanReceipt.final_artifact_persistence_plan_receipt_id
                      }
                    />
                    <Metric
                      label="HTML assembly plan"
                      value={
                        finalArtifactGraphCommitPlanReceipt.final_html_artifact_assembly_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Graph commit receipt"
                      value={
                        finalArtifactGraphCommitPlanReceipt.planned_final_artifact_graph_commit_receipt_id
                      }
                    />
                    <Metric
                      label="Graph commit"
                      value={finalArtifactGraphCommitPlanReceipt.planned_graph_commit_id}
                    />
                    <Metric
                      label="Graph transaction"
                      value={finalArtifactGraphCommitPlanReceipt.planned_graph_transaction_id}
                    />
                    <Metric
                      label="Graph node"
                      value={finalArtifactGraphCommitPlanReceipt.planned_graph_node_id}
                    />
                    <Metric
                      label="Graph edge set"
                      value={finalArtifactGraphCommitPlanReceipt.planned_graph_edge_set_id}
                    />
                    <Metric
                      label="Graph snapshot"
                      value={finalArtifactGraphCommitPlanReceipt.planned_graph_snapshot_id}
                    />
                    <Metric
                      label="Graph lineage index"
                      value={finalArtifactGraphCommitPlanReceipt.planned_graph_lineage_index_id}
                    />
                    <Metric
                      label="Information asset"
                      value={finalArtifactGraphCommitPlanReceipt.planned_information_asset_id}
                    />
                    <Metric
                      label="Hosted HTML asset"
                      value={finalArtifactGraphCommitPlanReceipt.planned_hosted_html_asset_id}
                    />
                    <Metric
                      label="Artifact ledger entry"
                      value={finalArtifactGraphCommitPlanReceipt.planned_artifact_ledger_entry_id}
                    />
                    <Metric
                      label="HTML artifact"
                      value={finalArtifactGraphCommitPlanReceipt.planned_final_html_artifact_id}
                    />
                    <Metric
                      label="HTML document"
                      value={finalArtifactGraphCommitPlanReceipt.planned_final_html_document_id}
                    />
                    <Metric
                      label="Final draft"
                      value={finalArtifactGraphCommitPlanReceipt.planned_final_synthesis_draft_id}
                    />
                    <Metric
                      label="Synthesis bundle"
                      value={finalArtifactGraphCommitPlanReceipt.planned_synthesis_bundle_id}
                    />
                    <Metric
                      label="Source packet"
                      value={
                        finalArtifactGraphCommitPlanReceipt.planned_synthesis_source_packet_id
                      }
                    />
                    <Metric
                      label="Evidence map"
                      value={finalArtifactGraphCommitPlanReceipt.planned_synthesis_evidence_map_id}
                    />
                    <Metric
                      label="Worker"
                      value={finalArtifactGraphCommitPlanReceipt.planned_worker_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={finalArtifactGraphCommitPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={finalArtifactGraphCommitPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={finalArtifactGraphCommitPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={finalArtifactGraphCommitPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {finalArtifactGraphCommitPlanReceipt.required_final_artifact_graph_commit_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final artifact graph commit blockers:{" "}
                    {finalArtifactGraphCommitPlanReceipt.final_artifact_graph_commit_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final artifact graph commit receipt fields:{" "}
                    {finalArtifactGraphCommitPlanReceipt.required_final_artifact_graph_commit_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Final artifact publish plan
                </p>
                <button
                  type="button"
                  onClick={onFinalArtifactPublishPlanGate}
                  disabled={
                    finalArtifactPublishPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {finalArtifactPublishPlanBusy
                    ? "Planning publish..."
                    : "Final artifact publish plan"}
                </button>
              </div>

              {finalArtifactPublishPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {finalArtifactPublishPlanError}
                </p>
              )}

              {finalArtifactPublishPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Final artifact publish receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {finalArtifactPublishPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={finalArtifactPublishPlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Publish"
                      value={
                        finalArtifactPublishPlanReceipt.final_artifact_publish_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Transaction"
                      value={
                        finalArtifactPublishPlanReceipt.publish_transaction_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Published asset"
                      value={
                        finalArtifactPublishPlanReceipt.information_asset_published
                          ? "published"
                          : "not published"
                      }
                    />
                    <Metric
                      label="Account asset"
                      value={
                        finalArtifactPublishPlanReceipt.account_visible_asset_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Reading entry"
                      value={
                        finalArtifactPublishPlanReceipt.reading_workspace_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Search index"
                      value={
                        finalArtifactPublishPlanReceipt.search_index_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Private URL"
                      value={
                        finalArtifactPublishPlanReceipt.private_read_url_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Notification"
                      value={
                        finalArtifactPublishPlanReceipt.operator_notification_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Graph commit plan"
                      value={
                        finalArtifactPublishPlanReceipt.final_artifact_graph_commit_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Persistence plan"
                      value={
                        finalArtifactPublishPlanReceipt.final_artifact_persistence_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Publish receipt"
                      value={
                        finalArtifactPublishPlanReceipt.planned_final_artifact_publish_receipt_id
                      }
                    />
                    <Metric
                      label="Publish transaction"
                      value={finalArtifactPublishPlanReceipt.planned_publish_transaction_id}
                    />
                    <Metric
                      label="Published information asset"
                      value={
                        finalArtifactPublishPlanReceipt.planned_published_information_asset_id
                      }
                    />
                    <Metric
                      label="Account-visible asset"
                      value={finalArtifactPublishPlanReceipt.planned_account_visible_asset_id}
                    />
                    <Metric
                      label="Reading workspace entry"
                      value={finalArtifactPublishPlanReceipt.planned_reading_workspace_entry_id}
                    />
                    <Metric
                      label="Twin notes workspace entry"
                      value={
                        finalArtifactPublishPlanReceipt.planned_twin_notes_workspace_entry_id
                      }
                    />
                    <Metric
                      label="Search index entry"
                      value={finalArtifactPublishPlanReceipt.planned_search_index_entry_id}
                    />
                    <Metric
                      label="Share policy"
                      value={finalArtifactPublishPlanReceipt.planned_share_policy_id}
                    />
                    <Metric
                      label="Private read URL"
                      value={finalArtifactPublishPlanReceipt.planned_private_read_url_id}
                    />
                    <Metric
                      label="Operator notification"
                      value={finalArtifactPublishPlanReceipt.planned_operator_notification_id}
                    />
                    <Metric
                      label="Graph commit"
                      value={finalArtifactPublishPlanReceipt.planned_graph_commit_id}
                    />
                    <Metric
                      label="Graph snapshot"
                      value={finalArtifactPublishPlanReceipt.planned_graph_snapshot_id}
                    />
                    <Metric
                      label="Graph lineage index"
                      value={finalArtifactPublishPlanReceipt.planned_graph_lineage_index_id}
                    />
                    <Metric
                      label="Information asset"
                      value={finalArtifactPublishPlanReceipt.planned_information_asset_id}
                    />
                    <Metric
                      label="Hosted HTML asset"
                      value={finalArtifactPublishPlanReceipt.planned_hosted_html_asset_id}
                    />
                    <Metric
                      label="HTML artifact"
                      value={finalArtifactPublishPlanReceipt.planned_final_html_artifact_id}
                    />
                    <Metric
                      label="HTML document"
                      value={finalArtifactPublishPlanReceipt.planned_final_html_document_id}
                    />
                    <Metric
                      label="Source packet"
                      value={finalArtifactPublishPlanReceipt.planned_synthesis_source_packet_id}
                    />
                    <Metric
                      label="Evidence map"
                      value={finalArtifactPublishPlanReceipt.planned_synthesis_evidence_map_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={finalArtifactPublishPlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={finalArtifactPublishPlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={finalArtifactPublishPlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={finalArtifactPublishPlanReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {finalArtifactPublishPlanReceipt.required_final_artifact_publish_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final artifact publish blockers:{" "}
                    {finalArtifactPublishPlanReceipt.final_artifact_publish_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final artifact publish receipt fields:{" "}
                    {finalArtifactPublishPlanReceipt.required_final_artifact_publish_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Final artifact completion finalization plan
                </p>
                <button
                  type="button"
                  onClick={onFinalArtifactCompletionFinalizationPlanGate}
                  disabled={
                    finalArtifactCompletionFinalizationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {finalArtifactCompletionFinalizationPlanBusy
                    ? "Planning finalization..."
                    : "Final artifact completion finalization plan"}
                </button>
              </div>

              {finalArtifactCompletionFinalizationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {finalArtifactCompletionFinalizationPlanError}
                </p>
              )}

              {finalArtifactCompletionFinalizationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Final artifact completion finalization receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {finalArtifactCompletionFinalizationPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={finalArtifactCompletionFinalizationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Completion finalization"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.final_artifact_completion_finalization_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Completion record"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.completion_record_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Finalization transaction"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.finalization_transaction_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Archive manifest"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.artifact_archive_manifest_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Operator handoff"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.operator_handoff_summary_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery status"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.delivery_status_marked_complete
                          ? "complete"
                          : "not complete"
                      }
                    />
                    <Metric
                      label="Quality attestation"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.quality_attestation_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Completion audit"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.completion_audit_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Publish plan"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.final_artifact_publish_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Graph commit plan"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.final_artifact_graph_commit_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Completion receipt"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_final_artifact_completion_receipt_id
                      }
                    />
                    <Metric
                      label="Finalization receipt"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_final_artifact_finalization_receipt_id
                      }
                    />
                    <Metric
                      label="Completion record"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_completion_record_id
                      }
                    />
                    <Metric
                      label="Finalization transaction"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_finalization_transaction_id
                      }
                    />
                    <Metric
                      label="Archive manifest"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_artifact_archive_manifest_id
                      }
                    />
                    <Metric
                      label="Operator handoff summary"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_operator_handoff_summary_id
                      }
                    />
                    <Metric
                      label="Delivery status"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_delivery_status_id
                      }
                    />
                    <Metric
                      label="Quality attestation"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_quality_attestation_id
                      }
                    />
                    <Metric
                      label="Completion audit entry"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_completion_audit_entry_id
                      }
                    />
                    <Metric
                      label="Publish transaction"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_publish_transaction_id
                      }
                    />
                    <Metric
                      label="Account-visible asset"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_account_visible_asset_id
                      }
                    />
                    <Metric
                      label="Reading workspace entry"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_reading_workspace_entry_id
                      }
                    />
                    <Metric
                      label="Search index entry"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_search_index_entry_id
                      }
                    />
                    <Metric
                      label="Private read URL"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_private_read_url_id
                      }
                    />
                    <Metric
                      label="Graph commit"
                      value={finalArtifactCompletionFinalizationPlanReceipt.planned_graph_commit_id}
                    />
                    <Metric
                      label="Graph snapshot"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_graph_snapshot_id
                      }
                    />
                    <Metric
                      label="Information asset"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_information_asset_id
                      }
                    />
                    <Metric
                      label="Hosted HTML asset"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_hosted_html_asset_id
                      }
                    />
                    <Metric
                      label="Runner dispatch"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_runner_dispatch_id
                      }
                    />
                    <Metric
                      label="Idempotency key"
                      value={
                        finalArtifactCompletionFinalizationPlanReceipt.planned_idempotency_key
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={finalArtifactCompletionFinalizationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={finalArtifactCompletionFinalizationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {finalArtifactCompletionFinalizationPlanReceipt.required_final_artifact_completion_finalization_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final artifact completion finalization blockers:{" "}
                    {finalArtifactCompletionFinalizationPlanReceipt.final_artifact_completion_finalization_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final artifact completion finalization receipt fields:{" "}
                    {finalArtifactCompletionFinalizationPlanReceipt.required_final_artifact_completion_finalization_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Final run closure plan
                </p>
                <button
                  type="button"
                  onClick={onFinalRunClosurePlanGate}
                  disabled={
                    finalRunClosurePlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {finalRunClosurePlanBusy ? "Planning closure..." : "Final run closure plan"}
                </button>
              </div>

              {finalRunClosurePlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {finalRunClosurePlanError}
                </p>
              )}

              {finalRunClosurePlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Final run closure receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {finalRunClosurePlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={finalRunClosurePlanReceipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Closure"
                      value={
                        finalRunClosurePlanReceipt.final_run_closure_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Closeout"
                      value={
                        finalRunClosurePlanReceipt.run_closeout_record_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery ledger"
                      value={
                        finalRunClosurePlanReceipt.operator_delivery_ledger_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Notification"
                      value={
                        finalRunClosurePlanReceipt.delivery_notification_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Workspace card"
                      value={
                        finalRunClosurePlanReceipt.workspace_delivery_card_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Retention"
                      value={
                        finalRunClosurePlanReceipt.run_retention_manifest_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Billing"
                      value={
                        finalRunClosurePlanReceipt.billing_reconciliation_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Usage rollup"
                      value={
                        finalRunClosurePlanReceipt.model_usage_rollup_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Completion finalization plan"
                      value={
                        finalRunClosurePlanReceipt.final_artifact_completion_finalization_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Publish plan"
                      value={finalRunClosurePlanReceipt.final_artifact_publish_plan_receipt_id}
                    />
                    <Metric
                      label="Closure receipt"
                      value={finalRunClosurePlanReceipt.planned_final_run_closure_receipt_id}
                    />
                    <Metric
                      label="Closeout record"
                      value={finalRunClosurePlanReceipt.planned_run_closeout_record_id}
                    />
                    <Metric
                      label="Delivery ledger"
                      value={
                        finalRunClosurePlanReceipt.planned_operator_delivery_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Delivery notification"
                      value={finalRunClosurePlanReceipt.planned_delivery_notification_id}
                    />
                    <Metric
                      label="Workspace card"
                      value={finalRunClosurePlanReceipt.planned_workspace_delivery_card_id}
                    />
                    <Metric
                      label="Retention manifest"
                      value={finalRunClosurePlanReceipt.planned_run_retention_manifest_id}
                    />
                    <Metric
                      label="Billing reconciliation"
                      value={finalRunClosurePlanReceipt.planned_billing_reconciliation_id}
                    />
                    <Metric
                      label="Model usage rollup"
                      value={finalRunClosurePlanReceipt.planned_model_usage_rollup_id}
                    />
                    <Metric
                      label="Source lineage archive"
                      value={finalRunClosurePlanReceipt.planned_source_lineage_archive_id}
                    />
                    <Metric
                      label="Completion record"
                      value={finalRunClosurePlanReceipt.planned_completion_record_id}
                    />
                    <Metric
                      label="Quality attestation"
                      value={finalRunClosurePlanReceipt.planned_quality_attestation_id}
                    />
                    <Metric
                      label="Completion audit"
                      value={finalRunClosurePlanReceipt.planned_completion_audit_entry_id}
                    />
                    <Metric
                      label="Account-visible asset"
                      value={finalRunClosurePlanReceipt.planned_account_visible_asset_id}
                    />
                    <Metric
                      label="Reading workspace entry"
                      value={finalRunClosurePlanReceipt.planned_reading_workspace_entry_id}
                    />
                    <Metric
                      label="Search index entry"
                      value={finalRunClosurePlanReceipt.planned_search_index_entry_id}
                    />
                    <Metric
                      label="Private read URL"
                      value={finalRunClosurePlanReceipt.planned_private_read_url_id}
                    />
                    <Metric
                      label="Hosted HTML asset"
                      value={finalRunClosurePlanReceipt.planned_hosted_html_asset_id}
                    />
                    <Metric
                      label="Runner dispatch"
                      value={finalRunClosurePlanReceipt.planned_runner_dispatch_id}
                    />
                    <Metric
                      label="Idempotency key"
                      value={finalRunClosurePlanReceipt.planned_idempotency_key}
                    />
                    <Metric
                      label="Adapter"
                      value={finalRunClosurePlanReceipt.adapter_key.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Blocker"
                      value={finalRunClosurePlanReceipt.blocker_reason.replaceAll("_", " ")}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {finalRunClosurePlanReceipt.required_final_run_closure_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final run closure blockers:{" "}
                    {finalRunClosurePlanReceipt.final_run_closure_blockers.join(", ")}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final run closure receipt fields:{" "}
                    {finalRunClosurePlanReceipt.required_final_run_closure_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator notification delivery readiness plan
                </p>
                <button
                  type="button"
                  onClick={onOperatorNotificationDeliveryReadinessPlanGate}
                  disabled={
                    operatorNotificationDeliveryReadinessPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorNotificationDeliveryReadinessPlanBusy
                    ? "Planning notification..."
                    : "Operator notification delivery readiness plan"}
                </button>
              </div>

              {operatorNotificationDeliveryReadinessPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorNotificationDeliveryReadinessPlanError}
                </p>
              )}

              {operatorNotificationDeliveryReadinessPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator notification delivery readiness receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {operatorNotificationDeliveryReadinessPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorNotificationDeliveryReadinessPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Notification readiness"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.operator_notification_delivery_readiness_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Dispatch"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.operator_notification_dispatch_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Payload"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.operator_notification_payload_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Channel policy"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.operator_delivery_channel_policy_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Template"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.operator_notification_template_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Notification audit"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.operator_notification_audit_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery ledger"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.operator_delivery_ledger_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Workspace card"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.workspace_delivery_card_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Final run closure plan"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.final_run_closure_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Readiness receipt"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_operator_notification_delivery_readiness_receipt_id
                      }
                    />
                    <Metric
                      label="Notification dispatch"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_operator_notification_dispatch_id
                      }
                    />
                    <Metric
                      label="Notification payload"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_operator_notification_payload_id
                      }
                    />
                    <Metric
                      label="Channel policy"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_operator_delivery_channel_policy_id
                      }
                    />
                    <Metric
                      label="Notification template"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_operator_notification_template_id
                      }
                    />
                    <Metric
                      label="Notification audit"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_operator_notification_audit_entry_id
                      }
                    />
                    <Metric
                      label="Workspace card"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_workspace_delivery_card_id
                      }
                    />
                    <Metric
                      label="Delivery ledger"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_operator_delivery_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Private read URL"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_private_read_url_id
                      }
                    />
                    <Metric
                      label="Hosted HTML asset"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_hosted_html_asset_id
                      }
                    />
                    <Metric
                      label="Model usage rollup"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_model_usage_rollup_id
                      }
                    />
                    <Metric
                      label="Source lineage archive"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_source_lineage_archive_id
                      }
                    />
                    <Metric
                      label="Idempotency key"
                      value={
                        operatorNotificationDeliveryReadinessPlanReceipt.planned_idempotency_key
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorNotificationDeliveryReadinessPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorNotificationDeliveryReadinessPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorNotificationDeliveryReadinessPlanReceipt.required_operator_notification_delivery_readiness_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator notification delivery readiness blockers:{" "}
                    {operatorNotificationDeliveryReadinessPlanReceipt.operator_notification_delivery_readiness_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator notification delivery readiness receipt fields:{" "}
                    {operatorNotificationDeliveryReadinessPlanReceipt.required_operator_notification_delivery_readiness_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator notification delivery apply plan
                </p>
                <button
                  type="button"
                  onClick={onOperatorNotificationDeliveryApplyPlanGate}
                  disabled={
                    operatorNotificationDeliveryApplyPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorNotificationDeliveryApplyPlanBusy
                    ? "Planning delivery apply..."
                    : "Operator notification delivery apply plan"}
                </button>
              </div>

              {operatorNotificationDeliveryApplyPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorNotificationDeliveryApplyPlanError}
                </p>
              )}

              {operatorNotificationDeliveryApplyPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator notification delivery apply receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {operatorNotificationDeliveryApplyPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorNotificationDeliveryApplyPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Delivery apply"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_delivery_apply_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Delivery transaction"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_delivery_transaction_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Dispatch"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_dispatch_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Payload"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_payload_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery attempt"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_delivery_attempt_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery result"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_delivery_result_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery status"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_delivery_status_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Retry policy"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_retry_policy_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Dead letter"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_dead_letter_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Operator notification"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Private URL"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.private_read_url_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Readiness plan"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.operator_notification_delivery_readiness_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Final run closure plan"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.final_run_closure_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Apply receipt"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_operator_notification_delivery_apply_receipt_id
                      }
                    />
                    <Metric
                      label="Delivery transaction"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_operator_notification_delivery_transaction_id
                      }
                    />
                    <Metric
                      label="Notification dispatch"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_operator_notification_dispatch_id
                      }
                    />
                    <Metric
                      label="Notification payload"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_operator_notification_payload_id
                      }
                    />
                    <Metric
                      label="Delivery attempt"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_operator_notification_delivery_attempt_id
                      }
                    />
                    <Metric
                      label="Delivery result"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_operator_notification_delivery_result_id
                      }
                    />
                    <Metric
                      label="Delivery status"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_operator_notification_delivery_status_id
                      }
                    />
                    <Metric
                      label="Retry policy"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_operator_notification_retry_policy_id
                      }
                    />
                    <Metric
                      label="Dead letter"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_operator_notification_dead_letter_id
                      }
                    />
                    <Metric
                      label="Workspace card"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_workspace_delivery_card_id
                      }
                    />
                    <Metric
                      label="Delivery ledger"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_operator_delivery_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Private read URL"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_private_read_url_id
                      }
                    />
                    <Metric
                      label="Source lineage archive"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_source_lineage_archive_id
                      }
                    />
                    <Metric
                      label="Idempotency key"
                      value={
                        operatorNotificationDeliveryApplyPlanReceipt.planned_idempotency_key
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorNotificationDeliveryApplyPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorNotificationDeliveryApplyPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorNotificationDeliveryApplyPlanReceipt.required_operator_notification_delivery_apply_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator notification delivery apply blockers:{" "}
                    {operatorNotificationDeliveryApplyPlanReceipt.operator_notification_delivery_apply_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator notification delivery apply receipt fields:{" "}
                    {operatorNotificationDeliveryApplyPlanReceipt.required_operator_notification_delivery_apply_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator notification delivery result reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={onOperatorNotificationDeliveryResultReconciliationPlanGate}
                  disabled={
                    operatorNotificationDeliveryResultReconciliationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorNotificationDeliveryResultReconciliationPlanBusy
                    ? "Planning result reconciliation..."
                    : "Operator notification delivery result reconciliation plan"}
                </button>
              </div>

              {operatorNotificationDeliveryResultReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorNotificationDeliveryResultReconciliationPlanError}
                </p>
              )}

              {operatorNotificationDeliveryResultReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator notification delivery result reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {operatorNotificationDeliveryResultReconciliationPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorNotificationDeliveryResultReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Reconciliation"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_delivery_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Outcome record"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_delivery_outcome_record_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Reconciliation entry"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_delivery_reconciliation_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Retry decision"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_delivery_retry_decision_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Dead-letter entry"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_dead_letter_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery transaction"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_delivery_transaction_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery result"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_delivery_result_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery status"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_delivery_status_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Retry policy"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_retry_policy_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Operator notification"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Private URL"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.private_read_url_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Apply plan"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_delivery_apply_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Readiness plan"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_delivery_readiness_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Reconciliation receipt"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_delivery_result_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Delivery transaction"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_delivery_transaction_id
                      }
                    />
                    <Metric
                      label="Delivery attempt"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_delivery_attempt_id
                      }
                    />
                    <Metric
                      label="Delivery result"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_delivery_result_id
                      }
                    />
                    <Metric
                      label="Delivery status"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_delivery_status_id
                      }
                    />
                    <Metric
                      label="Outcome record"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_delivery_outcome_record_id
                      }
                    />
                    <Metric
                      label="Reconciliation entry"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_delivery_reconciliation_entry_id
                      }
                    />
                    <Metric
                      label="Retry decision"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_delivery_retry_decision_id
                      }
                    />
                    <Metric
                      label="Dead letter"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_dead_letter_id
                      }
                    />
                    <Metric
                      label="Dead-letter entry"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_dead_letter_entry_id
                      }
                    />
                    <Metric
                      label="Notification audit"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_notification_audit_entry_id
                      }
                    />
                    <Metric
                      label="Delivery ledger"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_operator_delivery_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Source lineage archive"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_source_lineage_archive_id
                      }
                    />
                    <Metric
                      label="Idempotency key"
                      value={
                        operatorNotificationDeliveryResultReconciliationPlanReceipt.planned_idempotency_key
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorNotificationDeliveryResultReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorNotificationDeliveryResultReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorNotificationDeliveryResultReconciliationPlanReceipt.required_operator_notification_delivery_result_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator notification delivery result reconciliation blockers:{" "}
                    {operatorNotificationDeliveryResultReconciliationPlanReceipt.operator_notification_delivery_result_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator notification delivery result reconciliation receipt fields:{" "}
                    {operatorNotificationDeliveryResultReconciliationPlanReceipt.required_operator_notification_delivery_result_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator delivery ledger reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={onOperatorDeliveryLedgerReconciliationPlanGate}
                  disabled={
                    operatorDeliveryLedgerReconciliationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorDeliveryLedgerReconciliationPlanBusy
                    ? "Planning ledger reconciliation..."
                    : "Operator delivery ledger reconciliation plan"}
                </button>
              </div>

              {operatorDeliveryLedgerReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorDeliveryLedgerReconciliationPlanError}
                </p>
              )}

              {operatorDeliveryLedgerReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator delivery ledger reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {operatorDeliveryLedgerReconciliationPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorDeliveryLedgerReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Ledger reconciliation"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.operator_delivery_ledger_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Ledger result"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.operator_delivery_ledger_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Ledger status"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.operator_delivery_ledger_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Ledger retry"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.operator_delivery_ledger_retry_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Ledger dead letter"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.operator_delivery_ledger_dead_letter_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Outcome record"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.operator_notification_delivery_outcome_record_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery ledger"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.operator_delivery_ledger_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Operator notification"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.operator_notification_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Result reconciliation plan"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.operator_notification_delivery_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Apply plan"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.operator_notification_delivery_apply_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Ledger reconciliation receipt"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_delivery_ledger_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Ledger entry"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_delivery_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Ledger result entry"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_delivery_ledger_result_entry_id
                      }
                    />
                    <Metric
                      label="Ledger status entry"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_delivery_ledger_status_entry_id
                      }
                    />
                    <Metric
                      label="Ledger retry entry"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_delivery_ledger_retry_entry_id
                      }
                    />
                    <Metric
                      label="Ledger dead-letter entry"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_delivery_ledger_dead_letter_entry_id
                      }
                    />
                    <Metric
                      label="Outcome record"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_notification_delivery_outcome_record_id
                      }
                    />
                    <Metric
                      label="Delivery reconciliation"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_notification_delivery_reconciliation_entry_id
                      }
                    />
                    <Metric
                      label="Retry decision"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_notification_delivery_retry_decision_id
                      }
                    />
                    <Metric
                      label="Dead-letter entry"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_notification_dead_letter_entry_id
                      }
                    />
                    <Metric
                      label="Delivery result"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_notification_delivery_result_id
                      }
                    />
                    <Metric
                      label="Delivery status"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_operator_notification_delivery_status_id
                      }
                    />
                    <Metric
                      label="Source lineage archive"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_source_lineage_archive_id
                      }
                    />
                    <Metric
                      label="Idempotency key"
                      value={
                        operatorDeliveryLedgerReconciliationPlanReceipt.planned_idempotency_key
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorDeliveryLedgerReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorDeliveryLedgerReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorDeliveryLedgerReconciliationPlanReceipt.required_operator_delivery_ledger_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator delivery ledger reconciliation blockers:{" "}
                    {operatorDeliveryLedgerReconciliationPlanReceipt.operator_delivery_ledger_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator delivery ledger reconciliation receipt fields:{" "}
                    {operatorDeliveryLedgerReconciliationPlanReceipt.required_operator_delivery_ledger_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Workspace delivery card reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={onWorkspaceDeliveryCardReconciliationPlanGate}
                  disabled={
                    workspaceDeliveryCardReconciliationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
                    !operatorDeliveryLedgerReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {workspaceDeliveryCardReconciliationPlanBusy
                    ? "Planning workspace card..."
                    : "Workspace delivery card reconciliation plan"}
                </button>
              </div>

              {workspaceDeliveryCardReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {workspaceDeliveryCardReconciliationPlanError}
                </p>
              )}

              {workspaceDeliveryCardReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Workspace delivery card reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {workspaceDeliveryCardReconciliationPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={workspaceDeliveryCardReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Card reconciliation"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.workspace_delivery_card_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Card result"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.workspace_delivery_card_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Card status"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.workspace_delivery_card_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Card notification"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.workspace_delivery_card_notification_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Workspace card"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.workspace_delivery_card_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Ledger result"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.operator_delivery_ledger_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Outcome record"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.operator_notification_delivery_outcome_record_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Operator notification"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.operator_notification_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Ledger reconciliation plan"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.operator_delivery_ledger_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Result reconciliation plan"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.operator_notification_delivery_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Card reconciliation receipt"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_workspace_delivery_card_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Workspace card"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_workspace_delivery_card_id
                      }
                    />
                    <Metric
                      label="Card result entry"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_workspace_delivery_card_result_entry_id
                      }
                    />
                    <Metric
                      label="Card status entry"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_workspace_delivery_card_status_entry_id
                      }
                    />
                    <Metric
                      label="Card notification entry"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_workspace_delivery_card_notification_entry_id
                      }
                    />
                    <Metric
                      label="Card replay guard"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_workspace_delivery_card_replay_guard_id
                      }
                    />
                    <Metric
                      label="Ledger result entry"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_operator_delivery_ledger_result_entry_id
                      }
                    />
                    <Metric
                      label="Ledger status entry"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_operator_delivery_ledger_status_entry_id
                      }
                    />
                    <Metric
                      label="Outcome record"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_operator_notification_delivery_outcome_record_id
                      }
                    />
                    <Metric
                      label="Delivery reconciliation"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_operator_notification_delivery_reconciliation_entry_id
                      }
                    />
                    <Metric
                      label="Delivery result"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_operator_notification_delivery_result_id
                      }
                    />
                    <Metric
                      label="Delivery status"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_operator_notification_delivery_status_id
                      }
                    />
                    <Metric
                      label="Private URL"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_private_read_url_id
                      }
                    />
                    <Metric
                      label="Reading workspace"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_reading_workspace_entry_id
                      }
                    />
                    <Metric
                      label="Source lineage archive"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_source_lineage_archive_id
                      }
                    />
                    <Metric
                      label="Idempotency key"
                      value={
                        workspaceDeliveryCardReconciliationPlanReceipt.planned_idempotency_key
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={workspaceDeliveryCardReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={workspaceDeliveryCardReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {workspaceDeliveryCardReconciliationPlanReceipt.required_workspace_delivery_card_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Workspace delivery card reconciliation blockers:{" "}
                    {workspaceDeliveryCardReconciliationPlanReceipt.workspace_delivery_card_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Workspace delivery card reconciliation receipt fields:{" "}
                    {workspaceDeliveryCardReconciliationPlanReceipt.required_workspace_delivery_card_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 border-t border-rule pt-3 dark:border-charcoal-1 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Delivery notification reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={onDeliveryNotificationReconciliationPlanGate}
                  disabled={
                    deliveryNotificationReconciliationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
                    !operatorDeliveryLedgerReconciliationPlanReceipt ||
                    !workspaceDeliveryCardReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {deliveryNotificationReconciliationPlanBusy
                    ? "Planning delivery notification..."
                    : "Delivery notification reconciliation plan"}
                </button>
              </div>

              {deliveryNotificationReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {deliveryNotificationReconciliationPlanError}
                </p>
              )}

              {deliveryNotificationReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Delivery notification reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {deliveryNotificationReconciliationPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={deliveryNotificationReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Notification reconciliation"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.delivery_notification_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Notification status"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.delivery_notification_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Notification result"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.delivery_notification_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Operator-visible event"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.delivery_notification_operator_visible_event_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Delivery notification"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.delivery_notification_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Workspace card"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.workspace_delivery_card_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Ledger entry"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.operator_delivery_ledger_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Operator notification"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.operator_notification_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Workspace card plan"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.workspace_delivery_card_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Ledger plan"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.operator_delivery_ledger_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Notification reconciliation receipt"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_delivery_notification_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Delivery notification"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_delivery_notification_id
                      }
                    />
                    <Metric
                      label="Notification status entry"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_delivery_notification_status_entry_id
                      }
                    />
                    <Metric
                      label="Notification result entry"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_delivery_notification_result_entry_id
                      }
                    />
                    <Metric
                      label="Operator-visible event"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_delivery_notification_operator_visible_event_id
                      }
                    />
                    <Metric
                      label="Notification replay guard"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_delivery_notification_replay_guard_id
                      }
                    />
                    <Metric
                      label="Workspace card"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_workspace_delivery_card_id
                      }
                    />
                    <Metric
                      label="Card status entry"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_workspace_delivery_card_status_entry_id
                      }
                    />
                    <Metric
                      label="Ledger status entry"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_operator_delivery_ledger_status_entry_id
                      }
                    />
                    <Metric
                      label="Delivery reconciliation"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_operator_notification_delivery_reconciliation_entry_id
                      }
                    />
                    <Metric
                      label="Private URL"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_private_read_url_id
                      }
                    />
                    <Metric
                      label="Source lineage archive"
                      value={
                        deliveryNotificationReconciliationPlanReceipt.planned_source_lineage_archive_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={deliveryNotificationReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={deliveryNotificationReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {deliveryNotificationReconciliationPlanReceipt.required_delivery_notification_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Delivery notification reconciliation blockers:{" "}
                    {deliveryNotificationReconciliationPlanReceipt.delivery_notification_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Delivery notification reconciliation receipt fields:{" "}
                    {deliveryNotificationReconciliationPlanReceipt.required_delivery_notification_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Retention billing reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={onRetentionBillingReconciliationPlanGate}
                  disabled={
                    retentionBillingReconciliationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
                    !operatorDeliveryLedgerReconciliationPlanReceipt ||
                    !workspaceDeliveryCardReconciliationPlanReceipt ||
                    !deliveryNotificationReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {retentionBillingReconciliationPlanBusy
                    ? "Planning retention billing..."
                    : "Retention billing reconciliation plan"}
                </button>
              </div>

              {retentionBillingReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {retentionBillingReconciliationPlanError}
                </p>
              )}

              {retentionBillingReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Retention billing reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {retentionBillingReconciliationPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={retentionBillingReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Retention billing"
                      value={
                        retentionBillingReconciliationPlanReceipt.retention_billing_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Run retention manifest"
                      value={
                        retentionBillingReconciliationPlanReceipt.run_retention_manifest_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Billing reconciliation"
                      value={
                        retentionBillingReconciliationPlanReceipt.billing_reconciliation_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Model usage rollup"
                      value={
                        retentionBillingReconciliationPlanReceipt.model_usage_rollup_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Source lineage archive"
                      value={
                        retentionBillingReconciliationPlanReceipt.source_lineage_archive_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Retention status"
                      value={
                        retentionBillingReconciliationPlanReceipt.run_retention_manifest_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Billing status"
                      value={
                        retentionBillingReconciliationPlanReceipt.billing_reconciliation_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Usage reconciliation"
                      value={
                        retentionBillingReconciliationPlanReceipt.model_usage_rollup_reconciliation_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Delivery notification plan"
                      value={
                        retentionBillingReconciliationPlanReceipt.delivery_notification_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Retention billing receipt"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_retention_billing_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Run retention manifest"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_run_retention_manifest_id
                      }
                    />
                    <Metric
                      label="Billing reconciliation"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_billing_reconciliation_id
                      }
                    />
                    <Metric
                      label="Model usage rollup"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_model_usage_rollup_id
                      }
                    />
                    <Metric
                      label="Source lineage archive"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_source_lineage_archive_id
                      }
                    />
                    <Metric
                      label="Retention status entry"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_run_retention_manifest_status_entry_id
                      }
                    />
                    <Metric
                      label="Billing status entry"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_billing_reconciliation_status_entry_id
                      }
                    />
                    <Metric
                      label="Usage reconciliation"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_model_usage_rollup_reconciliation_entry_id
                      }
                    />
                    <Metric
                      label="Lineage reconciliation"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_source_lineage_archive_reconciliation_entry_id
                      }
                    />
                    <Metric
                      label="Delivery notification"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_delivery_notification_id
                      }
                    />
                    <Metric
                      label="Workspace card"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_workspace_delivery_card_id
                      }
                    />
                    <Metric
                      label="Ledger entry"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_operator_delivery_ledger_entry_id
                      }
                    />
                    <Metric
                      label="Private URL"
                      value={
                        retentionBillingReconciliationPlanReceipt.planned_private_read_url_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={retentionBillingReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={retentionBillingReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {retentionBillingReconciliationPlanReceipt.required_retention_billing_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Retention billing reconciliation blockers:{" "}
                    {retentionBillingReconciliationPlanReceipt.retention_billing_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Retention billing reconciliation receipt fields:{" "}
                    {retentionBillingReconciliationPlanReceipt.required_retention_billing_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Final closeout archive reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={onFinalCloseoutArchiveReconciliationPlanGate}
                  disabled={
                    finalCloseoutArchiveReconciliationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
                    !operatorDeliveryLedgerReconciliationPlanReceipt ||
                    !workspaceDeliveryCardReconciliationPlanReceipt ||
                    !deliveryNotificationReconciliationPlanReceipt ||
                    !retentionBillingReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {finalCloseoutArchiveReconciliationPlanBusy
                    ? "Planning closeout archive..."
                    : "Final closeout archive reconciliation plan"}
                </button>
              </div>

              {finalCloseoutArchiveReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {finalCloseoutArchiveReconciliationPlanError}
                </p>
              )}

              {finalCloseoutArchiveReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Final closeout archive reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {finalCloseoutArchiveReconciliationPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={finalCloseoutArchiveReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Closeout archive"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.final_closeout_archive_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Closure receipt"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.final_run_closure_receipt_reconciled
                          ? "reconciled"
                          : "not reconciled"
                      }
                    />
                    <Metric
                      label="Closeout record"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.run_closeout_record_reconciled
                          ? "reconciled"
                          : "not reconciled"
                      }
                    />
                    <Metric
                      label="Archive manifest"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.artifact_archive_manifest_reconciled
                          ? "reconciled"
                          : "not reconciled"
                      }
                    />
                    <Metric
                      label="Operator handoff"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.operator_handoff_summary_reconciled
                          ? "reconciled"
                          : "not reconciled"
                      }
                    />
                    <Metric
                      label="Quality attestation"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.quality_attestation_reconciled
                          ? "reconciled"
                          : "not reconciled"
                      }
                    />
                    <Metric
                      label="Completion audit"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.completion_audit_entry_reconciled
                          ? "reconciled"
                          : "not reconciled"
                      }
                    />
                    <Metric
                      label="Retention billing"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.retention_billing_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Retention billing plan"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.retention_billing_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Closeout archive receipt"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_final_closeout_archive_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Final run closure receipt"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_final_run_closure_receipt_id
                      }
                    />
                    <Metric
                      label="Run closeout record"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_run_closeout_record_id
                      }
                    />
                    <Metric
                      label="Artifact archive manifest"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_artifact_archive_manifest_id
                      }
                    />
                    <Metric
                      label="Operator handoff summary"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_operator_handoff_summary_id
                      }
                    />
                    <Metric
                      label="Quality attestation"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_quality_attestation_id
                      }
                    />
                    <Metric
                      label="Completion audit"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_completion_audit_entry_id
                      }
                    />
                    <Metric
                      label="Retention billing receipt"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_retention_billing_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Source lineage reconciliation"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_source_lineage_archive_reconciliation_entry_id
                      }
                    />
                    <Metric
                      label="Private URL"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_private_read_url_id
                      }
                    />
                    <Metric
                      label="Hosted HTML asset"
                      value={
                        finalCloseoutArchiveReconciliationPlanReceipt.planned_hosted_html_asset_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={finalCloseoutArchiveReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={finalCloseoutArchiveReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {finalCloseoutArchiveReconciliationPlanReceipt.required_final_closeout_archive_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final closeout archive reconciliation blockers:{" "}
                    {finalCloseoutArchiveReconciliationPlanReceipt.final_closeout_archive_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Final closeout archive reconciliation receipt fields:{" "}
                    {finalCloseoutArchiveReconciliationPlanReceipt.required_final_closeout_archive_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive handoff package plan
                </p>
                <button
                  type="button"
                  onClick={onOperatorArchiveHandoffPackagePlanGate}
                  disabled={
                    operatorArchiveHandoffPackagePlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
                    !operatorDeliveryLedgerReconciliationPlanReceipt ||
                    !workspaceDeliveryCardReconciliationPlanReceipt ||
                    !deliveryNotificationReconciliationPlanReceipt ||
                    !retentionBillingReconciliationPlanReceipt ||
                    !finalCloseoutArchiveReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchiveHandoffPackagePlanBusy
                    ? "Planning archive package..."
                    : "Operator archive handoff package plan"}
                </button>
              </div>

              {operatorArchiveHandoffPackagePlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorArchiveHandoffPackagePlanError}
                </p>
              )}

              {operatorArchiveHandoffPackagePlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive handoff package receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {operatorArchiveHandoffPackagePlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchiveHandoffPackagePlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Package handoff"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.operator_archive_handoff_package_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Archive package"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.operator_archive_package_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Archive manifest"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.operator_archive_manifest_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Handoff bundle"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.operator_handoff_bundle_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Closeout archive"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.final_closeout_archive_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Closeout archive plan"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.final_closeout_archive_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Package receipt"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.planned_operator_archive_handoff_package_receipt_id
                      }
                    />
                    <Metric
                      label="Archive package"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.planned_operator_archive_package_id
                      }
                    />
                    <Metric
                      label="Archive manifest"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.planned_operator_archive_manifest_id
                      }
                    />
                    <Metric
                      label="Handoff bundle"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.planned_operator_handoff_bundle_id
                      }
                    />
                    <Metric
                      label="Artifact archive manifest"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.planned_artifact_archive_manifest_id
                      }
                    />
                    <Metric
                      label="Operator handoff summary"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.planned_operator_handoff_summary_id
                      }
                    />
                    <Metric
                      label="Closeout archive receipt"
                      value={
                        operatorArchiveHandoffPackagePlanReceipt.planned_final_closeout_archive_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchiveHandoffPackagePlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchiveHandoffPackagePlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchiveHandoffPackagePlanReceipt.required_operator_archive_handoff_package_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive handoff package blockers:{" "}
                    {operatorArchiveHandoffPackagePlanReceipt.operator_archive_handoff_package_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive handoff package receipt fields:{" "}
                    {operatorArchiveHandoffPackagePlanReceipt.required_operator_archive_handoff_package_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package result reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={onOperatorArchiveHandoffPackageResultReconciliationPlanGate}
                  disabled={
                    operatorArchiveHandoffPackageResultReconciliationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
                    !operatorDeliveryLedgerReconciliationPlanReceipt ||
                    !workspaceDeliveryCardReconciliationPlanReceipt ||
                    !deliveryNotificationReconciliationPlanReceipt ||
                    !retentionBillingReconciliationPlanReceipt ||
                    !finalCloseoutArchiveReconciliationPlanReceipt ||
                    !operatorArchiveHandoffPackagePlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchiveHandoffPackageResultReconciliationPlanBusy
                    ? "Planning package result..."
                    : "Operator archive package result reconciliation plan"}
                </button>
              </div>

              {operatorArchiveHandoffPackageResultReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorArchiveHandoffPackageResultReconciliationPlanError}
                </p>
              )}

              {operatorArchiveHandoffPackageResultReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package result reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {operatorArchiveHandoffPackageResultReconciliationPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchiveHandoffPackageResultReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Result reconciliation"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.operator_archive_handoff_package_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Package result"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.operator_archive_package_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Manifest status"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.operator_archive_manifest_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Bundle status"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.operator_handoff_bundle_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Package handoff"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.operator_archive_handoff_package_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Package plan"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.operator_archive_handoff_package_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Result reconciliation receipt"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.planned_operator_archive_handoff_package_result_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Package result entry"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.planned_operator_archive_package_result_entry_id
                      }
                    />
                    <Metric
                      label="Manifest status entry"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.planned_operator_archive_manifest_status_entry_id
                      }
                    />
                    <Metric
                      label="Bundle status entry"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.planned_operator_handoff_bundle_status_entry_id
                      }
                    />
                    <Metric
                      label="Archive package"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.planned_operator_archive_package_id
                      }
                    />
                    <Metric
                      label="Archive manifest"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.planned_operator_archive_manifest_id
                      }
                    />
                    <Metric
                      label="Handoff bundle"
                      value={
                        operatorArchiveHandoffPackageResultReconciliationPlanReceipt.planned_operator_handoff_bundle_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchiveHandoffPackageResultReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchiveHandoffPackageResultReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchiveHandoffPackageResultReconciliationPlanReceipt.required_operator_archive_handoff_package_result_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package result reconciliation blockers:{" "}
                    {operatorArchiveHandoffPackageResultReconciliationPlanReceipt.operator_archive_handoff_package_result_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package result reconciliation receipt fields:{" "}
                    {operatorArchiveHandoffPackageResultReconciliationPlanReceipt.required_operator_archive_handoff_package_result_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery audit plan
                </p>
                <button
                  type="button"
                  onClick={onOperatorArchiveHandoffPackageDeliveryAuditPlanGate}
                  disabled={
                    operatorArchiveHandoffPackageDeliveryAuditPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
                    !operatorDeliveryLedgerReconciliationPlanReceipt ||
                    !workspaceDeliveryCardReconciliationPlanReceipt ||
                    !deliveryNotificationReconciliationPlanReceipt ||
                    !retentionBillingReconciliationPlanReceipt ||
                    !finalCloseoutArchiveReconciliationPlanReceipt ||
                    !operatorArchiveHandoffPackagePlanReceipt ||
                    !operatorArchiveHandoffPackageResultReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchiveHandoffPackageDeliveryAuditPlanBusy
                    ? "Planning delivery audit..."
                    : "Operator archive package delivery audit plan"}
                </button>
              </div>

              {operatorArchiveHandoffPackageDeliveryAuditPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorArchiveHandoffPackageDeliveryAuditPlanError}
                </p>
              )}

              {operatorArchiveHandoffPackageDeliveryAuditPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery audit receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Delivery audit"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.operator_archive_handoff_package_delivery_audit_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Package audit entry"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.operator_archive_package_delivery_audit_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Manifest audit entry"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.operator_archive_manifest_delivery_audit_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Bundle audit entry"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.operator_handoff_bundle_delivery_audit_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Evidence bundle"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.operator_archive_delivery_audit_evidence_bundle_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Result reconciliation plan"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.operator_archive_handoff_package_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Delivery audit receipt"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.planned_operator_archive_handoff_package_delivery_audit_receipt_id
                      }
                    />
                    <Metric
                      label="Package delivery audit entry"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.planned_operator_archive_package_delivery_audit_entry_id
                      }
                    />
                    <Metric
                      label="Manifest delivery audit entry"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.planned_operator_archive_manifest_delivery_audit_entry_id
                      }
                    />
                    <Metric
                      label="Bundle delivery audit entry"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.planned_operator_handoff_bundle_delivery_audit_entry_id
                      }
                    />
                    <Metric
                      label="Audit evidence bundle"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.planned_operator_archive_delivery_audit_evidence_bundle_id
                      }
                    />
                    <Metric
                      label="Package result entry"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.planned_operator_archive_package_result_entry_id
                      }
                    />
                    <Metric
                      label="Manifest status entry"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.planned_operator_archive_manifest_status_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.required_operator_archive_handoff_package_delivery_audit_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery audit blockers:{" "}
                    {operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.operator_archive_handoff_package_delivery_audit_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery audit receipt fields:{" "}
                    {operatorArchiveHandoffPackageDeliveryAuditPlanReceipt.required_operator_archive_handoff_package_delivery_audit_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery audit result reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanGate
                  }
                  disabled={
                    operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
                    !operatorDeliveryLedgerReconciliationPlanReceipt ||
                    !workspaceDeliveryCardReconciliationPlanReceipt ||
                    !deliveryNotificationReconciliationPlanReceipt ||
                    !retentionBillingReconciliationPlanReceipt ||
                    !finalCloseoutArchiveReconciliationPlanReceipt ||
                    !operatorArchiveHandoffPackagePlanReceipt ||
                    !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
                    !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanBusy
                    ? "Planning audit result..."
                    : "Operator archive package delivery audit result reconciliation plan"}
                </button>
              </div>

              {operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {
                    operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanError
                  }
                </p>
              )}

              {operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery audit result reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Audit result"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.operator_archive_handoff_package_delivery_audit_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Package result"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.operator_archive_package_delivery_audit_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Manifest status"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.operator_archive_manifest_delivery_audit_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Bundle status"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.operator_handoff_bundle_delivery_audit_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Evidence status"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.operator_archive_delivery_audit_evidence_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Delivery audit plan"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.operator_archive_handoff_package_delivery_audit_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Audit result receipt"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.planned_operator_archive_handoff_package_delivery_audit_result_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Package audit result"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_audit_result_entry_id
                      }
                    />
                    <Metric
                      label="Manifest audit status"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.planned_operator_archive_manifest_delivery_audit_status_entry_id
                      }
                    />
                    <Metric
                      label="Bundle audit status"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.planned_operator_handoff_bundle_delivery_audit_status_entry_id
                      }
                    />
                    <Metric
                      label="Evidence audit status"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.planned_operator_archive_delivery_audit_evidence_status_entry_id
                      }
                    />
                    <Metric
                      label="Delivery audit receipt"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.planned_operator_archive_handoff_package_delivery_audit_receipt_id
                      }
                    />
                    <Metric
                      label="Evidence bundle"
                      value={
                        operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.planned_operator_archive_delivery_audit_evidence_bundle_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.required_operator_archive_handoff_package_delivery_audit_result_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery audit result reconciliation blockers:{" "}
                    {operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.operator_archive_handoff_package_delivery_audit_result_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery audit result reconciliation receipt
                    fields:{" "}
                    {operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt.required_operator_archive_handoff_package_delivery_audit_result_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report plan
                </p>
                <button
                  type="button"
                  onClick={onOperatorArchivePackageDeliveryReportPlanGate}
                  disabled={
                    operatorArchivePackageDeliveryReportPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
                    !operatorDeliveryLedgerReconciliationPlanReceipt ||
                    !workspaceDeliveryCardReconciliationPlanReceipt ||
                    !deliveryNotificationReconciliationPlanReceipt ||
                    !retentionBillingReconciliationPlanReceipt ||
                    !finalCloseoutArchiveReconciliationPlanReceipt ||
                    !operatorArchiveHandoffPackagePlanReceipt ||
                    !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
                    !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
                    !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportPlanBusy
                    ? "Planning report..."
                    : "Operator archive package delivery report plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorArchivePackageDeliveryReportPlanError}
                </p>
              )}

              {operatorArchivePackageDeliveryReportPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {operatorArchivePackageDeliveryReportPlanReceipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Report"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.operator_archive_package_delivery_report_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Package report"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.operator_archive_package_delivery_report_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Manifest report"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.operator_archive_manifest_delivery_report_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Bundle report"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.operator_handoff_bundle_delivery_report_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Evidence bundle"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.operator_archive_delivery_report_evidence_bundle_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Audit result plan"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.operator_archive_handoff_package_delivery_audit_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Delivery report receipt"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.planned_operator_archive_package_delivery_report_receipt_id
                      }
                    />
                    <Metric
                      label="Package report entry"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.planned_operator_archive_package_delivery_report_entry_id
                      }
                    />
                    <Metric
                      label="Manifest report entry"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.planned_operator_archive_manifest_delivery_report_entry_id
                      }
                    />
                    <Metric
                      label="Bundle report entry"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.planned_operator_handoff_bundle_delivery_report_entry_id
                      }
                    />
                    <Metric
                      label="Report evidence"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.planned_operator_archive_delivery_report_evidence_bundle_id
                      }
                    />
                    <Metric
                      label="Audit result receipt"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.planned_operator_archive_handoff_package_delivery_audit_result_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Package audit result"
                      value={
                        operatorArchivePackageDeliveryReportPlanReceipt.planned_operator_archive_package_delivery_audit_result_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportPlanReceipt.required_operator_archive_package_delivery_report_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report blockers:{" "}
                    {operatorArchivePackageDeliveryReportPlanReceipt.operator_archive_package_delivery_report_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report receipt fields:{" "}
                    {operatorArchivePackageDeliveryReportPlanReceipt.required_operator_archive_package_delivery_report_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report result reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchivePackageDeliveryReportResultReconciliationPlanGate
                  }
                  disabled={
                    operatorArchivePackageDeliveryReportResultReconciliationPlanBusy ||
                    !preflight.launch_packet ||
                    !preflight.approval_receipt ||
                    !preflight.runner_handoff ||
                    !runnerControlPlanReceipt ||
                    !budgetProviderAdapterPlanReceipt ||
                    !providerExecutorAdapterPlanReceipt ||
                    !retrievalAdapterPlanReceipt ||
                    !graphAdapterPlanReceipt ||
                    !finalArtifactAdapterPlanReceipt ||
                    !operatorDispatchAdapterPlanReceipt ||
                    !controlLedgerAdapterPlanReceipt ||
                    !controlLedgerPersistencePlanReceipt ||
                    !controlLedgerPersistenceApplyPlanReceipt ||
                    !operatorDispatchActivationReadinessPlanReceipt ||
                    !liveDispatchFinalEnablementPlanReceipt ||
                    !liveDispatchFinalEnablementApplyPlanReceipt ||
                    !runnerDispatchSchedulerPlanReceipt ||
                    !runnerDispatchWorkerBootstrapPlanReceipt ||
                    !schedulerLeaseRetryPlanReceipt ||
                    !workerQueueClaimPlanReceipt ||
                    !repositoryTransactionPlanReceipt ||
                    !repositoryCommitRollbackPlanReceipt ||
                    !workerDispatchLeaseHeartbeatPlanReceipt ||
                    !workerCancellationAbandonPlanReceipt ||
                    !workerCompletionFinalizationPlanReceipt ||
                    !workerOutputAggregationPlanReceipt ||
                    !workerSynthesisHandoffPlanReceipt ||
                    !synthesisBundleAssemblyPlanReceipt ||
                    !finalSynthesisDraftPlanReceipt ||
                    !finalHtmlArtifactAssemblyPlanReceipt ||
                    !finalArtifactPersistencePlanReceipt ||
                    !finalArtifactGraphCommitPlanReceipt ||
                    !finalArtifactPublishPlanReceipt ||
                    !finalArtifactCompletionFinalizationPlanReceipt ||
                    !finalRunClosurePlanReceipt ||
                    !operatorNotificationDeliveryReadinessPlanReceipt ||
                    !operatorNotificationDeliveryApplyPlanReceipt ||
                    !operatorNotificationDeliveryResultReconciliationPlanReceipt ||
                    !operatorDeliveryLedgerReconciliationPlanReceipt ||
                    !workspaceDeliveryCardReconciliationPlanReceipt ||
                    !deliveryNotificationReconciliationPlanReceipt ||
                    !retentionBillingReconciliationPlanReceipt ||
                    !finalCloseoutArchiveReconciliationPlanReceipt ||
                    !operatorArchiveHandoffPackagePlanReceipt ||
                    !operatorArchiveHandoffPackageResultReconciliationPlanReceipt ||
                    !operatorArchiveHandoffPackageDeliveryAuditPlanReceipt ||
                    !operatorArchiveHandoffPackageDeliveryAuditResultReconciliationPlanReceipt ||
                    !operatorArchivePackageDeliveryReportPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportResultReconciliationPlanBusy
                    ? "Planning report result..."
                    : "Operator archive package delivery report result reconciliation plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportResultReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {
                    operatorArchivePackageDeliveryReportResultReconciliationPlanError
                  }
                </p>
              )}

              {operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report result reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Report result"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.operator_archive_package_delivery_report_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Package result"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.operator_archive_package_delivery_report_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Manifest status"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.operator_archive_manifest_delivery_report_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Bundle status"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.operator_handoff_bundle_delivery_report_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Evidence status"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.operator_archive_delivery_report_evidence_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Report plan"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.operator_archive_package_delivery_report_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Result receipt"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_result_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Package result entry"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_result_entry_id
                      }
                    />
                    <Metric
                      label="Manifest status entry"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.planned_operator_archive_manifest_delivery_report_status_entry_id
                      }
                    />
                    <Metric
                      label="Bundle status entry"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.planned_operator_handoff_bundle_delivery_report_status_entry_id
                      }
                    />
                    <Metric
                      label="Evidence status entry"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.planned_operator_archive_delivery_report_evidence_status_entry_id
                      }
                    />
                    <Metric
                      label="Report receipt"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_receipt_id
                      }
                    />
                    <Metric
                      label="Report entry"
                      value={
                        operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.required_operator_archive_package_delivery_report_result_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report result reconciliation
                    blockers:{" "}
                    {operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.operator_archive_package_delivery_report_result_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report result reconciliation receipt
                    fields:{" "}
                    {operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt.required_operator_archive_package_delivery_report_result_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report notification readiness plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchivePackageDeliveryReportNotificationReadinessPlanGate
                  }
                  disabled={
                    operatorArchivePackageDeliveryReportNotificationReadinessPlanBusy ||
                    !operatorArchivePackageDeliveryReportResultReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportNotificationReadinessPlanBusy
                    ? "Planning notification readiness..."
                    : "Operator archive package delivery report notification readiness plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportNotificationReadinessPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {
                    operatorArchivePackageDeliveryReportNotificationReadinessPlanError
                  }
                </p>
              )}

              {operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report notification readiness
                      receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Readiness"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.operator_archive_package_delivery_report_notification_readiness_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Payload"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.operator_archive_package_delivery_report_notification_payload_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Channel policy"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.operator_archive_package_delivery_report_notification_channel_policy_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Notification audit"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.operator_archive_package_delivery_report_notification_audit_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Report result"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.operator_archive_package_delivery_report_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Result plan"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.operator_archive_package_delivery_report_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Report plan"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.operator_archive_package_delivery_report_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Readiness receipt"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.planned_operator_archive_package_delivery_report_notification_readiness_receipt_id
                      }
                    />
                    <Metric
                      label="Payload id"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.planned_operator_archive_package_delivery_report_notification_payload_id
                      }
                    />
                    <Metric
                      label="Channel policy id"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.planned_operator_archive_package_delivery_report_notification_channel_policy_id
                      }
                    />
                    <Metric
                      label="Audit id"
                      value={
                        operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.planned_operator_archive_package_delivery_report_notification_audit_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.required_operator_archive_package_delivery_report_notification_readiness_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report notification readiness
                    blockers:{" "}
                    {operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.operator_archive_package_delivery_report_notification_readiness_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report notification readiness
                    receipt fields:{" "}
                    {operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt.required_operator_archive_package_delivery_report_notification_readiness_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report notification result
                  reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchivePackageDeliveryReportNotificationResultReconciliationPlanGate
                  }
                  disabled={
                    operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanBusy ||
                    !operatorArchivePackageDeliveryReportNotificationReadinessPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanBusy
                    ? "Planning notification result..."
                    : "Operator archive package delivery report notification result reconciliation plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {
                    operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanError
                  }
                </p>
              )}

              {operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report notification result
                      reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Result reconciliation"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_notification_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Result entry"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_notification_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Status entry"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_notification_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Audit status"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_notification_audit_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Readiness"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_notification_readiness_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Readiness plan"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_notification_readiness_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Result plan"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Result receipt"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_notification_result_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Result entry id"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_notification_result_entry_id
                      }
                    />
                    <Metric
                      label="Status entry id"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_notification_status_entry_id
                      }
                    />
                    <Metric
                      label="Audit status id"
                      value={
                        operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_notification_audit_status_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.required_operator_archive_package_delivery_report_notification_result_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report notification result
                    reconciliation blockers:{" "}
                    {operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_notification_result_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report notification result
                    reconciliation receipt fields:{" "}
                    {operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt.required_operator_archive_package_delivery_report_notification_result_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report delivery confirmation
                  plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchivePackageDeliveryReportDeliveryConfirmationPlanGate
                  }
                  disabled={
                    operatorArchivePackageDeliveryReportDeliveryConfirmationPlanBusy ||
                    !operatorArchivePackageDeliveryReportNotificationResultReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportDeliveryConfirmationPlanBusy
                    ? "Planning confirmation..."
                    : "Operator archive package delivery report delivery confirmation plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportDeliveryConfirmationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorArchivePackageDeliveryReportDeliveryConfirmationPlanError}
                </p>
              )}

              {operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report delivery
                      confirmation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Confirmation"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Confirmation entry"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Status entry"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Audit entry"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_audit_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Notification result"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.operator_archive_package_delivery_report_notification_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Notification result plan"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Readiness plan"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.operator_archive_package_delivery_report_notification_readiness_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Confirmation receipt"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.planned_operator_archive_package_delivery_report_delivery_confirmation_receipt_id
                      }
                    />
                    <Metric
                      label="Confirmation entry id"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.planned_operator_archive_package_delivery_report_delivery_confirmation_entry_id
                      }
                    />
                    <Metric
                      label="Status entry id"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.planned_operator_archive_package_delivery_report_delivery_confirmation_status_entry_id
                      }
                    />
                    <Metric
                      label="Audit entry id"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.planned_operator_archive_package_delivery_report_delivery_confirmation_audit_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.required_operator_archive_package_delivery_report_delivery_confirmation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report delivery confirmation
                    blockers:{" "}
                    {operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report delivery confirmation
                    receipt fields:{" "}
                    {operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt.required_operator_archive_package_delivery_report_delivery_confirmation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report delivery confirmation
                  result reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanGate
                  }
                  disabled={
                    operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanBusy ||
                    !operatorArchivePackageDeliveryReportDeliveryConfirmationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanBusy
                    ? "Planning confirmation result..."
                    : "Operator archive package delivery report delivery confirmation result reconciliation plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {
                    operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanError
                  }
                </p>
              )}

              {operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report delivery
                      confirmation result reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Result reconciliation"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Result entry"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Status result"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_status_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Audit result"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_audit_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Confirmation"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Confirmation plan"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Notification result plan"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_notification_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Result receipt"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Result entry id"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_delivery_confirmation_result_entry_id
                      }
                    />
                    <Metric
                      label="Status result id"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_delivery_confirmation_status_result_entry_id
                      }
                    />
                    <Metric
                      label="Audit result id"
                      value={
                        operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_delivery_confirmation_audit_result_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.required_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report delivery confirmation
                    result reconciliation blockers:{" "}
                    {operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report delivery confirmation
                    result reconciliation receipt fields:{" "}
                    {operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt.required_operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report final operator
                  acknowledgement plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanGate
                  }
                  disabled={
                    operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanBusy ||
                    !operatorArchivePackageDeliveryReportDeliveryConfirmationResultReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanBusy
                    ? "Planning acknowledgement..."
                    : "Operator archive package delivery report final operator acknowledgement plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanError}
                </p>
              )}

              {operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report final operator
                      acknowledgement receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Acknowledgement"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_operator_acknowledgement_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Acknowledgement entry"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_operator_acknowledgement_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Status entry"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_operator_acknowledgement_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Audit entry"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_operator_acknowledgement_audit_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Confirmation result"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Confirmation result plan"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Confirmation plan"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Acknowledgement receipt"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_acknowledgement_receipt_id
                      }
                    />
                    <Metric
                      label="Acknowledgement entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_acknowledgement_entry_id
                      }
                    />
                    <Metric
                      label="Status entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_acknowledgement_status_entry_id
                      }
                    />
                    <Metric
                      label="Audit entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_acknowledgement_audit_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.required_operator_archive_package_delivery_report_final_operator_acknowledgement_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report final operator
                    acknowledgement blockers:{" "}
                    {operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_operator_acknowledgement_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report final operator
                    acknowledgement receipt fields:{" "}
                    {operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt.required_operator_archive_package_delivery_report_final_operator_acknowledgement_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report acknowledgement result
                  reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanGate
                  }
                  disabled={
                    operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanBusy ||
                    !operatorArchivePackageDeliveryReportFinalOperatorAcknowledgementPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanBusy
                    ? "Planning result reconciliation..."
                    : "Operator archive package delivery report acknowledgement result reconciliation plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {
                    operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanError
                  }
                </p>
              )}

              {operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report acknowledgement
                      result reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Result reconciliation"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.operator_archive_package_delivery_report_acknowledgement_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Result entry"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.operator_archive_package_delivery_report_acknowledgement_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Status result"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.operator_archive_package_delivery_report_acknowledgement_status_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Audit result"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.operator_archive_package_delivery_report_acknowledgement_audit_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Final acknowledgement"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.operator_archive_package_delivery_report_final_operator_acknowledgement_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Acknowledgement plan"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Confirmation result plan"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.operator_archive_package_delivery_report_delivery_confirmation_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Result receipt"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Result entry id"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_acknowledgement_result_entry_id
                      }
                    />
                    <Metric
                      label="Status result id"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_acknowledgement_status_result_entry_id
                      }
                    />
                    <Metric
                      label="Audit result id"
                      value={
                        operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_acknowledgement_audit_result_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.required_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report acknowledgement result
                    reconciliation blockers:{" "}
                    {operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.operator_archive_package_delivery_report_acknowledgement_result_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report acknowledgement result
                    reconciliation receipt fields:{" "}
                    {operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt.required_operator_archive_package_delivery_report_acknowledgement_result_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report final closeout
                  acknowledgement plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanGate
                  }
                  disabled={
                    operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanBusy ||
                    !operatorArchivePackageDeliveryReportAcknowledgementResultReconciliationPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanBusy
                    ? "Planning final closeout..."
                    : "Operator archive package delivery report final closeout acknowledgement plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {
                    operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanError
                  }
                </p>
              )}

              {operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report final closeout
                      acknowledgement receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Final closeout"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_closeout_acknowledgement_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Closeout entry"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_closeout_acknowledgement_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Status entry"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_closeout_acknowledgement_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Audit entry"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_closeout_acknowledgement_audit_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Acknowledgement result"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.operator_archive_package_delivery_report_acknowledgement_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Acknowledgement result plan"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Final acknowledgement plan"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_operator_acknowledgement_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Closeout receipt"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_receipt_id
                      }
                    />
                    <Metric
                      label="Closeout entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_entry_id
                      }
                    />
                    <Metric
                      label="Status entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_status_entry_id
                      }
                    />
                    <Metric
                      label="Audit entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.planned_operator_archive_package_delivery_report_final_closeout_acknowledgement_audit_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.required_operator_archive_package_delivery_report_final_closeout_acknowledgement_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report final closeout
                    acknowledgement blockers:{" "}
                    {operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.operator_archive_package_delivery_report_final_closeout_acknowledgement_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report final closeout
                    acknowledgement receipt fields:{" "}
                    {operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt.required_operator_archive_package_delivery_report_final_closeout_acknowledgement_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report final operator delivery
                  closeout plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanGate
                  }
                  disabled={
                    operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanBusy ||
                    !operatorArchivePackageDeliveryReportFinalCloseoutAcknowledgementPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanBusy
                    ? "Planning delivery closeout..."
                    : "Operator archive package delivery report final operator delivery closeout plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {
                    operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanError
                  }
                </p>
              )}

              {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report final operator
                      delivery closeout receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Final delivery closeout"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Closeout entry"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Status entry"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_status_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Audit entry"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Final closeout acknowledgement"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.operator_archive_package_delivery_report_final_closeout_acknowledgement_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Final closeout acknowledgement plan"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.operator_archive_package_delivery_report_final_closeout_acknowledgement_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Acknowledgement result plan"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.operator_archive_package_delivery_report_acknowledgement_result_reconciliation_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Delivery closeout receipt"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_receipt_id
                      }
                    />
                    <Metric
                      label="Delivery closeout entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_entry_id
                      }
                    />
                    <Metric
                      label="Status entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_status_entry_id
                      }
                    />
                    <Metric
                      label="Audit entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.required_operator_archive_package_delivery_report_final_operator_delivery_closeout_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report final operator
                    delivery closeout blockers:{" "}
                    {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report final operator
                    delivery closeout receipt fields:{" "}
                    {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt.required_operator_archive_package_delivery_report_final_operator_delivery_closeout_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Operator archive package delivery report final operator delivery
                  closeout result reconciliation plan
                </p>
                <button
                  type="button"
                  onClick={
                    onOperatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanGate
                  }
                  disabled={
                    operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanBusy ||
                    !operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutPlanReceipt
                  }
                  className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
                >
                  {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanBusy
                    ? "Planning closeout result..."
                    : "Operator archive package delivery report final operator delivery closeout result reconciliation plan"}
                </button>
              </div>

              {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanError && (
                <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
                  {
                    operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanError
                  }
                </p>
              )}

              {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Operator archive package delivery report final operator
                      delivery closeout result reconciliation receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.receipt_id
                      }
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.status.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Delivery closeout result"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                    <Metric
                      label="Result entry"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Status result"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_status_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Audit result"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_result_entry_created
                          ? "created"
                          : "not created"
                      }
                    />
                    <Metric
                      label="Final delivery closeout"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_allowed
                          ? "allowed"
                          : "blocked"
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Delivery closeout plan"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Final closeout acknowledgement plan"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.operator_archive_package_delivery_report_final_closeout_acknowledgement_plan_receipt_id
                      }
                    />
                    <Metric
                      label="Result reconciliation receipt"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_receipt_id
                      }
                    />
                    <Metric
                      label="Result entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_entry_id
                      }
                    />
                    <Metric
                      label="Status result entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_status_result_entry_id
                      }
                    />
                    <Metric
                      label="Audit result entry id"
                      value={
                        operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.planned_operator_archive_package_delivery_report_final_operator_delivery_closeout_audit_result_entry_id
                      }
                    />
                    <Metric
                      label="Adapter"
                      value={operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.adapter_key.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                    <Metric
                      label="Blocker"
                      value={operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.blocker_reason.replaceAll(
                        "_",
                        " ",
                      )}
                    />
                  </div>
                  <ul className="mt-2 grid grid-cols-1 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                    {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.required_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_invariants
                      .slice(0, 5)
                      .map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                  </ul>
                  <p className="mt-2 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report final operator
                    delivery closeout result reconciliation blockers:{" "}
                    {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_blockers.join(
                      ", ",
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-soft dark:text-starlight">
                    Operator archive package delivery report final operator
                    delivery closeout result reconciliation receipt fields:{" "}
                    {operatorArchivePackageDeliveryReportFinalOperatorDeliveryCloseoutResultReconciliationPlanReceipt.required_operator_archive_package_delivery_report_final_operator_delivery_closeout_result_reconciliation_receipt_fields.join(
                      ", ",
                    )}
                  </p>
                </div>
              )}

              {preflight.notes.map((note) => (
                <p key={note} className="text-[11px] text-ink-soft dark:text-starlight">
                  {note}
                </p>
              ))}
            </div>
          </LemonCard>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
        {label}
      </p>
      <p className="mt-1 text-ink dark:text-bright">{value}</p>
    </div>
  );
}
