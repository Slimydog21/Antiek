import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";

import { stringAttr } from "../../Notebook/blocks/attrHelpers";
import { emitTraceIntent } from "./traceIntent";

import { emitWernerExperience } from "../../../werner/reactionBus";
/**
 * Inline citation chip (specs/write/ SPR-04 M3).
 *
 * Renders `[b: <id>]` after a cited span. Clicking it emits a
 * trace-to-source intent (SPR-07 resolves provenance and opens the shared
 * reader). The chip carries the node/outline-block reference so the trace
 * lands on the real source — provenance is the moat, surfaced inline.
 *
 * It is an inline atom node so it round-trips through HTML losslessly
 * (the AI/generation path emits `<antiek-cite …>`), matching the Notebook
 * block convention.
 */
function CitationView({ node }: NodeViewProps) {
  const nodeId = (node.attrs.node_id as string | null) ?? null;
  const outlineBlockId = (node.attrs.outline_block_id as string | null) ?? null;
  const sectionId = (node.attrs.section_id as string | null) ?? "";
  const provRaw = (node.attrs.provenance_kind as string | null) ?? "graph_node";
  const provenanceKind = (
    ["graph_node", "user_authored", "synthesized", "brainstorm"].includes(provRaw)
      ? provRaw
      : "graph_node"
  ) as "graph_node" | "user_authored" | "synthesized" | "brainstorm";
  const label = (node.attrs.label as string | null) ?? (nodeId ?? "source");
  const userOriginated = provenanceKind !== "graph_node";

  return (
    <NodeViewWrapper as="span" className="inline" data-block="citation">
      <button
        type="button"
        onClick={() =>
          emitWernerExperience("highlight"); emitTraceIntent({ sectionId, outlineBlockId, nodeId, provenanceKind, label })
        }
        title={
          userOriginated
            ? "User-originated — traces to the session, not an external source"
            : `Trace to source: ${label}`
        }
        className={
          "align-baseline mx-0.5 px-1 rounded font-mono text-[10px] font-semibold " +
          (userOriginated
            ? "bg-moonlight/30 text-ink-mute"
            : "bg-ocean/15 text-ocean hover:bg-ocean/25")
        }
      >
        [b: {label}]
      </button>
    </NodeViewWrapper>
  );
}

export const Citation = Node.create({
  name: "citation",
  group: "inline",
  inline: true,
  atom: true,
  addAttributes() {
    return {
      node_id: stringAttr("node_id"),
      outline_block_id: stringAttr("outline_block_id"),
      section_id: stringAttr("section_id"),
      provenance_kind: stringAttr("provenance_kind"),
      label: stringAttr("label"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-cite" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-cite", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(CitationView);
  },
});

export default Citation;
