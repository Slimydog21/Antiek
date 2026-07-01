import type { ResearchStatus } from "../../api/research";

export function launchedChildIdsFromSession(
  researches: readonly Pick<ResearchStatus, "investigation_id">[],
): ReadonlySet<string> {
  return new Set(researches.map((r) => r.investigation_id));
}
