// SPR-05 / M1 — Highlight → voice-note affordance.
//
// Floating selection toolbar PLUS a global Cmd+Shift+V (Ctrl+Shift+V
// on non-mac) keyboard shortcut. Listens to text-selection events
// scoped to a PdfViewer container; positions the toolbar above the
// selection rectangle.
//
// Differences from the existing ResearchWorkstation/HighlightToolbar:
//   - The Wrestle PdfViewer surface needs a "Voice note" affordance
//     that the Research/Reader surfaces don't (yet). We co-locate
//     here so the toolbar can be wired into the WrestleApp tree
//     without modifying the ResearchWorkstation copy. The two
//     toolbars overlap conceptually but serve different host
//     surfaces; merging into one is a future-sprint job.
//   - The Cmd+Shift+V shortcut is GLOBAL within the host
//     (researcher + reader mode both consume it — SPR-04 toggle is
//     orthogonal per the SPR-05 spec's "Where this sprint sits"
//     callout). When no selection is active, the shortcut emits a
//     page-level anchor — VoiceAnchor.tsx documents the rationale.

import { useEffect, useState } from "react";

import type { BBox } from "../../../lib/voiceAnchors";

import { PAGE_LEVEL_BBOX } from "./VoiceAnchor";

interface ToolbarState {
  visible: boolean;
  /** Viewport-relative anchor point — top edge of the selection
   *  rectangle. The recording widget reads this to position
   *  itself. */
  anchorTop: number;
  anchorLeft: number;
  /** Selection bbox in PAGE-LOCAL coordinates (the same convention
   *  PdfViewer.tsx uses: ``selRect.* - layerRect.*``). */
  bbox: BBox;
  /** 0-indexed page number of the selection. */
  page: number;
}

const COLLAPSED: ToolbarState = {
  visible: false,
  anchorTop: 0,
  anchorLeft: 0,
  bbox: PAGE_LEVEL_BBOX,
  page: 0,
};

export interface HighlightToolbarProps {
  /** The PdfViewer's text-layer / page-container ref. Selections
   *  outside this scope are ignored. */
  scopeRef: React.RefObject<HTMLElement | null>;
  /** Called when the operator triggers a voice-note recording
   *  (toolbar button OR shortcut). The parent opens VoiceAnchor
   *  with the supplied target. */
  onVoiceNote: (target: {
    page: number;
    bbox: BBox;
    anchorTop: number;
    anchorLeft: number;
    pageLevel: boolean;
  }) => void;
  /** Optional existing "Chase this" handler — kept so this toolbar
   *  can be a drop-in replacement for the ResearchWorkstation
   *  variant where needed. */
  onChaseThis?: (selectedText: string) => void;
  /** Current page the viewer is on (0-indexed). The shortcut uses
   *  this to construct a page-level anchor when no selection is
   *  active. */
  currentPage: number;
}

