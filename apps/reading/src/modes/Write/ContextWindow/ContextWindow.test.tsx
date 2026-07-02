import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DRAG_MIME } from "../../CreationStudio/BlockPalette";

const { promoteContextMock, generateSectionMock } = vi.hoisted(() => ({
  promoteContextMock: vi.fn(),
  generateSectionMock: vi.fn(),
}));

vi.mock("../writeApi", async (orig) => ({
  ...(await orig<typeof import("../writeApi")>()),
  promoteContext: promoteContextMock,
  generateSection: generateSectionMock,
}));

import { ContextWindow } from "./ContextWindow";

function dropBlock(label = "Useful claim", blockKind = "insight") {
  const dropZone = screen
    .getByText(/Drag lego blocks here from the repository/i)
    .closest("div");
  expect(dropZone).toBeTruthy();
  fireEvent.drop(dropZone!, {
    dataTransfer: {
      getData: (type: string) =>
        type === DRAG_MIME
          ? JSON.stringify({
              from: "palette",
              block_id: "node-1",
              block_kind: blockKind,
              label,
            })
          : "",
    },
  });
}

beforeEach(() => {
  promoteContextMock.mockReset().mockResolvedValue({
    deliverable_id: "dlv-1",
    section_id: " sec-promoted ",
    block_ids: ["oblk-1"],
  });
  generateSectionMock.mockReset().mockResolvedValue({
    status: "generated",
    section_id: " ",
    prose_text: "  Draft paragraph.  ",
    unsupported_paragraphs: ["0", 1.5, -1, Number.NaN],
    fabricated_citations: [" cite-1 ", "", "cite-1"],
    prose_provenance: { "0": ["node-1", "node-1"] },
  });
});

afterEach(cleanup);

describe("ContextWindow", () => {
  it("trims promoted section ids and sanitizes generation results before display", async () => {
    const onPromoted = vi.fn();
    render(<ContextWindow deliverableId="dlv-1" onPromoted={onPromoted} />);

    dropBlock();
    await userEvent.type(
      screen.getByPlaceholderText(/state the writing objective/i),
      "turn this into a section",
    );
    await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));

    await waitFor(() => expect(generateSectionMock).toHaveBeenCalledWith("sec-promoted"));
    expect(onPromoted).toHaveBeenCalled();
    expect(await screen.findByText("Draft paragraph.")).toBeTruthy();
    expect(screen.getByText(/1 paragraph\(s\) flagged unsupported/i)).toBeTruthy();
  });

  it("preserves dropped repository block kinds when promoting context", async () => {
    render(<ContextWindow deliverableId="dlv-1" />);

    dropBlock("Question to chase", "open_question");
    await userEvent.click(screen.getByRole("button", { name: /promote to outline/i }));

    await waitFor(() => expect(promoteContextMock).toHaveBeenCalled());
    expect(promoteContextMock).toHaveBeenCalledWith(
      expect.objectContaining({
        blocks: [
          expect.objectContaining({
            block_kind: "open_question",
            provenance_kind: "graph_node",
            node_id: "node-1",
          }),
        ],
      }),
    );
  });

  it("surfaces malformed promoted section ids instead of generating", async () => {
    promoteContextMock.mockResolvedValue({
      deliverable_id: "dlv-1",
      section_id: " ",
      block_ids: ["oblk-1"],
    });
    render(<ContextWindow deliverableId="dlv-1" />);

    dropBlock();
    await userEvent.type(
      screen.getByPlaceholderText(/state the writing objective/i),
      "turn this into a section",
    );
    await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));

    expect(await screen.findByText(/did not return a section id/i)).toBeTruthy();
    expect(generateSectionMock).not.toHaveBeenCalled();
  });

  it("validates promote-only responses before reporting success", async () => {
    promoteContextMock.mockResolvedValue({
      deliverable_id: "dlv-1",
      section_id: "",
      block_ids: ["oblk-1"],
    });
    const onPromoted = vi.fn();
    render(<ContextWindow deliverableId="dlv-1" onPromoted={onPromoted} />);

    dropBlock();
    await userEvent.click(screen.getByRole("button", { name: /promote to outline/i }));

    expect(await screen.findByText(/did not return a section id/i)).toBeTruthy();
    expect(onPromoted).not.toHaveBeenCalled();
  });
});
