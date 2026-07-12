/**
 * DeepResearchSessionHost — window-native page for deep_research_session kind.
 *
 * Glass-safe, no internal dock (not ResearchWorkstation). Renders identity
 * fields from the composition payload (Python window_compose handoff).
 * Content stance is HTML (`view_format: "html"`); PDF is never required.
 *
 * Props arrive via WindowsLayer: `<Renderer {...win.payload} />`.
 *
 * Residual (ag): mounts ResearchContextPanel when parent_asset_id is present.
 * Residual (ah): mounts CollectiveResearchPanel with availableSpawnIds from
 * current spawn + open deep_research_session windows.
 * Residual (ao): passes parentAssetId so draft/parent document merge is enabled.
 * Residual (ax): mounts ResearchProgressPanel when spawn_id is present.
 * Residual (ba): mounts TwinNotesPanel when parent_asset_id is present.
 * Residual (bx): mounts ResearchLaunchBudgetPanel for goal/selection projection.
 * Residual (ce): expand full / restore floating mode controls.
 * Residual (ci): SpawnMergePanel — this spawn → draft/parent reading asset.
 * Residual (anp): SpawnMergePanel inherits session researchTier for budget
 * foresight + soft-gate depth (parity host DR tier · budget-before-fire anl).
 * Residual (ck): PublicationAttachPanel — arxiv/substack attach + hydrate.
 * Residual (cl): SessionFlywheelPanel — complete flywheel + twins/usage.
 * Residual (cp): ResearchProgressPanel autoLoad + autoSeedIfEmpty.
 * Residual (cq): TwinNotesPanel autoLoad.
 * Residual (cr): ResearchProgressPanel pollIntervalMs for multi-minute jobs.
 * Residual (cw): DecisionTreeDriverBadge — active model driver readout.
 * Residual (pl): DecisionTreeDriverBadge promptText = selection + goal for
 * cost-vs-remaining projection (parity pg–pj host matrix).
 * Residual (dd): TwinNotesPanel autoSeedIfEmpty (offline recursive note-taker).
 * Residual (ea): TwinNotesPanel autoPromoteAfterLoad into research context.
 * Residual (ec): remount ResearchContextPanel after twin promote so context
 * pack reloads recursive notes for prompts.
 * Residual (ed): remount ResearchContextPanel after publication attach.
 * Residual (ee): remount ResearchContextPanel after session flywheel complete.
 * Residual (eh): remount ResearchContextPanel after spawn merge.
 * Residual (ep): remount ResearchContextPanel after collective document merge
 * / written analysis (onDocMerged → onContextNeedsRefresh).
 * Residual (fa): remount TwinNotesPanel on the same contextRefreshKey so
 * recursive note-taker reloads after promote/attach/flywheel/merge (parity ez).
 * Residual (je): prefill researchTier from Settings depth-tier (parity jd/jc).
 * Residual (jk): session payload research_tier wins when present; chrome Row
 * + data-session-research-tier audit (recorded spawn tier, not only Settings).
 * Residual (jo): ResearchProgressPanel poll interval scales by research_tier
 * (fast 2s · deep 4s · wrestle 8s) for multi-minute competitive depth honesty.
 * Residual (ju): poll ms via mapResearchTierToProgressPollMs (shared closed map).
 * Residual (qv): Open Write twin_seed handoff from selection+goal (no invented
 * document_id; parity twin draft path; recursive note-taker seed).
 * Residual (acv): data-write-seed-has-body true when selection_text non-empty
 * (goal-only is meta; selection is body; parity ResearchProgress acp).
 * Residual (aoe): parse research_domains= from goal → domainSubjects on twin +
 * research context (domain-aware chase/search survives into DR session).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  confirmSessionsCollective,
  createCollectiveWrittenAnalysis,
  fetchSessionsCollective,
  launchCollectiveResearch,
  listOwnedEngagementSessions,
  mergeEngagementSessions,
  type CollectiveResponse,
  type ConfirmedCollectiveUnit,
  type SessionLifecycleResponse,
  type SessionMergeResponse,
} from "../../api/engagement";
import { fetchDepthTiers } from "../../api/settings";
import {
  mapDepthTierToResearchTier,
  mapResearchTierToProgressPollMs,
} from "../../lib/researchTier";
import { CollectiveResearchPanel } from "../engagement/CollectiveResearchPanel";
import { DecisionTreeDriverBadge } from "../engagement/DecisionTreeDriverBadge";
import { PublicationAttachPanel } from "../engagement/PublicationAttachPanel";
import { ResearchContextPanel } from "../engagement/ResearchContextPanel";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchTier,
} from "../engagement/ResearchLaunchBudgetPanel";
import { ResearchProgressPanel } from "../engagement/ResearchProgressPanel";
import { SessionFlywheelPanel } from "../engagement/SessionFlywheelPanel";
import { SpawnMergePanel } from "../engagement/SpawnMergePanel";
import { TwinNotesPanel } from "../engagement/TwinNotesPanel";
import { collectDeepResearchSpawnIds } from "../../workspace/collectDeepResearchSpawnIds";
import { syncDeepResearchWindowModeDurably } from "../../workspace/deepResearchWindow";
import { openDeepResearchFromHighlight } from "../../workspace/deepResearchWindow";
import { parseResearchDomainsFromGoal } from "../../workspace/domainSearchDefaults";
import { listRecentDeepResearchSpawnIds } from "../../workspace/recentDeepResearchSpawns";
import { researchPathChoicesReadiness } from "../../workspace/researchPathChoices";
import { buildDeepResearchWriteHref } from "../../workspace/twinWriteSeed";
import { useWindows } from "../../workspace/windowsStore";
import { useInWindow } from "./windowHostContext";
import { openWindow } from "./openWindow";

export type DeepResearchSessionHostProps = {
  owner_id?: string;
  session_id?: string;
  spawn_id?: string;
  investigation_id?: string;
  parent_asset_id?: string;
  selection_text?: string;
  status?: string;
  view_format?: string;
  model_id?: string;
  region_id?: string;
  goal?: string;
  /** Residual (jk): research tier from session open payload when present. */
  research_tier?: string;
  /**
   * Residual (afx): highlight → DR path honesty when opened via FloatMenu /
   * openDeepResearchFromHighlight (parity seamless-highlight-dr).
   */
  seamless_highlight_dr?: boolean | string;
  /** Optional extra spawn ids for collective multi-select (tests / handoff). */
  available_spawn_ids?: string[];
  __windowId?: string;
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
      <dt className="shrink-0 text-xs font-medium uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        {label}
      </dt>
      <dd
        className="min-w-0 break-words text-sm text-ink dark:text-parchment"
        data-field={label.toLowerCase().replace(/\s+/g, "-")}
      >
        {value}
      </dd>
    </div>
  );
}

