import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Sources from "./index";

const ingestSourceMock = vi.fn();

vi.mock("../../lib/api", () => ({
  ingestSource: (...args: unknown[]) => ingestSourceMock(...args),
}));

const ingested = (title: string) => ({
  status: "ingested",
  detected_kind: "arxiv",
  title,
  chunks_written: 4,
  episodes_processed: 0,
  episodes_ingested: 0,
  skipped_reason: null,
  error_message: null,
});

describe("Sources — source intake field station", () => {
  beforeEach(() => ingestSourceMock.mockReset());
  afterEach(cleanup);

  it("keeps generated art decorative and the intake surface live HTML", () => {
    render(<Sources />);
    const art = screen.getByTestId("source-intake-station-art");
    expect(art.getAttribute("alt")).toBe("");
    expect(art.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByRole("heading", { name: "Bring the evidence into range" })).toBeTruthy();
    expect(screen.getByLabelText("Source URLs")).toBeTruthy();
  });

  it("detects source kinds without starting an ingest", () => {
    render(<Sources />);
    fireEvent.change(screen.getByLabelText("Source URLs"), {
      target: { value: "https://arxiv.org/abs/2402.03300\nhttps://youtu.be/example" },
    });
    expect(screen.getByText(/Detected: arxiv, youtube/i)).toBeTruthy();
    expect(ingestSourceMock).not.toHaveBeenCalled();
  });

  it("preserves serial intake order and authoritative request fields", async () => {
    let releaseFirst: (() => void) | undefined;
    ingestSourceMock
      .mockImplementationOnce(() => new Promise((resolve) => { releaseFirst = () => resolve(ingested("Paper one")); }))
      .mockResolvedValueOnce(ingested("Paper two"));
    render(<Sources />);
    fireEvent.change(screen.getByLabelText("Source URLs"), { target: { value: "https://arxiv.org/abs/one\nhttps://arxiv.org/abs/two" } });
    fireEvent.change(screen.getByLabelText("Investigation id"), { target: { value: "inv-field" } });
    fireEvent.click(screen.getByRole("button", { name: "Ingest" }));
    await waitFor(() => expect(ingestSourceMock).toHaveBeenCalledTimes(1));
    expect(ingestSourceMock).toHaveBeenNthCalledWith(1, {
      url: "https://arxiv.org/abs/one",
      kind: undefined,
      investigation_id: "inv-field",
      max_episodes: 10,
    });
    releaseFirst?.();
    await waitFor(() => expect(ingestSourceMock).toHaveBeenCalledTimes(2));
    expect(ingestSourceMock.mock.calls[1][0].url).toBe("https://arxiv.org/abs/two");
  });

  it("never renders thrown or adapter error details", async () => {
    ingestSourceMock
      .mockRejectedValueOnce(new Error("Authorization: Bearer secret-provider-token"))
      .mockResolvedValueOnce({ ...ingested("bad"), status: "error", error_message: "traceback /private/path" });
    render(<Sources />);
    fireEvent.change(screen.getByLabelText("Source URLs"), { target: { value: "https://example.com/one\nhttps://example.com/two" } });
    fireEvent.click(screen.getByRole("button", { name: "Ingest" }));
    await waitFor(() => expect(screen.getAllByText(/could not be received/i)).toHaveLength(2));
    expect(screen.queryByText(/secret-provider-token/i)).toBeNull();
    expect(screen.queryByText(/private\/path/i)).toBeNull();
  });
});
