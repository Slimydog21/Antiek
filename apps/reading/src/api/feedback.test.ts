import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, API_BASE: "", apiFetch: apiFetchMock };
});

import {
  createArtifactFeedback,
  getFeedbackThread,
  resolveFeedbackThread,
} from "./feedback";

const feedbackThreadPayload = {
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
};

describe("artifact feedback API", () => {
  beforeEach(() => apiFetchMock.mockReset());

  it("posts an immutable version and validated semantic anchor", async () => {
    apiFetchMock.mockResolvedValue(
      new Response(
        JSON.stringify(feedbackThreadPayload),
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

    apiFetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ...thread, state: "resolved" }), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(
      resolveFeedbackThread("fth-1", "feedback-resolve-0001"),
    ).resolves.toMatchObject({ state: "resolved" });
    expect(apiFetchMock).toHaveBeenLastCalledWith(
      "/feedback/threads/fth-1/resolve",
      expect.objectContaining({
        method: "POST",
        headers: { "Idempotency-Key": "feedback-resolve-0001" },
      }),
    );
  });

  it("uses ETag polling and represents 304 without inventing a thread", async () => {
    apiFetchMock.mockResolvedValue(
      new Response(null, { status: 304, headers: { ETag: '"thread-hash"' } }),
    );

    await expect(getFeedbackThread("fth-1", '"thread-hash"')).resolves.toEqual({
      kind: "not_modified",
      etag: '"thread-hash"',
    });
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/feedback/threads/fth-1",
      expect.objectContaining({ headers: { "If-None-Match": '"thread-hash"' } }),
    );
  });

  it("rejects a poll response that has no canonical ETag before reading its body", async () => {
    const response = new Response(JSON.stringify(feedbackThreadPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
    const jsonSpy = vi.spyOn(response, "json");
    apiFetchMock.mockResolvedValue(response);

    await expect(getFeedbackThread("fth-1")).rejects.toThrow(
      "Invalid feedback response: missing ETag",
    );
    expect(jsonSpy).not.toHaveBeenCalled();
  });
});
