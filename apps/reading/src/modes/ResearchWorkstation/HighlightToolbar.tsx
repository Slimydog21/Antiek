import FloatMenu from "../shared/FloatMenu/FloatMenu";
import { useFloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type { FloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";

/**
 * HighlightToolbar — the Research-synthesis HOST for the shared
 * {@link FloatMenu} (Living Roadmap SPR-04).
 *
 * It WAS the single-action "Follow this" floating toolbar; its selection-listen
 * + positioning is now the shared {@link useFloatMenuSelection} hook and its one
 * action is now the four-action FloatMenu {Note · Dialogue · Search ·
 * Deep-research}. This file is the thin Research-surface adapter: it owns the
 * scope + the host pixel read (via the hook) and wires Deep-research to the
 * EXISTING chase path (`onChaseThis` → ChaseThread + startInvestigation),
 * non-breaking against `ResearchWorkstation/index.tsx`.
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
  /** REUSED chase path — the host opens ChaseThread + startInvestigation. */
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
      onDeepResearch={(safeSpawnText: string | null, _sel: FloatMenuSelection) => {
        // §9.0: `safeSpawnText` is null when the selection crosses a withheld
        // region — the chase MUST NOT receive the withheld body. On the
        // synthesis surface a selection resolves no withheld chunk (provenance
        // empty), so safeSpawnText is the selection; the guard is the shared
        // policy regardless. We refuse rather than spawn on a withheld body.
        if (safeSpawnText === null) return;
        onChaseThis(safeSpawnText);
      }}
    />
  );
}
