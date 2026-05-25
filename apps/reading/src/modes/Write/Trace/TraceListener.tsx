import { useTrace } from "./useTrace";

/**
 * App-shell trace listener (specs/write/ SPR-07).
 *
 * Mounted once in the authenticated shell so a citation click anywhere in
 * the Write surface resolves its provenance and opens the shared
 * BookReader (navigation happens inside ``useTrace``). For the
 * non-navigating outcomes — a user-originated session, a node with no
 * linked document, or an unavailable (dangling) source — it shows a small
 * dismissible panel that labels the outcome honestly rather than opening a
 * reader on nothing.
 */
export function TraceListener() {
  const { state, clear } = useTrace();
  if (!state) return null;

  const label =
    state.type === "session"
      ? "User-originated"
      : state.type === "node_only"
        ? "Source node"
        : "Source unavailable";
  const tone =
    state.type === "unavailable"
      ? "border-emperor text-emperor"
      : "border-ocean text-ink dark:text-bright";

  return (
    <div
      role="status"
      className={
        "fixed bottom-4 right-4 z-50 max-w-sm rounded-hog border-edge bg-ice-0 dark:bg-charcoal-2 " +
        "shadow-z3 px-4 py-3 text-sm " + tone
      }
      data-component="write-trace-panel"
    >
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <p className="font-semibold">{label}</p>
          <p className="text-xs text-ink-mute dark:text-moonlight mt-0.5">{state.detail}</p>
        </div>
        <button
          type="button"
          onClick={clear}
          aria-label="Dismiss"
          className="text-ink-mute hover:text-emperor leading-none"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export default TraceListener;
