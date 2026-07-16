import { useEffect, useMemo, useRef, useState } from "react";
import type { Editor } from "@tiptap/react";

import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * Slash command menu — opens when the operator types `/` at the start
 * of an empty block. Keyboard nav: ↑/↓/Enter/Esc.
 */
type SlashEntry = {
  key: string;
  label: string;
  hint: string;
  run: (editor: Editor) => void;
};

const ENTRIES: SlashEntry[] = [
  {
    key: "h1",
    label: "Heading 1",
    hint: "Section title",
    run: (e) =>
      e.chain().focus().deleteRange(rangeOfSlash(e)).setNode("heading", { level: 1 }).run(),
  },
  {
    key: "h2",
    label: "Heading 2",
    hint: "Sub-section",
    run: (e) =>
      e.chain().focus().deleteRange(rangeOfSlash(e)).setNode("heading", { level: 2 }).run(),
  },
  {
    key: "bulletList",
    label: "Bullet list",
    hint: "Unordered items",
    run: (e) =>
      e.chain().focus().deleteRange(rangeOfSlash(e)).toggleBulletList().run(),
  },
  {
    key: "orderedList",
    label: "Numbered list",
    hint: "Ordered items",
    run: (e) =>
      e.chain().focus().deleteRange(rangeOfSlash(e)).toggleOrderedList().run(),
  },
  {
    key: "blockquote",
    label: "Quote",
    hint: "Indented block",
    run: (e) =>
      e.chain().focus().deleteRange(rangeOfSlash(e)).toggleBlockquote().run(),
  },
  {
    key: "code",
    label: "Code block",
    hint: "Fenced code",
    run: (e) =>
      e.chain().focus().deleteRange(rangeOfSlash(e)).toggleCodeBlock().run(),
  },
  {
    key: "note",
    label: "Note",
    hint: "Inline yellow-flag note",
    run: (e) => {
      const r = rangeOfSlash(e);
      e.chain()
        .focus()
        .deleteRange(r)
        .insertContent({ type: "noteBlock", attrs: { text: "New note" } })
        .run();
    },
  },
  {
    key: "claim",
    label: "Claim card",
    hint: "Reference a substrate claim",
    run: (e) => {
      const r = rangeOfSlash(e);
      e.chain()
        .focus()
        .deleteRange(r)
        .insertContent({ type: "claimCard", attrs: { claim_id: "claim-pending" } })
        .run();
    },
  },
  {
    key: "region",
    label: "Region embed",
    hint: "PDF region reference",
    run: (e) => {
      const r = rangeOfSlash(e);
      e.chain()
        .focus()
        .deleteRange(r)
        .insertContent({
          type: "regionEmbed",
          attrs: { document_id: null, page: null, caption: null },
        })
        .run();
    },
  },
  {
    key: "crossDoc",
    label: "Cross-doc link",
    hint: "Bridge between documents",
    run: (e) => {
      const r = rangeOfSlash(e);
      e.chain()
        .focus()
        .deleteRange(r)
        .insertContent({
          type: "crossDocLink",
          attrs: { from_doc: null, to_doc: null, bridge: "New bridge" },
        })
        .run();
    },
  },
  {
    key: "master",
    label: "Synthesis section",
    hint: "Embed a MASTER.md fragment",
    run: (e) => {
      const r = rangeOfSlash(e);
      e.chain()
        .focus()
        .deleteRange(r)
        .insertContent({
          type: "masterSection",
          attrs: { synthesis_id: null, section: "Insights" },
        })
        .run();
    },
  },
  {
    key: "question",
    label: "Question card",
    hint: "Emergent question · aurora bar",
    run: (e) => {
      const r = rangeOfSlash(e);
      e.chain()
        .focus()
        .deleteRange(r)
        .insertContent({
          type: "questionCard",
          attrs: { parked_question_id: null, text: "New question" },
        })
        .run();
    },
  },
  {
    key: "chat",
    label: "Chat exchange",
    hint: "Capture a Q+A from the chat panel",
    run: (e) => {
      const r = rangeOfSlash(e);
      e.chain()
        .focus()
        .deleteRange(r)
        .insertContent({
          type: "chatExchange",
          attrs: {
            exchange_id: null,
            user_text: null,
            assistant_text: null,
          },
        })
        .run();
    },
  },
  {
    key: "image",
    label: "Image",
    hint: "Figure / screenshot with caption",
    run: (e) => {
      const r = rangeOfSlash(e);
      e.chain()
        .focus()
        .deleteRange(r)
        .insertContent({
          type: "imageBlock",
          attrs: { src: null, alt: null, caption: null },
        })
        .run();
    },
  },
  {
    key: "latex",
    label: "LaTeX",
    hint: "Math source · raw / display-only",
    run: (e) => {
      const r = rangeOfSlash(e);
      e.chain()
        .focus()
        .deleteRange(r)
        .insertContent({
          type: "latexBlock",
          attrs: { source: "\\sum_{i=1}^{n} \\binom{n}{i}" },
        })
        .run();
    },
  },
];

