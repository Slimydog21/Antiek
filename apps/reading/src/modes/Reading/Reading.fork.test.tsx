/**
 * Reading.fork.test.tsx — the fork action + provenance header (thread-merge
 * + document fork SPR-01, the SPR-00 verdict's C with B's salvaged note).
 *
 *   1. The companion's fork action POSTs the copy fork idempotently (one
 *      operation id per intent, the page locator riding along), records the
 *      lineage the session just learned, and opens the fork BESIDE the book
 *      through the branch navigation (the landed tab wiring files it under
 *      this tab — routeSync's own suites pin the filing);
 *   2. failure is named from the server's status — the rights refusal
 *      (422) and the depth-1 limit (409) are honest lines, never a fake
 *      success;
 *   3. the fork tab's provenance header renders "Forked from <title> on
 *      <date> · the original is untouched" for a fork and NOTHING for a
 *      plain document.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { InvestigationState } from "../../hooks/useInvestigation";
import type { InvestigationSummary } from "../../lib/api";
import type { DocumentFork } from "../../api/forks";

const {
  useInvestigationMock,
  listState,
  createForkMock,
  branchToMock,
} = vi.hoisted(() => ({
  useInvestigationMock: vi.fn(),
  listState: { investigations: [] as InvestigationSummary[], loading: false, error: null, refetch: vi.fn() },
  createForkMock: vi.fn(),
  branchToMock: vi.fn(),
}));

vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: useInvestigationMock,
}));
vi.mock("../../hooks/useInvestigationList", () => ({
  useInvestigationList: () => listState,
}));
vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, API_BASE: "" };
});
vi.mock("../../api/forks", async (orig) => {
  const actual = await orig<typeof import("../../api/forks")>();
  return { ...actual, createFork: createForkMock };
});
vi.mock("../../workspace/useBranchTo", () => ({
  useBranchTo: () => branchToMock,
}));

import ReadingCompanion from "./ReadingCompanion";
import ForkProvenance from "./ForkProvenance";
import { ApiError } from "../../lib/api";
import { forkLineageOf, recordFork, resetForkLineage } from "../../workspace/forkLineage";
import { resumeWorkspaceOwner, setWorkspaceOwner, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";

const FORK_ROW: DocumentFork = {
  fork_id: "fork-1",
  parent_document_id: "doc-1",
  fork_document_id: "doc-fork-1",
  operation_id: "op-1",
  fork_point_locator: "page:2",
  note: null,
  generation_id: null,
  parent_body_sha256: "a".repeat(64),
  fork_body_sha256: "a".repeat(64),
  created_at: "2026-10-01T09:30:00Z",
  parent_title: "Meditations",
};

function state(over: Partial<InvestigationState>): InvestigationState {
  return {
    id: "read-doc-1",
    status: "completed",
    events: [],
    question: null,
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    reconnects: 0,
    ...over,
  } as InvestigationState;
}

beforeEach(() => {
  setWorkspaceOwner("account-a");
  useInvestigationMock.mockReset();
  useInvestigationMock.mockReturnValue(state({}));
  listState.investigations = [];
  createForkMock.mockReset();
  branchToMock.mockReset();
});

afterEach(() => {
  cleanup();
  setWorkspaceOwner(null);
  resetForkLineage();
});

function renderCompanion() {
  return render(
    <MemoryRouter>
      <ReadingCompanion
        documentId="doc-1"
        title="Meditations"
        readingThreadId="read-doc-1"
        pageIndex={2}
      />
    </MemoryRouter>,
  );
}

describe("the companion's fork action (SPR-01 verdict C)", () => {
  it("holds a completed fork while revalidating and clears busy after same-A confirmation", async () => {
    let finish: (row: DocumentFork) => void = () => { throw new Error("fork not dispatched"); };
    createForkMock.mockImplementation(() => new Promise<DocumentFork>((resolve) => { finish = resolve; }));
    renderCompanion();
    const owner = workspaceOwnerSession();
    fireEvent.click(screen.getByRole("button", { name: "Fork this book" }));
    act(suspendWorkspaceOwner);
    await act(async () => { finish(FORK_ROW); });
    expect(screen.getByRole("button", { name: "forking…" }).hasAttribute("disabled")).toBe(true);
    expect(branchToMock).not.toHaveBeenCalled();
    expect(forkLineageOf("doc-1").forks).toEqual([]);
    act(resumeWorkspaceOwner);
    await waitFor(() => expect(branchToMock).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.getByRole("button", { name: "Fork this book" }).hasAttribute("disabled")).toBe(false));
    expect(workspaceOwnerSession()).toBe(owner);
    expect(forkLineageOf("doc-1").forks).toEqual([FORK_ROW]);
    expect(createForkMock).toHaveBeenCalledOnce();
  });

  it("a held fork failure clears busy and retains the same operation id for a legitimate retry", async () => {
    let fail: (error: Error) => void = () => { throw new Error("fork not dispatched"); };
    createForkMock.mockImplementationOnce(() => new Promise<DocumentFork>((_, reject) => { fail = reject; }));
    createForkMock.mockResolvedValue(FORK_ROW);
    renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: "Fork this book" }));
    const operationId: unknown = createForkMock.mock.calls[0][1].operation_id;
    act(suspendWorkspaceOwner);
    await act(async () => { fail(new ApiError("controlled failure", 503, "")); });
    expect(screen.queryByRole("status")).toBeNull();
    expect(branchToMock).not.toHaveBeenCalled();
    act(resumeWorkspaceOwner);
    await screen.findByRole("status");
    const retry = screen.getByRole("button", { name: "Fork this book" });
    expect(retry.hasAttribute("disabled")).toBe(false);
    fireEvent.click(retry);
    await waitFor(() => expect(branchToMock).toHaveBeenCalledOnce());
    expect(createForkMock.mock.calls[1][1].operation_id).toBe(operationId);
  });

  it("B cannot record or navigate to a fork result held during A revalidation", async () => {
    let finish: (row: DocumentFork) => void = () => { throw new Error("fork not dispatched"); };
    createForkMock.mockImplementation(() => new Promise<DocumentFork>((resolve) => { finish = resolve; }));
    renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: "Fork this book" }));
    act(suspendWorkspaceOwner);
    await act(async () => { finish(FORK_ROW); });
    await act(async () => { setWorkspaceOwner("account-b"); });
    expect(branchToMock).not.toHaveBeenCalled();
    expect(forkLineageOf("doc-1").forks).toEqual([]);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("button", { name: "Fork this book" }).hasAttribute("disabled")).toBe(false);
  });

  it("unmount refuses a held fork without waiting for a later account confirmation", async () => {
    let finish: (row: DocumentFork) => void = () => { throw new Error("fork not dispatched"); };
    createForkMock.mockImplementation(() => new Promise<DocumentFork>((resolve) => { finish = resolve; }));
    const mounted = renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: "Fork this book" }));
    act(suspendWorkspaceOwner);
    await act(async () => { finish(FORK_ROW); });
    mounted.unmount();
    await act(async () => { resumeWorkspaceOwner(); });
    expect(branchToMock).not.toHaveBeenCalled();
    expect(forkLineageOf("doc-1").forks).toEqual([]);
  });

  it("creates the fork idempotently and opens it beside the book", async () => {
    createForkMock.mockResolvedValue(FORK_ROW);
    renderCompanion();

    fireEvent.click(screen.getByRole("button", { name: "Fork this book" }));

    await waitFor(() => expect(branchToMock).toHaveBeenCalledTimes(1));
    // The POST: one operation id, the page locator riding along.
    expect(createForkMock).toHaveBeenCalledTimes(1);
    const [docId, body] = createForkMock.mock.calls[0];
    expect(docId).toBe("doc-1");
    expect(typeof body.operation_id).toBe("string");
    expect(body.operation_id.length).toBeGreaterThan(0);
    expect(body.fork_point_locator).toBe("page:2");
    // The fork opens BESIDE the source: the branch navigation with this
    // book as the origin (the route sync files it under this tab).
    expect(branchToMock).toHaveBeenCalledWith("/read/doc-fork-1", {
      document_id: "doc-1",
      kind: "manual",
      page_index: 2,
    });
    // The session learned the lineage — the strip's chip/badge read it.
    expect(forkLineageOf("doc-fork-1").forkedFrom?.fork_id).toBe("fork-1");
    expect(forkLineageOf("doc-1").forks.map((f) => f.fork_id)).toEqual(["fork-1"]);
    expect(screen.getByRole("status").textContent).toContain(
      "opened in the tab beside this one",
    );
  });

  it("names the rights refusal (422) honestly", async () => {
    createForkMock.mockRejectedValue(
      new ApiError("POST /books/{id}/forks failed: HTTP 422", 422, "fork_rights_refused"),
    );
    renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: "Fork this book" }));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "This book's rights don't allow a fork.",
      ),
    );
    expect(branchToMock).not.toHaveBeenCalled();
  });

  it("names the depth-1 limit (409) honestly", async () => {
    createForkMock.mockRejectedValue(
      new ApiError("POST /books/{id}/forks failed: HTTP 409", 409, "fork_depth_limit"),
    );
    renderCompanion();
    fireEvent.click(screen.getByRole("button", { name: "Fork this book" }));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "This book is already a fork — forks of forks aren't available yet.",
      ),
    );
    expect(branchToMock).not.toHaveBeenCalled();
  });
});

describe("the fork tab's 'bring in outcomes' surface (SPR-03)", () => {
  it("offers the composed review on a fork, carrying the fork + parent threads", async () => {
    recordFork(FORK_ROW);
    const onCompose = vi.fn();
    render(
      <MemoryRouter>
        <ReadingCompanion
          documentId="doc-fork-1"
          title="Meditations (fork)"
          readingThreadId="read-doc-fork-1"
          pageIndex={0}
          onComposeOutcomes={onCompose}
        />
      </MemoryRouter>,
    );
    const button = screen.getByRole("button", { name: "Bring in outcomes…" });
    fireEvent.click(button);
    expect(onCompose).toHaveBeenCalledWith({
      investigationIds: ["read-doc-fork-1", "read-doc-1"],
      forkId: "fork-1",
      forkDocumentId: "doc-fork-1",
    });
  });

  it("is absent on a plain document", () => {
    render(
      <MemoryRouter>
        <ReadingCompanion
          documentId="doc-1"
          title="Meditations"
          readingThreadId="read-doc-1"
          onComposeOutcomes={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("button", { name: "Bring in outcomes…" })).toBeNull();
  });
});

describe("the fork tab's provenance header (salvaged from spike B)", () => {
  it("renders the provenance line for a fork", () => {
    recordFork(FORK_ROW);
    render(
      <MemoryRouter>
        <ForkProvenance documentId="doc-fork-1" />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Forked from/).textContent).toBe(
      "Forked from Meditations on 2026-10-01 · the original is untouched",
    );
  });

  it("renders nothing for a plain document", () => {
    const { container } = render(
      <MemoryRouter>
        <ForkProvenance documentId="doc-1" />
      </MemoryRouter>,
    );
    expect(container.textContent).toBe("");
  });
});
