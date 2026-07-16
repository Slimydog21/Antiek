import { WORKFLOWS } from "./workflowTaxonomy";
import { findForkedHop, type Thread, type ThreadHop } from "./threadModel";

import { emitWernerExperience } from "../werner/reactionBus";
/**
 * ThreadBreadcrumb (antiek-unified SPR-06 M2) — the unified cross-workflow
 * trail.
 *
 * Renders one graph entity's trajectory across the four workflows as a
 * navigable breadcrumb, e.g.
 *
 *   Research insight › Read published › Write outline › …
 *
 * Each segment is a workflow touch on the SAME node id (the no-duplicate
 * invariant — copies are provenance bugs). Clicking a built segment jumps to
 * that entity in its workflow (the parent wires `onJump`, see ThreadJump.tsx).
 *
 * Honesty contract (intellectual honesty #1):
 *   - A hop into an UNBUILT workflow is shown as a dimmed, non-navigable
 *     "not yet" segment — never a fake clickable target.
 *   - If the thread somehow carries a FORKED id (a copy — the server refuses
 *     to serve one, returning 409), the breadcrumb refuses to render the
 *     trail and shows an integrity warning instead. A breadcrumb over copied
 *     entities lies; not rendering is the honest failure (defensibility #5).
 *
 * Presentational by design: it takes a `Thread` + an `onJump(hop)` callback,
 * so Storybook can render every thread shape without a router or live API.
 * ThreadJump.tsx supplies the real navigation.
 *
 * Mounts in SPR-04's chrome (the Topbar breadcrumb row / SceneChrome zone 3);
 * Lemon tokens only, no hardcoded colors.
 */
export function ThreadBreadcrumb({
  thread,
  activeEntityId,
  onJump,
}: {
  thread: Thread;
  /** The entity currently in focus — its segment is shown as the current
   *  (non-link) crumb. Defaults to the canonical entity. */
  activeEntityId?: string;
  /** Fired when a built segment is clicked. ThreadJump wires this to open the
   *  target in its workflow's mode + advance the breadcrumb. */
  onJump?: (hop: ThreadHop) => void;
}) {
  // The navigation's warrant: a forked thread must NOT render a continuous
  // trail (it would assert a continuity the data doesn't support).
  const forked = findForkedHop(thread);
  if (forked) {
    return (
      <div
        className="px-4 py-1.5 text-[12.5px] font-mono text-emperor"
        data-testid="thread-breadcrumb-integrity-warning"
        role="alert"
      >
        Thread integrity error — a workflow holds a copy ({forked}) instead of
        the one entity. Navigation suppressed.
      </div>
    );
  }

  const current = activeEntityId ?? thread.canonicalEntityId;

  return (
    <nav
      aria-label="Cross-workflow thread"
      className="px-4 min-w-0"
      data-testid="thread-breadcrumb"
    >
      <ol className="flex items-center gap-1.5 text-[12.5px] font-mono text-ink-soft dark:text-moonlight overflow-x-auto whitespace-nowrap">
        {thread.hops.map((hop, i) => {
          const meta = WORKFLOWS[hop.workflow];
          // The current-focus segment is the one whose entity is in focus AND
          // is the last occurrence (so a back-and-forth thread highlights the
          // operator's actual position).
          const isCurrent =
            hop.entityId === current &&
            !thread.hops.slice(i + 1).some((h) => h.entityId === current);
          const label = `${meta.label} ${hop.entityKind.replace(/_/g, " ")}`;

          return (
            <li
              key={`${hop.workflow}-${hop.seamEventId ?? "origin"}-${i}`}
              className="flex items-center gap-1.5 shrink-0"
            >
              {i > 0 && (
                <span
                  aria-hidden="true"
                  className="text-ink-mute dark:text-moonlight/60"
                >
                  ›
                </span>
              )}
              {!hop.built ? (
                // Honest unbuilt-workflow segment — dimmed, non-navigable, says
                // plainly it's not available. Never a fake clickable target.
                <span
                  className="text-ink-mute dark:text-moonlight/50 italic cursor-not-allowed"
                  data-testid={`thread-hop-stub-${hop.workflow}`}
                  title={`${meta.label} is not built yet — this hop is a stub.`}
                >
                  {meta.label} — not yet available
                </span>
              ) : isCurrent ? (
                <span
                  className="text-ink dark:text-bright font-semibold"
                  aria-current="step"
                  data-testid={`thread-hop-current-${hop.workflow}`}
                >
                  {label}
                  {hop.viaProvisionalSeam && (
                    <span className="ml-1 text-ink-mute dark:text-moonlight/60 not-italic">
                      (provisional)
                    </span>
                  )}
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    emitWernerExperience("highlight");
                    onJump?.(hop);
                  }}
                  className="text-ink dark:text-bright hover:underline"
                  data-testid={`thread-hop-${hop.workflow}`}
                >
                  {label}
                  {hop.viaProvisionalSeam && (
                    <span className="ml-1 text-ink-mute dark:text-moonlight/60">
                      (provisional)
                    </span>
                  )}
                </button>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export default ThreadBreadcrumb;
