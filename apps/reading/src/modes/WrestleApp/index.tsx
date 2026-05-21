import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import type { DocumentLoadedPayload } from "../../generated/types";
import CrossDocSidebar from "../../components/CrossDocSidebar";
import NotesFeed from "../../components/NotesFeed";
import NotesPanel from "../../components/NotesPanel";
import PdfViewer from "../../components/PdfViewer";
import { useEventStream } from "../../hooks/useEventStream";
import { postTypedEvent } from "../../lib/api";
import {
  BehaviorEventType,
  emitBehaviorEvent,
  type BehaviorEventTypeValue,
} from "../../lib/behaviorEvents";
import { sha256Hex } from "../../lib/hash";
import { useUserSettings } from "../../settings/useUserSettings";
import HeaderBar from "../shared/HeaderBar";
import AiCommandPalette from "./AiCommandPalette";
import ReadingModeToggle from "./ReadingModeToggle";
import "./styles.css";

/**
 * Mode B — Document Wrestler.
 *
 * Three columns (researcher mode) or single-pane PDF (reader mode):
 *   - researcher: PDF (left), NotesPanel (middle), Notes+CrossDoc (right).
 *   - reader: PDF centered, side panels hidden, AI on Cmd+K.
 *
 * SPR-04 layered the reading-mode toggle on top of the original three-
 * column shell. The mode-switch is a CSS-class change on the root
 * element (see styles.css) — PdfViewer is NEVER unmounted across
 * toggles, so scroll position and zoom are preserved mechanically.
 *
 * Cmd+R toggles the mode. Cmd+K opens the AI command palette overlay
 * (a separate surface from the global navigation CommandPalette in
 * src/components/CommandPalette.tsx; we capture the event before the
 * global listener sees it).
 *
 * Behavior unchanged from the pre-SPR-04 implementation otherwise.
 */
