/**
 * Tests for the Krea scene-art client (SPR-02 M4).
 *
 * `fetch` is mocked (no network). Covers: success (200 art), the typed 503
 * fallback signal (disabled), offline (fetch rejects → synthesized fallback),
 * and partial/garbage JSON (200 but unparseable → fallback). The client never
 * references a key — it only talks to /krea/*.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { generateImage, getJob, isSceneArt, requestScene } from "./krea";
import type { SceneState } from "./krea";

const SCENE: SceneState = { mood: "calm", dayNight: "day", season: "summer" };

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
    blob: async () => new Blob(),
  } as unknown as Response;
}

function badJsonResponse(status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      throw new SyntaxError("Unexpected token");
    },
    text: async () => "<html>not json</html>",
  } as unknown as Response;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("requestScene", () => {
  it("success: 200 art is returned and discriminates as SceneArt", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(200, {
        enabled: true,
        isFallback: false,
        image_url: "https://img/x.png",
        scene_key: "calm|day|summer",
        cached: false,
      }),
    );
    const r = await requestScene(SCENE);
    expect(isSceneArt(r)).toBe(true);
    if (isSceneArt(r)) {
      expect(r.image_url).toBe("https://img/x.png");
      expect(r.scene_key).toBe("calm|day|summer");
    }
  });

  it("disabled: a 503 returns the typed fallback signal (no throw)", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(503, {
        enabled: false,
        isFallback: true,
        reason: "no_key",
        scene_key: "calm|day|summer",
      }),
    );
    const r = await requestScene(SCENE);
    expect(isSceneArt(r)).toBe(false);
    expect(r.enabled).toBe(false);
    if (!isSceneArt(r)) {
      expect(r.reason).toBe("no_key");
      expect(r.scene_key).toBe("calm|day|summer");
    }
  });

  it("offline: a rejecting fetch yields a synthesized fallback (no throw)", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new TypeError("Failed to fetch"),
    );
    const r = await requestScene(SCENE);
    expect(isSceneArt(r)).toBe(false);
    if (!isSceneArt(r)) {
      expect(r.reason).toBe("offline");
    }
  });

  it("garbage JSON on a 200 collapses to a fallback, not a crash", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      badJsonResponse(200),
    );
    const r = await requestScene(SCENE);
    expect(isSceneArt(r)).toBe(false);
    if (!isSceneArt(r)) {
      expect(r.reason).toBe("upstream_bad_response");
    }
  });

  it("an unexpected non-200/503 status throws (a real bug is not swallowed)", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(418, { teapot: true }),
    );
    await expect(requestScene(SCENE)).rejects.toThrow(/HTTP 418/);
  });
});

describe("generateImage / getJob", () => {
  it("generateImage success returns job_id", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(200, { enabled: true, job_id: "job_1", status: "queued" }),
    );
    const r = await generateImage("a mountain");
    expect(r.enabled).toBe(true);
    if (r.enabled) expect(r.job_id).toBe("job_1");
  });

  it("generateImage 503 returns the typed fallback signal", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(503, { enabled: false, isFallback: true, reason: "kill_switch" }),
    );
    const r = await generateImage("x");
    expect(r.enabled).toBe(false);
    if (!r.enabled) expect(r.reason).toBe("kill_switch");
  });

  it("getJob success returns the job status + image_url", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(200, {
        enabled: true, job_id: "job_1", status: "completed",
        image_url: "https://img/done.png",
      }),
    );
    const r = await getJob("job_1");
    expect(r.enabled).toBe(true);
    if (r.enabled) {
      expect(r.status).toBe("completed");
      expect(r.image_url).toBe("https://img/done.png");
    }
  });
});
