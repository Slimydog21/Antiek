import { describe, expect, it, vi } from "vitest";
import { apiFetch } from "../lib/api";
import {
  fetchSettingsModelCatalog,
  parseSettingsModelCatalog,
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
