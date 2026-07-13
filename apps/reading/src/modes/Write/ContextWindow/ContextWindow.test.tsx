import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { generateSectionMock, promoteContextMock } = vi.hoisted(() => ({
  generateSectionMock: vi.fn(),
  promoteContextMock: vi.fn(),
}));

vi.mock("../writeApi", async (orig) => ({
  ...(await orig<typeof import("../writeApi")>()),
  generateSection: generateSectionMock,
  promoteContext: promoteContextMock,
}));

import { ContextWindow } from "./ContextWindow";

afterEach(cleanup);

beforeEach(() => {
  promoteContextMock.mockReset().mockResolvedValue({
    deliverable_id: "dlv-1",
    section_id: "sec-1",
    block_ids: ["oblk-1"],
  });
  generateSectionMock.mockReset().mockResolvedValue({
    status: "citation_failed",
    section_id: "sec-1",
    prose_text: "Rejected prose must not be presented as a draft.",
    detail: "citation gate failed: 1 provenance mismatch; regenerate",
    provenance_mismatches: [0],
  });
});

describe("ContextWindow citation acceptance", () => {
  it("shows citation failure without presenting rejected prose", async () => {
    const { container } = render(<ContextWindow />);
    const dropZone = container.querySelector("[class*='border-dashed']");
    expect(dropZone).toBeTruthy();
    fireEvent.drop(dropZone!, {
      dataTransfer: {
        getData: () => JSON.stringify({
          from: "palette",
          block_id: "node-1",
          block_kind: "insight",
          label: "Grounded insight",
        }),
      },
    });
    await userEvent.type(
      screen.getByPlaceholderText(/state the writing objective/i),
      "Draft a grounded analysis",
    );
    await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));

    expect(await screen.findByText(/citations did not match the attached evidence/i)).toBeTruthy();
    expect(container.textContent ?? "").not.toContain("Rejected prose must not be presented");
  });
});
