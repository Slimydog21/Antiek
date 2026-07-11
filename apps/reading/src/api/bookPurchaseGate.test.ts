import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  PurchaseGateHttpError,
  formatPurchaseGateSummary,
  parsePurchaseGateDecision,
  postPurchaseGate,
} from "./bookPurchaseGate";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => mockFetch.mockReset());
afterEach(() => vi.restoreAllMocks());

const sample = {
  title: "Unknown Book",
  author: null,
  purchase_intent_allowed: true,
  purchase_executed: false,
  path: "purchase_intent_after_free_miss",
  reasons: [],
  notes: ["purchase_executed=false"],
  free_copy_freely_available: false,
  authority: "purchase_gate_advisory",
};

describe("parsePurchaseGateDecision", () => {
  it("parses allow", () => {
    const d = parsePurchaseGateDecision(sample);
    expect(d.purchase_intent_allowed).toBe(true);
    expect(d.purchase_executed).toBe(false);
  });

  it("rejects executed true and free hit + allow", () => {
    expect(() =>
      parsePurchaseGateDecision({ ...sample, purchase_executed: true }),
    ).toThrow(/purchase_executed/);
    expect(() =>
      parsePurchaseGateDecision({
        ...sample,
        free_copy_freely_available: true,
        purchase_intent_allowed: true,
      }),
    ).toThrow(/freely_available/);
  });

  it("rejects allow with free_copy null unless skip path", () => {
    expect(() =>
      parsePurchaseGateDecision({
        ...sample,
        free_copy_freely_available: null,
        purchase_intent_allowed: true,
        path: "purchase_intent_after_free_miss",
      }),
    ).toThrow(/skip_free_copy/);
    const skipOk = parsePurchaseGateDecision({
      ...sample,
      free_copy_freely_available: null,
      purchase_intent_allowed: true,
      path: "skip_free_copy",
    });
    expect(skipOk.path).toBe("skip_free_copy");
  });
});

describe("postPurchaseGate", () => {
  it("POSTs after free miss", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sample,
      text: async () => "",
    } as unknown as Response);
    const d = await postPurchaseGate({
      title: "Unknown Book",
      free_copy_preflight: { freely_available: false },
      skip_free_copy: false,
    });
    expect(d.path).toMatch(/free_miss/);
  });

  it("rejects skip without ack without network", async () => {
    await expect(
      postPurchaseGate({
        title: "X",
        skip_free_copy: true,
        operator_skip_acknowledged: false,
      }),
    ).rejects.toThrow(/operator_skip_acknowledged/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => "bad",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postPurchaseGate({
        title: "X",
        free_copy_preflight: { freely_available: false },
        skip_free_copy: false,
      }),
    ).rejects.toBeInstanceOf(PurchaseGateHttpError);
  });
});

describe("formatPurchaseGateSummary", () => {
  it("summarizes", () => {
    expect(formatPurchaseGateSummary(parsePurchaseGateDecision(sample))).toMatch(
      /intent_allowed=true/,
    );
  });
});
