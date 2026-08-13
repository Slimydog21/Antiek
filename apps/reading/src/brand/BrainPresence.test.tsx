/**
 * BrainPresence.test.tsx — the ambient background mark renders faint and
 * inert to input.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import BrainPresence from "./BrainPresence";

afterEach(cleanup);

describe("BrainPresence", () => {
  it("renders an aria-hidden faint brain", () => {
    const { container } = render(<BrainPresence />);
    const layer = container.firstChild as HTMLElement;
    expect(layer.getAttribute("aria-hidden")).toBe("true");
    expect(layer.classList.contains("brain-presence")).toBe(true);
    expect(layer.style.pointerEvents).toBe("none");
    expect(layer.style.opacity).toBe("0.08");
    expect(container.querySelector("img")?.getAttribute("src")).toBeTruthy();
  });

  it("accepts size/opacity overrides", () => {
    const { container } = render(<BrainPresence size={200} opacity={0.2} />);
    const layer = container.firstChild as HTMLElement;
    expect(layer.style.width).toBe("200px");
    expect(layer.style.opacity).toBe("0.2");
  });
});
