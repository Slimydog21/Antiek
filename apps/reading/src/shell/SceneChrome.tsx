import { useState } from "react";
import { useLocation, useNavigate, type NavigateFunction } from "react-router-dom";
import type { ReactNode } from "react";

import { createDeliverable } from "../lib/api";
import { SHORTCUT_EVENTS } from "../workspace/shortcuts";
import {
  WORKFLOWS,
  workflowForPath,
  workflowHasBuiltMode,
  type Workflow,
} from "./workflowTaxonomy";
import { WorkflowStub } from "./WorkflowStub";
import { ThreadBreadcrumb } from "./ThreadBreadcrumb";
import type { Thread, ThreadHop } from "./threadModel";

import { emitWernerExperience } from "../werner/reactionBus";
/**
 * SceneChrome (SPR-04 zone 3) — the per-workflow scene wrapper.
 *
 * It adds two things ABOVE the existing surface and then renders the
 * surface unchanged:
 *
 *   1. A contextual ACTION BAR — the verbs the active workflow runs
 *      (e.g. Research → "New investigation", "Ask"). Data-driven from a
 *      scene registry keyed by workflow, never hardcoded per route.
 *   2. In-scene TABS — when one object has several views (Research's
 *      investigation has Workstation / Replay / Outcome). Tabs navigate;
 *      they don't replace the panel system.
 *
 * Crucially, SceneChrome WRAPS its children — the route view / main slot.
 * The Zustand panel workspace lives underneath, untouched: a mode still
 * mounts as a panel exactly as before. This is chrome, not a rebuild.
 *
 * If the active workflow has no built surface, SceneChrome renders the
 * honest WorkflowStub instead of the children (which would be an empty or
 * fake scene). Build presence is read from the taxonomy, not hardcoded.
 */
type Action = {
  id: string;
  label: string;
  /** Navigate to a route, or dispatch a workspace event. */
  to?: string;
  event?: string;
  /** A verb that DOES something (create a record) before/instead of
   *  navigating. Takes precedence over `to`/`event`. The handler owns
   *  the navigate so it can land on the newly-created entity. */
  run?: (navigate: NavigateFunction) => Promise<void>;
  primary?: boolean;
};

type Tab = { id: string; label: string; to: string };

type SceneDef = {
  /** Contextual verbs for this workflow. */
  actions: Action[];
  /** In-scene tabs (object views). Shown only when 2+. */
  tabs?: Tab[];
};

/**
 * The scene registry. Keyed by workflow. This is the data the action bar
 * + tabs render from — adding a verb to a workflow is one entry here, not
 * a per-route edit.
 */
const SCENES: Record<Exclude<Workflow, "shared">, SceneDef> = {
  research: {
    actions: [
      { id: "new-investigation", label: "New investigation", to: "/", primary: true },
      { id: "ask", label: "Ask", event: SHORTCUT_EVENTS.AISIDECAR_TOGGLE },
      { id: "outcomes", label: "Outcomes", to: "/outcomes" },
    ],
    tabs: [
      { id: "workstation", label: "Workstation", to: "/" },
      // SPR-05: the one multi-research monitor (folds the old Investigations
      // list + the /deep-research grid into a single "manage all" door).
      { id: "my-research", label: "My research", to: "/my-research" },
      { id: "outcomes", label: "Outcomes", to: "/outcomes" },
    ],
  },
  read: {
    actions: [
      { id: "add-sources", label: "Add sources", to: "/sources", primary: true },
      { id: "documents", label: "Documents", to: "/documents" },
      { id: "new-notebook", label: "New notebook", to: "/notebooks" },
    ],
    tabs: [
      { id: "wrestle", label: "Library", to: "/wrestle" },
      { id: "documents", label: "Documents", to: "/documents" },
      { id: "notebooks", label: "Notebooks", to: "/notebooks" },
    ],
  },
  write: {
    actions: [
      {
        id: "new-deliverable",
        label: "New piece",
        primary: true,
        // The button used to only `navigate("/create")`, which lands on
        // the empty "Select or create a deliverable to begin" canvas and
        // creates nothing — it read as a dead button. The #12 hotfix made it
        // create + open; Write SPR-07 lands it on the REAL loop (/write/{id} —
        // outline + tap-to-add repository + generate + edit), not the demoted
        // studio (/create), so the door and this action agree.
        run: async (navigate) => {
          const d = await createDeliverable({
            title: "Untitled piece",
            deliverable_kind: "general_essay",
          });
          navigate(`/write/${d.deliverable_id}`);
        },
      },
    ],
  },
  speak: {
    actions: [
      { id: "new-project", label: "New project", to: "/speak", primary: true },
      { id: "interviews", label: "Interviews", to: "/interviews" },
    ],
    tabs: [
      { id: "projects", label: "Projects", to: "/speak" },
      { id: "interviews", label: "Interviews", to: "/interviews" },
    ],
  },
};

