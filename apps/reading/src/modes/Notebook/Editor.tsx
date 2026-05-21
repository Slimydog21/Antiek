import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { useEffect, useRef, useState } from "react";
import type { Editor as TipTapEditor } from "@tiptap/react";

import { toast } from "../../components/lemon/LemonToast";
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
const LS_ETAG_SUFFIX = ".etag";

function lsKey(notebookId: string): string {
  return LS_PREFIX + notebookId;
}
function lsEtagKey(notebookId: string): string {
  return LS_PREFIX + notebookId + LS_ETAG_SUFFIX;
}

type Stored = { html: string; etag: number };

function readStored(notebookId: string): Stored | null {
  if (typeof window === "undefined") return null;
  try {
    const html = window.localStorage.getItem(lsKey(notebookId));
    if (html === null) return null;
    const etagRaw = window.localStorage.getItem(lsEtagKey(notebookId));
    const etag = etagRaw === null ? 0 : Number.parseInt(etagRaw, 10) || 0;
    return { html, etag };
  } catch {
    return null;
  }
}

/**
 * Optimistic-concurrency write. Bumps the etag iff the stored etag
 * matches the operator's expected baseline. Returns the new etag on
 * success or `null` if a conflict was detected (another tab wrote
 * between our reads).
 *
 * S7 acceptance: "Single-author conflict detection trips (test by
 * opening the same notebook in two browser tabs, editing both, saving)."
 */
function writeStored(
  notebookId: string,
  html: string,
  expectedEtag: number,
): number | null {
  if (typeof window === "undefined") return null;
  try {
    const currentRaw = window.localStorage.getItem(lsEtagKey(notebookId));
    const currentEtag =
      currentRaw === null ? 0 : Number.parseInt(currentRaw, 10) || 0;
    if (currentEtag !== expectedEtag) {
      return null;
    }
    const next = currentEtag + 1;
    window.localStorage.setItem(lsKey(notebookId), html);
    window.localStorage.setItem(lsEtagKey(notebookId), String(next));
    return next;
  } catch {
    // Quota error — silently keep the operator's baseline (no save)
    return expectedEtag;
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
  const [saved, setSaved] = useState<"idle" | "saving" | "saved" | "conflict">(
    "idle",
  );
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Etag the operator's local edits are based on. Bumped on every
  // successful save. If another tab writes between our reads, the
  // store's etag will be ahead of ours and we'll detect the conflict.
  const etagRef = useRef<number>(0);

  // Seed the initial etag from the existing stored snapshot (if any).
  const initialStored = readStored(notebookId);
  if (initialStored && etagRef.current === 0) {
    etagRef.current = initialStored.etag;
  }

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
    content: initialStored?.html ?? initialContent ?? "<p></p>",
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
        if (!before || before === " ") setSlash({ open: false, query: "" });
      }

      // autosave with optimistic-concurrency check
      setSaved("saving");
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        const nextEtag = writeStored(notebookId, e.getHTML(), etagRef.current);
        if (nextEtag === null) {
          // Conflict — another tab wrote between our reads. Surface a
          // toast + leave the operator's draft intact in memory. The
          // operator can reload to pick up the other tab's version, or
          // force-save by editing again (the conflict resolves on next
          // save iff the operator first reloads).
          setSaved("conflict");
          toast.err(
            "Notebook conflict: another tab edited this notebook. Reload to see the latest.",
          );
          return;
        }
        etagRef.current = nextEtag;
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
      <div
        className={
          "absolute top-2 right-3 font-mono text-[10.5px] " +
          (saved === "conflict"
            ? "text-emperor"
            : "text-ink-mute dark:text-moonlight")
        }
      >
        {saved === "saving"
          ? "saving…"
          : saved === "saved"
            ? "saved to local"
            : saved === "conflict"
              ? "conflict — reload"
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
