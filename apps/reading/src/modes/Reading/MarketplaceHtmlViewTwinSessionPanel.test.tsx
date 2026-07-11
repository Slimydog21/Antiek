import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MarketplaceHtmlViewTwinSessionPanel from "./MarketplaceHtmlViewTwinSessionPanel";

afterEach(() => {
  cleanup();
});

describe("MarketplaceHtmlViewTwinSessionPanel", () => {
  it("paid path session ready without charge or twin write", async () => {
    render(<MarketplaceHtmlViewTwinSessionPanel />);
    fireEvent.click(screen.getByTestId("mhvts-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("mhvts-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("mhvts-charge").textContent).toMatch(/false/);
      expect(screen.getByTestId("mhvts-pdf").textContent).toMatch(/false/);
      expect(screen.getByTestId("mhvts-twin-w").textContent).toMatch(/false/);
    });
  });

  it("free path also ready", async () => {
    render(<MarketplaceHtmlViewTwinSessionPanel />);
    fireEvent.change(screen.getByTestId("mhvts-free"), {
      target: { value: "true" },
    });
    fireEvent.click(screen.getByTestId("mhvts-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("mhvts-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("mhvts-pdf").textContent).toMatch(/false/);
    });
  });
});
