import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  approveMultimediaDryRun,
  authorizeMultimediaNarration,
  createGroundedMultimediaDraft,
  createMultimediaDraft,
  failedGateIds,
  getMultimediaAsset,
  getMultimediaLocalAudiblePlayback,
  getMultimediaPlayback,
  getMultimediaReviewedVisualSet,
  listMultimediaAssets,
  manualGateIds,
  previewMultimediaSteering,
  runMultimediaHardening,
  searchMultimediaEvidence,
  registerMultimediaProduction,
  produceAuthorizedMultimedia,
  steerMultimediaAsset,
} from "../../api/multimedia";
import type {
  CreateMultimediaDraftRequest,
  MultimediaAssetRecord,
  MultimediaAssetSummary,
  MultimediaDepth,
  MultimediaEvidenceSearchResult,
  MultimediaLocalAudiblePlayback,
  MultimediaPlayback as MultimediaPlaybackRecord,
  MultimediaNarrationAuthorization,
  MultimediaReviewedVisualSet,
  MultimediaSteeringPreview,
  MultimediaSteeringRequest,
} from "../../api/multimedia";
import { LemonButton, LemonInput, LemonTag, LemonTextarea } from "../../components/lemon";
import { ReconciliationPanel } from "./ReconciliationPanel";
import { KnowledgePanel, retainCurrentMultimediaSelection } from "./KnowledgePanel";
import { LocalProductionPanel } from "./LocalProductionPanel";
import { LocalAudiblePanel } from "./LocalAudiblePanel";
import { VisualReviewPanel } from "./VisualReviewPanel";
import { VoiceSteeringInput } from "./VoiceSteeringInput";
import { projectMultimediaPlan } from "./planProjection";

type Mode = "video" | "audio" | "hybrid";
type RouteTier = "cheapest" | "balanced" | "highest_quality";
type RenderState = "pending" | "rendering" | "partial" | "failed" | "over_budget" | "provider_unavailable";
type PlayerView = "video" | "audio";
type PendingCommand = "list" | "create" | "evidence-search" | "ground" | "approve" | "steer-preview" | "steer" | "harden" | "open" | null;
type VerifiedPlaybackRecord = MultimediaPlaybackRecord | MultimediaLocalAudiblePlayback;
type SteeringPreviewState = {
  preview: MultimediaSteeringPreview;
  request: MultimediaSteeringRequest;
};

type Chapter = {
  id: string;
  title: string;
  minutes: number;
  purpose: string;
  visualLabel: "planned" | "sourced" | "diagram";
  sourceId: string | null;
  transcript: string;
};

const TIER_COPY: Record<RouteTier, { label: string; multiplier: number; tradeoff: string }> = {
  cheapest: {
    label: "Cheapest",
    multiplier: 0.55,
    tradeoff: "Fully local narration and source-card documentary. No Krea or paid-provider fallback.",
  },
  balanced: {
    label: "Balanced",
    multiplier: 1,
    tradeoff: "Krea standard for hero visuals, cached diagrams everywhere else.",
  },
  highest_quality: {
    label: "Highest quality",
    multiplier: 2.4,
    tradeoff: "Krea premium imagery and video passes wherever quality moves the lesson.",
  },
};

const CHAPTERS: Chapter[] = [
  {
    id: "ch-1",
    title: "Why wide-body jets changed route economics",
    minutes: 7,
    purpose: "Frame the business reason aircraft size mattered before the technical story.",
    visualLabel: "sourced",
    sourceId: "src-747-economics",
    transcript:
      "The first act explains how capacity, range, and airport slots turned the wide-body into an economic machine rather than only a larger airplane.",
  },
  {
    id: "ch-2",
    title: "The engineering constraint stack",
    minutes: 9,
    purpose: "Turn wing loading, engine reliability, and pressurization into a causal chain.",
    visualLabel: "diagram",
    sourceId: "src-engine-stack",
    transcript:
      "This section slows down around engines, wing structure, and fatigue testing so the viewer sees why each design choice made the next one possible.",
  },
  {
    id: "ch-3",
    title: "The market after the breakthrough",
    minutes: 6,
    purpose: "Connect the technical breakthrough back to ticket prices and global travel.",
    visualLabel: "planned",
    sourceId: "src-market-shift",
    transcript:
      "The close compares the route map before and after wide-body adoption, labeling generated visuals separately from sourced charts.",
  },
];

const SOURCES = [
  {
    id: "src-747-economics",
    title: "Civil aviation economics notes",
    status: "verified",
    detail: "Covers load factor, airline route planning, and aircraft utilization.",
  },
  {
    id: "src-engine-stack",
    title: "Engine reliability and certification digest",
    status: "verified",
    detail: "Supports the engine and fatigue-testing sequence.",
  },
  {
    id: "src-market-shift",
    title: "Route map comparison",
    status: "needs review",
    detail: "Good chart candidate; narration should not overclaim causality.",
  },
];

const SUGGESTIONS = [
  "Compare the 747, A380, and 787 as different answers to route economics.",
  "Explain how engine reliability changed ETOPS and long-haul network design.",
  "Make a gym-length audio brief on why military aircraft programs overrun.",
];

const OMISSIONS = [
  "No manufacturer interviews are attached yet.",
  "Maintenance cost data is summarized, not source-complete.",
  "Generated visuals are barred from claiming archival truth.",
];

function estimateCost(minutes: number, mode: Mode, tier: RouteTier): string {
  const modeBase = mode === "audio" ? 0.28 : mode === "video" ? 1.35 : 1.05;
  const total = minutes * modeBase * TIER_COPY[tier].multiplier;
  return `$${total.toFixed(2)}`;
}

function splitOperatorList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function formatRecordCost(record: MultimediaAssetRecord | null, fallback: string): string {
  if (!record) return fallback;
  const costRows = (record.asset.manifest as { cost_rows?: Array<{ cost_usd?: number }> }).cost_rows ?? [];
  if (!costRows.length) return "Unavailable";
  if (costRows.some((row) => !row || typeof row.cost_usd !== "number" || !Number.isFinite(row.cost_usd) || row.cost_usd < 0)) {
    return "Unavailable";
  }
  const total = costRows.reduce((sum, row) => sum + row.cost_usd!, 0);
  return `$${total.toFixed(2)}`;
}

function plannedProviderCalls(record: MultimediaAssetRecord | null): string {
  if (!record) return "Example only";
  const calls = (record.asset.manifest as { provider_calls?: unknown[] }).provider_calls;
  return Array.isArray(calls) ? String(calls.length) : "Unavailable";
}

function statusToRenderState(record: MultimediaAssetRecord | null): RenderState {
  if (!record) return "pending";
  if (record.asset.status === "ready" || record.asset.status === "script_ready") return "partial";
  if (record.asset.status === "failed") return "failed";
  return "pending";
}

function distributeMinutes(total: number): number[] {
  const weights = [0.32, 0.41, 0.27];
  return weights.map((w, i) => {
    if (i === weights.length - 1) {
      const used = weights.slice(0, -1).reduce((sum, x) => sum + Math.round(total * x), 0);
      return Math.max(1, total - used);
    }
    return Math.max(1, Math.round(total * w));
  });
}

