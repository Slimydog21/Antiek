import { useEffect, useState } from "react";

interface ToolbarState {
  visible: boolean;
  top: number; // viewport-relative
  left: number;
  selectedText: string;
}

/**
 * Floating action toolbar anchored to text selections within a scope
 * element. Shows "Chase this" (active) and "Mark golden" (disabled
 * with tooltip — Sprint 12+ deferred).
 *
 * Listens for `selectionchange` events globally, then narrows to
 * selections that are entirely within the configured scope container.
 * Positions itself just above the selection's bounding rect.
 *
 * Hides when the selection collapses or focus moves elsewhere.
 */
export default function HighlightToolbar({
  scopeRef,
  onChaseThis,
}: {
  scopeRef: React.RefObject<HTMLElement | null>;
  onChaseThis: (selectedText: string) => void;
}) {
  const [state, setState] = useState<ToolbarState>({
    visible: false,
    top: 0,
    left: 0,
    selectedText: "",
  });

  useEffect(() => {
    function onSelectionChange() {
      const sel = window.getSelection();
      const scope = scopeRef.current;
      if (!sel || sel.rangeCount === 0 || !scope) {
        setState((s) => (s.visible ? { ...s, visible: false } : s));
        return;
      }
      const text = sel.toString().trim();
      if (!text || text.length < 3) {
        setState((s) => (s.visible ? { ...s, visible: false } : s));
        return;
      }
      // Confirm the selection is inside the scope.
      const range = sel.getRangeAt(0);
      if (!scope.contains(range.commonAncestorContainer)) {
        setState((s) => (s.visible ? { ...s, visible: false } : s));
        return;
      }
      const rect = range.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) return;
      setState({
        visible: true,
        top: Math.max(8, rect.top - 44 + window.scrollY),
        left: rect.left + rect.width / 2 + window.scrollX,
        selectedText: text,
      });
    }
    document.addEventListener("selectionchange", onSelectionChange);
    return () =>
      document.removeEventListener("selectionchange", onSelectionChange);
  }, [scopeRef]);

  if (!state.visible) return null;

  return (
    <div
      style={{
        position: "absolute",
        top: state.top,
        left: state.left,
        transform: "translateX(-50%)",
        zIndex: 40,
      }}
      className="bg-ink text-white text-xs font-mono rounded-md shadow-lg flex items-center divide-x divide-charcoal-2"
      onMouseDown={(e) => e.preventDefault()} /* don't blur selection */
    >
      <button
        onClick={() => onChaseThis(state.selectedText)}
        className="px-3 py-1.5 hover:bg-shadow-2 transition-colors rounded-l-md"
      >
        Chase this
      </button>
      <button
        disabled
        className="px-3 py-1.5 text-shadow-1 dark:text-moonlight cursor-not-allowed rounded-r-md"
        title="Coming Sprint 12: mark this as a confirmed insight, attaches metadata + pushes new questions to chase"
      >
        Mark golden
      </button>
    </div>
  );
}
