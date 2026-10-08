/**
 * agentPaneId.test.ts — SPR-07 invariant 1 (the Phase A half: the id
 * algebra is deterministic and the draft key is account-scoped).
 */
import { describe, expect, it } from "vitest";

import { accountStorageKey, setWorkspaceOwner } from "../../lib/accountWorkspaceOwner";
import { agentDraftKey, agentPaneId, agentTabIdFor } from "./agentPaneId";

describe("agentPaneId", () => {
  it("a project-scoped agent is named by its project; a cross-project one by its seq", () => {
    expect(agentPaneId("project", "proj-1")).toBe("p:proj-1");
    expect(agentPaneId("cross-project", undefined, 3)).toBe("x:3");
    expect(agentPaneId("cross-project")).toBe("x:0");
  });

  it("the tab id is the agent:pane: prefix plus the agent id", () => {
    expect(agentTabIdFor("p:proj-1")).toBe("agent:pane:p:proj-1");
    expect(agentTabIdFor(agentPaneId("cross-project", undefined, 2))).toBe("agent:pane:x:2");
  });

  it("the draft key is account-scoped and omits the anchor (decision 4)", () => {
    setWorkspaceOwner("owner-a");
    expect(agentDraftKey({ projectId: "proj-1", agentId: "p:proj-1", pane: "companion" }))
      .toBe(accountStorageKey("antiek.agent.draft.v1.proj-1.p:proj-1.companion"));
    expect(agentDraftKey({ agentId: "x:1", pane: "companion" }))
      .toBe(accountStorageKey("antiek.agent.draft.v1.*.x:1.companion"));
    setWorkspaceOwner(null);
    expect(agentDraftKey({ projectId: "proj-1", agentId: "p:proj-1", pane: "companion" })).toBeNull();
  });
});
