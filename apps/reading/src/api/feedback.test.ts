import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, API_BASE: "", apiFetch: apiFetchMock };
});

import { createArtifactFeedback } from "./feedback";

describe("artifact feedback API", () => {
  beforeEach(() => apiFetchMock.mockReset());

  it("posts an immutable version and validated semantic anchor", async () => {
    apiFetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
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
            quote: "fact",
            prefix: "",
            suffix: " remains",
          },
          items: [
            {
              item_id: "fit-1",
              author_kind: "operator",
              author_id: "owner-1",
              body_markdown: "Verify this.",
              sequence: 1,
            },
          ],
          work: {
            work_id: "wrk-1",
            logical_worker_id: "research-owner",
            state: "queued",
            attempt_count: 0,
          },
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );

    const thread = await createArtifactFeedback({
      artifactId: "artifact-1",
      version: 2,
      investigationId: "inv-1",
      contentSha256: "a".repeat(64),
      sourceSha256: "b".repeat(64),
      anchor: {
        normalization: "unicode-nfc-v1",
        node_id: "insight-1",
        node_text_sha256: "c".repeat(64),
        start_scalar: 0,
        end_scalar: 4,
        quote: "fact",
        prefix: "",
        suffix: " remains",
      },
      bodyMarkdown: "Verify this.",
      idempotencyKey: "feedback-key-0001",
    });

    expect(thread.work.state).toBe("queued");
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/artifacts/artifact-1/versions/2/feedback/threads",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Idempotency-Key": "feedback-key-0001" }),
      }),
    );
  });
});
