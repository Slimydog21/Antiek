import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { stringAttr } from "./attrHelpers";

import { emitWernerExperience } from "../../../werner/reactionBus";
/**
 * Question-card block — captures an emergent question that the
 * literate analysis surfaced. Substrate-ref by parked_question id;
 * resolves at render time in the full backend.
 *
 * Visual: aurora left bar (the "open thread" colour), inline question
 * text + an "ask later" affordance that will hand off to the
 * Brainstorm parked-questions surface in a follow-up.
 */
function QuestionCardNodeView({ node, deleteNode }: NodeViewProps) {
  const text = (node.attrs.text as string | null) ?? "";
  const parkedId = (node.attrs.parked_question_id as string | null) ?? null;
  return (
    <NodeViewWrapper className="my-3" data-block="question-card">
      <div className="border-l-edge border-aurora bg-aurora/10 dark:bg-aurora/15 pl-3 py-2 pr-4 rounded-r flex items-start gap-2">
        <span className="text-aurora font-mono text-[10px] uppercase tracking-wider shrink-0 mt-1">
          question
        </span>
        <p className="flex-1 font-serif text-[15px] leading-relaxed text-ink dark:text-bright">
          {text || (
            <span className="italic text-ink-mute dark:text-moonlight">
              (empty question)
            </span>
          )}
          {parkedId && (
            <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight ml-2">
              ↳ {parkedId.slice(0, 10)}
            </span>
          )}
        </p>
        {/* S7 WP-7.3 acceptance: each block exposes a "contextual open
            as panel" affordance. For a question card, opening as a
            panel chases the question — opens BrainstormStation routed
            with the question text as the active parked item. */}
        {text && (
          <button
            type="button"
            onClick={() => {
              // Chase the question via the Chase panel (RW S5 flow).
              import("../../../workspace/WorkspaceStore").then(
                ({ useWorkspace }) => {
                  useWorkspace.getState().open(
                    "Chase",
                    { question: text },
                    {
                      mode: "floating",
                      title: "Chase",
                      id: `chase:${text.slice(0, 32)}`,
                    },
                  );
                },
              );
            }}
            className="text-[10px] font-mono text-aurora hover:underline shrink-0 mt-1"
            title="Chase this question in a floating panel"
          >
            chase
          </button>
        )}
        <button
          type="button"
          onClick={() => { emitWernerExperience("note_saved"); deleteNode(); }}
          aria-label="Remove question"
          className="text-[11px] text-ink-mute dark:text-moonlight hover:text-emperor leading-none mt-1"
        >
          ✕
        </button>
      </div>
    </NodeViewWrapper>
  );
}

export const QuestionCardBlock = Node.create({
  name: "questionCard",
  group: "block",
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      parked_question_id: stringAttr("parked_question_id"),
      text: stringAttr("text"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-question-card" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-question-card", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(QuestionCardNodeView);
  },
});

export default QuestionCardBlock;
