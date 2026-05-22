import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import LemonButton from "../../components/lemon/LemonButton";
import PdfViewer from "../../components/PdfViewer";
import type { DocumentLoadedPayload } from "../../generated/types";
import { useEventStream } from "../../hooks/useEventStream";
import { postTypedEvent } from "../../lib/api";
import { sha256Hex } from "../../lib/hash";
import { PanelHost } from "../../workspace/PanelHost";
import type { StarterPanel } from "../../workspace/PanelHost";
import { useWorkspace as useWorkspaceStore } from "../../workspace/WorkspaceStore";
import { recordLastOpenedDocument } from "../../settings/userSettings";
import {
  useUserSettings,
} from "../../settings/useUserSettings";
import {
  BehaviorEventType,
  emitBehaviorEvent,
} from "../../lib/behaviorEvents";
import ReadingModeToggle from "./ReadingModeToggle";
import ShareWithAnnotations from "./ShareWithAnnotations";
import AiCommandPalette from "./AiCommandPalette";

/**
 * Mode B — Document Wrestler (S6 redesign).
 *
 * Pre-S6 the route hand-rolled a 3-column grid (PDF | NotesPanel |
 * CrossDocSidebar) and rendered HeaderBar at the top. After S6 the
 * route renders inside `PanelHost`, which provides the chrome via
 * `AppShell`:
 *
 *   - NotesPanel        docked-left  (trajectory chat panel)
 *   - CrossDocSidebar   docked-right (cross-document bridges)
 *   - PdfViewer         main slot    (the PDF you're wrestling)
 *
 * The "load PDF" upload affordance has moved out of the legacy
 * HeaderBar (now no-op) into the empty-state of the main slot.
 * The investigation id is still stable per browser tab via
 * sessionStorage.
 *
 * pdf.js inside a docked panel uses `usePanelSizeStable` to debounce
 * re-rasterisation so the worker doesn't thrash during resize gestures.
 */
