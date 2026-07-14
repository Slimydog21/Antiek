import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const { listMock, detailMock, handoffMock } = vi.hoisted(() => ({
  listMock: vi.fn(), detailMock: vi.fn(), handoffMock: vi.fn(),
}));

vi.mock("../../lib/api", async (original) => ({
  ...(await original<typeof import("../../lib/api")>()),
  listDeliverables: listMock,
  getDeliverable: detailMock,
}));
vi.mock("../Write/writeApi", async (original) => ({
  ...(await original<typeof import("../Write/writeApi")>()),
  handoffReadNoteToWrite: handoffMock,
}));

import ReadToWritePicker from "./ReadToWritePicker";

beforeEach(() => {
  listMock.mockReset().mockResolvedValue({
    count: 1,
    deliverables: [{ deliverable_id: "piece-1", title: "My analysis", section_count: 1 }],
  });
  detailMock.mockReset().mockResolvedValue({
    deliverable_id: "piece-1", title: "My analysis",
    sections: [{ section_id: "section-1", title: "Evidence" }],
  });
  handoffMock.mockReset().mockResolvedValue({ deliverable_id: "piece-1" });
});
afterEach(cleanup);

it("chooses a section, sends identities only, and opens the committed piece", async () => {
  const complete = vi.fn();
  render(<ReadToWritePicker noteId="note-1" investigationId="read-doc-1"
    onClose={vi.fn()} onComplete={complete} />);
  fireEvent.click(await screen.findByRole("button", { name: "My analysis" }));
  fireEvent.click(await screen.findByRole("button", { name: "Evidence" }));
  await vi.waitFor(() => expect(complete).toHaveBeenCalledWith("piece-1"));
  expect(handoffMock).toHaveBeenCalledWith({
    note_id: "note-1", target_section_id: "section-1", investigation_id: "read-doc-1",
  });
  expect(JSON.stringify(handoffMock.mock.calls[0][0])).not.toContain("selected");
});

it("shows an honest empty state when there is no writing target", async () => {
  listMock.mockResolvedValue({ count: 0, deliverables: [] });
  render(<ReadToWritePicker noteId="note-1" investigationId="read-doc-1"
    onClose={vi.fn()} onComplete={vi.fn()} />);
  expect(await screen.findByText(/Start a piece in Write/)).toBeTruthy();
  expect(handoffMock).not.toHaveBeenCalled();
});

it("owns keyboard focus and closes on Escape", async () => {
  const close = vi.fn();
  render(<ReadToWritePicker noteId="note-1" investigationId="read-doc-1"
    onClose={close} onComplete={vi.fn()} />);
  await screen.findByRole("button", { name: "My analysis" });
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Close" }));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).toHaveBeenCalledTimes(1);
});
