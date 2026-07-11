import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MarketplaceBookHostComposePanel from "./MarketplaceBookHostComposePanel";

afterEach(() => {
  cleanup();
});

describe("MarketplaceBookHostComposePanel", () => {
  it("free miss yields purchase intent with honesty flags", async () => {
    render(
      <MarketplaceBookHostComposePanel initialTitle="Unknown Book" />,
    );
    fireEvent.click(screen.getByTestId("mbhc-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mbhc-path").textContent).toMatch(
        /purchase_intent/,
      );
      expect(screen.getByTestId("mbhc-purchase").textContent).toMatch(/false/);
      expect(screen.getByTestId("mbhc-hosted").textContent).toMatch(/false/);
    });
  });

  it("free hit with sha yields html_host still not purchased", async () => {
    render(<MarketplaceBookHostComposePanel initialTitle="Walden" />);
    fireEvent.change(screen.getByTestId("mbhc-free"), {
      target: { value: "true" },
    });
    fireEvent.change(screen.getByTestId("mbhc-sha"), {
      target: { value: "sha:ready" },
    });
    fireEvent.click(screen.getByTestId("mbhc-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mbhc-path").textContent).toMatch(/html_host/);
      expect(screen.getByTestId("mbhc-purchase").textContent).toMatch(/false/);
      expect(screen.getByTestId("mbhc-hosted").textContent).toMatch(/false/);
    });
  });

  it("surfaces empty title error", async () => {
    render(<MarketplaceBookHostComposePanel initialTitle="" />);
    fireEvent.click(screen.getByTestId("mbhc-run"));
    await waitFor(() => {
      expect(screen.getByTestId("mbhc-error").textContent).toMatch(/title/);
    });
  });
});
