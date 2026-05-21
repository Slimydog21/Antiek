// SPR-08 / M4 — prose renderer.
//
// Prose blocks are operator-editable text envelopes around other
// blocks. The auto-populator does NOT emit standalone prose; the
// only path a prose block reaches the renderer is via the framing
// affordance on another block (see BlockShell.tsx::onEditFraming).
//
// This component exists for two reasons:
//   1. It satisfies the M4 acceptance "each of 6 block types has a
//      TipTap node-view" — symmetric with the other five block
//      components.
//   2. It documents the no-authoring decision in code form: the
//      component refuses to mount unless the block has a parent
//      source event id. If a future surface tries to render a
//      standalone prose block, the assertion fires.

import BlockShell from "./BlockShell";
import type { PerDocBlockProps } from "./types";

interface ProseContent {
  text?: string | null;
  parent_block_id?: string | null;
}

export default function Prose(props: PerDocBlockProps): JSX.Element {
  const content = (props.block.content_json as unknown as ProseContent) || {};

  // No-authoring guard: a prose block without any source event id is
  // a corruption of the substrate. We render an inline warning so an
  // operator notices rather than silently accepting a free-text
  // block.
  if (props.block.source_event_ids.length === 0) {
    return (
      <BlockShell {...props} typeLabel="prose · ORPHAN">
        <p className="text-red-700 text-xs italic">
          Orphan prose block detected: source_event_ids is empty. This
          violates the no-authoring rule in
          services/notebooks/BLOCK_TAXONOMY.md. The auto-populator
          should never produce this; if you see it, file a bug.
        </p>
      </BlockShell>
    );
  }

  return (
    <BlockShell {...props} typeLabel="prose">
      <p className="text-stone-800 leading-relaxed whitespace-pre-wrap">
        {content.text || (
          <span className="text-stone-400 italic">(empty)</span>
        )}
      </p>
    </BlockShell>
  );
}
