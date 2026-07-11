import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PaidPurchaseHtmlViewSessionPanel from "./PaidPurchaseHtmlViewSessionPanel";

afterEach(() => {
  cleanup();
});

describe("PaidPurchaseHtmlViewSessionPanel", () => {
  it("paid path session package ready without charge", async () => {
    render(<PaidPurchaseHtmlViewSessionPanel />);
    fireEvent.click(screen.getByTestId("pphvs-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("pphvs-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("pphvs-charge").textContent).toMatch(/false/);
      expect(screen.getByTestId("pphvs-pdf").textContent).toMatch(/false/);
      expect(screen.getByTestId("pphvs-hosted").textContent).toMatch(/false/);
    });
  });

  it("free path also ready", async () => {
    render(<PaidPurchaseHtmlViewSessionPanel />);
    fireEvent.change(screen.getByTestId("pphvs-free"), {
      target: { value: "true" },
    });
    fireEvent.click(screen.getByTestId("pphvs-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("pphvs-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("pphvs-pdf").textContent).toMatch(/false/);
    });
  });
});
