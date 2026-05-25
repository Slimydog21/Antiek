import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  WORKFLOWS,
  landingModeForWorkflow,
  workflowHasBuiltMode,
  type Workflow,
} from "./workflowTaxonomy";
import { WorkflowStub } from "./WorkflowStub";
import { ThreadBreadcrumb } from "./ThreadBreadcrumb";
import type { Thread, ThreadHop } from "./threadModel";

/**
 * ThreadJump (antiek-unified SPR-06 M3) — cross-workflow jump.
 *
 * Given an entity's thread, the operator jumps from any hop to a related
 * entity in another workflow (published biography → Speak project → source
 * interview turn). A jump:
 *
 *   1. resolves the target hop's workflow to its landing route (the SPR-04 IA
 *      — `landingModeForWorkflow` / `WORKFLOWS[wf].defaultRoute`) and navigates
 *      there, opening the target in that workflow's mode;
 *   2. advances the breadcrumb to the new position in the thread (the active
 *      hop updates to the jumped-to entity).
 *
 * Honesty contract (intellectual honesty #1): a jump into a workflow with NO
 * built surface does NOT navigate to a fake screen — it surfaces the SPR-04
 * `WorkflowStub` ("not yet — <workflow> is on the way"), exactly the honest
 * placeholder SceneChrome uses. The thread does not lie about what exists.
 *
 * This component consumes — does NOT fork — SPR-04's IA: `workflowTaxonomy`
 * decides what's built + where each workflow lands, and `WorkflowStub` renders
 * the honest "not yet" state. The breadcrumb is `ThreadBreadcrumb`.
 *
 * `onOpenPanel` is optional: when provided (production), a jump can also open
 * the target as a workspace panel (the SPR-04 panel system) in addition to
 * navigating. Storybook/tests render without it.
 */
export function ThreadJump({
  thread,
  initialEntityId,
  onOpenPanel,
}: {
  thread: Thread;
  /** The entity in focus at mount (defaults to the canonical entity). */
  initialEntityId?: string;
  /** Optional: open the target as a workspace panel (route mode → panel kind
   *  resolution lives in the panel registry; the parent wires this). */
  onOpenPanel?: (hop: ThreadHop) => void;
}) {
  const navigate = useNavigate();
  const [activeEntityId, setActiveEntityId] = useState<string>(
    initialEntityId ?? thread.canonicalEntityId,
  );
  // When a jump targets an unbuilt workflow, we show the honest stub here
  // rather than navigating to a fake screen.
  const [stubbedWorkflow, setStubbedWorkflow] = useState<Exclude<
    Workflow,
    "shared"
  > | null>(null);

  const jumpTo = (hop: ThreadHop) => {
    if (!workflowHasBuiltMode(hop.workflow)) {
      // Honest: surface the SPR-04 stub, never a fabricated entity.
      setStubbedWorkflow(hop.workflow);
      return;
    }
    setStubbedWorkflow(null);
    // Advance the breadcrumb to the jumped-to position.
    setActiveEntityId(hop.entityId);
    // Resolve the workflow's landing surface (SPR-04 IA) and navigate.
    const landing = landingModeForWorkflow(hop.workflow);
    const route = landing?.route ?? WORKFLOWS[hop.workflow].defaultRoute;
    // Strip any route params (":id") — the landing scene resolves the entity.
    const concrete = route.replace(/\/:.*/, "");
    navigate(concrete);
    onOpenPanel?.(hop);
  };

  return (
    <div className="flex flex-col min-h-0" data-testid="thread-jump">
      <div className="shrink-0 border-b-edge border-sun bg-ice-1 dark:bg-charcoal-2 py-1.5">
        <ThreadBreadcrumb
          thread={thread}
          activeEntityId={activeEntityId}
          onJump={jumpTo}
        />
      </div>

      {stubbedWorkflow && (
        // The honest stub for a jump into an unbuilt workflow. This is the
        // SPR-04 WorkflowStub — the same surface SceneChrome shows — not a
        // fake screen.
        <div className="flex-1 min-h-0" data-testid="thread-jump-stub">
          <WorkflowStub workflow={stubbedWorkflow} />
        </div>
      )}
    </div>
  );
}

export default ThreadJump;
