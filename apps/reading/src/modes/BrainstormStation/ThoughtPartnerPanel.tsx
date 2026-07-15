/**
 * BrainstormStation's thought-partner placeholder as a PanelKind.
 *
 * The full thought-partner pane (real `/thought-partner` round-trip,
 * structured action surface) is the AISidecar — which the operator
 * can already toggle via ⌘/ from any route. This panel is a small
 * reminder + a CTA to open the sidecar; full ship as part of the
 * sidecar AI-action protocol (see components/ai/aiActions.ts).
 *
 * Living-TV brand: session Imagine desk key art (thought-partner invent
 * promoted 2026-07-16) so the panel is Antiek's home of the penguin, not
 * inventory-only invent.
 */
import deskArt from "../../brand/werner/poses/session/werner_thought_partner_desk_session_v1.webp";
import { emitWernerExperience } from "../../werner/reactionBus";

export default function ThoughtPartnerPanel() {
  function openSidecar() {
    // Living-TV: opening the thought partner is a curious glance from Werner.
    emitWernerExperience("highlight");
    window.dispatchEvent(new CustomEvent("antiek:aisidecar:toggle"));
  }

  return (
    <div
      className="h-full overflow-y-auto bg-ice-1 dark:bg-charcoal-2 p-4 space-y-3"
      data-testid="thought-partner-panel"
    >
      <header>
        <h3 className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Thought partner
        </h3>
      </header>

      <div
        className="overflow-hidden rounded-lg border border-rule dark:border-charcoal-3"
        data-testid="thought-partner-desk-brand"
      >
        <img
          src={deskArt}
          alt=""
          aria-hidden="true"
          data-testid="thought-partner-desk-art"
          className="h-28 w-full object-cover object-center"
          loading="lazy"
          decoding="async"
        />
      </div>

      <p className="text-sm font-serif text-ink dark:text-bright leading-relaxed">
        The thought-partner conversation lives in the AI sidecar.
        Press{" "}
        <kbd className="font-mono text-[11px] border border-ink dark:border-bright rounded px-1">
          ⌘/
        </kbd>{" "}
        to open it — the assistant receives this workspace&apos;s state and can
        dispatch panels + notebook entries directly back into your session.
      </p>
      <button
        type="button"
        data-testid="thought-partner-open-sidecar"
        onClick={openSidecar}
        className="w-full px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors"
      >
        Open AI sidecar
      </button>
      <p className="text-[10.5px] font-mono text-ink-mute dark:text-moonlight">
        The sidecar&apos;s structured action protocol (see
        components/ai/aiActions.ts) gives the assistant access to: open_panel,
        add_to_notebook, chase_question, focus_panel, close_panel,
        set_panel_mode, toast.
      </p>
    </div>
  );
}
