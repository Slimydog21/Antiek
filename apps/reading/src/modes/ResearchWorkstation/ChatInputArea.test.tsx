import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const { navigateMock, startInvestigationMock, trackExceptionMock, trackMock } = vi.hoisted(
  () => ({
    navigateMock: vi.fn(),
    startInvestigationMock: vi.fn(),
    trackExceptionMock: vi.fn(),
    trackMock: vi.fn(),
  }),
);

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, startInvestigation: startInvestigationMock };
});

vi.mock("../../lib/analytics", () => ({
  track: trackMock,
  trackException: trackExceptionMock,
}));

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

import ChatInputArea from "./ChatInputArea";

afterEach(() => {
  cleanup();
  navigateMock.mockReset();
  startInvestigationMock.mockReset();
  trackExceptionMock.mockReset();
  trackMock.mockReset();
});

function renderInput(props: Partial<React.ComponentProps<typeof ChatInputArea>> = {}) {
  return render(
    <MemoryRouter>
      <ChatInputArea {...props} />
    </MemoryRouter>,
  );
}

describe("ChatInputArea", () => {
  it("trims returned investigation ids before notifying the parent", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " inv-chat ",
      status: "in_progress",
      start_event_id: "e1",
    });
    const onSubmitted = vi.fn();
    const user = userEvent.setup();

    renderInput({ onSubmitted });

    await user.type(screen.getByRole("textbox"), "What changed in the evidence?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith("inv-chat"));
    expect(navigateMock).not.toHaveBeenCalled();
    expect(trackExceptionMock).not.toHaveBeenCalled();
  });

  it("encodes trimmed investigation ids before navigating", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " inv/chat ",
      status: "in_progress",
      start_event_id: "e1",
    });
    const user = userEvent.setup();

    renderInput();

    await user.type(screen.getByRole("textbox"), "What should we chase?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/inv/inv%2Fchat"));
    expect(trackExceptionMock).not.toHaveBeenCalled();
  });

  it("surfaces malformed investigation ids instead of navigating", async () => {
    startInvestigationMock.mockResolvedValue({
      investigation_id: " ",
      status: "in_progress",
      start_event_id: "e1",
    });
    const onSubmitted = vi.fn();
    const user = userEvent.setup();

    renderInput({ onSubmitted });

    await user.type(screen.getByRole("textbox"), "What failed here?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(
      await screen.findByText(/Submit failed: investigation_id must be a non-empty string/i),
    ).toBeTruthy();
    expect(onSubmitted).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
    expect(trackMock).not.toHaveBeenCalled();
    expect(trackExceptionMock).toHaveBeenCalledTimes(1);
  });
});
