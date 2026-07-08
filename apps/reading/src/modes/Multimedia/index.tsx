import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  attachMultimediaProviderArtifact,
  approveMultimediaDryRun,
  createMultimediaDraft,
  getMultimediaAsset,
  listMultimediaJobs,
  listMultimediaAssets,
  prepareMultimediaLiveExecution,
  runMultimediaProviderWorker,
  runMultimediaHardening,
  steerMultimediaAsset,
} from "../../api/multimedia";
import type {
  CreateMultimediaDraftRequest,
  LiveProviderExecutionRequest,
  MultimediaAssetRecord,
  MultimediaAssetSummary,
  MultimediaJobRecord,
  MultimediaProviderReadinessStatus,
} from "../../api/multimedia";
import { LemonButton, LemonInput, LemonTag, LemonTextarea } from "../../components/lemon";

type Mode = "video" | "audio" | "hybrid";
type RouteTier = "cheapest" | "balanced" | "highest_quality";
type RenderState = "pending" | "rendering" | "partial" | "failed" | "over_budget" | "provider_unavailable";
type PlayerView = "video" | "audio";
type ReadinessFilter = "all" | "manual_attach_ready" | "artifact_attached" | "artifact_rejected";
type AttachmentFeedback = {
  assetId: string;
  jobId: string;
  mediaType: string | null;
};
type LiveSpendReviewItem = {
  label: string;
  value: string;
  tone?: "default" | "muted" | "sun" | "danger";
};
type LiveSpendPreflight = {
  items: LiveSpendReviewItem[];
  request: LiveProviderExecutionRequest | null;
};
type QueueAuditFeedback = {
  items: LiveSpendReviewItem[];
};
type PersistedQueuedAuditItem = {
  label: string;
  value: string;
};
type PendingCommand =
  | "list"
  | "create"
  | "approve"
  | "steer"
  | "harden"
  | "open"
  | "jobs"
  | "queue"
  | "worker"
  | "attach"
  | null;

type Chapter = {
  id: string;
  title: string;
  minutes: number;
  purpose: string;
  visualLabel: "generated" | "sourced" | "diagram";
  sourceId: string;
  transcript: string;
};