export default function WrestleApp() {
  const params = useParams<{ documentId?: string }>();
  const initialDocumentId = params.documentId ?? null;

  // Read ?page= deep-link from Mode A's chunk-citation modal, plus the
  // SPR-07 ?chunk= follow-up param so cite-jumps from the gutter land
  // on the right chunk (not just the right page). The chunk-level
  // scroll fires inside PdfViewer once the page mounts.
  const { initialPage, initialChunkId } = (() => {
    const usp = new URLSearchParams(window.location.search);
    const rawPage = usp.get("page");
    const rawChunk = usp.get("chunk");
    let page: number | null = null;
    if (rawPage) {
      const n = parseInt(rawPage, 10);
      if (Number.isFinite(n) && n > 0) page = n;
    }
    return {
      initialPage: page,
      initialChunkId: rawChunk && rawChunk.length > 0 ? rawChunk : null,
    };
  })();

  // Once the PDF has rendered (or the route has changed back into a
  // doc already in DOM), scroll the named chunk into view. Polls
  // scrollToChunkWhenReady for up to 3s so the call can fire before
  // PdfViewer's effect has finished mounting.
  useEffect(() => {
    if (!initialChunkId) return;
    // Lazy-import so the chunk-jump pathway doesn't pull scrollToChunk
    // into routes that don't need it.
    void import("./PdfViewer/scrollToChunk").then((mod) => {
      void mod.scrollToChunkWhenReady(initialChunkId);
    });
  }, [initialChunkId]);

  // SPR-04 reading-mode wiring — surfaces the toggle in the main-slot
  // header (below) and emits reading_mode_toggled on every flip.
  const [settings, updateSettings] = useUserSettings();
  const readingMode = settings.reading_mode;
  const onToggleReadingMode = useCallback(() => {
    const from = readingMode;
    const to: "researcher" | "reader" =
      from === "researcher" ? "reader" : "researcher";
    updateSettings({ reading_mode: to });
    try {
      emitBehaviorEvent({
        eventType: BehaviorEventType.READING_MODE_TOGGLED,
        state: { surface: "wrestle" },
        action: { from, to },
      });
    } catch {
      // Emit failure must not block the toggle.
    }
  }, [readingMode, updateSettings]);

  // SPR-04 Cmd+K AI command palette state.
  const [aiPaletteOpen, setAiPaletteOpen] = useState(false);
  const [aiContext, setAiContext] = useState<string | undefined>(undefined);
  const closeAiPalette = useCallback(() => setAiPaletteOpen(false), []);

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

  // Keyboard shortcuts (capture-phase so the global CommandPalette's
  // bubbling-phase Cmd+K handler isn't disturbed). SPR-04 binds Cmd+R
  // (reading mode toggle) + Cmd+K (AI palette); SPR-07 binds Cmd+Shift+J
  // (CrossDocSidebar slide-out, since SPR-07 M5 removed it from default
  // panel starters).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;
      if (!isMod) return;
      const key = e.key.toLowerCase();
      if (key === "r" && !e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        onToggleReadingMode();
      } else if (key === "k" && !e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        const sel = window.getSelection?.()?.toString().trim() ?? "";
        setAiContext(sel.length > 0 ? sel : undefined);
        setAiPaletteOpen((v) => !v);
      } else if (key === "j" && e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        const store = useWorkspaceStore.getState();
        const id = `wrestle:crossdocs:${investigationId}`;
        if (store.panels[id]) {
          store.close(id);
        } else {
          store.open("CrossDocs", { events }, {
            mode: "docked-right",
            title: "Cross-doc",
            id,
          });
        }
      }
    };
    window.addEventListener("keydown", handler, { capture: true });
    return () => {
      window.removeEventListener("keydown", handler, { capture: true });
    };
  }, [onToggleReadingMode, investigationId, events]);

  // SPR-04 M3 — close/open Notes panel on reading-mode flip. PanelHost
  // captures starters on mount only; mid-session flips have to operate
  // imperatively against the workspace store. Reader mode closes Notes
  // (it's not a starter in reader mode anyway, but on a flip from
  // researcher→reader we need to close the already-open panel).
  useEffect(() => {
    if (!documentId) return;
    const store = useWorkspaceStore.getState();
    const notesId = `wrestle:notes:${investigationId}`;
    const isOpen = !!store.panels[notesId];
    if (readingMode === "reader" && isOpen) {
      store.close(notesId);
    } else if (readingMode === "researcher" && !isOpen) {
      store.open("Notes", {
        events,
        status,
        reconnects,
        investigationId,
        documentId,
      }, {
        mode: "docked-left",
        title: "Notes · trajectory",
        id: notesId,
      });
    }
  }, [readingMode, documentId, investigationId, events, status, reconnects]);

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
      "[antiek/wrestle] investigation_id:",
      investigationId,
      "documentId:",
      documentId,
      "initialPage:",
      initialPage,
    );
    // SPR-06 M4 — record last-opened so post-login routing
    // (src/routing/postLogin.ts) lands the user back here on next
    // session. Tracked per-device in localStorage; the substrate
    // has no last_session_at field yet.
    if (documentId) {
      recordLastOpenedDocument(documentId);
    }
  }, [investigationId, documentId, initialPage]);

  // Side panels start only when a document is loaded. Until then the
  // PanelHost shows just the upload-prompting EmptyState in the main slot.
  //
  // SPR-07 M5: CrossDocSidebar is intentionally NOT in default starters
  // — the gutter pills (rendered in-PdfViewer) are the primary cross-doc
  // surface now. CrossDocs is reachable via Cmd+Shift+J (bound below).
  //
  // SPR-04 M3: in 'reader' mode, even the Notes panel is closed to give
  // the cozy reader an undistracted view. The toggle effect below
  // imperatively closes/opens panels when readingMode flips.
  const notesPanelId = `wrestle:notes:${investigationId}`;
  // crossdocsPanelId is generated inside the Cmd+Shift+J handler
  // (above) where it's actually used; no module-level binding needed.
  const starters: StarterPanel[] = documentId && readingMode === "researcher"
    ? ([
        {
          kind: "Notes",
          mode: "docked-left",
          props: {
            events,
            status,
            reconnects,
            investigationId,
            documentId,
          },
          title: "Notes · trajectory",
          id: notesPanelId,
        },
      ] as StarterPanel[])
    : [];

  return (
    <PanelHost starters={starters}>
      {pdfBytes && documentId ? (
        <div
          className="h-full overflow-hidden bg-ice-2 dark:bg-space-2 relative"
          data-testid="wrestle-shell"
          data-reading-mode={readingMode}
        >
          {/* SPR-04 / SPR-10 integration follow-up: a thin in-main-slot
              header carries the reading-mode toggle and the share-with-
              annotations button. These were originally placed in the
              old WrestleApp HeaderBar (removed by sprint-6's PanelHost
              refactor). The proper port is into AppShell's topbar — see
              workspace/README.md — but until that lands, the main-slot
              header keeps the affordances visible. */}
          <div className="absolute top-2 right-2 z-10 flex items-center gap-2 pointer-events-auto">
            <ReadingModeToggle
              mode={readingMode}
              onToggle={onToggleReadingMode}
            />
            <ShareWithAnnotations
              documentId={documentId}
              userId={investigationId}
            />
          </div>
          {/* SPR-04 M4 — Cmd+K AI command palette overlay. Modal +
              dismissable; response renders inside, never in a side
              panel. */}
          <AiCommandPalette
            open={aiPaletteOpen}
            onClose={closeAiPalette}
            initialContext={aiContext}
            investigationId={investigationId}
          />
          <div
            data-testid="wrestle-pdf-wrapper"
            className="h-full overflow-auto"
          >
            <PdfViewer
              pdfBytes={pdfBytes}
              investigationId={investigationId}
              documentId={documentId}
              initialPage={initialPage ?? undefined}
            />
          </div>
        </div>
      ) : (
        <EmptyState
          onFileSelected={onFileSelected}
          loadError={loadError}
          investigationId={investigationId}
        />
      )}
    </PanelHost>
  );
}

function EmptyState({
  onFileSelected,
  loadError,
  investigationId,
}: {
  onFileSelected: (file: File) => void;
  loadError: string | null;
  investigationId: string;
}) {
  return (
    <div className="h-full flex items-center justify-center bg-ice-2 dark:bg-space-2">
      <div className="max-w-md text-center px-6 text-ink dark:text-bright">
        <h1 className="text-2xl font-serif mb-3">Load a PDF to wrestle.</h1>
        <p className="text-sm text-shadow-1 dark:text-moonlight font-serif leading-relaxed mb-5">
          Drop the PDF. Highlight any passage to capture it as a region.
          The trajectory feed will appear as a docked panel; cross-document
          bridges appear on the right.
        </p>
        <label className="inline-flex">
          <LemonButton variant="primary" size="lg" type="button" tabIndex={-1}>
            Choose PDF…
          </LemonButton>
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
        {loadError && (
          <div className="text-xs font-mono text-emperor mt-4">{loadError}</div>
        )}
        <p className="mt-6 text-[11px] font-mono text-ink-mute dark:text-moonlight">
          investigation:{" "}
          <span className="text-ink dark:text-bright">{investigationId}</span>
        </p>
      </div>
    </div>
  );
}
