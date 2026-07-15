import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MidnightOilPanel } from "./MidnightOilPanel";

describe("MidnightOilPanel", () => {
  afterEach(() => cleanup());

  it("builds preflight and requires ack for approval request", () => {
    render(<MidnightOilPanel />);

    fireEvent.change(screen.getByTestId("midnight-oil-goal-input"), {
      target: { value: "Map open-source agent evals" },
    });
    fireEvent.click(screen.getByTestId("midnight-oil-add-goal"));

    expect(screen.getByTestId("midnight-oil-preflight")).toBeTruthy();
    expect(screen.getByTestId("midnight-oil-spend-auth").textContent).toMatch(
      /spend_authorized=false/,
    );

    const btn = screen.getByTestId("midnight-oil-request") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(screen.getByTestId("midnight-oil-ack"));
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);

    const json = screen.getByTestId("midnight-oil-request-json").textContent ?? "";
    expect(json).toMatch(/operator_request_only/);
    expect(json).toMatch(/spend_authorized": false/);
  });

  it("emits deep_research_start when approval request succeeds", () => {
    const seen: string[] = [];
    const onExp = (e: Event) => {
      const d = (e as CustomEvent<{ experience?: string }>).detail?.experience;
      if (d) seen.push(d);
    };
    window.addEventListener("antiek:werner-experience", onExp);
    render(<MidnightOilPanel />);
    fireEvent.change(screen.getByTestId("midnight-oil-goal-input"), {
      target: { value: "Night eval sweep" },
    });
    fireEvent.click(screen.getByTestId("midnight-oil-add-goal"));
    fireEvent.click(screen.getByTestId("midnight-oil-ack"));
    fireEvent.click(screen.getByTestId("midnight-oil-request"));
    expect(seen).toContain("deep_research_start");
    window.removeEventListener("antiek:werner-experience", onExp);
  });
});
