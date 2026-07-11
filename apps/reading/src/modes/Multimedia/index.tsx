import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  approveMultimediaDryRun,
  createMultimediaDraft,
  failedGateIds,
  getMultimediaAsset,
  listMultimediaAssets,
  manualGateIds,
  runMultimediaHardening,
  steerMultimediaAsset,
} from "../../api/multimedia";
import type {
  CreateMultimediaDraftRequest,
  MultimediaAssetRecord,
  MultimediaAssetSummary,
} from "../../api/multimedia";
import { LemonButton, LemonInput, LemonTag, LemonTextarea } from "../../components/lemon";
import { ReconciliationPanel } from "./ReconciliationPanel";

type Mode = "video" | "audio" | "hybrid";
type RouteTier = "cheapest" | "balanced" | "highest_quality";
type RenderState = "pending" | "rendering" | "partial" | "failed" | "over_budget" | "provider_unavailable";
type PlayerView = "video" | "audio";
type PendingCommand = "list" | "create" | "approve" | "steer" | "harden" | "open" | null;

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
  const [selectedRecord, setSelectedRecord] = useState<MultimediaAssetRecord | null>(null);
  const [pendingCommand, setPendingCommand] = useState<PendingCommand>(null);
  const [apiError, setApiError] = useState<string | null>(null);

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
  // Approve posts only asset_id, so it runs against the STORED route_policy.
  // Gate it so the UI never prices one tier while approving another (grok #8).
  const routeTierMatchesRecord = !selectedRecord || selectedRecord.asset.route_policy === tier;
  const canApprove =
    planReady && topic.trim().length > 0 && duration >= 15 && duration <= 45 && routeTierMatchesRecord;
  const canRunAssetCommand = Boolean(selectedRecord) && pendingCommand === null;

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

  async function reopenAsset(assetId: string) {
    setPendingCommand("open");
    try {
      const record = await getMultimediaAsset(assetId);
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
      setApiError("Could not reopen that multimedia asset.");
    } finally {
      setPendingCommand(null);
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
      try {
        await refreshAssetList();
      } catch {
        // best-effort: a failed list refresh must not mask a successful mutation
      }
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
                      onClick={() => reopenAsset(asset.asset_id)}
                      className={
                        "rounded-md border px-3 py-2 text-left " +
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

                <p className="mb-1 font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                  Storyboard — sample preview{selectedRecord ? " (your plan is persisted server-side; narrative beats are not yet rendered)" : ""}
                </p>
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
                  {selectedRecord && !routeTierMatchesRecord && (
                    <span className="text-[12px] text-shadow-1 dark:text-moonlight">
                      Tier differs from the saved plan — create a new draft to apply it.
                    </span>
                  )}
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
            <ReconciliationPanel />
            <StatusPanel
              state={renderState}
              onState={setRenderState}
              onDowngrade={() => {
                setTier("cheapest");
                setRenderState("partial");
              }}
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
