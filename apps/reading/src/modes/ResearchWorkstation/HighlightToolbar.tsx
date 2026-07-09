import FloatMenu from "../shared/FloatMenu/FloatMenu";
import { useFloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type { FloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import { launchFloatingDeepResearch } from "../Reading/launchFloatingDeepResearch";

/**
 * HighlightToolbar — the Research-synthesis HOST for the shared
 * {@link FloatMenu} (Living Roadmap SPR-04 + residual cd).
 *
 * Deep-research primary path opens a floating deep_research_session window
 * (same product path as Reading). Residual (fe): Deep-research full opens
 * view_mode full. ChaseThread remains the degraded fallback via `onChaseThis`
 * when launch fails.
 *
 * Why a host adapter and not FloatMenu directly in the page: FloatMenu is
 * host-agnostic (it takes a rect prop, reads no DOM, imports nothing from
 * reading-physics) so Read/Write/Speak can mount it too. The DOM↔graph
 * provenance resolution is per-surface, so each host owns it; here a raw
 * synthesis selection has no resolved chunk yet (the synthesis prose isn't a
 * single chunk), so provenance is left empty — the NOTE records null chunk
 * honestly. A future enhancement maps a selection over a cited claim to its
 * chunk; the seam is `resolveProvenance` below.
 */
export default function HighlightToolbar({
  scopeRef,
  onChaseThis,
  investigationId,
}: {
  scopeRef: React.RefObject<HTMLElement | null>;
  /** Degraded chase path — ChaseThread + startInvestigation when float launch fails. */
  onChaseThis: (selectedText: string) => void;
  /** The investigation the synthesis belongs to — the NOTE event bucket +
   * dialogue session. Optional for back-compat with the empty-synthesis case;
   * when absent the menu still positions but actions that need an id no-op. */
  investigationId?: string;
}) {
  const selection = useFloatMenuSelection({ scopeRef });

  return (
    <FloatMenu
      selection={selection}
      investigationId={investigationId ?? "__research__"}
      onDeepResearch={(
        safeSpawnText: string | null,
        _sel: FloatMenuSelection,
        opts?: { viewMode?: "floating" | "full" },
      ) => {
        // §9.0: `safeSpawnText` is null when the selection crosses a withheld
        // region — the chase MUST NOT receive the withheld body.
        if (safeSpawnText === null) return;
        const assetId = (investigationId || "").trim() || "__research__";
        const viewMode = opts?.viewMode === "full" ? "full" : "floating";
        void (async () => {
          try {
            await launchFloatingDeepResearch({
              asset_id: assetId,
              selection_text: safeSpawnText,
              goal_hint: "Deep-research the highlighted synthesis passage",
              view_mode: viewMode,
            });
          } catch {
            onChaseThis(safeSpawnText);
          }
        })();
      }}
    />
  );
}
