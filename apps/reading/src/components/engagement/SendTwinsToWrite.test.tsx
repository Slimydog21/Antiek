import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SendTwinsToWrite } from "./SendTwinsToWrite";

const navigate = vi.fn();
const sendTwinsToWrite = vi.fn();
vi.mock("react-router-dom", async () => ({
  ...(await vi.importActual<object>("react-router-dom")),
  useNavigate: () => navigate,
}));
vi.mock("../../api/engagement", () => ({
  sendTwinsToWrite: (...args: unknown[]) => sendTwinsToWrite(...args),
}));

const props = {
  assetId: "doc-1", sessionId: "session-1", spawnId: "spawn-1",
  investigationId: "inv-1",
  notes: [
    { note_id: "note-1", asset_id: "doc-1", kind: "insight" as const, text: "Insight text" },
    { note_id: "note-2", asset_id: "doc-1", kind: "question" as const, text: "Question text?" },
  ],
};

describe("SendTwinsToWrite", () => {
  afterEach(cleanup);
  beforeEach(() => { navigate.mockReset(); sendTwinsToWrite.mockReset(); });

  it("requires reviewed selection and title, submits IDs, then navigates", async () => {
    sendTwinsToWrite.mockResolvedValue({ deliverable_id: "dlv-private", promoted_note_ids: ["note-2"] });
    render(<SendTwinsToWrite {...props} />);
    const button = screen.getByTestId("send-to-write") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(screen.getByText("Question text?"));
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("write-title"), { target: { value: "My brief" } });
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/write/dlv-private"));
    expect(sendTwinsToWrite).toHaveBeenCalledWith({
      asset_id: "doc-1", session_id: "session-1", spawn_id: "spawn-1",
      investigation_id: "inv-1", title: "My brief", note_ids: ["note-2"],
    });
    expect(screen.queryByText("dlv-private")).toBeNull();
  });

  it("keeps a failed handoff visible and does not navigate", async () => {
    sendTwinsToWrite.mockRejectedValue(new Error("Document is no longer available"));
    render(<SendTwinsToWrite {...props} />);
    fireEvent.click(screen.getByText("Insight text"));
    fireEvent.change(screen.getByTestId("write-title"), { target: { value: "Draft" } });
    fireEvent.click(screen.getByTestId("send-to-write"));
    expect((await screen.findByRole("alert")).textContent).toContain("Document is no longer available");
    expect(navigate).not.toHaveBeenCalled();
  });
});
