import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import NotDiamondShadowAdvisoryPanel from "./NotDiamondShadowAdvisoryPanel";

afterEach(() => {
  cleanup();
});

describe("NotDiamondShadowAdvisoryPanel", () => {
  it("default kill switch suppresses shadow; still REJECT", async () => {
    render(<NotDiamondShadowAdvisoryPanel />);
    fireEvent.click(screen.getByTestId("ndsa-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("ndsa-verdict").textContent).toMatch(/REJECT/);
      expect(screen.getByTestId("ndsa-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("ndsa-visible").textContent).toMatch(/false/);
    });
  });

  it("kill off shows differing shadow suggestion without authorizing router", async () => {
    render(<NotDiamondShadowAdvisoryPanel />);
    fireEvent.click(screen.getByTestId("ndsa-kill")); // uncheck kill
    fireEvent.click(screen.getByTestId("ndsa-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("ndsa-visible").textContent).toMatch(/true/);
      expect(screen.getByTestId("ndsa-differs").textContent).toMatch(/true/);
      expect(screen.getByTestId("ndsa-suggested").textContent).toMatch(
        /claude-opus/,
      );
      expect(screen.getByTestId("ndsa-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("ndsa-verdict").textContent).toMatch(/REJECT/);
    });
  });
});
