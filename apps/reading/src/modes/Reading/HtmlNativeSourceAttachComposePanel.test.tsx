import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import HtmlNativeSourceAttachComposePanel from "./HtmlNativeSourceAttachComposePanel";

afterEach(() => {
  cleanup();
});

describe("HtmlNativeSourceAttachComposePanel", () => {
  it("attaches sources with honesty flags false", async () => {
    render(<HtmlNativeSourceAttachComposePanel />);
    fireEvent.click(screen.getByTestId("hnsac-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("hnsac-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("hnsac-remote").textContent).toMatch(/false/);
      expect(screen.getByTestId("hnsac-pdf").textContent).toMatch(/false/);
      expect(screen.getByTestId("hnsac-store").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<HtmlNativeSourceAttachComposePanel />);
    fireEvent.click(screen.getByTestId("hnsac-ack"));
    fireEvent.click(screen.getByTestId("hnsac-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("hnsac-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("hnsac-remote").textContent).toMatch(/false/);
    });
  });
});
