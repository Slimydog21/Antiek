/**
 * BrainstormStation's thought-partner placeholder as a PanelKind.
 *
 * The full thought-partner pane (real `/thought-partner` round-trip,
 * structured action surface) is the AISidecar — which the operator
 * can already toggle via ⌘/ from any route. This panel is a small
 * reminder + a CTA to open the sidecar; full ship as part of the
 * sidecar AI-action protocol (see components/ai/aiActions.ts).
 */
export default function ThoughtPartnerPanel() {
  return (
    <div className="h-full overflow-y-auto bg-ice-1 dark:bg-charcoal-2 p-4 space-y-3">
      <header>
        <h3 className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Thought partner
        </h3>
      </header>
      <p className="text-sm font-serif text-ink dark:text-bright leading-relaxed">
        The thought-partner conversation lives in the AI sidecar.
        Press <kbd className="font-mono text-[11px] border border-ink dark:border-bright rounded px-1">⌘/</kbd> to open it — the assistant
        receives this workspace's state and can dispatch panels +
        notebook entries directly back into your session.
      </p>
      <button
        type="button"
        onClick={() => {
          window.dispatchEvent(
            new CustomEvent("antiek:aisidecar:toggle"),
          );
        }}
        className="w-full px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors"
      >
        Open AI sidecar
      </button>
      <p className="text-[10.5px] font-mono text-ink-mute dark:text-moonlight">
        The sidecar's structured action protocol (see
        components/ai/aiActions.ts) gives the assistant access to:
        open_panel, add_to_notebook, chase_question, focus_panel,
        close_panel, set_panel_mode, toast.
      </p>
    </div>
  );
}
