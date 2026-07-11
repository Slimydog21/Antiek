import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MarketplaceFreeBeforeBuyHtmlPortPanel from "./MarketplaceFreeBeforeBuyHtmlPortPanel";

afterEach(() => {
  cleanup();
});

describe("MarketplaceFreeBeforeBuyHtmlPortPanel", () => {
  it("free HTML port without purchase/host", async () => {
    render(<MarketplaceFreeBeforeBuyHtmlPortPanel />);
    fireEvent.click(screen.getByTestId("mfbhp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("mfbhp-path").textContent).toMatch(
        /prefer_free_html/,
      );
      expect(screen.getByTestId("mfbhp-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("mfbhp-purchase").textContent).toMatch(/false/);
      expect(screen.getByTestId("mfbhp-hosted").textContent).toMatch(/false/);
      expect(screen.getByTestId("mfbhp-pdf").textContent).toMatch(/false/);
    });
  });

  it("unknown free blocks", async () => {
    render(<MarketplaceFreeBeforeBuyHtmlPortPanel />);
    fireEvent.change(screen.getByTestId("mfbhp-free"), {
      target: { value: "null" },
    });
    fireEvent.click(screen.getByTestId("mfbhp-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("mfbhp-path").textContent).toMatch(
        /blocked_unknown_free/,
      );
      expect(screen.getByTestId("mfbhp-ready").textContent).toMatch(/false/);
    });
  });
});