export default function WrestleApp() {
  const params = useParams<{ documentId?: string }>();
  const initialDocumentId = params.documentId ?? null;
  const initialPage = (() => {
    const usp = new URLSearchParams(window.location.search);
    const raw = usp.get("page");
    if (!raw) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) && n > 0 ? n : null;
  })();

  const [investigationId] = useState<string>(() => {
    const stored = window.sessionStorage.getItem("antiek.investigation_id");
    if (stored) return stored;
    const fresh = "inv-" + crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    window.sessionStorage.setItem("antiek.investigation_id", fresh);
    return fresh;
  });

  const [pdfBytes, setPdfBytes] = useState<Uint8Array | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(initialDocumentId);
  const [loadError, setLoadError] = useState<string | null>(null);

  const { events, status, reconnects } = useEventStream(investigationId);

  // Reading mode + Cmd+K AI palette state (SPR-04).
  const [settings, updateSettings] = useUserSettings();
  const readingMode = settings.reading_mode;
  const [aiPaletteOpen, setAiPaletteOpen] = useState(false);
  const [aiContext, setAiContext] = useState<string | undefined>(undefined);

  // PdfViewer wrapper ref. After Esc-closing the palette we restore
  // focus here so screen-reader users return to a sensible anchor.
  const pdfWrapperRef = useRef<HTMLDivElement | null>(null);

  // Mount-time behavior event so the substrate sees the operator's
  // mode at session start. {from: null, to: <current>}. We use the
  // empty-deps form so this fires exactly once per WrestleApp mount.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    safeEmit(BehaviorEventType.READING_MODE_TOGGLED, {
      state: { surface: "wrestle" },
      action: { from: null, to: readingMode },
    });
    // We deliberately don't depend on readingMode here — the mount
    // emit is a one-shot. Toggle emits live in handleToggle().
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleToggle = useCallback(() => {
    const from = readingMode;
    const to: "researcher" | "reader" =
      from === "researcher" ? "reader" : "researcher";
    updateSettings({ reading_mode: to });
    safeEmit(BehaviorEventType.READING_MODE_TOGGLED, {
      state: { surface: "wrestle" },
      action: { from, to },
    });
  }, [readingMode, updateSettings]);

  // Cmd+R toggle + Cmd+K AI palette. Bound on window with capture: true
  // so the AI palette pre-empts the global navigation CommandPalette
  // (which uses a bubbling-phase listener — see
  // src/components/CommandPalette.tsx). The capture-phase listener
  // fires first and stops propagation for the AI shortcut.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isMetaOrCtrl = e.metaKey || e.ctrlKey;
      if (!isMetaOrCtrl) return;
      const k = e.key.toLowerCase();
      if (k === "r") {
        // Cmd/Ctrl+R would reload the page; intercept inside WrestleApp.
        e.preventDefault();
        e.stopPropagation();
        handleToggle();
      } else if (k === "k") {
        // Pre-empt the global palette: prevent its handler from seeing
        // the event. The selection captured here travels to the
        // overlay as initialContext.
        e.preventDefault();
        e.stopPropagation();
        const sel = window.getSelection?.()?.toString().trim() ?? "";
        setAiContext(sel.length > 0 ? sel : undefined);
        setAiPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler, { capture: true });
    return () => {
      window.removeEventListener("keydown", handler, { capture: true });
    };
  }, [handleToggle]);

  const closeAiPalette = useCallback(() => {
    setAiPaletteOpen(false);
    // Return focus to a stable anchor — the PdfViewer wrapper.
    setTimeout(() => pdfWrapperRef.current?.focus(), 0);
  }, []);

  const onFileSelected = useCallback(
    async (file: File) => {
      setLoadError(null);
      try {
        const buf = new Uint8Array(await file.arrayBuffer());
        const hash = await sha256Hex(buf);
        const docId = "doc-" + hash.slice(0, 16);

        const payload: DocumentLoadedPayload = {
          action_type: "document.loaded",
          media_type: "pdf",
          content_hash: "sha256:" + hash,
          size_bytes: file.size,
          title: file.name,
          page_count: null,
          source_uri: null,
        };

        await postTypedEvent({
          investigation_id: investigationId,
          document_id: docId,
          payload,
          role: "user_agent",
        });

        setPdfBytes(buf);
        setDocumentId(docId);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setLoadError(msg);
      }
    },
    [investigationId],
  );

  useEffect(() => {
    console.info(
      "[antiek/wrestle] investigation_id:", investigationId,
      "documentId:", documentId, "initialPage:", initialPage,
      "reading_mode:", readingMode,
    );
  }, [investigationId, documentId, initialPage, readingMode]);

  const onCiteJump = useCallback((eventId: string) => {
    const el = document.getElementById(`event-row-${eventId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("ring-2", "ring-amber-400", "shadow");
    window.setTimeout(() => {
      el.classList.remove("ring-2", "ring-amber-400", "shadow");
    }, 1500);
  }, []);

  return (
    <div
      className="wrestle-shell flex flex-col h-screen"
      data-reading-mode={readingMode}
      data-testid="wrestle-shell"
    >
      {/* WrestleApp keeps the legacy HeaderBar call for compatibility
       *  with downstream tests/skills that grep for it (it renders
       *  null since S4 — see modes/shared/HeaderBar.tsx). The visible
       *  header below is the SPR-04 owner of reading-mode controls. */}
      <HeaderBar />
      <header
        className="wrestle-shell__header flex items-center gap-3 px-4 py-2 border-b border-stone-200 bg-white"
        data-testid="wrestle-header"
      >
        <span
          className="wrestle-shell__investigation-chip text-xs font-mono text-stone-500"
        >
          investigation: <span className="text-stone-900">{investigationId}</span>
        </span>
        <label className="cursor-pointer text-xs px-3 py-1.5 bg-stone-900 text-white rounded-md hover:bg-stone-700 transition-colors">
          load PDF
          <input
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFileSelected(f);
            }}
          />
        </label>
        <ReadingModeToggle mode={readingMode} onToggle={handleToggle} />
        {readingMode === "reader" && (
          <span
            className="text-[11px] font-mono text-stone-500"
            data-testid="cmdk-hint"
          >
            ⌘K to ask AI
          </span>
        )}
        {loadError && (
          <div className="text-xs font-mono text-red-700">{loadError}</div>
        )}
      </header>
      <div className="wrestle-shell__columns flex-1 min-h-0">
        <div
          ref={pdfWrapperRef}
          tabIndex={-1}
          className="wrestle-shell__pdf flex flex-col h-full border-r border-stone-200 bg-stone-50 min-h-0"
          data-testid="wrestle-pdf-wrapper"
        >
          <div className="flex-1 overflow-hidden">
            {pdfBytes && documentId ? (
              <PdfViewer
                pdfBytes={pdfBytes}
                investigationId={investigationId}
                documentId={documentId}
                initialPage={initialPage ?? undefined}
              />
            ) : (
              <EmptyState mode={readingMode} />
            )}
          </div>
        </div>
        <div
          className="wrestle-shell__notes-panel"
          data-testid="wrestle-notes-panel"
        >
          <NotesPanel
            events={events}
            status={status}
            reconnects={reconnects}
            investigationId={investigationId}
            documentId={documentId}
          />
        </div>
        <div
          className="wrestle-shell__rail grid grid-rows-[3fr_2fr] h-full overflow-hidden min-h-0"
          data-testid="wrestle-cross-doc-rail"
        >
          <NotesFeed events={events} onCiteJump={onCiteJump} />
          <CrossDocSidebar events={events} />
        </div>
      </div>
      <AiCommandPalette
        open={aiPaletteOpen}
        onClose={closeAiPalette}
        initialContext={aiContext}
        investigationId={investigationId}
      />
    </div>
  );
}

function EmptyState({ mode }: { mode: "researcher" | "reader" }) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-stone-400">
      <p className="text-sm">No document loaded.</p>
      <p className="text-xs mt-1 font-mono">
        Use the "load PDF" button to begin
        {mode === "reader" ? " reading." : " a wrestling session."}
      </p>
    </div>
  );
}

// Defensive wrapper around emitBehaviorEvent. Per SPR-04 M5 acceptance:
// emit failure must be non-fatal. The SPR-01 client is currently a
// no-op-on-the-wire but its assertions (e.g. unknown event types) still
// throw synchronously; this wrapper absorbs anything.
function safeEmit(
  eventType: BehaviorEventTypeValue,
  payload: {
    state: Record<string, unknown>;
    action: Record<string, unknown>;
  },
): void {
  try {
    emitBehaviorEvent({
      eventType,
      state: payload.state,
      action: payload.action,
    });
  } catch (e) {
    // Non-fatal per acceptance criteria. Log once for forensics.
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn("[antiek/wrestle] emit failed (non-fatal):", e);
    }
  }
}
