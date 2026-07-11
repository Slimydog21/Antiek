import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import SourcePackPanel from "./SourcePackPanel";
import type { SourcePackResult } from "../../api/sourcePack";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: SourcePackResult = {
  selected: ["arxiv"],
  entries: [
    {
      source: "arxiv",
      pack_status: "included",
      readiness_status: "ready",
      adapter_importable: true,
      offline_probe_ok: true,
      runner_consumes_today: false,
      note: "ok",
    },
  ],
  pack_text: "# Deep research source pack\narxiv\n",
  included_count: 1,
  notes: [],
  authority: "advisory_preflight",
  live_fetch_authorized: false,
};

describe("SourcePackPanel", () => {
  it("builds pack via injectable", async () => {
    const buildFn = vi.fn(async () => sample);
    render(<SourcePackPanel buildFn={buildFn} initialSelected={["arxiv"]} />);
    fireEvent.click(screen.getByTestId("source-pack-build"));
    await waitFor(() => {
      expect(screen.getByTestId("source-pack-text").textContent).toMatch(
        /source pack/,
      );
    });
    expect(buildFn).toHaveBeenCalledWith({ selected: ["arxiv"] });
  });

  it("surfaces errors", async () => {
    const buildFn = vi.fn(async () => {
      throw new Error("unknown source");
    });
    render(<SourcePackPanel buildFn={buildFn} />);
    fireEvent.click(screen.getByTestId("source-pack-build"));
    await waitFor(() => {
      expect(screen.getByTestId("source-pack-error").textContent).toMatch(
        /unknown source/,
      );
    });
  });

  it("rejects live_fetch invent", async () => {
    const buildFn = vi.fn(async () => ({
      ...sample,
      live_fetch_authorized: true,
    }));
    render(<SourcePackPanel buildFn={buildFn} initialSelected={["arxiv"]} />);
    fireEvent.click(screen.getByTestId("source-pack-build"));
    await waitFor(() => {
      expect(screen.getByTestId("source-pack-error").textContent).toMatch(
        /live_fetch/,
      );
    });
  });
});
