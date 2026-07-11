import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import HighlightFloatingTwinBridgePanel from "./HighlightFloatingTwinBridgePanel";

afterEach(() => {
  cleanup();
});

describe("HighlightFloatingTwinBridgePanel", () => {
  it("bridges with honesty flags", async () => {
    render(
      <HighlightFloatingTwinBridgePanel
        gated={false}
        initialParentAssetId="asset-1"
        initialHighlight="interesting claim"
      />,
    );
    fireEvent.click(screen.getByTestId("hftb-run"));
    await waitFor(() => {
      expect(screen.getByTestId("hftb-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("hftb-twin-created").textContent).toMatch(
        /false/,
      );
    });
  });

  it("fails closed when gated", async () => {
    render(
      <HighlightFloatingTwinBridgePanel
        gated={true}
        initialParentAssetId="asset-1"
        initialHighlight="secret"
      />,
    );
    fireEvent.click(screen.getByTestId("hftb-run"));
    await waitFor(() => {
      expect(screen.getByTestId("hftb-error").textContent).toMatch(/gated/);
    });
  });
});
