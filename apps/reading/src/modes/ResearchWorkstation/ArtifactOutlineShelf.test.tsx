import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import ArtifactOutlineShelf from "./ArtifactOutlineShelf";

const { composeResearchArtifactsMock, exportResearchArtifactMock, getResearchArtifactBlocksMock, listState } =
  vi.hoisted(() => ({
    composeResearchArtifactsMock: vi.fn(),
    exportResearchArtifactMock: vi.fn(),
    getResearchArtifactBlocksMock: vi.fn(),
    listState: { investigations: [] as unknown[], loading: false, error: null, refetch: vi.fn() },
  }));

vi.mock("../../lib/api", () => ({
  composeResearchArtifacts: composeResearchArtifactsMock,
  exportResearchArtifact: exportResearchArtifactMock,
  getResearchArtifactBlocks: getResearchArtifactBlocksMock,
}));

vi.mock("../../hooks/useInvestigationList", () => ({
  useInvestigationList: () => listState,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  listState.investigations = [];
});

describe("ArtifactOutlineShelf", () => {
  it("exports the research artifact and surfaces the twin notes path", async () => {
    getResearchArtifactBlocksMock.mockResolvedValue({ investigation_id: "inv-a", blocks: [] });
    exportResearchArtifactMock.mockResolvedValue({
      investigation_id: "inv-a",
      path: "/tmp/artifacts/inv-a.html",
      twin_notes_path: "/tmp/artifacts/inv-a.notes.html",
      content_hash: "hash-a",
      size_bytes: 42,
      event_id: "ev-1",
    });

    render(<ArtifactOutlineShelf investigationId="inv-a" />);

    fireEvent.click(await screen.findByRole("button", { name: /Export research HTML/i }));

    await waitFor(() => expect(exportResearchArtifactMock).toHaveBeenCalledWith("inv-a"));
    expect(await screen.findByText("/tmp/artifacts/inv-a.html")).toBeTruthy();
    expect(screen.getByText("notes: /tmp/artifacts/inv-a.notes.html")).toBeTruthy();
  });

  it("draft-merges the current research with entered sibling research ids", async () => {
    getResearchArtifactBlocksMock.mockResolvedValue({
      investigation_id: "inv-a",
      blocks: [
        {
          node_id: "node-1",
          kind: "insight",
          label: "A useful finding",
          investigation_id: "inv-a",
          artifact_path: null,
        },
      ],
    });
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/artifacts/compose.html",
      draft_merge_path: "/tmp/artifacts/draft-merge.html",
      members: [],
      hash_conflicts: [],
    });

    render(<ArtifactOutlineShelf investigationId="inv-a" />);

    fireEvent.change(await screen.findByLabelText("Other research ids"), {
      target: { value: "inv-b, inv-c inv-b" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Draft merge/i }));

    await waitFor(() =>
      expect(composeResearchArtifactsMock).toHaveBeenCalledWith(["inv-a", "inv-b", "inv-c"], true),
    );
    expect(await screen.findByText("/tmp/artifacts/draft-merge.html")).toBeTruthy();
  });

  it("draft-merges selected child researches from the investigation list", async () => {
    listState.investigations = [
      {
        investigation_id: "inv-child-a",
        question: "Child A",
        status: "completed",
        started_at: "2026-07-09T12:00:00Z",
        completed_at: null,
        cost_usd_total: 0,
        parent_investigation_id: "inv-a",
      },
      {
        investigation_id: "inv-other",
        question: "Other parent",
        status: "completed",
        started_at: "2026-07-09T12:01:00Z",
        completed_at: null,
        cost_usd_total: 0,
        parent_investigation_id: "inv-z",
      },
    ];
    getResearchArtifactBlocksMock.mockResolvedValue({
      investigation_id: "inv-a",
      blocks: [
        {
          node_id: "node-1",
          kind: "insight",
          label: "A useful finding",
          investigation_id: "inv-a",
          artifact_path: null,
        },
      ],
    });
    composeResearchArtifactsMock.mockResolvedValue({
      path: "/tmp/artifacts/compose.html",
      draft_merge_path: "/tmp/artifacts/child-draft-merge.html",
      members: [],
      hash_conflicts: [],
    });

    render(<ArtifactOutlineShelf investigationId="inv-a" />);

    fireEvent.click(await screen.findByLabelText("Child A"));
    expect(screen.queryByLabelText("Other parent")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Draft merge/i }));

    await waitFor(() =>
      expect(composeResearchArtifactsMock).toHaveBeenCalledWith(["inv-a", "inv-child-a"], true),
    );
    expect(await screen.findByText("/tmp/artifacts/child-draft-merge.html")).toBeTruthy();
  });

  it("refuses a draft merge without a second research id", async () => {
    getResearchArtifactBlocksMock.mockResolvedValue({
      investigation_id: "inv-a",
      blocks: [
        {
          node_id: "node-1",
          kind: "insight",
          label: "A useful finding",
          investigation_id: "inv-a",
          artifact_path: null,
        },
      ],
    });

    render(<ArtifactOutlineShelf investigationId="inv-a" />);

    fireEvent.click(await screen.findByRole("button", { name: /Draft merge/i }));

    expect(await screen.findByText("Add at least one other research id to draft a merge.")).toBeTruthy();
    expect(composeResearchArtifactsMock).not.toHaveBeenCalled();
  });
});
