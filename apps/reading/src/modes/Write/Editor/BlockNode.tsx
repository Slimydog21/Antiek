import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";

import { stringAttr } from "../../Notebook/blocks/attrHelpers";
import { emitTraceIntent } from "./traceIntent";

import { emitWernerExperience } from "../../../werner/reactionBus";
/**
 * Lego block node (specs/write/ SPR-04 M2).
 *
 * Renders an OutlineBlock (SPR-01) inside the editor: the block's text
 * plus a provenance marker and an inline trace chip. A graph-node block
 * shows its source chip (click → trace-to-source); a user-originated
 * block (operator_note / user_authored / brainstorm) is honestly labeled
 * "yours" and carries NO source chip — no fabricated citation.
 *
 * The node retains its node reference across edits (the attrs persist),
 * which is what keeps trace-to-source intact after the block is dragged
 * in from the repository (SPR-03).
 */
function LegoBlockView({ node, deleteNode }: NodeViewProps) {
  const outlineBlockId = (node.attrs.outline_block_id as string | null) ?? null;
  const nodeId = (node.attrs.node_id as string | null) ?? null;
  const blockKind = (node.attrs.block_kind as string | null) ?? "insight";
  const provRaw = (node.attrs.provenance_kind as string | null) ?? "graph_node";
  const provenanceKind = (
    ["graph_node", "user_authored", "synthesized", "brainstorm"].includes(provRaw)
      ? provRaw
      : "graph_node"
  ) as "graph_node" | "user_authored" | "synthesized" | "brainstorm";
  const sectionId = (node.attrs.section_id as string | null) ?? "";
  const text = (node.attrs.text as string | null) ?? "";
  const userOriginated = provenanceKind !== "graph_node";

  return (
    <NodeViewWrapper className="my-2" data-block="lego">
      <div className="border-l-edge border-ocean bg-ocean/5 pl-3 py-2 pr-4 rounded-r flex items-start gap-2">
        <span className="text-ocean font-mono text-[10px] font-bold uppercase tracking-wider shrink-0 mt-1">
          {blockKind}
        </span>
        <p className="flex-1 font-serif text-[15px] leading-relaxed text-ink dark:text-bright">
          {text || (
            <span className="italic text-ink-mute dark:text-moonlight">(empty block)</span>
          )}
        </p>
        {userOriginated ? (
          <span
            className="shrink-0 mt-1 px-1 rounded font-mono text-[10px] font-semibold bg-moonlight/30 text-ink-mute"
            title="User-originated — traces to the session, not an external source"
          >
            yours
          </span>
        ) : (
          <button
            type="button"
            onClick={() => {
              emitWernerExperience("highlight");
              emitTraceIntent({
                sectionId, outlineBlockId, nodeId, provenanceKind,
                label: nodeId ?? "source",
              });
            }}
            title="Trace to source"
            className="shrink-0 mt-1 px-1 rounded font-mono text-[10px] font-semibold bg-ocean/15 text-ocean hover:bg-ocean/25"
          >
            trace
          </button>
        )}
        <button
          type="button"
          onClick={() => { emitWernerExperience("note_saved"); deleteNode(); }}
          aria-label="Remove block"
          className="text-[11px] text-ink-mute dark:text-moonlight hover:text-emperor leading-none mt-1"
        >
          ✕
        </button>
      </div>
    </NodeViewWrapper>
  );
}

export const LegoBlock = Node.create({
  name: "legoBlock",
  group: "block",
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      outline_block_id: stringAttr("outline_block_id"),
      node_id: stringAttr("node_id"),
      block_kind: stringAttr("block_kind"),
      provenance_kind: stringAttr("provenance_kind"),
      section_id: stringAttr("section_id"),
      text: stringAttr("text"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-block" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-block", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(LegoBlockView);
  },
});

export default LegoBlock;
