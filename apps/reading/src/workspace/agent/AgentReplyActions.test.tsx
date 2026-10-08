/** AgentReplyActions.test.tsx — SPR-07 M6 / invariant 24: buttons the user confirms; nothing runs on render; open_writer is honestly disabled (F3). */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const openDocumentFromAgent = vi.fn();
vi.mock("../contracts/openers", () => ({ openDocumentFromAgent: (...a: unknown[]) => openDocumentFromAgent(...a) }));

import type { BookDocumentAnchor } from "../contracts/anchor";
import { AGENT_REPLY_AGENT_KIND, AgentReplyActions } from "./AgentReplyActions";
import type { AgentPaneTab } from "./agentTypes";

afterEach(() => { cleanup(); openDocumentFromAgent.mockReset(); });

const anchor: BookDocumentAnchor = {
  space: "book", documentId: "guard-b", kind: "text",
  version: { kind: "unversioned", reason: "metadata_only_anchor" },
  range: { kind: "text", nodeId: "n1", start: 0, end: 4, unit: "utf16", basis: "chunk" },
  quoteHint: { quote: "beak", prefix: "", suffix: "" },
};
const tab: AgentPaneTab = { id: "agent:pane:p:proj-1", title: "agent", scope: "project", projectId: "proj-1", agentId: "p:proj-1" };

describe("AgentReplyActions", () => {
  it("renders open_document as a button; nothing runs on render; Enter/click calls the frozen opener once with the pane's AgentRef", () => {
    openDocumentFromAgent.mockReturnValue({ ok: true });
    const { getByRole } = render(<AgentReplyActions tab={tab} isCurrent={() => true} interview={false} actions={[{ kind: "open_document", anchor }]} />);
    expect(openDocumentFromAgent).not.toHaveBeenCalled();
    const button = getByRole("button", { name: /open the passage/i });
    fireEvent.click(button);
    expect(openDocumentFromAgent).toHaveBeenCalledTimes(1);
    expect(openDocumentFromAgent).toHaveBeenCalledWith({
      documentId: "guard-b", anchor, agent: { id: tab.id, viewId: tab.id, kind: AGENT_REPLY_AGENT_KIND },
    });
  });

  it("a refusal renders beside the button instead of being swallowed", () => {
    openDocumentFromAgent.mockReturnValue({ ok: false, reason: "document_mismatch" });
    const { getByRole, container } = render(<AgentReplyActions tab={tab} isCurrent={() => true} interview={false} actions={[{ kind: "open_document", anchor }]} />);
    fireEvent.click(getByRole("button", { name: /open the passage/i }));
    expect(container.querySelector("[data-reply-action-refusal]")!.textContent).toContain("That passage is in another document");
  });

  it("open_writer renders a disabled button whose accessible description names openers.ts:42 and never navigates", () => {
    const { getByRole } = render(<AgentReplyActions tab={tab} isCurrent={() => true} interview={false} actions={[{ kind: "open_writer", deliverable_id: "d-1", block_id: "b-2" }]} />);
    const button = getByRole("button", { name: /open in the writer/i }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    const description = document.getElementById(button.getAttribute("aria-describedby")!)!;
    expect(description.textContent).toContain("openers.ts:42");
    expect(description.textContent).toContain("F3");
    fireEvent.click(button);
    expect(openDocumentFromAgent).not.toHaveBeenCalled();
  });

  it("project_seed renders only in interview mode and confirms through the callback", () => {
    const onSeedConfirm = vi.fn();
    const seed = { kind: "project_seed" as const, title: "Finches", prompt: "Did beak depth track the drought?", sources: ["doc-1"] };
    const outside = render(<AgentReplyActions tab={tab} isCurrent={() => true} interview={false} actions={[seed]} onSeedConfirm={onSeedConfirm} />);
    expect(outside.container.querySelector("[data-seed-card]")).toBeNull();
    cleanup();
    const inside = render(<AgentReplyActions tab={tab} isCurrent={() => true} interview actions={[seed]} onSeedConfirm={onSeedConfirm} />);
    const card = inside.container.querySelector("[data-seed-card]")!;
    expect(card.textContent).toContain("Finches");
    expect(onSeedConfirm).not.toHaveBeenCalled();
    fireEvent.click(inside.getByRole("button", { name: /create this project/i }));
    expect(onSeedConfirm).toHaveBeenCalledWith({ title: "Finches", prompt: "Did beak depth track the drought?", sources: ["doc-1"] });
  });
});
