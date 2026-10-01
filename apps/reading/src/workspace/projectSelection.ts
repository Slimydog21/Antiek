import { create } from "zustand";

export const PROJECT_PARAM = "project";
export const projectFromSearch = (search: string): string | null => new URLSearchParams(search).get(PROJECT_PARAM)?.trim() || null;

/** The URL selects; the tab store's projectId records only the bound scope. */
export const useProjectSelection = create<{
  requestedId: string | null;
  status: "idle" | "loading" | "ready" | "unavailable" | "missing";
  retry: number;
}>()(() => ({ requestedId: null, status: "idle", retry: 0 }));

export const retryProjectSelection = () => useProjectSelection.setState((state) => ({ retry: state.retry + 1 }));

export function withProject(to: string, projectId: string | null): string {
  if (!projectId) return to;
  const [bare, hash] = to.split("#", 2);
  const [path, query] = bare.split("?", 2);
  const params = new URLSearchParams(query);
  if (!params.has(PROJECT_PARAM)) params.set(PROJECT_PARAM, projectId);
  return `${path}?${params.toString()}${hash === undefined ? "" : `#${hash}`}`;
}
