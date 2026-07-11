import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import BookPurchaseGatePanel from "./BookPurchaseGatePanel";
import type { PurchaseGateDecision } from "../../api/bookPurchaseGate";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: PurchaseGateDecision = {
  title: "Unknown Book",
  author: null,
  purchase_intent_allowed: true,
  purchase_executed: false,
  path: "purchase_intent_after_free_miss",
  reasons: [],
  notes: [],
  free_copy_freely_available: false,
  authority: "purchase_gate_advisory",
};

describe("BookPurchaseGatePanel", () => {
  it("evaluates after free miss via injectable", async () => {
    const gateFn = vi.fn(async () => sample);
    render(
      <BookPurchaseGatePanel
        gateFn={gateFn}
        initialTitle="Unknown Book"
        freeCopyFreelyAvailable={false}
      />,
    );
    fireEvent.click(screen.getByTestId("bpg-evaluate"));
    await waitFor(() => {
      expect(screen.getByTestId("bpg-summary").textContent).toMatch(
        /intent_allowed=true/,
      );
    });
    expect(screen.getByTestId("bpg-executed").textContent).toMatch(/false/);
    expect(gateFn).toHaveBeenCalledWith({
      title: "Unknown Book",
      author: null,
      skip_free_copy: false,
      operator_skip_acknowledged: null,
      free_copy_preflight: { freely_available: false },
    });
  });

  it("surfaces errors", async () => {
    const gateFn = vi.fn(async () => {
      throw new Error("free copy available");
    });
    render(
      <BookPurchaseGatePanel
        gateFn={gateFn}
        initialTitle="Walden"
        freeCopyFreelyAvailable={true}
      />,
    );
    fireEvent.click(screen.getByTestId("bpg-evaluate"));
    await waitFor(() => {
      expect(screen.getByTestId("bpg-error").textContent).toMatch(
        /free copy/,
      );
    });
  });

  it("rejects purchase_executed invent", async () => {
    const gateFn = vi.fn(async () => ({
      ...sample,
      purchase_executed: true,
    }));
    render(
      <BookPurchaseGatePanel
        gateFn={gateFn}
        initialTitle="X"
        freeCopyFreelyAvailable={false}
      />,
    );
    fireEvent.click(screen.getByTestId("bpg-evaluate"));
    await waitFor(() => {
      expect(screen.getByTestId("bpg-error").textContent).toMatch(
        /purchase_executed/,
      );
    });
  });
});
