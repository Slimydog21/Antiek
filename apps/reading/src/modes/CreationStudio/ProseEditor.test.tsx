import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ApiError } from "../../lib/api";
import { ProseEditor } from "./index";

const { updateSectionProseMock } = vi.hoisted(() => ({
  updateSectionProseMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  updateSectionProse: updateSectionProseMock,
}));

const section = {
  section_id: "sec-1",
  deliverable_id: "dlv-1",
  parent_section_id: null,
  section_index: 0,
  title: "Thesis",
  prose_text: "Server prose.",
  prose_provenance: null,
  block_count: 1,
} as unknown as Parameters<typeof ProseEditor>[0]["section"];

afterEach(cleanup);

beforeEach(() => {
  updateSectionProseMock.mockReset().mockResolvedValue({ status: "saved", section_id: "sec-1", claim_node_id: null, claim_event_id: null });
});

describe("/create prose editor — the second prose surface", () => {
  // The revision guard (interfaces/research/api/app.py) refuses a write whose
  // based_on_prose_text does not match the stored prose. This surface was the
  // blind caller an independent critic found on #3601/#3602: it is routed at
  // App.tsx:175-176, so the defect class was reachable end to end without it.
  it("sends the confirmed baseline so a stale save is refused, not silently won", async () => {
    render(<ProseEditor section={section} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /edit prose/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Edited on /create." } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(updateSectionProseMock).toHaveBeenCalledTimes(1));
    expect(updateSectionProseMock).toHaveBeenCalledWith(
      "sec-1",
      expect.objectContaining({ based_on_prose_text: "Server prose." }),
    );
  });

  it("shows the conflict copy on 409 and stays in the editor, keeping the draft", async () => {
    updateSectionProseMock.mockRejectedValueOnce(new ApiError("conflict", 409, "prose_revision_conflict"));
    render(<ProseEditor section={section} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /edit prose/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Kept draft." } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("changed somewhere else"),
    );
    // Still editing, and the operator's words are still there.
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("Kept draft.");
  });
});
