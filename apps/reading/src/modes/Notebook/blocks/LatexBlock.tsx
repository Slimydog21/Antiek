import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { stringAttr } from "./attrHelpers";
import { useState } from "react";

import { emitWernerExperience } from "../../../werner/reactionBus";
/**
 * LaTeX block — math source rendered as monospace (raw) until the
 * operator opts in to a KaTeX render. KaTeX is intentionally NOT
 * bundled; the spec says math blocks are display-only on main +
 * an optional dynamic-import-KaTeX hook lands when math is heavily
 * used in real notebooks. For now, the block is a chunky monospace
 * frame that clearly marks "this is math source".
 */
function LatexNodeView({ node, deleteNode, updateAttributes }: NodeViewProps) {
  const source = (node.attrs.source as string | null) ?? "";
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(source);

  return (
    <NodeViewWrapper className="my-3" data-block="latex">
      <div className="border-edge border-sun bg-ice-1 dark:bg-charcoal-2 rounded-hog shadow-z1 dark:shadow-z1-night relative">
        <div className="px-3 py-2 border-b-edge border-sun flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-wider text-sun-deep dark:text-sun">
            LaTeX · raw source (display-only)
          </span>
          <span className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                if (editing) {
                  updateAttributes({ source: draft });
                }
                setEditing((v) => !v);
              }}
              className="text-[11px] text-ink dark:text-bright hover:underline"
            >
              {editing ? "save" : "edit"}
            </button>
            {/* S7 WP-7.3 acceptance: "open as panel" affordance.
                For LaTeX, open the source in a full-window scratch
                NotebookEditor where the operator gets the slash
                menu + larger writing surface. */}
            {source && (
              <button
                type="button"
                onClick={() => {
                  import("../../../workspace/actions").then(
                    ({ openNotebook }) => {
                      openNotebook({
                        kind: "NotebookEditor",
                        mode: "floating",
                        notebookId: `latex-scratch-${source.slice(0, 16)}`,
                        title: "LaTeX scratch",
                        initialContent: `<antiek-latex source="${source.replace(/"/g, "&quot;")}"></antiek-latex>`,
                      } as Parameters<typeof openNotebook>[0]);
                    },
                  );
                }}
                className="text-[11px] text-ink dark:text-bright hover:underline"
                title="Open in a dedicated editor panel"
              >
                open
              </button>
            )}
            <button
              type="button"
              onClick={() => { emitWernerExperience("note_saved"); deleteNode(); }}
              aria-label="Remove block"
              className="text-[11px] text-ink-mute dark:text-moonlight hover:text-emperor"
            >
              ✕
            </button>
          </span>
        </div>
        {editing ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="w-full min-h-[80px] px-4 py-3 font-mono text-[13px] bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright outline-none resize-y"
            placeholder="\\sum_{i=1}^{n} \\binom{n}{i}…"
          />
        ) : (
          <pre className="px-4 py-3 font-mono text-[13px] text-ink dark:text-bright whitespace-pre-wrap break-words m-0">
            {source || (
              <span className="text-ink-mute dark:text-moonlight italic">
                (empty — click "edit" to add math source)
              </span>
            )}
          </pre>
        )}
      </div>
    </NodeViewWrapper>
  );
}

export const LatexBlock = Node.create({
  name: "latexBlock",
  group: "block",
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      source: stringAttr("source"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-latex" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-latex", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(LatexNodeView);
  },
});

export default LatexBlock;