export default function Multimedia() {
  const openRequestId = useRef(0);
  const evidenceRequestId = useRef(0);
  const productionRequestId = useRef(0);
  const narrationAuthorizationRequestId = useRef(0);
  const steeringRequestId = useRef(0);
  const steeringApplyInFlight = useRef(false);
  const narrationIdempotency = useRef<{ key: string; requestId: string } | null>(null);
  const [topic, setTopic] = useState("The aircraft program that made cheap long-haul travel possible");
  const [duration, setDuration] = useState(30);
  const [customDuration, setCustomDuration] = useState("30");
  const [mode, setMode] = useState<Mode>("video");
  const [depth, setDepth] = useState<MultimediaDepth>("intermediate");
  const [tier, setTier] = useState<RouteTier>("balanced");
  const [sourceScope, setSourceScope] = useState("Owned corpus + vetted web sources");
  const [style, setStyle] = useState("Asianometry-style explainer with restrained Ken Burns motion");
  const [mustCover, setMustCover] = useState("747 economics, engine reliability, route maps");
  const [planReady, setPlanReady] = useState(false);
  const [approved, setApproved] = useState(false);
  const [renderState, setRenderState] = useState<RenderState>("pending");
  const [playerView, setPlayerView] = useState<PlayerView>("video");
  const [activeChapterId, setActiveChapterId] = useState(CHAPTERS[0].id);
  const [selectedSourceId, setSelectedSourceId] = useState(SOURCES[0].id);
  const [steer, setSteer] = useState("Make chapter 2 more concrete and add a voice note about turbofan reliability.");
  const [rawVoiceSteer, setRawVoiceSteer] = useState<string | null>(null);
  const [voiceSteeringBusy, setVoiceSteeringBusy] = useState(false);
  const [steeringPreview, setSteeringPreview] = useState<SteeringPreviewState | null>(null);
  const [assets, setAssets] = useState<MultimediaAssetSummary[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<MultimediaAssetRecord | null>(null);
  const [selectedCoverageArcIds, setSelectedCoverageArcIds] = useState<string[]>([]);
  const [evidenceSearch, setEvidenceSearch] = useState<MultimediaEvidenceSearchResult | null>(null);
  const [selectedEvidenceIds, setSelectedEvidenceIds] = useState<string[]>([]);
  const [pendingCommand, setPendingCommand] = useState<PendingCommand>(null);
  const [knowledgeMutationPending, setKnowledgeMutationPending] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [playback, setPlayback] = useState<VerifiedPlaybackRecord | null>(null);
  const [playbackLoading, setPlaybackLoading] = useState(false);
  const [productionRegistrationPending, setProductionRegistrationPending] = useState(false);
  const [narrationCeilingUsd, setNarrationCeilingUsd] = useState("1.00");
  const [narrationSpendAcknowledged, setNarrationSpendAcknowledged] = useState(false);
  const [narrationAuthorization, setNarrationAuthorization] = useState<MultimediaNarrationAuthorization | null>(null);
  const [narrationAuthorizationPending, setNarrationAuthorizationPending] = useState(false);
  const [reviewedVisualSet, setReviewedVisualSet] = useState<MultimediaReviewedVisualSet | null>(null);
  const [reviewedVisualStatus, setReviewedVisualStatus] = useState<"idle" | "loading" | "missing" | "error" | "ready">("idle");
  const [chapterNarrationAuthorities, setChapterNarrationAuthorities] = useState<Record<string, MultimediaNarrationAuthorization>>({});
  const [productionWorkerPending, setProductionWorkerPending] = useState(false);

  useEffect(() => {
    productionRequestId.current += 1;
    steeringRequestId.current += 1;
    setProductionRegistrationPending(false);
    setPendingCommand((current) =>
      current === "steer-preview" || current === "steer" ? null : current
    );
    setRawVoiceSteer(null);
    setSteeringPreview(null);
  }, [selectedRecord?.asset.asset_id, selectedRecord?.asset.revision_id]);

  useEffect(() => {
    narrationAuthorizationRequestId.current += 1;
    narrationIdempotency.current = null;
    setNarrationAuthorization(null);
    setNarrationSpendAcknowledged(false);
    setNarrationAuthorizationPending(false);
  }, [selectedRecord?.asset.asset_id, selectedRecord?.asset.revision_id, activeChapterId]);

  useEffect(() => {
    setChapterNarrationAuthorities({});
    setProductionWorkerPending(false);
  }, [selectedRecord?.asset.asset_id, selectedRecord?.asset.revision_id]);

  useEffect(() => {
    if (steeringPreview?.preview.status !== "ready") return;
    const expiresAtMs = steeringPreview.preview.expires_at_epoch_seconds * 1000;
    const expire = () => {
      steeringRequestId.current += 1;
      setSteeringPreview(null);
      setApiError("That steering preview expired. Preview the current request again.");
    };
    let timeout: number | undefined;
    const scheduleExpiry = () => {
      const remaining = expiresAtMs - Date.now();
      if (remaining <= 0) {
        expire();
        return;
      }
      timeout = window.setTimeout(scheduleExpiry, Math.min(remaining, 2_147_483_647));
    };
    scheduleExpiry();
    return () => {
      if (timeout !== undefined) window.clearTimeout(timeout);
    };
  }, [steeringPreview]);

  useEffect(() => {
    let cancelled = false;
    setPendingCommand("list");
    listMultimediaAssets()
      .then((result) => {
        if (cancelled) return;
        setAssets(result.assets);
        setApiError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setApiError("Multimedia API is unavailable. Fixture preview remains available, but assets will not persist.");
      })
      .finally(() => {
        if (!cancelled) setPendingCommand(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setPlayback(null);
    if (!approved || !selectedRecord) {
      setPlaybackLoading(false);
      return () => {
        cancelled = true;
      };
    }
    const { asset_id: assetId, revision_id: revisionId } = selectedRecord.asset;
    setPlaybackLoading(true);
    const request = shouldUseLocalAudiblePlayback(selectedRecord)
      ? getMultimediaLocalAudiblePlayback(assetId, revisionId)
      : getMultimediaPlayback(assetId, revisionId);
    if (selectedRecord.mode === "audio") setPlayerView("audio");
    request
      .then((result) => {
        if (!cancelled) setPlayback(result);
      })
      .catch(() => {
        if (!cancelled) setPlayback(null);
      })
      .finally(() => {
        if (!cancelled) setPlaybackLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [approved, selectedRecord]);

  useEffect(() => {
    let cancelled = false;
    setReviewedVisualSet(null);
    setReviewedVisualStatus("idle");
    if (!selectedRecord || selectedRecord.mode === "audio") return;
    const { asset_id: assetId, revision_id: revisionId } = selectedRecord.asset;
    setReviewedVisualStatus("loading");
    getMultimediaReviewedVisualSet(assetId, revisionId)
      .then((result) => {
        if (!cancelled) {
          setReviewedVisualSet(result);
          setReviewedVisualStatus("ready");
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setReviewedVisualSet(null);
          setReviewedVisualStatus(
            error instanceof Error && error.message === "multimedia_reviewed_visuals_unavailable"
              ? "missing"
              : "error",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRecord]);

  const exampleChapters = useMemo(() => {
    const minutes = distributeMinutes(duration);
    return CHAPTERS.map((chapter, index) => ({ ...chapter, minutes: minutes[index] }));
  }, [duration]);

  const planProjection = useMemo(
    () => (selectedRecord ? projectMultimediaPlan(selectedRecord.plan) : null),
    [selectedRecord],
  );
  const projectedPlan = planProjection?.ok ? planProjection.value : null;
  const planProjectionError = planProjection && !planProjection.ok ? planProjection.error : null;
  const planChapters = projectedPlan?.chapters ?? (selectedRecord ? [] : exampleChapters);
  const planSuggestions = projectedPlan?.suggestions ?? (selectedRecord ? [] : SUGGESTIONS);
  const planOmissions = projectedPlan?.omissions ?? (selectedRecord ? [] : OMISSIONS);
  const planSources = projectedPlan?.sources ?? (selectedRecord ? [] : SOURCES);
  const unsourcedClaims = projectedPlan?.unsourcedClaims ?? [];
  const coverageOptions = projectedPlan?.coverageOptions ?? [];

  const activeChapter = planChapters.find((chapter) => chapter.id === activeChapterId) ?? planChapters[0];
  const selectedSource = planSources.find((source) => source.id === selectedSourceId) ?? planSources[0];
  const estimatedCost = formatRecordCost(selectedRecord, estimateCost(duration, mode, tier));
  // Approve posts only asset_id, so it runs against the STORED route_policy.
  // Gate it so the UI never prices one tier while approving another (grok #8).
  const routeTierMatchesRecord = !selectedRecord || selectedRecord.asset.route_policy === tier;
  const canApprove =
    planReady && topic.trim().length > 0 && duration >= 15 && duration <= 45 && routeTierMatchesRecord &&
    planProjection?.ok === true && unsourcedClaims.length === 0;
  const canRunAssetCommand =
    Boolean(selectedRecord) && pendingCommand === null && !knowledgeMutationPending;

  useEffect(() => {
    if (!planChapters.some((chapter) => chapter.id === activeChapterId)) {
      setActiveChapterId(planChapters[0]?.id ?? "");
    }
    if (!planSources.some((source) => source.id === selectedSourceId)) {
      setSelectedSourceId(planSources[0]?.id ?? "");
    }
  }, [activeChapterId, planChapters, planSources, selectedSourceId]);

  useEffect(() => {
    if (!projectedPlan) {
      setSelectedCoverageArcIds([]);
      return;
    }
    setSelectedCoverageArcIds(projectedPlan.chosenArcIds);
    setDepth(projectedPlan.depth);
    setSourceScope(projectedPlan.sourceScope ?? "");
  }, [projectedPlan]);

  useEffect(() => {
    evidenceRequestId.current += 1;
    setEvidenceSearch(null);
    setSelectedEvidenceIds([]);
  }, [selectedRecord?.asset.asset_id, selectedRecord?.asset.revision_id]);

  function setPreset(next: number) {
    setDuration(next);
    setCustomDuration(String(next));
  }

  function setCustom(next: string) {
    setCustomDuration(next);
    const parsed = Number.parseInt(next, 10);
    if (Number.isFinite(parsed)) {
      setDuration(Math.max(15, Math.min(45, parsed)));
    }
  }

  async function refreshAssetList() {
    const result = await listMultimediaAssets();
    setAssets(result.assets);
  }

  async function createPlan(selectedArcIds: string[]) {
    if (knowledgeMutationPending) return;
    const request: CreateMultimediaDraftRequest = {
      topic,
      target_minutes: duration,
      mode,
      route_policy: tier,
      source_scope: sourceScope.trim() || null,
      must_cover: splitOperatorList(mustCover),
      audience: "curious generalist",
      style,
      depth,
      selected_arc_ids: selectedArcIds,
    };
    setPendingCommand("create");
    try {
      const record = await createMultimediaDraft(request);
      setSelectedRecord(record);
      setPlanReady(true);
      setApproved(false);
      setRenderState(statusToRenderState(record));
      setApiError(null);
      try {
        await refreshAssetList();
      } catch {
        // best-effort: a failed list refresh must not mask a successful mutation
      }
    } catch {
      setApiError("Could not create a persisted multimedia draft. Check the API process and retry.");
      setPlanReady(true);
      setApproved(false);
      setRenderState("pending");
    } finally {
      setPendingCommand(null);
    }
  }

  function generatePlan() {
    return createPlan([]);
  }

  async function discoverEvidence() {
    if (!selectedRecord || pendingCommand !== null) return;
    const requestId = ++evidenceRequestId.current;
    const requestedRecord = selectedRecord;
    setPendingCommand("evidence-search");
    try {
      const result = await searchMultimediaEvidence(
        requestedRecord.asset.asset_id,
        requestedRecord.asset.revision_id,
      );
      if (requestId !== evidenceRequestId.current) return;
      setEvidenceSearch(result);
      setSelectedEvidenceIds(result.candidates.map((candidate) => candidate.chunk_id));
      setApiError(null);
    } catch {
      if (requestId !== evidenceRequestId.current) return;
      setEvidenceSearch(null);
      setSelectedEvidenceIds([]);
      setApiError("Could not retrieve evidence from the current knowledge graph.");
    } finally {
      if (requestId === evidenceRequestId.current) setPendingCommand(null);
    }
  }

  async function createGroundedDraft() {
    if (!selectedRecord || !evidenceSearch || pendingCommand !== null) return;
    const selected = evidenceSearch.candidates.filter((candidate) => selectedEvidenceIds.includes(candidate.chunk_id));
    if (!selected.length) return;
    setPendingCommand("ground");
    try {
      const record = await createGroundedMultimediaDraft(
        selectedRecord.asset.asset_id,
        selectedRecord.asset.revision_id,
        selected,
      );
      setSelectedRecord(record);
      setPlanReady(true);
      setApproved(false);
      setRenderState("pending");
      setApiError(null);
      try {
        await refreshAssetList();
      } catch {
        // best-effort: the grounded draft is already durable
      }
    } catch {
      setApiError("Evidence changed or became unavailable. Search the graph again before creating a grounded draft.");
    } finally {
      setPendingCommand(null);
    }
  }

  function toggleCoverageArc(arcId: string) {
    setSelectedCoverageArcIds((current) =>
      current.includes(arcId) ? current.filter((id) => id !== arcId) : [...current, arcId],
    );
  }

  async function reopenAsset(assetId: string) {
    if (knowledgeMutationPending) return;
    const requestId = ++openRequestId.current;
    setPendingCommand("open");
    try {
      const record = await getMultimediaAsset(assetId);
      if (requestId !== openRequestId.current) return;
      setSelectedRecord(record);
      setTopic(record.asset.title);
      setDuration(record.asset.requested_duration_minutes);
      setCustomDuration(String(record.asset.requested_duration_minutes));
      setMode(record.mode);
      setTier(record.asset.route_policy);
      setStyle(record.style ?? "");
      setPlanReady(true);
      setApproved(record.asset.status === "ready");
      setRenderState(statusToRenderState(record));
      setApiError(null);
    } catch {
      if (requestId !== openRequestId.current) return;
      setApiError("Could not reopen that multimedia asset.");
    } finally {
      if (requestId === openRequestId.current) setPendingCommand(null);
    }
  }

  async function approvePlan() {
    if (!selectedRecord) return;
    setPendingCommand("approve");
    try {
      const record = await approveMultimediaDryRun(selectedRecord.asset.asset_id);
      setSelectedRecord(record);
      setApproved(true);
      setRenderState(statusToRenderState(record));
      setApiError(null);
      try {
        await refreshAssetList();
      } catch {
        // best-effort: a failed list refresh must not mask a successful mutation
      }
    } catch {
      setApiError("Could not approve the dry-run render.");
      setRenderState("failed");
    } finally {
      setPendingCommand(null);
    }
  }

  async function registerProducedMedia() {
    if (!selectedRecord || productionRegistrationPending) return;
    const requestedAssetId = selectedRecord.asset.asset_id;
    const requestedRevisionId = selectedRecord.asset.revision_id;
    const requestedRecord = selectedRecord;
    const requestId = ++productionRequestId.current;
    setProductionRegistrationPending(true);
    try {
      const record = await registerMultimediaProduction(
        requestedAssetId,
        requestedRevisionId,
      );
      if (requestId === productionRequestId.current) {
        setSelectedRecord((current) => (current === requestedRecord ? record : current));
      }
      if (requestId === productionRequestId.current) setApiError(null);
    } catch {
      if (requestId === productionRequestId.current) {
        setApiError("No verified production receipt is available for this revision.");
      }
    } finally {
      if (requestId === productionRequestId.current) setProductionRegistrationPending(false);
    }
  }

  async function authorizeCurrentChapterNarration() {
    if (!selectedRecord || !activeChapter || !narrationSpendAcknowledged || narrationAuthorizationPending) return;
    const ceiling = Math.round(Number(narrationCeilingUsd) * 1_000_000);
    if (!Number.isSafeInteger(ceiling) || ceiling <= 0) {
      setApiError("Enter a positive narration ceiling.");
      return;
    }
    const idempotencyKey = `${selectedRecord.asset.asset_id}\0${selectedRecord.asset.revision_id}\0${activeChapter.id}\0${ceiling}`;
    if (narrationIdempotency.current?.key !== idempotencyKey) {
      const nonce = typeof globalThis.crypto?.randomUUID === "function"
        ? globalThis.crypto.randomUUID()
        : `${Date.now().toString(36)}-${narrationAuthorizationRequestId.current.toString(36)}`;
      narrationIdempotency.current = { key: idempotencyKey, requestId: `narration-${nonce}` };
    }
    const requestId = narrationIdempotency.current.requestId;
    const completionId = ++narrationAuthorizationRequestId.current;
    setNarrationAuthorizationPending(true);
    try {
      const authority = await authorizeMultimediaNarration(selectedRecord.asset.asset_id, {
        request_id: requestId,
        expected_revision_id: selectedRecord.asset.revision_id,
        chapter_id: activeChapter.id,
        approved_ceiling_microdollars: ceiling,
        operator_acknowledged_spend: true,
      });
      if (completionId === narrationAuthorizationRequestId.current) {
        setNarrationAuthorization(authority);
        setChapterNarrationAuthorities((current) => ({
          ...current,
          [authority.chapter_id]: authority,
        }));
        setApiError(null);
      }
    } catch {
      if (completionId === narrationAuthorizationRequestId.current) {
        setApiError("Could not authorize narration for this chapter and ceiling.");
      }
    } finally {
      if (completionId === narrationAuthorizationRequestId.current) {
        setNarrationAuthorizationPending(false);
      }
    }
  }

  async function produceCurrentDocumentary() {
    if (!selectedRecord || !reviewedVisualSet || productionWorkerPending) return;
    const authorities = planChapters.map((chapter) => chapterNarrationAuthorities[chapter.id]);
    if (authorities.some((authority) => !authority)) return;
    const requestedRecord = selectedRecord;
    setProductionWorkerPending(true);
    try {
      const produced = await produceAuthorizedMultimedia(
        requestedRecord.asset.asset_id,
        requestedRecord.asset.revision_id,
        authorities.map((authority, index) => ({
          chapter_id: planChapters[index].id,
          authorization: authority!.authorization,
        })),
      );
      setSelectedRecord((current) => (current === requestedRecord ? produced : current));
      setApiError(null);
    } catch {
      setApiError("Could not produce this revision from its current authorities.");
    } finally {
      setProductionWorkerPending(false);
    }
  }

  function steeringRequest(): MultimediaSteeringRequest | null {
    if (!selectedRecord || !steer.trim()) return null;
    const prompt = steer.trim();
    return {
      expected_parent_revision_id: selectedRecord.asset.revision_id,
      prompt,
      ...(rawVoiceSteer ? {
        raw_voice_transcript: rawVoiceSteer,
        ...(prompt === rawVoiceSteer ? {} : { corrected_voice_transcript: prompt }),
      } : {}),
    };
  }

  function invalidateSteeringPreview() {
    steeringRequestId.current += 1;
    setSteeringPreview(null);
    setPendingCommand((current) => current === "steer-preview" ? null : current);
  }

  function updateSteeringText(value: string) {
    invalidateSteeringPreview();
    setSteer(value);
  }

  async function previewSteeringPrompt() {
    const request = steeringRequest();
    if (!selectedRecord || !request) return;
    const assetId = selectedRecord.asset.asset_id;
    const requestId = ++steeringRequestId.current;
    setSteeringPreview(null);
    setPendingCommand("steer-preview");
    try {
      const preview = await previewMultimediaSteering(assetId, request);
      if (requestId !== steeringRequestId.current) return;
      setSteeringPreview({ preview, request });
      setApiError(null);
    } catch {
      if (requestId === steeringRequestId.current) {
        setApiError("Could not preview that steering prompt.");
      }
    } finally {
      if (requestId === steeringRequestId.current) setPendingCommand(null);
    }
  }

  async function applySteeringPrompt() {
    if (!selectedRecord || !steeringPreview) return;
    const readyPreview = steeringPreview.preview;
    if (readyPreview.status !== "ready") return;
    if (readyPreview.expires_at_epoch_seconds * 1000 <= Date.now()) {
      invalidateSteeringPreview();
      setApiError("That steering preview expired. Preview the current request again.");
      return;
    }
    if (steeringApplyInFlight.current) return;
    steeringApplyInFlight.current = true;
    const requestedRecord = selectedRecord;
    const requestedPreview = steeringPreview;
    const requestId = ++steeringRequestId.current;
    setSteeringPreview(null);
    setPendingCommand("steer");
    try {
      const record = await steerMultimediaAsset(requestedRecord.asset.asset_id, {
        ...requestedPreview.request,
        preview_token: readyPreview.preview_token,
      });
      if (requestId !== steeringRequestId.current) return;
      setPendingCommand(null);
      setSelectedRecord(record);
      setSteeringPreview(null);
      setPlanReady(true);
      setApproved(record.asset.status === "ready");
      setRenderState(statusToRenderState(record));
      setApiError(null);
      try {
        await refreshAssetList();
      } catch {
        // best-effort: a failed list refresh must not mask a successful mutation
      }
    } catch (error) {
      if (requestId !== steeringRequestId.current) return;
      setSteeringPreview(null);
      const code = error instanceof Error ? error.message : "";
      if (code === "multimedia_steering_stale_parent") {
        try {
          const reopened = await getMultimediaAsset(requestedRecord.asset.asset_id);
          if (requestId !== steeringRequestId.current) return;
          setPendingCommand(null);
          setApiError("This asset changed after preview. Review the current revision and preview again.");
          setSelectedRecord(reopened);
        } catch {
          // The conflict remains actionable even if the best-effort refresh fails.
          if (requestId !== steeringRequestId.current) return;
          setApiError("This asset changed after preview. Review the current revision and preview again.");
        }
      } else {
        setApiError("Could not apply that reviewed steering preview.");
      }
    } finally {
      steeringApplyInFlight.current = false;
      if (requestId === steeringRequestId.current) setPendingCommand(null);
    }
  }

  async function runHardening() {
    if (!selectedRecord) return;
    setPendingCommand("harden");
    try {
      const record = await runMultimediaHardening(selectedRecord.asset.asset_id);
      setSelectedRecord(record);
      setApiError(null);
      try {
        await refreshAssetList();
      } catch {
        // best-effort: a failed list refresh must not mask a successful mutation
      }
    } catch {
      setApiError("Could not run multimedia hardening.");
    } finally {
      setPendingCommand(null);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-ice-0 dark:bg-charcoal-2">
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-7xl grid-cols-1 gap-4 px-5 py-5 xl:grid-cols-[360px_minmax(0,1fr)_320px]">
          <section className="space-y-4 rounded-md border border-rule bg-ice-1 p-4 dark:border-charcoal-1 dark:bg-charcoal-2">
            <header>
              <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">
                Multimedia
              </p>
              <h1 className="font-serif text-2xl text-ink dark:text-bright">
                Generate information media
              </h1>
              <p className="mt-1 text-[13px] leading-relaxed text-shadow-1 dark:text-moonlight">
                Plan a grounded explainer, audio brief, or documentary-style reel before spending on media generation.
              </p>
            </header>

            <Labeled label="Topic" htmlFor="multimedia-topic">
              <LemonTextarea
                id="multimedia-topic"
                value={topic}
                minRows={3}
                maxRows={5}
                onChange={(event) => setTopic(event.target.value)}
                aria-label="Topic"
              />
            </Labeled>

            <div>
              <p className="mb-2 font-mono text-[12px] text-shadow-2 dark:text-moonlight">Duration</p>
              <div role="radiogroup" aria-label="Duration presets" className="grid grid-cols-3 gap-2">
                {[15, 30, 45].map((minutes) => (
                  <button
                    key={minutes}
                    type="button"
                    role="radio"
                    aria-checked={duration === minutes}
                    onClick={() => setPreset(minutes)}
                    className={segmentClass(duration === minutes)}
                  >
                    {minutes} min
                  </button>
                ))}
              </div>
              <label className="mt-2 flex items-center gap-2 text-[12px] text-shadow-1 dark:text-moonlight">
                Custom
                <input
                  type="number"
                  min={15}
                  max={45}
                  value={customDuration}
                  onChange={(event) => setCustom(event.target.value)}
                  aria-label="Custom duration"
                  className="h-8 w-20 rounded-md border border-rule bg-ice-0 px-2 text-[13px] text-ink outline-none dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                />
                <span>15-45 minutes</span>
              </label>
            </div>

            <Fieldset label="Mode">
              {(["video", "audio", "hybrid"] as Mode[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  role="radio"
                  aria-checked={mode === item}
                  onClick={() => {
                    setMode(item);
                    if (item === "audio") setPlayerView("audio");
                  }}
                  className={segmentClass(mode === item)}
                >
                  {item}
                </button>
              ))}
            </Fieldset>

            <Fieldset label="Learning depth">
              {(["overview", "intermediate", "deep"] as MultimediaDepth[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  role="radio"
                  aria-checked={depth === item}
                  onClick={() => setDepth(item)}
                  className={segmentClass(depth === item)}
                >
                  {item}
                </button>
              ))}
            </Fieldset>

            <div>
              <p className="mb-2 font-mono text-[12px] text-shadow-2 dark:text-moonlight">Generation route</p>
              <div className="space-y-2">
                {(["cheapest", "balanced", "highest_quality"] as RouteTier[]).map((item) => (
                  <button
                    key={item}
                    type="button"
                    aria-pressed={tier === item}
                    onClick={() => setTier(item)}
                    className={
                      "w-full rounded-md border px-3 py-2 text-left " +
                      (tier === item
                        ? "border-sun bg-sun/20 text-ink dark:text-bright"
                        : "border-rule bg-ice-0 text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright")
                    }
                  >
                    <span className="block font-mono text-[12px] font-semibold">{TIER_COPY[item].label}</span>
                    <span className="mt-1 block text-[12px] leading-snug text-shadow-1 dark:text-moonlight">
                      {TIER_COPY[item].tradeoff}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <Labeled label="Research scope" htmlFor="multimedia-source-scope">
              <LemonInput
                id="multimedia-source-scope"
                value={sourceScope}
                onChange={(event) => setSourceScope(event.target.value)}
                wrapperClassName="w-full"
              />
            </Labeled>
            <Labeled label="Style" htmlFor="multimedia-style">
              <LemonInput
                id="multimedia-style"
                value={style}
                onChange={(event) => setStyle(event.target.value)}
                wrapperClassName="w-full"
              />
            </Labeled>
            <Labeled label="Must cover" htmlFor="multimedia-must-cover">
              <LemonTextarea
                id="multimedia-must-cover"
                value={mustCover}
                minRows={2}
                maxRows={4}
                onChange={(event) => setMustCover(event.target.value)}
              />
            </Labeled>

            <div className="flex items-center justify-between gap-3 border-t border-rule pt-3 dark:border-charcoal-1">
              <div>
                <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Estimated render</p>
                <p className="text-lg font-semibold text-ink dark:text-bright" data-testid="multimedia-estimated-cost">
                  {estimatedCost}
                </p>
              </div>
              <LemonButton type="button" variant="primary" onClick={generatePlan} disabled={pendingCommand !== null || knowledgeMutationPending}>
                {pendingCommand === "create" ? "Creating..." : "Review plan"}
              </LemonButton>
            </div>
          </section>

          <section className="min-w-0 space-y-4 rounded-md border border-rule bg-ice-1 p-4 dark:border-charcoal-1 dark:bg-charcoal-2">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">Plan review</p>
                <h2 className="font-serif text-xl text-ink dark:text-bright">
                  {planReady ? selectedRecord?.asset.title ?? topic : "No plan reviewed yet"}
                </h2>
                {selectedRecord && (
                  <p className="mt-1 font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                    {selectedRecord.asset.asset_id} / {selectedRecord.asset.revision_id}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <LemonTag colour="sun">{duration} minutes</LemonTag>
                <LemonTag>{mode}</LemonTag>
                <LemonTag colour={tier === "highest_quality" ? "aurora" : "default"}>
                  {TIER_COPY[tier].label}
                </LemonTag>
              </div>
            </div>

            {apiError && (
              <div className="rounded-md border border-danger bg-danger/10 p-3 text-[13px] text-ink dark:text-bright" role="alert">
                {apiError}
              </div>
            )}

            {assets.length > 0 && (
              <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Persisted assets</p>
                  <LemonTag>{assets.length}</LemonTag>
                </div>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  {assets.map((asset) => (
                    <button
                      key={`${asset.asset_id}-${asset.revision_id}`}
                      type="button"
                      disabled={knowledgeMutationPending || pendingCommand !== null}
                      onClick={() => reopenAsset(asset.asset_id)}
                      className={
                        "rounded-md border px-3 py-2 text-left disabled:cursor-not-allowed disabled:opacity-50 " +
                        (selectedRecord?.asset.asset_id === asset.asset_id
                          ? "border-sun bg-sun/20"
                          : "border-rule bg-ice-1 dark:border-charcoal-1 dark:bg-charcoal-2")
                      }
                    >
                      <span className="block font-mono text-[12px] text-ink dark:text-bright">{asset.status}</span>
                      <span className="mt-1 block text-[13px] leading-snug text-shadow-1 dark:text-moonlight">
                        {asset.title}
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            )}

            {!planReady ? (
              <div className="rounded-md border border-dashed border-rule px-4 py-10 text-center text-[13px] text-shadow-1 dark:border-charcoal-1 dark:text-moonlight">
                Set a topic, duration, source scope, route tier, and must-cover constraints, then review the plan before rendering.
              </div>
            ) : (
              <>
                {planProjectionError ? (
                  <div className="rounded-md border border-danger bg-danger/10 p-3 text-[13px] text-ink dark:text-bright" role="alert">
                    Persisted plan cannot be reviewed: {planProjectionError}
                  </div>
                ) : (
                <>
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                  <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1" data-testid="multimedia-suggestions">
                    <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Coverage suggestions</p>
                    {selectedRecord ? (
                      <div className="mt-2 space-y-2">
                        {coverageOptions.map((option) => {
                          const selected = selectedCoverageArcIds.includes(option.id);
                          return (
                            <label key={option.id} className="flex cursor-pointer items-start gap-2 rounded border border-rule p-2 dark:border-charcoal-1">
                              <input
                                type="checkbox"
                                checked={selected}
                                onChange={() => toggleCoverageArc(option.id)}
                                aria-label={`Include ${option.title}`}
                              />
                              <span className="min-w-0 text-[12px] leading-snug text-ink dark:text-bright">
                                <strong className="block">{option.title}</strong>
                                <span className="block text-shadow-1 dark:text-moonlight">{option.teaches}</span>
                                <span className="mt-1 block font-mono text-[10px] text-shadow-2 dark:text-moonlight">
                                  {option.evidenceCount} cited source{option.evidenceCount === 1 ? "" : "s"} / {option.tradeoff}
                                </span>
                              </span>
                            </label>
                          );
                        })}
                        <LemonButton
                          type="button"
                          size="sm"
                          variant="secondary"
                          disabled={selectedCoverageArcIds.length === 0 || pendingCommand !== null || knowledgeMutationPending}
                          onClick={() => createPlan(selectedCoverageArcIds)}
                        >
                          {pendingCommand === "create" ? "Creating..." : "Create focused draft"}
                        </LemonButton>
                      </div>
                    ) : (
                      <InfoList items={planSuggestions} />
                    )}
                  </section>
                  <InfoPanel title="Known omissions" items={planOmissions} testId="multimedia-omissions" />
                  <div className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                    <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Render budget</p>
                    <p className="mt-2 text-2xl font-semibold text-ink dark:text-bright">{estimatedCost}</p>
                    <p className="mt-1 text-[12px] leading-snug text-shadow-1 dark:text-moonlight">
                      {selectedRecord
                        ? `Persisted ${selectedRecord.asset.route_policy.replaceAll("_", " ")} route.`
                        : `${sourceScope}. ${TIER_COPY[tier].tradeoff}`}
                    </p>
                  </div>
                </div>

                <p className="mb-1 font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                  {selectedRecord ? "Persisted storyboard" : "Offline example storyboard"}
                </p>
                <ol className="space-y-2" aria-label="Storyboard outline">
                  {planChapters.map((chapter, chapterIndex) => (
                    <li
                      key={chapter.id}
                      className="list-none"
                    >
                      <button
                        type="button"
                        aria-label={`Select storyboard chapter ${chapterIndex + 1}`}
                        onClick={() => {
                          setActiveChapterId(chapter.id);
                          setSelectedSourceId(chapter.sourceId ?? "");
                        }}
                        className={
                          "w-full rounded-md border p-3 text-left " +
                          (chapter.id === activeChapterId
                            ? "border-sun bg-sun/20"
                            : "border-rule bg-ice-0 dark:border-charcoal-1 dark:bg-charcoal-1")
                        }
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h3 className="font-serif text-base text-ink dark:text-bright">{chapter.title}</h3>
                          <p className="mt-1 text-[13px] leading-relaxed text-shadow-1 dark:text-moonlight">
                            {chapter.purpose}
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <LemonTag colour="muted">{chapter.minutes} min</LemonTag>
                          <LemonTag colour={chapter.visualLabel === "planned" ? "muted" : "default"}>
                            {chapter.visualLabel}
                          </LemonTag>
                        </div>
                        </div>
                      </button>
                    </li>
                  ))}
                </ol>

                <div className="rounded-md border border-sun bg-sun/10 p-3">
                  <p className="font-mono text-[12px] text-ink">Unsourced claim guard</p>
                  {unsourcedClaims.length ? (
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-shadow-2">
                      {unsourcedClaims.map((claim) => <li key={claim}>{claim}</li>)}
                    </ul>
                  ) : (
                    <p className="mt-1 text-[13px] leading-relaxed text-shadow-2">
                      {selectedRecord ? "No unsourced factual lines are recorded in this plan." : "Example only. Create a persisted plan to inspect grounding."}
                    </p>
                  )}
                </div>

                {selectedRecord && unsourcedClaims.length > 0 && (
                  <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Knowledge graph evidence</p>
                      <LemonButton
                        type="button"
                        onClick={discoverEvidence}
                        disabled={pendingCommand !== null}
                      >
                        {pendingCommand === "evidence-search" ? "Searching..." : "Find evidence"}
                      </LemonButton>
                    </div>
                    {evidenceSearch && (
                      <div className="mt-3 space-y-3" data-testid="multimedia-evidence-results">
                        {evidenceSearch.candidates.length > 0 ? (
                          <ul className="space-y-2">
                            {evidenceSearch.candidates.map((candidate) => (
                              <li key={candidate.chunk_id}>
                                <label className="flex gap-3 rounded-md border border-rule p-3 dark:border-charcoal-1">
                                  <input
                                    type="checkbox"
                                    checked={selectedEvidenceIds.includes(candidate.chunk_id)}
                                    onChange={() => setSelectedEvidenceIds((current) =>
                                      current.includes(candidate.chunk_id)
                                        ? current.filter((id) => id !== candidate.chunk_id)
                                        : [...current, candidate.chunk_id]
                                    )}
                                    aria-label={`Include evidence from ${candidate.document_title}`}
                                  />
                                  <span className="min-w-0">
                                    <span className="block text-[13px] font-semibold text-ink dark:text-bright">
                                      {candidate.document_title}
                                    </span>
                                    <span className="mt-1 block text-[12px] leading-relaxed text-shadow-1 dark:text-moonlight">
                                      {candidate.excerpt}
                                    </span>
                                    <span className="mt-1 block font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                                      {candidate.section_path ?? "Source"} · {candidate.similarity.toFixed(3)}
                                    </span>
                                  </span>
                                </label>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-[13px] text-shadow-1 dark:text-moonlight">No matching evidence found.</p>
                        )}
                        <LemonButton
                          type="button"
                          variant="primary"
                          onClick={createGroundedDraft}
                          disabled={pendingCommand !== null || selectedEvidenceIds.length === 0}
                        >
                          {pendingCommand === "ground" ? "Creating..." : "Create grounded draft"}
                        </LemonButton>
                      </div>
                    )}
                  </section>
                )}

                {selectedRecord && activeChapter && (
                  <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                    <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Narration authority</p>
                    <div className="mt-2 flex flex-wrap items-end gap-3">
                      <label className="text-[12px] text-shadow-1 dark:text-moonlight">
                        Ceiling (USD)
                        <input
                          type="number"
                          min="0.01"
                          step="0.01"
                          value={narrationCeilingUsd}
                          onChange={(event) => setNarrationCeilingUsd(event.target.value)}
                          className="mt-1 block h-9 w-28 rounded-md border border-rule bg-ice-1 px-2 text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
                        />
                      </label>
                      <label className="flex items-center gap-2 pb-2 text-[12px] text-shadow-1 dark:text-moonlight">
                        <input
                          type="checkbox"
                          checked={narrationSpendAcknowledged}
                          onChange={(event) => setNarrationSpendAcknowledged(event.target.checked)}
                        />
                        Approve this maximum
                      </label>
                      <LemonButton
                        type="button"
                        variant="secondary"
                        onClick={authorizeCurrentChapterNarration}
                        disabled={!narrationSpendAcknowledged || narrationAuthorizationPending}
                      >
                        {narrationAuthorizationPending ? "Authorizing..." : "Authorize narration"}
                      </LemonButton>
                    </div>
                    {narrationAuthorization && (
                      <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[12px]">
                        <dt className="text-shadow-1 dark:text-moonlight">Authority</dt>
                        <dd className="truncate text-ink dark:text-bright">{narrationAuthorization.authorization.authorization_id}</dd>
                        <dt className="text-shadow-1 dark:text-moonlight">Provider</dt>
                        <dd className="text-ink dark:text-bright">{narrationAuthorization.authorization.provider} / {narrationAuthorization.authorization.model}</dd>
                        <dt className="text-shadow-1 dark:text-moonlight">Body digest</dt>
                        <dd className="truncate text-ink dark:text-bright">{narrationAuthorization.request_body_digest}</dd>
                        <dt className="text-shadow-1 dark:text-moonlight">Expires</dt>
                        <dd className="text-ink dark:text-bright">{narrationAuthorization.authorization.expires_at}</dd>
                      </dl>
                    )}
                  </section>
                )}

                {selectedRecord && selectedRecord.mode !== "audio" && selectedRecord.asset.route_policy === "cheapest" && (
                  <LocalProductionPanel
                    record={selectedRecord}
                    onRegistered={() => reopenAsset(selectedRecord.asset.asset_id)}
                  />
                )}

                {selectedRecord && selectedRecord.mode === "audio" && selectedRecord.asset.route_policy === "cheapest" && (
                  <LocalAudiblePanel
                    record={selectedRecord}
                    onRegistered={() => reopenAsset(selectedRecord.asset.asset_id)}
                  />
                )}

                {selectedRecord && selectedRecord.mode !== "audio" && selectedRecord.asset.route_policy !== "cheapest" && (
                  <>
                    {reviewedVisualStatus === "loading" ? (
                      <p className="border-t border-rule pt-4 font-mono text-[11px] text-shadow-2 dark:border-charcoal-1 dark:text-moonlight">
                        Checking visual sequence...
                      </p>
                    ) : reviewedVisualStatus === "error" ? (
                      <p className="border-t border-rule pt-4 font-mono text-[11px] text-emperor dark:border-charcoal-1">
                        Status unavailable
                      </p>
                    ) : (
                      <VisualReviewPanel
                        record={selectedRecord}
                        reviewedSet={reviewedVisualSet}
                        onRegistered={(value) => {
                          setReviewedVisualSet(value);
                          setReviewedVisualStatus("ready");
                        }}
                      />
                    )}
                    <section className="border-t border-rule pt-3 dark:border-charcoal-1">
                    <LemonButton
                      type="button"
                      variant="secondary"
                      onClick={produceCurrentDocumentary}
                      disabled={
                        !reviewedVisualSet ||
                        productionWorkerPending ||
                        planChapters.some((chapter) => !chapterNarrationAuthorities[chapter.id])
                      }
                    >
                      {productionWorkerPending ? "Producing..." : "Produce documentary"}
                    </LemonButton>
                    </section>
                  </>
                )}

                <div className="flex flex-wrap items-center gap-2">
                  <LemonButton
                    type="button"
                    variant="primary"
                    disabled={!canApprove || !selectedRecord || pendingCommand !== null || knowledgeMutationPending}
                    onClick={approvePlan}
                  >
                    {pendingCommand === "approve" ? "Approving..." : "Approve render"}
                  </LemonButton>
                  {selectedRecord && !routeTierMatchesRecord && (
                    <span className="text-[12px] text-shadow-1 dark:text-moonlight">
                      Tier differs from the saved plan — create a new draft to apply it.
                    </span>
                  )}
                  <LemonButton
                    type="button"
                    variant="secondary"
                    disabled={knowledgeMutationPending}
                    onClick={() => {
                      setPlanReady(false);
                      setApproved(false);
                      setRenderState(selectedRecord ? statusToRenderState(selectedRecord) : "pending");
                    }}
                  >
                    Edit brief
                  </LemonButton>
                  <LemonButton
                    type="button"
                    variant="tertiary"
                    disabled={!canRunAssetCommand}
                    onClick={() => updateSteeringText("Shorten the economics setup and add more diagrams.")}
                  >
                    Steer outline
                  </LemonButton>
                </div>

                {selectedRecord && (
                  <KnowledgePanel
                    key={`${selectedRecord.asset.asset_id}:${selectedRecord.asset.revision_id}`}
                    asset={selectedRecord}
                    onAssetUpdated={(updated) => {
                      const expectedAssetId = selectedRecord.asset.asset_id;
                      const expectedRevisionId = selectedRecord.asset.revision_id;
                      setSelectedRecord((current) =>
                        retainCurrentMultimediaSelection(
                          current,
                          expectedAssetId,
                          expectedRevisionId,
                          updated,
                        ),
                      );
                    }}
                    onMutationBusyChange={setKnowledgeMutationPending}
                  />
                )}
                </>
                )}
              </>
            )}
          </section>

          <aside className="space-y-4">
            <ReconciliationPanel assetId={selectedRecord?.asset.asset_id ?? null} />
            <StatusPanel
              state={renderState}
              onState={setRenderState}
              onDowngrade={() => {
                setTier("cheapest");
                setRenderState("partial");
              }}
            />
            <section className="rounded-md border border-rule bg-ice-1 p-3 dark:border-charcoal-1 dark:bg-charcoal-2">
              <VoiceSteeringInput
                key={`${selectedRecord?.asset.asset_id ?? "none"}:${selectedRecord?.asset.revision_id ?? "none"}`}
                value={steer}
                rawTranscript={rawVoiceSteer}
                disabled={!canRunAssetCommand}
                onChange={(value) => {
                  updateSteeringText(value);
                }}
                onTranscript={(transcript) => {
                  invalidateSteeringPreview();
                  setRawVoiceSteer(transcript);
                  setSteer(transcript);
                }}
                onDiscardTranscript={() => {
                  invalidateSteeringPreview();
                  setRawVoiceSteer(null);
                }}
                onBusyChange={setVoiceSteeringBusy}
              />
              <div className="mt-2 flex gap-2">
                <LemonButton
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={!canRunAssetCommand || voiceSteeringBusy}
                  onClick={previewSteeringPrompt}
                >
                  {pendingCommand === "steer-preview" ? "Previewing..." : "Preview steer"}
                </LemonButton>
                {steeringPreview?.preview.status === "ready" && (
                  <LemonButton
                    type="button"
                    size="sm"
                    variant="primary"
                    disabled={!canRunAssetCommand || voiceSteeringBusy}
                    onClick={applySteeringPrompt}
                  >
                    {pendingCommand === "steer" ? "Applying..." : "Apply preview"}
                  </LemonButton>
                )}
                <LemonButton
                  type="button"
                  size="sm"
                  variant="tertiary"
                  disabled={!canRunAssetCommand}
                  onClick={runHardening}
                >
                  {pendingCommand === "harden" ? "Checking..." : "Run hardening"}
                </LemonButton>
              </div>
              {pendingCommand === "steer" && (
                <p className="mt-2 text-[12px] text-shadow-1 dark:text-moonlight" role="status">
                  Applying reviewed revision...
                </p>
              )}
              {steeringPreview?.preview.status === "needs_clarification" && (
                <div className="mt-3 rounded-md border border-rule bg-ice-0 p-2 text-[12px] text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright" role="status">
                  <p className="font-mono font-semibold">Clarify before applying</p>
                  {steeringPreview.preview.intent.clarifications.map((clarification) => (
                    <p key={clarification} className="mt-1">{clarification}</p>
                  ))}
                </div>
              )}
              {steeringPreview?.preview.status === "ready" && (
                <div className="mt-3 rounded-md border border-rule bg-ice-0 p-2 text-[12px] text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright" data-testid="multimedia-steering-preview">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-mono font-semibold">Revision preview</p>
                    <LemonTag>{steeringPreview.preview.route_policy.replace("_", " ")}</LemonTag>
                  </div>
                  <p className="mt-1">Incremental cost: ${steeringPreview.preview.estimated_cost_delta_usd.toFixed(4)}</p>
                  <p>Affected: {steeringPreview.preview.affected_segment_ids.length} segments</p>
                  <p>Reused: {steeringPreview.preview.segment_reuse.filter((row) => row.reused).length} segments</p>
                  <ul className="mt-1 space-y-1">
                    {steeringPreview.preview.operations.map((operation) => (
                      <li key={operation.operation_id}>{operation.reason}</li>
                    ))}
                  </ul>
                </div>
              )}
              {selectedRecord?.hardening_report && (
                <div className="mt-3 rounded-md border border-rule bg-ice-0 p-2 text-[12px] text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright">
                  <p className="font-mono">Hardening: {selectedRecord.hardening_report.ship_status}</p>
                  <p>Manual: {manualGateIds(selectedRecord.hardening_report).join(", ") || "none"}</p>
                  <p>Failed: {failedGateIds(selectedRecord.hardening_report).join(", ") || "none"}</p>
                </div>
              )}
            </section>
          </aside>

          {approved && (
            <section
              className="space-y-4 rounded-md border border-rule bg-ice-1 p-4 dark:border-charcoal-1 dark:bg-charcoal-2 xl:col-span-3"
              data-testid="multimedia-player"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">Asset playback</p>
                  <h2 className="font-serif text-xl text-ink dark:text-bright">
                    {playback ? "Verified media" : "Playback unavailable"}
                  </h2>
                </div>
                {selectedRecord?.mode !== "audio" && (
                  <div role="radiogroup" aria-label="Playback type" className="flex gap-2">
                    {(["video", "audio"] as PlayerView[]).map((view) => (
                      <button
                        key={view}
                        type="button"
                        role="radio"
                        aria-checked={playerView === view}
                        onClick={() => setPlayerView(view)}
                        className={segmentClass(playerView === view)}
                      >
                        {view}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
                <div className="space-y-3">
                  <div className="flex aspect-video items-center justify-center overflow-hidden rounded-md border border-rule bg-charcoal-2 text-bright dark:border-charcoal-1">
                    {playbackLoading ? (
                      <p className="font-mono text-[12px] uppercase text-moonlight" role="status">Verifying media...</p>
                    ) : playback && playerView === "video" && "video_url" in playback ? (
                      <video
                        key={`${playback.revision_id}-video`}
                        controls
                        crossOrigin="use-credentials"
                        preload="metadata"
                        src={playback.video_url}
                        className="h-full w-full bg-black object-contain"
                        aria-label={`Video playback for ${selectedRecord?.asset.title ?? "multimedia asset"}`}
                      />
                    ) : playback ? (
                      <audio
                        key={`${playback.revision_id}-audio`}
                        controls
                        crossOrigin="use-credentials"
                        preload="metadata"
                        src={playback.audio_url}
                        className="w-[min(90%,640px)]"
                        aria-label={`Audio playback for ${selectedRecord?.asset.title ?? "multimedia asset"}`}
                      />
                    ) : (
                      <div className="px-6 text-center" role="status">
                        <p className="font-mono text-[12px] uppercase text-moonlight">No verified media receipt</p>
                        <p className="mt-2 text-[13px] text-moonlight">
                          This revision has plan and transcript data, but no verified video or narration is available to play.
                        </p>
                        {selectedRecord && selectedRecord.mode !== "audio" && !selectedRecord.production_link && (
                          <LemonButton
                            type="button"
                            variant="secondary"
                            className="mt-3"
                            onClick={registerProducedMedia}
                            disabled={productionRegistrationPending}
                          >
                            {productionRegistrationPending ? "Checking receipt..." : "Register produced media"}
                          </LemonButton>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                    {planChapters.map((chapter) => (
                      <button
                        key={chapter.id}
                        type="button"
                        onClick={() => {
                          setActiveChapterId(chapter.id);
                          setSelectedSourceId(chapter.sourceId ?? "");
                        }}
                        className={
                          "rounded-md border px-3 py-2 text-left " +
                          (chapter.id === activeChapterId
                            ? "border-sun bg-sun/20"
                            : "border-rule bg-ice-0 dark:border-charcoal-1 dark:bg-charcoal-1")
                        }
                      >
                        <span className="block font-mono text-[12px] text-ink dark:text-bright">{chapter.minutes} min</span>
                        <span className="mt-1 block text-[13px] leading-snug text-shadow-1 dark:text-moonlight">
                          {chapter.title}
                        </span>
                      </button>
                    ))}
                  </div>

                  <article
                    data-testid="multimedia-transcript"
                    className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <LemonTag colour="sun">Current segment</LemonTag>
                      <LemonTag>{activeChapter?.visualLabel ?? "unavailable"} visual</LemonTag>
                    </div>
                    <p className="mt-3 text-[14px] leading-relaxed text-ink dark:text-bright">
                      {activeChapter?.transcript ?? "No persisted transcript is available."}
                    </p>
                  </article>
                </div>

                <div className="space-y-3">
                  <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                    <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Source cards</p>
                    <div className="mt-2 space-y-2">
                      {planSources.map((source) => (
                        <button
                          key={source.id}
                          type="button"
                          onClick={() => setSelectedSourceId(source.id)}
                          className={
                            "w-full rounded-md border px-3 py-2 text-left " +
                            (source.id === selectedSourceId
                              ? "border-sun bg-sun/15"
                              : "border-rule bg-ice-1 dark:border-charcoal-1 dark:bg-charcoal-2")
                          }
                        >
                          <span className="block font-mono text-[12px] text-ink dark:text-bright">{source.title}</span>
                          <span className="mt-1 block text-[12px] text-shadow-1 dark:text-moonlight">{source.status}</span>
                        </button>
                      ))}
                    </div>
                    <p className="mt-3 text-[13px] leading-relaxed text-ink dark:text-bright" data-testid="multimedia-source-detail">
                      {selectedSource?.detail ?? "No cited source is attached to this plan."}
                    </p>
                  </section>

                  <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                    <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Cost ledger</p>
                    <dl className="mt-2 grid grid-cols-2 gap-2 text-[13px]">
                      <dt className="text-shadow-1 dark:text-moonlight">Route</dt>
                      <dd className="text-right text-ink dark:text-bright">{TIER_COPY[tier].label}</dd>
                      <dt className="text-shadow-1 dark:text-moonlight">Estimate</dt>
                      <dd className="text-right text-ink dark:text-bright">{estimatedCost}</dd>
                      <dt className="text-shadow-1 dark:text-moonlight">Provider calls</dt>
                      <dd className="text-right text-ink dark:text-bright">{plannedProviderCalls(selectedRecord)}</dd>
                    </dl>
                  </section>

                  <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                    <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Revision history</p>
                    <ol className="mt-2 space-y-1 text-[13px] text-shadow-1 dark:text-moonlight">
                      <li>{selectedRecord ? `Persisted revision ${selectedRecord.asset.revision_id}.` : "Offline example; no revision persisted."}</li>
                      {selectedRecord?.asset.parent_revision_id && (
                        <li>Child revision from {selectedRecord.asset.parent_revision_id}.</li>
                      )}
                      <li>{unsourcedClaims.length} unsourced factual line{unsourcedClaims.length === 1 ? "" : "s"} recorded.</li>
                    </ol>
                  </section>
                </div>
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

function Labeled({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block font-mono text-[12px] text-shadow-2 dark:text-moonlight">
        {label}
      </label>
      {children}
    </div>
  );
}

function Fieldset({ label, children }: { label: string; children: ReactNode }) {
  return (
    <fieldset>
      <legend className="mb-2 font-mono text-[12px] text-shadow-2 dark:text-moonlight">{label}</legend>
      <div role="radiogroup" aria-label={label} className="grid grid-cols-3 gap-2">
        {children}
      </div>
    </fieldset>
  );
}

function InfoPanel({ title, items, testId }: { title: string; items: string[]; testId: string }) {
  return (
    <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1" data-testid={testId}>
      <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">{title}</p>
      <ul className="mt-2 space-y-1 text-[13px] leading-snug text-ink dark:text-bright">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function InfoList({ items }: { items: string[] }) {
  return (
    <ul className="mt-2 space-y-1 text-[13px] leading-snug text-ink dark:text-bright">
      {items.map((item) => <li key={item}>{item}</li>)}
    </ul>
  );
}

function StatusPanel({
  state,
  onState,
  onDowngrade,
}: {
  state: RenderState;
  onState: (state: RenderState) => void;
  onDowngrade: () => void;
}) {
  const message: Record<RenderState, string> = {
    pending: "Waiting for plan approval. No paid media calls have started.",
    rendering: "Rendering dry-run package. Provider calls are queued behind budget approval.",
    partial: "Partial render available. One visual beat fell back to a placeholder.",
    failed: "Render failed. The manifest and transcript are retained for retry.",
    over_budget: "Over budget. Choose a cheaper route or approve a higher ceiling.",
    provider_unavailable: "Krea provider unavailable. Downgrade to placeholders or retry later.",
  };

  return (
    <section className="rounded-md border border-rule bg-ice-1 p-3 dark:border-charcoal-1 dark:bg-charcoal-2">
      <div className="flex items-center justify-between gap-3">
        <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Render status</p>
        <LemonTag colour={state === "failed" || state === "over_budget" ? "danger" : state === "rendering" ? "sun" : "default"}>
          {state.replace("_", " ")}
        </LemonTag>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-ink dark:text-bright" role="status">
        {message[state]}
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <LemonButton type="button" size="sm" variant="secondary" onClick={() => onState("provider_unavailable")}>
          Sim provider down
        </LemonButton>
        <LemonButton type="button" size="sm" variant="secondary" onClick={() => onState("over_budget")}>
          Sim over budget
        </LemonButton>
        <LemonButton type="button" size="sm" variant="tertiary" onClick={() => onState("failed")}>
          Sim failed
        </LemonButton>
        <LemonButton
          type="button"
          size="sm"
          variant={state === "failed" ? "secondary" : "primary"}
          onClick={state === "failed" ? () => onState("rendering") : onDowngrade}
        >
          {state === "failed" ? "Retry render" : "Use cheapest fallback"}
        </LemonButton>
        {state === "failed" && (
          <LemonButton type="button" size="sm" variant="primary" onClick={onDowngrade}>
            Use cheapest fallback
          </LemonButton>
        )}
        {state !== "failed" && (
          <LemonButton type="button" size="sm" variant="tertiary" onClick={() => onState("partial")}>
            Keep partial
          </LemonButton>
        )}
      </div>
    </section>
  );
}

function segmentClass(active: boolean): string {
  return (
    "rounded-md border px-3 py-2 text-center font-mono text-[12px] font-semibold " +
    (active
      ? "border-sun bg-sun text-ink"
      : "border-rule bg-ice-0 text-ink hover:border-sun dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright")
  );
}

export function shouldUseLocalAudiblePlayback(record: MultimediaAssetRecord): boolean {
  return (
    record.mode === "audio" &&
    record.asset.route_policy === "cheapest" &&
    record.audio_production_link !== null &&
    record.audio_production_link !== undefined
  );
}
