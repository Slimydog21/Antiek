import { getActivity } from "./registry";
import type { ActivityId, StationActivity } from "./types";

/**
 * The route policy is deliberately explicit. Knowledge-work routes receive a
 * research lens; utility, settings, billing, and creation routes retain the
 * default ice-fishing activity. No random rotation and no hidden timing state.
 */
const KNOWLEDGE_WORK_EXACT = new Set([
  "/",
  "/deep-research",
  "/my-research",
  "/readings",
  "/meta-readings",
]);

const KNOWLEDGE_WORK_PREFIXES = ["/inv/", "/deep-research/", "/read/"] as const;

export function activityIdForPathname(pathname: string): ActivityId {
  const normalized =
    pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (
    KNOWLEDGE_WORK_EXACT.has(normalized) ||
    KNOWLEDGE_WORK_PREFIXES.some((prefix) => normalized.startsWith(prefix))
  ) {
    return "research-lens";
  }
  return "ice-fishing";
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
