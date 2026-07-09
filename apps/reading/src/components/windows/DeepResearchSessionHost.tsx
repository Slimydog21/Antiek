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
 * Residual (ck): PublicationAttachPanel — arxiv/substack attach + hydrate.
 * Residual (cl): SessionFlywheelPanel — complete flywheel + twins/usage.
 * Residual (cp): ResearchProgressPanel autoLoad + autoSeedIfEmpty.
 * Residual (cq): TwinNotesPanel autoLoad.
 * Residual (cr): ResearchProgressPanel pollIntervalMs for multi-minute jobs.
 * Residual (cw): DecisionTreeDriverBadge — active model driver readout.
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
 */

import { useCallback, useEffect, useMemo, useState } from "react";

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
import { syncDeepResearchWindowMode } from "../../workspace/deepResearchWindow";
import { listRecentDeepResearchSpawnIds } from "../../workspace/recentDeepResearchSpawns";
import { useWindows } from "../../workspace/windowsStore";
import { useInWindow } from "./windowHostContext";

export type DeepResearchSessionHostProps = {
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

export default function DeepResearchSessionHost(props: DeepResearchSessionHostProps) {
  // Defensive: window-only page; full-page mount stays readable.
  useInWindow();

  const rawSessionId = props.session_id?.trim() || "";
  const sessionId = rawSessionId || "(missing session_id)";
  const spawnId = props.spawn_id?.trim() || "(missing spawn_id)";
  const parent = props.parent_asset_id?.trim() || "(missing parent)";
  const selection = props.selection_text?.trim() || "(no selection)";
  const status = props.status?.trim() || "unknown";
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
  // Residual (ob/oc): re-read recent ring when windows change or clear recent.
  const [recentTick, setRecentTick] = useState(0);
  const availableSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: props.spawn_id,
        extraSpawnIds: props.available_spawn_ids,
        windows,
        recentSpawnIds: listRecentDeepResearchSpawnIds(),
      }),
    [props.spawn_id, props.available_spawn_ids, windows, recentTick],
  );

  const windowId = props.__windowId?.trim() || "";
  const hostWindow = windowId ? windows[windowId] : undefined;
  const isFull = hostWindow?.mode === "full";

  return (
    <div
      className="flex h-full flex-col gap-4 bg-transparent p-6"
      data-testid="deep-research-session-host"
      data-view-format={viewFormat}
      data-session-id={props.session_id ?? ""}
      data-window-mode={hostWindow?.mode ?? "unknown"}
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
            <DecisionTreeDriverBadge researchTier={researchTier} />
          </div>
          {/* Residual (ce): floating ⇄ full without leaving the host. */}
          {rawSessionId ? (
            <div
              className="flex flex-wrap gap-2"
              data-testid="deep-research-mode-controls"
            >
              <button
                type="button"
                data-testid="deep-research-expand-full"
                disabled={isFull}
                onClick={() => syncDeepResearchWindowMode(rawSessionId, "full")}
                className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono hover:bg-ink/5 disabled:opacity-40 dark:border-bright/30"
              >
                Expand full
              </button>
              <button
                type="button"
                data-testid="deep-research-restore-floating"
                disabled={!isFull}
                onClick={() =>
                  syncDeepResearchWindowMode(rawSessionId, "floating")
                }
                className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono hover:bg-ink/5 disabled:opacity-40 dark:border-bright/30"
              >
                Restore floating
              </button>
            </div>
          ) : null}
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
            <ResearchContextPanel
              key={`ctx-${props.parent_asset_id.trim()}-${contextRefreshKey}`}
              assetId={props.parent_asset_id.trim()}
              spawnId={props.spawn_id?.trim() || null}
              autoLoad
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
              autoLoad
              autoSeedIfEmpty
              researchTier={researchTier}
              pollIntervalMs={mapResearchTierToProgressPollMs(researchTier)}
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
              autoLoad
              autoSeedIfEmpty
              autoPromoteAfterLoad
              onPromoted={onContextNeedsRefresh}
              seedTitle={props.goal?.trim() || props.parent_asset_id.trim()}
              seedBodyText={
                props.selection_text?.trim() || props.goal?.trim() || ""
              }
              researchTier={researchTier}
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
            onCompleted={onContextNeedsRefresh}
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
            onAttached={onContextNeedsRefresh}
            researchTier={researchTier}
          />
        </section>
      ) : null}

      {/* Residual (ci): one-click merge this spawn into reading parent/draft. */}
      {props.spawn_id?.trim() && props.parent_asset_id?.trim() ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-spawn-merge-mount"
          data-view-format="html"
        >
          <SpawnMergePanel
            spawnId={props.spawn_id.trim()}
            parentAssetId={props.parent_asset_id.trim()}
            onMerged={onContextNeedsRefresh}
          />
        </section>
      ) : null}

      {/* Product mount (ah): multi-select collective merge over open spawns. */}
      {availableSpawnIds.length > 0 ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-collective-mount"
          data-view-format="html"
          data-available-spawn-count={String(availableSpawnIds.length)}
        >
          <CollectiveResearchPanel
            availableSpawnIds={availableSpawnIds}
            parentAssetId={props.parent_asset_id?.trim() || null}
            preferredSpawnId={props.spawn_id?.trim() || null}
            onDocMerged={onContextNeedsRefresh}
            onRecentSpawnsCleared={() => setRecentTick((n) => n + 1)}
          />
        </section>
      ) : null}
    </div>
  );
}
