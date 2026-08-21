import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const createFeedbackMock = vi.hoisted(() => vi.fn());
vi.mock("../../api/feedback", async () => {
  const actual = await vi.importActual<typeof import("../../api/feedback")>(
    "../../api/feedback",
  );
  return { ...actual, createArtifactFeedback: createFeedbackMock };
});

import ArtifactFeedbackReview from "./ArtifactFeedbackReview";

describe("ArtifactFeedbackReview", () => {
  afterEach(() => {
    cleanup();
    createFeedbackMock.mockReset();
  });

  it("turns a one-node selection into a durable feedback thread", async () => {
    createFeedbackMock.mockResolvedValue({
      thread_id: "fth-1",
      investigation_id: "inv-1",
      state: "open",
      artifact: {
        artifact_id: "artifact-1",
        version: 2,
        content_sha256: "a".repeat(64),
        source_sha256: "b".repeat(64),
      },
      anchor: {
        normalization: "unicode-nfc-v1",
        node_id: "insight-1",
        node_text_sha256: "c".repeat(64),
        start_scalar: 0,
        end_scalar: 4,
        quote: "Fact",
        prefix: "",
        suffix: " remains.",
      },
      items: [
        {
          item_id: "fit-1",
          author_kind: "operator",
          author_id: "owner-1",
          body_markdown: "Verify the source.",
          sequence: 1,
        },
      ],
      work: {
        work_id: "wrk-1",
        logical_worker_id: "research-owner",
        state: "queued",
        attempt_count: 0,
      },
    });
    render(
      <ArtifactFeedbackReview
        investigationId="inv-1"
        previewUrl="about:blank"
        receipt={{
          artifactId: "artifact-1",
          version: "2",
          hash: "a".repeat(64),
          sourceHash: "b".repeat(64),
        }}
        title="Folio artifact"
      />,
    );
    const frame = screen.getByTitle("Folio artifact");
    if (!(frame instanceof HTMLIFrameElement) || !frame.contentDocument) {
      throw new Error("review frame unavailable");
    }
    frame.contentDocument.body.innerHTML =
      '<p data-antiek-node-id="insight-1">Fact remains.</p>';
    const text = frame.contentDocument.querySelector("p")?.firstChild;
    const frameWindow = frame.contentWindow;
    if (!frameWindow || !text || text.nodeType !== Node.TEXT_NODE) {
      throw new Error("text unavailable");
    }
    const range = frame.contentDocument.createRange();
    range.setStart(text, 0);
    range.setEnd(text, 4);
    const selection = frameWindow.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    fireEvent.load(frame);
    fireEvent.mouseUp(frame.contentDocument.body);

    expect(await screen.findByText("“Fact”")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Comment for the research agent"), {
      target: { value: "Verify the source." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send to research agent" }));

    await waitFor(() => expect(createFeedbackMock).toHaveBeenCalledOnce());
    expect(await screen.findByText("Queued for research-owner")).toBeTruthy();
  });
});
