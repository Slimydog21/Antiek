import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import DeliverableSidebar from "./DeliverableSidebar";

const { createDeliverableMock, listDeliverablesMock, navigateMock } =
  vi.hoisted(() => ({
    createDeliverableMock: vi.fn(),
    listDeliverablesMock: vi.fn(),
    navigateMock: vi.fn(),
  }));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  createDeliverable: createDeliverableMock,
  listDeliverables: listDeliverablesMock,
}));

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("./VoiceNoteCapture", () => ({
  VoiceNoteCapture: () => <div data-testid="voice-note-capture" />,
}));

beforeEach(() => {
  navigateMock.mockReset();
  createDeliverableMock.mockReset().mockResolvedValue({
    deliverable_id: "dlv dirty/new",
    title: "New memo",
    deliverable_kind: "research_memo",
    investigation_root_id: null,
    status: "draft",
    created_at: null,
    updated_at: null,
    section_count: 0,
  });
  listDeliverablesMock.mockReset().mockResolvedValue({
    count: 1,
    deliverables: [
      {
        deliverable_id: "dlv dirty/listed",
        title: "Listed memo",
        deliverable_kind: "research_memo",
        investigation_root_id: null,
        status: "draft",
        created_at: null,
        updated_at: null,
        section_count: 2,
      },
    ],
  });
});

afterEach(cleanup);

function renderSidebar() {
  return render(
    <MemoryRouter>
      <DeliverableSidebar />
    </MemoryRouter>,
  );
}

describe("DeliverableSidebar", () => {
  it("encodes listed deliverable ids before opening them in CreationStudio", async () => {
    renderSidebar();

    await userEvent.click(await screen.findByText("Listed memo"));

    expect(navigateMock).toHaveBeenCalledWith("/create/dlv%20dirty%2Flisted");
  });

  it("encodes newly created deliverable ids before opening them in CreationStudio", async () => {
    renderSidebar();

    await userEvent.type(
      await screen.findByPlaceholderText(/new deliverable title/i),
      "New memo",
    );
    await userEvent.click(screen.getByRole("button", { name: /new deliverable/i }));

    await waitFor(() => expect(createDeliverableMock).toHaveBeenCalled());
    expect(navigateMock).toHaveBeenCalledWith("/create/dlv%20dirty%2Fnew");
  });
});
