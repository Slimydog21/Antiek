import { useState } from "react";

import {
  activationChecklistMidnightOil,
  budgetProviderAdapterPlanMidnightOil,
  budgetReservationMidnightOil,
  controlLedgerAdapterPlanMidnightOil,
  dispatchMidnightOil,
  dryRunMidnightOil,
  finalArtifactAdapterPlanMidnightOil,
  finalArtifactMidnightOil,
  graphAdapterPlanMidnightOil,
  graphMutationMidnightOil,
  liveRunActivationSettingsMidnightOil,
  operatorDispatchAdapterPlanMidnightOil,
  preflightMidnightOil,
  providerExecutorAdapterPlanMidnightOil,
  providerRouteMidnightOil,
  retrievalAdapterPlanMidnightOil,
  retrievalMidnightOil,
  runnerControlPlanMidnightOil,
  runnerReadinessMidnightOil,
  type MidnightOilActivationChecklistReceipt,
  type MidnightOilAppliedRunReceipt,
  type MidnightOilBudgetProviderAdapterPlanReceipt,
  type MidnightOilBudgetReservationReceipt,
  type MidnightOilControlLedgerAdapterPlanReceipt,
  type MidnightOilDispatchReceipt,
  type MidnightOilFinalArtifactAdapterPlanReceipt,
  type MidnightOilFinalArtifactReceipt,
  type MidnightOilGraphAdapterPlanReceipt,
  type MidnightOilGraphMutationReceipt,
  type MidnightOilLiveRunActivationSettingsReceipt,
  type MidnightOilOperatorDispatchAdapterPlanReceipt,
  type MidnightOilPreflight,
  type MidnightOilProviderExecutorAdapterPlanReceipt,
  type MidnightOilProviderRouteReceipt,
  type MidnightOilRetrievalAdapterPlanReceipt,
  type MidnightOilRetrievalReceipt,
  type MidnightOilRunnerControlPlanReceipt,
  type MidnightOilRunnerReadinessReceipt,
  type MidnightOilRouteMode,
  type MidnightOilSourcePolicy,
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

  function clearControlLedgerAdapterPlan() {
    setControlLedgerAdapterPlanError(null);
    setControlLedgerAdapterPlanReceipt(null);
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
