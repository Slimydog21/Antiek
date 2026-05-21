// SPR-04 M2 — toggle button rendered in the WrestleApp header.
//
// One control, two visual states. The actual mode lives in
// userSettings; this component is a controlled-ish view that calls
// `onToggle` and reflects the current mode via `mode`.
//
// Keyboard shortcut (Cmd/Ctrl+R) is bound inside WrestleApp/index.tsx
// alongside its other route-scoped listeners — per rigor #4 we do NOT
// add a global `document.addEventListener` here.

interface ReadingModeToggleProps {
  mode: "researcher" | "reader";
  onToggle: () => void;
}

/**
 * Visual: a compact pill that shows the *target* mode (i.e. the mode
 * the user gets if they click). This is the same affordance pattern
 * the existing AI sidecar uses — the label answers "what does clicking
 * do" rather than "what mode am I in", which tested as less ambiguous
 * during the UI redesign sprints.
 */
export default function ReadingModeToggle({ mode, onToggle }: ReadingModeToggleProps) {
  const target = mode === "researcher" ? "reader" : "researcher";
  const label =
    target === "reader" ? "Reading mode" : "Researcher mode";

  return (
    <button
      type="button"
      onClick={onToggle}
      title={`${label} (⌘R)`}
      aria-label={`Switch to ${label.toLowerCase()}`}
      data-mode={mode}
      data-testid="reading-mode-toggle"
      className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md border border-stone-300 bg-white text-stone-700 hover:bg-stone-100 transition-colors font-mono"
    >
      <span aria-hidden="true">{mode === "reader" ? "○" : "▦"}</span>
      <span>{label}</span>
      <span className="text-stone-400">⌘R</span>
    </button>
  );
}
