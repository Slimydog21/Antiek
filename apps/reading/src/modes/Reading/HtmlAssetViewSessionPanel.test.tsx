import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import HtmlAssetViewSessionPanel from "./HtmlAssetViewSessionPanel";

afterEach(() => {
  cleanup();
});

describe("HtmlAssetViewSessionPanel", () => {
  it("opens HTML session without PDF authority", async () => {
    render(<HtmlAssetViewSessionPanel />);
    fireEvent.click(screen.getByTestId("havs-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("havs-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("havs-html").textContent).toMatch(/true/);
      expect(screen.getByTestId("havs-pdf").textContent).toMatch(/false/);
    });
  });

  it("pdf claim denies html view", async () => {
    render(<HtmlAssetViewSessionPanel />);
    fireEvent.change(screen.getByTestId("havs-format"), {
      target: { value: "pdf" },
    });
    fireEvent.click(screen.getByTestId("havs-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("havs-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("havs-pdf").textContent).toMatch(/false/);
    });
  });
});
