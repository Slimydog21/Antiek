/**
 * Sources.brand.test.tsx — living-TV densify on the Sources door.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("../../lib/api", () => ({
  ingestSource: vi.fn(async () => ({ ok: true })),
}));

import Sources from "./index";

afterEach(() => {
  cleanup();
});

describe("Sources — living-TV brand densify", () => {
  it("renders session thinking + living-TV brand chrome", () => {
    render(<Sources />);
    expect(screen.getByText("Sources")).toBeTruthy();
    expect(screen.getByTestId("sources-home-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "sources-home-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });

  it("emits highlight living-TV beat when ingest starts", () => {
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent<{ experience?: string }>).detail?.experience;
      if (d) seen.push(d);
    };
    window.addEventListener("antiek:werner-experience", onExp);
    render(<Sources />);
    const input = screen.getByPlaceholderText(/arxiv\.org\/abs/i);
    fireEvent.change(input, {
      target: { value: "https://arxiv.org/abs/1706.03762" },
    });
    fireEvent.submit(input.closest("form")!);
    expect(seen).toContain("highlight");
    window.removeEventListener("antiek:werner-experience", onExp);
  });
});
