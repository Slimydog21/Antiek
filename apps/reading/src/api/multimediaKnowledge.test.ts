import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  finalizeMultimediaKnowledge,
  getMultimediaKnowledgeFinalization,
  getMultimediaKnowledgeTwin,
  recoverMultimediaKnowledgeFinalization,
} from "./multimedia";

function response(status: number, body: unknown = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("multimedia knowledge client", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
  afterEach(() => vi.unstubAllGlobals());

  it("uses encoded owner-scoped status URL", async () => {
    vi.mocked(fetch).mockResolvedValue(response(200, { revision_id: "rev-1" }));
    await getMultimediaKnowledgeFinalization("asset / 1");
    expect(fetch).toHaveBeenCalledWith(
      "/multimedia/assets/asset%20%2F%201/knowledge-finalization",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("reads the owner-scoped twin through an encoded asset URL", async () => {
    vi.mocked(fetch).mockResolvedValue(response(200, { twin_document_id: "twin-1" }));
    await getMultimediaKnowledgeTwin("asset / 1");
    expect(fetch).toHaveBeenCalledWith(
      "/multimedia/assets/asset%20%2F%201/knowledge-twin",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it.each([
    [404, "multimedia_twin_unavailable"],
    [409, "multimedia_twin_integrity_conflict"],
    [503, "multimedia_knowledge_runtime_unavailable"],
  ])("maps twin HTTP %s to safe code %s", async (httpStatus, code) => {
    vi.mocked(fetch).mockResolvedValue(response(httpStatus));
    await expect(getMultimediaKnowledgeTwin("asset-1")).rejects.toThrow(code);
  });

  it("binds initial finalization to the revision and model acknowledgement", async () => {
    vi.mocked(fetch).mockResolvedValue(response(200));
    await finalizeMultimediaKnowledge("asset-1", "rev-1");
    expect(fetch).toHaveBeenCalledWith(
      "/multimedia/assets/asset-1/finalize-knowledge",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expected_revision_id: "rev-1",
          operator_acknowledged_model_use: true,
        }),
      }),
    );
  });

  it("sends both acknowledgements only through explicit recovery", async () => {
    vi.mocked(fetch).mockResolvedValue(response(200));
    await recoverMultimediaKnowledgeFinalization("asset-1", "rev-1");
    expect(fetch).toHaveBeenCalledWith(
      "/multimedia/assets/asset-1/recover-knowledge-finalization",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expected_revision_id: "rev-1",
          operator_acknowledged_model_use: true,
          operator_acknowledged_duplicate_model_risk: true,
        }),
      }),
    );
  });

  it.each([
    [404, "multimedia_knowledge_unavailable"],
    [409, "multimedia_knowledge_conflict"],
    [503, "multimedia_knowledge_runtime_unavailable"],
  ])("maps HTTP %s to safe code %s", async (httpStatus, code) => {
    vi.mocked(fetch).mockResolvedValue(response(httpStatus));
    await expect(getMultimediaKnowledgeFinalization("asset-1")).rejects.toThrow(code);
  });
});
