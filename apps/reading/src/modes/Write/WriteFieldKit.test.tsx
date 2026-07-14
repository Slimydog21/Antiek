import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const hit = {
  node_id: "node-private-id",
  label: "A durable market signal",
  node_type: "insight",
  document_title: "Field notes",
  document_id: "doc-1",
  source_tier: 1,
  score: 0.9,
};

vi.mock("./BlockRepository", () => ({
  default: ({ onAdd }: { onAdd: (value: typeof hit) => void }) => (
    <button type="button" onClick={() => onAdd(hit)}>Pick durable signal</button>
  ),
}));

import WriteFieldKit from "./WriteFieldKit";

afterEach(cleanup);

describe("WriteFieldKit", () => {
  it("is mobile-only, opens a provenance tray, and returns focus on Escape", async () => {
    render(<WriteFieldKit onSelect={vi.fn()} />);
    const kit = screen.getByTestId("write-field-kit");
    expect(kit.className).toContain("lg:hidden");
    const trigger = screen.getByRole("button", { name: /evidence blocks/i });
    await userEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: /choose evidence to place/i })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /^close$/i }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await new Promise((resolve) => requestAnimationFrame(resolve));
    expect(document.activeElement).toBe(trigger);
  });

  it("hands the selected repository block to the outline owner and closes", async () => {
    const onSelect = vi.fn();
    render(<WriteFieldKit onSelect={onSelect} />);
    await userEvent.click(screen.getByRole("button", { name: /evidence blocks/i }));
    await userEvent.click(screen.getByRole("button", { name: /pick durable signal/i }));
    expect(onSelect).toHaveBeenCalledWith(hit);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes from the backdrop and returns focus to its one trigger", async () => {
    render(<WriteFieldKit onSelect={vi.fn()} />);
    const trigger = screen.getByRole("button", { name: /evidence blocks/i });
    await userEvent.click(trigger);
    await userEvent.click(screen.getByTestId("write-field-kit-backdrop"));
    expect(screen.queryByRole("dialog")).toBeNull();
    await new Promise((resolve) => requestAnimationFrame(resolve));
    expect(document.activeElement).toBe(trigger);
  });

  it("contains forward, reverse, and escaped focus while open", async () => {
    render(<WriteFieldKit onSelect={vi.fn()} />);
    const trigger = screen.getByRole("button", { name: /evidence blocks/i });
    await userEvent.click(trigger);
    const close = screen.getByRole("button", { name: /^close$/i });
    const pick = screen.getByRole("button", { name: /pick durable signal/i });

    pick.focus();
    fireEvent.keyDown(window, { key: "Tab" });
    expect(document.activeElement).toBe(close);
    close.focus();
    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(pick);
    trigger.focus();
    fireEvent.keyDown(window, { key: "Tab" });
    expect(document.activeElement).toBe(close);
  });
});
