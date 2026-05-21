// SPR-08 / M4 — Per-block-type shared interfaces.
//
// Each component in this directory takes a ``PerDocBlockProps`` and
// renders the block's content. The block_type field is closed (six
// values; see services/notebooks/blocks.py). Operator-edit happens
// on the prose envelope around each block, not on the source-of-truth
// content_json; ``onEditFraming`` updates the prose only.
//
// TipTap node-view note
// ---------------------
// Each component is shaped so that wrapping it as a TipTap NodeView
// is a one-line conversion: the props it accepts mirror what a TipTap
// node-view component receives (``node.attrs`` ≈ ``block``,
// ``updateAttributes`` ≈ ``onEditFraming``). The "install TipTap +
// register node-views" step is a near-term operator task tracked in
// the SPR-08 handoff — until then the components render as ordinary
// React + Tailwind blocks.

import type { PerDocNotebookBlock } from "../../../../api/notebooks/by-doc";

/** Props every block component accepts. */
export interface PerDocBlockProps {
  block: PerDocNotebookBlock;

  /** Cite-jump invoked when the block's payload references another
   * document or chunk. The cite-jump handler is supplied by the
   * outer PerDocNotebook component; reuses the existing
   * cross-doc-link path (master-spec §13.2 substrate-is-source-of-
   * truth pattern). */
  onCiteJump?: (targetDocumentId: string, targetChunkId?: string | null) => void;

  /** Voice playback invoked when a voice_block's audio control is
   * clicked. SPR-05 ships the inline playback component; until then
   * the handler is a no-op + a console breadcrumb. */
  onVoicePlay?: (voiceNoteId: string) => void;

  /** Operator edit on the prose framing around this block. The
   * substrate's content_json (passage_text, voice_note_id, etc.) is
   * NOT editable here — only the operator's surrounding prose. The
   * no-authoring rule (see services/notebooks/BLOCK_TAXONOMY.md)
   * lets framing change without conjuring a new block. */
  onEditFraming?: (blockId: string, prose: string) => void;

  /** Demote handler. The outer component fires the
   * notebook_block_demoted behavior event AND calls the API to flip
   * demoted_at; the block component just surfaces the button. */
  onDemote?: (blockId: string, demoted: boolean) => void;
}

/** Helper: pull the operator-edited framing out of a block's
 * content_json. Returns "" if absent. */
export function readFraming(block: PerDocNotebookBlock): string {
  const v = (block.content_json as Record<string, unknown>)["operator_framing"];
  return typeof v === "string" ? v : "";
}