const TIER_COPY: Record<RouteTier, { label: string; multiplier: number; tradeoff: string }> = {
  cheapest: {
    label: "Cheapest",
    multiplier: 0.55,
    tradeoff: "Local placeholders first; Krea only for missing motion beats.",
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
    visualLabel: "generated",
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

const READINESS_FILTERS: Array<{ value: ReadinessFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "manual_attach_ready", label: "Manual attach" },
  { value: "artifact_attached", label: "Attached" },
  { value: "artifact_rejected", label: "Rejected" },
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

function formatRecordCost(record: MultimediaAssetRecord | null, tier: RouteTier, fallback: string): string {
  if (!record) return fallback;
  if (record.asset.route_policy !== tier) return fallback;
  const costRows = (record.asset.manifest as { cost_rows?: Array<{ cost_usd?: number }> }).cost_rows ?? [];
  if (!costRows.length) return fallback;
  const total = costRows.reduce((sum, row) => sum + (typeof row.cost_usd === "number" ? row.cost_usd : 0), 0);
  return `$${total.toFixed(2)}`;
}

function formatBudgetCap(value: string): string {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return "Enter positive budget";
  return `$${parsed.toFixed(2)} cap`;
}

function formatPersistedBudgetCap(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `$${value.toFixed(2)} cap` : "unavailable";
}

function buildLiveSpendPreflight({
  maxBudgetUsd,
  operatorAck,
  selectedRecord,
  tier,
  duration,
  mode,
}: {
  maxBudgetUsd: string;
  operatorAck: boolean;
  selectedRecord: MultimediaAssetRecord | null;
  tier: RouteTier;
  duration: number;
  mode: Mode;
}): LiveSpendPreflight {
  const parsedBudget = Number.parseFloat(maxBudgetUsd);
  const hasPositiveBudget = Number.isFinite(parsedBudget) && parsedBudget > 0;
  const providerFamilies = ["krea"];
  const dryRunRevisionId = selectedRecord?.asset.revision_id ?? null;
  const request =
    hasPositiveBudget && dryRunRevisionId
      ? {
          max_budget_usd: parsedBudget,
          route_policy: tier,
          operator_acknowledged_spend: operatorAck,
          provider_families: providerFamilies,
          dry_run_revision_id: dryRunRevisionId,
        }
      : null;

  return {
    request,
    items: [
      { label: "Spend boundary", value: "No paid worker runs from Queue live job", tone: "sun" },
      { label: "Budget cap", value: formatBudgetCap(maxBudgetUsd), tone: hasPositiveBudget ? "default" : "danger" },
      { label: "Acknowledgement", value: operatorAck ? "Spend acknowledged" : "Acknowledgement required", tone: operatorAck ? "default" : "danger" },
      { label: "Dry-run revision", value: dryRunRevisionId ?? "No asset selected", tone: dryRunRevisionId ? "default" : "muted" },
      { label: "Provider route", value: `${TIER_COPY[tier].label} / ${providerFamilies.join(", ")}`, tone: "default" },
      { label: "Requested media", value: `${selectedRecord?.asset.requested_duration_minutes ?? duration} min ${mode}`, tone: "default" },
      { label: "Worker state", value: "Live worker disabled", tone: "muted" },
    ],
  };
}

function buildQueueAuditFeedback(job: MultimediaJobRecord, preflight: LiveSpendPreflight): QueueAuditFeedback {
  const itemValue = (label: string) => preflight.items.find((item) => item.label === label)?.value ?? "Unknown";
  return {
    items: [
      { label: "Queued job", value: job.job_id, tone: "sun" },
      { label: "Budget cap", value: itemValue("Budget cap") },
      { label: "Dry-run revision", value: itemValue("Dry-run revision") },
      { label: "Provider route", value: itemValue("Provider route") },
      { label: "Requested media", value: itemValue("Requested media") },
      { label: "Worker state", value: "No paid worker consumed this job", tone: "muted" },
    ],
  };
}

function buildPersistedQueuedAuditItems(asset: MultimediaAssetSummary): PersistedQueuedAuditItem[] {
  const readiness = asset.provider_readiness;
  const routePolicy = readiness.live_request_route_policy ?? asset.route_policy;
  return [
    { label: "Asset", value: asset.asset_id },
    { label: "Queued job", value: readiness.source_job_id ?? "unavailable" },
    { label: "Status", value: readiness.status },
    { label: "Route", value: TIER_COPY[routePolicy].label },
    { label: "Requested media", value: `${asset.requested_duration_minutes} min ${asset.kind.replace(/_/g, " ")}` },
    { label: "Provider", value: readiness.provider_family ?? "unavailable" },
    { label: "Execution mode", value: readiness.execution_mode ?? "unavailable" },
    { label: "Budget cap", value: formatPersistedBudgetCap(readiness.live_request_max_budget_usd) },
    { label: "Dry-run revision", value: readiness.live_request_dry_run_revision_id ?? "unavailable" },
    { label: "Worker state", value: "No paid worker consumed this job" },
  ];
}

function buildArtifactLineageItems(asset: MultimediaAssetSummary): PersistedQueuedAuditItem[] {
  const readiness = asset.provider_readiness;
  const routePolicy = readiness.live_request_route_policy ?? asset.route_policy;
  return [
    { label: "Request route", value: TIER_COPY[routePolicy].label },
    { label: "Budget cap", value: formatPersistedBudgetCap(readiness.live_request_max_budget_usd) },
    { label: "Dry-run revision", value: readiness.live_request_dry_run_revision_id ?? "unavailable" },
  ];
}

function buildAttachedArtifactAuditItems(asset: MultimediaAssetSummary): PersistedQueuedAuditItem[] {
  const readiness = asset.provider_readiness;
  return [
    { label: "Asset", value: asset.asset_id },
    { label: "Status", value: readiness.status },
    { label: "Artifact URI", value: readiness.artifact_uri ?? "unavailable" },
    { label: "Artifact checksum", value: readiness.artifact_checksum ?? "unavailable" },
    { label: "Artifact media type", value: readiness.artifact_media_type ?? "unavailable" },
    { label: "Provider", value: readiness.provider_family ?? "unavailable" },
    { label: "Execution mode", value: readiness.execution_mode ?? "unavailable" },
    { label: "Source job", value: readiness.source_job_id ?? "unavailable" },
    ...buildArtifactLineageItems(asset),
    { label: "Copy action", value: "Read-only; no provider worker triggered" },
  ];
}

function statusToRenderState(record: MultimediaAssetRecord | null): RenderState {
  if (!record) return "pending";
  if (record.asset.status === "ready") return "partial";
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

function latestAttachableArtifactJobId(record: MultimediaAssetRecord): string {
  return (
    record.jobs
      .filter((job) => job.kind === "provider_execution" && job.execution_mode === "live_requested")
      .at(-1)?.job_id ?? ""
  );
}

function providerReadinessTone(status: MultimediaProviderReadinessStatus): "default" | "muted" | "sun" | "danger" {
  if (status === "manual_attach_ready") return "sun";
  if (status === "artifact_rejected") return "danger";
  if (status === "no_provider_jobs") return "muted";
  return "default";
}

function providerReadinessSummary(jobs: MultimediaJobRecord[], artifactJobId: string): Array<{ label: string; value: string; tone: "default" | "muted" | "sun" | "danger" }> {
  const providerJobs = jobs.filter((job) => job.kind === "provider_execution");
  const latestMatchingJob = (predicate: (job: MultimediaJobRecord) => boolean): MultimediaJobRecord | undefined =>
    providerJobs.slice().reverse().find(predicate);
  const activeLiveJob = latestMatchingJob(
    (job) => job.execution_mode === "live_requested" && (job.status === "queued" || job.status === "running"),
  );
  const attachedArtifact = latestMatchingJob((job) => Boolean(job.artifact_uri));
  const rejectedArtifact = latestMatchingJob((job) => job.error_code === "artifact_validation_failed");
  const dryRunCompletion = latestMatchingJob((job) => job.execution_mode === "dry_run" && job.status === "succeeded");

  return [
    {
      label: "Spend boundary",
      value: "Live worker disabled",
      tone: "muted",
    },
    {
      label: "Dry-run worker",
      value: dryRunCompletion ? "Completed" : providerJobs.length ? "Available" : "No job rows",
      tone: dryRunCompletion ? "default" : "muted",
    },
    {
      label: "Live queue",
      value: activeLiveJob ? `Queued ${activeLiveJob.job_id}` : "No active live job",
      tone: activeLiveJob ? "sun" : "muted",
    },
    {
      label: "Manual attach",
      value: artifactJobId.trim() ? `Ready for ${artifactJobId.trim()}` : "Waiting for live job",
      tone: artifactJobId.trim() ? "default" : "muted",
    },
    {
      label: "Artifact state",
      value: attachedArtifact ? "Attached" : rejectedArtifact ? "Rejected" : activeLiveJob ? "Pending" : "Not attached",
      tone: attachedArtifact ? "default" : rejectedArtifact ? "danger" : activeLiveJob ? "sun" : "muted",
    },
  ];
}

function artifactValidationHints(message: string | null | undefined) {
  if (!message) return [];
  const hints: string[] = [];
  if (message.includes("artifact_uri") || message.includes("http(s) URL")) {
    hints.push("Artifact URL: http(s) URL with host");
  }
  if (message.includes("artifact_checksum") || message.includes("sha256")) {
    hints.push("Checksum: sha256 digest");
  }
  if (message.includes("artifact_media_type") || message.includes("type/subtype")) {
    hints.push("Media type: type/subtype");
  }
  return hints;
}

export default function Multimedia() {
  const [topic, setTopic] = useState("The aircraft program that made cheap long-haul travel possible");
  const [duration, setDuration] = useState(30);
  const [customDuration, setCustomDuration] = useState("30");
  const [mode, setMode] = useState<Mode>("video");
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
  const [assets, setAssets] = useState<MultimediaAssetSummary[]>([]);
  const [readinessFilter, setReadinessFilter] = useState<ReadinessFilter>("all");
  const [selectedRecord, setSelectedRecord] = useState<MultimediaAssetRecord | null>(null);
  const [pendingCommand, setPendingCommand] = useState<PendingCommand>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [maxBudgetUsd, setMaxBudgetUsd] = useState("50");
  const [operatorAck, setOperatorAck] = useState(false);
  const [artifactJobId, setArtifactJobId] = useState("");
  const [artifactUri, setArtifactUri] = useState("");
  const [artifactChecksum, setArtifactChecksum] = useState("");
  const [artifactMediaType, setArtifactMediaType] = useState("video/mp4");
  const [artifactValidationMessage, setArtifactValidationMessage] = useState<string | null>(null);
  const [attachmentFeedback, setAttachmentFeedback] = useState<AttachmentFeedback | null>(null);
  const [queueAuditFeedback, setQueueAuditFeedback] = useState<QueueAuditFeedback | null>(null);
  const [copiedAssetId, setCopiedAssetId] = useState<string | null>(null);
  const [copiedSourceJobAssetId, setCopiedSourceJobAssetId] = useState<string | null>(null);
  const [copiedAttachedAuditAssetId, setCopiedAttachedAuditAssetId] = useState<string | null>(null);
  const [copiedRejectedAuditAssetId, setCopiedRejectedAuditAssetId] = useState<string | null>(null);
  const [copiedQueuedAuditAssetId, setCopiedQueuedAuditAssetId] = useState<string | null>(null);
  const [expandedArtifactAssetId, setExpandedArtifactAssetId] = useState<string | null>(null);
  const [expandedQueuedAuditAssetId, setExpandedQueuedAuditAssetId] = useState<string | null>(null);

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

  const planChapters = useMemo(() => {
    const minutes = distributeMinutes(duration);
    return CHAPTERS.map((chapter, index) => ({ ...chapter, minutes: minutes[index] }));
  }, [duration]);

  const activeChapter = planChapters.find((chapter) => chapter.id === activeChapterId) ?? planChapters[0];
  const selectedSource = SOURCES.find((source) => source.id === selectedSourceId) ?? SOURCES[0];
  const estimatedCost = formatRecordCost(selectedRecord, tier, estimateCost(duration, mode, tier));
  const canApprove = planReady && topic.trim().length > 0 && duration >= 15 && duration <= 45;
  const canRunAssetCommand = Boolean(selectedRecord) && pendingCommand === null;
  const latestJob = selectedRecord?.jobs.at(-1) ?? null;
  const shouldPollJobs = latestJob?.kind === "provider_execution" && ["queued", "running"].includes(latestJob.status);
  const liveSpendPreflight = buildLiveSpendPreflight({ maxBudgetUsd, operatorAck, selectedRecord, tier, duration, mode });
  const visibleAssets = useMemo(
    () =>
      readinessFilter === "all"
        ? assets
        : assets.filter((asset) => asset.provider_readiness.status === readinessFilter),
    [assets, readinessFilter],
  );

  useEffect(() => {
    if (artifactJobId || !selectedRecord) return;
    const attachableJob = selectedRecord.jobs
      .filter((job) => job.kind === "provider_execution" && job.execution_mode === "live_requested")
      .at(-1);
    if (attachableJob) setArtifactJobId(attachableJob.job_id);
  }, [artifactJobId, selectedRecord]);

  useEffect(() => {
    if (!selectedRecord || !shouldPollJobs) return;
    const assetId = selectedRecord.asset.asset_id;
    const interval = window.setInterval(() => {
      listMultimediaJobs(assetId)
        .then((result) => {
          setSelectedRecord((current) => {
            if (!current || current.asset.asset_id !== assetId) return current;
            return { ...current, jobs: result.jobs };
          });
        })
        .catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(interval);
  }, [selectedRecord?.asset.asset_id, shouldPollJobs]);

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

  function resetManualArtifactFields(nextJobId = "", nextValidationMessage: string | null = null) {
    setArtifactJobId(nextJobId);
    setArtifactUri("");
    setArtifactChecksum("");
    setArtifactMediaType("video/mp4");
    setArtifactValidationMessage(nextValidationMessage);
  }

  async function refreshAssetList() {
    const result = await listMultimediaAssets();
    setAssets(result.assets);
  }

  async function refreshJobs() {
    if (!selectedRecord) return;
    setPendingCommand("jobs");
    try {
      const result = await listMultimediaJobs(selectedRecord.asset.asset_id);
      setSelectedRecord({ ...selectedRecord, jobs: result.jobs });
      setApiError(null);
      await refreshAssetList();
    } catch {
      setApiError("Could not refresh provider job status.");
    } finally {
      setPendingCommand(null);
    }
  }

  async function generatePlan() {
    const request: CreateMultimediaDraftRequest = {
      topic,
      target_minutes: duration,
      mode,
      route_policy: tier,
      sources: [sourceScope].filter((item) => item.trim().length > 0),
      must_cover: splitOperatorList(mustCover),
      audience: "curious generalist",
      style,
    };
    setPendingCommand("create");
    try {
      const record = await createMultimediaDraft(request);
      setSelectedRecord(record);
      resetManualArtifactFields(latestAttachableArtifactJobId(record));
      setQueueAuditFeedback(null);
      setPlanReady(true);
      setApproved(false);
      setRenderState(statusToRenderState(record));
      setApiError(null);
      await refreshAssetList();
    } catch {
      setApiError("Could not create a persisted multimedia draft. Check the API process and retry.");
      setPlanReady(true);
      setApproved(false);
      setRenderState("pending");
    } finally {
      setPendingCommand(null);
    }
  }

  async function reopenAsset(assetId: string) {
    setPendingCommand("open");
    try {
      const record = await getMultimediaAsset(assetId);
      setSelectedRecord(record);
      resetManualArtifactFields(latestAttachableArtifactJobId(record));
      setQueueAuditFeedback(null);
      setTopic(record.asset.title);
      setDuration(record.asset.requested_duration_minutes);
      setCustomDuration(String(record.asset.requested_duration_minutes));
      setMode(record.mode);
      setTier(record.asset.route_policy);
      setPlanReady(true);
      setApproved(record.asset.status === "ready");
      setRenderState(statusToRenderState(record));
      setApiError(null);
    } catch {
      setApiError("Could not reopen that multimedia asset.");
    } finally {
      setPendingCommand(null);
    }
  }

  async function reopenAssetForAttachment(asset: MultimediaAssetSummary) {
    await reopenAsset(asset.asset_id);
    resetManualArtifactFields(asset.provider_readiness.source_job_id ?? "", asset.provider_readiness.message);
  }

  async function copyPersistedArtifactUri(asset: MultimediaAssetSummary) {
    const artifactUri = asset.provider_readiness.artifact_uri;
    if (!artifactUri || !navigator.clipboard) return;
    await navigator.clipboard.writeText(artifactUri);
    setCopiedAssetId(asset.asset_id);
  }

  async function copyPersistedSourceJobId(asset: MultimediaAssetSummary) {
    const sourceJobId = asset.provider_readiness.source_job_id;
    if (!sourceJobId || !navigator.clipboard) return;
    await navigator.clipboard.writeText(sourceJobId);
    setCopiedSourceJobAssetId(asset.asset_id);
  }

  async function copyAttachedArtifactAudit(asset: MultimediaAssetSummary) {
    if (!navigator.clipboard) return;
    const auditLines = buildAttachedArtifactAuditItems(asset).map((item) => `${item.label}: ${item.value}`);
    await navigator.clipboard.writeText(auditLines.join("\n"));
    setCopiedAttachedAuditAssetId(asset.asset_id);
  }

  async function copyRejectedArtifactAudit(asset: MultimediaAssetSummary) {
    if (!navigator.clipboard) return;
    const readiness = asset.provider_readiness;
    const lineageLines = buildArtifactLineageItems(asset).map((item) => `${item.label}: ${item.value}`);
    const auditLines = [
      `asset_id: ${asset.asset_id}`,
      `status: ${readiness.status}`,
      readiness.error_code ? `error_code: ${readiness.error_code}` : null,
      readiness.message ? `message: ${readiness.message}` : null,
      readiness.provider_family ? `provider_family: ${readiness.provider_family}` : null,
      readiness.execution_mode ? `execution_mode: ${readiness.execution_mode}` : null,
      readiness.source_job_id ? `source_job_id: ${readiness.source_job_id}` : null,
      ...lineageLines,
    ].filter((line): line is string => Boolean(line));
    await navigator.clipboard.writeText(auditLines.join("\n"));
    setCopiedRejectedAuditAssetId(asset.asset_id);
  }

  async function copyPersistedQueuedAudit(asset: MultimediaAssetSummary) {
    if (!navigator.clipboard) return;
    const auditLines = buildPersistedQueuedAuditItems(asset).map((item) => `${item.label}: ${item.value}`);
    await navigator.clipboard.writeText(auditLines.join("\n"));
    setCopiedQueuedAuditAssetId(asset.asset_id);
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
      await refreshAssetList();
    } catch {
      setApiError("Could not approve the dry-run render.");
      setRenderState("failed");
    } finally {
      setPendingCommand(null);
    }
  }

  async function applySteeringPrompt() {
    if (!selectedRecord || !steer.trim()) return;
    setPendingCommand("steer");
    try {
      const record = await steerMultimediaAsset(selectedRecord.asset.asset_id, { prompt: steer });
      setSelectedRecord(record);
      setPlanReady(true);
      setApproved(record.asset.status === "ready");
      setRenderState(statusToRenderState(record));
      setApiError(null);
      await refreshAssetList();
    } catch {
      setApiError("Could not apply that steering prompt.");
    } finally {
      setPendingCommand(null);
    }
  }

  async function runHardening() {
    if (!selectedRecord) return;
    setPendingCommand("harden");
    try {
      const record = await runMultimediaHardening(selectedRecord.asset.asset_id);
      setSelectedRecord(record);
      setApiError(null);
      await refreshAssetList();
    } catch {
      setApiError("Could not run multimedia hardening.");
    } finally {
      setPendingCommand(null);
    }
  }

  async function runProviderWorker() {
    if (!selectedRecord) return;
    setPendingCommand("worker");
    try {
      const record = await runMultimediaProviderWorker(selectedRecord.asset.asset_id, { dry_run: true });
      setSelectedRecord(record);
      setRenderState(statusToRenderState(record));
      setApiError(null);
      await refreshAssetList();
    } catch {
      setApiError("Could not run the dry-run provider worker.");
    } finally {
      setPendingCommand(null);
    }
  }

  async function queueLiveProviderJob() {
    if (!selectedRecord) return;
    if (!liveSpendPreflight.request) {
      setApiError("Enter a positive live provider budget before queueing.");
      return;
    }
    setPendingCommand("queue");
    try {
      const record = await prepareMultimediaLiveExecution(selectedRecord.asset.asset_id, liveSpendPreflight.request);
      setSelectedRecord(record);
      const queuedJob = record.jobs.at(-1);
      setQueueAuditFeedback(queuedJob?.kind === "provider_execution" ? buildQueueAuditFeedback(queuedJob, liveSpendPreflight) : null);
      resetManualArtifactFields(queuedJob?.kind === "provider_execution" ? queuedJob.job_id : "");
      setApiError(null);
      await refreshAssetList();
    } catch {
      setApiError("Could not queue live provider execution.");
    } finally {
      setPendingCommand(null);
    }
  }

  async function attachProviderArtifact() {
    if (!selectedRecord) return;
    setPendingCommand("attach");
    try {
      const record = await attachMultimediaProviderArtifact(selectedRecord.asset.asset_id, {
        job_id: artifactJobId.trim(),
        artifact_uri: artifactUri.trim(),
        artifact_checksum: artifactChecksum.trim(),
        artifact_media_type: artifactMediaType.trim(),
      });
      setSelectedRecord(record);
      const attachedJob = record.jobs.filter((job) => job.kind === "provider_execution" && Boolean(job.artifact_uri)).at(-1);
      setAttachmentFeedback(
        attachedJob
          ? {
              assetId: record.asset.asset_id,
              jobId: attachedJob.job_id,
              mediaType: attachedJob.artifact_media_type,
            }
          : null,
      );
      setApiError(null);
      await refreshAssetList();
    } catch {
      setAttachmentFeedback(null);
      setApiError("Could not attach that provider artifact.");
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

            <Labeled label="Source scope" htmlFor="multimedia-source-scope">
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
              <LemonButton type="button" variant="primary" onClick={generatePlan} disabled={pendingCommand !== null}>
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
              <section
                className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1"
                data-testid="multimedia-persisted-assets"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Persisted assets</p>
                  <LemonTag>{assets.length}</LemonTag>
                </div>
                <div className="mt-2 flex flex-wrap gap-2" aria-label="Persisted asset readiness filters">
                  {READINESS_FILTERS.map((filter) => {
                    const count =
                      filter.value === "all"
                        ? assets.length
                        : assets.filter((asset) => asset.provider_readiness.status === filter.value).length;
                    const active = readinessFilter === filter.value;
                    return (
                      <button
                        key={filter.value}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setReadinessFilter(filter.value)}
                        className={
                          "rounded-md border px-2.5 py-1 font-mono text-[11px] " +
                          (active
                            ? "border-sun bg-sun text-ink"
                            : "border-rule bg-ice-1 text-shadow-1 dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-moonlight")
                        }
                      >
                        {filter.label} {count}
                      </button>
                    );
                  })}
                </div>
                {attachmentFeedback && (
                  <p className="mt-2 text-[12px] text-shadow-1 dark:text-moonlight" role="status">
                    Attachment saved for {attachmentFeedback.jobId}
                    {attachmentFeedback.mediaType ? ` (${attachmentFeedback.mediaType})` : ""}.
                  </p>
                )}
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  {visibleAssets.map((asset) => {
                    const attachedNow = attachmentFeedback?.assetId === asset.asset_id;
                    const persistedQueuedAuditItems =
                      asset.provider_readiness.status === "manual_attach_ready" && asset.provider_readiness.source_job_id
                        ? buildPersistedQueuedAuditItems(asset)
                        : [];
                    return (
                      <div
                        key={`${asset.asset_id}-${asset.revision_id}`}
                        className={
                          "flex min-h-[96px] items-stretch rounded-md border " +
                          (selectedRecord?.asset.asset_id === asset.asset_id
                            ? "border-sun bg-sun/20"
                            : "border-rule bg-ice-1 dark:border-charcoal-1 dark:bg-charcoal-2")
                        }
                      >
                        <div className="min-w-0 flex-1">
                          <button
                            type="button"
                            onClick={() => reopenAsset(asset.asset_id)}
                            className="w-full px-3 py-2 text-left"
                          >
                            <span className="block font-mono text-[12px] text-ink dark:text-bright">{asset.status}</span>
                            <span className="mt-1 block text-[13px] leading-snug text-shadow-1 dark:text-moonlight">
                              {asset.title}
                            </span>
                            <span className="mt-2 flex flex-wrap items-center gap-2">
                              <LemonTag colour={attachedNow ? "default" : providerReadinessTone(asset.provider_readiness.status)}>
                                {attachedNow ? "Attachment saved" : asset.provider_readiness.label}
                              </LemonTag>
                              {asset.provider_readiness.artifact_media_type && (
                                <span className="font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                                  {asset.provider_readiness.artifact_media_type}
                                </span>
                              )}
                              {asset.provider_readiness.execution_mode && (
                                <span className="font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                                  {asset.provider_readiness.execution_mode}
                                </span>
                              )}
                              {asset.provider_readiness.provider_family && (
                                <span className="font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                                  {asset.provider_readiness.provider_family}
                                </span>
                              )}
                              {asset.provider_readiness.error_code && (
                                <span className="font-mono text-[11px] text-danger">
                                  {asset.provider_readiness.error_code}
                                </span>
                              )}
                              {asset.provider_readiness.artifact_checksum && (
                                <span className="max-w-full truncate font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                                  {asset.provider_readiness.artifact_checksum}
                                </span>
                              )}
                              {asset.provider_readiness.source_job_id && (
                                <span className="font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                                  {asset.provider_readiness.source_job_id}
                                </span>
                              )}
                            </span>
                          </button>
                          {expandedArtifactAssetId === asset.asset_id && asset.provider_readiness.artifact_uri && (
                            <dl className="mx-3 mb-3 grid gap-1 rounded-md border border-rule bg-ice-0 p-2 text-[11px] dark:border-charcoal-1 dark:bg-charcoal-1">
                              <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-2">
                                <dt className="font-mono text-shadow-2 dark:text-moonlight">Artifact URI</dt>
                                <dd className="truncate font-mono text-ink dark:text-bright">{asset.provider_readiness.artifact_uri}</dd>
                              </div>
                              {asset.provider_readiness.artifact_checksum && (
                                <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-2">
                                  <dt className="font-mono text-shadow-2 dark:text-moonlight">Checksum</dt>
                                  <dd className="truncate font-mono text-ink dark:text-bright">{asset.provider_readiness.artifact_checksum}</dd>
                                </div>
                              )}
                              {asset.provider_readiness.source_job_id && (
                                <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-2">
                                  <dt className="font-mono text-shadow-2 dark:text-moonlight">Source job</dt>
                                  <dd className="truncate font-mono text-ink dark:text-bright">{asset.provider_readiness.source_job_id}</dd>
                                </div>
                              )}
                              {(asset.provider_readiness.provider_family || asset.provider_readiness.execution_mode || asset.provider_readiness.artifact_media_type) && (
                                <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-2">
                                  <dt className="font-mono text-shadow-2 dark:text-moonlight">Route</dt>
                                  <dd className="truncate font-mono text-ink dark:text-bright">
                                    {[asset.provider_readiness.provider_family, asset.provider_readiness.execution_mode, asset.provider_readiness.artifact_media_type]
                                      .filter(Boolean)
                                      .join(" / ")}
                                  </dd>
                                </div>
                              )}
                              {buildArtifactLineageItems(asset).map((item) => (
                                <div key={item.label} className="grid grid-cols-[88px_minmax(0,1fr)] gap-2">
                                  <dt className="font-mono text-shadow-2 dark:text-moonlight">{item.label}</dt>
                                  <dd className="truncate font-mono text-ink dark:text-bright">{item.value}</dd>
                                </div>
                              ))}
                            </dl>
                          )}
                          {asset.provider_readiness.status === "artifact_attached" && asset.provider_readiness.artifact_uri && !attachedNow && (
                            <div className="mx-3 mb-3 rounded-md border border-rule bg-ice-0 p-2 text-[11px] text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright">
                              <p className="font-mono text-ink dark:text-bright">Artifact attached and ready</p>
                              <p className="mt-1 leading-snug text-shadow-1 dark:text-moonlight">
                                Review the attached {asset.provider_readiness.artifact_media_type ?? "artifact"} from{" "}
                                {asset.provider_readiness.source_job_id ?? "the provider job"} before publishing or exporting.
                              </p>
                              <p className="mt-1 truncate font-mono text-shadow-2 dark:text-moonlight">
                                Open, download, copy link, and copy audit are read-only actions; no provider worker is triggered.
                              </p>
                            </div>
                          )}
                          {asset.provider_readiness.status === "artifact_rejected" && asset.provider_readiness.message && (
                            <div className="mx-3 mb-3 rounded-md border border-danger bg-danger/10 p-2 text-[11px] text-ink dark:text-bright">
                              <p className="font-mono text-danger">{asset.provider_readiness.error_code ?? "artifact_rejected"}</p>
                              <p className="mt-1 leading-snug text-shadow-1 dark:text-moonlight">{asset.provider_readiness.message}</p>
                              {(asset.provider_readiness.provider_family || asset.provider_readiness.execution_mode || asset.provider_readiness.source_job_id) && (
                                <p className="mt-1 truncate font-mono text-shadow-2 dark:text-moonlight">
                                  {[asset.provider_readiness.provider_family, asset.provider_readiness.execution_mode, asset.provider_readiness.source_job_id]
                                    .filter(Boolean)
                                    .join(" / ")}
                                </p>
                              )}
                              <p className="mt-1 truncate font-mono text-shadow-2 dark:text-moonlight">
                                {buildArtifactLineageItems(asset).map((item) => item.value).join(" / ")}
                              </p>
                            </div>
                          )}
                          {asset.provider_readiness.status === "manual_attach_ready" && asset.provider_readiness.source_job_id && (
                            <div className="mx-3 mb-3 rounded-md border border-sun bg-sun/10 p-2 text-[11px] text-ink dark:border-sun/80 dark:bg-sun/10 dark:text-bright">
                              <p className="font-mono text-shadow-2 dark:text-moonlight">Queued live request</p>
                              <p className="mt-1 truncate font-mono text-ink dark:text-bright">
                                {asset.provider_readiness.source_job_id} /{" "}
                                {TIER_COPY[asset.provider_readiness.live_request_route_policy ?? asset.route_policy].label} /{" "}
                                {asset.requested_duration_minutes} min
                              </p>
                              {expandedQueuedAuditAssetId === asset.asset_id && (
                                <dl className="mt-2 grid gap-1">
                                  {persistedQueuedAuditItems.map((item) => (
                                    <div key={item.label} className="grid grid-cols-[104px_minmax(0,1fr)] gap-2">
                                      <dt className="font-mono text-shadow-2 dark:text-moonlight">{item.label}</dt>
                                      <dd className="truncate font-mono text-ink dark:text-bright">{item.value}</dd>
                                    </div>
                                  ))}
                                </dl>
                              )}
                            </div>
                          )}
                        </div>
                        {asset.provider_readiness.status === "manual_attach_ready" && !attachedNow && (
                          <div className="m-2 flex shrink-0 flex-col gap-1 self-center">
                            {asset.provider_readiness.source_job_id && (
                              <button
                                type="button"
                                onClick={() => void copyPersistedQueuedAudit(asset)}
                                className="rounded-md border border-rule bg-ice-0 px-3 py-1.5 font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                              >
                                {copiedQueuedAuditAssetId === asset.asset_id ? "Queue audit copied" : "Copy queue audit"}
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedQueuedAuditAssetId((current) =>
                                  current === asset.asset_id ? null : asset.asset_id,
                                )
                              }
                              className="rounded-md border border-rule bg-ice-0 px-3 py-1.5 font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                            >
                              {expandedQueuedAuditAssetId === asset.asset_id ? "Hide details" : "Details"}
                            </button>
                            <button
                              type="button"
                              onClick={() => reopenAssetForAttachment(asset)}
                              className="rounded-md border border-sun bg-sun px-3 py-1.5 font-mono text-[11px] font-semibold text-ink"
                            >
                              Attach
                            </button>
                          </div>
                        )}
                        {asset.provider_readiness.status === "artifact_attached" && !attachedNow && (
                          asset.provider_readiness.artifact_uri ? (
                            <div className="m-2 flex shrink-0 flex-col gap-1 self-center">
                              <a
                                href={asset.provider_readiness.artifact_uri}
                                target="_blank"
                                rel="noreferrer"
                                className="rounded-md border border-rule bg-ice-0 px-3 py-1.5 text-center font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                              >
                                Open
                              </a>
                              <a
                                href={asset.provider_readiness.artifact_uri}
                                download
                                className="rounded-md border border-rule bg-ice-0 px-3 py-1.5 text-center font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                              >
                                Download
                              </a>
                              <button
                                type="button"
                                onClick={() => void copyPersistedArtifactUri(asset)}
                                className="rounded-md border border-rule bg-ice-0 px-3 py-1.5 font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                              >
                                {copiedAssetId === asset.asset_id ? "Copied" : "Copy link"}
                              </button>
                              {asset.provider_readiness.source_job_id && (
                                <button
                                  type="button"
                                  onClick={() => void copyPersistedSourceJobId(asset)}
                                  className="rounded-md border border-rule bg-ice-0 px-3 py-1.5 font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                                >
                                  {copiedSourceJobAssetId === asset.asset_id ? "Job copied" : "Copy job"}
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => void copyAttachedArtifactAudit(asset)}
                                className="rounded-md border border-rule bg-ice-0 px-3 py-1.5 font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                              >
                                {copiedAttachedAuditAssetId === asset.asset_id ? "Audit copied" : "Copy audit"}
                              </button>
                              <button
                                type="button"
                                onClick={() =>
                                  setExpandedArtifactAssetId((current) => (current === asset.asset_id ? null : asset.asset_id))
                                }
                                className="rounded-md border border-rule bg-ice-0 px-3 py-1.5 font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                              >
                                {expandedArtifactAssetId === asset.asset_id ? "Hide details" : "Details"}
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => reopenAsset(asset.asset_id)}
                              className="m-2 self-center rounded-md border border-rule bg-ice-0 px-3 py-1.5 font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                            >
                              View
                            </button>
                          )
                        )}
                        {asset.provider_readiness.status === "artifact_rejected" && !attachedNow && (
                          <div className="m-2 flex shrink-0 flex-col gap-1 self-center">
                            <button
                              type="button"
                              onClick={() => void copyRejectedArtifactAudit(asset)}
                              className="rounded-md border border-rule bg-ice-0 px-3 py-1.5 font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                            >
                              {copiedRejectedAuditAssetId === asset.asset_id ? "Audit copied" : "Copy audit"}
                            </button>
                            {asset.provider_readiness.source_job_id && (
                              <button
                                type="button"
                                onClick={() => void copyPersistedSourceJobId(asset)}
                                className="rounded-md border border-rule bg-ice-0 px-3 py-1.5 font-mono text-[11px] font-semibold text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
                              >
                                {copiedSourceJobAssetId === asset.asset_id ? "Job copied" : "Copy job"}
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => reopenAssetForAttachment(asset)}
                              className="rounded-md border border-danger bg-ice-0 px-3 py-1.5 font-mono text-[11px] font-semibold text-danger dark:bg-charcoal-1"
                            >
                              Retry
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
                {visibleAssets.length === 0 && (
                  <p className="mt-2 text-[12px] text-shadow-1 dark:text-moonlight" role="status">
                    No persisted assets match this readiness filter.
                  </p>
                )}
              </section>
            )}

            {!planReady ? (
              <div className="rounded-md border border-dashed border-rule px-4 py-10 text-center text-[13px] text-shadow-1 dark:border-charcoal-1 dark:text-moonlight">
                Set a topic, duration, source scope, route tier, and must-cover constraints, then review the plan before rendering.
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                  <InfoPanel title="Coverage suggestions" items={SUGGESTIONS} testId="multimedia-suggestions" />
                  <InfoPanel title="Known omissions" items={OMISSIONS} testId="multimedia-omissions" />
                  <div className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                    <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Render budget</p>
                    <p className="mt-2 text-2xl font-semibold text-ink dark:text-bright">{estimatedCost}</p>
                    <p className="mt-1 text-[12px] leading-snug text-shadow-1 dark:text-moonlight">
                      {sourceScope}. {TIER_COPY[tier].tradeoff}
                    </p>
                  </div>
                </div>

                <ol className="space-y-2" aria-label="Storyboard outline">
                  {planChapters.map((chapter) => (
                    <li
                      key={chapter.id}
                      className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1"
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
                          <LemonTag colour={chapter.visualLabel === "generated" ? "danger" : "default"}>
                            {chapter.visualLabel}
                          </LemonTag>
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>

                <div className="rounded-md border border-sun bg-sun/10 p-3">
                  <p className="font-mono text-[12px] text-ink">Unsourced claim guard</p>
                  <p className="mt-1 text-[13px] leading-relaxed text-shadow-2">
                    The planner found one narration bridge that needs a source before final render:
                    "wide-body adoption directly caused lower fares on every route." It can be revised,
                    sourced, or omitted before approval.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <LemonButton
                    type="button"
                    variant="primary"
                    disabled={!canApprove || !selectedRecord || pendingCommand !== null}
                    onClick={approvePlan}
                  >
                    {pendingCommand === "approve" ? "Approving..." : "Approve render"}
                  </LemonButton>
                  <LemonButton
                    type="button"
                    variant="secondary"
                    onClick={() => {
                      setPlanReady(false);
                      setApproved(false);
                      setRenderState(selectedRecord ? statusToRenderState(selectedRecord) : "pending");
                    }}
                  >
                    Edit brief
                  </LemonButton>
                  <LemonButton type="button" variant="tertiary" onClick={() => setSteer("Shorten the economics setup and add more diagrams.")}>
                    Steer outline
                  </LemonButton>
                </div>
              </>
            )}
          </section>

          <aside className="space-y-4">
            <StatusPanel
              state={renderState}
              onState={setRenderState}
              onDowngrade={() => {
                setTier("cheapest");
                setRenderState("partial");
              }}
            />
            <JobPanel
              jobs={selectedRecord?.jobs ?? []}
              latestJob={latestJob}
              busy={pendingCommand === "jobs" || pendingCommand === "queue" || pendingCommand === "worker" || pendingCommand === "attach"}
              canRunWorker={Boolean(selectedRecord) && pendingCommand === null}
              canQueue={Boolean(selectedRecord) && pendingCommand === null}
              canAttach={Boolean(selectedRecord) && pendingCommand === null}
              liveSpendReview={liveSpendPreflight.items}
              queueAuditFeedback={queueAuditFeedback}
              maxBudgetUsd={maxBudgetUsd}
              operatorAck={operatorAck}
              artifactJobId={artifactJobId}
              artifactUri={artifactUri}
              artifactChecksum={artifactChecksum}
              artifactMediaType={artifactMediaType}
              artifactValidationMessage={artifactValidationMessage}
              onBudgetChange={setMaxBudgetUsd}
              onAckChange={setOperatorAck}
              onArtifactJobIdChange={(value) => {
                setArtifactJobId(value);
                setArtifactValidationMessage(null);
              }}
              onArtifactUriChange={(value) => {
                setArtifactUri(value);
                setArtifactValidationMessage(null);
              }}
              onArtifactChecksumChange={(value) => {
                setArtifactChecksum(value);
                setArtifactValidationMessage(null);
              }}
              onArtifactMediaTypeChange={(value) => {
                setArtifactMediaType(value);
                setArtifactValidationMessage(null);
              }}
              onRefresh={refreshJobs}
              onQueue={queueLiveProviderJob}
              onRunWorker={runProviderWorker}
              onAttachArtifact={attachProviderArtifact}
            />
            <section className="rounded-md border border-rule bg-ice-1 p-3 dark:border-charcoal-1 dark:bg-charcoal-2">
              <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Text or voice steering</p>
              <LemonTextarea
                value={steer}
                minRows={3}
                maxRows={5}
                onChange={(event) => setSteer(event.target.value)}
                aria-label="Steering prompt"
                className="mt-2"
              />
              <div className="mt-2 flex gap-2">
                <LemonButton
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={!canRunAssetCommand}
                  onClick={applySteeringPrompt}
                >
                  {pendingCommand === "steer" ? "Applying..." : "Apply steer"}
                </LemonButton>
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
              {selectedRecord?.hardening_report && (
                <div className="mt-3 rounded-md border border-rule bg-ice-0 p-2 text-[12px] text-ink dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright">
                  <p className="font-mono">Hardening: {selectedRecord.hardening_report.ship_status}</p>
                  <p>Manual: {selectedRecord.hardening_report.manual_gate_ids.join(", ") || "none"}</p>
                  <p>Failed: {selectedRecord.hardening_report.failed_gate_ids.join(", ") || "none"}</p>
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
                  <h2 className="font-serif text-xl text-ink dark:text-bright">Draft render package</h2>
                </div>
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
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
                <div className="space-y-3">
                  <div className="flex aspect-video items-center justify-center rounded-md border border-rule bg-charcoal-2 text-bright dark:border-charcoal-1">
                    <div className="text-center">
                      <p className="font-mono text-[12px] uppercase text-moonlight">
                        {playerView === "video" ? "Ken Burns preview" : "Audio waveform"}
                      </p>
                      <p className="mt-2 font-serif text-xl">{activeChapter.title}</p>
                      <p className="mt-1 text-[12px] text-moonlight">
                        Visual label: {activeChapter.visualLabel}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                    {planChapters.map((chapter) => (
                      <button
                        key={chapter.id}
                        type="button"
                        onClick={() => {
                          setActiveChapterId(chapter.id);
                          setSelectedSourceId(chapter.sourceId);
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
                      <LemonTag>{activeChapter.visualLabel} visual</LemonTag>
                    </div>
                    <p className="mt-3 text-[14px] leading-relaxed text-ink dark:text-bright">
                      {activeChapter.transcript}
                    </p>
                  </article>
                </div>

                <div className="space-y-3">
                  <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                    <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Source cards</p>
                    <div className="mt-2 space-y-2">
                      {SOURCES.map((source) => (
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
                      {selectedSource.detail}
                    </p>
                  </section>

                  <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                    <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Cost ledger</p>
                    <dl className="mt-2 grid grid-cols-2 gap-2 text-[13px]">
                      <dt className="text-shadow-1 dark:text-moonlight">Route</dt>
                      <dd className="text-right text-ink dark:text-bright">{TIER_COPY[tier].label}</dd>
                      <dt className="text-shadow-1 dark:text-moonlight">Estimate</dt>
                      <dd className="text-right text-ink dark:text-bright">{estimatedCost}</dd>
                      <dt className="text-shadow-1 dark:text-moonlight">Krea calls</dt>
                      <dd className="text-right text-ink dark:text-bright">{tier === "cheapest" ? "1" : tier === "balanced" ? "4" : "9"}</dd>
                    </dl>
                  </section>

                  <section className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
                    <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Revision history</p>
                    <ol className="mt-2 space-y-1 text-[13px] text-shadow-1 dark:text-moonlight">
                      <li>Plan v1 generated from topic and source scope.</li>
                      {selectedRecord?.asset.parent_revision_id && (
                        <li>Child revision from {selectedRecord.asset.parent_revision_id}.</li>
                      )}
                      <li>Unsourced claim marked before render approval.</li>
                      <li>Current steer queued: {steer}</li>
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

function JobPanel({
  jobs,
  latestJob,
  busy,
  canRunWorker,
  canQueue,
  canAttach,
  liveSpendReview,
  queueAuditFeedback,
  maxBudgetUsd,
  operatorAck,
  artifactJobId,
  artifactUri,
  artifactChecksum,
  artifactMediaType,
  artifactValidationMessage,
  onBudgetChange,
  onAckChange,
  onArtifactJobIdChange,
  onArtifactUriChange,
  onArtifactChecksumChange,
  onArtifactMediaTypeChange,
  onRefresh,
  onQueue,
  onRunWorker,
  onAttachArtifact,
}: {
  jobs: MultimediaJobRecord[];
  latestJob: MultimediaJobRecord | null;
  busy: boolean;
  canRunWorker: boolean;
  canQueue: boolean;
  canAttach: boolean;
  liveSpendReview: LiveSpendReviewItem[];
  queueAuditFeedback: QueueAuditFeedback | null;
  maxBudgetUsd: string;
  operatorAck: boolean;
  artifactJobId: string;
  artifactUri: string;
  artifactChecksum: string;
  artifactMediaType: string;
  artifactValidationMessage: string | null;
  onBudgetChange: (value: string) => void;
  onAckChange: (value: boolean) => void;
  onArtifactJobIdChange: (value: string) => void;
  onArtifactUriChange: (value: string) => void;
  onArtifactChecksumChange: (value: string) => void;
  onArtifactMediaTypeChange: (value: string) => void;
  onRefresh: () => void;
  onQueue: () => void;
  onRunWorker: () => void;
  onAttachArtifact: () => void;
}) {
  const recentJobs = jobs.slice(-4).reverse();
  const [copiedJobId, setCopiedJobId] = useState<string | null>(null);
  const [liveReviewCopied, setLiveReviewCopied] = useState(false);
  const [activationChecklistCopied, setActivationChecklistCopied] = useState(false);
  const [activationHandoffCopied, setActivationHandoffCopied] = useState(false);
  const [queueAuditCopied, setQueueAuditCopied] = useState(false);
  const canSubmitArtifact =
    canAttach && artifactJobId.trim().length > 0 && artifactUri.trim().length > 0 && artifactChecksum.trim().length > 0 && artifactMediaType.trim().length > 0;
  const readiness = providerReadinessSummary(jobs, artifactJobId);
  const liveReviewValue = (label: string) => liveSpendReview.find((item) => item.label === label)?.value ?? "Unavailable";
  const activationChecklist = [
    { label: "Budget gate", value: liveReviewValue("Budget cap") },
    { label: "Operator acknowledgement", value: liveReviewValue("Acknowledgement") },
    { label: "Dry-run revision", value: liveReviewValue("Dry-run revision") },
    { label: "Provider route", value: liveReviewValue("Provider route") },
    { label: "Execution boundary", value: liveReviewValue("Worker state") },
  ];
  const activationChecklistKey = activationChecklist.map((item) => `${item.label}:${item.value}`).join("|");
  const artifactJob = jobs.find((job) => job.job_id === artifactJobId);
  const validationHints =
    artifactJob?.error_code === "artifact_validation_failed" ? artifactValidationHints(artifactJob.message) : artifactValidationHints(artifactValidationMessage);

  async function copyArtifactUri(job: MultimediaJobRecord) {
    if (!job.artifact_uri || !navigator.clipboard) return;
    await navigator.clipboard.writeText(job.artifact_uri);
    setCopiedJobId(job.job_id);
  }

  async function copyLiveSpendReview() {
    if (!navigator.clipboard) return;
    await navigator.clipboard.writeText(liveSpendReview.map((item) => `${item.label}: ${item.value}`).join("\n"));
    setLiveReviewCopied(true);
  }

  async function copyActivationChecklist() {
    if (!navigator.clipboard) return;
    await navigator.clipboard.writeText(
      [
        ...activationChecklist.map((item) => `${item.label}: ${item.value}`),
        "Activation state: Evidence only; provider execution still requires a separate worker activation.",
      ].join("\n"),
    );
    setActivationChecklistCopied(true);
  }

  async function copyActivationHandoff() {
    if (!navigator.clipboard) return;
    await navigator.clipboard.writeText(
      [
        "Activation handoff",
        ...activationChecklist.map((item) => `${item.label}: ${item.value}`),
        "Activation state: Evidence only; provider execution still requires a separate worker activation.",
        "Operator next step: Review this bundle before enabling a live provider worker.",
        "Spend boundary: Queue live job records intent only; it does not call Krea/TTS/video providers.",
      ].join("\n"),
    );
    setActivationHandoffCopied(true);
  }

  async function copyQueueAudit() {
    if (!queueAuditFeedback || !navigator.clipboard) return;
    await navigator.clipboard.writeText(queueAuditFeedback.items.map((item) => `${item.label}: ${item.value}`).join("\n"));
    setQueueAuditCopied(true);
  }

  useEffect(() => {
    setQueueAuditCopied(false);
  }, [queueAuditFeedback]);

  useEffect(() => {
    setActivationChecklistCopied(false);
    setActivationHandoffCopied(false);
  }, [activationChecklistKey]);

  return (
    <section
      className="rounded-md border border-rule bg-ice-1 p-3 dark:border-charcoal-1 dark:bg-charcoal-2"
      data-testid="multimedia-job-panel"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Provider jobs</p>
        <LemonTag colour={latestJob?.status === "failed" ? "danger" : latestJob?.status === "queued" ? "sun" : "default"}>
          {latestJob?.status ?? "none"}
        </LemonTag>
      </div>
      <dl className="mt-3 grid grid-cols-1 gap-2" data-testid="multimedia-provider-readiness">
        {readiness.map((item) => (
          <div
            key={item.label}
            className="flex items-center justify-between gap-2 rounded-md border border-rule bg-ice-0 px-2 py-1.5 text-[12px] dark:border-charcoal-1 dark:bg-charcoal-1"
          >
            <dt className="text-shadow-1 dark:text-moonlight">{item.label}</dt>
            <dd className="flex justify-end text-right">
              <LemonTag colour={item.tone}>{item.value}</LemonTag>
            </dd>
          </div>
        ))}
      </dl>
      <div
        className="mt-3 rounded-md border border-rule bg-ice-0 p-2 dark:border-charcoal-1 dark:bg-charcoal-1"
        data-testid="multimedia-live-spend-review"
      >
        <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">Live spend review</p>
        <dl className="mt-2 grid grid-cols-1 gap-1.5">
          {liveSpendReview.map((item) => (
            <div key={item.label} className="flex items-center justify-between gap-2 text-[12px]">
              <dt className="text-shadow-1 dark:text-moonlight">{item.label}</dt>
              <dd className="text-right">
                <LemonTag colour={item.tone ?? "default"}>{item.value}</LemonTag>
              </dd>
            </div>
          ))}
        </dl>
        <LemonButton type="button" size="sm" variant="secondary" className="mt-2" onClick={copyLiveSpendReview}>
          {liveReviewCopied ? "Review copied" : "Copy review"}
        </LemonButton>
      </div>
      <div
        className="mt-3 rounded-md border border-rule bg-ice-0 p-2 dark:border-charcoal-1 dark:bg-charcoal-1"
        data-testid="multimedia-live-activation-checklist"
      >
        <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">Live activation checklist</p>
        <dl className="mt-2 grid grid-cols-1 gap-1.5">
          {activationChecklist.map((item) => (
            <div key={item.label} className="flex items-center justify-between gap-2 text-[12px]">
              <dt className="text-shadow-1 dark:text-moonlight">{item.label}</dt>
              <dd className="text-right">
                <LemonTag colour={item.value.includes("required") || item.value.includes("Unavailable") ? "danger" : "default"}>
                  {item.value}
                </LemonTag>
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 text-[11px] leading-snug text-shadow-1 dark:text-moonlight">
          This checklist is evidence only; provider execution still requires a separate worker activation.
        </p>
        <LemonButton type="button" size="sm" variant="secondary" className="mt-2" onClick={copyActivationChecklist}>
          {activationChecklistCopied ? "Checklist copied" : "Copy checklist"}
        </LemonButton>
        <div className="mt-3 border-t border-rule pt-2 dark:border-charcoal-2" data-testid="multimedia-live-activation-handoff">
          <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">Activation handoff</p>
          <dl className="mt-2 grid grid-cols-1 gap-1.5">
            <div className="flex items-center justify-between gap-2 text-[12px]">
              <dt className="text-shadow-1 dark:text-moonlight">Operator next step</dt>
              <dd className="text-right">
                <LemonTag colour="sun">Review before worker activation</LemonTag>
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2 text-[12px]">
              <dt className="text-shadow-1 dark:text-moonlight">Spend boundary</dt>
              <dd className="text-right">
                <LemonTag colour="default">Queue records intent only</LemonTag>
              </dd>
            </div>
          </dl>
          <LemonButton type="button" size="sm" variant="secondary" className="mt-2" onClick={copyActivationHandoff}>
            {activationHandoffCopied ? "Handoff copied" : "Copy handoff"}
          </LemonButton>
        </div>
      </div>
      {queueAuditFeedback && (
        <div
          className="mt-3 rounded-md border border-sun bg-sun/10 p-2 dark:border-sun/80 dark:bg-sun/10"
          data-testid="multimedia-live-queue-audit"
        >
          <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">Queued live request</p>
          <dl className="mt-2 grid grid-cols-1 gap-1.5">
            {queueAuditFeedback.items.map((item) => (
              <div key={item.label} className="flex items-center justify-between gap-2 text-[12px]">
                <dt className="text-shadow-1 dark:text-moonlight">{item.label}</dt>
                <dd className="text-right">
                  <LemonTag colour={item.tone ?? "default"}>{item.value}</LemonTag>
                </dd>
              </div>
            ))}
          </dl>
          <LemonButton type="button" size="sm" variant="secondary" className="mt-2" onClick={copyQueueAudit}>
            {queueAuditCopied ? "Queued audit copied" : "Copy queued audit"}
          </LemonButton>
        </div>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <label className="col-span-1 text-[12px] text-shadow-1 dark:text-moonlight">
          Budget
          <input
            type="number"
            min={1}
            step={1}
            value={maxBudgetUsd}
            onChange={(event) => onBudgetChange(event.target.value)}
            className="mt-1 h-8 w-full rounded-md border border-rule bg-ice-0 px-2 text-[13px] text-ink outline-none dark:border-charcoal-1 dark:bg-charcoal-1 dark:text-bright"
          />
        </label>
        <label className="col-span-1 flex items-end gap-2 pb-1 text-[12px] text-shadow-1 dark:text-moonlight">
          <input
            type="checkbox"
            checked={operatorAck}
            onChange={(event) => onAckChange(event.target.checked)}
            className="h-4 w-4"
          />
          Spend acknowledged
        </label>
        <LemonButton type="button" size="sm" variant="secondary" disabled={!canQueue || busy} onClick={onQueue}>
          {busy ? "Queueing..." : "Queue live job"}
        </LemonButton>
        <LemonButton type="button" size="sm" variant="secondary" disabled={!jobs.length || busy} onClick={onRefresh}>
          {busy ? "Refreshing..." : "Refresh jobs"}
        </LemonButton>
        <LemonButton type="button" size="sm" variant="primary" disabled={!canRunWorker} onClick={onRunWorker}>
          {busy ? "Working..." : "Run dry-run worker"}
        </LemonButton>
      </div>
      <div className="mt-3 rounded-md border border-rule bg-ice-0 p-2 dark:border-charcoal-1 dark:bg-charcoal-1">
        <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">Manual artifact attach</p>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <label className="col-span-2 text-[12px] text-shadow-1 dark:text-moonlight">
            Artifact job id
            <input
              type="text"
              value={artifactJobId}
              onChange={(event) => onArtifactJobIdChange(event.target.value)}
              className="mt-1 h-8 w-full rounded-md border border-rule bg-ice-1 px-2 font-mono text-[12px] text-ink outline-none dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
            />
          </label>
          <label className="col-span-2 text-[12px] text-shadow-1 dark:text-moonlight">
            Artifact URL
            <input
              type="url"
              value={artifactUri}
              onChange={(event) => onArtifactUriChange(event.target.value)}
              className="mt-1 h-8 w-full rounded-md border border-rule bg-ice-1 px-2 font-mono text-[12px] text-ink outline-none dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
            />
          </label>
          <label className="text-[12px] text-shadow-1 dark:text-moonlight">
            Checksum
            <input
              type="text"
              value={artifactChecksum}
              onChange={(event) => onArtifactChecksumChange(event.target.value)}
              className="mt-1 h-8 w-full rounded-md border border-rule bg-ice-1 px-2 font-mono text-[12px] text-ink outline-none dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
            />
          </label>
          <label className="text-[12px] text-shadow-1 dark:text-moonlight">
            Media type
            <input
              type="text"
              value={artifactMediaType}
              onChange={(event) => onArtifactMediaTypeChange(event.target.value)}
              className="mt-1 h-8 w-full rounded-md border border-rule bg-ice-1 px-2 font-mono text-[12px] text-ink outline-none dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
            />
          </label>
        </div>
        {validationHints.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1" aria-label="Artifact validation hints">
            {validationHints.map((hint) => (
              <span key={hint} className="rounded-md border border-danger bg-danger/10 px-2 py-1 font-mono text-[11px] text-danger">
                {hint}
              </span>
            ))}
          </div>
        )}
        <LemonButton
          type="button"
          size="sm"
          variant="secondary"
          className="mt-2"
          disabled={!canSubmitArtifact || busy}
          onClick={onAttachArtifact}
        >
          {busy ? "Attaching..." : "Attach artifact"}
        </LemonButton>
      </div>
      {recentJobs.length === 0 ? (
        <p className="mt-3 text-[13px] leading-relaxed text-shadow-1 dark:text-moonlight">
          No provider job rows yet.
        </p>
      ) : (
        <ol className="mt-3 space-y-2">
          {recentJobs.map((job) => (
            <li key={job.job_id} className="border-t border-rule pt-2 text-[12px] dark:border-charcoal-1">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-ink dark:text-bright">{job.kind}</span>
                <span className="text-shadow-1 dark:text-moonlight">{job.progress_percent}%</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                <LemonTag>{job.execution_mode}</LemonTag>
                {job.provider_family && <LemonTag colour="muted">{job.provider_family}</LemonTag>}
              </div>
              {job.artifact_uri ? (
                <div className="mt-2 rounded-md border border-rule bg-ice-0 p-2 dark:border-charcoal-1 dark:bg-charcoal-1">
                  <div className="flex flex-wrap items-center gap-1">
                    <LemonTag colour="muted">{job.artifact_media_type ?? "artifact"}</LemonTag>
                    {job.artifact_checksum && (
                      <span className="break-all font-mono text-[11px] text-shadow-1 dark:text-moonlight">
                        {job.artifact_checksum}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 break-all font-mono text-[11px] text-ink dark:text-bright">{job.artifact_uri}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <a
                      className="inline-flex h-7 items-center rounded-hog border-edge border-sun bg-ice-0 px-2.5 font-mono text-[12px] font-semibold text-ink shadow-z1 dark:bg-charcoal-2 dark:text-bright dark:shadow-z1-night"
                      href={job.artifact_uri}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open artifact
                    </a>
                    <a
                      className="inline-flex h-7 items-center rounded-hog border-edge border-sun bg-ice-0 px-2.5 font-mono text-[12px] font-semibold text-ink shadow-z1 dark:bg-charcoal-2 dark:text-bright dark:shadow-z1-night"
                      href={job.artifact_uri}
                      download
                    >
                      Download
                    </a>
                    <LemonButton type="button" size="sm" variant="tertiary" onClick={() => void copyArtifactUri(job)}>
                      {copiedJobId === job.job_id ? "Copied" : "Copy link"}
                    </LemonButton>
                  </div>
                </div>
              ) : (
                <p className="mt-1 font-mono text-[11px] text-shadow-1 dark:text-moonlight">
                  {job.error_code === "artifact_validation_failed"
                    ? "Artifact rejected"
                    : job.status === "queued" || job.status === "running"
                      ? "Artifact pending"
                      : "No artifact attached"}
                </p>
              )}
              {job.error_code === "artifact_validation_failed" && (
                <p className="mt-1 rounded-md border border-danger bg-ice-0 p-2 text-[12px] leading-snug text-danger dark:bg-charcoal-1">
                  Check the artifact URL, sha256 checksum, and media type before attaching this provider output again.
                </p>
              )}
              <p className="mt-1 text-[13px] leading-snug text-ink dark:text-bright">{job.message}</p>
              {job.error_code && (
                <p className="mt-1 font-mono text-[11px] text-danger">{job.error_code}</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
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
