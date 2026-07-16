import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { useEffect, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import type { Editor as TipTapEditor } from "@tiptap/react";
import type { JSONContent } from "@tiptap/core";

import { toast } from "../../components/lemon/LemonToast";
import { API_BASE, apiFetch, getNotebookContent } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";
import { ChatExchangeBlock } from "./blocks/ChatExchangeBlock";
import { ClaimCardBlock } from "./blocks/ClaimCardBlock";
import { CrossDocLinkBlock } from "./blocks/CrossDocLinkBlock";
import { ImageBlock } from "./blocks/ImageBlock";
import { LatexBlock } from "./blocks/LatexBlock";
import { MasterSectionBlock } from "./blocks/MasterSectionBlock";
import { NoteBlock } from "./blocks/NoteBlock";
import { QuestionCardBlock } from "./blocks/QuestionCardBlock";
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
  /** Optional handle to the underlying TipTap editor (for a parent toolbar
   * or tests). Populated once the editor mounts, cleared on unmount. */
  editorRef?: MutableRefObject<TipTapEditor | null>;
  /** Idle delay before an edit autosaves. Defaults to 1500 ms; overridable
   * so tests don't depend on wall-clock timing. */
  autosaveDelayMs?: number;
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

/**
 * Whether a ProseMirror/TipTap doc carries real, operator-authored content.
 * Mirrors the server's ``tiptap_codec.is_effectively_empty`` (inverted): a
 * doc of only empty/whitespace paragraphs is what a fresh/unhydrated editor
 * emits and is NOT real content. Used to decide (a) whether to seed the
 * editor from the substrate on mount, and (b) never to overwrite content the
 * operator already typed.
 */
function nodeHasRealContent(node: unknown): boolean {
  if (typeof node !== "object" || node === null) return false;
  const n = node as { type?: unknown; text?: unknown; content?: unknown };
  if (n.type === "text") {
    return typeof n.text === "string" && n.text.trim().length > 0;
  }
  if (typeof n.type === "string" && n.type !== "paragraph" && n.type !== "doc") {
    return true;
  }
  if (Array.isArray(n.content)) {
    return n.content.some(nodeHasRealContent);
  }
  return false;
}

function docHasRealContent(doc: unknown): boolean {
  if (typeof doc !== "object" || doc === null) return false;
  const content = (doc as { content?: unknown }).content;
  if (!Array.isArray(content)) return false;
  return content.some(nodeHasRealContent);
}

export function NotebookEditor({
  notebookId,
  initialContent,
  placeholder,
  className = "",
  editorRef,
  autosaveDelayMs = 1500,
}: Props) {
  const [slash, setSlash] = useState<{ open: boolean; query: string }>({
    open: false,
    query: "",
  });
  const [saved, setSaved] = useState<
    "idle" | "saving" | "saved" | "offline" | "conflict"
  >("idle");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Etag the operator's local edits are based on. Bumped on every
  // successful save. If another tab writes between our reads, the
  // store's etag will be ahead of ours and we'll detect the conflict.
  const etagRef = useRef<number>(0);
  // SPR-01: the autosave timer is GATED on this flag so it can never fire
  // before the editor has hydrated from the substrate. Without the gate, a
  // fresh browser's first edit would PUT the near-empty seed doc and the
  // server's atomic-replace would destroy the persisted blocks (the data-loss
  // bug). ``hydratedRef`` is read synchronously inside ``onUpdate``; the
  // ``hydrated`` state exists only to surface the status + reflect a DOM flag.
  const hydratedRef = useRef<boolean>(false);
  const [hydrated, setHydrated] = useState<boolean>(false);

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
      QuestionCardBlock,
      ChatExchangeBlock,
      ImageBlock,
      LatexBlock,
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

      // SPR-01 gate: never schedule an autosave before the editor has
      // hydrated from the substrate. If the operator (or an AI append)
      // changes the doc during the hydration window, we hold the save —
      // otherwise the first PUT could carry the pre-hydration empty seed
      // and the server's atomic-replace would destroy persisted blocks.
      // The server-side empty-doc floor is the backstop; this is the
      // belt (the common fresh-browser case never even reaches it).
      if (!hydratedRef.current) {
        return;
      }

      // autosave: PUT /notebooks/{id}/content (substrate decomposes
      // TipTap doc → notebook_blocks rows atomically per §4.2). On
      // network failure we fall back to localStorage so the
      // operator's draft never disappears; next online save reconciles.
      setSaved("saving");
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        const doc = e.getJSON();
        try {
          const r = await apiFetch(`${API_BASE}/notebooks/${notebookId}/content`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ doc }),
          });
          if (!r.ok) {
            throw new Error(`HTTP ${r.status}`);
          }
          setSaved("saved");
          // Keep a local mirror so a reload while offline shows the
          // last-known-good state.
          writeStored(notebookId, e.getHTML(), etagRef.current);
          etagRef.current += 1;
        } catch (err) {
          // Offline / network error vs. true etag conflict are
          // semantically different states — the operator sees them
          // differently.
          //
          // Offline (substrate unreachable, 4xx, 5xx): the local etag
          // advances + the draft survives in localStorage. Indicator
          // shows "saved to local" so the operator knows the file
          // isn't lost.
          //
          // Conflict (writeStored returned null because another tab
          // raced ahead of our baseline etag): the local write was
          // refused. Indicator shows "conflict — reload" + a toast.
          const nextEtag = writeStored(notebookId, e.getHTML(), etagRef.current);
          if (nextEtag === null) {
            setSaved("conflict");
            toast.err(
              "Notebook conflict: another tab edited this notebook. Reload to see the latest.",
            );
          } else {
            etagRef.current = nextEtag;
            setSaved("offline");
            if (import.meta.env.DEV) {
              // eslint-disable-next-line no-console
              console.warn(
                "[notebook] substrate unreachable; draft saved locally:",
                err instanceof Error ? err.message : err,
              );
            }
          }
        }
      }, autosaveDelayMs);
    },
  });

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  // Expose the editor instance to a parent/toolbar (and tests) while mounted.
  useEffect(() => {
    if (!editorRef) return;
    editorRef.current = editor ?? null;
    return () => {
      editorRef.current = null;
    };
  }, [editor, editorRef]);

  // SPR-01 hydration — the second defense against the data-loss bug.
  // On mount, fetch the composed TipTap doc from the substrate
  // (GET /notebooks/{id}/content) and seed the editor from it so a fresh
  // browser never starts empty over persisted blocks. localStorage is only
  // a cache/offline mirror now: we only overwrite the editor from the
  // substrate when it is still effectively empty (a fresh mount), so we
  // never clobber cached content or an in-flight local edit. If the fetch
  // fails (offline), we keep whatever we have and still mark hydrated so
  // autosave can resume — the offline localStorage path is preserved.
  useEffect(() => {
    if (!editor) return;
    let cancelled = false;
    hydratedRef.current = false;
    setHydrated(false);
    (async () => {
      try {
        const { doc } = await getNotebookContent(notebookId);
        if (cancelled || editor.isDestroyed) return;
        if (docHasRealContent(doc) && !docHasRealContent(editor.getJSON())) {
          // emitUpdate:false — hydration must not itself trigger an autosave.
          editor.commands.setContent(doc as JSONContent, {
            emitUpdate: false,
          });
          setSaved("saved");
        }
      } catch {
        // Offline / no substrate doc: keep the cached (localStorage) or
        // empty content. Hydration still "completes" so the operator can
        // keep editing offline; the draft survives in localStorage.
      } finally {
        if (!cancelled) {
          hydratedRef.current = true;
          setHydrated(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [editor, notebookId]);

  // S8 WP-8.4 follow-through — when the AI tool-call protocol's
  // `add_to_notebook` action writes to our localStorage key, it
  // dispatches a same-window custom event. We listen here + reload
  // the editor's content. Cross-tab writes already arrive through
  // the browser's standard `storage` event, which we also handle.
  useEffect(() => {
    const reloadFromStorage = () => {
      if (!editor) return;
      const stored = readStored(notebookId);
      if (!stored) return;
      // Only swap if the etag advanced past our baseline — avoids
      // clobbering an in-flight local edit on every dispatched action.
      if (stored.etag <= etagRef.current) return;
      editor.commands.setContent(stored.html);
      etagRef.current = stored.etag;
      setSaved("saved");
    };
    const onCustom = (e: Event) => {
      const ce = e as CustomEvent<{ notebookId: string }>;
      if (ce.detail?.notebookId !== notebookId) return;
      reloadFromStorage();
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key !== "antiek.notebook." + notebookId) return;
      reloadFromStorage();
    };
    window.addEventListener("antiek:notebook:appended", onCustom);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("antiek:notebook:appended", onCustom);
      window.removeEventListener("storage", onStorage);
    };
  }, [editor, notebookId]);

  if (!editor) {
    return (
      <div className="p-4 text-sm text-shadow-1 dark:text-moonlight italic">
        Loading editor…
      </div>
    );
  }

  return (
    <div
      className={"relative " + className}
      data-notebook-editor
      data-hydrated={hydrated ? "true" : "false"}
    >
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
            ? "saved"
            : saved === "offline"
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
