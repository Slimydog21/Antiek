/**
 * Tests for the useKreaScene hook + its pure resolver (SPR-02 M5).
 *
 * Covers (acceptance criteria): success (mocked fetch), disabled (typed 503
 * fallback), and error→fallback (fetch rejects). Also asserts the placeholder
 * is DETERMINISTIC across calls so SPR-04 snapshots are stable. Zero network:
 * the fetch seam is injected, not hit.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";

import { resolveScene, useKreaScene } from "./useKreaScene";
import { deterministicPlaceholder, sceneKeyOf } from "./placeholder";
import { useKreaScene as mockHook, mockReadyScene } from "./__mocks__/useKreaScene";
import type { SceneResult, SceneState } from "../api/krea";

const SCENE: SceneState = { mood: "calm", dayNight: "day", season: "summer" };

afterEach(() => cleanup());

describe("resolveScene", () => {
  it("success: returns ready art from a mocked fetch (no network)", async () => {
    const fetchScene = async (): Promise<SceneResult> => ({
      enabled: true,
      isFallback: false,
      image_url: "https://img/live.png",
      scene_key: "calm|day|summer",
      cached: false,
    });
    const r = await resolveScene(SCENE, fetchScene);
    expect(r.status).toBe("ready");
    expect(r.isFallback).toBe(false);
    expect(r.error).toBeNull();
    expect(r.art?.image_url).toBe("https://img/live.png");
  });

  it("disabled: a typed 503 fallback → deterministic placeholder, no throw", async () => {
    const fetchScene = async (): Promise<SceneResult> => ({
      enabled: false,
      isFallback: true,
      reason: "no_key",
      scene_key: "calm|day|summer",
    });
    const r = await resolveScene(SCENE, fetchScene);
    expect(r.status).toBe("fallback");
    expect(r.isFallback).toBe(true);
    expect(r.error).toBe("no_key");
    // Placeholder present + deterministic.
    expect(r.art?.image_url).toBe(deterministicPlaceholder(SCENE));
    expect(r.art?.scene_key).toBe(sceneKeyOf(SCENE));
  });

  it("error→fallback: a rejecting fetch never throws; yields the placeholder", async () => {
    const fetchScene = async (): Promise<SceneResult> => {
      throw new Error("boom");
    };
    const r = await resolveScene(SCENE, fetchScene);
    expect(r.status).toBe("fallback");
    expect(r.isFallback).toBe(true);
    expect(r.art?.image_url).toBe(deterministicPlaceholder(SCENE));
  });

  it("over-budget reason is surfaced honestly as the error", async () => {
    const fetchScene = async (): Promise<SceneResult> => ({
      enabled: false,
      isFallback: true,
      reason: "over_daily_budget",
      scene_key: "calm|day|summer",
    });
    const r = await resolveScene(SCENE, fetchScene);
    expect(r.isFallback).toBe(true);
    expect(r.error).toBe("over_daily_budget");
  });
});

describe("useKreaScene (the React hook)", () => {
  it("seeds the deterministic placeholder synchronously (never a flash of nothing)", () => {
    // First render — BEFORE any async resolve. art must already be the
    // placeholder so SPR-04's background paints something on frame one.
    const fetchScene = async (): Promise<SceneResult> =>
      ({ enabled: false, isFallback: true, reason: "no_key", scene_key: "calm|day|summer" });
    const { result } = renderHook(() => useKreaScene(SCENE, fetchScene));
    // Interim, pre-flush: loading, but art is non-null and IS the placeholder.
    expect(result.current.status).toBe("loading");
    expect(result.current.art?.image_url).toBe(deterministicPlaceholder(SCENE));
    expect(result.current.art?.scene_key).toBe(sceneKeyOf(SCENE));
  });

  it("ready art on success: swaps the placeholder for live art", async () => {
    const fetchScene = async (): Promise<SceneResult> => ({
      enabled: true,
      isFallback: false,
      image_url: "https://img/live.png",
      scene_key: "calm|day|summer",
      cached: false,
    });
    const { result } = renderHook(() => useKreaScene(SCENE, fetchScene));
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.isFallback).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.art?.image_url).toBe("https://img/live.png");
  });

  it("falls back (never throws) when the API is disabled (503)", async () => {
    // The disabled/over-budget/kill-switch path: the client returns the typed
    // 503 fallback signal, NOT a throw. The hook must collapse it to a
    // deterministic placeholder. Asserting synchronously here would read the
    // interim 'loading' seed, so we await the resolve's microtask via waitFor
    // (which also lets the hook's own .catch consume any rejection — no leak).
    const fetchScene = async (): Promise<SceneResult> =>
      ({ enabled: false, isFallback: true, reason: "no_key", scene_key: "calm|day|summer" });
    const { result } = renderHook(() => useKreaScene(SCENE, fetchScene));
    await waitFor(() => expect(result.current.status).toBe("fallback"));
    // The guarantee, fully verified post-flush — NOT weakened:
    expect(result.current.isFallback).toBe(true);
    expect(result.current.error).toBe("no_key");
    expect(result.current.art?.image_url).toBe(deterministicPlaceholder(SCENE));
    expect(result.current.art?.scene_key).toBe(sceneKeyOf(SCENE));
  });

  it("recovers on network error: a rejecting fetch never throws, yields the placeholder", async () => {
    // A genuine throw escaping the fetch seam (offline / unexpected). The hook
    // must STILL never throw and must render the deterministic placeholder.
    const fetchScene = async (): Promise<SceneResult> => {
      throw new Error("boom");
    };
    const { result } = renderHook(() => useKreaScene(SCENE, fetchScene));
    await waitFor(() => expect(result.current.status).toBe("fallback"));
    expect(result.current.isFallback).toBe(true);
    // resolveScene surfaces the thrown reason honestly (never null/silent).
    expect(result.current.error).toBe("boom");
    expect(result.current.art?.image_url).toBe(deterministicPlaceholder(SCENE));
    expect(result.current.art?.scene_key).toBe(sceneKeyOf(SCENE));
  });
});

describe("deterministicPlaceholder", () => {
  it("is byte-stable for the same scene-state (snapshot-safe)", () => {
    expect(deterministicPlaceholder(SCENE)).toBe(deterministicPlaceholder(SCENE));
  });

  it("differs for a different scene-state", () => {
    const night: SceneState = { mood: "calm", dayNight: "night", season: "summer" };
    expect(deterministicPlaceholder(SCENE)).not.toBe(deterministicPlaceholder(night));
  });

  it("is a usable data-URI", () => {
    expect(deterministicPlaceholder(SCENE).startsWith("data:image/svg+xml,")).toBe(true);
  });

  it("scene key matches the server normalization (case/space-insensitive)", () => {
    expect(sceneKeyOf({ mood: "Calm ", dayNight: "Day", season: "Summer" }))
      .toBe("calm|day|summer");
  });
});

describe("__mocks__/useKreaScene", () => {
  it("default mock is always the deterministic fallback", () => {
    const r = mockHook(SCENE);
    expect(r.isFallback).toBe(true);
    expect(r.status).toBe("fallback");
    expect(r.art?.image_url).toBe(deterministicPlaceholder(SCENE));
  });

  it("mockReadyScene yields a ready live-art fake", () => {
    const fake = mockReadyScene("https://img/fixed.png");
    const r = fake(SCENE);
    expect(r.status).toBe("ready");
    expect(r.isFallback).toBe(false);
    expect(r.art?.image_url).toBe("https://img/fixed.png");
  });
});
