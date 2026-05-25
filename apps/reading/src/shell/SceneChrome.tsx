import { useLocation, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";

import { SHORTCUT_EVENTS } from "../workspace/shortcuts";
import {
  WORKFLOWS,
  workflowForPath,
  workflowHasBuiltMode,
  type Workflow,
} from "./workflowTaxonomy";
import { WorkflowStub } from "./WorkflowStub";

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
      { id: "investigations", label: "Investigations", to: "/investigations" },
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
      { id: "new-deliverable", label: "New deliverable", to: "/create", primary: true },
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

export function SceneChrome({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const wf = workflowForPath(pathname);

  // Shared/operator routes don't get workflow scene chrome — they render
  // their own surface bare (governance surfaces aren't a workflow scene).
  if (wf === "shared") {
    return <>{children}</>;
  }

  const meta = WORKFLOWS[wf];
  const scene = SCENES[wf];
  const built = workflowHasBuiltMode(wf);

  const runAction = (a: Action) => {
    if (a.to) navigate(a.to);
    else if (a.event) window.dispatchEvent(new CustomEvent(a.event));
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
            {scene.actions.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => runAction(a)}
                className={
                  "px-2.5 py-1 rounded text-[12.5px] " +
                  (a.primary
                    ? "bg-sun text-ink hover:bg-sun-glow"
                    : "text-ink-soft dark:text-starlight hover:bg-ice-3 dark:hover:bg-charcoal-1")
                }
              >
                {a.label}
              </button>
            ))}
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
                  onClick={() => navigate(t.to)}
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
      </div>

      {/* The scene body. Either the real route view (children — with the
          panel workspace underneath) or, if nothing is built for this
          workflow, the honest stub. */}
      <div className="flex-1 min-h-0">
        {built ? children : <WorkflowStub workflow={wf} />}
      </div>
    </div>
  );
}

export default SceneChrome;