export default function HighlightToolbar({
  scopeRef,
  onVoiceNote,
  onChaseThis,
  currentPage,
}: HighlightToolbarProps) {
  const [state, setState] = useState<ToolbarState>(COLLAPSED);

  // selectionchange — toolbar visibility.
  useEffect(() => {
    function onSelectionChange() {
      const sel = window.getSelection();
      const scope = scopeRef.current;
      if (!sel || sel.rangeCount === 0 || !scope) {
        setState((s) => (s.visible ? COLLAPSED : s));
        return;
      }
      const text = sel.toString().trim();
      if (!text || text.length < 3) {
        setState((s) => (s.visible ? COLLAPSED : s));
        return;
      }
      const range = sel.getRangeAt(0);
      if (!scope.contains(range.commonAncestorContainer)) {
        setState((s) => (s.visible ? COLLAPSED : s));
        return;
      }
      const rect = range.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) return;
      const scopeRect = scope.getBoundingClientRect();
      const bbox: BBox = {
        x0: rect.left - scopeRect.left,
        y0: rect.top - scopeRect.top,
        x1: rect.right - scopeRect.left,
        y1: rect.bottom - scopeRect.top,
      };
      setState({
        visible: true,
        anchorTop: rect.top,
        anchorLeft: rect.left + rect.width / 2,
        bbox,
        page: currentPage,
      });
    }
    document.addEventListener("selectionchange", onSelectionChange);
    return () =>
      document.removeEventListener("selectionchange", onSelectionChange);
  }, [scopeRef, currentPage]);

  // Cmd+Shift+V (Mac) / Ctrl+Shift+V (others) — global voice-note
  // trigger. Works regardless of mode (researcher / reader) per M1.
  // If a selection is active, use it; otherwise emit a page-level
  // anchor (PAGE_LEVEL_BBOX).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const isMac = navigator.platform.toUpperCase().includes("MAC");
      const modOK = isMac ? e.metaKey : e.ctrlKey;
      if (!modOK || !e.shiftKey) return;
      if (e.key !== "v" && e.key !== "V") return;
      // Only intercept when focus is within the scope element OR
      // when no selection is active anywhere (so the shortcut is
      // usable as a "drop a voice note on this page" command from
      // anywhere in the surface).
      const scope = scopeRef.current;
      const sel = window.getSelection();
      const hasSelection = !!(
        sel && sel.rangeCount > 0 && sel.toString().trim().length >= 3
      );
      const inScope = (() => {
        if (!scope) return false;
        if (!hasSelection) return true; // page-level: always intercept
        const range = sel!.getRangeAt(0);
        return scope.contains(range.commonAncestorContainer);
      })();
      if (!inScope) return;
      e.preventDefault();
      if (hasSelection && state.visible) {
        // Selection toolbar is up — reuse its computed bbox.
        onVoiceNote({
          page: state.page,
          bbox: state.bbox,
          anchorTop: state.anchorTop,
          anchorLeft: state.anchorLeft,
          pageLevel: false,
        });
      } else if (hasSelection && scope) {
        // Selection exists but the toolbar event hasn't fired yet
        // (race on fast keypress). Compute the bbox inline.
        const range = sel!.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        const scopeRect = scope.getBoundingClientRect();
        onVoiceNote({
          page: currentPage,
          bbox: {
            x0: rect.left - scopeRect.left,
            y0: rect.top - scopeRect.top,
            x1: rect.right - scopeRect.left,
            y1: rect.bottom - scopeRect.top,
          },
          anchorTop: rect.top,
          anchorLeft: rect.left + rect.width / 2,
          pageLevel: false,
        });
      } else {
        // No selection — page-level anchor.
        const vpW = window.innerWidth;
        const vpH = window.innerHeight;
        onVoiceNote({
          page: currentPage,
          bbox: PAGE_LEVEL_BBOX,
          anchorTop: vpH / 3,
          anchorLeft: vpW / 2,
          pageLevel: true,
        });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [scopeRef, currentPage, onVoiceNote, state]);

  if (!state.visible) return null;
  return (
    <div
      style={{
        position: "fixed",
        top: Math.max(8, state.anchorTop - 44),
        left: state.anchorLeft,
        transform: "translateX(-50%)",
        zIndex: 40,
      }}
      className="bg-stone-900 text-white text-xs font-mono rounded-md shadow-lg flex items-center divide-x divide-stone-700"
      onMouseDown={(e) => e.preventDefault()}
      data-testid="highlight-toolbar"
    >
      {onChaseThis ? (
        <button
          type="button"
          onClick={() => {
            const sel = window.getSelection();
            if (sel) onChaseThis(sel.toString());
          }}
          className="px-3 py-1.5 hover:bg-stone-800 rounded-l-md"
        >
          Chase this
        </button>
      ) : null}
      <button
        type="button"
        title="Voice note (⌘⇧V)"
        onClick={() =>
          onVoiceNote({
            page: state.page,
            bbox: state.bbox,
            anchorTop: state.anchorTop,
            anchorLeft: state.anchorLeft,
            pageLevel: false,
          })
        }
        className={
          "px-3 py-1.5 hover:bg-stone-800 transition-colors " +
          (onChaseThis ? "rounded-r-md" : "rounded-md")
        }
      >
        Voice note (⌘⇧V)
      </button>
    </div>
  );
}
