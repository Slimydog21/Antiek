import { afterEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetchMock(...args) };
});

import { WERNER_EXPERIENCE_EVENT } from "../../werner/reactionBus";
import { placeBlock, type PlaceBlockBody } from "./writeApi";

const BODY: PlaceBlockBody = {
  section_id: "section-1",
  block_kind: "insight",
  provenance_kind: "graph_node",
  node_id: "node-1",
  block_index: 0,
  deliverable_id: "deliverable-1",
};

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

function captureExperiences(): { seen: string[]; teardown: () => void } {
  const seen: string[] = [];
  const listener = (event: Event) => {
    seen.push((event as CustomEvent).detail?.experience);
  };
  window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);
  return {
    seen,
    teardown: () => window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener),
  };
}

afterEach(() => {
  apiFetchMock.mockReset();
  vi.restoreAllMocks();
});

describe("placeBlock Werner reaction boundary", () => {
  it("reacts only after the server confirms the new outline block", async () => {
    let resolveCommit!: (value: Response) => void;
    apiFetchMock.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveCommit = resolve;
      }),
    );
    const capture = captureExperiences();

    const pending = placeBlock(BODY);
    expect(capture.seen).toEqual([]);
    resolveCommit(response({ outline_block_id: "outline-block-1" }));
    await expect(pending).resolves.toBe("outline-block-1");
    expect(capture.seen).toEqual(["outline_block_committed"]);
    expect(apiFetchMock).toHaveBeenCalledTimes(1);

    capture.teardown();
  });

  it("stays silent when persistence rejects the block", async () => {
    apiFetchMock.mockResolvedValueOnce(response({ detail: "rejected" }, 409));
    const capture = captureExperiences();

    await expect(placeBlock(BODY)).rejects.toThrow("POST /write/blocks failed");
    expect(capture.seen).toEqual([]);

    capture.teardown();
  });

  it.each([
    {},
    { outline_block_id: null },
    { outline_block_id: "" },
    { outline_block_id: "   " },
  ])("rejects malformed 2xx identity without reacting: %j", async (body) => {
    apiFetchMock.mockResolvedValueOnce(response(body));
    const capture = captureExperiences();

    await expect(placeBlock(BODY)).rejects.toThrow(
      "POST /write/blocks returned an invalid outline_block_id",
    );
    expect(capture.seen).toEqual([]);

    capture.teardown();
  });
});
