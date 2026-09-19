import type { JSONContent } from "@tiptap/core";
import Placeholder from "@tiptap/extension-placeholder";
import { EditorContent, useEditor } from "@tiptap/react";
import type { Editor as TipTapEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useRef, useState } from "react";
import type { MutableRefObject } from "react";

import { toast } from "../../components/lemon/LemonToast";
import {
  ApiError,
  getNotebookContent,
  putNotebookContent,
} from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ChatExchangeBlock } from "./blocks/ChatExchangeBlock";
import { ClaimCardBlock } from "./blocks/ClaimCardBlock";
import { CrossDocLinkBlock } from "./blocks/CrossDocLinkBlock";
import { ImageBlock } from "./blocks/ImageBlock";
import { LatexBlock } from "./blocks/LatexBlock";
import { MasterSectionBlock } from "./blocks/MasterSectionBlock";
import { NoteBlock } from "./blocks/NoteBlock";
import { QuestionCardBlock } from "./blocks/QuestionCardBlock";
import { RegionEmbedBlock } from "./blocks/RegionEmbedBlock";
import {
  hasLegacyNotebookDraft,
  readRecoveryDraft,
  removeRecoveryDraft,
  writeRecoveryDraft,
} from "./recoveryDraft";
import type { NotebookRecoveryDraft } from "./recoveryDraft";
import { SlashMenu } from "./SlashMenu";

type Props = {
  notebookId: string;
  /** Retained for call-site compatibility. Canonical server content always wins. */
  initialContent?: string;
  placeholder?: string;
  className?: string;
  editorRef?: MutableRefObject<TipTapEditor | null>;
  autosaveDelayMs?: number;
};

type SaveState = "idle" | "saving" | "saved" | "offline" | "conflict" | "error";

type Canonical = {
  notebookId: string;
  sessionGeneration: number;
  revision: number;
  contentSha256: string;
  accountScope: string;
  recoveryScope: string;
};

const EMPTY_DOC: JSONContent = { type: "doc", content: [{ type: "paragraph" }] };

function mutationKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `notebook-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function NotebookEditor({
  notebookId,
  placeholder,
  className = "",
  editorRef,
  autosaveDelayMs = 1500,
}: Props) {
  const { sessionGeneration } = useAuth();
  const [slash, setSlash] = useState({ open: false, query: "" });
  const [saved, setSaved] = useState<SaveState>("idle");
  const [hydrated, setHydrated] = useState(false);
  const [recovery, setRecovery] = useState<NotebookRecoveryDraft | null>(null);
  const [legacyDraftPresent, setLegacyDraftPresent] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hydratedRef = useRef(false);
  const canonicalRef = useRef<Canonical | null>(null);
  const editorContextRef = useRef({ notebookId, sessionGeneration });
  const editVersionRef = useRef(0);
  const saveInFlightRef = useRef(false);
  const saveQueuedRef = useRef(false);
  const persistRef = useRef<(editor: TipTapEditor) => Promise<void>>(async () => {});
  editorContextRef.current = { notebookId, sessionGeneration };

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
    content: EMPTY_DOC,
    editorProps: {
      attributes: {
        class:
          "tiptap font-serif text-[15px] leading-relaxed text-ink dark:text-bright " +
          "focus:outline-none min-h-[120px]",
      },
    },
    onUpdate: ({ editor: currentEditor }) => {
      const { from } = currentEditor.state.selection;
      const blockText = blockTextAt(currentEditor, from);
      if (blockText.startsWith("/")) {
        setSlash({ open: true, query: blockText.slice(1) });
      } else {
        setSlash({ open: false, query: "" });
      }

      const canonical = canonicalRef.current;
      const activeContext = editorContextRef.current;
      if (
        !hydratedRef.current ||
        canonical === null ||
        canonical.notebookId !== activeContext.notebookId ||
        canonical.sessionGeneration !== activeContext.sessionGeneration
      ) {
        return;
      }

      editVersionRef.current += 1;

      setSaved("saving");
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        void persistRef.current(currentEditor);
      }, autosaveDelayMs);
    },
  });

  persistRef.current = async (currentEditor: TipTapEditor) => {
        if (saveInFlightRef.current) {
          saveQueuedRef.current = true;
          return;
        }
        saveInFlightRef.current = true;
        const savingVersion = editVersionRef.current;
        const baseline = canonicalRef.current;
        const saveContext = editorContextRef.current;
        if (
          baseline === null ||
          baseline.notebookId !== saveContext.notebookId ||
          baseline.sessionGeneration !== saveContext.sessionGeneration ||
          currentEditor.isDestroyed
        ) {
          saveInFlightRef.current = false;
          return;
        }
        const doc = currentEditor.getJSON();
        try {
          const receipt = await putNotebookContent(saveContext.notebookId, {
            schema_version: 1,
            base_revision: baseline.revision,
            mutation_key: mutationKey(),
            doc,
          });
          const active = canonicalRef.current;
          if (
            active !== baseline ||
            editorContextRef.current.sessionGeneration !== saveContext.sessionGeneration ||
            editorContextRef.current.notebookId !== saveContext.notebookId
          ) {
            return;
          }
          canonicalRef.current = {
            ...baseline,
            revision: receipt.revision,
            contentSha256: receipt.content_sha256,
          };
          removeRecoveryDraft(baseline.recoveryScope);
          setRecovery(null);
          setSaved("saved");
        } catch (error) {
          if (canonicalRef.current !== baseline) return;
          if (error instanceof ApiError) {
            if (error.status === 409) {
              writeRecoveryDraft(baseline.recoveryScope, {
                schema_version: 2,
                account_scope: baseline.accountScope,
                notebook_id: saveContext.notebookId,
                base_revision: baseline.revision,
                base_content_sha256: baseline.contentSha256,
                doc,
                saved_at: new Date().toISOString(),
              });
              setSaved("conflict");
              toast.err("Notebook conflict: the server has a newer revision. Reload before saving again.");
            } else {
              setSaved("error");
              toast.err(`Notebook save failed (HTTP ${error.status}). Your server copy was not changed.`);
            }
            return;
          }
          const draft: NotebookRecoveryDraft = {
            schema_version: 2,
            account_scope: baseline.accountScope,
            notebook_id: saveContext.notebookId,
            base_revision: baseline.revision,
            base_content_sha256: baseline.contentSha256,
            doc,
            saved_at: new Date().toISOString(),
          };
          if (writeRecoveryDraft(baseline.recoveryScope, draft)) {
            setRecovery(draft);
            setSaved("offline");
          } else {
            setSaved("error");
            toast.err("Notebook save failed and the browser could not store a recovery draft.");
          }
        } finally {
          saveInFlightRef.current = false;
          if (editVersionRef.current > savingVersion) saveQueuedRef.current = true;
          if (saveQueuedRef.current && canonicalRef.current === baseline) {
            saveQueuedRef.current = false;
            saveTimer.current = setTimeout(() => {
              void persistRef.current(currentEditor);
            }, 0);
          }
        }
  };

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  useEffect(() => {
    if (!editorRef) return;
    editorRef.current = editor ?? null;
    return () => {
      editorRef.current = null;
    };
  }, [editor, editorRef]);

  useEffect(() => {
    if (!editor) return;
    const abort = new AbortController();
    const request = { notebookId, sessionGeneration };
    hydratedRef.current = false;
    canonicalRef.current = null;
    saveQueuedRef.current = false;
    setHydrated(false);
    setRecovery(null);
    setLegacyDraftPresent(false);
    setSaved("idle");
    editor.commands.setContent(EMPTY_DOC, { emitUpdate: false });

    void getNotebookContent(notebookId, abort.signal)
      .then((content) => {
        if (abort.signal.aborted || editor.isDestroyed) return;
        if (
          request.notebookId !== notebookId ||
          request.sessionGeneration !== sessionGeneration
        ) {
          return;
        }
        editor.commands.setContent(content.doc as JSONContent, { emitUpdate: false });
        canonicalRef.current = {
          notebookId,
          sessionGeneration,
          revision: content.revision,
          contentSha256: content.content_sha256,
          accountScope: content.account_scope,
          recoveryScope: content.recovery_scope,
        };
        setRecovery(
          readRecoveryDraft(content.recovery_scope, content.account_scope, notebookId),
        );
        // Presence-only migration warning: legacy bytes are deliberately never read.
        setLegacyDraftPresent(hasLegacyNotebookDraft(notebookId));
        hydratedRef.current = true;
        setHydrated(true);
        setSaved("saved");
      })
      .catch((error: unknown) => {
        if (abort.signal.aborted) return;
        setSaved(error instanceof ApiError && error.status === 409 ? "conflict" : "error");
      });
    return () => abort.abort();
  }, [editor, notebookId, sessionGeneration]);

  if (!editor) {
    return <div className="p-4 text-sm text-shadow-1 dark:text-moonlight italic">Loading editor…</div>;
  }

  const restoreRecovery = () => {
    if (!recovery || !canonicalRef.current) return;
    editor.commands.setContent(recovery.doc, { emitUpdate: false });
    setRecovery(null);
    setSaved("idle");
  };
  const recoveryMatches =
    recovery !== null &&
    canonicalRef.current !== null &&
    recovery.base_revision === canonicalRef.current.revision &&
    recovery.base_content_sha256 === canonicalRef.current.contentSha256;

  return (
    <div
      className={`relative ${className}`}
      data-notebook-editor
      data-hydrated={hydrated ? "true" : "false"}
    >
      <EditorContent editor={editor} className="px-6 py-6 max-w-3xl mx-auto" />
      {slash.open && (
        <div className="absolute left-6 bottom-6">
          <SlashMenu editor={editor} query={slash.query} onClose={() => setSlash({ open: false, query: "" })} />
        </div>
      )}
      {recovery && (
        <div className="mx-6 mb-3 rounded border border-emperor/30 bg-emperor/5 p-3 text-xs">
          <p>
            {recoveryMatches
              ? "A transport-failure recovery draft matches this server revision."
              : "A recovery draft was based on an older server revision. Review it before saving."}
          </p>
          <button type="button" className="mt-2 underline" onClick={restoreRecovery}>
            Load for review (won't save automatically)
          </button>
        </div>
      )}
      {legacyDraftPresent && (
        <p className="mx-6 mb-3 text-xs text-shadow-1 dark:text-moonlight">
          A legacy browser draft exists. Its unscoped bytes were not read or attached to this account.
        </p>
      )}
      <div
        className={`absolute top-2 right-3 font-mono text-[10.5px] ${
          saved === "conflict" || saved === "error"
            ? "text-emperor"
            : "text-ink-mute dark:text-moonlight"
        }`}
      >
        {saved === "saving"
          ? "saving…"
          : saved === "saved"
            ? "saved"
            : saved === "offline"
              ? "recovery saved locally"
              : saved === "conflict"
                ? "conflict — reload"
                : saved === "error"
                  ? "save unavailable"
                  : ""}
      </div>
    </div>
  );
}

function blockTextAt(editor: TipTapEditor, from: number): string {
  const $pos = editor.state.doc.resolve(from);
  return editor.state.doc.textBetween($pos.start(), $pos.end(), "\n");
}

export default NotebookEditor;
