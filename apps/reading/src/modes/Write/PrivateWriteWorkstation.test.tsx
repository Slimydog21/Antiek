import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const harness = vi.hoisted(() => ({
  generation: 1,
  getDocument: vi.fn(), getHistory: vi.fn(), getRevision: vi.fn(),
  edit: vi.fn(), restore: vi.fn(),
}));

vi.mock("../../lib/auth", () => ({ useAuth: () => ({ sessionGeneration: harness.generation }) }));
vi.mock("../../lib/api", async (original) => {
  const actual = await original<typeof import("../../lib/api")>();
  return {
    ...actual,
    getPrivateWriteDocument: harness.getDocument,
    getPrivateWriteHistory: harness.getHistory,
    getPrivateWriteRevision: harness.getRevision,
    editPrivateWriteDocument: harness.edit,
    restorePrivateWriteDocument: harness.restore,
  };
});

import { ApiError } from "../../lib/api";
import PrivateWriteWorkstation from "./PrivateWriteWorkstation";

const H1 = "1".repeat(64); const H2 = "2".repeat(64); const H3 = "3".repeat(64);
const revision = (number: number, operation: "accept" | "undo" | "edit" | "restore" | "create" | "evidence_insert" | "evidence_bundle" | "synthesis_accept", hash: string) => ({
  revision: number, operation, event_id: `event-${number}`, html_sha256: hash,
  prior_html_sha256: number === 1 ? null : H1, root_acceptance_event_id: "event-1",
  proposal_id: "proposal-1", target_revision: operation === "restore" ? 1 : null,
  target_html_sha256: operation === "restore" ? H1 : null,
  created_at: "2026-07-16 10:00:00", has_summary: false,
  origin_kind: "ai_composition" as const,
});
const documentAt = (number = 2, html = "<article>current</article>", hash = H2) => ({
  write_document_id: "write-1", project_id: "project-1", title: "Evidence manuscript",
  revision: number, html, html_sha256: hash, visibility: "private" as const,
  origin_kind: "ai_composition" as const,
});
const historyAt = (items = [revision(1, "accept", H1), revision(2, "edit", H2)]) => ({
  write_document_id: "write-1", project_id: "project-1",
  current_revision: items.length, revisions: items,
  origin_kind: "ai_composition" as const,
});

beforeEach(() => {
  harness.generation = 1;
  for (const mock of [harness.getDocument, harness.getHistory, harness.getRevision, harness.edit, harness.restore]) mock.mockReset();
  harness.getDocument.mockResolvedValue(documentAt());
  harness.getHistory.mockResolvedValue(historyAt());
});
afterEach(cleanup);