function newBrowserMergeKey(): string {
  return `browser-merge-${
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2)
  }`;
}

export default function DeepResearchSessionHost(props: DeepResearchSessionHostProps) {
  // Defensive: window-only page; full-page mount stays readable.
  useInWindow();

  const rawSessionId = props.session_id?.trim() || "";
  const sessionId = rawSessionId || "(missing session_id)";
  const spawnId = props.spawn_id?.trim() || "(missing spawn_id)";
  const parent = props.parent_asset_id?.trim() || "(missing parent)";
  const selection = props.selection_text?.trim() || "(no selection)";
  const [status, setStatus] = useState(props.status?.trim() || "unknown");
  const viewFormat = (props.view_format?.trim() || "html").toLowerCase();
  const isHtml = viewFormat === "html";

  /** Residual (je/jk): Settings depth-tier prefill; session payload wins. */
  const sessionTierRaw = (props.research_tier || "").trim().toLowerCase();
  const sessionTier: ResearchLaunchTier | null =
    sessionTierRaw === "fast" ||
    sessionTierRaw === "deep" ||
    sessionTierRaw === "wrestle"
      ? sessionTierRaw
      : null;

  const [researchTier, setResearchTier] = useState<ResearchLaunchTier>(
    sessionTier ?? "deep",
  );
  const [depthPrefill, setDepthPrefill] = useState<
    "pending" | "installed" | "none" | "error" | "session"
  >(sessionTier ? "session" : "pending");

  useEffect(() => {
    // Residual (jk): session open payload is the reserved spawn's tier.
    if (sessionTier) {
      setResearchTier(sessionTier);
      setDepthPrefill("session");
      return;
    }
    let cancelled = false;
    void fetchDepthTiers()
      .then((resp) => {
        if (cancelled) return;
        const mapped = mapDepthTierToResearchTier(resp.active_depth_tier);
        if (mapped) {
          setResearchTier(mapped);
          setDepthPrefill("installed");
        } else {
          setDepthPrefill("none");
        }
      })
      .catch(() => {
        if (!cancelled) setDepthPrefill("error");
      });
    return () => {
      cancelled = true;
    };
  }, [sessionTier]);

  // Residuals (ec/ed/ee/eh/ei): shared remount chokepoint for ResearchContextPanel
  // after twin promote, pub attach, flywheel complete, or spawn merge.
  const [contextRefreshKey, setContextRefreshKey] = useState(0);
  const onContextNeedsRefresh = useCallback(() => {
    setContextRefreshKey((k) => k + 1);
  }, []);

  // Subscribe to open windows so multi-session spawns appear in collective list.
  const windows = useWindows((s) => s.windows);
  const patchWindowPayload = useWindows((s) => s.patchPayload);
  const windowId = props.__windowId?.trim() || "";
  const onSessionCompleted = useCallback(
    (result: { status?: string }) => {
      const completedStatus = result.status?.trim() || "complete";
      setStatus(completedStatus);
      if (windowId) patchWindowPayload(windowId, { status: completedStatus });
      onContextNeedsRefresh();
    },
    [onContextNeedsRefresh, patchWindowPayload, windowId],
  );
  // Residual (ob/oc): re-read recent ring when windows change or clear recent.
  const [recentTick, setRecentTick] = useState(0);
  const recentSpawnIds = useMemo(
    () => listRecentDeepResearchSpawnIds(),
    [windows, recentTick],
  );
  /** Residual (ue): currently open DR windows only (no recent-ring closed ids). */
  const openSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: props.spawn_id,
        extraSpawnIds: props.available_spawn_ids,
        windows,
      }),
    [props.spawn_id, props.available_spawn_ids, windows],
  );
  const availableSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: props.spawn_id,
        extraSpawnIds: props.available_spawn_ids,
        windows,
        recentSpawnIds,
      }),
    [props.spawn_id, props.available_spawn_ids, windows, recentSpawnIds],
  );
  const [ownedSessions, setOwnedSessions] = useState<SessionLifecycleResponse[]>(() =>
    rawSessionId
      ? [
          {
            session_id: rawSessionId,
            spawn_id: props.spawn_id?.trim() || "",
            investigation_id: props.investigation_id?.trim() || "",
            parent_asset_id: props.parent_asset_id?.trim() || "",
            selection_text: props.selection_text?.trim() || "",
            status,
            view_mode: "floating",
            model_id: props.model_id ?? null,
            goal: props.goal?.trim() || "",
            research_tier: props.research_tier ?? null,
            view_format: "html",
            owner_id: props.owner_id?.trim() || "",
            source_references: [],
          },
        ]
      : [],
  );
  const [sessionDiscoveryState, setSessionDiscoveryState] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [sessionDiscoveryError, setSessionDiscoveryError] = useState<string | null>(null);
  const [sessionDiscoveryErrorPhase, setSessionDiscoveryErrorPhase] = useState<
    "initial" | "more" | null
  >(null);
  const [sessionDiscoveryTick, setSessionDiscoveryTick] = useState(0);
  const [nextOwnedSessionCursor, setNextOwnedSessionCursor] = useState<string | null>(null);
  const [sessionDiscoveryMoreBusy, setSessionDiscoveryMoreBusy] = useState(false);
  const [selectedSessionIds, setSelectedSessionIds] = useState<Set<string>>(
    () => new Set(rawSessionId ? [rawSessionId] : []),
  );
  const selectionRevision = useRef(0);
  const [crossAssetApproved, setCrossAssetApproved] = useState(false);

  useEffect(() => {
    if (!rawSessionId) return;
    let cancelled = false;
    setSessionDiscoveryState("loading");
    setSessionDiscoveryError(null);
    setSessionDiscoveryErrorPhase(null);
    void (async () => {
      try {
        const page = await listOwnedEngagementSessions({ limit: 100 });
        if (cancelled) return;
        setOwnedSessions((current) => {
          if (page.sessions.some((session) => session.session_id === rawSessionId)) {
            return page.sessions;
          }
          const currentSession = current.find(
            (session) => session.session_id === rawSessionId,
          );
          return currentSession ? [currentSession, ...page.sessions] : page.sessions;
        });
        setNextOwnedSessionCursor(page.next_cursor);
        const availableIds = new Set(page.sessions.map((session) => session.session_id));
        availableIds.add(rawSessionId);
        setSelectedSessionIds((current) => {
          const retained = new Set([...current].filter((id) => availableIds.has(id)));
          if (availableIds.has(rawSessionId)) retained.add(rawSessionId);
          return retained;
        });
        setSessionDiscoveryState("ready");
      } catch (error) {
        if (cancelled) return;
        setSessionDiscoveryState("error");
        setSessionDiscoveryErrorPhase("initial");
        setSessionDiscoveryError(
          error instanceof Error ? error.message : "Session discovery failed",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [rawSessionId, sessionDiscoveryTick]);

  const loadMoreOwnedSessions = useCallback(async () => {
    if (!nextOwnedSessionCursor || sessionDiscoveryMoreBusy) return;
    const requestCursor = nextOwnedSessionCursor;
    setSessionDiscoveryMoreBusy(true);
    setSessionDiscoveryError(null);
    setSessionDiscoveryErrorPhase(null);
    try {
      const page = await listOwnedEngagementSessions({
        cursor: requestCursor,
        limit: 100,
      });
      if (page.next_cursor === requestCursor) {
        throw new Error("Session discovery cursor repeated");
      }
      setOwnedSessions((current) => {
        const byId = new Map(current.map((session) => [session.session_id, session]));
        for (const session of page.sessions) byId.set(session.session_id, session);
        return [...byId.values()];
      });
      setNextOwnedSessionCursor(page.next_cursor);
    } catch (error) {
      setSessionDiscoveryErrorPhase("more");
      setSessionDiscoveryError(
        error instanceof Error ? error.message : "Session discovery failed",
      );
    } finally {
      setSessionDiscoveryMoreBusy(false);
    }
  }, [nextOwnedSessionCursor, sessionDiscoveryMoreBusy]);

  const liveSessionStatuses = useMemo(() => {
    const statuses = new Map<string, string>();
    const ownerId = props.owner_id?.trim() || "";
    for (const window of Object.values(windows)) {
      if (window.kind !== "deep_research_session") continue;
      if (String(window.payload.owner_id || "").trim() !== ownerId) continue;
      const candidate = String(window.payload.session_id || "").trim();
      const candidateStatus = String(window.payload.status || "").trim();
      if (candidate && candidateStatus) statuses.set(candidate, candidateStatus);
    }
    return statuses;
  }, [props.owner_id, windows]);

  const reconciledOwnedSessions = useMemo(
    () =>
      ownedSessions
        .map((session) => ({
          ...session,
          status:
            session.session_id === rawSessionId
              ? status
              : liveSessionStatuses.get(session.session_id) || session.status,
        })),
    [liveSessionStatuses, ownedSessions, rawSessionId, status],
  );
  const selectedSessions = useMemo(
    () =>
      reconciledOwnedSessions.filter((session) =>
        selectedSessionIds.has(session.session_id),
      ),
    [reconciledOwnedSessions, selectedSessionIds],
  );
  const selectedSessionIdList = useMemo(
    () => selectedSessions.map((session) => session.session_id),
    [selectedSessions],
  );
  const selectedAssets = useMemo(
    () => new Set(selectedSessions.map((session) => session.parent_asset_id)),
    [selectedSessions],
  );
  const selectionCrossesAssets = selectedAssets.size > 1;
  const selectedMergeSessionIds = useMemo(
    () =>
      selectedSessions
        .filter(
          (session) =>
            session.status === "complete" &&
            session.parent_asset_id === props.parent_asset_id?.trim(),
        )
        .map((session) => session.session_id),
    [props.parent_asset_id, selectedSessions],
  );
  const mergeAuthoritySignature = selectedMergeSessionIds.join("\0");
  const mergeAuthoritySignatureRef = useRef(mergeAuthoritySignature);
  mergeAuthoritySignatureRef.current = mergeAuthoritySignature;
  const collectiveAuthoritySignature = JSON.stringify({
    session_ids: selectedSessionIdList,
    allow_cross_asset: selectionCrossesAssets && crossAssetApproved,
  });
  const collectiveAuthoritySignatureRef = useRef(collectiveAuthoritySignature);
  collectiveAuthoritySignatureRef.current = collectiveAuthoritySignature;
  const [sessionMerge, setSessionMerge] = useState<SessionMergeResponse | null>(null);
  const [sessionCollective, setSessionCollective] = useState<
    (CollectiveResponse & { html?: string }) | null
  >(null);
  const [confirmedCollective, setConfirmedCollective] =
    useState<ConfirmedCollectiveUnit | null>(null);
  const collectiveConfirmKey = useRef(newBrowserMergeKey());
  const collectiveResearchKey = useRef(newBrowserMergeKey());
  const collectiveWritingKey = useRef(newBrowserMergeKey());
  const [sessionMergeError, setSessionMergeError] = useState<string | null>(null);
  const [sessionMergeBusy, setSessionMergeBusy] = useState(false);
  const [previewedSessionIds, setPreviewedSessionIds] = useState<string[]>([]);
  const mergeKey = useRef(newBrowserMergeKey());
  const toggleSessionSelection = useCallback((sessionId: string) => {
    selectionRevision.current += 1;
    setSelectedSessionIds((current) => {
      const next = new Set(current);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
    setSessionCollective(null);
    setConfirmedCollective(null);
    setSessionMerge(null);
    setPreviewedSessionIds([]);
    setCrossAssetApproved(false);
  }, []);
  const previewSessionMerge = useCallback(async () => {
    const parentAssetId = props.parent_asset_id?.trim();
    if (!parentAssetId || selectedMergeSessionIds.length === 0) return;
    setSessionMergeBusy(true);
    setSessionMergeError(null);
    const requestRevision = selectionRevision.current;
    const requestAuthority = mergeAuthoritySignature;
    try {
      const preview = await mergeEngagementSessions({
          parent_asset_id: parentAssetId,
          session_ids: selectedMergeSessionIds,
          mode: "draft_combined",
          include_html: true,
        });
      if (
        requestRevision !== selectionRevision.current ||
        requestAuthority !== mergeAuthoritySignatureRef.current
      ) return;
      mergeKey.current = newBrowserMergeKey();
      setSessionMerge(preview);
      setPreviewedSessionIds(selectedMergeSessionIds);
    } catch (error) {
      setSessionMergeError(error instanceof Error ? error.message : "Draft merge failed");
    } finally {
      setSessionMergeBusy(false);
    }
  }, [mergeAuthoritySignature, props.parent_asset_id, selectedMergeSessionIds]);
  const buildSessionCollective = useCallback(async () => {
    setSessionMergeBusy(true);
    setSessionMergeError(null);
    setConfirmedCollective(null);
    const requestRevision = selectionRevision.current;
    const requestAuthority = collectiveAuthoritySignature;
    try {
      const collective = await fetchSessionsCollective({
          session_ids: selectedSessionIdList,
          include_twin_preview: true,
          allow_cross_asset: selectionCrossesAssets && crossAssetApproved,
          include_prompt_block: true,
          include_html: true,
        });
      if (
        requestRevision !== selectionRevision.current ||
        requestAuthority !== collectiveAuthoritySignatureRef.current
      ) return;
      collectiveConfirmKey.current = newBrowserMergeKey();
      collectiveResearchKey.current = newBrowserMergeKey();
      collectiveWritingKey.current = newBrowserMergeKey();
      setSessionCollective(collective);
    } catch (error) {
      setSessionMergeError(
        error instanceof Error ? error.message : "Collective context failed",
      );
    } finally {
      setSessionMergeBusy(false);
    }
  }, [
    collectiveAuthoritySignature,
    crossAssetApproved,
    selectedSessionIdList,
    selectionCrossesAssets,
  ]);
  const confirmSessionCollective = useCallback(async () => {
    if (!sessionCollective?.collective_preview_sha256) return;
    setSessionMergeBusy(true);
    setSessionMergeError(null);
    const requestRevision = selectionRevision.current;
    const requestAuthority = collectiveAuthoritySignature;
    try {
      const confirmed = await confirmSessionsCollective({
        session_ids: selectedSessionIdList,
        include_twin_preview: true,
        allow_cross_asset: selectionCrossesAssets && crossAssetApproved,
        expected_preview_sha256: sessionCollective.collective_preview_sha256,
        idempotency_key: collectiveConfirmKey.current,
      });
      if (
        requestRevision !== selectionRevision.current ||
        requestAuthority !== collectiveAuthoritySignatureRef.current
      ) return;
      setConfirmedCollective(confirmed);
    } catch (error) {
      setConfirmedCollective(null);
      setSessionMergeError(error instanceof Error ? error.message : "Collective confirmation failed");
    } finally {
      setSessionMergeBusy(false);
    }
  }, [
    collectiveAuthoritySignature,
    crossAssetApproved,
    selectedSessionIdList,
    selectionCrossesAssets,
    sessionCollective,
  ]);
  const continueConfirmedCollective = useCallback(async () => {
    if (!confirmedCollective) return;
    const anchor = props.parent_asset_id?.trim() || confirmedCollective.material.unit.asset_ids?.[0];
    if (!anchor) return;
    setSessionMergeBusy(true);
    setSessionMergeError(null);
    try {
      const session = await launchCollectiveResearch(confirmedCollective.collective_unit_id, {
        idempotency_key: collectiveResearchKey.current,
        anchor_asset_id: anchor,
        view_mode: "floating",
        model_id: props.model_id ?? null,
        research_tier: researchTier,
      });
      openDeepResearchFromHighlight({
        session_id: session.session_id,
        spawn_id: session.spawn_id,
        investigation_id: session.investigation_id,
        asset_id: session.parent_asset_id,
        selection_text: session.selection_text,
        owner_id: session.owner_id,
        status: session.status,
        model_id: session.model_id ?? undefined,
        goal: session.goal,
        research_tier: session.research_tier ?? undefined,
      });
    } catch (error) {
      setSessionMergeError(error instanceof Error ? error.message : "Collective research launch failed");
    } finally {
      setSessionMergeBusy(false);
    }
  }, [confirmedCollective, props.model_id, props.parent_asset_id, researchTier]);
  const writeConfirmedCollective = useCallback(async () => {
    if (!confirmedCollective) return;
    setSessionMergeBusy(true);
    setSessionMergeError(null);
    try {
      const draft = await createCollectiveWrittenAnalysis(
        confirmedCollective.collective_unit_id,
        collectiveWritingKey.current,
      );
      openWindow(
        "hosted_html_document",
        {
          document_id: draft.document_id,
          title: "Collective research analysis draft",
          html: draft.html,
          view_format: "html",
          source: "collective_research",
        },
        { id: `win:collective-analysis:${draft.document_id}`, title: "Collective analysis" },
      );
    } catch (error) {
      setSessionMergeError(error instanceof Error ? error.message : "Written analysis failed");
    } finally {
      setSessionMergeBusy(false);
    }
  }, [confirmedCollective]);
  const confirmSessionMerge = useCallback(async () => {
    const parentAssetId = props.parent_asset_id?.trim();
    if (!parentAssetId || !sessionMerge?.parent_revision_sha256) return;
    setSessionMergeBusy(true);
    setSessionMergeError(null);
    try {
      const committed = await mergeEngagementSessions({
        parent_asset_id: parentAssetId,
        session_ids: previewedSessionIds,
        mode: "into_parent",
        confirm_parent_write: true,
        expected_parent_sha256: sessionMerge.parent_revision_sha256,
        idempotency_key: mergeKey.current,
        include_html: true,
      });
      setSessionMerge(committed);
      onContextNeedsRefresh();
    } catch (error) {
      setSessionMergeError(
        error instanceof Error ? error.message : "Confirmed merge failed",
      );
    } finally {
      setSessionMergeBusy(false);
    }
  }, [onContextNeedsRefresh, previewedSessionIds, props.parent_asset_id, sessionMerge]);

  const hostWindow = windowId ? windows[windowId] : undefined;
  const isFull = hostWindow?.mode === "full";
  const [modeSyncError, setModeSyncError] = useState<string | null>(null);
  const persistWindowMode = useCallback(
    async (target: "floating" | "full") => {
      if (!rawSessionId || !hostWindow) return;
      setModeSyncError(null);
      try {
        await syncDeepResearchWindowModeDurably(
          rawSessionId,
          target,
          hostWindow.mode,
        );
      } catch (error) {
        setModeSyncError(
          error instanceof Error ? error.message : "Session view update failed",
        );
      }
    },
    [hostWindow, rawSessionId],
  );

  /** Residual (qv): twin_seed-only Write handoff (selection+goal; no invent doc). */
  const writeHref = useMemo(
    () =>
      buildDeepResearchWriteHref({
        selectionText: props.selection_text,
        goal: props.goal,
        spawnId: props.spawn_id,
        parentAssetId: props.parent_asset_id,
      }),
    [
      props.selection_text,
      props.goal,
      props.spawn_id,
      props.parent_asset_id,
    ],
  );

  const seamlessHighlightDr =
    props.seamless_highlight_dr === true ||
    props.seamless_highlight_dr === "true";

  // Residual (aoe): rehydrate domain subjects from goal_hint research_domains=
  // so twin chase + intelligent search stay domain-aware inside the session.
  const domainSubjects = useMemo(
    () => parseResearchDomainsFromGoal(props.goal),
    [props.goal],
  );

  // Residual (aqz): pure path-choices readiness (shared aqy contract).
  const pathChoices = useMemo(
    () =>
      researchPathChoicesReadiness({
        parentAssetId: props.parent_asset_id,
        selectedCount: String(props.spawn_id || "").trim() ? 1 : 0,
        sessionBound: Boolean(rawSessionId),
      }),
    [props.parent_asset_id, props.spawn_id, rawSessionId],
  );

  return (
    <div
      className="flex h-full flex-col gap-4 bg-transparent p-6"
      data-testid="deep-research-session-host"
      data-view-format={viewFormat}
      data-session-id={props.session_id ?? ""}
      data-window-mode={hostWindow?.mode ?? "unknown"}
      // Residual (afx): highlight → DR window path honesty.
      data-seamless-highlight-dr={String(seamlessHighlightDr)}
      data-research-domains={domainSubjects.join(",") || ""}
    >
      <header className="space-y-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h1 className="font-serif text-lg text-ink dark:text-parchment">
              Deep research session
            </h1>
            <p className="text-xs text-shadow-1 dark:text-moonlight">
              Window-native host · content stance: {isHtml ? "HTML" : viewFormat} · not PDF
            </p>
            <DecisionTreeDriverBadge
              researchTier={researchTier}
              /* Residual (pl): session selection + goal cost foresight. */
              promptText={
                [
                  props.selection_text?.trim() || "",
                  props.goal?.trim() || "",
                ]
                  .filter(Boolean)
                  .join("\n\n") || null
              }
            />
          </div>
          <div className="flex flex-col items-end gap-1">
            {/* Residual (ce): floating ⇄ full without leaving the host. */}
            {rawSessionId ? (
              <div
                className="flex flex-wrap gap-2"
                data-testid="deep-research-mode-controls"
                data-view-format="html"
                data-seamless-highlight-dr={String(seamlessHighlightDr)}
                data-window-mode={hostWindow?.mode ?? "unknown"}
                data-mode-sync-error={modeSyncError ? "true" : "false"}
              >
                <button
                  type="button"
                  data-testid="deep-research-expand-full"
                  data-view-mode-target="full"
                  data-seamless-highlight-dr={String(seamlessHighlightDr)}
                  data-view-format="html"
                  data-float-full-ready={String(pathChoices.float_full_ready)}
                  data-html-first="true"
                  disabled={isFull || !pathChoices.float_full_ready}
                  onClick={() => void persistWindowMode("full")}
                  className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono hover:bg-ink/5 disabled:opacity-40 dark:border-bright/30"
                  title={
                    !pathChoices.float_full_ready
                      ? "Session unbound — cannot expand full without window session"
                      : isFull
                        ? "Already full-screen"
                        : "Open this deep research full-screen (highlight→float stays HTML · not PDF)"
                  }
                >
                  Expand full
                </button>
                <button
                  type="button"
                  data-testid="deep-research-restore-floating"
                  data-view-mode-target="floating"
                  data-seamless-highlight-dr={String(seamlessHighlightDr)}
                  data-view-format="html"
                  data-float-full-ready={String(pathChoices.float_full_ready)}
                  data-html-first="true"
                  disabled={!isFull || !pathChoices.float_full_ready}
                  onClick={() => void persistWindowMode("floating")}
                  className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono hover:bg-ink/5 disabled:opacity-40 dark:border-bright/30"
                  title={
                    !pathChoices.float_full_ready
                      ? "Session unbound — cannot restore floating without window session"
                      : !isFull
                        ? "Already floating"
                        : "Restore floating window (highlight→float path · HTML-first)"
                  }
                >
                  Restore floating
                </button>
                {modeSyncError ? (
                  <p className="w-full text-right text-[10px] text-red-700" role="alert">
                    {modeSyncError}
                  </p>
                ) : null}
              </div>
            ) : null}
            {/* Residual (aqw/aqz): path choices via researchPathChoicesReadiness pure helper. */}
            <p
              className="max-w-xs text-right text-[10px] font-mono opacity-80"
              data-testid="deep-research-path-choices"
              data-view-format="html"
              data-html-first="true"
              data-seamless-highlight-dr={String(seamlessHighlightDr)}
              data-float-full-ready={String(pathChoices.float_full_ready)}
              data-draft-merge-ready={String(pathChoices.draft_merge_ready)}
              data-into-parent-ready={String(pathChoices.into_parent_ready)}
              data-written-analysis-ready={String(
                pathChoices.written_analysis_ready,
              )}
              data-parent-bound={String(pathChoices.parent_bound)}
              data-window-mode={hostWindow?.mode ?? "unknown"}
              data-path-choices-source="researchPathChoicesReadiness"
              role="status"
              title="Highlight→DR product path: float or full, then draft-combined or merge into the reading asset"
            >
              Path: float|full · draft merge · into parent · {pathChoices.summary}
            </p>
            {/* Residual (qv/acv/ael): Open Write twin seed + reading→research→Write path honesty. */}
            {writeHref ? (
              <a
                href={writeHref}
                data-testid="deep-research-open-write"
                data-view-format="html"
                data-has-twin-seed="1"
                // Residual (acv): selection is body; goal-only → has-body false.
                data-write-seed-has-body={String(
                  Boolean(String(props.selection_text || "").trim()),
                )}
                // Residual (ael): parent reading asset provenance for seamless path.
                data-parent-asset-id={
                  String(props.parent_asset_id || "").trim() || ""
                }
                data-seamless-reading-research-write={String(
                  Boolean(String(props.parent_asset_id || "").trim()),
                )}
                data-spawn-id={String(props.spawn_id || "").trim() || ""}
                className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
                title="Open Write with deep research selection+goal as twin_seed (sessionStorage; no invented document_id)"
              >
                Open Write (twin seed)
              </a>
            ) : null}
          </div>
        </div>
      </header>

      <dl className="flex flex-col gap-3">
        <Row label="Session" value={sessionId} />
        <Row label="Spawn" value={spawnId} />
        <Row label="Parent asset" value={parent} />
        <Row label="Status" value={status} />
        {props.investigation_id ? (
          <Row label="Investigation" value={props.investigation_id} />
        ) : null}
        {props.model_id ? <Row label="Model" value={props.model_id} /> : null}
        {props.region_id ? <Row label="Region" value={props.region_id} /> : null}
        {props.goal ? <Row label="Goal" value={props.goal} /> : null}
        {/* Residual (aol): operator-visible research_domains chrome when goal
            rehydrated domain subjects (aoe path honesty). */}
        {domainSubjects.length > 0 ? (
          <div
            data-testid="deep-research-session-domains"
            data-research-domains={domainSubjects.join(",")}
            data-domain-count={String(domainSubjects.length)}
            className="font-mono text-[11px] opacity-90"
            role="status"
          >
            <Row
              label="Research domains"
              value={domainSubjects.join(", ")}
            />
          </div>
        ) : null}
        {/* Residual (jk): always show research tier chrome (default deep). */}
        <div
          data-testid="deep-research-session-tier"
          data-session-research-tier={researchTier}
          data-depth-prefill={depthPrefill}
        >
          <Row label="Research tier" value={researchTier} />
        </div>
      </dl>

      <section className="mt-2 space-y-2 border-t border-black/10 pt-4 dark:border-white/10">
        <h2 className="text-xs font-medium uppercase tracking-wide text-shadow-1 dark:text-moonlight">
          Selection
        </h2>
        <p
          className="whitespace-pre-wrap text-sm leading-relaxed text-ink dark:text-parchment"
          data-testid="deep-research-selection"
        >
          {selection}
        </p>
      </section>

      {/* Residual (bx/je): budget bar + Settings depth prefill for projection. */}
      <section
        className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
        data-testid="deep-research-budget-mount"
        data-view-format="html"
        data-research-tier={researchTier}
        data-depth-prefill={depthPrefill}
      >
        <p
          className="mb-1 text-[10px] font-mono text-shadow-1 dark:text-moonlight"
          data-testid="deep-research-depth-prefill"
          role="status"
        >
          Depth prefill: {depthPrefill}
          {depthPrefill === "installed" || depthPrefill === "session"
            ? ` → ${researchTier}`
            : depthPrefill === "none"
              ? " (default deep)"
              : ""}
        </p>
        <ResearchLaunchBudgetPanel
          promptText={
            (props.goal?.trim() || "") +
            (selection && selection !== "(no selection)"
              ? `\n\n${selection}`
              : "")
          }
          researchTier={researchTier}
          allowTierPick
          onResearchTierChange={setResearchTier}
        />
      </section>

      {/* Product mount: twin + source-ref research context for this session's
          parent asset / spawn. Panel owns fetch/attach; host only passes identity. */}
      {props.parent_asset_id?.trim() ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-research-context-mount"
          data-view-format="html"
        >
          <div
            data-testid="deep-research-context-refresh"
            data-refresh-key={String(contextRefreshKey)}
          >
            {/* Residual (aml): session researchTier prefill for context depth. */}
            <ResearchContextPanel
              key={`ctx-${props.parent_asset_id.trim()}-${contextRefreshKey}`}
              assetId={props.parent_asset_id.trim()}
              spawnId={props.spawn_id?.trim() || null}
              sessionId={rawSessionId}
              autoLoad
              researchTier={researchTier}
              domainSubjects={domainSubjects}
            />
          </div>
        </section>
      ) : null}

      {props.spawn_id?.trim() ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-progress-mount"
          data-view-format="html"
        >
          {/* Residual (jo/ju): poll cadence from shared researchTier map. */}
          <div
            data-testid="deep-research-progress-tier-poll"
            data-research-tier={researchTier}
            data-poll-ms={String(mapResearchTierToProgressPollMs(researchTier))}
          >
            <ResearchProgressPanel
              spawnId={props.spawn_id.trim()}
              sessionId={rawSessionId}
              autoLoad
              autoSeedIfEmpty={!rawSessionId}
              researchTier={researchTier}
              pollIntervalMs={mapResearchTierToProgressPollMs(researchTier)}
              /* Residual (qw): terminal Open Write seed provenance. */
              parentAssetId={props.parent_asset_id}
              goal={props.goal}
            />
          </div>
        </section>
      ) : null}

      {props.parent_asset_id?.trim() ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-twins-mount"
          data-view-format="html"
        >
          {/* Residual (fa): remount twins with context refresh key (parity ez). */}
          <div
            data-testid="deep-research-twins-refresh"
            data-refresh-key={String(contextRefreshKey)}
          >
            <TwinNotesPanel
              key={`twins-${props.parent_asset_id.trim()}-${contextRefreshKey}`}
              assetId={props.parent_asset_id.trim()}
              spawnId={props.spawn_id?.trim() || null}
              sessionId={rawSessionId}
              autoLoad
              autoSeedIfEmpty={!rawSessionId}
              autoPromoteAfterLoad={!rawSessionId}
              onPromoted={onContextNeedsRefresh}
              seedTitle={props.goal?.trim() || props.parent_asset_id.trim()}
              seedBodyText={
                props.selection_text?.trim() || props.goal?.trim() || ""
              }
              researchTier={researchTier}
              domainSubjects={domainSubjects}
            />
          </div>
        </section>
      ) : null}

      {/* Residual (cl): complete session → twins/context + bench usage. */}
      {rawSessionId ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-flywheel-mount"
          data-view-format="html"
        >
          <SessionFlywheelPanel
            sessionId={rawSessionId}
            defaultOutputText={
              props.goal?.trim() ||
              (selection !== "(no selection)" ? selection : "")
            }
            onCompleted={onSessionCompleted}
            researchTier={researchTier}
          />
        </section>
      ) : null}

      {/* Residual (ck): attach knowledge-dense publications mid-session. */}
      {props.spawn_id?.trim() ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-publication-attach-mount"
          data-view-format="html"
        >
          <PublicationAttachPanel
            spawnId={props.spawn_id.trim()}
            sessionId={rawSessionId}
            onAttached={onContextNeedsRefresh}
            researchTier={researchTier}
          />
        </section>
      ) : null}

      {/* Residual (ci/agu): one-click merge this spawn into reading parent/draft. */}
      {props.spawn_id?.trim() && props.parent_asset_id?.trim() && !rawSessionId ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-spawn-merge-mount"
          data-view-format="html"
          data-spawn-id={props.spawn_id.trim()}
          data-parent-asset-id={props.parent_asset_id.trim()}
          data-seamless-spawn-merge="true"
          data-seamless-highlight-dr-merge="true"
          data-research-tier={researchTier}
          data-depth-prefill={depthPrefill}
        >
          <SpawnMergePanel
            spawnId={props.spawn_id.trim()}
            parentAssetId={props.parent_asset_id.trim()}
            onMerged={onContextNeedsRefresh}
            researchTier={researchTier}
          />
        </section>
      ) : null}

      {rawSessionId && props.parent_asset_id?.trim() ? (
        <section
          className="mt-2 space-y-3 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="durable-session-merge-panel"
          data-session-count={String(ownedSessions.length)}
          data-selected-session-count={String(selectedSessionIds.size)}
          data-discovery-state={sessionDiscoveryState}
          data-merge-state={sessionMerge?.merge_receipt_state ?? sessionMerge?.mode ?? "idle"}
        >
          <div className="space-y-2" data-testid="owned-session-selector">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-xs font-semibold">Collect research sessions</h3>
              <span className="text-[10px] font-mono opacity-70">
                {sessionDiscoveryState === "loading"
                  ? "Discovering…"
                  : `${ownedSessions.length} owned · ${selectedSessionIds.size} selected`}
              </span>
            </div>
            {sessionDiscoveryError ? (
              <div className="flex items-center gap-2">
                <p role="alert">{sessionDiscoveryError}</p>
                <button
                  type="button"
                  className="rounded border border-ink/30 px-2 py-1 text-[10px]"
                  onClick={() => {
                    if (sessionDiscoveryErrorPhase === "more") {
                      void loadMoreOwnedSessions();
                    } else {
                      setSessionDiscoveryTick((tick) => tick + 1);
                    }
                  }}
                >
                  Retry discovery
                </button>
              </div>
            ) : null}
            {sessionDiscoveryState === "ready" && ownedSessions.length === 0 ? (
              <p className="text-xs opacity-75">No durable research sessions found.</p>
            ) : null}
            <ul className="max-h-48 space-y-1 overflow-y-auto" aria-label="Owned research sessions">
              {reconciledOwnedSessions.map((session) => {
                const sessionAsset = session.parent_asset_id?.trim() || "unknown asset";
                const mergeable =
                  session.status === "complete" &&
                  sessionAsset === props.parent_asset_id?.trim();
                return (
                  <li key={session.session_id}>
                    <label className="flex cursor-pointer items-start gap-2 rounded border border-ink/15 p-2 text-xs">
                      <input
                        type="checkbox"
                        checked={selectedSessionIds.has(session.session_id)}
                        disabled={sessionDiscoveryState === "loading"}
                        onChange={() => toggleSessionSelection(session.session_id)}
                        aria-label={`Select ${session.goal || session.selection_text || session.session_id}`}
                      />
                      <span className="min-w-0">
                        <span className="block truncate font-medium">
                          {session.goal || session.selection_text || "Untitled research session"}
                        </span>
                        <span className="block font-mono text-[10px] opacity-70">
                          {sessionAsset} · {session.status} · {mergeable ? "mergeable" : "context only"}
                        </span>
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
            {nextOwnedSessionCursor ? (
              <button
                type="button"
                className="rounded border border-ink/30 px-2 py-1 text-[10px]"
                disabled={sessionDiscoveryMoreBusy}
                onClick={() => void loadMoreOwnedSessions()}
              >
                {sessionDiscoveryMoreBusy ? "Loading…" : "Load more sessions"}
              </button>
            ) : null}
            {selectionCrossesAssets ? (
              <label className="flex items-center gap-2 rounded border border-sun/60 bg-sun/10 p-2 text-xs">
                <input
                  type="checkbox"
                  checked={crossAssetApproved}
                  onChange={(event) => {
                    selectionRevision.current += 1;
                    setCrossAssetApproved(event.currentTarget.checked);
                    setSessionCollective(null);
                    setConfirmedCollective(null);
                  }}
                />
                Include selected sessions from {selectedAssets.size} assets in this preview
              </label>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="rounded border border-ink/30 px-3 py-1.5 text-xs disabled:opacity-40"
              disabled={
                sessionMergeBusy ||
                sessionDiscoveryState !== "ready" ||
                selectedSessionIdList.length < 2 ||
                (selectionCrossesAssets && !crossAssetApproved)
              }
              onClick={() => void buildSessionCollective()}
              data-testid="build-session-collective"
            >
              Build collective context
            </button>
            <button
              type="button"
              className="rounded border border-ink/30 px-3 py-1.5 text-xs disabled:opacity-40"
              disabled={
                sessionMergeBusy ||
                !sessionCollective?.collective_preview_sha256 ||
                Boolean(confirmedCollective)
              }
              onClick={() => void confirmSessionCollective()}
              data-testid="confirm-session-collective"
            >
              Save reviewed unit
            </button>
            <button
              type="button"
              className="rounded border border-ink/30 px-3 py-1.5 text-xs disabled:opacity-40"
              disabled={sessionMergeBusy || !confirmedCollective}
              onClick={() => void continueConfirmedCollective()}
              data-testid="continue-session-collective"
            >
              Continue as cohesive research
            </button>
            <button
              type="button"
              className="rounded border border-ink/30 px-3 py-1.5 text-xs disabled:opacity-40"
              disabled={sessionMergeBusy || !confirmedCollective}
              onClick={() => void writeConfirmedCollective()}
              data-testid="write-session-collective"
            >
              Create written analysis
            </button>
            <button
              type="button"
              className="rounded border border-ink/30 px-3 py-1.5 text-xs disabled:opacity-40"
              disabled={sessionMergeBusy || selectedMergeSessionIds.length === 0}
              onClick={() => void previewSessionMerge()}
              data-testid="preview-session-merge"
            >
              Preview {selectedMergeSessionIds.length > 1 ? "collective " : ""}draft
            </button>
            <button
              type="button"
              className="rounded border border-ink bg-ink px-3 py-1.5 text-xs text-white disabled:opacity-40"
              disabled={
                sessionMergeBusy ||
                previewedSessionIds.length === 0 ||
                sessionMerge?.mode !== "draft_combined" ||
                !sessionMerge.parent_revision_sha256
              }
              onClick={() => void confirmSessionMerge()}
              data-testid="confirm-session-merge"
            >
              Confirm merge into reading asset
            </button>
          </div>
          <p className="text-[10px] font-mono opacity-75" data-testid="session-merge-readiness">
            {selectedMergeSessionIds.length} of {selectedSessionIdList.length} selected sessions are complete on this parent and mergeable.
            Collective context is a non-mutating preview; incomplete or cross-parent sessions are context only.
          </p>
          {sessionMergeError ? <p role="alert">{sessionMergeError}</p> : null}
          {sessionMerge?.merge_receipt_id ? (
            <p className="text-[10px] font-mono" data-testid="session-merge-receipt">
              Applied receipt {sessionMerge.merge_receipt_id}
            </p>
          ) : null}
          {confirmedCollective ? (
            <p className="text-[10px] font-mono" data-testid="confirmed-session-collective">
              Confirmed unit {confirmedCollective.collective_unit_id} · source assets unchanged
            </p>
          ) : null}
          {sessionCollective?.html ? (
            <iframe
              title="Collective research context"
              sandbox=""
              srcDoc={sessionCollective.html}
              className="h-64 w-full rounded border border-black/10 bg-white"
              data-testid="session-collective-preview"
            />
          ) : null}
          {sessionMerge?.html && sessionMerge.mode === "draft_combined" ? (
            <iframe
              title="Combined research draft preview"
              sandbox=""
              srcDoc={sessionMerge.html}
              className="h-64 w-full rounded border border-black/10 bg-white"
              data-testid="session-merge-draft-preview"
            />
          ) : null}
        </section>
      ) : null}

      {/* Product mount (ah/ox): multi-select open + recent DR spawns. */}
      {/* Residual (anq): open-vs-recent honesty stamps (parity ResearchThis ou). */}
      {availableSpawnIds.length > 0 && !rawSessionId ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-collective-mount"
          data-view-format="html"
          data-available-spawn-count={String(availableSpawnIds.length)}
          data-recent-count={String(recentSpawnIds.length)}
          data-open-spawn-count={String(openSpawnIds.length)}
          data-seamless-dr-session-collective="true"
        >
          <CollectiveResearchPanel
            availableSpawnIds={availableSpawnIds}
            parentAssetId={props.parent_asset_id?.trim() || null}
            preferredSpawnId={props.spawn_id?.trim() || null}
            recentSpawnIds={recentSpawnIds}
            openSpawnIds={openSpawnIds}
            onDocMerged={onContextNeedsRefresh}
            onRecentSpawnsCleared={() => setRecentTick((n) => n + 1)}
          />
        </section>
      ) : null}
    </div>
  );
}
