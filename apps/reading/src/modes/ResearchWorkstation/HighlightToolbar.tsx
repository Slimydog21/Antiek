import FloatMenu from "../shared/FloatMenu/FloatMenu";
import { useFloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type { FloatMenuSelection, SelectionProvenance } from "../shared/FloatMenu/useFloatMenuSelection";
import { useSettingsResearchTier } from "../../lib/useSettingsResearchTier";
import { launchFloatingDeepResearch } from "../Reading/launchFloatingDeepResearch";
import { toast } from "../../components/lemon/LemonToast";

/**
 * HighlightToolbar — the Research-synthesis HOST for the shared
 * {@link FloatMenu} (Living Roadmap SPR-04 + residual cd).
 *
 * Deep-research primary path opens a floating deep_research_session window
 * (same product path as Reading). Residual (fe): Deep-research full opens
 * view_mode full. ChaseThread remains the degraded fallback via `onChaseThis`
 * when launch fails.
 * Residual (jj): Settings depth-tier → research_tier on launch (parity ji).
 *
 * Why a host adapter and not FloatMenu directly in the page: FloatMenu is
 * host-agnostic (it takes a rect prop, reads no DOM, imports nothing from
 * reading-physics) so Read/Write/Speak can mount it too. The DOM↔graph
 * provenance resolution is per-surface, so each host owns it. Only a range
 * wholly inside one cited claim receives provenance; free prose and cross-claim
 * ranges remain explicitly uncited rather than borrowing a nearby citation.
 */
function boundaryElement(node: Node): Element | null {
  return node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement;
}

export function resolveSynthesisSelectionProvenance(range: Range): SelectionProvenance {
  const start = boundaryElement(range.startContainer)?.closest<HTMLElement>("[data-claim-id]") ?? null;
  const end = boundaryElement(range.endContainer)?.closest<HTMLElement>("[data-claim-id]") ?? null;
  if (!start || start !== end || !start.contains(range.commonAncestorContainer)) return {};
  const claimId = (start.dataset.claimId || "").trim();
  if (!claimId) return {};
  let value: unknown;
  try { value = JSON.parse(start.dataset.citedChunkIds || "[]"); } catch { return {}; }
  if (!Array.isArray(value)) return {};
  const chunkIds = value.filter((id): id is string => typeof id === "string" && id.length > 0 && id.trim() === id);
  if (chunkIds.length === 0 || chunkIds.length !== value.length || new Set(chunkIds).size !== chunkIds.length) return {};
  return { claimId, chunkId: chunkIds[0], chunkIds };
}

function citationEnvelope(selection: FloatMenuSelection, assetId: string) {
  const claimId = selection.provenance.claimId?.trim();
  const chunkIds = selection.provenance.chunkIds;
  return claimId && chunkIds?.length ? {
    source_kind: "synthesis_claim" as const,
    source_asset_id: assetId,
    claim_id: claimId,
    chunk_ids: [...chunkIds],
  } : undefined;
}

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
  const selection = useFloatMenuSelection({ scopeRef, resolveProvenance: resolveSynthesisSelectionProvenance });
  const { researchTier } = useSettingsResearchTier();

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
        const citationProvenance = citationEnvelope(_sel, assetId);
        void (async () => {
          try {
            await launchFloatingDeepResearch({
              asset_id: assetId,
              selection_text: safeSpawnText,
              goal_hint: "Deep-research the highlighted synthesis passage",
              view_mode: viewMode,
              research_tier: researchTier,
              citation_provenance: citationProvenance,
            });
          } catch (reason: unknown) {
            // A cited launch must never degrade into the legacy uncited writer;
            // that would bypass server citation authorization after rejection.
            if (citationProvenance) {
              toast.err(reason instanceof Error ? reason.message : "Cited evidence could not be authorized");
            } else {
              onChaseThis(safeSpawnText);
            }
          }
        })();
      }}
    />
  );
}
