/**
 * PasteIngest.test.tsx — paste any file → max-context pack (SPR-04 M3).
 *
 * Pins the gates:
 *   - a pasted URL goes through the shipped /sources/ingest path;
 *   - a pasted passage goes through the shipped text→document ingest
 *     (/voice-notes/ingest) and reports plainly ("Absorbed <Title>");
 *   - content larger than the max-context bound is reported plainly, not
 *     silently truncated;
 *   - a binary file the path can't read as text is rejected honestly;
 *   - an ingest failure shows the shared failure surface, not a fake success.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const { ingestSourceMock, ingestVoiceNoteMock } = vi.hoisted(() => ({
  ingestSourceMock: vi.fn(),
  ingestVoiceNoteMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    ingestSource: ingestSourceMock,
    ingestVoiceNote: ingestVoiceNoteMock,
  };
});

import PasteIngest from "./PasteIngest";

afterEach(() => {
  cleanup();
  ingestSourceMock.mockReset();
  ingestVoiceNoteMock.mockReset();
});

/** Build a paste event with a text payload. */
function pasteText(el: Element, text: string) {
  fireEvent.paste(el, {
    clipboardData: {
      files: [],
      getData: (kind: string) => (kind === "text" ? text : ""),
    },
  });
}

const dropZoneText = /Drop a file, paste a link/;

describe("PasteIngest — universal ingest wiring (M3)", () => {
  it("routes a pasted URL to /sources/ingest", async () => {
    ingestSourceMock.mockResolvedValue({
      status: "ingested",
      detected_kind: "arxiv",
      document_id: "doc-1",
      title: "A Paper",
      chunks_written: 4,
      episodes_processed: 0,
      episodes_ingested: 0,
      document_loaded_event_id: "e",
      skipped_reason: null,
      error_message: null,
    });
    render(<PasteIngest investigationId="inv-1" />);
    pasteText(screen.getByText(dropZoneText), "https://arxiv.org/abs/2401.00001");
    await waitFor(() => expect(screen.getByText(/Absorbed/)).toBeTruthy());
    expect(ingestSourceMock).toHaveBeenCalledWith({
      url: "https://arxiv.org/abs/2401.00001",
      investigation_id: "inv-1",
    });
    expect(screen.getByText(/A Paper/)).toBeTruthy();
  });

  it("routes a pasted passage to the text→document ingest", async () => {
    ingestVoiceNoteMock.mockResolvedValue({
      status: "ingested",
      document_id: "doc-2",
      title: "Pasted note",
      chunks_written: 1,
      document_loaded_event_id: "e",
      skipped_reason: null,
    });
    render(<PasteIngest investigationId="inv-1" />);
    pasteText(screen.getByText(dropZoneText), "A handful of sentences I want absorbed.");
    await waitFor(() => expect(screen.getByText(/Absorbed/)).toBeTruthy());
    expect(ingestVoiceNoteMock).toHaveBeenCalledTimes(1);
    const arg = ingestVoiceNoteMock.mock.calls[0][0];
    expect(arg.transcript).toBe("A handful of sentences I want absorbed.");
    expect(arg.investigation_id).toBe("inv-1");
  });

  it("tells the user plainly when content exceeds the max-context bound", async () => {
    ingestVoiceNoteMock.mockResolvedValue({
      status: "ingested",
      document_id: "doc-big",
      title: "Big note",
      chunks_written: 50,
      document_loaded_event_id: "e",
      skipped_reason: null,
    });
    render(<PasteIngest investigationId="inv-1" />);
    // > 256_000 tokens * ~4 chars/token ⇒ > ~1,024,000 chars.
    const huge = "x".repeat(1_100_000);
    pasteText(screen.getByText(dropZoneText), huge);
    await waitFor(() => expect(screen.getByText(/Absorbed/)).toBeTruthy());
    expect(screen.getByText(/larger than the research can hold/)).toBeTruthy();
  });

  it("rejects a binary file honestly (no shipped multipart path)", async () => {
    render(<PasteIngest investigationId="inv-1" />);
    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "scan.pdf", {
      type: "application/pdf",
    });
    fireEvent.drop(screen.getByText(dropZoneText), {
      dataTransfer: { files: [file], getData: () => "" },
    });
    await waitFor(() =>
      expect(screen.getByText(/isn.t a kind I can absorb directly yet/)).toBeTruthy(),
    );
    expect(ingestVoiceNoteMock).not.toHaveBeenCalled();
    expect(ingestSourceMock).not.toHaveBeenCalled();
  });

  it("shows the failure surface when ingest fails", async () => {
    ingestVoiceNoteMock.mockRejectedValue(new Error("boom"));
    render(<PasteIngest investigationId="inv-1" />);
    pasteText(screen.getByText(dropZoneText), "some text");
    await waitFor(() => expect(screen.getByText(/Couldn.t absorb that/)).toBeTruthy());
  });
});
