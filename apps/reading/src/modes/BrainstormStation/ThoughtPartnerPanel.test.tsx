/**
 * Thought partner panel — session desk brand + living-TV highlight on CTA.
 */
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import ThoughtPartnerPanel from "./ThoughtPartnerPanel";
import { WERNER_EXPERIENCE_EVENT } from "../../werner/reactionBus";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => cleanup());

describe("ThoughtPartnerPanel living-TV brand", () => {
  it("renders session thought-partner desk key art in the UI", () => {
    render(<ThoughtPartnerPanel />);
    expect(screen.getByTestId("thought-partner-panel")).toBeTruthy();
    expect(screen.getByTestId("thought-partner-desk-brand")).toBeTruthy();
    const art = screen.getByTestId(
      "thought-partner-desk-art",
    ) as HTMLImageElement;
    expect(art.getAttribute("src")).toBeTruthy();
    expect(art.getAttribute("src") ?? "").toMatch(
      /werner_thought_partner_desk_session_v1/,
    );
  });

  it("CTA opens sidecar and emits Werner highlight (living-TV)", () => {
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    const onSide = () => seen.push("sidecar");
    window.addEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    window.addEventListener("antiek:aisidecar:toggle", onSide);
    render(<ThoughtPartnerPanel />);
    fireEvent.click(screen.getByTestId("thought-partner-open-sidecar"));
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, onExp);
    window.removeEventListener("antiek:aisidecar:toggle", onSide);
    expect(seen).toContain("highlight");
    expect(seen).toContain("sidecar");
  });
});
