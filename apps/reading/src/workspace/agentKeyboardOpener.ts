import {
  awaitWorkspaceOwnerSession,
  isWorkspaceOwnerSession,
  workspaceOwnerSession,
} from "../lib/accountWorkspaceOwner";
import { tabTreeHandle } from "./tabTreeHandle";

/** Keep the lazy keyboard action in its originating account and project. */
export async function openAgentPaneForKeyboard(available: () => boolean) {
  const owner = workspaceOwnerSession();
  const store = tabTreeHandle.store;
  if (owner.subject === null || store === null) return null;
  const { projectId, contextEpoch } = store.getState();
  if (!available()) return null;

  const { openAgentPane } = await import("./agent/openAgentPane");
  if (!await awaitWorkspaceOwnerSession(owner)) return null;
  // Availability can publish synchronously; check captured identities after it.
  if (!available() || !isWorkspaceOwnerSession(owner) || tabTreeHandle.store !== store) return null;
  const current = store.getState();
  if (current.projectId !== projectId || current.contextEpoch !== contextEpoch) return null;
  return openAgentPane({ scope: "project", projectId });
}
