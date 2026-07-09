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
 */

import { useMemo } from "react";

import { CollectiveResearchPanel } from "../engagement/CollectiveResearchPanel";
import { ResearchContextPanel } from "../engagement/ResearchContextPanel";
import { ResearchLaunchBudgetPanel } from "../engagement/ResearchLaunchBudgetPanel";
import { ResearchProgressPanel } from "../engagement/ResearchProgressPanel";
import { TwinNotesPanel } from "../engagement/TwinNotesPanel";
import { collectDeepResearchSpawnIds } from "../../workspace/collectDeepResearchSpawnIds";
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

  const sessionId = props.session_id?.trim() || "(missing session_id)";
  const spawnId = props.spawn_id?.trim() || "(missing spawn_id)";
  const parent = props.parent_asset_id?.trim() || "(missing parent)";
  const selection = props.selection_text?.trim() || "(no selection)";
  const status = props.status?.trim() || "unknown";
  const viewFormat = (props.view_format?.trim() || "html").toLowerCase();
  const isHtml = viewFormat === "html";

  // Subscribe to open windows so multi-session spawns appear in collective list.
  const windows = useWindows((s) => s.windows);
  const availableSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: props.spawn_id,
        extraSpawnIds: props.available_spawn_ids,
        windows,
      }),
    [props.spawn_id, props.available_spawn_ids, windows],
  );

  return (
    <div
      className="flex h-full flex-col gap-4 bg-transparent p-6"
      data-testid="deep-research-session-host"
      data-view-format={viewFormat}
      data-session-id={props.session_id ?? ""}
    >
      <header className="space-y-1">
        <h1 className="font-serif text-lg text-ink dark:text-parchment">
          Deep research session
        </h1>
        <p className="text-xs text-shadow-1 dark:text-moonlight">
          Window-native host · content stance: {isHtml ? "HTML" : viewFormat} · not PDF
        </p>
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

      {/* Residual (bx): budget bar + prompt projection for goal/selection. */}
      <section
        className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
        data-testid="deep-research-budget-mount"
        data-view-format="html"
      >
        <ResearchLaunchBudgetPanel
          promptText={
            (props.goal?.trim() || "") +
            (selection && selection !== "(no selection)"
              ? `\n\n${selection}`
              : "")
          }
          researchTier="deep"
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
          <ResearchContextPanel
            assetId={props.parent_asset_id.trim()}
            spawnId={props.spawn_id?.trim() || null}
          />
        </section>
      ) : null}

      {props.spawn_id?.trim() ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-progress-mount"
          data-view-format="html"
        >
          <ResearchProgressPanel spawnId={props.spawn_id.trim()} />
        </section>
      ) : null}

      {props.parent_asset_id?.trim() ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="deep-research-twins-mount"
          data-view-format="html"
        >
          <TwinNotesPanel
            assetId={props.parent_asset_id.trim()}
            spawnId={props.spawn_id?.trim() || null}
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
          />
        </section>
      ) : null}
    </div>
  );
}