export function SceneChrome({
  children,
  /**
   * The cross-workflow thread for the entity currently in focus (SPR-06). When
   * present, SceneChrome renders the unified ThreadBreadcrumb in the chrome
   * (zone 3) row — the entity's trajectory across the four workflows. Absent
   * when no entity is focused (the breadcrumb only appears when there's a
   * thread to show). The parent supplies it from GET /thread/{node_id}.
   */
  thread,
  /** Fired when a breadcrumb segment is clicked — wire to ThreadJump's jump. */
  onThreadJump,
}: {
  children: ReactNode;
  thread?: Thread;
  onThreadJump?: (hop: ThreadHop) => void;
}) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const wf = workflowForPath(pathname);
  const [runningAction, setRunningAction] = useState<string | null>(null);

  // Shared/operator routes don't get workflow scene chrome — they render
  // their own surface bare (governance surfaces aren't a workflow scene).
  if (wf === "shared") {
    return <>{children}</>;
  }

  const meta = WORKFLOWS[wf];
  const scene = SCENES[wf];
  const built = workflowHasBuiltMode(wf);

  const runAction = (a: Action) => {
    if (a.run) {
      if (runningAction) return; // guard double-clicks during the await
      setRunningAction(a.id);
      void a
        .run(navigate)
        .finally(() => setRunningAction(null));
    } else if (a.to) {
      navigate(a.to);
    } else if (a.event) {
      window.dispatchEvent(new CustomEvent(a.event));
    }
  };

  const tabActive = (t: Tab) =>
    t.to === "/" ? pathname === "/" : pathname.startsWith(t.to);

  return (
    <div className="h-full w-full flex flex-col min-h-0">
      {/* Action bar — workflow verbs + in-scene tabs. */}
      <div
        className="shrink-0 border-b-edge border-sun bg-ice-1 dark:bg-charcoal-2"
        data-testid={`scene-chrome-${wf}`}
      >
        <div className="h-10 px-4 flex items-center gap-3">
          <span className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight shrink-0">
            {meta.label}
          </span>
          <div className="flex-1" />
          <div className="flex items-center gap-1.5">
            {scene.actions.map((a) => {
              const busy = runningAction === a.id;
              return (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => { emitWernerExperience("highlight"); runAction(a); }}
                  disabled={busy}
                  aria-busy={busy || undefined}
                  className={
                    "px-2.5 py-1 rounded text-[12.5px] disabled:opacity-60 " +
                    (a.primary
                      ? "bg-sun text-ink hover:bg-sun-glow"
                      : "text-ink-soft dark:text-starlight hover:bg-ice-3 dark:hover:bg-charcoal-1")
                  }
                >
                  {busy ? "Creating…" : a.label}
                </button>
              );
            })}
          </div>
        </div>

        {scene.tabs && scene.tabs.length > 1 && (
          <nav
            className="px-4 flex items-center gap-1 -mb-px"
            aria-label={`${meta.label} views`}
          >
            {scene.tabs.map((t) => {
              const active = tabActive(t);
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => { emitWernerExperience("highlight"); navigate(t.to); }}
                  aria-current={active ? "page" : undefined}
                  className={
                    "px-3 py-1.5 text-[12.5px] border-b-2 " +
                    (active
                      ? "border-sun text-ink dark:text-bright font-medium"
                      : "border-transparent text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright")
                  }
                >
                  {t.label}
                </button>
              );
            })}
          </nav>
        )}

        {/* SPR-06 — the cross-workflow thread breadcrumb. Shown only when an
            entity is in focus (a thread to follow). It is the SAME node id at
            every hop; copies are provenance bugs the breadcrumb refuses to
            render (see ThreadBreadcrumb). */}
        {thread && (
          <div
            className="border-t border-rule/60 dark:border-charcoal-1 py-1"
            data-testid="scene-chrome-thread"
          >
            <ThreadBreadcrumb thread={thread} onJump={onThreadJump} />
          </div>
        )}
      </div>

      {/* The scene body. Either the real route view (children — with the
          panel workspace underneath) or, if nothing is built for this
          workflow, the honest stub.

          SPR-04 — GLASS SURFACE. The working surface is now translucent
          (bg-glass + backdrop-blur-glass, SPR-01 tokens) so the living
          mountainscape behind the shell shows through as a frosted backdrop.
          The glass tokens carry a high-alpha frost (~0.66–0.72) AND we blur
          the scene behind, which together keep body text above the WCAG-AA
          contrast floor over the moving scene (the SPR-01 glass legibility
          contract). Under reduced-motion / no-scene the token degrades to its
          opaque `--glass-bg-solid` fallback via the consumer's choice — here
          we keep the blur+frost, which is already legible on a frozen frame.
          A maintainer may raise the scrim alpha if a future busier scene
          drops contrast; the seam is this one className. */}
      <div className="flex-1 min-h-0 bg-glass backdrop-blur-glass">
        {built ? children : <WorkflowStub workflow={wf} />}
      </div>
    </div>
  );
}

export default SceneChrome;
