import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import HtmlHostPanel from "./HtmlHostPanel";
import type { HtmlHostReceipt } from "../../api/htmlHost";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const SHA = "d".repeat(64);

const sample: HtmlHostReceipt = {
  host_allowed: true,
  hosted: false,
  acquisition_path: "free_copy",
  parent_asset_id: "asset-1",
  title: "Walden",
  html_sha256: SHA,
  html_bytes: 100,
  view_mode: "html",
  reasons: [],
  notes: [],
  authority: "html_host_port_advisory",
  purchase_executed: false,
};

describe("HtmlHostPanel", () => {
  it("evaluates via injectable", async () => {
    const evaluateFn = vi.fn(async () => sample);
    render(
      <HtmlHostPanel
        evaluateFn={evaluateFn}
        initialTitle="Walden"
        freeCopyFreelyAvailable={true}
        htmlProjectionReady={true}
        htmlSha256={SHA}
        htmlBytes={100}
      />,
    );
    fireEvent.click(screen.getByTestId("html-host-evaluate"));
    await waitFor(() => {
      expect(screen.getByTestId("html-host-summary").textContent).toMatch(
        /host_allowed=true/,
      );
    });
    expect(screen.getByTestId("html-host-hosted").textContent).toMatch(
      /hosted=false/,
    );
  });

  it("surfaces errors", async () => {
    const evaluateFn = vi.fn(async () => {
      throw new Error("html_projection_ready=false");
    });
    render(
      <HtmlHostPanel
        evaluateFn={evaluateFn}
        initialTitle="X"
        purchaseIntentAllowed={true}
        htmlProjectionReady={false}
      />,
    );
    fireEvent.click(screen.getByTestId("html-host-evaluate"));
    await waitFor(() => {
      expect(screen.getByTestId("html-host-error").textContent).toMatch(
        /html_projection/,
      );
    });
  });

  it("rejects hosted invent", async () => {
    const evaluateFn = vi.fn(async () => ({ ...sample, hosted: true }));
    render(
      <HtmlHostPanel
        evaluateFn={evaluateFn}
        initialTitle="Walden"
        freeCopyFreelyAvailable={true}
        htmlProjectionReady={true}
        htmlSha256={SHA}
      />,
    );
    fireEvent.click(screen.getByTestId("html-host-evaluate"));
    await waitFor(() => {
      expect(screen.getByTestId("html-host-error").textContent).toMatch(
        /hosted/,
      );
    });
  });
});
