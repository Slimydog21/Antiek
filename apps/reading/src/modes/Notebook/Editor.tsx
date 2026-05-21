import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { useEffect, useRef, useState } from "react";
import type { Editor as TipTapEditor } from "@tiptap/react";

import { ClaimCardBlock } from "./blocks/ClaimCardBlock";
import { CrossDocLinkBlock } from "./blocks/CrossDocLinkBlock";
import { MasterSectionBlock } from "./blocks/MasterSectionBlock";
import { NoteBlock } from "./blocks/NoteBlock";
import { RegionEmbedBlock } from "./blocks/RegionEmbedBlock";
import { SlashMenu } from "./SlashMenu";

/**
 * Antiek notebook editor — TipTap-based block editor with five custom
 * Antiek-specific block kinds plus the StarterKit defaults (prose,
 * heading, lists, blockquote, code, etc.).
 *
 * Persistence in S7-full on main: autosave to localStorage by
 * `notebookId` every 1.5 s of idle. The substrate-side `notebooks`
 * table + REST endpoints are tracked separately (S7-FOLLOWUP.md); when
 * those land, the autosave call swaps from localStorage to API.
 *
 * Slash menu: type `/` at any block start to open the block-insert menu.
 */
type Props = {
  notebookId: string;
  initialContent?: string;
  placeholder?: string;
  className?: string;
};

const LS_PREFIX = "antiek.notebook.";

function lsKey(notebookId: string): string {
  return LS_PREFIX + notebookId;
}

function readStored(notebookId: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(lsKey(notebookId));
  } catch {
    return null;
  }
}

function writeStored(notebookId: string, html: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(lsKey(notebookId), html);
  } catch {
    // ignore quota / privacy-mode
  }
}

export function NotebookEditor({
  notebookId,
  initialContent,
  placeholder,
  className = "",
}: Props) {
  const [slash, setSlash] = useState<{ open: boolean; query: string }>({
    open: false,
    query: "",
  });
  const [saved, setSaved] = useState<"idle" | "saving" | "saved">("idle");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({}),
      Placeholder.configure({
        placeholder: placeholder ?? "Type `/` for blocks, or just start writing.",
      }),
      ClaimCardBlock,
      RegionEmbedBlock,
      NoteBlock,
      CrossDocLinkBlock,
      MasterSectionBlock,
    ],
    content:
      readStored(notebookId) ??
      initialContent ??
      "<p></p>",
    editorProps: {
      attributes: {
        class:
          "tiptap font-serif text-[15px] leading-relaxed text-ink dark:text-bright " +
          "focus:outline-none min-h-[120px]",
      },
    },
    onUpdate: ({ editor: e }) => {
      // detect "/" trigger at the start of an empty block-ish
      const { from } = e.state.selection;
      const before = e.state.doc.textBetween(Math.max(0, from - 1), from);
      const blockText = blockTextAt(e, from);
      if (blockText.startsWith("/")) {
        setSlash({ open: true, query: blockText.slice(1) });
      } else if (slash.open) {
        // typing anywhere else closes the slash menu
        if (!before || before === " ") setSlash({ open: false, query: "" });
      }

      // autosave
      setSaved("saving");
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        writeStored(notebookId, e.getHTML());
        setSaved("saved");
      }, 1500);
    },
  });

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  if (!editor) {
    return (
      <div className="p-4 text-sm text-shadow-1 dark:text-moonlight italic">
        Loading editor…
      </div>
    );
  }

  return (
    <div className={"relative " + className}>
      <EditorContent editor={editor} className="px-6 py-6 max-w-3xl mx-auto" />
      {slash.open && (
        <div className="absolute left-6 bottom-6">
          <SlashMenu
            editor={editor}
            query={slash.query}
            onClose={() => setSlash({ open: false, query: "" })}
          />
        </div>
      )}
      <div className="absolute top-2 right-3 font-mono text-[10.5px] text-ink-mute dark:text-moonlight">
        {saved === "saving"
          ? "saving…"
          : saved === "saved"
            ? "saved to local"
            : ""}
      </div>
    </div>
  );
}

/** Block text at the current cursor's parent (used for slash detection). */
function blockTextAt(editor: TipTapEditor, from: number): string {
  const $pos = editor.state.doc.resolve(from);
  const start = $pos.start();
  return editor.state.doc.textBetween(start, $pos.end(), "\n");
}

export default NotebookEditor;
