/**
 * openers.test.tsx — SPR-06 M5: the two opener interfaces over the existing
 * crossPane and companion implementations, with no behaviour change for
 * today's callers.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookAnchor, InvestigationSummary } from "../../lib/api";
import { ResearchThreadSurface } from "../CompanionAgents";
import { useCompanion } from "../companionStore";
import { openDocumentInLeftPane, setOpenDocumentHandler, type OpenDocumentRequest } from "../crossPane";
import { mothershipForPath } from "../documentSpace";
import { useTabTrees } from "../tabTreeStore";
import { useWorkspace } from "../WorkspaceStore";
import { anchorFromPin, toBranchAnchor, type BookDocumentAnchor, type DeliverableDocumentAnchor } from "./anchor";
import { openAgentFromDocument, openDocumentFromAgent } from "./openers";

const pinned: BookAnchor = {
  anchor_id: "ahl-1", document_id: "doc-1",
  anchor: { normalization: "unicode-nfc-v1", node_id: "chunk-1", node_text_sha256: "a".repeat(64), start_scalar: 3, end_scalar: 9, quote: "passage", prefix: "pre", suffix: "suf" },
  servable_at_pin: true, selection_text_sha256: "b".repeat(64), page_index_hint: 2, source: "pin", status: "active", exact_valid: true,
  investigation_id: null, created_at: "2026-10-07T00:00:00Z", updated_at: "2026-10-07T00:00:00Z",
};
const bookAnchor = (): BookDocumentAnchor => anchorFromPin(pinned);
const pageOnly = (): BookDocumentAnchor => ({
  space: "book", documentId: "doc-1", version: { kind: "unversioned", reason: "reader_page_only" }, kind: "page",
  range: { kind: "page", pageIndex: 4 }, quoteHint: null,
});
const deliverable: DeliverableDocumentAnchor = {
  space: "deliverable", deliverableId: "d1", version: { kind: "unversioned", reason: "writer_prose_block_unpersisted" },
  kind: "block", range: { kind: "block", sectionId: "s1", outlineBlockId: null, paragraphIndex: null }, quoteHint: null,
};
const agent = { id: "inv-a", viewId: "agent:thread:inv-a", kind: "research-thread" as const, investigationId: "inv-a" };

beforeEach(() => {
  useWorkspace.getState().reset();
  useCompanion.getState().reset();
  useTabTrees.getState().resetTabTrees();
});
afterEach(() => {
  cleanup();
  setOpenDocumentHandler(null);
  useCompanion.getState().reset();
  useTabTrees.getState().resetTabTrees();
  useWorkspace.getState().reset();
});

describe("O1 openAgentFromDocument refusals", () => {
  it("refuses a blank investigation id and a project-scoped dialogue", () => {
    expect(openAgentFromDocument({ kind: "research-thread", scope: "cross-project", investigationId: "" })).toEqual({ ok: false, reason: "empty_investigation_id" });
    expect(openAgentFromDocument({ kind: "research-thread", scope: "cross-project" })).toEqual({ ok: false, reason: "empty_investigation_id" });
    expect(useCompanion.getState().tabs).toEqual([]);
    expect(openAgentFromDocument({ kind: "dialogue", scope: "project" })).toEqual({ ok: false, reason: "scope_kind_mismatch" });
    expect(useCompanion.getState().tabs).toEqual([]);
  });
});

describe("O2 openAgentFromDocument descriptors", () => {
  it("carries documentId, scope and anchor for a book anchor; no documentId for a deliverable", () => {
    const a = bookAnchor();
    expect(openAgentFromDocument({ kind: "research-thread", scope: "cross-project", investigationId: "inv-a", anchor: a, title: "A" }))
      .toEqual({ ok: true, viewId: "agent:thread:inv-a", reused: false });
    const tab = useCompanion.getState().tabs[0];
    expect(tab).toEqual({ id: "agent:thread:inv-a", kind: "research-thread", title: "A", investigationId: "inv-a", documentId: "doc-1", seq: 1, scope: "cross-project", anchor: a });
    const second = openAgentFromDocument({ kind: "research-thread", scope: "cross-project", investigationId: "inv-a" });
    expect(second).toEqual({ ok: true, viewId: "agent:thread:inv-a", reused: true });
    expect(useCompanion.getState().tabs[0].anchor).toBe(a);
    const b = pageOnly();
    openAgentFromDocument({ kind: "research-thread", scope: "cross-project", investigationId: "inv-a", anchor: b });
    expect(useCompanion.getState().tabs[0].anchor).toBe(b);
    expect(useCompanion.getState().tabs).toHaveLength(1);

    useCompanion.getState().reset();
    openAgentFromDocument({ kind: "research-thread", scope: "project", investigationId: "inv-b", anchor: deliverable });
    const tabB = useCompanion.getState().tabs[0];
    expect(Object.hasOwn(tabB, "documentId")).toBe(false);
    expect(tabB.anchor).toBe(deliverable);
    expect(tabB.scope).toBe("project");
  });
  it("an existing caller passing no scope/anchor gets today's six-field descriptor", () => {
    useCompanion.getState().openAgentTab({ kind: "research-thread", investigationId: "inv-c", documentId: "doc-c", title: "C" });
    expect(useCompanion.getState().tabs[0]).toEqual({ id: "agent:thread:inv-c", kind: "research-thread", title: "C", investigationId: "inv-c", documentId: "doc-c", seq: 1 });
    useCompanion.getState().openAgentTab({ kind: "dialogue" });
    expect(useCompanion.getState().tabs[1]).toEqual({ id: "agent:dialogue", kind: "dialogue", title: "dialogue", seq: 2 });
    expect(Object.keys(useCompanion.getState().tabs[1]).sort()).toEqual(["id", "kind", "seq", "title"]);
    expect(Object.keys(useCompanion.getState().tabs[0]).sort()).toEqual(["documentId", "id", "investigationId", "kind", "seq", "title"]);
  });
});

describe("O3 openDocumentFromAgent with a swapped handler", () => {
  it("projects the anchor to the wire and keeps absent keys absent", () => {
    const seen: OpenDocumentRequest[] = [];
    setOpenDocumentHandler((req) => { seen.push(req); });
    const a = bookAnchor();
    expect(openDocumentFromAgent({ documentId: "doc-1", anchor: a, agent })).toEqual({ ok: true });
    expect(seen).toEqual([{
      documentId: "doc-1",
      origin: { from: "companion", investigationId: "inv-a", agentTabId: "agent:thread:inv-a", agentKind: "research" },
      anchor: toBranchAnchor(a),
    }]);
    expect(openDocumentFromAgent({ documentId: "doc-1", anchor: pageOnly(), agent, documentTitle: "Title" })).toEqual({ ok: true });
    expect(seen[1]).toEqual({
      documentId: "doc-1", documentTitle: "Title",
      origin: { from: "companion", investigationId: "inv-a", agentTabId: "agent:thread:inv-a", agentKind: "research" },
      anchor: { document_id: "doc-1", page_index: 4 },
    });
    expect(Object.hasOwn(seen[1].anchor!, "source_locator")).toBe(false);
    expect(openDocumentFromAgent({ documentId: "doc-1", agent: { id: "agent:dialogue", viewId: "agent:dialogue", kind: "dialogue" } })).toEqual({ ok: true });
    expect(seen[2]).toEqual({ documentId: "doc-1", origin: { from: "companion", agentTabId: "agent:dialogue", agentKind: "dialogue" } });
    expect(Object.hasOwn(seen[2], "anchor")).toBe(false);
    expect(Object.hasOwn(seen[2].origin, "investigationId")).toBe(false);
  });
  it("refuses blank ids, deliverable anchors and mismatched documents without calling the handler", () => {
    const seen: OpenDocumentRequest[] = [];
    setOpenDocumentHandler((req) => { seen.push(req); });
    expect(openDocumentFromAgent({ documentId: "   ", agent })).toEqual({ ok: false, reason: "empty_document_id" });
    expect(openDocumentFromAgent({ documentId: "doc-1", anchor: deliverable as unknown as BookDocumentAnchor, agent })).toEqual({ ok: false, reason: "deliverable_anchor" });
    expect(openDocumentFromAgent({ documentId: "doc-2", anchor: bookAnchor(), agent })).toEqual({ ok: false, reason: "document_mismatch" });
    expect(seen).toEqual([]);
  });
});

describe("O4 the default handler", () => {
  it("spawns an agent node carrying the anchor; a second open with another anchor activates (anchor-blind dedup)", async () => {
    window.history.replaceState({ key: "k1" }, "", "/");
    const a = bookAnchor();
    expect(openDocumentFromAgent({ documentId: "doc-1", anchor: a, agent })).toEqual({ ok: true });
    await act(async () => {});
    await act(async () => {});
    const m = mothershipForPath(window.location.pathname, window.location.search);
    const tree = useTabTrees.getState().trees[m];
    const node = tree ? Object.values(tree.nodes).find((n) => n.kind === "reader" && n.ref === "doc-1") : undefined;
    expect(node).toBeTruthy();
    expect(node!.branch_origin).toEqual({ document_id: "doc-1", kind: "agent", anchor: toBranchAnchor(a) });
    expect(node!.opened_by).toEqual({ thread_id: "inv-a", agent_kind: "research" });
    const countBefore = Object.keys(tree!.nodes).length;
    // Move away so the open has somewhere to come back to, then reopen with a different anchor.
    expect(openDocumentFromAgent({ documentId: "doc-1", anchor: pageOnly(), agent })).toEqual({ ok: true });
    await act(async () => {});
    await act(async () => {});
    const after = useTabTrees.getState().trees[m]!;
    expect(Object.keys(after.nodes).length).toBe(countBefore);
    expect(after.nodes[node!.tab_id].branch_origin?.anchor).toEqual(toBranchAnchor(a));
    expect(after.active_tab_id).toBe(node!.tab_id);
  });
});

describe("O5 CompanionAgents Open source document", () => {
  const summary: InvestigationSummary = {
    investigation_id: "inv-1", question: "Q?", status: "completed", started_at: "2026-09-20T10:00:00Z",
    completed_at: "2026-09-20T11:00:00Z", cost_usd_total: 0.5, parent_investigation_id: null,
  };
  it("includes investigationId only when the tab has one", () => {
    const seen: OpenDocumentRequest[] = [];
    setOpenDocumentHandler((req) => { seen.push(req); });
    const { unmount } = render(
      <MemoryRouter>
        <ResearchThreadSurface tab={{ id: "agent:thread:inv-1", kind: "research-thread", title: "t", investigationId: "inv-1", documentId: "doc-1", seq: 1 }} summary={summary} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Open source document →"));
    expect(seen).toEqual([{ documentId: "doc-1", origin: { from: "companion", investigationId: "inv-1", agentTabId: "agent:thread:inv-1", agentKind: "research" } }]);
    unmount();
    render(
      <MemoryRouter>
        <ResearchThreadSurface tab={{ id: "agent:thread:", kind: "research-thread", title: "t", documentId: "doc-1", seq: 2 }} summary={summary} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Open source document →"));
    expect(seen[1]).toEqual({ documentId: "doc-1", origin: { from: "companion", agentTabId: "agent:thread:", agentKind: "research" } });
    expect(Object.hasOwn(seen[1].origin, "investigationId")).toBe(false);
    // A tab opened from a book anchor passes it through to the wire.
    const a = bookAnchor();
    cleanup();
    render(
      <MemoryRouter>
        <ResearchThreadSurface tab={{ id: "agent:thread:inv-1", kind: "research-thread", title: "t", investigationId: "inv-1", documentId: "doc-1", seq: 3, anchor: a }} summary={summary} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Open source document →"));
    expect(seen[2].anchor).toEqual(toBranchAnchor(a));
    // The legacy seam is untouched: a direct call still reaches the handler verbatim.
    openDocumentInLeftPane("doc-9", { from: "companion" });
    expect(seen[3]).toEqual({ documentId: "doc-9", origin: { from: "companion" } });
  });
});