/** Compute the range of the leading "/<query>" we want to replace. */
function rangeOfSlash(editor: Editor): { from: number; to: number } {
  const { from } = editor.state.selection;
  // Walk backwards to find the slash on the same block.
  let i = from;
  const $pos = editor.state.doc.resolve(from);
  const parentStart = $pos.start();
  while (i > parentStart) {
    if (editor.state.doc.textBetween(i - 1, i) === "/") {
      return { from: i - 1, to: from };
    }
    i -= 1;
  }
  return { from, to: from };
}

type Props = {
  editor: Editor;
  query: string;
  onClose: () => void;
};

export function SlashMenu({ editor, query, onClose }: Props) {
  const lower = query.toLowerCase();
  const filtered = useMemo(
    () =>
      ENTRIES.filter(
        (e) =>
          !lower ||
          e.label.toLowerCase().includes(lower) ||
          e.key.toLowerCase().includes(lower),
      ),
    [lower],
  );
  const [hoverIdx, setHoverIdx] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setHoverIdx(0);
  }, [filtered.length]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHoverIdx((i) => (i + 1) % Math.max(1, filtered.length));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHoverIdx((i) => (i - 1 + filtered.length) % Math.max(1, filtered.length));
      } else if (e.key === "Enter") {
        const choice = filtered[hoverIdx];
        if (choice) {
          e.preventDefault();
          choice.run(editor);
          onClose();
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filtered, hoverIdx, editor, onClose]);

  if (filtered.length === 0) return null;
  return (
    <div
      ref={containerRef}
      className="absolute z-[120] mt-2 w-[280px] bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z3 dark:shadow-z3-night py-1 max-h-[320px] overflow-y-auto"
      role="listbox"
    >
      {filtered.map((entry, idx) => (
        <button
          type="button"
          key={entry.key}
          role="option"
          aria-selected={idx === hoverIdx}
          onMouseEnter={() => setHoverIdx(idx)}
          onClick={() => {
            // Living-TV: slash insert is a happy craft beat.
            emitWernerExperience("piece_started");
            entry.run(editor);
            onClose();
          }}
          className={
            "w-full text-left px-3 py-2 flex items-baseline justify-between gap-3 " +
            (idx === hoverIdx
              ? "bg-sun/25 dark:bg-sun/15"
              : "hover:bg-sun/15 dark:hover:bg-sun/10")
          }
        >
          <span className="font-sans text-[13px] text-ink dark:text-bright">
            {entry.label}
          </span>
          <span className="font-mono text-[11px] text-ink-mute dark:text-moonlight shrink-0">
            {entry.hint}
          </span>
        </button>
      ))}
    </div>
  );
}

export default SlashMenu;
