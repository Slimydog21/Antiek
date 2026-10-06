import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { readNotebookDraft, writeNotebookDraft } from "../../lib/notebookDraftStorage";
import { apiFetch } from "../../lib/api";
import ThoughtPartnerPanel from "./ThoughtPartnerPanel";

vi.mock("../../lib/api", async (original) => {
  const actual = await original<typeof import("../../lib/api")>();
  return { ...actual, apiFetch: vi.fn(), postTypedEvent: vi.fn().mockResolvedValue({ event_id: "unit-event" }) };
});
const request = vi.mocked(apiFetch);
const reply = { text: 'A reply\n@@actions\n[{"kind":"add_to_notebook","notebook_id":"shared","block":{"kind":"note","text":"A private append"}}]\n@@end', shape: "SYNTHESIS" };
function send() {
  fireEvent.change(screen.getByLabelText("Thought partner prompt"), { target: { value: "A prompt" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}
beforeEach(() => {
  setWorkspaceOwner(null);
  window.localStorage.clear();
  window.sessionStorage.clear();
  setWorkspaceOwner("account-a");
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no live transport in unit controls")));
  request.mockReset();
});
afterEach(() => { cleanup(); setWorkspaceOwner(null); vi.unstubAllGlobals(); });

describe("ThoughtPartnerPanel awaited account boundary", () => {
  it("still dispatches a same-owner notebook append", async () => {
    request.mockImplementation(async (input) => String(input) === "/thought-partner"
      ? new Response(JSON.stringify(reply), { status: 200 })
      : new Response(null, { status: 404 }));
    render(<ThoughtPartnerPanel />);
    send();
    await waitFor(() => expect(readNotebookDraft("shared")?.html).toContain("A private append"), { timeout: 10000 });
  }, 15000);

  it("cannot append A's delayed parsed response into B's same-id notebook", async () => {
    let finish: (value: unknown) => void = () => { throw new Error("JSON not requested"); };
    const result = new Response(null, { status: 200 });
    vi.spyOn(result, "json").mockImplementation(() => new Promise((done) => { finish = done; }));
    request.mockImplementation(async (input) => String(input) === "/thought-partner"
      ? result : new Response(null, { status: 404 }));
    render(<ThoughtPartnerPanel />);
    send();
    await waitFor(() => expect(result.json).toHaveBeenCalled(), { timeout: 10000 });
    act(() => { setWorkspaceOwner("account-b"); });
    writeNotebookDraft("shared", "B private draft", 0, workspaceOwnerSession());
    await act(async () => { finish(reply); });
    expect(readNotebookDraft("shared")).toEqual({ html: "B private draft", etag: 1 });
    expect(screen.queryByText("A reply")).toBeNull();
    setWorkspaceOwner("account-a");
    expect(readNotebookDraft("shared")).toBeNull();
  }, 15000);
});
