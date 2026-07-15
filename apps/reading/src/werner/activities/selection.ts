import { MODE_TAXONOMY, type Workflow } from "../../shell/workflowTaxonomy";
import { getActivity } from "./registry";
import type { ActivityId, StationActivity } from "./types";

/**
 * The workflow taxonomy is the product authority for routed modes. Deriving
 * station activity from it keeps the lens on every Research + Read surface
 * without maintaining a second, inevitably incomplete route catalog here.
 */
interface WorkflowRoute {
  readonly workflow: Workflow;
  readonly prefix: string;
}

const WORKFLOW_SUBSURFACES = [
  { workflow: "read", prefix: "/readings" },
  { workflow: "read", prefix: "/meta-readings" },
  { workflow: "read", prefix: "/read/meta-reading" },
  { workflow: "research", prefix: "/inv" },
] satisfies readonly WorkflowRoute[];

const ROUTED_WORKFLOWS: readonly WorkflowRoute[] = [
  ...MODE_TAXONOMY.filter((mode) => mode.route).map((mode) => ({
    workflow: mode.workflow,
    // `/outcomes/:synthesisId` becomes the boundary-aware `/outcomes` prefix.
    prefix: mode.route!.replace(/\/:.*/, ""),
  })),
  // These are real App routes that intentionally share their parent mode and
  // therefore have no standalone MODE_TAXONOMY row. Keep this small seam in
  // lockstep with workflowTaxonomy's READ_SUBSURFACE_ROUTES plus `/inv`.
  ...WORKFLOW_SUBSURFACES,
].sort((a, b) => b.prefix.length - a.prefix.length);

function knownWorkflowForPathname(pathname: string): Workflow | null {
  const normalized =
    pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;

  for (const candidate of ROUTED_WORKFLOWS) {
    if (candidate.prefix === "/") {
      if (normalized === "/") return candidate.workflow;
      continue;
    }
    if (
      normalized === candidate.prefix ||
      normalized.startsWith(`${candidate.prefix}/`)
    ) {
      return candidate.workflow;
    }
  }
  return null;
}

export function activityIdForPathname(pathname: string): ActivityId {
  const workflow = knownWorkflowForPathname(pathname);
  if (workflow === "write") return "writing-nib";
  return workflow === "research" || workflow === "read"
    ? "research-lens"
    : "ice-fishing";
}

export function getActivityForPathname(pathname: string): StationActivity {
  const id = activityIdForPathname(pathname);
  const activity = getActivity(id);
  if (!activity) {
    throw new Error(
      `Werner station: route policy selected unregistered activity "${id}"`,
    );
  }
  return activity;
}
