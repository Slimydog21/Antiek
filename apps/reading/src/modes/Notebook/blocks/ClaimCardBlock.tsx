import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { stringAttr } from "./attrHelpers";

import LemonCard from "../../../components/lemon/LemonCard";
import { openClaimInspector } from "../../../workspace/actions";

import { emitWernerExperience } from "../../../werner/reactionBus";
/**
 * Claim-card block — references a substrate claim by id. Renders a
 * LemonCard with the claim id + a "Inspect" affordance that opens the
 * ClaimInspector as a floating panel via the workspace.
 *
 * The actual claim payload is fetched at render time (S7-full
 * substrate side); on main we just render the id + the affordance.
 */
function ClaimCardNodeView({ node, deleteNode }: NodeViewProps) {
  const claimId = (node.attrs.claim_id as string | null) ?? "(unset)";
  const investigationId = (node.attrs.investigation_id as string | null) ?? "";
  return (
    <NodeViewWrapper className="my-3" data-block="claim-card">
      <LemonCard
        elevation="z1"
        title={
          <span className="flex items-center justify-between">
            <span>Claim · {claimId.slice(0, 12)}</span>
            <span className="font-sans normal-case tracking-normal flex gap-2">
              <button
                type="button"
                onClick={() => {
                  if (claimId && investigationId) {
                    openClaimInspector({ claimId, investigationId });
                  }
                }}
                className="text-[11px] font-bold text-ink dark:text-sun hover:underline"
              >
                Inspect
              </button>
              <button
                type="button"
                onClick={() => { emitWernerExperience("note_saved"); deleteNode(); }}
                aria-label="Remove block"
                className="text-[11px] text-ink-mute dark:text-moonlight hover:text-emperor"
              >
                ✕
              </button>
            </span>
          </span>
        }
      >
        <p className="font-mono text-[12px] text-ink-soft dark:text-starlight">
          (claim content fetched at render in the full notebook backend;
          this is the substrate-ref shape per architecture_notes §13)
        </p>
      </LemonCard>
    </NodeViewWrapper>
  );
}

export const ClaimCardBlock = Node.create({
  name: "claimCard",
  group: "block",
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      claim_id: stringAttr("claim_id"),
      investigation_id: stringAttr("investigation_id"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-claim-card" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-claim-card", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(ClaimCardNodeView);
  },
});

export default ClaimCardBlock;
