import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ModelInventoryPanel from "./ModelInventoryPanel";
import type { InventoryModelRow } from "../../api/modelDecisionInventory";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const rows: InventoryModelRow[] = [
  {
    provider_id: "openai",
    ready: true,
    primary_model: "gpt-5.5",
    tier_bindings: ["reasoning"],
  },
  {
    provider_id: "local",
    ready: false,
    primary_model: "local-flash",
    tier_bindings: ["flash"],
  },
  {
    provider_id: "empty",
    ready: true,
    primary_model: null,
  },
];

describe("ModelInventoryPanel", () => {
  it("lists ready and not-ready models; skips missing primary_model", () => {
    render(<ModelInventoryPanel rows={rows} />);
    expect(screen.getByTestId("model-inventory-row-gpt-5.5").getAttribute("data-ready")).toBe(
      "true",
    );
    expect(
      screen.getByTestId("model-inventory-row-local-flash").getAttribute("data-ready"),
    ).toBe("false");
    expect(screen.queryByTestId("model-inventory-row-")).toBeNull();
    // empty primary skipped — only two rows
    expect(screen.getByTestId("model-inventory-list").querySelectorAll("li").length).toBe(
      2,
    );
  });

  it("shows honest empty inventory", () => {
    render(<ModelInventoryPanel rows={[]} />);
    expect(screen.getByTestId("model-inventory-empty").textContent).toMatch(
      /No rankable models/,
    );
  });

  it("selects only ready models", () => {
    const onSelect = vi.fn();
    render(<ModelInventoryPanel rows={rows} onSelectModel={onSelect} />);
    fireEvent.click(screen.getByTestId("model-inventory-select-gpt-5.5"));
    expect(screen.getByTestId("model-inventory-selected").textContent).toMatch(
      /gpt-5.5/,
    );
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ model_id: "gpt-5.5", enabled: true }),
    );
    // not-ready button disabled — click should not select
    fireEvent.click(screen.getByTestId("model-inventory-select-local-flash"));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("loadFn re-validates rows and surfaces invent ready failures", async () => {
    const loadFn = vi.fn(async () => [
      { provider_id: "x", ready: "yes", primary_model: "m" },
    ]);
    render(<ModelInventoryPanel loadFn={loadFn} />);
    fireEvent.click(screen.getByTestId("model-inventory-load"));
    await waitFor(() => {
      expect(screen.getByTestId("model-inventory-error").textContent).toMatch(
        /ready must be boolean/,
      );
    });
  });

  it("loadFn success maps inventory", async () => {
    const loadFn = vi.fn(async () => rows);
    render(<ModelInventoryPanel loadFn={loadFn} />);
    fireEvent.click(screen.getByTestId("model-inventory-load"));
    await waitFor(() => {
      expect(screen.getByTestId("model-inventory-row-gpt-5.5")).toBeTruthy();
    });
  });

  it("rejects malformed direct rows (invented ready) without listing", () => {
    render(
      <ModelInventoryPanel
        rows={
          [
            {
              provider_id: "x",
              ready: "yes" as unknown as boolean,
              primary_model: "m",
            },
          ] as InventoryModelRow[]
        }
      />,
    );
    expect(screen.getByTestId("model-inventory-error").textContent).toMatch(
      /ready must be boolean/,
    );
    expect(screen.queryByTestId("model-inventory-list")).toBeNull();
  });
});