describe("PrivateWriteWorkstation authority", () => {
  it("admits the complete owner-native semantic history vocabulary", async () => {
    harness.getDocument.mockResolvedValue({
      ...documentAt(2), origin_kind: "owner_native",
    });
    harness.getHistory.mockResolvedValue({
      write_document_id: "write-1", project_id: "project-1", current_revision: 2,
      origin_kind: "owner_native",
      revisions: [
        { ...revision(1, "create", H1), root_acceptance_event_id: null,
          proposal_id: null, origin_kind: "owner_native" },
        { ...revision(2, "synthesis_accept", H2), root_acceptance_event_id: null,
          proposal_id: null, origin_kind: "owner_native" },
      ],
    });
    const view = render(<PrivateWriteWorkstation projectId="project-1" writeDocumentId="write-1" />);
    await waitFor(() => expect(view.container.textContent).toContain("Revision strata2"));
    expect(view.getByRole("button", { name: /r2.*synthesis_accept/i })).toBeTruthy();
  });

  it("walks paginated history with a stable current pointer", async () => {
    harness.getDocument.mockResolvedValue(documentAt(3, "<p>third</p>", H3));
    harness.getHistory
      .mockResolvedValueOnce({
        write_document_id: "write-1", project_id: "project-1", current_revision: 3,
        origin_kind: "ai_composition",
        revisions: [revision(1, "accept", H1), revision(2, "edit", H2)],
      })
      .mockResolvedValueOnce({
        write_document_id: "write-1", project_id: "project-1", current_revision: 3,
        origin_kind: "ai_composition",
        revisions: [revision(3, "edit", H3)],
      });
    const view = render(<PrivateWriteWorkstation projectId="project-1" writeDocumentId="write-1" />);
    await waitFor(() => expect(view.container.textContent).toContain("Revision strata3"));
    expect(harness.getHistory).toHaveBeenNthCalledWith(
      2, "project-1", "write-1", expect.any(AbortSignal), 2, 500,
    );
  });

  it("hydrates canonical source and fetches historical bytes only on selection", async () => {
    harness.getRevision.mockResolvedValue({ ...revision(1, "accept", H1), project_id: "project-1", write_document_id: "write-1", html: "<p>first</p>", is_current: false });
    const view = render(<PrivateWriteWorkstation projectId="project-1" writeDocumentId="write-1" />);
    const source = await waitFor(() => view.getByLabelText("Private Write HTML source") as HTMLTextAreaElement);
    await waitFor(() => expect(source.value).toBe("<article>current</article>"));
    expect(harness.getRevision).not.toHaveBeenCalled();
    fireEvent.click(view.getByRole("button", { name: /r1.*accept/i }));
    await waitFor(() => expect(source.value).toBe("<p>first</p>"));
    expect(source.disabled).toBe(true);
    expect(harness.getRevision).toHaveBeenCalledWith("project-1", "write-1", 1, expect.any(AbortSignal));
  });

  it("saves one explicit optimistic revision and never renders dirty unadmitted HTML", async () => {
    harness.edit.mockResolvedValue({
      event_id: "edit-3", write_document_id: "write-1", project_id: "project-1",
      revision: 3, prior_revision: 2, html_sha256: H3, replayed: false, visibility: "private",
    });
    harness.getDocument.mockResolvedValueOnce(documentAt()).mockResolvedValueOnce(documentAt(3, "<p>dirty</p>", H3));
    harness.getHistory.mockResolvedValueOnce(historyAt()).mockResolvedValueOnce(historyAt([
      revision(1, "accept", H1), revision(2, "edit", H2), revision(3, "edit", H3),
    ]));
    const view = render(<PrivateWriteWorkstation projectId="project-1" writeDocumentId="write-1" />);
    const source = await waitFor(() => view.getByLabelText("Private Write HTML source") as HTMLTextAreaElement);
    await waitFor(() => expect(source.disabled).toBe(false));
    fireEvent.change(source, { target: { value: "<p>dirty</p>" } });
    fireEvent.click(view.getByRole("button", { name: "rendered" }));
    expect((view.getByTitle("Current manuscript preview") as HTMLIFrameElement).getAttribute("srcdoc")).toBe("");
    expect(view.container.textContent).toContain("server-admitted HTML");
    const save = view.getByRole("button", { name: "Save revision" });
    fireEvent.click(save); fireEvent.click(save);
    await waitFor(() => expect(harness.edit).toHaveBeenCalledTimes(1));
    expect(harness.edit).toHaveBeenCalledWith(
      "project-1", "write-1",
      { base_revision: 2, base_html_sha256: H2, html: "<p>dirty</p>" },
      expect.any(String),
    );
    await waitFor(() => expect(view.container.textContent).toContain("Revision saved"));
  });

  it("preserves dirty bytes on conflict until explicit reload", async () => {
    harness.edit.mockRejectedValue(new ApiError("conflict", 409, "{}"));
    const view = render(<PrivateWriteWorkstation projectId="project-1" writeDocumentId="write-1" />);
    const source = await waitFor(() => view.getByLabelText("Private Write HTML source") as HTMLTextAreaElement);
    await waitFor(() => expect(source.disabled).toBe(false));
    fireEvent.change(source, { target: { value: "<p>my unsaved work</p>" } });
    fireEvent.click(view.getByRole("button", { name: "Save revision" }));
    await waitFor(() => expect(view.container.textContent).toContain("changed elsewhere"));
    expect(source.value).toBe("<p>my unsaved work</p>");
    expect(source.disabled).toBe(true);
    fireEvent.click(view.getByRole("button", { name: "Reload current" }));
    await waitFor(() => expect(source.value).toBe("<article>current</article>"));
  });

  it("preserves dirty bytes when explicit conflict reload fails", async () => {
    harness.edit.mockRejectedValue(new ApiError("conflict", 409, "{}"));
    const view = render(<PrivateWriteWorkstation projectId="project-1" writeDocumentId="write-1" />);
    const source = await waitFor(() => view.getByLabelText("Private Write HTML source") as HTMLTextAreaElement);
    await waitFor(() => expect(source.disabled).toBe(false));
    fireEvent.change(source, { target: { value: "<p>irreplaceable draft</p>" } });
    fireEvent.click(view.getByRole("button", { name: "Save revision" }));
    await waitFor(() => expect(view.getByRole("button", { name: "Reload current" })).toBeTruthy());
    harness.getDocument.mockRejectedValueOnce(new Error("offline"));
    fireEvent.click(view.getByRole("button", { name: "Reload current" }));
    await waitFor(() => expect(view.container.textContent).toContain("Reload failed"));
    expect(source.value).toBe("<p>irreplaceable draft</p>");
  });

  it("restores only after confirmation then rehydrates the authoritative pointer", async () => {
    harness.getRevision.mockResolvedValue({ ...revision(1, "accept", H1), project_id: "project-1", write_document_id: "write-1", html: "<p>first</p>", is_current: false });
    harness.restore.mockResolvedValue({
      event_id: "restore-3", write_document_id: "write-1", project_id: "project-1",
      revision: 3, prior_revision: 2, html_sha256: H1, replayed: false,
      visibility: "private", operation: "restore", target_revision: 1,
    });
    harness.getDocument.mockResolvedValueOnce(documentAt()).mockResolvedValueOnce(documentAt(3, "<p>first</p>", H1));
    harness.getHistory.mockResolvedValueOnce(historyAt()).mockResolvedValueOnce(historyAt([
      revision(1, "accept", H1), revision(2, "edit", H2), revision(3, "restore", H1),
    ]));
    const view = render(<PrivateWriteWorkstation projectId="project-1" writeDocumentId="write-1" />);
    await waitFor(() => expect(view.getByLabelText("Private Write HTML source")).toBeTruthy());
    fireEvent.click(view.getByRole("button", { name: /r1.*accept/i }));
    await waitFor(() => expect(view.container.textContent).toContain("Restore this revision"));
    fireEvent.click(view.getByRole("button", { name: "Restore this revision" }));
    expect(harness.restore).not.toHaveBeenCalled();
    fireEvent.click(view.getByRole("button", { name: "Restore as new revision" }));
    await waitFor(() => expect(harness.restore).toHaveBeenCalledWith(
      "project-1", "write-1",
      { base_revision: 2, base_html_sha256: H2, target_revision: 1 }, expect.any(String),
    ));
    await waitFor(() => expect(view.container.textContent).toContain("Revision 1 restored"));
  });

  it("rejects metadata carrying manuscript or rationale bytes", async () => {
    harness.getHistory.mockResolvedValue({
      ...historyAt(), revisions: [{ ...revision(1, "accept", H1), html: "LEAK" }, revision(2, "edit", H2)],
    });
    const view = render(<PrivateWriteWorkstation projectId="project-1" writeDocumentId="write-1" />);
    await waitFor(() => expect(view.container.textContent).toContain("authority could not be verified"));
    expect(view.container.textContent).not.toContain("LEAK");
  });
});
