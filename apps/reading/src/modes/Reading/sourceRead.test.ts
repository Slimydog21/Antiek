import { afterEach, describe, expect, it, vi } from "vitest";

const postTypedEventMock = vi.hoisted(() =>
  vi.fn((_e: unknown) => Promise.resolve({ event_id: "ev-read-1", action_type: "source.read" })),
);

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, postTypedEvent: (e: unknown) => postTypedEventMock(e) };
});

import {
  READ_DWELL_MS_THRESHOLD,
  READ_MIN_PAGES,
  emitSourceRead,
  isRead,
} from "./sourceRead";

afterEach(() => postTypedEventMock.mockClear());

describe("isRead — the justified dwell threshold", () => {
  it("is NOT read on a glance (below the dwell threshold)", () => {
    expect(isRead(READ_DWELL_MS_THRESHOLD - 1, READ_MIN_PAGES)).toBe(false);
  });
  it("is NOT read on a single-page dwell (below the min pages)", () => {
    expect(isRead(READ_DWELL_MS_THRESHOLD + 5_000, READ_MIN_PAGES - 1)).toBe(false);
  });
  it("IS read once BOTH the dwell AND the page bar are met", () => {
    expect(isRead(READ_DWELL_MS_THRESHOLD, READ_MIN_PAGES)).toBe(true);
  });
});

describe("emitSourceRead — single-writer funnel, no body (§9.0)", () => {
  it("posts a source.read typed event to the reading thread carrying only the dwell evidence", async () => {
    await emitSourceRead({
      documentId: "doc-1",
      readingThreadId: "read-doc-1",
      chunkId: "chunk-9",
      dwellMs: 31_234.7,
      pageCount: 3,
    });
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    const env = postTypedEventMock.mock.calls[0][0] as {
      investigation_id: string;
      document_id?: string;
      payload: Record<string, unknown>;
    };
    expect(env.investigation_id).toBe("read-doc-1");
    expect(env.document_id).toBe("doc-1");
    expect(env.payload.action_type).toBe("source.read");
    expect(env.payload.chunk_id).toBe("chunk-9");
    // dwell rounded to an integer (the schema pins ge=0 int).
    expect(env.payload.dwell_ms).toBe(31_235);
    expect(env.payload.page_count).toBe(3);
    // §9.0: NO body field rides the event — only metadata + evidence.
    for (const forbidden of ["excerpt", "text", "body", "full_text", "snippet"]) {
      expect(env.payload[forbidden]).toBeUndefined();
    }
  });

  it("is best-effort — a failed emit never throws into the reader", async () => {
    postTypedEventMock.mockRejectedValueOnce(new Error("503"));
    await expect(
      emitSourceRead({ documentId: "d", readingThreadId: "read-d", dwellMs: 40_000, pageCount: 2 }),
    ).resolves.toBeUndefined();
  });
});
