import { API_BASE, ApiError, apiFetch } from "../lib/api";

export interface FeedbackAnchor {
  normalization: "unicode-nfc-v1";
  node_id: string;
  node_text_sha256: string;
  start_scalar: number;
  end_scalar: number;
  quote: string;
  prefix: string;
  suffix: string;
}

export interface FeedbackThread {
  thread_id: string;
  investigation_id: string;
  state: string;
  artifact: {
    artifact_id: string;
    version: number;
    content_sha256: string;
    source_sha256: string;
  };
  anchor: FeedbackAnchor;
  items: Array<{
    item_id: string;
    author_kind: "operator" | "agent" | "system";
    author_id: string;
    body_markdown: string;
    sequence: number;
  }>;
  work: {
    work_id: string;
    logical_worker_id: string;
    state: string;
    attempt_count: number;
  };
}

export interface CreateArtifactFeedbackInput {
  artifactId: string;
  version: number;
  investigationId: string;
  contentSha256: string;
  sourceSha256: string;
  anchor: FeedbackAnchor;
  bodyMarkdown: string;
  idempotencyKey: string;
}

export type FeedbackPollResult =
  | { kind: "not_modified"; etag: string }
  | { kind: "thread"; etag: string; thread: FeedbackThread };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown, name: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`Invalid feedback response: ${name}`);
  return value;
}

function string(value: unknown, name: string): string {
  if (typeof value !== "string") throw new Error(`Invalid feedback response: ${name}`);
  return value;
}

function number(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) {
    throw new Error(`Invalid feedback response: ${name}`);
  }
  return value;
}

function authorKind(
  value: unknown,
  name: string,
): "operator" | "agent" | "system" {
  if (value === "operator" || value === "agent" || value === "system") return value;
  throw new Error(`Invalid feedback response: ${name}`);
}

function parseAnchor(value: unknown): FeedbackAnchor {
  const data = record(value, "anchor");
  if (data.normalization !== "unicode-nfc-v1") {
    throw new Error("Invalid feedback response: normalization");
  }
  return {
    normalization: data.normalization,
    node_id: string(data.node_id, "anchor.node_id"),
    node_text_sha256: string(data.node_text_sha256, "anchor.node_text_sha256"),
    start_scalar: number(data.start_scalar, "anchor.start_scalar"),
    end_scalar: number(data.end_scalar, "anchor.end_scalar"),
    quote: string(data.quote, "anchor.quote"),
    prefix: string(data.prefix, "anchor.prefix"),
    suffix: string(data.suffix, "anchor.suffix"),
  };
}

export function parseFeedbackThread(value: unknown): FeedbackThread {
  const data = record(value, "thread");
  const artifact = record(data.artifact, "artifact");
  const work = record(data.work, "work");
  if (!Array.isArray(data.items)) throw new Error("Invalid feedback response: items");
  const items = data.items.map((value, index) => {
    const item = record(value, `items[${index}]`);
    return {
      item_id: string(item.item_id, `items[${index}].item_id`),
      author_kind: authorKind(item.author_kind, `items[${index}].author_kind`),
      author_id: string(item.author_id, `items[${index}].author_id`),
      body_markdown: string(item.body_markdown, `items[${index}].body_markdown`),
      sequence: number(item.sequence, `items[${index}].sequence`),
    };
  });
  return {
    thread_id: string(data.thread_id, "thread_id"),
    investigation_id: string(data.investigation_id, "investigation_id"),
    state: string(data.state, "state"),
    artifact: {
      artifact_id: string(artifact.artifact_id, "artifact.artifact_id"),
      version: number(artifact.version, "artifact.version"),
      content_sha256: string(artifact.content_sha256, "artifact.content_sha256"),
      source_sha256: string(artifact.source_sha256, "artifact.source_sha256"),
    },
    anchor: parseAnchor(data.anchor),
    items,
    work: {
      work_id: string(work.work_id, "work.work_id"),
      logical_worker_id: string(work.logical_worker_id, "work.logical_worker_id"),
      state: string(work.state, "work.state"),
      attempt_count: number(work.attempt_count, "work.attempt_count"),
    },
  };
}

async function checkedJson(response: Response, action: string): Promise<unknown> {
  if (!response.ok) {
    let message = `${action} failed (HTTP ${response.status}).`;
    try {
      const body: unknown = await response.json();
      if (isRecord(body) && typeof body.detail === "string") message = body.detail;
    } catch {
      // Preserve the bounded HTTP message when the body is not JSON.
    }
    throw new ApiError(message, response.status, message);
  }
  return response.json();
}

export async function createArtifactFeedback(
  input: CreateArtifactFeedbackInput,
): Promise<FeedbackThread> {
  const response = await apiFetch(
    `${API_BASE}/artifacts/${encodeURIComponent(input.artifactId)}` +
      `/versions/${input.version}/feedback/threads`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": input.idempotencyKey,
      },
      body: JSON.stringify({
        investigation_id: input.investigationId,
        artifact_content_sha256: input.contentSha256,
        artifact_source_sha256: input.sourceSha256,
        anchor: input.anchor,
        body_markdown: input.bodyMarkdown,
      }),
    },
  );
  return parseFeedbackThread(await checkedJson(response, "Creating feedback"));
}

export async function getFeedbackThread(
  threadId: string,
  etag: string | null = null,
  signal?: AbortSignal,
): Promise<FeedbackPollResult> {
  const headers = etag === null ? undefined : { "If-None-Match": etag };
  const response = await apiFetch(
    `${API_BASE}/feedback/threads/${encodeURIComponent(threadId)}`,
    { headers, signal },
  );
  const responseEtag = response.headers.get("ETag");
  if (response.status === 304) {
    if (!responseEtag) throw new Error("Invalid feedback response: missing ETag");
    return { kind: "not_modified", etag: responseEtag };
  }
  if (!responseEtag) throw new Error("Invalid feedback response: missing ETag");
  const thread = parseFeedbackThread(await checkedJson(response, "Loading feedback"));
  return { kind: "thread", etag: responseEtag, thread };
}

export async function resolveFeedbackThread(
  threadId: string,
  idempotencyKey: string,
): Promise<FeedbackThread> {
  const response = await apiFetch(
    `${API_BASE}/feedback/threads/${encodeURIComponent(threadId)}/resolve`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    },
  );
  return parseFeedbackThread(await checkedJson(response, "Resolving feedback"));
}
