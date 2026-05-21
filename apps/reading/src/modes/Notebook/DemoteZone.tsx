// SPR-08 / M5 — Demote zone.
//
// The bottom-of-notebook collapsed section holding all demoted
// blocks. Collapsed by default; expanding shows the demoted blocks
// in their original order with a per-block restore button (which
// flips demoted_at back to NULL).
//
// Demoted blocks remain queryable (per SPR-11) — the soft-delete is
// only a UX hide, not a data delete.

import { useState } from "react";

import { renderBlock } from "./blocks";
import type { PerDocBlockProps } from "./blocks/types";
import type { PerDocNotebookBlock } from "../../../api/notebooks/by-doc";

interface Props {
  blocks: PerDocNotebookBlock[];
  onDemote: (blockId: string, demoted: boolean) => void;
  onCiteJump?: PerDocBlockProps["onCiteJump"];
  onVoicePlay?: PerDocBlockProps["onVoicePlay"];
  onEditFraming?: PerDocBlockProps["onEditFraming"];
}

export default function DemoteZone({
  blocks,
  onDemote,
  onCiteJump,
  onVoicePlay,
  onEditFraming,
}: Props): JSX.Element | null {
  const [expanded, setExpanded] = useState<boolean>(false);

  if (blocks.length === 0) return null;

  return (
    <section
      className="mt-12 border-t border-stone-200 pt-6"
      data-testid="demote-zone"
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className={
          "text-xs font-mono text-stone-500 hover:text-stone-900 " +
          "flex items-center gap-2"
        }
        aria-expanded={expanded}
        data-testid="demote-zone-toggle"
      >
        <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
        Demoted ({blocks.length})
      </button>

      {expanded && (
        <div className="mt-4 space-y-4 opacity-70">
          {blocks.map((block) =>
            renderBlock({
              block,
              onCiteJump,
              onVoicePlay,
              onEditFraming,
              onDemote,
            }),
          )}
        </div>
      )}
    </section>
  );
}
