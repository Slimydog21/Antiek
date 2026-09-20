import { describe, expect, it, vi } from "vitest";
import { apiFetch } from "../lib/api";
import {
  fetchSettingsModelCatalog,
  parseSettingsModelCatalog,
  parseUserModelsResponse,
} from "./settingsModels";

vi.mock("../lib/api", () => ({ API_BASE: "", apiFetch: vi.fn() }));

const provider = (catalogId: string, modelId: string) => ({
  catalog_id: catalogId,
  display: catalogId.toUpperCase(),
  provider_kind: "openai_compat",
  default_base_url: `https://${catalogId}.example`,
  models: [
    {
      id: modelId,
      label: modelId.toUpperCase(),
      snapshot: `${modelId}-snapshot`,
    },
  ],
  pricing_source: `https://${catalogId}.example/pricing`,
});

describe("parseUserModelsResponse", () => {
  const executable = {
    id: "user-1", provider_kind: "anthropic", provider_catalog_id: "anthropic",
    model_id: "claude", display_name: "Claude", base_url: null, enabled: true,
    key_present: true, registered: true, route_eligible: true, pricing_status: "known",
    hard_ceiling_eligible: true, execution_status: "executable", rate_snapshot: "rates-1",
  };

  it("accepts the strict non-secret inventory contract", () => {
    expect(parseUserModelsResponse({ models: [executable], count: 1, stale_registered: [], source: "server" }).models[0]).toEqual(executable);
  });

  it.each([
    { models: [executable], count: 0, stale_registered: [], source: "server" },
    { models: [{ ...executable, execution_status: "maybe" }], count: 1, stale_registered: [], source: "server" },
    { models: [{ ...executable, key_present: "yes" }], count: 1, stale_registered: [], source: "server" },
    { models: [executable], count: 1, stale_registered: [], source: "server", api_key: "sk-secret" },
    { models: [{ ...executable, credential: "sk-secret" }], count: 1, stale_registered: [], source: "server" },
    { models: [executable, { ...executable }], count: 2, stale_registered: [], source: "server" },
    { models: [{ ...executable, rate_snapshot: 4 }], count: 1, stale_registered: [], source: "server" },
  ])("rejects malformed inventory", (body) => {
    let message = "";
    try { parseUserModelsResponse(body); } catch (error) { message = error instanceof Error ? error.message : String(error); }
    expect(message).toBe("Invalid user model inventory response.");
    expect(message).not.toContain("sk-");
  });
});

describe("parseSettingsModelCatalog", () => {
  it("strictly parses the server contract without changing tuple order", () => {
    const parsed = parseSettingsModelCatalog({
      providers: [provider("second", "model-b"), provider("first", "model-a")],
      count: 2,
    });
    expect(parsed.providers.map((item) => item.catalog_id)).toEqual([
      "second",
      "first",
    ]);
    expect(parsed.providers.map((item) => item.models[0].id)).toEqual([
      "model-b",
      "model-a",
    ]);
  });

  it.each([
    { providers: [], count: 1 },
    {
      providers: [provider("duplicate", "a"), provider("duplicate", "b")],
      count: 2,
    },
    {
      providers: [{ ...provider("openai", "a"), provider_kind: "other" }],
      count: 1,
    },
    {
      providers: [
        { ...provider("openai", "a"), models: [{ id: "a", label: "A" }] },
      ],
      count: 1,
    },
    { providers: [provider("custom", "a")], count: 1 },
    {
      providers: [provider("openai", "a")],
      count: 1,
      api_key: "sk-top-secret",
    },
    {
      providers: [
        { ...provider("openai", "a"), credential: "sk-provider-secret" },
      ],
      count: 1,
    },
    {
      providers: [
        {
          ...provider("openai", "a"),
          models: [
            {
              id: "a",
              label: "A",
              snapshot: "snapshot",
              api_key: "sk-model-secret",
            },
          ],
        },
      ],
      count: 1,
    },
    {
      providers: [
        {
          ...provider("openai", "a"),
          models: [
            { id: "a", label: "A", snapshot: "one" },
            { id: "a", label: "A duplicate", snapshot: "two" },
          ],
        },
      ],
      count: 1,
    },
  ])("rejects malformed or ambiguous catalog data", (body) => {
    expect(() => parseSettingsModelCatalog(body)).toThrow(
      "Invalid settings model catalog response.",
    );
  });

  it.each([
    {
      providers: [provider("openai", "a")],
      count: 1,
      api_key: "sk-fetch-top-secret",
    },
    {
      providers: [
        { ...provider("openai", "a"), api_key: "sk-fetch-provider-secret" },
      ],
      count: 1,
    },
    {
      providers: [
        {
          ...provider("openai", "a"),
          models: [
            {
              id: "a",
              label: "A",
              snapshot: "snapshot",
              api_key: "sk-fetch-model-secret",
            },
          ],
        },
      ],
      count: 1,
    },
  ])(
    "rejects secret-shaped API extras with a value-free error",
    async (body) => {
      vi.mocked(apiFetch).mockResolvedValueOnce(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
      let message = "";
      try {
        await fetchSettingsModelCatalog();
      } catch (error) {
        message = error instanceof Error ? error.message : String(error);
      }
      expect(message).toBe("Invalid settings model catalog response.");
      expect(message).not.toContain("sk-");
    },
  );
});
