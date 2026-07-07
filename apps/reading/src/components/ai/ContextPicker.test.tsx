import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("../../lib/api", () => ({
  // Minimal stand-in so ``err instanceof ApiError`` resolves in-component.
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
  composeContext: vi.fn(),
}));

import { composeContext } from "../../lib/api";
import ContextPicker from "./ContextPicker";

const composeMock = composeContext as unknown as ReturnType<typeof vi.fn>;

describe("ContextPicker", () => {
  beforeEach(() => composeMock.mockReset());
  afterEach(cleanup);

  it("composes the selected items and surfaces withheld + onContextChange", async () => {
    const onContextChange = vi.fn();
    composeMock.mockResolvedValueOnce({
      system_context: "CTX",
      withheld: ["doc-1"],
      missing: [],
    });

    render(<ContextPicker onContextChange={onContextChange} />);

    fireEvent.change(screen.getByLabelText("Item id"), {
      target: { value: "doc-1" },
    });
    fireEvent.click(screen.getByText("Add"));
    fireEvent.click(screen.getByText("Compose context"));

    await waitFor(() => expect(composeMock).toHaveBeenCalledTimes(1));
    expect(composeMock).toHaveBeenCalledWith({
      items: [{ kind: "doc", id: "doc-1" }],
    });

    await waitFor(() => expect(onContextChange).toHaveBeenCalledWith("CTX"));
    expect(screen.getByTestId("withheld").textContent).toContain("doc-1");
  });

  it("disables Compose when the item list is empty", () => {
    render(<ContextPicker onContextChange={() => undefined} />);
    expect(
      (screen.getByText("Compose context") as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("renders a network error and does not call onContextChange on failure", async () => {
    const onContextChange = vi.fn();
    composeMock.mockRejectedValueOnce(new Error("boom"));

    render(<ContextPicker onContextChange={onContextChange} />);

    fireEvent.change(screen.getByLabelText("Item id"), {
      target: { value: "insight-9" },
    });
    fireEvent.change(screen.getByLabelText("Item kind"), {
      target: { value: "insight" },
    });
    fireEvent.click(screen.getByText("Add"));
    fireEvent.click(screen.getByText("Compose context"));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("network error"),
    );
    expect(onContextChange).not.toHaveBeenCalled();
  });
});
