/**
 * ResearchSessionTwinRail — recursive twin companion on the DR glass-box.
 *
 * Operator vision: reading and research are the same substrate. Every session
 * deserves the same twin notes surface as a book (insights + open questions).
 * Fail-closed autoLoad reuses TwinNotesPanel's live GET /twins/:id client.
 */

import { TwinNotesPanel } from "../shared/twinNotes";

export type ResearchSessionTwinRailProps = {
  /** Durable session id (or investigation id) used as twin parent asset. */
  parentAssetId: string;
};

export function ResearchSessionTwinRail({
  parentAssetId,
}: ResearchSessionTwinRailProps) {
  if (!parentAssetId.trim()) return null;
  return (
    <aside
      data-testid="research-session-twin-rail"
      data-parent-asset-id={parentAssetId}
      className="shrink-0 border-t border-rule pt-3 dark:border-charcoal-1"
      aria-label="Session twin notes"
    >
      <TwinNotesPanel parentAssetId={parentAssetId} autoLoad />
    </aside>
  );
}

export default ResearchSessionTwinRail;
