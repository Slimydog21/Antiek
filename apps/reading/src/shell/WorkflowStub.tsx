/**
 * WorkflowStub — the honest "not yet available" state for a scene tab/section
 * whose product surface hasn't shipped.
 *
 * Functional rationale (frontend-design spec, SPR-05): a stub keyed to a
 * hardcoded "these are built" list rots the moment a product ships. The single
 * switch is the scene tab's `builtState` (sourced from the registry, which
 * marks `built` only where a real route exists in App.tsx today). When that
 * tab gains a `to` route and flips to `built`, the tab becomes a live NavLink
 * and this stub is never reached for it — the flip is the proof, tested in
 * WorkflowStub.test logic via the registry test. No tab can be both `built`
 * and missing its surface (the registry test enforces a `to` on every `built`
 * tab).
 *
 * Tone is researcher's-notebook calm: it states the fact and the owning sprint,
 * no marketing. The owning sprint is passed in by the caller (the product
 * surface that knows which sprint ships it), defaulting to the SPR-07
 * registration sprint that wires the four workflows' real tabs.
 */

import type { SceneTab } from "./sceneRegistry";

type Props = {
  /** What the section is — used in the heading ("Trajectory is not yet available"). */
  label: string;
  /** The sprint that ships this surface. Defaults to SPR-07 (tab wiring). */
  sprint?: string;
};

/**
 * The default owning sprint. SPR-05 ships the chrome + honest stubs; SPR-07
 * registers the four workflows' real tab routes, flipping `soon` → `built`.
 * A caller with a more specific sprint passes it explicitly.
 */
const DEFAULT_OWNING_SPRINT = "SPR-07";

export function WorkflowStub({ label, sprint = DEFAULT_OWNING_SPRINT }: Props) {
  return (
    <div
      className="h-full w-full flex items-center justify-center p-12"
      role="status"
    >
      <div className="max-w-sm text-center">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-shadow-1 dark:text-moonlight mb-2">
          {label}
        </p>
        <p className="text-ink dark:text-bright text-sm leading-relaxed mb-1">
          Not yet available.
        </p>
        <p className="text-shadow-1 dark:text-moonlight text-[13px] leading-relaxed">
          This view ships in {sprint}. The work it belongs to exists; the
          surface for it isn&rsquo;t built here yet.
        </p>
      </div>
    </div>
  );
}

/**
 * Resolve whether a tab should render its real route or the stub, from the
 * tab's live `builtState` — the same switch the Topbar keys off, so the two
 * can never disagree. Returns the stub-or-route decision as a discriminated
 * result the caller renders. Kept beside the component (not inlined in a
 * route) so "why did this section stop stubbing?" has one answer: its tab
 * flipped to `built` in the registry.
 */
export function tabSurface(
  tab: SceneTab,
): { kind: "route"; to: string } | { kind: "stub" } {
  if (tab.builtState === "built" && tab.to) return { kind: "route", to: tab.to };
  return { kind: "stub" };
}

export default WorkflowStub;
