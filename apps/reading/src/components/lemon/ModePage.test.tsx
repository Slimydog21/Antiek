import { afterEach, describe, it, expect } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

import { ModePage } from "./ModePage";

afterEach(() => {
  cleanup();
});

describe("ModePage — shell contract", () => {
  it("renders the standard serif title + lede header", () => {
    render(
      <ModePage title="Billing summary" lede="Pay-as-you-go.">
        <p>body</p>
      </ModePage>,
    );
    const h1 = screen.getByRole("heading", { level: 1, name: "Billing summary" });
    expect(h1.className).toContain("font-serif");
    expect(h1.className).toContain("text-2xl");
    expect(screen.getByText("Pay-as-you-go.")).toBeTruthy();
  });

  it("paints the page ramp, not the card tones (D5)", () => {
    const { container } = render(<ModePage title="t">x</ModePage>);
    const root = container.firstElementChild;
    expect(root?.className).toContain("bg-ice-2");
    expect(root?.className).toContain("dark:bg-space-2");
    expect(root?.className).toContain("h-full");
    expect(root?.className).toContain("overflow-y-auto");
    expect(root?.className).not.toContain("h-screen");
  });

  it("applies the width tier to the content column", () => {
    const { container } = render(
      <ModePage title="t" width="lg">
        x
      </ModePage>,
    );
    const main = container.querySelector("main");
    expect(main?.className).toContain("max-w-4xl");
  });

  it("replaces the standard header when a bespoke header is given", () => {
    render(
      <ModePage title="ignored" header={<h1>Custom header</h1>}>
        <p>body</p>
      </ModePage>,
    );
    expect(screen.getByRole("heading", { name: "Custom header" })).toBeTruthy();
    expect(screen.queryByText("ignored")).toBeNull();
  });

  it("renders no header when neither title nor header is given", () => {
    const { container } = render(<ModePage>only children</ModePage>);
    expect(container.querySelector("header")).toBeNull();
    expect(screen.getByText("only children")).toBeTruthy();
  });
});
